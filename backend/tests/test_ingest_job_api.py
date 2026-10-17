"""The ingest job endpoints must survive a real database round trip.

These exist because ``POST /repos/ingest`` had no coverage at all. Its serializer
passed a ``datetime`` column straight into a field declared ``str``, which raised
a 500 only once the rows came back from Postgres. A test that builds the
response object by hand never sees that, so the endpoints are exercised through
HTTP against the real store instead.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    """A client whose ingest endpoint records the job but never scans.

    ``POST /repos/ingest`` queues a background task, and Starlette runs those
    before the response is released. Unpatched, every test here would launch a
    real E2B sandbox against a real repository.
    """
    from app.api.routes import repos

    original = repos._run_ingest
    repos._run_ingest = lambda *args, **kwargs: None
    try:
        from app.main import create_app

        yield TestClient(create_app(), raise_server_exceptions=False)
    finally:
        repos._run_ingest = original


def _ingest(client, url="https://github.com/example/repo"):
    return client.post("/api/repos/ingest", json={"repository_url": url})


def test_a_queued_job_is_accepted_and_returns_an_iso_created_at(client):
    response = _ingest(client)

    # 202, not 200: the work is queued and returns immediately.
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "queued"
    assert body["commits_ingested"] == 0


def test_created_at_is_a_string_not_a_datetime(client):
    """The failure mode: a datetime column cannot satisfy a ``str`` field."""
    created_at = _ingest(client).json()["created_at"]

    assert isinstance(created_at, str), f"expected a string, got {type(created_at).__name__}"
    # Round-tripping proves it is a real timestamp, not just any string.
    from datetime import datetime

    assert datetime.fromisoformat(created_at).year >= 2024


def test_polling_a_job_returns_the_same_timestamp_shape(client):
    job_id = _ingest(client).json()["id"]

    polled = client.get(f"/api/repos/ingest/{job_id}")

    assert polled.status_code == 200, polled.text
    body = polled.json()
    assert body["id"] == job_id
    assert isinstance(body["created_at"], str)
    # Nothing has run yet, so completion is still open.
    assert body["completed_at"] is None


def test_a_completed_job_reports_an_iso_completion(client):
    from datetime import datetime, timezone

    from app.core.dependencies import SessionLocal
    from app.db.models import IngestJob

    job_id = _ingest(client).json()["id"]
    session = SessionLocal()
    try:
        job = session.get(IngestJob, job_id)
        job.status = "done"
        job.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        session.commit()
    finally:
        session.close()

    completed_at = client.get(f"/api/repos/ingest/{job_id}").json()["completed_at"]

    assert isinstance(completed_at, str)
    assert datetime.fromisoformat(completed_at) is not None


def test_a_job_id_that_does_not_exist_is_a_404(client):
    assert client.get("/api/repos/ingest/99999999").status_code == 404


def test_a_non_http_repository_url_is_refused(client):
    assert _ingest(client, "ftp://example.com/repo").status_code == 400