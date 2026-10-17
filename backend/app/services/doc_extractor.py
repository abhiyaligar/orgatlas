"""Extract graph facts from a document.

This is the one place OrgAtlas asks a model to *add* to the graph rather than to
phrase an answer, which changes the risk profile and the rules that follow from
it:

* Every extracted item must carry the exact sentence it came from, so a reader
  can check the claim against the source without opening the file.
* An item whose supporting quote cannot be found in the document is dropped.
  A paraphrase is not evidence, and a citation that does not resolve is worse
  than no citation because it looks verified.
* Nothing is inferred that the document does not state. A document that says a
  migration improved latency but never says by how much yields a decision and no
  metric, rather than a metric invented to fill the gap.

The raw response is returned alongside the parsed result so an extraction can be
audited against what the model actually said.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

PROMPT_VERSION = "doc-extract-v1"

# Extraction emits a JSON object of a few kilobytes. A non-reasoning model
# produces that in well under 4,000 tokens, and it is the configured default for
# extraction precisely because a reasoning model spends an order of magnitude
# more thinking first.
MAX_TOKENS = 4096
MAX_TOKEN_CEILING = 32768

# Overridden at construction from settings; kept as a fallback for tests and for
# a deployment that sets no extraction model.
MODEL_NAME = "deepseek-ai/DeepSeek-V4.1-Flash"


class _ProviderClient:
    """Thin wrapper over the shared chat helper, shaped for one extraction.

    The configured model is a reasoning model: it spends completion tokens
    thinking before it answers. A budget that looks generous for a JSON object
    can be entirely consumed by reasoning, leaving an empty or truncated
    response. That is not a transient failure, so the shared retry helper does
    not help -- the budget itself has to grow, and it does so here.
    """

    def __init__(self, timeout: int, max_retries: int, max_tokens: int, model: str) -> None:
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_tokens = max_tokens
        self.model = model

    def complete(self, messages: List[Dict[str, str]]) -> Any:
        from app.services.llm_client import _chat

        budget = self.max_tokens
        last_completion = None

        for attempt in range(1, self.max_retries + 2):
            completion = _chat(
                messages,
                timeout=self.timeout,
                max_retries=self.max_retries,
                max_tokens=budget,
                model=self.model,
            )
            last_completion = completion

            choice = completion.choices[0]
            content = choice.message.content or ""
            finish = getattr(choice, "finish_reason", "") or ""
            used = getattr(getattr(completion, "usage", None), "completion_tokens", 0) or 0

            exhausted = finish in ("length", "max_tokens") or (not content.strip() and used)
            if not exhausted or attempt == self.max_retries + 1:
                break

            budget = min(budget * 2, MAX_TOKEN_CEILING)
            logger.info(
                "extraction response exhausted its %s-token budget; retrying with %s",
                used or budget // 2,
                budget,
            )

        choice = last_completion.choices[0]
        usage = getattr(last_completion, "usage", None)
        return SimpleNamespace(
            text=choice.message.content or "",
            finish_reason=getattr(choice, "finish_reason", "") or "",
            usage={
                "total_tokens": getattr(usage, "total_tokens", None),
                "prompt_tokens": getattr(usage, "prompt_tokens", None),
                "completion_tokens": getattr(usage, "completion_tokens", None),
            },
        )

MAX_ITEMS = {
    "decisions": 8,
    "people": 25,
    "quotes": 12,
    "metrics": 15,
    "entities": 40,
}

SYSTEM_PROMPT = """You extract structured facts from a company document so they can be \
retrieved later as evidence.

Return JSON only, with no prose and no code fence.

Shape:
{
  "decisions": [
    {"title": "...", "summary": "why it was decided, in the document's own terms",
     "rationale": "...", "alternatives": "...", "status": "proposed|accepted|rejected|deprecated|unknown",
     "decided_at": "ISO date or null", "quote": "the exact sentence that states the decision"}
  ],
  "people": [{"name": "...", "role": "their role in the document, or null",
              "involvement": "proposed|approved|objected|implemented|reviewed|discussed|unknown",
              "quote": "the exact sentence that attributes this to them"}],
  "quotes": [{"speaker": "...", "text": "what they said, quoted verbatim", "context": "..."}],
  "metrics": [{"name": "...", "value": 0.0, "unit": "percent|ms|count|duration|ratio|score|unknown",
               "baseline": "what it was before, or null", "direction": "improvement|regression|neutral",
               "quote": "the exact sentence containing the number"}],
  "entities": [{"name": "...", "kind": "Service|Technology|Decision|Team|Repository|Product|unknown",
                "mentions": 1}]
}

Rules:
- "quote" must be copied character-for-character from the document. It is checked.
- If the document states no number, return no metric. Never estimate one.
- If the document does not say why, leave "rationale" empty rather than inventing one.
- Do not merge two separate decisions into one entry.
- Return an empty list rather than guessing when a section has nothing."""


@dataclass
class ExtractionResult:
    decisions: List[Dict[str, Any]] = field(default_factory=list)
    people: List[Dict[str, Any]] = field(default_factory=list)
    quotes: List[Dict[str, Any]] = field(default_factory=list)
    metrics: List[Dict[str, Any]] = field(default_factory=list)
    entities: List[Dict[str, Any]] = field(default_factory=list)

    def counts(self) -> Dict[str, int]:
        return {
            "decisions": len(self.decisions),
            "people": len(self.people),
            "quotes": len(self.quotes),
            "metrics": len(self.metrics),
            "entities": len(self.entities),
        }

    def to_payload(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ExtractionOutcome:
    """What was extracted, plus the record of how it was obtained."""

    result: ExtractionResult
    model: Optional[str] = None
    prompt_version: str = PROMPT_VERSION
    input_sha: str = ""
    usage: Dict[str, Any] = field(default_factory=dict)
    raw_response: str = ""
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None


def _normalise(text: str) -> str:
    """Fold whitespace so a quote can be found across a line wrap."""
    return re.sub(r"\s+", " ", (text or "").strip())


def quote_is_supported(quote: str, document_text: str) -> bool:
    """Whether the document actually contains this sentence.

    Whitespace is folded on both sides because a PDF or a wrap point will have
    inserted line breaks the model reasonably removed. Everything else must match
    exactly: a paraphrase is not evidence.
    """
    if not quote or not quote.strip():
        return False
    return _normalise(quote) in _normalise(document_text)


def _coerce(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _as_float(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = re.search(r"-?\d+(?:\.\d+)?", value)
        if match:
            return float(match.group(0))
    return None


def _parse_json(raw: str) -> Dict[str, Any]:
    """Pull the JSON object out of a response that may be wrapped in prose."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"```\s*$", "", text).strip()
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in response")
    parsed = json.loads(text[start : end + 1])
    return parsed if isinstance(parsed, dict) else {}


def validate(parsed: Dict[str, Any], document_text: str) -> ExtractionResult:
    """Keep only items the document actually supports.

    Drops rather than repairs. An item whose quote is missing or unresolvable is
    removed and counted, so a caller can see how much of the model's output
    survived verification instead of assuming all of it did.
    """
    result = ExtractionResult()

    for entry in _iter_list(parsed.get("decisions")):
        quote = _coerce(entry.get("quote"))
        if not quote_is_supported(quote, document_text):
            logger.info("dropping decision with unverifiable quote")
            continue
        title = _coerce(entry.get("title"))
        if not title:
            continue
        result.decisions.append(
            {
                "title": title[:300],
                "summary": _coerce(entry.get("summary"))[:2000],
                "rationale": _coerce(entry.get("rationale"))[:2000],
                "alternatives": _coerce(entry.get("alternatives"))[:1000],
                "status": _coerce(entry.get("status"), "unknown")[:40].lower(),
                "decided_at": _coerce(entry.get("decided_at"))[:40] or None,
                "quote": quote,
            }
        )

    for entry in _iter_list(parsed.get("people")):
        quote = _coerce(entry.get("quote"))
        name = _coerce(entry.get("name"))
        if not name:
            continue
        # A person with a fabricated quote is dropped. With no quote at all the
        # name may still come from a byline or a table, so it is kept, marked.
        if quote and not quote_is_supported(quote, document_text):
            logger.info("dropping person with unverifiable quote: %s", name)
            continue
        result.people.append(
            {
                "name": name[:200],
                "role": _coerce(entry.get("role"))[:200],
                "involvement": _coerce(entry.get("involvement"), "unknown")[:40].lower(),
                "quote": quote,
            }
        )

    for entry in _iter_list(parsed.get("quotes")):
        text_quote = _coerce(entry.get("text"))
        speaker = _coerce(entry.get("speaker"))
        if not text_quote or not speaker:
            continue
        if not quote_is_supported(text_quote, document_text):
            logger.info("dropping quote not present verbatim")
            continue
        result.quotes.append(
            {
                "speaker": speaker[:200],
                "text": text_quote[:2000],
                "context": _coerce(entry.get("context"))[:500],
            }
        )

    for entry in _iter_list(parsed.get("metrics")):
        quote = _coerce(entry.get("quote"))
        if not quote_is_supported(quote, document_text):
            logger.info("dropping metric with unverifiable quote")
            continue
        value = _as_float(entry.get("value"))
        if value is None:
            continue
        name = _coerce(entry.get("name"))
        if not name:
            continue
        result.metrics.append(
            {
                "name": name[:200],
                "value": value,
                "unit": _coerce(entry.get("unit"), "unknown")[:40],
                "baseline": _coerce(entry.get("baseline"))[:200] or None,
                "direction": _coerce(entry.get("direction"), "unknown")[:40].lower(),
                "quote": quote,
            }
        )

    for entry in _iter_list(parsed.get("entities")):
        name = _coerce(entry.get("name"))
        if not name:
            continue
        result.entities.append(
            {
                "name": name[:200],
                "kind": _coerce(entry.get("kind"), "unknown")[:40],
                "mentions": _as_float(entry.get("mentions")) or 1.0,
            }
        )

    for key in MAX_ITEMS:
        setattr(result, key, getattr(result, key)[: MAX_ITEMS[key]])

    return result


def _iter_list(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [entry for entry in value if isinstance(entry, dict)]


class DocumentExtractor:
    """Runs one extraction. Injectable client so tests never call a provider.

    The default client is the same retrying chat helper the file-description
    fallback uses, so document extraction shares one provider configuration and
    one set of transient-failure semantics with the rest of the system.
    """

    def __init__(
        self,
        client: Any = None,
        model: Optional[str] = None,
        timeout: int = 120,
        max_retries: int = 2,
        max_tokens: int = MAX_TOKENS,
    ) -> None:
        from app.core.config import settings

        self._client = client
        # Falls back to the answer model so a deployment that sets no extraction
        # model still works, at the reasoning model's cost.
        self.model = (
            model
            or getattr(settings, "NEBIUS_EXTRACTION_MODEL_NAME", None)
            or settings.NEBIUS_MODEL_NAME
            or MODEL_NAME
        )
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_tokens = max_tokens

    def _resolve_client(self) -> Any:
        if self._client is None:
            self._client = _ProviderClient(
                timeout=self.timeout,
                max_retries=self.max_retries,
                max_tokens=self.max_tokens,
                model=self.model,
            )
        return self._client

    def extract(self, title: str, text: str, kind: str = "text") -> ExtractionOutcome:
        """Extract from one document, verifying every claim against its source."""
        input_sha = hashlib.sha256(f"{title}\n{text}".encode("utf-8")).hexdigest()

        if not text.strip():
            return ExtractionOutcome(
                result=ExtractionResult(),
                input_sha=input_sha,
                error="document has no text to extract from",
            )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Document title: {title}\n"
                    f"Document kind: {kind}\n\n"
                    f"---- BEGIN DOCUMENT ----\n{text}\n---- END DOCUMENT ----"
                ),
            },
        ]

        try:
            client = self._resolve_client()
            raw = client.complete(messages)
        except Exception as exc:
            logger.warning("extraction failed for %s: %s", title, exc)
            return ExtractionOutcome(
                result=ExtractionResult(),
                input_sha=input_sha,
                error=f"{type(exc).__name__}: {exc}",
            )

        raw_text = getattr(raw, "text", "") or ""
        usage = getattr(raw, "usage", {}) or {}

        try:
            parsed = _parse_json(raw_text)
        except Exception as exc:
            return ExtractionOutcome(
                result=ExtractionResult(),
                model=self.model,
                input_sha=input_sha,
                usage=usage,
                raw_response=raw_text,
                error=f"could not parse extraction JSON: {exc}",
            )

        result = validate(parsed, text)
        return ExtractionOutcome(
            result=result,
            model=self.model,
            input_sha=input_sha,
            usage=usage,
            raw_response=raw_text,
        )