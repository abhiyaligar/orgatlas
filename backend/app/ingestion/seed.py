import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from alembic import command
from alembic.config import Config

from app.core.config import settings
from app.graph.connection import graph_manager
from app.graph.schema import get_graph_index_statements

logger = logging.getLogger(__name__)


def run_alembic_migrations():
    """Ensure relational/metadata schema is migrated using Alembic before any data operations."""
    backend_dir = Path(__file__).resolve().parent.parent.parent
    alembic_ini_path = backend_dir / "alembic.ini"
    logger.info("Executing Alembic migrations from %s", alembic_ini_path)
    alembic_cfg = Config(str(alembic_ini_path))
    command.upgrade(alembic_cfg, "head")
    logger.info("Alembic migrations applied successfully.")


def load_fixtures(fixtures_dir: Path) -> Dict[str, Any]:
    fixtures = {}
    files = [
        "organization",
        "teams",
        "people",
        "technologies",
        "repositories",
        "services",
        "incidents",
        "decisions",
        "documents",
        "pull_requests",
        "tickets",
        "onboarding_topics",
    ]
    for name in files:
        file_path = fixtures_dir / f"{name}.json"
        if not file_path.exists():
            raise FileNotFoundError(f"Fixture file missing: {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            fixtures[name] = json.load(f)
    return fixtures


def cypher_literal(value: Any) -> str:
    """Render a Python value as a safely escaped OpenCypher literal.

    Fixture text routinely contains apostrophes and semicolons; without
    escaping them a value terminates its own string literal and the rest of
    the statement is parsed as a second query.
    """
    if value is None:
        return "''"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    escaped = str(value).replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def generate_seed_queries(fixtures: Dict[str, Any]) -> List[str]:
    """Generates idempotent OpenCypher queries using MERGE."""
    queries = []

    # 1. Organization
    org = fixtures["organization"]
    queries.append(
        f"MERGE (o:Organization {{id: {cypher_literal(org['id'])}}}) "
        f"SET o.name = {cypher_literal(org['name'])}, o.domain = {cypher_literal(org.get('domain'))}, "
        f"o.description = {cypher_literal(org.get('description'))}"
    )

    # 2. Teams & HAS_TEAM
    for team in fixtures["teams"]:
        queries.append(
            f"MERGE (t:Team {{id: {cypher_literal(team['id'])}}}) "
            f"SET t.name = {cypher_literal(team['name'])}, t.mission = {cypher_literal(team.get('mission'))}"
        )
        queries.append(
            f"MATCH (o:Organization {{id: {cypher_literal(team['organization_id'])}}}), "
            f"(t:Team {{id: {cypher_literal(team['id'])}}}) MERGE (o)-[:HAS_TEAM]->(t)"
        )

    # 3. People & MEMBER_OF
    for person in fixtures["people"]:
        queries.append(
            f"MERGE (p:Person {{id: {cypher_literal(person['id'])}}}) "
            f"SET p.name = {cypher_literal(person['name'])}, p.role = {cypher_literal(person.get('role'))}, "
            f"p.email = {cypher_literal(person.get('email'))}, "
            f"p.expertise = {cypher_literal(json.dumps(person.get('expertise', [])))}"
        )
        queries.append(
            f"MATCH (p:Person {{id: {cypher_literal(person['id'])}}}), "
            f"(t:Team {{id: {cypher_literal(person['team_id'])}}}) MERGE (p)-[:MEMBER_OF]->(t)"
        )

    # 4. Technologies
    for tech in fixtures["technologies"]:
        queries.append(
            f"MERGE (tech:Technology {{id: {cypher_literal(tech['id'])}}}) "
            f"SET tech.name = {cypher_literal(tech['name'])}, tech.category = {cypher_literal(tech.get('category'))}, "
            f"tech.description = {cypher_literal(tech.get('description'))}"
        )

    # 5. Repositories
    for repo in fixtures["repositories"]:
        queries.append(
            f"MERGE (r:Repository {{id: {cypher_literal(repo['id'])}}}) "
            f"SET r.name = {cypher_literal(repo['name'])}, r.url = {cypher_literal(repo.get('url'))}, "
            f"r.description = {cypher_literal(repo.get('description'))}"
        )

    # 6. Services, OWNS, USES, PRIMARY_IMPLEMENTATION_OF, DEPENDS_ON
    for svc in fixtures["services"]:
        queries.append(
            f"MERGE (s:Service {{id: {cypher_literal(svc['id'])}}}) "
            f"SET s.name = {cypher_literal(svc['name'])}, s.description = {cypher_literal(svc.get('description'))}, "
            f"s.criticality = {cypher_literal(svc.get('criticality'))}"
        )
        queries.append(
            f"MATCH (t:Team {{id: {cypher_literal(svc['owner_team_id'])}}}), "
            f"(s:Service {{id: {cypher_literal(svc['id'])}}}) MERGE (t)-[:OWNS]->(s)"
        )
        queries.append(
            f"MATCH (r:Repository {{id: {cypher_literal(svc['repository_id'])}}}), "
            f"(s:Service {{id: {cypher_literal(svc['id'])}}}) MERGE (r)-[:PRIMARY_IMPLEMENTATION_OF]->(s)"
        )
        for tech_id in svc.get("technology_ids", []):
            queries.append(
                f"MATCH (s:Service {{id: {cypher_literal(svc['id'])}}}), "
                f"(tech:Technology {{id: {cypher_literal(tech_id)}}}) MERGE (s)-[:USES]->(tech)"
            )
        for dep_id in svc.get("dependency_ids", []):
            queries.append(
                f"MATCH (s:Service {{id: {cypher_literal(svc['id'])}}}), "
                f"(dep:Service {{id: {cypher_literal(dep_id)}}}) MERGE (s)-[:DEPENDS_ON]->(dep)"
            )

    # 7. Incidents & AFFECTS
    for inc in fixtures["incidents"]:
        queries.append(
            f"MERGE (i:Incident {{id: {cypher_literal(inc['id'])}}}) "
            f"SET i.title = {cypher_literal(inc['title'])}, i.severity = {cypher_literal(inc.get('severity'))}, "
            f"i.summary = {cypher_literal(inc.get('summary'))}, i.occurred_at = {cypher_literal(inc.get('occurred_at'))}"
        )
        for aff_svc_id in inc.get("affected_service_ids", []):
            queries.append(
                f"MATCH (i:Incident {{id: {cypher_literal(inc['id'])}}}), "
                f"(s:Service {{id: {cypher_literal(aff_svc_id)}}}) MERGE (i)-[:AFFECTS]->(s)"
            )

    # 8. Decisions, DECIDED_BY, AFFECTS, LED_TO
    for dec in fixtures["decisions"]:
        queries.append(
            f"MERGE (d:Decision {{id: {cypher_literal(dec['id'])}}}) "
            f"SET d.title = {cypher_literal(dec['title'])}, d.status = {cypher_literal(dec.get('status'))}, "
            f"d.summary = {cypher_literal(dec.get('summary'))}, "
            f"d.alternatives = {cypher_literal(dec.get('alternatives'))}, "
            f"d.decided_at = {cypher_literal(dec.get('decided_at'))}"
        )
        for person_id in dec.get("decided_by_person_ids", []):
            queries.append(
                f"MATCH (d:Decision {{id: {cypher_literal(dec['id'])}}}), "
                f"(p:Person {{id: {cypher_literal(person_id)}}}) MERGE (d)-[:DECIDED_BY]->(p)"
            )
        for team_id in dec.get("decided_by_team_ids", []):
            queries.append(
                f"MATCH (d:Decision {{id: {cypher_literal(dec['id'])}}}), "
                f"(t:Team {{id: {cypher_literal(team_id)}}}) MERGE (d)-[:DECIDED_BY]->(t)"
            )
        for aff_svc in dec.get("affected_service_ids", []):
            queries.append(
                f"MATCH (d:Decision {{id: {cypher_literal(dec['id'])}}}), "
                f"(s:Service {{id: {cypher_literal(aff_svc)}}}) MERGE (d)-[:AFFECTS]->(s)"
            )

    # Link Incidents to Decisions (LED_TO)
    for inc in fixtures["incidents"]:
        if inc.get("led_to_decision_id"):
            queries.append(
                f"MATCH (i:Incident {{id: {cypher_literal(inc['id'])}}}), "
                f"(d:Decision {{id: {cypher_literal(inc['led_to_decision_id'])}}}) MERGE (i)-[:LED_TO]->(d)"
            )

    # 9. Documents, DOCUMENTS, SUPPORTED_BY
    for doc in fixtures["documents"]:
        queries.append(
            f"MERGE (doc:Document {{id: {cypher_literal(doc['id'])}}}) "
            f"SET doc.title = {cypher_literal(doc['title'])}, doc.type = {cypher_literal(doc.get('type'))}, "
            f"doc.url = {cypher_literal(doc.get('url'))}, doc.excerpt = {cypher_literal(doc.get('excerpt'))}, "
            f"doc.created_at = {cypher_literal(doc.get('created_at'))}"
        )
        if doc.get("author_id"):
            queries.append(
                f"MATCH (p:Person {{id: {cypher_literal(doc['author_id'])}}}), "
                f"(doc:Document {{id: {cypher_literal(doc['id'])}}}) MERGE (p)-[:AUTHORED]->(doc)"
            )
        for entity_id in doc.get("documents_entity_ids", []):
            queries.append(
                f"MATCH (doc:Document {{id: {cypher_literal(doc['id'])}}}), "
                f"(n {{id: {cypher_literal(entity_id)}}}) MERGE (doc)-[:DOCUMENTS]->(n)"
            )

    # Decision SUPPORTED_BY Documents
    for dec in fixtures["decisions"]:
        for doc_id in dec.get("supported_by_doc_ids", []):
            queries.append(
                f"MATCH (d:Decision {{id: {cypher_literal(dec['id'])}}}), "
                f"(doc:Document {{id: {cypher_literal(doc_id)}}}) MERGE (d)-[:SUPPORTED_BY]->(doc)"
            )

    # 10. Pull Requests & IMPLEMENTS
    for pr in fixtures["pull_requests"]:
        queries.append(
            f"MERGE (pr:PullRequest {{id: {cypher_literal(pr['id'])}}}) "
            f"SET pr.title = {cypher_literal(pr['title'])}, pr.url = {cypher_literal(pr.get('url'))}, "
            f"pr.merged_at = {cypher_literal(pr.get('merged_at'))}"
        )
        if pr.get("author_id"):
            queries.append(
                f"MATCH (p:Person {{id: {cypher_literal(pr['author_id'])}}}), "
                f"(pr:PullRequest {{id: {cypher_literal(pr['id'])}}}) MERGE (p)-[:AUTHORED]->(pr)"
            )
        if pr.get("repository_id"):
            queries.append(
                f"MATCH (pr:PullRequest {{id: {cypher_literal(pr['id'])}}}), "
                f"(r:Repository {{id: {cypher_literal(pr['repository_id'])}}}) MERGE (pr)-[:TARGETS_REPOSITORY]->(r)"
            )
        if pr.get("implements_decision_id"):
            queries.append(
                f"MATCH (pr:PullRequest {{id: {cypher_literal(pr['id'])}}}), "
                f"(d:Decision {{id: {cypher_literal(pr['implements_decision_id'])}}}) MERGE (pr)-[:IMPLEMENTS]->(d)"
            )

    # 11. Tickets & IMPLEMENTS
    for ticket in fixtures["tickets"]:
        queries.append(
            f"MERGE (tk:Ticket {{id: {cypher_literal(ticket['id'])}}}) "
            f"SET tk.title = {cypher_literal(ticket['title'])}, tk.status = {cypher_literal(ticket.get('status'))}, "
            f"tk.url = {cypher_literal(ticket.get('url'))}"
        )
        if ticket.get("implements_decision_id"):
            queries.append(
                f"MATCH (tk:Ticket {{id: {cypher_literal(ticket['id'])}}}), "
                f"(d:Decision {{id: {cypher_literal(ticket['implements_decision_id'])}}}) MERGE (tk)-[:IMPLEMENTS]->(d)"
            )

    # 12. Onboarding Topics & RECOMMENDED_FOR & LEARN_ABOUT
    for topic in fixtures["onboarding_topics"]:
        queries.append(
            f"MERGE (ot:OnboardingTopic {{id: {cypher_literal(topic['id'])}}}) "
            f"SET ot.title = {cypher_literal(topic['title'])}, ot.sequence = {cypher_literal(topic.get('sequence', 1))}, "
            f"ot.summary = {cypher_literal(topic.get('summary'))}, "
            f"ot.resources = {cypher_literal(json.dumps(topic.get('resources', [])))}"
        )
        queries.append(
            f"MATCH (ot:OnboardingTopic {{id: {cypher_literal(topic['id'])}}}), "
            f"(t:Team {{id: {cypher_literal(topic['team_id'])}}}) MERGE (ot)-[:RECOMMENDED_FOR]->(t)"
        )
        for entity_id in topic.get("learn_about_entity_ids", []):
            queries.append(
                f"MATCH (ot:OnboardingTopic {{id: {cypher_literal(topic['id'])}}}), "
                f"(n {{id: {cypher_literal(entity_id)}}}) MERGE (ot)-[:LEARN_ABOUT]->(n)"
            )

    # Add CONTRIBUTED_TO connections for demo persons
    for person_id, svc_id in (
        ("person_sarah_chen", "svc_checkout"),
        ("person_marcus_vance", "svc_token_service"),
        ("person_alex_rivera", "svc_checkout"),
    ):
        queries.append(
            f"MATCH (p:Person {{id: {cypher_literal(person_id)}}}), "
            f"(s:Service {{id: {cypher_literal(svc_id)}}}) MERGE (p)-[:CONTRIBUTED_TO]->(s)"
        )

    return queries


def seed_database(dry_run: bool = False) -> Dict[str, Any]:
    """Orchestrates Alembic migration and FalkorDB seed ingestion."""
    # 1. Run Alembic migrations first, unless this is a side-effect free dry run
    if not dry_run:
        run_alembic_migrations()

    # 2. Load fixtures
    fixtures_dir = Path(__file__).resolve().parent.parent.parent.parent / "data" / "fixtures"
    fixtures = load_fixtures(fixtures_dir)

    # 3. Generate Cypher queries
    queries = generate_seed_queries(fixtures)
    index_statements = get_graph_index_statements()

    if dry_run:
        logger.info("[DRY RUN] Generated %d seed queries and %d index statements.", len(queries), len(index_statements))
        return {
            "status": "dry_run",
            "fixtures_count": len(fixtures),
            "index_statements_count": len(index_statements),
            "seed_queries_count": len(queries),
        }

    # 4. Connect to FalkorDB and execute
    graph = graph_manager.get_graph()

    # Create indices
    for stmt in index_statements:
        try:
            graph.query(stmt)
        except Exception as e:
            logger.debug("Index creation notice: %s", str(e))

    # Execute seed queries
    for q in queries:
        graph.query(q)

    logger.info("FalkorDB graph '%s' seeded successfully with %d operations.", settings.FALKORDB_GRAPH_NAME, len(queries))
    return {
        "status": "seeded",
        "operations_count": len(queries),
    }
