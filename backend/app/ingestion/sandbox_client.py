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
from pathlib import PurePosixPath
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

SANDBOX_WORKDIR = "/home/user"
SANDBOX_OUTPUT_DIR = PurePosixPath(SANDBOX_WORKDIR) / "out"
PAYLOAD_PATH = SANDBOX_OUTPUT_DIR / "graph.json"

SCAN_SCRIPT = "app.ingestion.repo_scanner"


class SandboxError(RuntimeError):
    """Raised when the sandbox cannot be created or does not produce a payload."""


class SandboxUnavailableError(SandboxError):
    """Raised when Track A environment configuration is missing."""


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
        stage(f"sandbox {sandbox_id} ready; starting clone")

        result = sandbox.commands.run(
            "cd /home/user && "
            f"ORGATLAS_REPO_URL={request.repository_url!r} "
            f"ORGATLAS_COMMIT_DEPTH={request.commit_depth} "
            f"ORGATLAS_OUTPUT_DIR={SANDBOX_OUTPUT_DIR} "
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