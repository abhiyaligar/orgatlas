from unittest.mock import MagicMock
from app.services.onboarding_service import OnboardingContextService
from app.services.decision_service import DecisionTraceService
from app.services.impact_service import ChangeImpactService
from app.services.ownership_service import OwnershipService
from app.services.demo_prompt_service import DemoPromptService


def _make_mock_gateway(return_value):
    gateway = MagicMock()
    gateway.get_onboarding_context.return_value = return_value
    gateway.get_decision_trace.return_value = return_value
    gateway.get_change_impact.return_value = return_value
    gateway.get_service_ownership.return_value = return_value
    return gateway


def test_onboarding_service_returns_none_when_no_data():
    gateway = _make_mock_gateway(None)
    service = OnboardingContextService(gateway=gateway)
    result = service.get_onboarding_map("team_payments")
    assert result is None


def test_decision_service_returns_none_when_no_data():
    gateway = _make_mock_gateway(None)
    service = DecisionTraceService(gateway=gateway)
    result = service.trace_decision("dec_kafka_async")
    assert result is None


def test_impact_service_returns_none_when_no_data():
    gateway = _make_mock_gateway(None)
    service = ChangeImpactService(gateway=gateway)
    result = service.assess_impact("svc_checkout")
    assert result is None


def test_ownership_service_returns_none_when_no_data():
    gateway = _make_mock_gateway(None)
    service = OwnershipService(gateway=gateway)
    result = service.get_ownership("svc_token_service")
    assert result is None


def test_demo_prompt_service_returns_five_prompts():
    service = DemoPromptService()
    prompts = service.get_all_prompts()
    assert len(prompts) == 5
    assert all(p.id and p.prompt and p.intent for p in prompts)


def test_demo_prompt_service_get_by_id():
    service = DemoPromptService()
    prompt = service.get_prompt_by_id("prompt_kafka_decision")
    assert prompt is not None
    assert "Kafka" in prompt.prompt
    assert "dec_kafka_async" in prompt.expected_entities
