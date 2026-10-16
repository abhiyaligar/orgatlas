"""Thin E2B sandbox client used to delegate heavy repository work.

Security boundary: this module passes the repository URL and commit depth into
the sandbox and nothing else. FalkorDB and Nebius credentials are never
forwarded, and the sandbox never writes to the graph — it returns a JSON
payload which the API process ingests.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from app.core.config import settings
from app.ingestion.repo_scanner import encode_filter_config, load_repository_config

logger = logging.getLogger(__name__)

SANDBOX_WORKDIR = "/home/user"
SANDBOX_APP_DIR = "/home/user/app"
SANDBOX_OUTPUT_DIR = PurePosixPath(SANDBOX_WORKDIR) / "out"
PAYLOAD_PATH = SANDBOX_OUTPUT_DIR / "graph.json"

SCAN_SCRIPT = "app.ingestion.repo_scanner"


class SandboxError(RuntimeError):
    """Raised when the sandbox cannot be created or does not produce a payload."""


class SandboxUnavailableError(SandboxError):
    """Raised when Track A environment configuration is missing."""


def _filter_config_for(repository_url: str) -> dict | None:
    """Read the host-side include/exclude filters for this repository.

    The sandbox only ever sees a clone of the target repository, so it has no
    access to OrgAtlas' own ``data/repos.json``. Without this the scanner would
    silently fall back to ingesting every path.
    """
    repo_root = Path(__file__).resolve().parents[3]
    return load_repository_config(str(repo_root), repository_url)


def sync_app_tree(sandbox, app_dir: Path | None = None) -> int:
    """Upload the current ``backend/app`` package into the sandbox.

    The template bakes in a snapshot of the application package, so without
    this the sandbox would run whatever scanner was current when the template
    was last built. That silently disables every later scanner change, which is
    how an ingest once ran with no include/exclude filters at all.

    Uploading the tree (a couple of hundred kilobytes) makes the sandbox's
    behaviour match the host exactly, so the template only has to supply the
    OS, git and Python.
    """
    # sandbox_client.py lives in backend/app/ingestion/, so parents[1] is
    # already the application package directory.
    if app_dir is None:
        app_dir = Path(__file__).resolve().parents[1]

    if not app_dir.is_dir() or app_dir.name != "app":
        raise SandboxError(f"application package not found at {app_dir}")

    uploaded = 0
    for path in sorted(app_dir.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        relative = path.relative_to(app_dir).as_posix()
        sandbox.files.write(f"{SANDBOX_APP_DIR}/{relative}", path.read_bytes())
        uploaded += 1

    # Never let a stale snapshot run quietly: an empty upload means the sandbox
    # would execute whatever the template was built with.
    if uploaded == 0:
        raise SandboxError(
            "refusing to scan: no application modules were synced into the sandbox"
        )

    # The baked snapshot may carry bytecode that shadows the uploaded source.
    sandbox.commands.run(
        f"find {SANDBOX_APP_DIR} -name '__pycache__' -type d -prune -exec rm -rf {{}} + ; "
        f"find {SANDBOX_APP_DIR} -name '*.pyc' -delete",
        timeout=60,
    )
    return uploaded


@dataclass(frozen=True)
class ScanRequest:
    """Everything the sandbox is allowed to know."""

    repository_url: str
    commit_depth: int


@dataclass(frozen=True)
class ScanResult:
    """What the sandbox handed back."""

    sandbox_id: str
    payload: dict[str, Any]


def _require_settings() -> tuple[str, int]:
    template = settings.E2B_INGEST_TEMPLATE
    timeout = settings.E2B_SANDBOX_TIMEOUT

    missing = [
        name
        for name, value in (
            ("E2B_API_KEY", settings.E2B_API_KEY),
            ("E2B_INGEST_TEMPLATE", template),
            ("E2B_SANDBOX_TIMEOUT", timeout),
        )
        if not value
    ]
    if missing:
        raise SandboxUnavailableError(
            f"Repository ingestion is not configured. Set {', '.join(missing)} in .env."
        )

    return str(template), int(timeout or 0)


def run_scan(request: ScanRequest, on_stage=None) -> ScanResult:
    """Clone and parse a repository inside an isolated sandbox.

    The sandbox is always killed in a ``finally`` block so billing stops even
    when the scan fails.
    """
    from e2b import Sandbox

    template, timeout = _require_settings()

    def stage(message: str) -> None:
        logger.info("[ingest] %s", message)
        if on_stage is not None:
            on_stage(message)

    stage(f"creating sandbox from template {template!r}")
    sandbox = Sandbox.create(
        template=template,
        timeout=timeout,
        allow_internet_access=True,
        api_key=settings.E2B_API_KEY,
        metadata={"orgatlas": "repo-ingest"},
    )

    try:
        sandbox_id = str(sandbox.sandbox_id)
        stage(f"sandbox {sandbox_id} ready; syncing scanner code")

        uploaded = sync_app_tree(sandbox)
        stage(f"synced {uploaded} application module(s) into the sandbox")

        filter_config = _filter_config_for(request.repository_url)
        encoded_filters = encode_filter_config(filter_config)
        stage(
            "filter config: "
            + (
                f"{len(filter_config.get('include_globs') or [])} include globs, "
                f"{len(filter_config.get('exclude_paths') or [])} exclude paths"
                if filter_config
                else "none configured for this repository (all paths ingested)"
            )
        )

        result = sandbox.commands.run(
            "cd /home/user && "
            f"ORGATLAS_REPO_URL={request.repository_url!r} "
            f"ORGATLAS_COMMIT_DEPTH={request.commit_depth} "
            f"ORGATLAS_OUTPUT_DIR={SANDBOX_OUTPUT_DIR} "
            f"ORGATLAS_FILTER_CONFIG_B64={encoded_filters or ''} "
            f"python -m {SCAN_SCRIPT}",
            cwd=SANDBOX_WORKDIR,
            timeout=timeout,
        )

        if result.exit_code != 0:
            stderr = (result.stderr or "").strip()
            raise SandboxError(f"scan failed inside sandbox: {stderr[:400]}")

        stage(f"downloading payload from {PAYLOAD_PATH}")
        raw = sandbox.files.read(str(PAYLOAD_PATH))
        payload = json.loads(raw)

        stage(
            f"payload received: {len(payload.get('commits', []))} commits, "
            f"{len(payload.get('files', []))} files"
        )
        return ScanResult(sandbox_id=sandbox_id, payload=payload)
    finally:
        try:
            sandbox.kill()
            stage("sandbox killed; billing stopped")
        except Exception as exc:  # pragma: no cover - best effort cleanup
            logger.warning("Failed to kill sandbox: %s", exc)