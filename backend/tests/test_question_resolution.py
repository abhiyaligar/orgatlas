"""Graph-driven question resolution.

These are the routing rules that decide what ``/ask`` retrieves. They are pure
functions over a resolved entity list, so they can be tested without a graph,
and the cases below are the specific misroutings this design was built to
remove: a word in the wrong question redirecting it, and a better textual match
hijacking a question it cannot actually answer.
"""

from app.services.question_resolution import (
    INTENT_DECISION,
    INTENT_FILE,
    INTENT_HISTORY,
    INTENT_IMPACT,
    INTENT_ONBOARDING,
    INTENT_OWNERSHIP,
    INTENT_SYMBOL,
    ResolvedEntity,
    candidate_terms,
    choose_route,
    score_signals,
    subject_terms,
)


def entity(label: str, name: str, term: str = "", quality: int = 0) -> ResolvedEntity:
    return ResolvedEntity(
        term=term or name,
        entity_id=f"{label}:{name}",
        label=label,
        name=name,
        quality=quality,
    )


# --- term extraction --------------------------------------------------------


def test_question_words_are_not_offered_as_terms():
    terms = [term.lower() for term in candidate_terms("What is the graph and why does it matter?")]
    assert "what" not in terms
    assert "the" not in terms
    assert "and" not in terms


def test_a_quoted_name_is_kept_verbatim():
    terms = candidate_terms('What does "open_batch" do?')
    assert "open_batch" in terms


def test_a_filename_is_recognised():
    terms = candidate_terms("Describe the graph.rs module")
    assert "graph.rs" in terms


def test_consecutive_capitalised_words_form_one_term():
    """Keeps "Token Service" whole so it can outmatch a symbol called Token."""
    terms = candidate_terms("Who should I contact before changing Token Service?")
    assert "Token Service" in terms


def test_identifiers_with_underscores_are_recognised():
    terms = candidate_terms("Explain open_batch in the parser")
    assert "open_batch" in terms


def test_no_terms_from_an_empty_question():
    assert candidate_terms("   ") == []


# --- phrase signals ---------------------------------------------------------


def test_signals_survive_trailing_punctuation():
    """A comma must not hide the phrase it follows."""
    signals = score_signals("Which incident led to the Kafka decision, and where was it documented?")
    assert signals.get(INTENT_DECISION, 0) >= 1


def test_a_near_miss_word_does_not_match():
    """"changed" used to be routed as change-impact by substring matching."""
    signals = score_signals("What has changed recently?")
    assert INTENT_IMPACT not in signals
    assert INTENT_HISTORY in signals


def test_phrase_matching_respects_word_boundaries():
    signals = score_signals("The downstream payment risk is low")
    # "depend" must not be found inside "downstream", and "risk" is a real hit.
    assert INTENT_OWNERSHIP not in signals


# --- subject detection ------------------------------------------------------


def test_an_identifier_next_to_a_code_noun_is_the_subject():
    subjects = subject_terms("What does the open function in the FalkorDB module do?")
    assert "open" in subjects


def test_the_earliest_subject_is_the_primary_one():
    """Head of the phrase first; the repository name after it is only context."""
    subjects = subject_terms("What does the open function in the FalkorDB graph module do?")
    assert list(subjects)[0] == "open"


# --- routing ----------------------------------------------------------------


def test_an_exact_match_on_the_wrong_label_does_not_hijack_the_question():
    """A repository named FalkorDB cannot answer a question about a function."""
    route = choose_route(
        "What does the open function in the FalkorDB graph module do?",
        [
            entity("Repository", "FalkorDB", term="FalkorDB", quality=0),
            entity("CodeSymbol", "open_payload", term="open", quality=1),
        ],
    )
    assert route is not None
    assert route.intent == INTENT_SYMBOL
    assert route.entity.label == "CodeSymbol"


def test_a_symbol_does_not_hijack_a_question_about_its_service():
    """An enum called Token must not beat Service 'Token Service'."""
    route = choose_route(
        "Who should I contact before changing Token Service?",
        [
            entity("CodeSymbol", "Token", term="Token", quality=0),
            entity("Service", "Token Service", term="Token Service", quality=0),
        ],
    )
    assert route is not None
    assert route.entity.label == "Service"
    assert route.intent in (INTENT_IMPACT, INTENT_OWNERSHIP)


def test_ownership_phrase_selects_ownership_on_a_service():
    route = choose_route(
        "Who owns Token Service?",
        [entity("Service", "Token Service", term="Token Service")],
    )
    assert route.intent == INTENT_OWNERSHIP


def test_impact_phrase_selects_impact_on_a_service():
    route = choose_route(
        "What depends on Checkout Service?",
        [entity("Service", "Checkout Service", term="Checkout Service")],
    )
    assert route.intent == INTENT_IMPACT


def test_a_declaration_answers_a_code_question():
    route = choose_route(
        "What does the RedisModule_OpenKey function do?",
        [entity("CodeSymbol", "RedisModule_OpenKey", term="RedisModule_OpenKey")],
    )
    assert route.intent == INTENT_SYMBOL


def test_a_file_answers_a_describe_question():
    route = choose_route(
        "Describe the graph.rs module",
        [entity("File", "graph.rs", term="graph.rs")],
    )
    assert route.intent == INTENT_FILE


def test_history_phrase_on_a_symbol_selects_history():
    route = choose_route(
        "What has changed recently in graph.rs?",
        [entity("File", "graph.rs", term="graph.rs")],
    )
    assert route.intent == INTENT_HISTORY


def test_a_team_resolves_to_onboarding():
    route = choose_route(
        "What is the onboarding path for a new engineer on Payments?",
        [entity("Team", "Payments Core", term="Payments")],
    )
    assert route.intent == INTENT_ONBOARDING


def test_nothing_resolvable_returns_no_route():
    """Reporting insufficient evidence beats answering a different question."""
    route = choose_route("How many teams does the organization have?", [])
    assert route is None


def test_a_node_that_cannot_answer_the_question_yields_no_route():
    route = choose_route(
        "How many teams does the organization have?",
        [entity("CodeSymbol", "teams", term="teams")],
    )
    assert route is None


def test_alternates_exclude_the_chosen_subject():
    route = choose_route(
        "Who owns Token Service?",
        [
            entity("Service", "Token Service", term="Token Service"),
            entity("Document", "Token Service Runbook", term="Token", quality=1),
        ],
    )
    assert route.entity.entity_id == "Service:Token Service"
    assert all(other.entity_id != route.entity.entity_id for other in route.alternates)


def test_routing_is_stable_for_the_same_question():
    entities = [
        entity("Service", "Checkout Service", term="Checkout"),
        entity("Incident", "Checkout Cascade", term="Checkout", quality=1),
    ]
    question = "Who owns Checkout Service?"
    first = choose_route(question, entities)
    second = choose_route(question, list(reversed(entities)))
    assert first.intent == second.intent
    assert first.entity.entity_id == second.entity.entity_id


def test_named_entities_are_distinct_from_ordinary_words():
    """Only what a question names is worth checking against a decision's text.

    A verb like "move" is absent from every decision by construction, so
    flagging it would attach a correction to every answer ever asked.
    """
    from app.services.question_resolution import distinctive_terms

    named = distinctive_terms("Why did we move Checkout from Kafka to Redis, who was involved?")
    assert "Redis" in named
    assert "Kafka" in named
    assert "move" not in named
    assert "involved" not in named


def test_a_question_word_is_never_treated_as_a_named_entity():
    from app.services.question_resolution import distinctive_terms

    named = distinctive_terms("What does the open function in the FalkorDB module do?")
    assert named == ("FalkorDB",)


def test_a_single_capitalised_name_counts_as_named():
    from app.services.question_resolution import distinctive_terms

    assert "Kafka" in distinctive_terms("Why Kafka?")


# --- a resolved node may stand on its own -----------------------------------
#
# "Where is verify_auth_otp defined?" resolved to the declaration exactly and
# still reported no evidence, because the phrase list said "definition" and the
# question said "defined". Refusing a confidently resolved node is what kept the
# code-level detail unreachable through ordinary English.


def test_an_exact_name_routes_without_a_recognised_phrase():
    route = choose_route(
        "Where is verify_auth_otp defined?",
        [entity("CodeSymbol", "verify_auth_otp", term="verify_auth_otp", quality=0)],
    )

    assert route is not None
    assert route.intent == INTENT_SYMBOL
    assert route.entity.name == "verify_auth_otp"


def test_a_file_named_verbatim_routes_without_a_phrase():
    route = choose_route(
        "What changed in Navbar.jsx recently?",
        [entity("File", "Navbar.jsx", term="Navbar.jsx", quality=0)],
    )

    assert route is not None, "the question names the file exactly"


def test_defined_is_a_symbol_phrase():
    assert score_signals("Where is it defined?").get(INTENT_SYMBOL, 0) >= 1


def test_a_recognised_phrase_always_beats_a_name_on_its_own():
    with_phrase = choose_route(
        "What does verify_auth_otp do?",
        [entity("CodeSymbol", "verify_auth_otp", term="verify_auth_otp", quality=0)],
    )
    without_phrase = choose_route(
        "verify_auth_otp verify_auth_otp verify_auth_otp",
        [entity("CodeSymbol", "verify_auth_otp", term="verify_auth_otp", quality=0)],
    )

    assert with_phrase is not None and without_phrase is not None
    # Both resolve, but the phrase-supported pair is the better answer, so the
    # scoring must not let the fallback outrank a stated intent.
    assert _pair_score(with_phrase) >= _pair_score(without_phrase)


def _pair_score(route) -> int:
    """Recover the winning score from the reason the router records."""
    import re

    return int(re.search(r"score (-?\d+)", route.reason).group(1))


def test_a_prefix_of_a_real_name_still_routes():
    """"Where is the Auth class?" should reach AuthService, not bounce."""
    route = choose_route(
        "Auth class?",
        [entity("CodeSymbol", "AuthService", term="Auth", quality=1)],
    )

    assert route is not None
    assert route.entity.name == "AuthService"


def test_a_prefix_match_scores_below_an_exact_one():
    exact = choose_route(
        "x",
        [entity("CodeSymbol", "AuthService", term="AuthService", quality=0)],
    )
    prefix = choose_route(
        "x",
        [entity("CodeSymbol", "AuthService", term="Auth", quality=1)],
    )

    assert exact is not None and prefix is not None
    assert _pair_score(exact) > _pair_score(prefix)


def test_a_name_merely_containing_the_term_routes_to_nothing():
    """Naming half a word from the middle is not naming the thing."""
    route = choose_route(
        "auth auth auth",
        [entity("CodeSymbol", "send_auth_otp", term="auth", quality=2)],
    )

    assert route is None


def test_an_aggregate_question_is_not_answered_by_a_similarly_named_node():
    """The honesty rule: a count is not a declaration."""
    route = choose_route(
        "How many teams are there?",
        [entity("CodeSymbol", "teams", term="teams", quality=0)],
    )

    assert route is None


def test_a_node_cannot_carry_an_intent_its_label_cannot_answer():
    """The fallback must not let a repository answer a question about a function."""
    route = choose_route(
        "repo repo repo",
        [entity("Repository", "EstateX", term="EstateX", quality=0)],
    )

    assert route is None or route.intent != INTENT_SYMBOL


def test_a_weak_question_about_a_named_node_still_finds_it():
    """The whole point: ordinary English reaches code-level detail."""
    route = choose_route(
        "auth",
        [entity("CodeSymbol", "AuthService", term="AuthService", quality=0)],
    )

    assert route is not None
    assert route.entity.name == "AuthService"
