"""Model-provider contract for answer synthesis.

A provider is only ever asked to write a narrative from evidence that has
already been retrieved. It is never given a query, never given credentials
for the graph, and never asked to decide what is true.

Failures are values, not exceptions. A synthesis failure has to be
recoverable in the same way a missing document is, so every provider method
returns a typed outcome and the caller decides what to do.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@dataclass
class SynthesisRequest:
    """An evidence package and the question that motivated it."""

    question: str
    facts: str
    citations: List[Dict[str, Any]] = field(default_factory=list)
    intent: str = ""
    entity_id: str = ""


@dataclass
class SynthesisSuccess:
    """A generated narrative plus what it cost."""

    answer: str
    model: str
    usage: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SynthesisFailure:
    """Why no narrative was produced. Never carries credentials."""

    reason: str
    detail: str = ""
    attempts: int = 0

    def __bool__(self) -> bool:
        return False


SynthesisOutcome = Any  # SynthesisSuccess | SynthesisFailure


@runtime_checkable
class LLMProvider(Protocol):
    """What the ask path needs from a model provider."""

    async def generate_synthesis(self, request: SynthesisRequest) -> SynthesisOutcome:
        """Return a narrative for the evidence, or a typed failure."""
        ...


def evidence_package_payload(request: SynthesisRequest) -> Dict[str, Any]:
    """Serialise the citations a narrative is allowed to cite."""
    return {
        "citations": [
            {
                "source_id": citation.get("source_id"),
                "title": citation.get("title"),
                "type": citation.get("type"),
                "excerpt": (citation.get("excerpt") or "")[:400],
            }
            for citation in request.citations
        ]
    }


def citeable_ids(request: SynthesisRequest) -> List[str]:
    return [
        citation.get("source_id")
        for citation in request.citations
        if citation.get("source_id")
    ]


def unavailable_provider(reason: str, detail: str = "") -> Optional[LLMProvider]:
    """Return None so the caller can fall back deterministically."""
    return None