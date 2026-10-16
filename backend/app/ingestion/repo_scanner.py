"""Repository scanning executed inside the E2B sandbox.

Everything in this module runs in the sandbox process. It performs git
operations and produces a JSON payload; it never touches the graph database
and never receives database or model-provider credentials.
"""

from __future__ import annotations

import base64
import fnmatch
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from app.ingestion.dependency_scanner import collect_dependencies
from app.ingestion.git_history_parser import (
    GIT_LOG_FORMAT,
    CommitRecord,
    collect_authors,
    collect_codeowners_paths,
    collect_unique_files,
    detect_language,
    is_test_path,
    module_path_for,
    parse_git_log,
)

MANIFEST_FILENAMES = (
    ".gitmodules",
    "Cargo.toml",
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "go.mod",
    "pom.xml",
    "Gemfile",
)

OUTPUT_FILENAME = "graph.json"

# Always ingested regardless of include globs, because dependency edges and
# ownership are derived from them.
ALWAYS_KEEP = frozenset({".gitmodules", "CODEOWNERS", ".github/CODEOWNERS"})


class FileFilter:
    """Applies the include globs and exclude paths from the repository config.

    Filters are applied to the touched-file list before any node or edge is
    created, so excluded paths never reach the graph.
    """

    def __init__(
        self,
        include_globs: list[str] | None = None,
        exclude_paths: list[str] | None = None,
    ) -> None:
        self.include_globs = [glob for glob in (include_globs or []) if glob]
        self.exclude_paths = [path for path in (exclude_paths or []) if path]

    @classmethod
    def from_config(cls, config: dict | None) -> "FileFilter":
        config = config or {}
        return cls(
            include_globs=config.get("include_globs"),
            exclude_paths=config.get("exclude_paths"),
        )

    def keep(self, path: str) -> bool:
        if not path:
            return False
        if path in ALWAYS_KEEP:
            return True

        normalised = path.replace("\\", "/")

        for pattern in self.exclude_paths:
            if _matches(normalised, pattern):
                return False

        if self.include_globs and not any(
            _matches(normalised, pattern) for pattern in self.include_globs
        ):
            return False

        return True

    def apply(self, commits):
        """Return commits with filtered file lists, dropping any that become empty."""
        kept = []
        for commit in commits:
            filtered = tuple(path for path in commit.files if self.keep(path))
            if not filtered and commit.files:
                # Every touched path was excluded; the commit has no graph relevance.
                continue
            kept.append(
                CommitRecord(
                    sha=commit.sha,
                    author_name=commit.author_name,
                    author_email=commit.author_email,
                    authored_at=commit.authored_at,
                    subject=commit.subject,
                    parents=commit.parents,
                    files=filtered,
                )
            )
        return kept


def _matches(path: str, pattern: str) -> bool:
    """Match a repository-relative path against a prefix or glob pattern."""
    pattern = pattern.replace("\\", "/").rstrip("/")
    if not pattern:
        return False

    if any(char in pattern for char in "*?["):
        return fnmatch.fnmatch(path, pattern)

    return path == pattern or path.startswith(f"{pattern}/")


class ScanError(RuntimeError):
    """Raised when the repository cannot be cloned or scanned."""


def _run(command: list[str], cwd: str | None = None, timeout: int = 900) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise ScanError(f"{' '.join(command[:3])} failed: {stderr[:300]}")
    return result.stdout.decode("utf-8", errors="replace")


def clone_repository(url: str, destination: str, depth: int) -> str:
    """Clone only the target repository.

    Submodules are deliberately **not** fetched: dependency edges are derived
    from manifest text in the target's own working tree, so no dependency
    repository is ever downloaded.
    """
    target = os.path.join(destination, "repo")
    _run(
        [
            "git",
            "clone",
            "--depth",
            str(depth),
            "--single-branch",
            "--no-tags",
            url,
            target,
        ]
    )
    return target


def read_manifests(repo_path: str) -> dict[str, str]:
    """Read build manifests from the working tree, ignoring anything unreadable."""
    manifests: dict[str, str] = {}
    root = Path(repo_path)

    for name in MANIFEST_FILENAMES:
        candidate = root / name
        if candidate.is_file():
            try:
                manifests[name] = candidate.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

    for owner_path in (root / "CODEOWNERS", root / ".github" / "CODEOWNERS"):
        if owner_path.is_file():
            try:
                manifests["CODEOWNERS"] = owner_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                pass

    return manifests


def load_repository_config(repo_root: str, url: str) -> dict[str, Any]:
    """Read the matching entry from ``data/repos.json``, if present."""
    config_path = Path(repo_root) / "data" / "repos.json"
    if not config_path.is_file():
        return {}

    try:
        manifest = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    for entry in manifest.get("repositories", []):
        if entry.get("url") == url:
            return entry
    return {}


def encode_filter_config(config: dict | None) -> str | None:
    """Base64-encode the subset of a repository entry the scanner needs.

    Only the filter keys are sent, so no unrelated manifest field ever reaches
    the sandbox.
    """
    if not config:
        return None
    subset = {
        "include_globs": config.get("include_globs") or [],
        "exclude_paths": config.get("exclude_paths") or [],
    }
    raw = json.dumps(subset, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def decode_filter_config(encoded: str | None) -> dict | None:
    """Inverse of :func:`encode_filter_config`."""
    if not encoded:
        return None
    try:
        raw = base64.b64decode(encoded.encode("ascii"), validate=True)
        decoded = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(decoded, dict):
        return None
    return {
        "include_globs": decoded.get("include_globs") or [],
        "exclude_paths": decoded.get("exclude_paths") or [],
    }


def scan_repository(repo_path: str, url: str, depth: int, config: dict | None = None) -> dict[str, Any]:
    """Produce the structured graph payload for a cloned repository."""
    raw_log = _run(
        [
            "git",
            "log",
            f"--pretty=format:{GIT_LOG_FORMAT}",
            "--name-only",
            f"-n{depth}",
        ],
        cwd=repo_path,
    )

    commits = parse_git_log(raw_log)
    if not commits:
        raise ScanError("git log produced no parseable commits")

    resolved_config = config if config is not None else load_repository_config(repo_path, url)
    file_filter = FileFilter.from_config(resolved_config)
    commits = file_filter.apply(commits)

    files = collect_unique_files(commits)
    manifests = read_manifests(repo_path)
    dependencies = collect_dependencies(
        {k: v for k, v in manifests.items() if k != "CODEOWNERS"}
    )

    commit_records = []
    for commit in commits:
        commit_records.append(
            {
                "sha": commit.sha,
                "short_sha": commit.short_sha,
                "author_name": commit.author_name,
                "author_email": commit.author_email,
                "authored_at": commit.authored_at,
                "subject": commit.subject,
                "parents": list(commit.parents),
                "is_merge": commit.is_merge,
                "pr_number": commit.pr_number,
                "files": list(commit.files),
            }
        )

    file_records = [
        {
            "path": path,
            "language": detect_language(path),
            "is_test": is_test_path(path),
            "module": module_path_for(path),
        }
        for path in files
    ]

    codeowners_paths = (
        collect_codeowners_paths(manifests["CODEOWNERS"]) if "CODEOWNERS" in manifests else []
    )

    return {
        "repository_url": url,
        "commit_depth": depth,
        "filters": {
            "include_globs": file_filter.include_globs,
            "exclude_paths": file_filter.exclude_paths,
        },
        "commits": commit_records,
        "files": file_records,
        "authors": [
            {"name": name, "email": email} for name, email in collect_authors(commits)
        ],
        "dependencies": [
            {
                "slug": dependency.slug,
                "repository_id": dependency.repository_id,
                "url": dependency.url,
                "kind": dependency.kind,
                "declared_in": dependency.declared_in,
            }
            for dependency in dependencies
        ],
        "codeowners_paths": codeowners_paths,
        "manifest_files": sorted(manifests.keys()),
    }


def main() -> int:
    """Sandbox entry point: clone, scan, and write the JSON payload."""
    url = os.environ.get("ORGATLAS_REPO_URL")
    depth = int(os.environ.get("ORGATLAS_COMMIT_DEPTH", "600"))
    output_dir = os.environ.get("ORGATLAS_OUTPUT_DIR", "/home/user/out")
    # The sandbox only ever holds a clone of the target repository, which does
    # not contain OrgAtlas' own data/repos.json. The host therefore injects the
    # matching filter config through this variable, base64 encoded so it
    # survives the shell without quoting problems.
    injected_config = decode_filter_config(os.environ.get("ORGATLAS_FILTER_CONFIG_B64"))

    if not url:
        print("ORGATLAS_REPO_URL is required", file=sys.stderr)
        return 2

    os.makedirs(output_dir, exist_ok=True)
    repo_path = clone_repository(url, output_dir, depth)
    config = injected_config if injected_config is not None else None
    payload = scan_repository(repo_path, url, depth, config=config)

    output_path = os.path.join(output_dir, OUTPUT_FILENAME)
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)

    print(
        f"scanned {len(payload['commits'])} commits, "
        f"{len(payload['files'])} files, "
        f"{len(payload['authors'])} authors, "
        f"{len(payload['dependencies'])} dependencies -> {output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())