"""Pure extraction of cross-repository dependencies from build manifests.

Only dependencies that name an actual repository URL produce an edge. Registry
packages are never mapped to a guessed repository, because a wrong guess would
put a fabricated relationship into the knowledge graph.
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass

_GITHUB_SLUG = re.compile(r"github\.com[:/]+(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)")
_GITLAB_SLUG = re.compile(r"gitlab\.com[:/]+(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)")


@dataclass(frozen=True)
class RepositoryDependency:
    """A dependency on another repository, with the source that declared it."""

    owner: str
    repo: str
    declared_in: str
    kind: str

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.repo}"

    @property
    def repository_id(self) -> str:
        owner = re.sub(r"[^a-z0-9]+", "_", self.owner.lower()).strip("_")
        repo = re.sub(r"[^a-z0-9]+", "_", self.repo.lower()).strip("_")
        return f"repo_{owner}_{repo}"

    @property
    def url(self) -> str:
        return f"https://github.com/{self.owner}/{self.repo}"


def normalise_repository_url(url: str) -> RepositoryDependency | None:
    """Extract owner/repo from a git URL, or None when it is not a known host.

    Handles both ``https://host/owner/repo.git`` and scp-style
    ``git@host:owner/repo.git`` forms.
    """
    if not url:
        return None

    cleaned = url.strip().rstrip("/")
    if cleaned.endswith(".git"):
        cleaned = cleaned[: -len(".git")]

    match = _GITHUB_SLUG.search(cleaned) or _GITLAB_SLUG.search(cleaned)
    if not match:
        return None

    return RepositoryDependency(
        owner=match.group("owner"),
        repo=match.group("repo"),
        declared_in="",
        kind="git-url",
    )


def parse_gitmodules(text: str) -> list[RepositoryDependency]:
    """Read git submodule URLs from a ``.gitmodules`` file."""
    dependencies: list[RepositoryDependency] = []
    path: str | None = None

    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("[submodule"):
            path = None
            continue

        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()

        if key == "path":
            path = value
        elif key == "url":
            dependency = normalise_repository_url(value)
            if dependency is not None:
                dependencies.append(
                    RepositoryDependency(
                        owner=dependency.owner,
                        repo=dependency.repo,
                        declared_in=path or ".gitmodules",
                        kind="submodule",
                    )
                )

    return dependencies


def parse_cargo_toml(text: str) -> list[RepositoryDependency]:
    """Read ``git`` dependencies and git submodule paths from a Cargo manifest."""
    if not text:
        return []

    try:
        manifest = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return []

    dependencies: list[RepositoryDependency] = []
    sections = (
        "dependencies",
        "dev-dependencies",
        "build-dependencies",
    )

    for section in sections:
        table = manifest.get(section)
        if not isinstance(table, dict):
            continue

        for name, spec in table.items():
            url = spec.get("git") if isinstance(spec, dict) else None
            if not url:
                continue
            dependency = normalise_repository_url(url)
            if dependency is not None:
                dependencies.append(
                    RepositoryDependency(
                        owner=dependency.owner,
                        repo=dependency.repo,
                        declared_in=f"Cargo.toml:{section}:{name}",
                        kind="cargo-git",
                    )
                )

    return dependencies


def parse_package_json(text: str) -> list[RepositoryDependency]:
    """Read the ``repository`` field from an npm manifest."""
    if not text:
        return []

    try:
        manifest = json.loads(text)
    except json.JSONDecodeError:
        return []

    field = manifest.get("repository")
    url = field.get("url") if isinstance(field, dict) else field
    if not isinstance(url, str):
        return []

    dependency = normalise_repository_url(url)
    if dependency is None:
        return []

    return [
        RepositoryDependency(
            owner=dependency.owner,
            repo=dependency.repo,
            declared_in="package.json:repository",
            kind="npm",
        )
    ]


def parse_pyproject_toml(text: str) -> list[RepositoryDependency]:
    """Read ``[project.urls]`` repository/homepage links from a Python manifest."""
    if not text:
        return []

    try:
        manifest = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return []

    urls = manifest.get("project", {}).get("urls")
    if not isinstance(urls, dict):
        return []

    for key in ("Repository", "Source", "Homepage"):
        url = urls.get(key)
        if not isinstance(url, str):
            continue
        dependency = normalise_repository_url(url)
        if dependency is not None:
            return [
                RepositoryDependency(
                    owner=dependency.owner,
                    repo=dependency.repo,
                    declared_in=f"pyproject.toml:urls.{key}",
                    kind="pypi",
                )
            ]

    return []


def parse_codeowners(text: str) -> list[tuple[str, list[str]]]:
    """Read CODEOWNERS into ``(owner_pattern, path_prefixes)`` pairs.

    Handles both forms GitHub accepts: bracketed sections and a bare list of
    ``pattern @owner`` lines.
    """
    entries: list[tuple[str, list[str]]] = []

    for raw_line in (text or "").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            continue

        tokens = line.split()
        owners = [token for token in tokens if token.startswith("@")]
        paths = [token for token in tokens if not token.startswith("@")]
        if owners and paths:
            entries.append((",".join(owners), paths))

    return entries


def collect_dependencies(manifests: dict[str, str]) -> list[RepositoryDependency]:
    """Scan a mapping of filename to contents and return unique dependencies."""
    collectors = {
        ".gitmodules": parse_gitmodules,
        "Cargo.toml": parse_cargo_toml,
        "package.json": parse_package_json,
        "pyproject.toml": parse_pyproject_toml,
    }

    seen: dict[str, RepositoryDependency] = {}
    for filename, contents in manifests.items():
        basename = filename.rsplit("/", 1)[-1]
        collector = collectors.get(basename)
        if collector is None:
            continue
        for dependency in collector(contents):
            seen.setdefault(dependency.slug, dependency)

    return list(seen.values())