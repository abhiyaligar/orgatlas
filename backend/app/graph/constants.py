from enum import StrEnum


class NodeLabels(StrEnum):
    ORGANIZATION = "Organization"
    TEAM = "Team"
    PERSON = "Person"
    SERVICE = "Service"
    REPOSITORY = "Repository"
    DOCUMENT = "Document"
    DECISION = "Decision"
    INCIDENT = "Incident"
    PULL_REQUEST = "PullRequest"
    TICKET = "Ticket"
    TECHNOLOGY = "Technology"
    ONBOARDING_TOPIC = "OnboardingTopic"


class RelationshipTypes(StrEnum):
    HAS_TEAM = "HAS_TEAM"
    MEMBER_OF = "MEMBER_OF"
    OWNS = "OWNS"
    DEPENDS_ON = "DEPENDS_ON"
    USES = "USES"
    AFFECTS = "AFFECTS"
    DECIDED_BY = "DECIDED_BY"
    SUPPORTED_BY = "SUPPORTED_BY"
    DISCUSSED_IN = "DISCUSSED_IN"
    LED_TO = "LED_TO"
    IMPLEMENTS = "IMPLEMENTS"
    PRIMARY_IMPLEMENTATION_OF = "PRIMARY_IMPLEMENTATION_OF"
    CONTRIBUTED_TO = "CONTRIBUTED_TO"
    DOCUMENTS = "DOCUMENTS"
    RECOMMENDED_FOR = "RECOMMENDED_FOR"
    LEARN_ABOUT = "LEARN_ABOUT"
