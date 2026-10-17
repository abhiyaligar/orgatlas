"""Assemble the full story of one decision.

A question like "why did we move from Kafka to Redis, who was involved, and how
much did we gain" is a single question with six parts, and answering it well
means answering all six together:

* what was decided, and why
* which documents say so
* which people argued for it, approved it, or objected
* what they said, in Slack, in their own words
* what numbers the documents state
* what commits shipped it

Two rules shape everything here.

**Absence is stated, not hidden.** A graph that holds no metric for a migration
answers "no improvement figure is recorded in the documents" rather than letting
the reader assume there was none. A blank section invites the reader to fill the
gap with their own assumption, which is the failure this product exists to
prevent.

**Summarised, never flooded.** Each part is bounded and each excerpt is
truncated. A Slack transcript read back verbatim is not context, it is noise
with a citation attached.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.api.schemas import (
    Citation,
    CommitSummary,
    DecisionEvidenceResponse,
    MetricResponse,
    PersonInvolvement,
    QuotedStatement,
)
from app.graph.gateway import GraphGateway

logger = logging.getLogger(__name__)

# Bounds per section. An answer that reads as a wall of evidence is not read.
MAX_DOCUMENTS = 5
MAX_PEOPLE = 12
MAX_QUOTES = 5
MAX_METRICS = 8
MAX_COMMITS = 8

# An excerpt is evidence, so it is long enough to check, and short enough that
# six of them still fit on a screen.
EXCERPT_CHARS = 600
QUOTE_CHARS = 400


class DecisionEvidenceService:
    """Assembles every kind of evidence attached to one decision."""

    def __init__(self, gateway: Optional[GraphGateway] = None) -> None:
        self.gateway = gateway or GraphGateway()

    def get_evidence(self, decision_id: str) -> Optional[DecisionEvidenceResponse]:
        decision = self.gateway.get_decision_evidence(decision_id)
        if decision is None:
            return None

        documents = self.gateway.get_decision_documents(decision_id, limit=MAX_DOCUMENTS)
        incidents = self.gateway.get_decision_incidents(decision_id, limit=MAX_DOCUMENTS)
        people = self.gateway.get_decision_people(decision_id, limit=MAX_PEOPLE)
        discussion = self.gateway.get_decision_discussion(decision_id, limit=MAX_QUOTES)
        metrics = self.gateway.get_decision_metrics(decision_id, limit=MAX_METRICS)
        migration = self.gateway.get_decision_migration(decision_id)

        person_ids = [person["person_id"] for person in people]
        commits = self.gateway.get_people_commits(person_ids, limit=MAX_COMMITS)

        notes = self._notes(
            documents=documents,
            people=people,
            discussion=discussion,
            metrics=metrics,
            commits=commits,
            migration=migration,
        )

        return DecisionEvidenceResponse(
            decision_id=decision["decision_id"],
            title=decision["title"],
            summary=decision["summary"],
            rationale=decision["rationale"],
            alternatives=decision["alternatives"],
            status=decision["status"],
            decided_at=decision["decided_at"],
            quote=decision["quote"],
            documents=[
                Citation(
                    source_id=doc["id"],
                    title=doc["title"],
                    type="document",
                    url=doc.get("uri") or None,
                    excerpt=(doc.get("excerpt") or "")[:EXCERPT_CHARS],
                    author=doc.get("author") or "",
                )
                for doc in documents
            ],
            people=[
                PersonInvolvement(
                    person_id=person["person_id"],
                    name=person["name"],
                    involvement=person["involvement"],
                    role=person.get("role") or "",
                    quote=(person.get("quote") or "")[:EXCERPT_CHARS],
                )
                for person in people
            ],
            quotes=[
                QuotedStatement(
                    source_id=message["source_id"],
                    speaker=message["speaker"],
                    text=(message.get("text") or "")[:QUOTE_CHARS],
                    channel=message.get("channel") or "",
                    posted_at=message.get("posted_at"),
                    permalink=message.get("permalink"),
                )
                for message in discussion
            ],
            metrics=[
                MetricResponse(
                    id=metric["id"],
                    name=metric["name"],
                    value=float(metric["value"] or 0),
                    unit=metric.get("unit") or "unknown",
                    baseline=metric.get("baseline"),
                    direction=metric.get("direction") or "unknown",
                    quote=(metric.get("quote") or "")[:EXCERPT_CHARS],
                    document_id=metric.get("document_id"),
                )
                for metric in metrics
            ],
            commits=[
                CommitSummary(
                    sha=commit["sha"],
                    message=(commit.get("message") or "")[:200],
                    authored_at=commit.get("authored_at"),
                    pr_number=commit.get("pr_number"),
                    author=commit.get("author") or "",
                )
                for commit in commits
            ],
            migrated_from=migration.get("from", []),
            migrated_to=migration.get("to", []),
            incidents=[
                Citation(
                    source_id=incident["id"],
                    title=incident["title"],
                    type="incident",
                    url=incident.get("uri") or None,
                )
                for incident in incidents
            ],
            notes=notes,
        )

    # --- the honest gaps -----------------------------------------------------

    @staticmethod
    def _notes(
        documents: List[Dict[str, Any]],
        people: List[Dict[str, Any]],
        discussion: List[Dict[str, Any]],
        metrics: List[Dict[str, Any]],
        commits: List[Dict[str, Any]],
        migration: Dict[str, List[str]],
    ) -> List[str]:
        """Say what the graph does not hold, so a gap is not read as a finding."""
        notes: List[str] = []

        if not documents:
            notes.append(
                "No document in the graph supports this decision, so the reason "
                "cannot be attributed to a source."
            )
        if not people:
            notes.append(
                "No individual is recorded as proposing, approving or objecting. "
                "The decision is not attributed to a named person."
            )
        if not discussion:
            notes.append(
                "No Slack discussion about this decision has been ingested."
            )
        if not metrics:
            notes.append(
                "No improvement figure is recorded in the documents. Any claim "
                "about what the change achieved would be unevidenced."
            )
        if not commits:
            notes.append(
                "No commits by the people involved are linked to this decision."
            )
        if not migration.get("from") and not migration.get("to"):
            notes.append(
                "This is not recorded as a migration between technologies."
            )

        return notes

    # --- narrative -----------------------------------------------------------

    def render(self, evidence: DecisionEvidenceResponse) -> str:
        """Render the evidence as the deterministic answer text.

        This is both the fallback when no model is available and the factual base
        a model is asked to write from. Sections appear only where the graph has
        something, and every absence is stated.
        """
        parts: List[str] = [
            f"**Decision: {evidence.title}**",
        ]
        if evidence.status and evidence.status != "unknown":
            decided = f", decided {evidence.decided_at[:10]}" if evidence.decided_at else ""
            parts.append(f"**Status:** {evidence.status}{decided}")
        if evidence.summary:
            parts.append(evidence.summary)

        if evidence.rationale:
            parts.append(f"**Why:** {evidence.rationale}")
        elif not evidence.rationale:
            parts.append(
                "**Why:** not recorded. The documents describing this decision "
                "do not state a reason."
            )

        if evidence.alternatives:
            parts.append(f"**Alternatives considered:** {evidence.alternatives}")

        if evidence.migrated_from or evidence.migrated_to:
            moved = []
            if evidence.migrated_from:
                moved.append(f"from {', '.join(evidence.migrated_from)}")
            if evidence.migrated_to:
                moved.append(f"to {', '.join(evidence.migrated_to)}")
            parts.append("**Migration:** " + " ".join(moved))

        if evidence.incidents:
            titles = ", ".join(incident.title for incident in evidence.incidents)
            parts.append(f"**Triggered by:** {titles}")

        if evidence.people:
            lines = []
            for person in evidence.people:
                role = f", {person.role}" if person.role else ""
                quote = f' — "{person.quote}"' if person.quote else ""
                lines.append(
                    f"- {person.name} ({person.involvement.lower()}{role}){quote}"
                )
            parts.append("**People involved:**\n" + "\n".join(lines))

        if evidence.quotes:
            lines = [
                f'- "{quote.text}" — {quote.speaker}'
                + (f" in #{quote.channel}" if quote.channel else "")
                for quote in evidence.quotes
            ]
            parts.append("**In discussion:**\n" + "\n".join(lines))

        if evidence.metrics:
            lines = []
            for metric in evidence.metrics:
                baseline = f" (from {metric.baseline})" if metric.baseline else ""
                direction = (
                    f" {metric.direction}" if metric.direction != "unknown" else ""
                )
                lines.append(
                    f"- {metric.name}: {_format_value(metric.value)}"
                    f"{_unit_suffix(metric.unit)}{baseline}{direction}"
                )
            parts.append("**Stated outcomes:**\n" + "\n".join(lines))

        if evidence.commits:
            lines = [
                f"- `{commit.sha[:7]}` {commit.message} — {commit.author}"
                for commit in evidence.commits
            ]
            parts.append(f"**Commits by those involved ({len(evidence.commits)}):**\n" + "\n".join(lines))

        if evidence.documents:
            lines = [
                f"- {document.title}" + (f" — {document.author}" if document.author else "")
                for document in evidence.documents
            ]
            parts.append("**Sources:**\n" + "\n".join(lines))

        if evidence.notes:
            parts.append("**Not recorded:**\n" + "\n".join(f"- {note}" for note in evidence.notes))

        return "\n\n".join(parts)

    @staticmethod
    def premise_note(unmatched_terms: List[str], other_candidates: List[Any]) -> List[str]:
        """Flag the part of a question no decision accounts for.

        When a question names something -- a technology, a service -- and no
        decision mentions it, the honest answer says so before explaining what
        the graph does hold. Otherwise a reader gets a confident answer about
        the wrong decision, which reads as a correction nobody asked for.
        """
        notes: List[str] = []
        if unmatched_terms:
            named = ", ".join(f"`{term}`" for term in unmatched_terms[:6])
            others = (
                f" {len(other_candidates)} other decision(s) in the graph also "
                "mention part of this question."
                if other_candidates
                else ""
            )
            notes.append(
                f"The question names {named}, which the decision below does not "
                f"mention.{others} If you expected this answer to be about them, "
                "the document stating it has not been ingested."
            )
        return notes


def _format_value(value: float) -> str:
    """Render a metric value without a spurious decimal.

    A latency recorded as 120 is an integer in every document that states it;
    rendering it as 120.0 makes the answer look like it came from arithmetic
    rather than from the source.
    """
    if value == int(value):
        return str(int(value))
    return f"{value:g}"


def _unit_suffix(unit: str) -> str:
    """Render a metric's value with its unit, when the unit is a real one."""
    if unit in ("percent", "%"):
        return "%"
    if unit == "ms":
        return "ms"
    if unit == "duration":
        return " (duration)"
    if unit == "ratio":
        return "x"
    if unit == "count":
        return ""
    return f" {unit}" if unit and unit != "unknown" else ""


def as_package(evidence: DecisionEvidenceResponse) -> Dict[str, Any]:
    """Shape evidence as an ask package the existing pipeline understands."""
    citations: List[Citation] = list(evidence.documents) + list(evidence.incidents)
    for quote in evidence.quotes:
        citations.append(
            Citation(
                source_id=quote.source_id,
                title=f"{quote.speaker}: {quote.text[:80]}",
                type="slack",
                url=quote.permalink,
                excerpt=quote.text,
                author=quote.speaker,
            )
        )
    for commit in evidence.commits:
        citations.append(
            Citation(
                source_id=commit.sha,
                title=f"{commit.sha[:7]} {commit.message[:80]}",
                type="commit",
                excerpt="",
                author=commit.author,
            )
        )

    return {
        "intent": "decision",
        "entity_id": evidence.decision_id,
        "answer": "",
        "evidence_summary": (
            f"Assembled from {len(evidence.documents)} document(s), "
            f"{len(evidence.people)} person(s), {len(evidence.quotes)} Slack quote(s), "
            f"{len(evidence.metrics)} stated metric(s) and {len(evidence.commits)} commit(s)."
        ),
        "citations": citations,
        "graph": None,
        "decision_evidence": evidence,
    }