"""Shared test configuration.

Answer synthesis is disabled for the whole suite so no test depends on the
model provider being reachable, deterministic, or free. The synthesis paths
themselves are covered in test_answer_synthesis.py with a stubbed provider,
and a live check is available through the opt-in evaluation suite.
"""

from contextlib import ExitStack
from unittest.mock import patch

import pytest

from app.core.config import settings


# The nodes the demo questions talk about. A test that patches retrieval still
# needs term resolution to succeed first: /ask resolves the question against the
# graph before it decides which retrieval to run, and it returns "insufficient
# evidence" when nothing resolves. Those tests therefore passed or failed
# depending on whether a real graph happened to be loaded, which made a fresh
# database look like a regression.
DEMO_TERM_ENTITIES = {
    "checkout": ("svc_checkout", "Service", "Checkout Service"),
    "kafka": ("tech_kafka", "Technology", "Kafka"),
    "token": ("svc_token_service", "Service", "Token Service"),
    "service": ("svc_checkout", "Service", "Checkout Service"),
    "payments": ("team_payments", "Team", "Payments"),
    "team": ("team_payments", "Team", "Payments"),
    "engineer": ("person_dana", "Person", "Dana"),
    "oncall": ("person_dana", "Person", "Dana"),
    "incident": ("inc_2024_03", "Incident", "Kafka brownout"),
    "brownout": ("inc_2024_03", "Incident", "Kafka brownout"),
    "pipeline": ("svc_checkout", "Service", "Checkout Service"),
    "event": ("svc_checkout", "Service", "Checkout Service"),
    "doc": ("doc_adr_kafka", "Document", "ADR: Kafka for Checkout"),
    "adr": ("doc_adr_kafka", "Document", "ADR: Kafka for Checkout"),
    "rfp": ("doc_rfp_kafka", "Document", "Kafka RFP"),
    "postmortem": ("doc_postmortem_2024_03", "Document", "March 2024 postmortem"),
    "redis": ("tech_redis", "Technology", "Redis"),
    "kubernetes": ("tech_kubernetes", "Technology", "Kubernetes"),
    "repo": ("repo_checkout", "Repository", "checkout-service"),
}


@pytest.fixture
def seeded_term_resolution():
    """Answer term resolution from a fixed map instead of the live graph."""

    def _search(terms):
        rows = []
        for term in terms or []:
            found = DEMO_TERM_ENTITIES.get(str(term).strip().lower())
            if not found:
                continue
            entity_id, label, name = found
            rows.append(
                {"term": term, "id": entity_id, "label": label, "name": name, "quality": 3}
            )
        return rows

    from app.graph.gateway import graph_gateway

    with ExitStack() as stack:
        stack.enter_context(
            patch.object(graph_gateway, "search_entities_by_terms", side_effect=_search)
        )
        yield


@pytest.fixture(autouse=True)
def disable_synthesis():
    """Keep every test offline and cost-free."""
    previous = settings.ASK_SYNTHESIS_ENABLED
    settings.ASK_SYNTHESIS_ENABLED = False
    yield
    settings.ASK_SYNTHESIS_ENABLED = previous
