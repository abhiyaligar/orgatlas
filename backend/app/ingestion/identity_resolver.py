"""Resolution of commit authors to seeded People or external identities."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable, Protocol

from app.ingestion.git_history_parser import is_automation_author


@dataclass(frozen=True)
class ResolvedIdentity:
    """The attribution target for a commit author."""

    kind: str  # "person" | "external" | "automation"
    identity_id: str
    display_name: str
    matched_person_id: str | None = None

    @property
    def is_employee(self) -> bool:
        return self.kind == "person"


class PersonLookup(Protocol):
    """Minimal view of the seeded employee graph needed for resolution."""

    def person_id_for_email(self, email: str) -> str | None: ...


class InMemoryPersonLookup:
    """Email to Person lookup backed by an in-memory mapping."""

    def __init__(self, mapping: dict[str, str] | None = None) -> None:
        self._mapping = {key.strip().lower(): value for key, value in (mapping or {}).items()}

    def person_id_for_email(self, email: str) -> str | None:
        return self._mapping.get((email or "").strip().lower())


def external_identity_id(email: str, provider: str = "github") -> str:
    """Build a stable identifier for an unseeded contributor.

    The identifier is a digest of the email so the raw address is not embedded
    in a node id that may later be logged or displayed.
    """
    normalised = (email or "").strip().lower()
    digest = hashlib.sha256(normalised.encode("utf-8")).hexdigest()[:16]
    return f"eid_{provider}_{digest}"


def resolve_author(
    name: str,
    email: str,
    lookup: PersonLookup,
    provider: str = "github",
) -> ResolvedIdentity:
    """Attribute a commit author to a seeded person, an external identity, or a bot."""
    display = (name or "").strip() or (email or "").strip()

    if is_automation_author(email, name):
        return ResolvedIdentity(kind="automation", identity_id="", display_name=display)

    person_id = lookup.person_id_for_email(email)
    if person_id:
        return ResolvedIdentity(
            kind="person",
            identity_id=person_id,
            display_name=display,
            matched_person_id=person_id,
        )

    return ResolvedIdentity(
        kind="external",
        identity_id=external_identity_id(email, provider=provider),
        display_name=display,
    )


def resolve_authors(
    authors: Iterable[tuple[str, str]],
    lookup: PersonLookup,
    provider: str = "github",
) -> list[ResolvedIdentity]:
    """Resolve every distinct author, keeping automation accounts out of the graph."""
    resolved: dict[str, ResolvedIdentity] = {}
    for name, email in authors:
        identity = resolve_author(name, email, lookup, provider=provider)
        if identity.kind == "automation":
            continue
        resolved.setdefault(identity.identity_id, identity)
    return list(resolved.values())