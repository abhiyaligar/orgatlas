import logging
from typing import Dict, Any
from app.graph.connection import graph_manager

logger = logging.getLogger(__name__)


def verify_demo_graph() -> Dict[str, Any]:
    """Verifies that the 5 essential demo graph paths exist and are queryable."""
    graph = graph_manager.get_graph()
    results = {}

    # Verification 1: Payments Onboarding Path
    q1 = """
    MATCH (t:Team {id: 'team_payments'})-[:OWNS]->(s:Service),
          (ot:OnboardingTopic)-[:RECOMMENDED_FOR]->(t)
    RETURN t.name AS team, collect(DISTINCT s.name) AS services, collect(DISTINCT ot.title) AS topics
    """
    res1 = graph.query(q1).result_set
    results["payments_onboarding"] = len(res1) > 0 and len(res1[0][1]) > 0

    # Verification 2: Kafka Decision Trace
    q2 = """
    MATCH (s:Service {id: 'svc_checkout'})<-[:AFFECTS]-(d:Decision {id: 'dec_kafka_async'}),
          (d)-[:SUPPORTED_BY]->(doc:Document),
          (i:Incident)-[:LED_TO]->(d)
    RETURN d.title AS decision, doc.title AS document, i.title AS incident
    """
    res2 = graph.query(q2).result_set
    results["kafka_decision_trace"] = len(res2) > 0

    # Verification 3: Token Service Ownership
    q3 = """
    MATCH (t:Team)-[:OWNS]->(s:Service {id: 'svc_token_service'}),
          (p:Person)-[:MEMBER_OF]->(t)
    RETURN t.name AS team, collect(p.name) AS members
    """
    res3 = graph.query(q3).result_set
    results["token_service_ownership"] = len(res3) > 0

    # Verification 4: Token Service Dependency Impact
    q4 = """
    MATCH (s:Service {id: 'svc_checkout'})-[:DEPENDS_ON]->(dep:Service {id: 'svc_token_service'})
    RETURN s.name, dep.name
    """
    res4 = graph.query(q4).result_set
    results["token_service_dependency"] = len(res4) > 0

    # Verification 5: Checkout Contributor/Expertise
    q5 = """
    MATCH (p:Person)-[:CONTRIBUTED_TO]->(s:Service {id: 'svc_checkout'})
    RETURN collect(p.name) AS contributors
    """
    res5 = graph.query(q5).result_set
    results["checkout_contributors"] = len(res5) > 0 and len(res5[0][0]) > 0

    all_passed = all(results.values())
    return {
        "verified": all_passed,
        "checks": results,
    }
