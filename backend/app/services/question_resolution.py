"""Graph-driven question resolution.

The first version of ``/ask`` decided what a question was about by testing
substring keywords and mapping them onto a hardcoded table of four services and
three teams. That had two failure modes worth removing rather than patching:

* A word could match the wrong intent. "Who owns Graph and what has it changed
  recently?" contains "changed", which matched the impact keywords, so the
  question was routed to change-impact analysis of a service named Graph that
  never existed.
* Nothing outside that fixed table was reachable. The ingested repository, with
  its files, commits and declarations, was in the same graph and still could not
  be asked about.

Resolution here is therefore driven by the graph. Terms are pulled out of the
question, resolved against the nodes that actually exist, and the intent is
chosen from the label that came back. Keyword signals are still used, but only
to break ties between labels, and they are matched on word boundaries so a
near-miss word cannot hijack a question.

Pure functions only. Nothing here touches the database, which is what makes the
routing rules testable without one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

# --- labels -----------------------------------------------------------------
# Labels are grouped by the question shape they can answer. A label the graph
# knows about but this table omits still resolves; it just carries no intent
# preference.

LABEL_CODE_SYMBOL = "CodeSymbol"
LABEL_FILE = "File"
LABEL_SERVICE = "Service"
LABEL_TEAM = "Team"
LABEL_ORGANIZATION = "Organization"
LABEL_DECISION = "Decision"
LABEL_INCIDENT = "Incident"
LABEL_REPOSITORY = "Repository"
LABEL_COMMIT = "Commit"

# Labels whose questions are about the organisation rather than the code.
ORG_LABELS = frozenset(
    {
        LABEL_SERVICE,
        LABEL_TEAM,
        LABEL_ORGANIZATION,
        LABEL_DECISION,
        LABEL_INCIDENT,
        LABEL_REPOSITORY,
        "Document",
        "PullRequest",
        "Ticket",
        "Technology",
        "OnboardingTopic",
    }
)

CODE_LABELS = frozenset({LABEL_CODE_SYMBOL, LABEL_FILE, LABEL_COMMIT})

# --- intents ----------------------------------------------------------------

INTENT_ONBOARDING = "onboarding"
INTENT_DECISION = "decision"
INTENT_IMPACT = "impact"
INTENT_OWNERSHIP = "ownership"
INTENT_SYMBOL = "symbol"
INTENT_FILE = "file"
INTENT_HISTORY = "commit_history"

# Phrases matched on word boundaries. Each entry is a phrase, not a stem, so
# "changed" no longer matches "change" and "owns" cannot be found inside
# "downstream".
INTENT_PHRASES: Dict[str, Tuple[str, ...]] = {
    INTENT_ONBOARDING: (
        "onboard",
        "onboarding",
        "first week",
        "new engineer",
        "learning path",
        "week one",
        "getting started",
        "join the team",
    ),
    INTENT_DECISION: (
        "why",
        "rationale",
        "decided",
        "decision",
        "chose",
        "chosen",
        "instead of",
        "reason for",
        "trade-off",
        "tradeoff",
    ),
    INTENT_IMPACT: (
        "impact",
        "affect",
        "affected",
        "affects",
        "dependency",
        "dependencies",
        "depend on",
        "depends on",
        "before changing",
        "if i change",
        "blast radius",
        "blast-radius",
        "risk",
        "breaking",
    ),
    INTENT_OWNERSHIP: (
        "who owns",
        "owner",
        "owners",
        "maintainer",
        "maintained",
        "who is responsible",
        "responsible for",
        "who should i contact",
        "who do i contact",
        "expertise",
        "expert",
        "experience",
        "relevant experience",
        "familiar with",
        "worked on",
    ),
    INTENT_HISTORY: (
        "history",
        "recently changed",
        "changed recently",
        "how often",
        "commit",
        "commits",
        "last modified",
        "touched",
        "who changed",
        "evolution",
    ),
    INTENT_SYMBOL: (
        "function",
        "method",
        "struct",
        "class",
        "enum",
        "symbol",
        "signature",
        "definition",
        # "defined" is how the word is used in a question. Without it the
        # phrase match misses and the name-only fallback has to carry it.
        "defined",
        "define",
        "implement",
        "declaration",
        "what does",
    ),
    INTENT_FILE: (
        "file",
        "module",
        "directory",
        "documentation",
        "doc comment",
        "readme",
        "describe",
        "summary of",
    ),
}

# A signal this strong means the question is about history regardless of label,
# because "what changed in X" is a history question whatever X is.
_HISTORY_OVERRIDE = ("changed recently", "recently changed", "how often", "who changed")

_QUESTION_WORDS = frozenset(
    """
    describe a about above after again against all also am an and any anybody anyone anything
    are around as at back be became because become becomes been before being below
    between both but by came can cannot come could did do does doing done down during
    each either else enough even ever every explain few for from further get give
    given goes going gone good got great had has have having he her here hers herself
    him himself his how however i if in into is it its itself just know known last
    later least less let like likely made make many may maybe me might mine more
    most much must my myself near need neither never new next no nobody none nor not
    nothing now number of off often on once one only onto or other others otherwise
    our ours ourselves out over own part particular perhaps please possible probably
    put quite rather really right said same say says see seen several shall she should
    since so some somebody someone something sometimes somewhat still such sure take
    taken than that the their theirs them themselves then there therefore these they
    this those though through thus to together too took toward towards under until up
    upon us use used uses using usually very want was way we well were what whatever
    when whenever where whereas whether which while who whoever whole whom whose why
    will with within without would yeah yes yet you your yours yourself yourselves
    """.split()
)

# Quoted spans are an explicit name from the user and outrank everything else.
_QUOTED = re.compile(r"[\"'`]([^\"'`]{2,80})[\"'`]")
# graph.rs, foo.py, src/main.rs
_FILE_LIKE = re.compile(r"^[A-Za-z0-9_./-]+\.[A-Za-z0-9_]{1,6}$")
# open_connection, RSQNTYPE_TOKEN, max_iterations
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_CAMEL = re.compile(r"[a-z][A-Z]")
# Two or more capitalised words in a row, allowing hyphen and slash joins.
_PROPER_NOUN = re.compile(r"\b[A-Z][A-Za-z0-9]*(?:[ -][A-Z][A-Za-z0-9]*)*\b")

# "the open function", "function open": the identifier adjacent to a
# code noun is what the question is about. Everything else in the sentence is
# qualifying context, and without this rule "the open function in the FalkorDB
# module" resolves to a symbol called falkordb, because that name matches the
# repository more exactly than "open" matches anything.
_CODE_NOUNS = (
    "function",
    "method",
    "class",
    "struct",
    "enum",
    "module",
    "file",
    "symbol",
    "interface",
    "type",
    "struct",
)
_SUBJECT_BEFORE = re.compile(
    r"\b([A-Za-z_][A-Za-z0-9_.]*)\s+(?:" + "|".join(_CODE_NOUNS) + r")\b", re.IGNORECASE
)
_SUBJECT_AFTER = re.compile(
    r"\b(?:" + "|".join(_CODE_NOUNS) + r")\s+([A-Za-z_][A-Za-z0-9_.]*)\b", re.IGNORECASE
)

MAX_SEARCH_TERMS = 6
MAX_CANDIDATES = 24


@dataclass(frozen=True)
class ResolvedEntity:
    """A graph node a question term resolved to.

    ``quality`` comes from the graph query, which already ranked exact name
    matches ahead of prefix and partial ones. It is carried through rather than
    recomputed so the ordering survives the trip out of Cypher.
    """

    term: str
    entity_id: str
    label: str
    name: str
    quality: int = 2

    @property
    def is_code(self) -> bool:
        return self.label in CODE_LABELS

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "ResolvedEntity":
        return cls(
            term=row["term"],
            entity_id=row["id"],
            label=row["label"],
            name=row["name"],
            quality=int(row.get("quality", 2)),
        )


@dataclass(frozen=True)
class Route:
    """The retrieval intent and the entity it should be resolved against."""

    intent: str
    entity: Optional[ResolvedEntity] = None
    alternates: Tuple[ResolvedEntity, ...] = ()
    reason: str = ""


def subject_terms(question: str) -> Dict[str, int]:
    """Identifiers the question names as its subject, mapped to their position.

    An identifier sitting next to a code noun is a candidate subject; the rest of
    the sentence describes where it lives. Several can qualify at once, as in
    "the open function in the FalkorDB graph module", where both "open" and
    "graph" sit next to a code noun but only one is what the question is about.

    Position breaks that tie. English puts the head of the phrase before its
    modifiers, so the earliest candidate is the subject and later ones are
    context.
    """
    found: Dict[str, int] = {}
    for pattern in (_SUBJECT_BEFORE, _SUBJECT_AFTER):
        for match in pattern.finditer(question):
            token = match.group(1).lower()
            if token in _QUESTION_WORDS:
                continue
            position = match.start(1)
            if token not in found or position < found[token]:
                found[token] = position

    return dict(sorted(found.items(), key=lambda item: item[1]))


def candidate_terms(question: str, max_terms: int = MAX_SEARCH_TERMS) -> List[str]:
    """Pull the terms worth resolving against the graph, best first.

    Order matters only for truncation: a quoted name, a filename and an
    identifier are far more likely to be the subject than an ordinary word, so
    they are offered first when the question is long enough to overflow.
    """
    text = question.strip()
    if not text:
        return []

    strong: List[str] = []
    weak: List[str] = []
    seen = set()

    def offer(token: str, bucket: List[str]) -> None:
        cleaned = token.strip().strip(".,;:!?'\"")
        if len(cleaned) < 3:
            return
        key = cleaned.lower()
        if key in seen or key in _QUESTION_WORDS:
            return
        seen.add(key)
        bucket.append(cleaned)

    for match in _QUOTED.finditer(text):
        offer(match.group(1), strong)

    # Capitalised words are usually entity names. Offering "Token Service" as a
    # single term is what stops the one-word match on a CodeSymbol called Token
    # from outranking the service the user meant, and offering single ones too
    # is what lets "Kafka" and "Redis" be checked against a decision's text.
    # A capitalised question word is dropped by the stopword check.
    for match in _PROPER_NOUN.finditer(text):
        span = match.group(0).strip()
        # A span such as "Why Kafka" glues a question word onto a real name, so
        # its words are offered individually as well. The stopword check drops
        # the "Why"; the "Kafka" survives as the named entity.
        for word in span.split():
            offer(word, strong)
        if len(span.split()) > 1:
            offer(span, strong)

    for raw in re.split(r"[\s,()]+", text):
        if any(raw in phrase or phrase in raw for phrase in strong):
            continue
        if _FILE_LIKE.match(raw):
            offer(raw, strong)
        elif _IDENTIFIER.match(raw) and (
            "_" in raw or _CAMEL.search(raw) or raw.isupper() and len(raw) > 3
        ):
            offer(raw, strong)
        else:
            offer(raw, weak)

    # Strong candidates first, then fill with ordinary words up to the cap.
    _LAST_STRENGTH["strong"] = strong
    return (strong + weak)[:max_terms]


# The strong bucket of the most recent extraction, so callers that care about
# which terms were *named* rather than merely mentioned can ask without
# re-parsing. Module-level because candidate_terms is a pure function that must
# keep returning a plain list.
_LAST_STRENGTH: Dict[str, List[str]] = {"strong": []}


def distinctive_terms(question: str) -> Tuple[str, ...]:
    """Terms the question names, as opposed to ordinary words it uses.

    "Why did we move Checkout from Kafka to Redis?" names Kafka and Redis and
    merely uses move, gain and involved. Only the former are worth checking
    against a decision's text: flagging a verb as uncovered would attach a
    correction to every answer ever asked.
    """
    candidate_terms(question)
    return tuple(_LAST_STRENGTH["strong"])


def score_signals(question: str) -> Dict[str, int]:
    """Count word-boundary phrase hits per intent.

    Punctuation is flattened to spaces first. Without that, "the kafka
    decision, and where" does not contain " decision " and the question loses
    the one signal that identifies it as a decision question.
    """
    flat = re.sub(r"[^a-z0-9]+", " ", question.lower())
    text = f" {flat.strip()} "
    scores: Dict[str, int] = {}
    for intent, phrases in INTENT_PHRASES.items():
        hits = 0
        for phrase in phrases:
            # Boundaries are spaces, so a phrase cannot match inside a longer
            # word. This is what stops "changed" matching "change".
            if f" {phrase} " in text:
                hits += 1
        if hits:
            scores[intent] = hits
    return scores


def _match_strength(term: str, name: str) -> int:
    """How well a graph node's name matches the term that found it."""
    t = term.lower()
    n = name.lower()
    if t == n:
        return 3
    if n.startswith(t):
        return 2
    if t in n:
        return 1
    return 0


def rank_entities(entities: Sequence[ResolvedEntity]) -> List[ResolvedEntity]:
    """Order candidates so the best-supported subject comes first.

    The primary key is the graph's own match quality, so an exact name match
    always beats a partial one regardless of label. The secondary key only
    breaks ties within one quality band, preferring an exact name the query may
    have ranked loosely, then keeping the order stable so results do not shuffle
    between identical questions.
    """
    return sorted(
        entities,
        key=lambda e: (e.quality, -_match_strength(e.term, e.name), e.entity_id),
    )


def _label_intents(entity: ResolvedEntity) -> Tuple[str, ...]:
    """The intents this node's label is able to answer.

    A label is a capability, not an assignment. A declaration can answer both
    "what is this" and "what has changed in it", and a service can answer both
    "who owns this" and "what does changing this break". Which one applies is
    decided by the question's phrase signals, so both are offered here.
    """
    label = entity.label

    if label == LABEL_CODE_SYMBOL:
        return (INTENT_SYMBOL, INTENT_HISTORY, INTENT_FILE)
    if label == LABEL_FILE:
        return (INTENT_FILE, INTENT_HISTORY)
    if label == LABEL_COMMIT:
        return (INTENT_HISTORY,)
    if label == LABEL_SERVICE:
        return (INTENT_IMPACT, INTENT_OWNERSHIP)
    if label in (LABEL_TEAM, LABEL_ORGANIZATION):
        return (INTENT_ONBOARDING,)
    if label in (LABEL_DECISION, LABEL_INCIDENT):
        return (INTENT_DECISION, INTENT_IMPACT)
    if label == LABEL_REPOSITORY:
        return (INTENT_FILE, INTENT_HISTORY)
    if label in ("Document", "PullRequest", "Ticket", "Technology"):
        return (INTENT_DECISION,)
    return ()


# An intent the question shows no sign of asking for is a poor answer even when
# the entity matches perfectly, so a weak signal still counts for something.
_UNSUPPORTED_SIGNAL = 0
# A label able to answer the question's strongest intent beats a better textual
# match that cannot answer it at all.
_LABEL_FIT = 6
# Outranks a better textual match, because naming the thing in the right role
# beats incidentally matching a repository or file name.
_SUBJECT_BONUS = 3
# A later modifier still beats an incidental match, but not the subject itself.
_SECONDARY_SUBJECT_BONUS = 1
# "What has changed recently in the Graph struct?" asks about a struct, so
# a code-noun signal points at symbol -- but the history phrase is the more
# specific claim and has to win, or the question answers about the type
# instead of its history.
_HISTORY_OVERRIDE_BONUS = 4
# What a resolved node is worth on its own, with no phrase the router
# recognises. It sits below any pair that a phrase did support, because a
# phrase is the question stating what it wants and a node name is not.
_EXACT_NAME_ONLY_SCORE = 2
_PREFIX_NAME_ONLY_SCORE = 1
_EXACT_MATCH_STRENGTH = 3
_PREFIX_MATCH_STRENGTH = 2
_EMPTY_SUBJECTS: Dict[str, int] = {}

# Questions about a how-many rather than about a thing. They are not supported,
# and a name-only fallback must not answer them: "how many teams does the
# organization have" resolves to a CodeSymbol called "teams", and returning that
# declaration would answer a different question than the one that was asked.
_AGGREGATE_PHRASES = (
    "how many",
    "how much",
    "number of",
    "count of",
    "total number",
    "list all",
    "list every",
    "percentage",
    "average",
)


def _has_history_override(question: str) -> bool:
    """True when the question explicitly asks about change over time."""
    flat = re.sub(r"[^a-z0-9]+", " ", question.lower())
    padded = f" {flat.strip()} "
    return any(f" {phrase} " in padded for phrase in _HISTORY_OVERRIDE)


def _is_aggregate_question(question: str) -> bool:
    """True when the question asks for a count or a total rather than a thing."""
    flat = re.sub(r"[^a-z0-9]+", " ", question.lower())
    padded = f" {flat.strip()} "
    return any(f" {phrase} " in padded for phrase in _AGGREGATE_PHRASES)


def _score_pair(
    entity: ResolvedEntity,
    intent: str,
    signals: Dict[str, int],
    subjects: Dict[str, int] = _EMPTY_SUBJECTS,
    question: str = "",
) -> int:
    """Rank one (node, intent) answer against the alternatives."""
    supported = signals.get(intent, _UNSUPPORTED_SIGNAL)
    strength = _match_strength(entity.term, entity.name)
    if supported <= 0:
        # The question used no phrase this router knows. That used to be fatal,
        # and it is why "where is verify_auth_otp defined" reported no evidence
        # while the graph held the declaration and the term had resolved to it
        # exactly. A name the question used verbatim is evidence in itself: the
        # node's label has already decided which intents it could answer, so
        # naming it does not smuggle in an intent the question never asked for.
        #
        # It is scored low on purpose. Any question carrying a recognised
        # phrase outranks it, and a weak or incidental name match still fails.
        if _is_aggregate_question(question):
            return -1
        # Only a name the question used verbatim. A fragment of a longer name is
        # not naming the thing: "what is our churn rate" contains "rate", which
        # prefixes "Rate limit one-time passcode sends" and "Stale exchange
        # rates", and answering it with either was answering a different
        # question. A question that genuinely means a prefix says so in its
        # words -- "where is the Auth class" carries "class", and routes on it.
        if strength >= _EXACT_MATCH_STRENGTH:
            return _EXACT_NAME_ONLY_SCORE
        return -1

    score = supported * _LABEL_FIT
    score -= entity.quality  # 0 exact beats 2 partial
    score += min(len(entity.term), 12) * 0.1  # prefer the more specific term
    if entity.label == LABEL_CODE_SYMBOL and intent in (INTENT_SYMBOL, INTENT_HISTORY):
        score += 1  # a declaration is the most precise thing we could cite
    if intent == INTENT_HISTORY and _has_history_override(question):
        score += _HISTORY_OVERRIDE_BONUS
    rank = list(subjects).index(entity.term.lower()) if entity.term.lower() in subjects else None
    if rank == 0:
        score += _SUBJECT_BONUS  # first code noun in the phrase: the subject
    elif rank is not None:
        score += _SECONDARY_SUBJECT_BONUS  # also a subject, but a modifier of it
    return score


def choose_route(
    question: str,
    entities: Sequence[ResolvedEntity],
    fallback_label: Optional[str] = None,
) -> Optional[Route]:
    """Pick the retrieval intent from the graph nodes the question resolved to.

    Every resolved node is scored against every intent its label can answer, and
    the highest-scoring pair wins. Scoring is what keeps a repository named
    FalkorDB from hijacking a question about a function inside it: the question
    asks about a function, so only a declaration can answer it well, and a text
    match alone is not enough to carry an intent the question never asked for.
    """
    signals = score_signals(question)
    subjects = subject_terms(question)

    best: Optional[Tuple[float, ResolvedEntity, str]] = None
    for entity in entities:
        for intent in _label_intents(entity):
            score = _score_pair(entity, intent, signals, subjects, question)
            if score < 0:
                continue
            if best is None or score > best[0]:
                best = (score, entity, intent)

    if best is not None:
        _, entity, intent = best
        alternates = tuple(other for other in entities if other.entity_id != entity.entity_id)
        return Route(
            intent=intent,
            entity=entity,
            alternates=alternates[:4],
            reason=f"{entity.label} '{entity.name}' -> {intent} (score {best[0]:.1f})",
        )

    # Onboarding asks about a team, not about one node, so it can be answered
    # with nothing resolved at all. "What should a new engineer learn in their
    # first week" names no entity in the graph, and the team falls back to the
    # default exactly as the interface does when nobody has picked one.
    if (
        score_signals(question).get(INTENT_ONBOARDING, 0) > 0
        and not _is_aggregate_question(question)
    ):
        return Route(
            intent=INTENT_ONBOARDING,
            entity=None,
            alternates=(),
            reason="onboarding question with no named node -> default team",
        )

    # Nothing in the graph can answer what was asked. Reporting insufficient
    # evidence is the honest outcome; a fallback here would answer a different
    # question than the one that was put.
    return None
