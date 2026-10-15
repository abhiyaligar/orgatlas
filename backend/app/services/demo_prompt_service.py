from typing import List
from app.api.schemas import DemoPrompt

_DEMO_PROMPTS: List[DemoPrompt] = [
    DemoPrompt(
        id="prompt_kafka_decision",
        prompt="Why does Checkout use Kafka instead of synchronous calls?",
        intent="decision_trace",
        expected_entities=["svc_checkout", "dec_kafka_async", "tech_kafka", "inc_2024_03_black_friday"],
    ),
    DemoPrompt(
        id="prompt_token_ownership",
        prompt="Who owns Token Service and which services depend on it?",
        intent="ownership_and_impact",
        expected_entities=["svc_token_service", "team_payments", "person_marcus_vance", "svc_checkout"],
    ),
    DemoPrompt(
        id="prompt_payments_onboarding",
        prompt="What should a new Payments engineer learn in their first week?",
        intent="onboarding",
        expected_entities=["team_payments", "topic_pay_w1_01", "topic_pay_w1_02", "topic_pay_w1_03"],
    ),
    DemoPrompt(
        id="prompt_incident_decision_link",
        prompt="Which incident led to the Kafka decision, and where was it documented?",
        intent="decision_trace",
        expected_entities=["inc_2024_03_black_friday", "dec_kafka_async", "doc_rfp_kafka", "doc_postmortem_2024_03"],
    ),
    DemoPrompt(
        id="prompt_checkout_expertise",
        prompt="Who has relevant experience with the Checkout event pipeline?",
        intent="ownership",
        expected_entities=["svc_checkout", "person_sarah_chen", "person_alex_rivera"],
    ),
]


class DemoPromptService:
    """Provides the 5 stable seeded demo prompts with expected entity references."""

    def get_all_prompts(self) -> List[DemoPrompt]:
        return _DEMO_PROMPTS

    def get_prompt_by_id(self, prompt_id: str):
        return next((p for p in _DEMO_PROMPTS if p.id == prompt_id), None)
