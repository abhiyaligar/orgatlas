from unittest.mock import MagicMock
from app.graph.gateway import GraphGateway


def test_graph_gateway_empty_results():
    mock_manager = MagicMock()
    mock_graph = MagicMock()
    mock_result = MagicMock()
    mock_result.result_set = []
    mock_graph.query.return_value = mock_result
    mock_manager.get_graph.return_value = mock_graph

    gateway = GraphGateway(manager=mock_manager)

    assert gateway.get_onboarding_context("team_payments") is None
    assert gateway.get_decision_trace("dec_kafka_async") is None
    assert gateway.get_change_impact("svc_checkout") is None
    assert gateway.get_service_ownership("svc_checkout") is None
    assert gateway.search_entities("kafka") == []


def test_graph_gateway_parses_search_rows():
    mock_manager = MagicMock()
    mock_graph = MagicMock()
    mock_result = MagicMock()
    mock_result.result_set = [
        ["svc_checkout", "Service", "Checkout Service", {"criticality": "critical"}]
    ]
    mock_graph.query.return_value = mock_result
    mock_manager.get_graph.return_value = mock_graph

    gateway = GraphGateway(manager=mock_manager)
    results = gateway.search_entities("checkout")

    assert len(results) == 1
    assert results[0]["id"] == "svc_checkout"
    assert results[0]["label"] == "Service"
    assert results[0]["name"] == "Checkout Service"
