from contextlib import ExitStack
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.graph.gateway import graph_gateway
from app.main import app

client = TestClient(app)

ASK_RESPONSE_FIELDS = {"answer", "evidence_summary", "citations", "graph", "confidence", "suggested_questions"}
ONBOARDING_RESPONSE_FIELDS = {
    "team_id", "team_name", "mission", "topics", "owned_services", "people_to_meet", "reading_list", "graph"
}
CITATION_FIELDS = {"source_id", "title", "type"}
GRAPH_FIELDS = {"nodes", "edges", "paths"}


class FakeNode:
    """Minimal stand-in for a FalkorDB node record."""

    def __init__(self, properties, labels):
        self.properties = properties
        self.labels = labels


def service_node(service_id="svc_checkout", name="Checkout Service"):
    return FakeNode(
        {"id": service_id, "name": name, "description": f"{name} handles checkout", "criticality": "critical"},
        ["Service"],
    )


def team_node(team_id="team_payments", name="Payments Core", mission="Own the money path"):
    return FakeNode({"id": team_id, "name": name, "mission": mission}, ["Team"])


def person_node(person_id="person_sarah_chen", name="Sarah Chen", role="Staff Engineer"):
    return FakeNode({"id": person_id, "name": name, "role": role, "expertise": '["kafka"]'}, ["Person"])


def document_node(doc_id="doc_rfp_kafka", title="RFC-042", doc_type="design_doc"):
    return FakeNode({"id": doc_id, "title": title, "type": doc_type, "excerpt": f"{title} excerpt"}, ["Document"])


def incident_node(incident_id="inc_2024_03_black_friday", title="SEV-1 Checkout Outage"):
    return FakeNode({"id": incident_id, "title": title, "summary": "cascade failure"}, ["Incident"])


DECISION = FakeNode(
    {
        "id": "dec_kafka_async",
        "title": "Adopt Asynchronous Event Sourcing via Kafka",
        "summary": "Synchronous calls caused a cascade failure.",
        "alternatives": "Synchronous HTTP calls",
        "status": "Accepted",
        "decided_at": "2024-04-01T00:00:00",
    },
    ["Decision"],
)

DECISION_TRACE = {
    "decision": DECISION,
    "people": [person_node()],
    "teams": [],
    "services": [service_node()],
    "documents": [document_node(), document_node("doc_runbook_token_service", "Token Runbook", "runbook")],
    "incidents": [incident_node()],
    "pull_requests": [],
    "tickets": [],
}

CHANGE_IMPACT = {
    "target_service": service_node(),
    "owner_team": team_node(),
    "downstream_services": [service_node("svc_token_service", "Token Service")],
    "upstream_services": [],
    "incidents": [incident_node()],
    "decisions": [],
}

OWNERSHIP = {
    "service": service_node(),
    "team": team_node(),
    "team_members": [person_node()],
    "contributors": [person_node("person_alex_rivera", "Alex Rivera", "Principal Architect")],
    "repository": FakeNode({"id": "repo_checkout", "name": "acme/checkout", "url": "http://git/checkout"}, ["Repository"]),
    "documents": [],
}

ONBOARDING = {
    "team_id": "team_payments",
    "team_name": "Payments Core",
    "team_mission": "Own the money path",
    "topics": [
        FakeNode({"id": "topic_pay_w1_01", "title": "Foundations", "sequence": 2, "summary": "Domain"}, ["OnboardingTopic"]),
        FakeNode({"id": "topic_pay_w1_02", "title": "Kafka Pipeline", "sequence": 1, "summary": "Events"}, ["OnboardingTopic"]),
    ],
    "services": [service_node()],
    "people": [person_node(), person_node()],
    "documents": [document_node("doc_payments_onboarding_guide", "Onboarding Handbook", "guide")],
}

ENTITY_DETAIL = {
    "entity": service_node(),
    "outgoing": [
        {"rel": "DEPENDS_ON", "dir": "outgoing", "target": service_node("svc_token_service", "Token Service")},
        {"rel": "SUPPORTED_BY", "dir": "outgoing", "target": document_node("doc_runbook_token_service", "Token Runbook", "runbook")},
    ],
    "incoming": [
        {"rel": "AFFECTS", "dir": "incoming", "source": DECISION},
    ],
}


@pytest.fixture
def seeded_graph():
    """Bind every gateway retrieval method to a deterministic seeded result."""
    patches = {
        "get_decision_trace": DECISION_TRACE,
        "get_change_impact": CHANGE_IMPACT,
        "get_service_ownership": OWNERSHIP,
        "get_onboarding_context": ONBOARDING,
        "get_entity_detail": ENTITY_DETAIL,
    }
    with ExitStack() as stack:
        for method, result in patches.items():
            stack.enter_context(patch.object(graph_gateway, method, return_value=result))
        yield


@pytest.fixture
def empty_graph():
    """Simulate an empty knowledge graph."""
    with ExitStack() as stack:
        methods = (
            "get_decision_trace",
            "get_decision_evidence",
            "get_decision_documents",
            "get_decision_incidents",
            "get_decision_people",
            "get_decision_discussion",
            "get_decision_metrics",
            "get_decision_migration",
            "get_change_impact",
            "get_service_ownership",
            "get_onboarding_context",
            "get_entity_detail",
        )
        for method in methods:
            stack.enter_context(patch.object(graph_gateway, method, return_value=None))
        yield


def assert_citations_valid(citations):
    assert isinstance(citations, list)
    for citation in citations:
        assert CITATION_FIELDS.issubset(citation), citation
        assert citation["source_id"]
        assert citation["title"]


def assert_graph_valid(graph):
    assert GRAPH_FIELDS.issubset(graph), graph
    node_ids = {node["id"] for node in graph["nodes"]}
    for edge in graph["edges"]:
        assert edge["source"] in node_ids, "edge references a node missing from the payload"
        assert edge["target"] in node_ids, "edge references a node missing from the payload"


def test_health_returns_service_status():
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["service"] == "orgatlas-api"
    assert "environment" in body and "graph_connected" in body


def test_demo_prompts_returns_five_curated_questions():
    body = client.get("/api/demo-prompts").json()
    assert len(body) == 5
    for prompt in body:
        assert {"id", "prompt", "intent", "expected_entities"}.issubset(prompt)
        assert prompt["expected_entities"]


@pytest.mark.parametrize("prompt", [
    "Why does Checkout use Kafka instead of synchronous calls?",
    "Who owns Token Service and which services depend on it?",
    "What should a new Payments engineer learn in their first week?",
    "Which incident led to the Kafka decision, and where was it documented?",
    "Who has relevant experience with the Checkout event pipeline?",
])
def test_ask_answers_every_demo_prompt(seeded_graph, prompt):
    response = client.post("/api/ask", json={"question": prompt})
    assert response.status_code == 200
    body = response.json()

    assert ASK_RESPONSE_FIELDS.issubset(body), body
    assert body["answer"].strip()
    assert body["confidence"] in {"supported", "partial", "insufficient"}
    assert body["graph"]["nodes"], "a demo answer must expose graph evidence"
    assert_citations_valid(body["citations"])
    assert_graph_valid(body["graph"])


def test_ask_ownership_intent_is_reachable(seeded_graph):
    body = client.post("/api/ask", json={"question": "Who has relevant experience with the Checkout event pipeline?"}).json()
    assert "Checkout Service" in body["answer"]


def test_ask_never_claims_support_without_evidence(seeded_graph):
    body = client.post("/api/ask", json={"question": "Who has relevant experience with the Checkout event pipeline?"}).json()
    if not body["citations"]:
        assert body["confidence"] == "partial"


def test_ask_unrecognised_question_returns_insufficient_evidence(seeded_graph):
    body = client.post("/api/ask", json={"question": "What is the weather?"}).json()
    assert body["confidence"] == "insufficient"
    assert body["citations"] == []
    assert body["graph"]["nodes"] == []


def test_ask_unmatched_entity_does_not_fall_back_to_an_unrelated_decision(seeded_graph):
    body = client.post("/api/ask", json={"question": "Why do we use Cobol?"}).json()
    assert body["confidence"] == "insufficient"
    assert "Kafka" not in body["answer"]


def test_ask_rejects_an_empty_question():
    assert client.post("/api/ask", json={"question": "   "}).status_code == 400


def test_ask_degrades_to_insufficient_when_the_graph_is_empty(empty_graph):
    body = client.post("/api/ask", json={"question": "Why does Checkout use Kafka instead of synchronous calls?"}).json()
    assert body["confidence"] == "insufficient"
    assert body["citations"] == []


def test_onboarding_returns_the_documented_contract(seeded_graph):
    body = client.get("/api/onboarding/team_payments").json()
    assert ONBOARDING_RESPONSE_FIELDS.issubset(body), body
    assert body["team_id"] == "team_payments"
    assert [topic["sequence"] for topic in body["topics"]] == [1, 2]
    assert body["owned_services"] and body["people_to_meet"]
    assert len(body["people_to_meet"]) == 1, "duplicate people must be collapsed"
    assert_citations_valid(body["reading_list"])


def test_onboarding_returns_404_for_an_unknown_team(empty_graph):
    assert client.get("/api/onboarding/team_missing").status_code == 404


def test_decision_trace_returns_the_documented_contract(seeded_graph):
    body = client.get("/api/decisions/dec_kafka_async").json()
    assert {"decision_id", "title", "summary", "alternatives", "status", "decided_at", "citations", "graph"}.issubset(body)
    assert body["decision_id"] == "dec_kafka_async"
    assert body["alternatives"] == "Synchronous HTTP calls"
    assert_citations_valid(body["citations"])
    assert_graph_valid(body["graph"])
    assert body["graph"]["paths"]


def test_decision_trace_returns_404_when_absent(empty_graph):
    assert client.get("/api/decisions/dec_missing").status_code == 404


def test_entity_detail_returns_both_neighbour_directions(seeded_graph):
    body = client.get("/api/entity/svc_checkout").json()
    assert {"id", "label", "name", "properties", "neighbors", "citations"}.issubset(body)
    assert body["label"] == "Service"
    assert {neighbor["direction"] for neighbor in body["neighbors"]} == {"outgoing", "incoming"}
    assert_citations_valid(body["citations"])


def test_entity_detail_returns_404_when_absent(empty_graph):
    response = client.get("/api/entity/svc_missing")
    assert response.status_code == 404
    assert response.json()["error"]["type"] == "EntityNotFoundError"


def test_error_responses_never_expose_connection_details(empty_graph):
    detail = client.get("/api/entity/svc_missing").text
    for leak in ("password", "FALKORDB_", "localhost:6379", "Traceback"):
        assert leak not in detail