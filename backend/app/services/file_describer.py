"""Fill the documentation gap with a model, recording every detail.

The sandbox identifies which files their authors left undescribed and ships a
bounded excerpt for each. This module runs on the API side, calls the provider
for that gap set only, and writes back a full audit trail so it is always
possible to tell whether a summary was written by a human or generated, by
which model, from which revision, at what cost.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional

from app.core.config import settings
from app.graph.connection import graph_manager
from app.services.llm_client import (
    MAX_EXCERPT_CHARS,
    ModelDescription,
    ModelFailure,
    describe_file,
    llm_fallback_available,
)

logger = logging.getLogger(__name__)

TRIGGER = "missing_docs"
DOCS_SOURCE_MODEL = "model"

# Written per file. Only files with no authored description are touched.
UPSERT_MODEL_DESCRIPTION = """
UNWIND $rows AS row
MATCH (f:File {id: row.id})
SET f.summary = row.summary,
    f.symbols = row.symbols,
    f.docs_source = row.docs_source,
    f.docs_model = row.docs_model,
    f.docs_generated_at = row.docs_generated_at,
    f.docs_input_sha = row.docs_input_sha,
    f.docs_trigger = row.docs_trigger,
    f.docs_usage = row.docs_usage,
    f.docs_raw_response = row.docs_raw_response,
    f.docs_prompt_version = row.docs_prompt_version,
    f.docs_error = ''
RETURN count(f) AS updated
"""

BATCH = 100


def needs_model(record: Dict[str, Any]) -> bool:
    """True only for files with nothing usable written by their authors.

    Files described from authored module docs, item docs, public
    declarations or structured keys are left alone. Binary and oversized
    files are excluded so the fallback never sees a truncated or non-text
    source.
    """
    return record.get("docs_source") == "none" and bool(record.get("excerpt"))


def gap_records(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [record for record in payload.get("files", []) if needs_model(record)]


def estimate_calls(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Report what a fallback pass would cost before it is run."""
    gap = gap_records(payload)
    total_files = len(payload.get("files", []))
    approx_prompt_tokens = 0
    for record in gap:
        # ~4 characters per token is a reasonable planning estimate.
        approx_prompt_tokens += len(record.get("excerpt") or "") // 4
    return {
        "total_files": total_files,
        "gap_files": len(gap),
        "already_described": total_files - len(gap),
        "approx_prompt_tokens": approx_prompt_tokens,
        "approx_calls": len(gap),
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row(
    file_id: str,
    result: ModelDescription,
    docs_at_sha: str,
) -> Dict[str, Any]:
    return {
        "id": file_id,
        "summary": result.summary,
        "symbols": json.dumps(result.symbols),
        "docs_source": DOCS_SOURCE_MODEL,
        "docs_model": result.model,
        "docs_generated_at": _now_iso(),
        "docs_input_sha": docs_at_sha,
        "docs_trigger": TRIGGER,
        "docs_usage": json.dumps(result.usage or {}),
        "docs_raw_response": result.raw_response,
        "docs_prompt_version": result.prompt_version,
        "docs_error": "",
    }


def _error_row(file_id: str, result: ModelFailure, docs_at_sha: str) -> Dict[str, Any]:
    """Record why a file stayed undescribed without marking it described."""
    detail = f"{result.reason}: {result.detail}".strip()
    return {
        "id": file_id,
        "summary": "",
        "symbols": "[]",
        "docs_source": "none",
        "docs_model": "",
        "docs_generated_at": "",
        "docs_input_sha": docs_at_sha,
        "docs_trigger": TRIGGER,
        "docs_usage": "{}",
        "docs_raw_response": "",
        "docs_prompt_version": "",
        "docs_error": detail[:400],
    }


def _chunks(rows: List[Dict[str, Any]], size: int = BATCH) -> Iterable[List[Dict[str, Any]]]:
    for start in range(0, len(rows), size):
        yield rows[start:start + size]


def run_fallback(
    payload: Dict[str, Any],
    repository_id: str,
    *,
    dry_run: bool = False,
    describe: Callable[..., Any] = describe_file,
    on_stage: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Describe every gap file with the model and store the result.

    Never raises: a provider outage leaves files undescribed with a recorded
    reason, which is a better outcome than failing the ingestion.
    """

    def stage(message: str) -> None:
        logger.info("[describer] %s", message)
        if on_stage is not None:
            on_stage(message)

    estimate = estimate_calls(payload)
    if not llm_fallback_available(settings.NEBIUS_API_KEY):
        stage("no usable provider key; leaving the gap set undescribed")
        return {
            **estimate,
            "skipped": True,
            "reason": "no_provider_key",
            "described": 0,
            "failed": 0,
        }

    if estimate["approx_calls"] == 0:
        stage("every file carries authored documentation; nothing to do")
        return {
            **estimate,
            "skipped": False,
            "described": 0,
            "failed": 0,
        }

    stage(
        f"model fallback for {estimate['gap_files']} of {estimate['total_files']} files "
        f"using {settings.NEBIUS_MODEL_NAME}"
    )

    if dry_run:
        stage("dry run: no provider calls made and nothing written")
        return {**estimate, "skipped": False, "dry_run": True, "described": 0, "failed": 0}

    rows: List[Dict[str, Any]] = []
    described = 0
    failed = 0

    for index, record in enumerate(gap_records(payload), start=1):
        file_id = f"{repository_id}::{record['path']}"
        try:
            result = describe(
                record.get("excerpt") or "",
                record["path"],
                record.get("language") or "",
            )
        except Exception as exc:  # a fallback must never fail an ingestion
            logger.warning("describer raised for %s: %s", file_id, exc)
            result = ModelFailure(
                reason="describer_error",
                detail=f"{type(exc).__name__}: {exc}",
            )

        if isinstance(result, ModelDescription):
            rows.append(_row(file_id, result, record.get("docs_at_sha") or ""))
            described += 1
        else:
            rows.append(_error_row(file_id, result, record.get("docs_at_sha") or ""))
            failed += 1

        if index % 10 == 0 or index == estimate["gap_files"]:
            stage(f"described {described}/{estimate['gap_files']} (failed {failed})")

    graph = graph_manager.get_or_create_graph()
    updated = 0
    for chunk in _chunks(rows):
        result = graph.query(UPSERT_MODEL_DESCRIPTION, {"rows": chunk})
        for row in result.result_set:
            updated += row[0] if row else 0

    usage_totals: Dict[str, int] = {}
    for row in rows:
        if row["docs_usage"] == "{}":
            continue
        for key, value in json.loads(row["docs_usage"]).items():
            if isinstance(value, int):
                usage_totals[key] = usage_totals.get(key, 0) + value

    stage(f"wrote {updated} file description(s); {failed} left undescribed")
    return {
        **estimate,
        "skipped": False,
        "described": described,
        "failed": failed,
        "updated": updated,
        "usage": usage_totals,
        "max_excerpt_chars": MAX_EXCERPT_CHARS,
    }