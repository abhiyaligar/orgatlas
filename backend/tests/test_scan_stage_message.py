"""The scan stage must be able to announce what it found.

``ingest_repository`` emits a progress line that mixes two different sources:
the counts priced by ``estimate_calls`` and the declaration total the scanner
puts on the payload. Those live in different places, and reading the wrong one
raised a ``KeyError`` that aborted every real ingestion after the sandbox had
already finished its expensive work.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.ingestion import seed_repo
from app.services.file_describer import estimate_calls


def _run(monkeypatch, payload):
    """Drive ingest_repository over a stubbed scan and capture its stage messages."""
    monkeypatch.setattr(
        seed_repo,
        "run_scan",
        lambda request, on_stage=None: SimpleNamespace(payload=payload, sandbox_id="sbx-1"),
    )
    monkeypatch.setattr(seed_repo, "cache_payload", lambda *a, **kw: None)
    monkeypatch.setattr(
        seed_repo, "write_payload", lambda *a, **kw: {"files": 0, "commits": 0, "symbols": 0}
    )

    # ingest_repository imports these by name when it is called, so patching the
    # module attribute is what actually takes effect.
    from app.services import file_describer

    monkeypatch.setattr(file_describer, "run_fallback", lambda *a, **kw: {"described": 0})

    messages: list[str] = []
    seed_repo.ingest_repository(
        "https://github.com/example/repo",
        on_stage=messages.append,
        run_model_fallback=False,
    )
    return messages


@pytest.fixture()
def payload():
    return {
        "declaration_count": 42,
        "files": [
            {"path": "src/lib.rs", "excerpt": "/// doc", "docs_source": "authored"},
            {"path": "src/main.rs", "excerpt": "", "docs_source": None},
        ],
    }


def test_the_scan_line_reports_the_declarations_the_scanner_found(monkeypatch, payload):
    messages = _run(monkeypatch, payload)

    line = next(m for m in messages if "declarations extracted" in m)
    assert "42 declarations extracted" in line


def test_the_scan_line_also_reports_the_fallback_estimate(monkeypatch, payload):
    messages = _run(monkeypatch, payload)

    line = next(m for m in messages if "declarations extracted" in m)
    assert "scanned 2 files" in line
    assert "1 documented by their authors" in line


def test_a_payload_without_a_declaration_total_still_announces(monkeypatch, payload):
    """An older or partial payload must not abort an expensive scan."""
    payload.pop("declaration_count")

    messages = _run(monkeypatch, payload)

    assert any("0 declarations extracted" in m for m in messages)


def test_a_null_declaration_total_does_not_crash(monkeypatch, payload):
    payload["declaration_count"] = None

    messages = _run(monkeypatch, payload)

    assert any("0 declarations extracted" in m for m in messages)


def test_estimate_calls_does_not_claim_to_price_declarations():
    """Pin the contract: the declaration count is the payload's, not the estimate's."""
    keys = estimate_calls({"files": []})

    assert "declaration_count" not in keys
    assert {"total_files", "gap_files", "already_described"} <= set(keys)