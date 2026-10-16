"""Repository scanning executed inside the E2B sandbox.

Everything in this module runs in the sandbox process. It performs git
operations and produces a JSON payload; it never touches the graph database
and never receives database or model-provider credentials.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from app.ingestion.dependency_scanner import collect_dependencies
from app.ingestion.git_history_parser import (
    GIT_LOG_FORMAT,
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


def scan_repository(repo_path: str, url: str, depth: int) -> dict[str, Any]:
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

    if not url:
        print("ORGATLAS_REPO_URL is required", file=sys.stderr)
        return 2

    os.makedirs(output_dir, exist_ok=True)
    repo_path = clone_repository(url, output_dir, depth)
    payload = scan_repository(repo_path, url, depth)

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