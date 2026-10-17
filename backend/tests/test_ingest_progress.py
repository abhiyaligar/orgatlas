"""Ingest job progress reporting.

The background scan runs sandbox creation, clone, parsing, graph writes and the
description fallback inside one call. These tests pin the stage mapping that
turns those messages into the statuses the Repositories panel renders.
"""

from unittest.mock import MagicMock

from app.api.routes.repos import _progress_advance
from app.ingestion.seed_repo import _identity_count


def _report(stage: str, messages: list[str]) -> list[str]:
    job = MagicMock()
    session = MagicMock()
    report = _progress_advance(job, session, stage)

    statuses = []
    for message in messages:
        report(message)
        statuses.append(job.status)

    return statuses


def test_sandbox_and_clone_messages_report_cloning():
    statuses = _report(
        "parsing",
        ["creating sandbox from template", "starting clone", "clone finished"],
    )
    assert statuses == ["cloning", "cloning", "cloning"]


def test_scan_and_batch_messages_report_writing():
    statuses = _report(
        "parsing",
        ["scanned 329 files", "batch 6/13 MERGE (f:File)"],
    )
    assert statuses == ["writing", "writing"]


def test_model_fallback_message_reports_describing():
    statuses = _report("writing", ["model fallback for 4 of 329 files"])
    assert statuses == ["describing"]


def test_unmapped_message_keeps_the_current_status():
    job = MagicMock()
    session = MagicMock()
    report = _progress_advance(job, session, "writing")

    report("batch 1/13 MERGE")
    assert job.status == "writing"

    report("something the scanner did not describe")
    assert job.status == "writing", "an unmapped message must not invent a status"


def test_stage_detail_is_recorded_and_truncated():
    job = MagicMock()
    session = MagicMock()
    _progress_advance(job, session, "writing")("x" * 900)

    assert len(job.stage_detail) == 500


def test_each_reported_message_is_committed():
    job = MagicMock()
    session = MagicMock()
    report = _progress_advance(job, session, "writing")

    report("batch 1/13 MERGE")
    report("batch 2/13 MERGE")

    assert session.commit.call_count == 2


def test_identity_count_ignores_case_and_blanks():
    payload = {
        "authors": [
            {"name": "A", "email": "a@example.com"},
            {"name": "B", "email": "A@Example.com"},
            {"name": "C", "email": "c@example.com"},
            {"name": "D", "email": ""},
            {"name": "E"},
        ]
    }
    assert _identity_count(payload) == 2


def test_identity_count_handles_a_missing_authors_key():
    assert _identity_count({}) == 0