"""Ask-question orchestration: intent routing, evidence assembly, answer shape.

This module owns everything that happens between a question and an
``AskQuestionResponse``. Keeping it out of the route means the route only
validates input and serialises output, and it gives the answer-synthesis
boundary one place to live.

Retrieval is deliberately split from presentation. The retrieval services return
structured evidence; building the deterministic narrative from it is one step,
and asking the model to write a narrative from the same evidence is another.
The two are alternatives, never sequential, so a slow or missing provider never
blocks the deterministic answer.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple

from app.api.schemas import (
    AskQuestionResponse,
    Citation,
    EvidenceSubgraph,
    GraphEdge,
    GraphNode,
)
from app.core.config import settings
from app.evidence.service import EvidenceService
from app.graph.gateway import GraphGateway, graph_gateway
from app.llm.grounding import lower_confidence, validate_citations
from app.services.decision_service import DecisionTraceService
from app.services.impact_service import ChangeImpactService
from app.services.onboarding_service import OnboardingContextService
from app.services.ownership_service import OwnershipService
from app.services.decision_evidence_service import (
    DecisionEvidenceService,
    as_package as decision_evidence_package_fn,
)
from app.services.question_resolution import (
    INTENT_DECISION,
    INTENT_FILE,
    INTENT_HISTORY,
    INTENT_IMPACT,
    INTENT_ONBOARDING,
    INTENT_OWNERSHIP,
    INTENT_SYMBOL,
    LABEL_CODE_SYMBOL,
    LABEL_COMMIT,
    LABEL_FILE,
    LABEL_REPOSITORY,
    LABEL_SERVICE,
    ResolvedEntity,
    Route,
    candidate_terms,
    choose_route,
    distinctive_terms,
)

logger = logging.getLogger(__name__)

ONBOARDING_KEYWORDS = (
    "onboard",
    "first week",
    "new engineer",
    "learning path",
    "week one",
    "join",
)
DECISION_KEYWORDS = (
    "why",
    "kafka",
    "decision",
    "chose",
    "chosen",
    "architecture",
    "decided",
    "instead",
    "rationale",
    "reason",
)
IMPACT_KEYWORDS = (
    "impact",
    "change",
    "changing",
    "affect",
    "affecting",
    "depend",
    "before changing",
    "what depends",
    "risk",
)
OWNERSHIP_KEYWORDS = (
    "who owns",
    "owner",
    "maintainer",
    "who is responsible",
    "who should i contact",
    "expertise",
    "experience",
    "worked on",
    "expert",
)

DECISION_ENTITIES = {
    "kafka": "dec_kafka_async",
    "checkout": "dec_kafka_async",
    "synchronous": "dec_kafka_async",
    "settlement": "dec_kafka_async",
}
SERVICE_ENTITIES = {
    "checkout": "svc_checkout",
    "token": "svc_token_service",
    "billing": "svc_billing",
    "notification": "svc_notification",
}
TEAM_ENTITIES = {
    "payments": "team_payments",
    "platform": "team_platform",
    "infrastructure": "team_platform",
}

# A "why" question can land on the decision itself or on the record that
# motivated it.
DECISION_LABELS = frozenset({"Decision", "Incident", "Document", "Ticket", "PullRequest"})

DEFAULT_TEAM_ID = "team_payments"

# The package answer now carries a full description, so the fact text handed
# to the model has to fit one plus the framing around it.
MAX_FACT_CHARS = 6000
# A citation excerpt is evidence, so it is not shortened to a teaser.
MAX_EXCERPT_CHARS = 5000


def _dedupe_declarations(declarations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """De-duplicate declarations gathered from several name lookups."""
    seen = set()
    unique = []
    for declaration in declarations:
        key = declaration.get("id")
        if key in seen:
            continue
        seen.add(key)
        unique.append(declaration)
    return unique


class SynthesisProvider(Protocol):
    """The slice of the provider this service depends on."""

    available: bool

    async def generate_synthesis(self, request: Any) -> Any:
        ...


class AskService:
    """Routes a question to an approved intent and assembles its evidence."""

    def __init__(
        self,
        evidence: Optional[EvidenceService] = None,
        decisions: Optional[DecisionTraceService] = None,
        impact: Optional[ChangeImpactService] = None,
        onboarding: Optional[OnboardingContextService] = None,
        ownership: Optional[OwnershipService] = None,
        decision_evidence: Optional[DecisionEvidenceService] = None,
        gateway: Optional[GraphGateway] = None,
        provider: Optional[SynthesisProvider] = None,
    ) -> None:
        self.evidence = evidence or EvidenceService()
        # The shared gateway, not a fresh instance: one connection manager per
        # process, and it is the object tests patch to simulate an empty graph.
        self.gateway = gateway or graph_gateway
        self.decisions = decisions or DecisionTraceService(evidence=self.evidence)
        self.impact = impact or ChangeImpactService(evidence=self.evidence)
        self.onboarding = onboarding or OnboardingContextService(evidence=self.evidence)
        self.ownership = ownership or OwnershipService(evidence=self.evidence)
        self.decision_evidence = decision_evidence or DecisionEvidenceService(
            gateway=self.gateway
        )
        self._provider = provider
        self._provider_loaded = provider is not None

    @property
    def provider(self) -> Optional[SynthesisProvider]:
        """Resolve the synthesis provider.

        An explicitly injected provider always wins, so a caller can drive the
        synthesis path deliberately regardless of the global setting.
        Otherwise synthesis is on by default and loaded lazily, and
        ``ASK_SYNTHESIS_ENABLED=false`` disables it so an offline or
        cost-free run answers from graph facts only.
        """
        if self._provider is not None:
            return self._provider
        if not settings.ASK_SYNTHESIS_ENABLED:
            return None
        if not self._provider_loaded:
            self._provider_loaded = True
            try:
                from app.llm.adapter import NebiusLLMAdapter

                self._provider = NebiusLLMAdapter()
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("no synthesis provider available: %s", exc)
                self._provider = None
        return self._provider

    # --- intent routing ------------------------------------------------------

    @staticmethod
    def classify_intent(question: str) -> Optional[str]:
        """Map a question to an approved retrieval intent, or None."""
        normalized = question.lower()

        if any(keyword in normalized for keyword in ONBOARDING_KEYWORDS):
            return "onboarding"
        if any(keyword in normalized for keyword in DECISION_KEYWORDS):
            return "decision"

        asks_ownership = any(keyword in normalized for keyword in OWNERSHIP_KEYWORDS)
        asks_impact = any(keyword in normalized for keyword in IMPACT_KEYWORDS)

        if asks_ownership and not asks_impact:
            return "ownership"
        if asks_impact:
            return "impact"
        if asks_ownership:
            return "ownership"
        return None

    @staticmethod
    def resolve_entity(question: str, entity_map: Dict[str, str]) -> Optional[str]:
        normalized = question.lower()
        for keyword, entity_id in entity_map.items():
            if keyword in normalized:
                return entity_id
        return None

    def resolve_team_id(self, question: str, context: Optional[str]) -> str:
        candidate = (context or "").strip()
        if not candidate:
            candidate = self.resolve_entity(question, TEAM_ENTITIES) or DEFAULT_TEAM_ID
        return candidate if candidate.startswith("team_") else DEFAULT_TEAM_ID

    # --- evidence retrieval --------------------------------------------------

    def resolve_question(
        self, question: str
    ) -> Tuple[Optional[Route], List[ResolvedEntity]]:
        """Resolve a question against the graph.

        Two things happen here that the old keyword router could not do. Terms
        from the question are matched to the nodes that actually exist, so a
        repository ingested last week is reachable by its own name. And the
        intent is chosen from the label of the node that matched, so a word
        appearing in the wrong question can no longer redirect it: "changed" no
        longer forces change-impact analysis, because impact requires a Service
        node to analyse.
        """
        terms = candidate_terms(question)
        if not terms:
            return None, []

        # Searched across every graph, because a question can name code that
        # lives in one repository's graph and an organisation entity that lives
        # in the org graph. Each row records which graph it came from so the
        # retrieval reads the same one rather than reporting no evidence for an
        # entity it just found.
        rows = self.gateway.search_entities_by_terms(terms)
        entities = [ResolvedEntity.from_row(row) for row in rows]
        route = choose_route(question, entities)
        logger.info(
            "Ask resolved %d term(s) to %d node(s): %s",
            len(terms),
            len(entities),
            route.reason if route else "no route",
        )
        return route, entities

    def retrieve(self, question: str, context: Optional[str]) -> Optional[Dict[str, Any]]:
        """Run the approved retrieval for a question and build its evidence package.

        Returns ``None`` when nothing matches, which the caller turns into an
        explicit insufficient-evidence response rather than a guess.
        """
        route, _entities = self.resolve_question(question)
        if route is None:
            logger.info("Ask found no route for the question")
            return None

        intent = route.intent
        entity = route.entity

        if intent == INTENT_ONBOARDING:
            return self.retrieve_onboarding(question, context)
        if intent == INTENT_DECISION:
            # Rank by how much of the question each decision actually covers, not
            # by which node matched the best single term. Two decisions about the
            # same technology are separated by the terms only one of them
            # mentions, and that difference is invisible to a single-term match.
            terms = candidate_terms(question)
            ranked = self.gateway.rank_decisions_by_coverage(terms)
            if ranked:
                decision_id = ranked[0]["id"]
                package = self.retrieve_decision(decision_id)
                if package is not None:
                    package["question_terms"] = terms
                    package["coverage"] = ranked[0]["coverage"]
                    package["other_candidates"] = ranked[1:3]
                    # Only terms the question *names* are checked. A verb like
                    # "move" is absent from every decision by construction, and
                    # flagging it would put a correction on every answer.
                    covered = {str(term).lower() for term in ranked[0]["terms"]}
                    named = distinctive_terms(question)
                    package["unmatched_terms"] = [
                        term for term in named if term.lower() not in covered
                    ]
                    premise = self.decision_evidence.premise_note(
                        package["unmatched_terms"], package["other_candidates"]
                    )
                    if premise:
                        package["answer"] = "\n\n".join(premise) + "\n\n" + package["answer"]
                        package["notes"] = premise
                    return package

            decision_id = self._resolve_decision_id(question, entity)
            return self.retrieve_decision(decision_id) if decision_id else None
        if intent in (INTENT_IMPACT, INTENT_OWNERSHIP):
            service_id = self._entity_id_matching(entity, {LABEL_SERVICE})
            if service_id is None:
                service_id = self.resolve_entity(question, SERVICE_ENTITIES)
            if not service_id:
                return None
            return (
                self.retrieve_impact(service_id)
                if intent == INTENT_IMPACT
                else self.retrieve_ownership(service_id)
            )
        if intent == INTENT_SYMBOL:
            return self.retrieve_symbol(
                self._subject_name(entity) or (entity.name if entity else ""),
                graph_name=entity.graph_name if entity else "",
            )
        if intent == INTENT_FILE:
            # A repository routes here too, because "what is the tech stack" is a
            # question about a repository's files rather than about one file.
            # Without this branch it fell through to a file id that could never
            # exist, and the answer was a bare "insufficient evidence" while the
            # graph held every file and its language.
            if entity is not None and entity.label == LABEL_REPOSITORY:
                return self.retrieve_repository(
                    entity.entity_id, entity.name, graph_name=entity.graph_name
                )
            file_id = self._entity_id_matching(entity, {LABEL_FILE})
            return (
                self.retrieve_file(file_id, graph_name=entity.graph_name)
                if file_id
                else None
            )
        if intent == INTENT_HISTORY:
            if entity is None:
                return None
            return self.retrieve_history(entity)

        return None

    def _resolve_decision_id(
        self, question: str, entity: Optional[ResolvedEntity]
    ) -> Optional[str]:
        """Find the decision a "why" question is about.

        A "why" question usually resolves to the incident that prompted the
        decision, or the service the decision was made for, rather than to the
        decision node itself. Tracing those ids directly returns nothing, so the
        decision is followed one hop in the graph. The old keyword table is kept
        only as a last resort, for a question that names no node at all.
        """
        if entity is not None:
            if entity.label == "Decision":
                return entity.entity_id
            for related in self.gateway.find_related_decisions(entity.entity_id):
                return related["id"]

        return self.resolve_entity(question, DECISION_ENTITIES)

    @staticmethod
    def _entity_id_matching(
        entity: Optional[ResolvedEntity], labels: set
    ) -> Optional[str]:
        """The resolved node's id, but only when its label is one we can act on."""
        if entity is None or entity.label not in labels:
            return None
        return entity.entity_id

    @staticmethod
    def _subject_name(entity: Optional[ResolvedEntity]) -> str:
        if entity is None:
            return ""
        # The question's own wording is the better lookup key when the node name
        # is qualified; "Graph" should find the declaration named Graph.
        return entity.term or entity.name

    def retrieve_onboarding(
        self, question: str, context: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        team_id = self.resolve_team_id(question, context)
        result = self.onboarding.get_onboarding_map(team_id)
        if result is None:
            return None

        topics = "\n".join(
            f"{topic.sequence}. {topic.title} — {topic.summary}"
            for topic in result.topics
        )
        services = (
            ", ".join(service.name for service in result.owned_services)
            or "none recorded"
        )
        people = (
            ", ".join(
                f"{person.name} ({person.role})" for person in result.people_to_meet
            )
            or "none recorded"
        )

        answer = (
            f"**Onboarding guide for {result.team_name}**\n\n"
            f"**Mission:** {result.mission}\n\n"
            f"**First-week learning path:**\n{topics}\n\n"
            f"**Services you own:** {services}\n\n"
            f"**People to meet:** {people}"
        )

        return {
            "intent": "onboarding",
            "entity_id": team_id,
            "answer": answer,
            "evidence_summary": (
                f"Retrieved from the team graph: {len(result.topics)} topics, "
                f"{len(result.owned_services)} services, "
                f"{len(result.people_to_meet)} people."
            ),
            "citations": result.reading_list,
            "graph": result.graph,
            "suggested_questions": [
                "Why does Checkout use Kafka instead of synchronous calls?",
                "Who owns Token Service and what depends on it?",
            ],
        }

    def retrieve_decision(self, decision_id: str) -> Optional[Dict[str, Any]]:
        """Answer a "why" question with every kind of evidence attached.

        The full narrative -- documents, people, Slack quotes, stated metrics,
        implementing commits -- replaces the thin decision row. A reader asking
        why something happened is asking about the documents, the people and the
        code, not about a status field.
        """
        evidence = self.decision_evidence.get_evidence(decision_id)
        if evidence is not None:
            package = decision_evidence_package_fn(evidence)
            package["answer"] = self.decision_evidence.render(evidence)
            package["graph"] = self._decision_subgraph(evidence)
            return package


        result = self.decisions.trace_decision(decision_id)
        if result is None:
            return None

        decided_at = result["decided_at"][:10] if result["decided_at"] else "not recorded"
        answer = (
            f"**Decision: {result['title']}**\n\n{result['summary']}\n\n"
            f"**Alternatives considered:** "
            f"{result['alternatives'] or 'none recorded'}\n\n"
            f"**Status:** {result['status']} (decided {decided_at})"
        )

        return {
            "intent": "decision",
            "entity_id": decision_id,
            "answer": answer,
            "evidence_summary": (
                "Traced from the FalkorDB decision graph. "
                f"{len(result['citations'])} source(s) found."
            ),
            "citations": result["citations"],
            "graph": result["graph"],
            "suggested_questions": [
                "Who owns Checkout Service and what are its dependencies?",
                "Which incident led to this decision?",
            ],
        }

    @staticmethod
    def _decision_subgraph(evidence: Any) -> EvidenceSubgraph:
        """A compact subgraph for the graph panel on a decision answer."""
        nodes = [
            GraphNode(
                id=evidence.decision_id,
                label="Decision",
                name=evidence.title,
                properties={"status": evidence.status, "decided_at": evidence.decided_at or ""},
            )
        ]
        edges: List[GraphEdge] = []
        paths: List[str] = []

        for document in evidence.documents:
            nodes.append(
                GraphNode(id=document.source_id, label="Document", name=document.title)
            )
            edges.append(
                GraphEdge(
                    id=f"supported_by:{evidence.decision_id}->{document.source_id}",
                    source=evidence.decision_id,
                    target=document.source_id,
                    type="SUPPORTED_BY",
                )
            )
            paths.append(
                f"{evidence.title} [Decision] --SUPPORTED_BY--> {document.title} [Document]"
            )

        for person in evidence.people:
            nodes.append(GraphNode(id=person.person_id, label="Person", name=person.name))
            edges.append(
                GraphEdge(
                    id=f"{person.involvement.lower()}:{person.person_id}->{evidence.decision_id}",
                    source=person.person_id,
                    target=evidence.decision_id,
                    type=person.involvement,
                )
            )
            paths.append(
                f"{person.name} [Person] --{person.involvement}--> {evidence.title} [Decision]"
            )

        return EvidenceSubgraph(nodes=nodes, edges=edges, paths=paths[:12])

    def retrieve_impact(self, service_id: str) -> Optional[Dict[str, Any]]:
        result = self.impact.assess_impact(service_id)
        if result is None:
            return None

        answer = (
            f"**Change Impact: {result['service_name']}**\n\n"
            f"**Owner:** {result['owner_team'] or 'not recorded'}\n\n"
            f"**Downstream dependencies:** {result['downstream_count']}\n\n"
            f"**Upstream consumers:** {result['upstream_count']}\n\n"
            f"**Risk notes:** {result['risk_notes']}"
        )

        return {
            "intent": "impact",
            "entity_id": service_id,
            "answer": answer,
            "evidence_summary": (
                f"Traversed up to 2 hops from {result['service_name']}. "
                f"{len(result['citations'])} incident/decision record(s) found."
            ),
            "citations": result["citations"],
            "graph": result["graph"],
            "suggested_questions": [
                "Who should I contact before changing this service?",
                "What incidents have affected this service?",
            ],
        }

    def retrieve_ownership(self, service_id: str) -> Optional[Dict[str, Any]]:
        result = self.ownership.get_ownership(service_id)
        if result is None:
            return None

        members = (
            ", ".join(
                f"{member['name']} ({member['role']})"
                for member in result["team_members"]
            )
            or "none recorded"
        )
        contributors = (
            ", ".join(person["name"] for person in result["contributors"])
            or "none recorded"
        )

        answer = (
            f"**Ownership: {result['service_name']}**\n\n"
            f"**Owner team:** {result['owner_team'] or 'not recorded'}\n\n"
            f"**Team members:** {members}\n\n"
            f"**Contributors:** {contributors}\n\n"
            f"**Repository:** {result['repository_url'] or 'not recorded'}"
        )

        return {
            "intent": "ownership",
            "entity_id": service_id,
            "answer": answer,
            "evidence_summary": (
                f"Retrieved ownership from FalkorDB. "
                f"{len(result['team_members'])} team member(s), "
                f"{len(result['contributors'])} contributor(s)."
            ),
            "citations": result["citations"],
            "graph": result["graph"],
            "suggested_questions": [
                "What depends on this service?",
                "What incidents have affected this service?",
            ],
        }

    # --- code retrieval ------------------------------------------------------
    #
    # These answer questions about the ingested repository. Each one attaches a
    # file path and, where it exists, a line number, so a generated answer can
    # cite where in the code the claim came from. A symbol whose authors wrote
    # no doc comment says so rather than receiving an invented explanation.

    def retrieve_symbol(
        self,
        name: str,
        file_id: str = "",
        limit: int = 6,
        graph_name: str = "",
    ) -> Optional[Dict[str, Any]]:
        matches = self.gateway.get_code_symbol(
            name, file_id=file_id, limit=limit, graph_name=graph_name
        )
        exact = bool(matches)

        if not matches:
            # Resolution matches on a prefix, so "the open function" can land on
            # open_payload while an exact-name lookup for "open" finds nothing.
            # Rather than report no evidence for a symbol that clearly exists,
            # widen to the declarations whose names contain the term.
            near = self.gateway.search_code_symbols(name, limit=limit, graph_name=graph_name)
            for candidate in near:
                matches.extend(
                    self.gateway.get_code_symbol(
                        candidate["name"],
                        file_id=file_id,
                        limit=limit,
                        # The graph has to travel with this lookup too. Reading
                        # the org graph here finds no declarations at all, so a
                        # symbol that resolution had just located would be
                        # reported as having no evidence.
                        graph_name=graph_name,
                    )
                )
            matches = _dedupe_declarations(matches)[:limit]

        described = [match for match in matches if match.get("signature")]
        if not described:
            return None

        lines = []
        for match in described:
            location = ""
            if match.get("repository_id"):
                location = ""
            doc = match.get("doc_comment") or ""
            lines.append(
                f"- `{match['name']}` ({match.get('kind') or 'item'}"
                f"{', ' + match['visibility'] if match.get('visibility') else ''}): "
                f"{match.get('signature') or 'no signature recorded'}"
            )
            if doc:
                lines.append(f"  Authored documentation: {doc}")
            else:
                lines.append(
                    "  No authored documentation was found for this declaration."
                )

        undocumented = sum(1 for match in described if not match.get("doc_comment"))

        citations: List[Citation] = []
        neighbours: List[Tuple[GraphNode, str, str]] = []
        for match in described[:4]:
            file_node = self.gateway.get_symbol_file(match["id"], graph_name=graph_name)
            if file_node is None:
                continue
            neighbour = GraphNode(
                id=file_node["file_id"],
                label=LABEL_FILE,
                name=file_node["path"],
                properties={
                    "language": file_node.get("language", ""),
                    "is_test": file_node.get("is_test", False),
                },
            )
            neighbours.append((neighbour, "DECLARES", "in"))
            # A declaration cites the file it is declared in. The line number
            # travels with the citation so a reader can open the exact place.
            citations.append(
                Citation(
                    source_id=match["id"],
                    title=f"{file_node['path']}:{match.get('line', 0)}",
                    type="code",
                    excerpt=(match.get("signature") or match["name"])[:MAX_EXCERPT_CHARS],
                    author="",
                    url="",
                )
            )

        primary = GraphNode(
            id=described[0]["id"],
            label=LABEL_CODE_SYMBOL,
            name=described[0]["name"],
            properties={
                "kind": described[0].get("kind", ""),
                "signature": described[0].get("signature", ""),
                "line": described[0].get("line", 0),
                "documented": bool(described[0].get("doc_comment")),
                "visibility": described[0].get("visibility", ""),
            },
        )

        headline = (
            f"**Declarations matching `{name}`** ({len(described)} found)"
            if exact
            else (
                f"**No declaration is named exactly `{name}`.** "
                f"These {len(described)} declaration(s) contain that name:"
            )
        )

        return {
            "intent": INTENT_SYMBOL,
            "entity_id": described[0]["id"],
            "answer": (
                headline
                + "\n\n"
                + "\n".join(lines)
                + (
                    f"\n\n{undocumented} of these have no authored documentation, "
                    "so nothing further can be said about them from the repository "
                    "alone."
                    if undocumented
                    else ""
                )
            ),
            "evidence_summary": (
                f"Resolved '{name}' against tree-sitter declarations in the "
                f"ingested repository; {len(described)} match(es)."
            ),
            "citations": citations,
            "graph": self._code_subgraph(primary, neighbours),
            "declarations": described,
            "suggested_questions": [
                f"What has changed recently in the file that declares {name}?",
                f"What does {name} depend on?",
            ],
        }

    def retrieve_repository(
        self, repository_id: str, name: str = "", graph_name: str = ""
    ) -> Optional[Dict[str, Any]]:
        """Answer a question about a repository from the files it contains.

        The counts come from the graph rather than from a stored total, so a
        repository that has been re-ingested reports what is there now. Test
        files are excluded: they are written in the same languages as the code
        they exercise and would otherwise inflate every language in the answer.
        """
        mix = self.gateway.get_repository_language_mix(repository_id, graph_name=graph_name)
        if not mix:
            return None

        rows = self.gateway.get_repository_files(
            repository_id, per_language=3, graph_name=graph_name
        )
        total = sum(entry["files"] for entry in mix)
        label = name or repository_id

        spoken = ", ".join(
            f"{entry['language']} ({entry['files']} file{'s' if entry['files'] != 1 else ''})"
            for entry in mix
        )

        nodes: List[GraphNode] = [
            GraphNode(id=repository_id, label=LABEL_REPOSITORY, name=label, properties={})
        ]
        edges: List[GraphEdge] = []
        paths: List[str] = []
        citations: List[Citation] = []
        described = 0
        for entry in rows:
            for sample in entry.get("samples") or []:
                path = sample.get("path")
                if not path:
                    continue
                summary = sample.get("summary") or ""
                if summary:
                    described += 1
                file_node = GraphNode(
                    id=f"{repository_id}::{path}",
                    label=LABEL_FILE,
                    name=path.rsplit("/", 1)[-1],
                    properties={
                        "path": path,
                        "language": entry["language"],
                        "is_test": False,
                        "docs_source": sample.get("docs_source", ""),
                    },
                )
                nodes.append(file_node)
                edges.append(
                    GraphEdge(
                        id=f"{repository_id}::PART_OF::{path}",
                        source=file_node.id,
                        target=repository_id,
                        type="PART_OF",
                        properties={},
                    )
                )
                paths.append(
                    f"{file_node.name} [{LABEL_FILE}] <--PART_OF--> {label} [{LABEL_REPOSITORY}]"
                )
                citations.append(
                    Citation(
                        source_id=f"{repository_id}::{path}",
                        title=path,
                        type="file",
                        url=None,
                        excerpt=summary or None,
                        author=None,
                        created_at=None,
                    )
                )

        return {
            "intent": INTENT_FILE,
            "entity_id": repository_id,
            "answer": (
                f"{label} is written in {spoken}, across {total} indexed files. "
                f"{described} of the {len(citations)} sampled files carry a "
                f"description read from their own source."
            ),
            "evidence_summary": (
                f"Counted {total} File nodes carrying repository_id "
                f"{repository_id!r} in the graph, tests excluded, and sampled "
                f"{len(citations)} of them across {len(mix)} languages."
            ),
            "citations": citations,
            "graph": EvidenceSubgraph(nodes=nodes, edges=edges, paths=paths[:12]),
            "confidence": "supported" if total else "insufficient",
            "suggested_questions": [
                f"Which files changed most recently in {label}?",
                f"Who changed {label}?",
            ],
        }

    def retrieve_file(
        self, file_id: str, graph_name: str = ""
    ) -> Optional[Dict[str, Any]]:
        description = self.gateway.get_file_description(file_id, graph_name=graph_name)
        if description is None:
            return None

        path = description.get("path") or description.get("name") or file_id
        summary = description.get("summary")
        provenance = []
        if description.get("docs_source"):
            provenance.append(str(description["docs_source"]))
        if description.get("docs_model"):
            provenance.append(str(description["docs_model"]))
        if description.get("docs_trigger"):
            provenance.append(f"trigger: {description['docs_trigger']}")

        body = summary or "The authors left no usable description for this file."
        symbols = description.get("symbols") or []

        answer = (
            f"**{path}**\n\n"
            f"{body}\n\n"
            f"**Declared symbols ({len(symbols)}):** "
            + (", ".join(str(symbol) for symbol in symbols[:12]) or "none recorded")
            + "\n\n"
            f"**Provenance:** {'; '.join(provenance) or 'not recorded'}"
        )

        primary = GraphNode(
            id=file_id,
            label=LABEL_FILE,
            name=path,
            properties={
                "language": description.get("language", ""),
                "is_test": description.get("is_test", False),
                "docs_source": description.get("docs_source", ""),
            },
        )
        neighbours: List[Tuple[GraphNode, str, str]] = []
        repository_id = description.get("repository_id")
        if repository_id:
            neighbours.append(
                (
                    GraphNode(
                        id=str(repository_id),
                        label=LABEL_REPOSITORY,
                        name=str(repository_id),
                        properties={},
                    ),
                    "PART_OF",
                    "in",
                )
            )

        return {
            "intent": INTENT_FILE,
            "entity_id": file_id,
            "answer": answer,
            "evidence_summary": (
                f"Read the description OrgAtlas derived from {path} itself "
                f"(source: {description.get('docs_source') or 'none'})."
            ),
            "citations": [
                Citation(
                    source_id=file_id,
                    title=path,
                    type="code",
                    excerpt=(summary or "")[:MAX_EXCERPT_CHARS],
                    author="",
                    url="",
                )
            ],
            "graph": self._code_subgraph(primary, neighbours),
            "file": description,
            "suggested_questions": [
                f"How often has {path} changed recently?",
                "Which commits touched this file?",
            ],
        }

    def retrieve_history(
        self, entity: ResolvedEntity, limit: int = 12
    ) -> Optional[Dict[str, Any]]:
        """Answer a history question about a symbol, file, or repository."""
        target = ""
        label = entity.label

        if label == LABEL_FILE:
            target = entity.entity_id
        elif label in (LABEL_CODE_SYMBOL, LABEL_COMMIT):
            symbol_file = self.gateway.get_symbol_file(entity.entity_id, graph_name=entity.graph_name)
            if symbol_file is not None:
                target = symbol_file["file_id"]
        elif label == LABEL_REPOSITORY:
            target = entity.entity_id

        if not target:
            return None

        history = self.gateway.get_file_history(target, limit=limit, graph_name=entity.graph_name)
        if not history:
            return None

        rows = []
        for entry in history:
            who = entry.get("author") or entry.get("author_id") or "unknown author"
            rows.append(f"- `{str(entry.get('sha', ''))[:7]}` {entry.get('message', '')} ? {who}")

        path = history[0].get("path") or entity.name

        primary = GraphNode(
            id=target,
            label=LABEL_FILE,
            name=str(path),
            properties={"commit_count": len(history)},
        )
        commit_nodes: List[Tuple[GraphNode, str, str]] = []
        citations: List[Citation] = []
        for entry in history[:5]:
            sha = str(entry.get("sha", ""))
            commit_nodes.append(
                (
                    GraphNode(
                        id=sha,
                        label=LABEL_COMMIT,
                        name=(entry.get("message") or sha)[:80],
                        properties={"authored_at": entry.get("authored_at") or ""},
                    ),
                    "MODIFIES",
                    "in",
                )
            )
            citations.append(
                Citation(
                    source_id=sha,
                    title=f"{sha[:7]} {(entry.get('message') or '')[:80]}",
                    type="commit",
                    excerpt="",
                    author=entry.get("author") or "",
                    url="",
                )
            )

        return {
            "intent": INTENT_HISTORY,
            "entity_id": target,
            "answer": (
                f"**Change history for {path}** ({len(history)} commits)\n\n"
                + "\n".join(rows)
            ),
            "evidence_summary": (
                f"Walked {len(history)} commits that modified {path} in the "
                "ingested repository."
            ),
            "citations": citations,
            "graph": self._code_subgraph(primary, commit_nodes),
            "history": history,
            "suggested_questions": [
                f"What does the most important symbol in {path} do?",
                "Which authors changed this file most?",
            ],
        }

    # --- code evidence graph --------------------------------------------------

    def _code_subgraph(
        self,
        primary: GraphNode,
        neighbours: Optional[List[Tuple[GraphNode, str, str]]] = None,
    ) -> EvidenceSubgraph:
        """Assemble the small subgraph a code answer is grounded in.

        Code retrievals are leaf lookups, so there is no multi-hop traversal to
        return. The subject and the two nodes it lives between -- its file and
        that file's repository -- are enough for the panel to show where the
        claim came from, and keep the file and line on the record.
        """
        nodes = [primary]
        edges: List[GraphEdge] = []
        paths: List[str] = []

        for neighbour, edge_type, direction in neighbours or []:
            nodes.append(neighbour)
            source, target = (
                (primary, neighbour) if direction == "out" else (neighbour, primary)
            )
            edges.append(
                GraphEdge(
                    id=f"{edge_type.lower()}:{source.id}->{target.id}",
                    source=source.id,
                    target=target.id,
                    type=edge_type,
                )
            )
            arrow = "-->" if direction == "out" else "<--"
            paths.append(f"{primary.name} [{primary.label}] {arrow}{edge_type}--> {neighbour.name} [{neighbour.label}]")

        return EvidenceSubgraph(nodes=nodes, edges=edges, paths=paths)

    # --- answer synthesis ----------------------------------------------------

    @staticmethod
    def _facts_text(package: Dict[str, Any]) -> str:
        """Flatten a package into the facts a narrative may be written from."""
        lines: List[str] = [package["answer"][:MAX_FACT_CHARS]]

        graph = package.get("graph")
        if graph is not None and graph.paths:
            lines.append("\nEvidence paths:")
            lines.extend(f"- {path}" for path in graph.paths[:8])
        return "\n".join(lines)

    @staticmethod
    def _citeable(citations: List[Any]) -> List[str]:
        return [
            citation.source_id
            for citation in citations
            if getattr(citation, "source_id", None)
        ]

    async def synthesize(self, question: str, package: Dict[str, Any]) -> Dict[str, Any]:
        """Return the package with its answer replaced by a grounded narrative.

        Falls back to the deterministic answer whenever the provider is
        unavailable, fails, or produces an answer that does not stand on the
        retrieved sources.
        """
        provider = self.provider
        citations = package.get("citations") or []

        if provider is None or not provider.available:
            return self._fallback(
                question, package, "no provider is configured; answering from graph facts"
            )

        from app.llm.client import SynthesisRequest, SynthesisSuccess

        outcome = await provider.generate_synthesis(
            SynthesisRequest(
                question=question,
                facts=self._facts_text(package),
                citations=[
                    {
                        "source_id": citation.source_id,
                        "title": citation.title,
                        "type": citation.type,
                        "excerpt": getattr(citation, "excerpt", None),
                    }
                    for citation in citations
                    if isinstance(citation, Citation)
                ],
                intent=package.get("intent", ""),
                entity_id=package.get("entity_id", ""),
            )
        )

        if not isinstance(outcome, SynthesisSuccess):
            return self._fallback(
                question,
                package,
                f"provider unavailable ({outcome.reason}); answering from graph facts",
            )

        grounding = validate_citations(outcome.answer, self._citeable(citations))
        if not grounding.accepted:
            logger.info("discarding ungrounded synthesis for %r", question)
            return self._fallback(
                question,
                package,
                "the generated answer cited sources that were not retrieved, "
                "so it was discarded",
            )

        if grounding.notes:
            logger.info("synthesis degraded for %r: %s", question, grounding.notes)

        package["answer"] = grounding.answer
        package["grounding"] = grounding
        package["synthesis"] = {"model": outcome.model, "usage": outcome.usage}
        package["evidence_summary"] = (
            f"{package['evidence_summary']} Synthesised by {outcome.model} from "
            f"{len(citations)} retrieved source(s)."
        )
        if grounding.degraded:
            package["evidence_summary"] += " " + " ".join(grounding.notes)
        return package

    def _fallback(self, question: str, package: Dict[str, Any], reason: str) -> Dict[str, Any]:
        """Answer from the retrieved evidence without the model.

        The deterministic narrative is preferred over the generic evidence
        listing, because it carries real content the listing cannot: an
        ownership query with no cited documents still knows the owning team and
        its members. The evidence-listing helper is used only when there is no
        narrative at all.
        """
        logger.info("fallback answer for %r: %s", question, reason)
        package["fallback_reason"] = reason

        if package.get("answer"):
            package["evidence_summary"] = (
                f"{package['evidence_summary']} Answered from graph facts: {reason}."
            )
            return package

        fallback = self.evidence.build_fallback_answer(
            {
                "citations": package.get("citations") or [],
                "graph": package.get("graph") or EvidenceSubgraph(),
            },
            question,
        )
        package["answer"] = fallback["answer"]
        package["evidence_summary"] = fallback["evidence_summary"]
        return package

    # --- response assembly ---------------------------------------------------

    async def answer(
        self, question: str, context: Optional[str] = None
    ) -> AskQuestionResponse:
        """Answer one question end to end.

        This is the single path a caller should use, and the HTTP route is a thin
        wrapper over it. The Slack bot calls the same method, which is the point:
        an answer in Slack is the answer the API gives, with the same evidence
        and the same refusal to answer what the graph does not support. Keeping
        the flow in one place is what stops the two faces from drifting apart.
        """
        package = self.retrieve(question, context)

        if package is None:
            logger.info("No route matched the question; returning insufficient evidence")
            return self.insufficient(question)

        package["confidence"] = self.confidence_for(
            package.get("citations") or [], package.get("graph")
        )
        package = await self.synthesize(question, package)
        return self.build_response(question, package)

    def insufficient(self, question: str) -> AskQuestionResponse:
        return AskQuestionResponse(**self.evidence.build_insufficient_response(question))

    def build_response(self, question: str, package: Dict[str, Any]) -> AskQuestionResponse:
        """Assemble the final response, bounding the subgraph for rendering.

        A package may arrive without a subgraph. The code retrievers build one
        when they can, but a retrieval that matched nothing renderable must not
        be turned into a crash on the way out.
        """
        if package.get("graph") is not None:
            package["graph"] = self.evidence.truncate_subgraph(package["graph"])

        confidence = package.get("confidence") or "partial"
        grounding = package.get("grounding")
        if grounding is not None:
            confidence = lower_confidence(confidence, grounding.confidence_ceiling)

        return AskQuestionResponse(
            answer=package["answer"],
            evidence_summary=package["evidence_summary"],
            citations=package.get("citations") or [],
            graph=package["graph"] or EvidenceSubgraph(),
            confidence=confidence,
            suggested_questions=package.get("suggested_questions")
            or self.evidence.default_follow_ups(),
        )

    def confidence_for(
        self, citations: List[Any], graph: Optional[EvidenceSubgraph]
    ) -> str:
        return self.evidence.compute_confidence(citations, graph)