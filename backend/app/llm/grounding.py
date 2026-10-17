"""Citation validation: the boundary between generated text and evidence.

A generated answer is only allowed to stand on sources that were actually
retrieved. This module is what makes that claim checkable rather than
aspirational.

The rules, in order of severity:

1. Every identifier cited must exist in the evidence package.
2. An answer with no citation that resolves is treated as unsupported and is
   discarded, whatever the provider said.
3. An answer that cites a mix of real and invented identifiers has the
   invented ones removed and is marked as degraded, but is kept when it still
   rests on real sources.
4. An answer citing nothing at all is also unsupported.

Removing an invented identifier is not the same as removing the claim around
it, so a degraded answer is also downgraded in confidence and carries an
explicit note. Anything that survives to the client therefore either stands
on real evidence or says plainly that it does not.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence

logger = logging.getLogger(__name__)

# [source_id] where the identifier is a plain stable id. Deliberately strict:
# anything that is not a bare identifier inside brackets is left alone rather
# than guessed at, because markdown links must keep working.
CITATION_PATTERN = re.compile(r"\[([A-Za-z0-9_.:-]{2,120})\]")

CONFIDENCE = {"supported": 3, "partial": 2, "insufficient": 0}


@dataclass
class GroundingResult:
    """The verdict on one generated answer."""

    answer: str
    valid_ids: List[str] = field(default_factory=list)
    invalid_ids: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    accepted: bool = True

    @property
    def degraded(self) -> bool:
        return bool(self.invalid_ids) and self.accepted

    @property
    def confidence_ceiling(self) -> str:
        """Highest confidence this answer may carry."""
        if not self.accepted:
            return "insufficient"
        if self.invalid_ids:
            return "partial"
        return "supported"


def extract_citations(answer: str) -> List[str]:
    """Return every identifier cited in the answer, in order, de-duplicated."""
    seen: set[str] = set()
    ordered: List[str] = []
    for match in CITATION_PATTERN.finditer(answer or ""):
        identifier = match.group(1)
        if identifier in seen:
            continue
        seen.add(identifier)
        ordered.append(identifier)
    return ordered


def strip_invalid_citations(answer: str, invalid: Iterable[str]) -> str:
    """Remove citation tags that do not correspond to real evidence."""
    invalid_set = set(invalid)
    if not invalid_set:
        return answer

    def replace(match: "re.Match[str]") -> str:
        if match.group(1) in invalid_set:
            return ""
        return match.group(0)

    return CITATION_PATTERN.sub(replace, answer or "")


def validate_citations(
    answer: str,
    allowed_ids: Sequence[str],
    *,
    require_citation: bool = True,
) -> GroundingResult:
    """Check a generated answer against the sources that were retrieved."""
    allowed = {identifier for identifier in allowed_ids if identifier}
    cited = extract_citations(answer)

    if not cited:
        if not require_citation:
            return GroundingResult(answer=answer, notes=["No citations were required."])
        return GroundingResult(
            answer=answer,
            notes=[
                "The generated answer cited no source, so it cannot be shown as "
                "evidence-backed."
            ],
            accepted=False,
        )

    valid = [identifier for identifier in cited if identifier in allowed]
    invalid = [identifier for identifier in cited if identifier not in allowed]

    if not valid:
        # Every citation was invented. Nothing here is supportable.
        return GroundingResult(
            answer=answer,
            valid_ids=[],
            invalid_ids=invalid,
            notes=[
                "The generated answer cited only identifiers that are absent from "
                "the evidence, so it was discarded."
            ],
            accepted=False,
        )

    notes: List[str] = []
    if invalid:
        notes.append(
            "Removed citation(s) not present in the retrieved evidence: "
            + ", ".join(invalid)
        )

    return GroundingResult(
        answer=strip_invalid_citations(answer, invalid),
        valid_ids=valid,
        invalid_ids=invalid,
        notes=notes,
        accepted=True,
    )


def lower_confidence(current: str, ceiling: str) -> str:
    """Never report a confidence higher than grounding allows."""
    if CONFIDENCE.get(ceiling, 0) < CONFIDENCE.get(current, 0):
        return ceiling
    return current