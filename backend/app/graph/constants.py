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
    # Ingested from code and from Slack.
    FILE = "File"
    COMMIT = "Commit"
    CODE_SYMBOL = "CodeSymbol"
    MODULE = "Module"
    PATH = "Path"
    EXTERNAL_IDENTITY = "ExternalIdentity"
    # Ingested documents, discussion, and the numbers a document states.
    SLACK_MESSAGE = "SlackMessage"
    METRIC = "Metric"


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
    # Document and discussion edges.
    MODIFIES = "MODIFIES"
    AUTHORED = "AUTHORED"
    DECLARES = "DECLARES"
    DEPENDS_ON_REPO = "DEPENDS_ON_REPO"
    CODEOWNERS_PATH = "CODEOWNERS_PATH"
    CONTEXT = "CONTEXT"
    # Who argued for a decision, and what evidence backs it.
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    OBJECTED = "OBJECTED"
    DISCUSSED = "DISCUSSED"
    QUOTED = "QUOTED"
    STATES_METRIC = "STATES_METRIC"
    # What shipped a decision, and what a message was about.
    IMPLEMENTED_IN = "IMPLEMENTED_IN"
    MIGRATED_FROM = "MIGRATED_FROM"
    MIGRATED_TO = "MIGRATED_TO"
    ABOUT = "ABOUT"
