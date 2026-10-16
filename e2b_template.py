"""Build the E2B sandbox template used for repository ingestion.

Run once with E2B_API_KEY set:

    python e2b_template.py

Deliberate choices:

* The template is built at 4096 MB. E2B's default sandbox is 1024 MB, which is
  not enough to clone the target repository.
* tree-sitter and its ten grammars are installed at build time, from the pinned
  list in ``tree_sitter_deps.py``. Everything else the scanner needs is Python's
  standard library, so the template still needs no database or model client.
  Grammar versions are pinned in one place and shared with
  ``backend/requirements.txt``, so the sandbox and the local venv cannot
  diverge.
* A grammar smoke test runs during the build. If any grammar fails to import or
  parse, the build fails instead of shipping a template that would silently
  extract no symbols.
* The application package is uploaded into each sandbox per run, so this
  template only has to supply the operating system, git and Python.
"""

from __future__ import annotations

import sys
from pathlib import Path

from tree_sitter_deps import SMOKE_TEST, TREE_SITTER_PACKAGES

REPO_ROOT = Path(__file__).resolve().parent
TEMPLATE_NAME = "orgatlas-ingest-ts"
CPU_COUNT = 2
MEMORY_MB = 4096
MIN_FREE_DISK_MB = 4096


def build() -> None:
    import os
    import sys

    from e2b import Template

    # E2B resolves copy sources relative to a context directory and rejects
    # absolute paths, so run from the repository root.
    os.chdir(REPO_ROOT)
    sys.path.insert(0, str(REPO_ROOT / "backend"))

    from app.core.config import settings

    api_key = settings.E2B_API_KEY
    if not api_key:
        print("E2B_API_KEY is not set. Add it to .env before building the template.", file=sys.stderr)
        raise SystemExit(1)

    builder = (
        Template(
            file_context_path=str(REPO_ROOT),
            file_ignore_patterns=[
                "**/__pycache__/**",
                "**/*.pyc",
                "**/venv/**",
                "**/node_modules/**",
                "**/dist/**",
                "**/.git/**",
            ],
        )
        .from_python_image("3.11")
        .apt_install(["git", "ca-certificates"])
        .pip_install(TREE_SITTER_PACKAGES)
        .set_workdir("/home/user")
        # Forward slashes are required: E2B does not normalise the native
        # Windows separator, and a backslash path collects zero files.
        .copy("backend/app", "/home/user/app")
        .run_cmd("git --version")
        # A template that cannot parse would silently produce no symbols, so
        # the build fails here instead.
        .run_cmd(
            "python - <<'PY'\n"
            + SMOKE_TEST
            + "PY"
        )
    )

    print(f"Building template {TEMPLATE_NAME!r} (cpu={CPU_COUNT}, memory={MEMORY_MB} MB)...")
    info = Template.build(
        builder,
        TEMPLATE_NAME,
        cpu_count=CPU_COUNT,
        memory_mb=MEMORY_MB,
        min_free_disk_mb=MIN_FREE_DISK_MB,
        api_key=api_key,
    )
    template_id = getattr(info, "template_id", None)
    print(f"Template built: {template_id or info}")
    print(f"Set E2B_INGEST_TEMPLATE={TEMPLATE_NAME} in your .env")


if __name__ == "__main__":
    try:
        build()
    except Exception as exc:  # pragma: no cover - CLI entry point
        print(f"Template build failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc