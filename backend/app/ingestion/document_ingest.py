"""Ingest uploaded documents and Slack history into the graph.

The pipeline is the same shape as repository ingestion -- a job that reports
stages -- because a caller watching it needs the same thing: to see that parsing
is happening, that extraction is happening, and how much of it produced facts.

    queued -> parsing -> extracting -> linking -> writing -> done | failed

Ordering matters and is not arbitrary. Extraction runs before linking because the
extractor names the entities a document talks about; linking then resolves those
names against nodes that already exist, which is what turns a document into
graph structure rather than a stored blob.

Writes are idempotent. Everything is a MERGE on a stable id derived from the
content hash, so re-uploading the same file updates its node instead of
producing a second copy that disagrees with the first.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.db.models import Document, DocumentExtraction, SlackMessage
from app.graph.gateway import GraphGateway
from app.ingestion.doc_parsers import (
    DocumentParseError,
    ParsedDocument,
    for_extraction,
    kind_for_filename,
    parse_document,
)
from app.services.doc_extractor import DocumentExtractor

logger = logging.getLogger(__name__)

Stage = Callable[[str], None]

STAGE_QUEUED = "queued"
STAGE_PARSING = "parsing"
STAGE_EXTRACTING = "extracting"
STAGE_LINKING = "linking"
STAGE_WRITING = "writing"

# A Slack message is stored as an excerpt. The full text stays in the relational
# table; the graph carries enough to cite it and enough to decide it is relevant,
# and a transcript in the graph would be read aloud in an answer.
SLACK_EXCERPT_CHARS = 500

_SLUG = re.compile(r"[^a-z0-9]+")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _dedupe_terms(terms: List[str]) -> List[str]:
    """Strip and de-duplicate, preserving the caller's order."""
    cleaned: List[str] = []
    for raw in terms:
        token = (raw or "").strip()
        if token and token not in cleaned:
            cleaned.append(token)
    return cleaned


def _slug(text: str, limit: int = 60) -> str:
    return _SLUG.sub("-", (text or "").lower()).strip("-")[:limit] or "document"


def document_id_for(sha256: str, title: str) -> str:
    """A stable id from the content, so re-upload is an update not a duplicate."""
    return f"doc_up_{sha256[:16]}"


def person_id_for(name: str) -> str:
    return f"person_up_{_slug(name)}"


class DocumentIngestor:
    """Runs one upload end to end."""

    def __init__(
        self,
        gateway: Optional[GraphGateway] = None,
        extractor: Optional[DocumentExtractor] = None,
        session_factory: Optional[Callable[[], Any]] = None,
        store_originals: Optional[bool] = None,
    ) -> None:
        self.gateway = gateway or GraphGateway()
        self.extractor = extractor or DocumentExtractor()
        self._session_factory = session_factory
        self.store_originals = store_originals

    def _session(self) -> Any:
        if self._session_factory is None:
            from app.core.dependencies import SessionLocal

            return SessionLocal()
        return self._session_factory()

    # --- entity resolution ---------------------------------------------------

    def resolve_entities(self, terms: List[str]) -> Dict[str, Dict[str, Any]]:
        """Resolve extracted entity names to nodes that already exist.

        This is the same name resolution ``/ask`` uses, run in reverse: the
        document supplies the terms and the graph decides what they are. A term
        that matches nothing is dropped rather than created, because inventing a
        node for a misspelling is how a graph fills with ghosts.
        """
        cleaned = _dedupe_terms(terms)
        if not cleaned:
            return {}

        resolved: Dict[str, Dict[str, Any]] = {}
        for row in self.gateway.search_entities_by_terms(cleaned):
            key = (row.get("name") or "").strip().lower()
            if key and key not in resolved:
                resolved[key] = row
        return resolved

    def _entity_edges(
        self, parsed: ParsedDocument, result: Any
    ) -> List[Dict[str, Any]]:
        """Build DOCUMENTS edges for the entities an extraction named."""
        names = [entity["name"] for entity in result.entities]
        names += [person["name"] for person in result.people]
        names += [decision["title"] for decision in result.decisions]
        names += [metric["name"] for metric in result.metrics]

        resolved = self.resolve_entities(names)
        edges: List[Dict[str, Any]] = []
        seen: set = set()
        for name in names:
            key = name.strip().lower()
            match = resolved.get(key)
            if not match or match["id"] in seen:
                continue
            seen.add(match["id"])
            edges.append({"target_id": match["id"], "role": "mentions"})
        return edges

    # --- persistence ---------------------------------------------------------

    def _store(self, parsed: ParsedDocument, sha256: str, extraction: Any) -> Document:
        record = Document(
            id=parsed.id,
            title=parsed.title,
            kind=parsed.kind,
            uri=parsed.metadata.get("uri"),
            sha256=sha256,
            char_count=parsed.char_count,
            text=parsed.text,
            author=parsed.metadata.get("author"),
            created_at=_now(),
        )
        if parsed.metadata.get("source_at"):
            try:
                record.source_at = datetime.fromisoformat(parsed.metadata["source_at"])
            except (TypeError, ValueError):
                pass

        session = self._session()
        try:
            existing = session.get(Document, record.id)
            if existing is not None:
                # Content hash matches: this is a re-upload of the same file.
                session.delete(existing)
            session.merge(record)
            session.commit()
        finally:
            session.close()
        return record

    def _store_extraction(
        self, parsed: ParsedDocument, sha256: str, outcome: Any
    ) -> None:
        session = self._session()
        try:
            session.merge(
                DocumentExtraction(
                    document_id=parsed.id,
                    payload=json.dumps(outcome.result.to_payload()),
                    model=outcome.model,
                    prompt_version=outcome.prompt_version,
                    input_sha=sha256,
                    trigger="upload",
                    usage=json.dumps(outcome.usage) if outcome.usage else None,
                    raw_response=outcome.raw_response or None,
                    error=outcome.error,
                    created_at=_now(),
                )
            )
            session.commit()
        finally:
            session.close()

    # --- the pipeline --------------------------------------------------------

    def ingest(
        self,
        data: bytes,
        filename: str,
        title: Optional[str] = None,
        author: Optional[str] = None,
        on_stage: Optional[Stage] = None,
        run_extraction: bool = True,
    ) -> Dict[str, Any]:
        """Parse, extract, link and write one uploaded file."""
        emit: Stage = on_stage or (lambda message: None)
        emit(f"reading {filename}")

        sha256 = hashlib.sha256(data).hexdigest()
        kind = kind_for_filename(filename)
        base_id = document_id_for(sha256, title or filename)

        emit(f"parsing {filename} as {kind}")
        try:
            parsed_documents = parse_document(data, filename, base_id, title)
        except DocumentParseError as exc:
            raise

        for parsed in parsed_documents:
            if author:
                parsed.metadata.setdefault("author", author)

        summary: Dict[str, Any] = {
            "filename": filename,
            "kind": kind,
            "sha256": sha256,
            "documents": len(parsed_documents),
            "decisions": 0,
            "metrics": 0,
            "entities_linked": 0,
            "people": 0,
            "model_calls": 0,
            "extraction_errors": [],
        }

        for index, parsed in enumerate(parsed_documents, 1):
            label = (
                f"{parsed.title}"
                if len(parsed_documents) == 1
                else f"{parsed.title} ({index}/{len(parsed_documents)})"
            )

            emit(f"extracting {label}")
            outcome = (
                self.extractor.extract(
                    title=parsed.title,
                    text=for_extraction(parsed.text),
                    kind=parsed.kind,
                )
                if run_extraction
                else _empty_outcome()
            )
            if outcome.model or outcome.usage:
                summary["model_calls"] += 1
            if outcome.error:
                summary["extraction_errors"].append(f"{parsed.id}: {outcome.error}")

            emit(f"storing {label}")
            self._store(parsed, sha256, outcome)
            self._store_extraction(parsed, sha256, outcome)

            # The Document node must exist before anything links to it. Every
            # writer below MATCHes on it, so writing it last silently drops each
            # row: the MERGE still creates the decision node, but the MATCH finds
            # no document, so no SUPPORTED_BY edge is written and no id comes
            # back -- which also means no people and no migration.
            self.gateway.upsert_document(
                {
                    "id": parsed.id,
                    "title": parsed.title,
                    "kind": parsed.kind,
                    "uri": parsed.metadata.get("uri"),
                    "sha256": sha256,
                    "char_count": parsed.char_count,
                    "summary": parsed.text[:5000],
                    "author": parsed.metadata.get("author"),
                    "source_at": parsed.metadata.get("source_at"),
                    "ingested_at": _now().isoformat(),
                    "extraction_model": outcome.model,
                }
            )

            emit(f"writing {label}")
            result = outcome.result

            decision_rows = [
                {
                    "key": _slug(decision["title"], 40) or f"d{index}",
                    "title": decision["title"],
                    "summary": decision["summary"],
                    "rationale": decision["rationale"],
                    "alternatives": decision["alternatives"],
                    "status": decision["status"],
                    "decided_at": decision["decided_at"],
                    "quote": decision["quote"],
                }
                for decision in result.decisions
            ]
            # Extraction can be switched off, so every write below is guarded:
            # a pipeline run that legitimately extracted nothing should not make
            # graph calls with empty lists.
            decision_ids = (
                self.gateway.upsert_extracted_decisions(parsed.id, decision_rows)
                if decision_rows
                else []
            )
            by_key = dict(zip((row["key"] for row in decision_rows), decision_ids))

            people_rows = [
                {
                    "person_id": person_id_for(person["name"]),
                    "name": person["name"],
                    "role": person.get("role", ""),
                    "involvement": person.get("involvement", "unknown"),
                    "quote": person.get("quote", ""),
                }
                for person in result.people
            ]
            written_people = 0
            if people_rows:
                for decision_id in by_key.values():
                    written_people += self.gateway.upsert_decision_people(
                        decision_id, people_rows
                    )

            metric_rows = [
                {
                    "key": _slug(f"{metric['name']}-{metric['value']}", 48) or f"m{index}",
                    "name": metric["name"],
                    "value": metric["value"],
                    "unit": metric["unit"],
                    "baseline": metric.get("baseline"),
                    "direction": metric.get("direction", "unknown"),
                    "quote": metric["quote"],
                }
                for metric in result.metrics
            ]
            written_metrics = (
                self.gateway.upsert_metrics(parsed.id, metric_rows) if metric_rows else []
            )
            # Counted from what the graph accepted rather than from what the
            # model proposed, so the job reports the numbers a reader would find.
            summary["decisions"] += len(decision_ids)
            summary["metrics"] += len(written_metrics)
            summary["people"] += written_people

            edges = self._entity_edges(parsed, result)
            if edges:
                linked = self.gateway.link_document(parsed.id, edges)
                summary["entities_linked"] += linked

            # A migration is only recorded when the document itself states both
            # ends of it. Nothing infers a migration from a mention of two tools.
            self._record_migrations(parsed, result, by_key)

        emit(f"complete: {summary['documents']} document(s)")
        return summary

    def _record_migrations(
        self,
        parsed: ParsedDocument,
        result: Any,
        decision_ids: Dict[str, str],
    ) -> None:
        """Record the technology-to-technology move a document states outright.

        The vocabulary comes from the extraction rather than from the raw text. A
        regex guessing at prose produces "Redis Streams in June 2024. The reason
        was" as a technology name; matching against the names the model actually
        identified, and that resolve to something, does not. Where the document
        does not state both ends, nothing is recorded -- a migration is never
        inferred from two tools merely appearing in one file.
        """
        if not decision_ids:
            return

        technologies = [
            entity["name"].strip()
            for entity in result.entities
            if entity.get("kind") == "Technology" and entity.get("name")
        ]
        if len(technologies) < 2:
            return

        pairs = _migration_pairs(parsed.text, technologies)
        if not pairs:
            return

        for decision_id in decision_ids.values():
            for source, target in pairs:
                self.gateway.record_migration(
                    decision_id,
                    [{"id": f"tech_up_{_slug(source, 40)}", "name": source}],
                )
                self.gateway.record_migration_to(
                    decision_id,
                    [{"id": f"tech_up_{_slug(target, 40)}", "name": target}],
                )

    # --- Slack ---------------------------------------------------------------

    def ingest_slack_messages(
        self,
        messages: List[Dict[str, Any]],
        on_stage: Optional[Stage] = None,
    ) -> Dict[str, Any]:
        """Ingest Slack history so 'who said what' is answerable with a citation.

        Each message becomes a node holding an excerpt rather than a transcript,
        attributed to a person already in the graph when one matches, and linked
        to whatever it was about. A Slack identity that matches nobody is left
        unattributed rather than invented as a person.
        """
        emit: Stage = on_stage or (lambda message: None)
        summary = {
            "messages": 0,
            "attributed": 0,
            "linked": 0,
            "skipped": 0,
        }
        if not messages:
            return summary

        emit(f"ingesting {len(messages)} Slack message(s)")

        for message in messages:
            text = (message.get("text") or "").strip()
            if not text:
                summary["skipped"] += 1
                continue

            ts = str(message.get("ts") or uuid.uuid4().hex[:12])
            message_id = f"slack_{message.get('channel_id', 'unknown')}_{ts}".replace(".", "_")

            session = self._session()
            try:
                session.merge(
                    SlackMessage(
                        id=message_id,
                        channel_id=str(message.get("channel_id") or ""),
                        channel_name=message.get("channel_name"),
                        slack_user_id=message.get("user"),
                        author=message.get("author"),
                        posted_at=_parse_ts(ts),
                        text=text,
                        permalink=message.get("permalink"),
                        thread_ts=message.get("thread_ts"),
                        created_at=_now(),
                    )
                )
                session.commit()
            finally:
                session.close()

            self.gateway.upsert_slack_message(
                {
                    "id": message_id,
                    "channel_id": str(message.get("channel_id") or ""),
                    "channel_name": message.get("channel_name") or "",
                    "author": message.get("author") or "",
                    "slack_user_id": message.get("user") or "",
                    "posted_at": (message.get("posted_at") or ts),
                    "excerpt": text[:SLACK_EXCERPT_CHARS],
                    "permalink": message.get("permalink") or "",
                    "thread_ts": message.get("thread_ts") or "",
                }
            )
            summary["messages"] += 1

            author = message.get("author")
            if author:
                matched = self.resolve_entities([author])
                person_ids = [row["id"] for row in matched.values() if row["label"] == "Person"]
                if person_ids:
                    summary["attributed"] += self.gateway.link_slack_author(
                        message_id, person_ids
                    )

            about = message.get("about") or []
            if about:
                resolved = self.resolve_entities([str(term) for term in about])
                edges = [
                    {"target_id": row["id"]} for row in resolved.values()
                ]
                summary["linked"] += self.gateway.link_slack_message(message_id, edges)

        emit(f"complete: {summary['messages']} message(s)")
        return summary


def _empty_outcome() -> Any:
    """An extraction that ran but found nothing, used when the model is off."""
    from app.services.doc_extractor import ExtractionOutcome, ExtractionResult

    return ExtractionOutcome(result=ExtractionResult())


# A sentence fragment naming one technology as the thing left behind and another
# as the thing moved to.
_FROM_TO = re.compile(r"\bfrom\s+(?P<from>[^.!?\n]{0,60}?)\s+to\s+(?P<to>[^.!?\n]{0,60})", re.IGNORECASE)
_SENTENCE_SPLIT = re.compile(r"[.!?\n]+")


def _mentions(fragment: str, name: str) -> bool:
    """Whether a text fragment names a given technology."""
    return name.lower() in fragment.lower()


def _migration_pairs(text: str, technologies: List[str]) -> List[Tuple[str, str]]:
    """Find (left behind, moved to) pairs a document states explicitly.

    Both ends must match a name the extraction identified. A fragment that names
    nothing recognisable is skipped rather than becoming a technology node, so a
    trailing clause like "in June 2024" never turns into a system.
    """
    pairs: List[Tuple[str, str]] = []
    for sentence in _SENTENCE_SPLIT.split(text):
        for match in _FROM_TO.finditer(sentence):
            source_fragment = match.group("from")
            target_fragment = match.group("to")

            sources = [name for name in technologies if _mentions(source_fragment, name)]
            targets = [name for name in technologies if _mentions(target_fragment, name)]

            for source in sources:
                for target in targets:
                    if source.lower() == target.lower():
                        continue
                    pair = (source, target)
                    if pair not in pairs:
                        pairs.append(pair)
    return pairs


def _parse_ts(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc)
    except (TypeError, ValueError):
        return None