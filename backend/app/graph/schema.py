from typing import List
from app.graph.constants import NodeLabels


def get_graph_index_statements() -> List[str]:
    """Generates OpenCypher statements to create indices on primary entity identifiers and titles."""
    indexed_labels = [
        NodeLabels.ORGANIZATION,
        NodeLabels.TEAM,
        NodeLabels.PERSON,
        NodeLabels.SERVICE,
        NodeLabels.REPOSITORY,
        NodeLabels.DOCUMENT,
        NodeLabels.DECISION,
        NodeLabels.INCIDENT,
        NodeLabels.PULL_REQUEST,
        NodeLabels.TICKET,
        NodeLabels.TECHNOLOGY,
        NodeLabels.ONBOARDING_TOPIC,
    ]

    statements = []
    for label in indexed_labels:
        statements.append(f"CREATE INDEX FOR (n:{label}) ON (n.id)")
    return statements
