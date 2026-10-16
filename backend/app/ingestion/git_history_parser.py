"""Pure parsing of captured ``git log`` output.

This module performs no network access and no subprocess execution so it can
be unit tested against captured fixtures with zero external dependencies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

RECORD_SEPARATOR = "\x1e"
FIELD_SEPARATOR = "\x1f"

GIT_LOG_FORMAT = (
    f"%x1e%H{FIELD_SEPARATOR}%an{FIELD_SEPARATOR}%ae{FIELD_SEPARATOR}"
    f"%aI{FIELD_SEPARATOR}%s{FIELD_SEPARATOR}%P"
)

_SQUASH_PR = re.compile(r"\(#(\d+)\)")
_MERGE_PR = re.compile(r"Merge pull request #(\d+)\b")
_OWNER_KEYS = (".github/", "CODEOWNERS")

_LANGUAGE_BY_SUFFIX = {
    ".rs": "Rust",
    ".py": "Python",
    ".js": "JavaScript",
       ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".go": "Go",
    ".java": "Java",
    ".c": "C",
    ".h": "C",
    ".cc": "C++",
    ".cpp": "C++",
    ".hpp": "C++",
    ".rb": "Ruby",
    ".sh": "Shell",
    ".bash": "Shell",
    ".ps1": "PowerShell",
    ".toml": "TOML",
    ".yml": "YAML",
    ".yaml": "YAML",
    ".json": "JSON",
    ".md": "Markdown",
}

_TEST_PATH_SEGMENTS = ("test", "tests", "spec", "specs", "fuzz", "bench", "benches", "fixtures")
_TEST_FILE_PREFIXES = ("test_", "bench_", "fuzz_")
_TEST_FILE_SUFFIXES = (
    "_test.py",
    "_test.go",
    "_test.rs",
    ".test.ts",
    ".test.tsx",
    ".spec.ts",
    ".spec.tsx",
)


@dataclass(frozen=True)
class CommitRecord:
    """One revision with the files it touched."""

    sha: str
    author_name: str
    author_email: str
    authored_at: str
    subject: str
    parents: tuple[str, ...]
    files: tuple[str, ...] = field(default_factory=tuple)

    @property
    def short_sha(self) -> str:
        return self.sha[:12]

    @property
    def is_merge(self) -> bool:
        return len(self.parents) > 1

    @property
    def pr_number(self) -> int | None:
        return extract_pr_number(self.subject)


def extract_pr_number(subject: str) -> int | None:
    """Recover a pull-request number from squash- or merge-style commit subjects."""
    for pattern in (_MERGE_PR, _SQUASH_PR):
        match = pattern.search(subject or "")
        if match:
            return int(match.group(1))
    return None


def detect_language(path: str) -> str:
    """Best-effort language label from a file extension."""
    lowered = (path or "").lower()
    for suffix, language in _LANGUAGE_BY_SUFFIX.items():
        if lowered.endswith(suffix):
            return language
    return "Other"


def is_test_path(path: str) -> bool:
    """Flag test, benchmark and fuzz files so risk scoring can weight them."""
    lowered = (path or "").lower()
    if not lowered:
        return False

    segments = lowered.split("/")
    if any(segment in _TEST_PATH_SEGMENTS for segment in segments[:-1]):
        return True

    name = segments[-1]
    if name.startswith(_TEST_FILE_PREFIXES):
        return True

    return name.endswith(_TEST_FILE_SUFFIXES)


def module_path_for(path: str) -> str:
    """Return the directory grouping for a file, or '' for repository root files."""
    if "/" not in path:
        return ""
    return path.rsplit("/", 1)[0]


def is_automation_author(email: str, name: str = "") -> bool:
    """Identify bot and automation accounts so they are not treated as people."""
    lowered_email = (email or "").lower()
    lowered_name = (name or "").lower()
    markers = ("[bot]", "bot@", "dependabot", "renovate", "github-actions", "noreply@")
    return any(marker in lowered_email for marker in markers) or lowered_name.endswith("[bot]")


def parse_git_log(raw: str) -> list[CommitRecord]:
    """Parse output produced by ``git log`` using :data:`GIT_LOG_FORMAT`.

    Records are separated by ``\\x1e``, fields by ``\\x1f``; the touched file
    list follows the sixth field, one path per line.

    Merge commits legitimately carry an empty file list: ``git log --name-only``
    suppresses the combined diff for merges. The content of a merged branch is
    still present via its own non-merge commits, so no history is lost.
    """
    if not raw:
        return []

    commits: list[CommitRecord] = []
    for chunk in raw.split(RECORD_SEPARATOR):
        if not chunk.strip():
            continue

        parts = chunk.split(FIELD_SEPARATOR)
        if len(parts) < 6:
            continue

        sha = parts[0].strip()
        if not sha:
            continue

        # The sixth field carries the parents followed by a newline and the
        # touched file list, one path per line.
        tail = parts[5].splitlines()
        parents = tuple(p for p in tail[0].split() if p) if tail else ()
        files = tuple(line.strip() for line in tail[1:] if line.strip())

        commits.append(
            CommitRecord(
                sha=sha,
                author_name=parts[1].strip(),
                author_email=parts[2].strip(),
                authored_at=parts[3].strip(),
                subject=parts[4].strip(),
                parents=parents,
                files=files,
            )
        )

    return commits


def collect_unique_files(commits: Iterable[CommitRecord]) -> list[str]:
    """Distinct touched file paths, in first-seen order."""
    seen: dict[str, None] = {}
    for commit in commits:
        for path in commit.files:
            seen.setdefault(path, None)
    return list(seen)


def collect_authors(commits: Iterable[CommitRecord]) -> list[tuple[str, str]]:
    """Distinct ``(name, email)`` pairs, in first-seen order."""
    seen: dict[tuple[str, str], None] = {}
    for commit in commits:
        seen.setdefault((commit.author_name, commit.author_email), None)
    return list(seen)


def collect_codeowners_paths(owners: str) -> list[str]:
    """Extract path prefixes from a CODEOWNERS file body."""
    prefixes: list[str] = []
    for line in (owners or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("["):
            continue
        candidate = stripped.split()[0]
        if candidate not in _OWNER_KEYS:
            prefixes.append(candidate)
    return prefixes