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


def generate_seed_queries(fixtures: Dict[str, Any]) -> List[str]:
    """Generates idempotent OpenCypher queries using MERGE."""
    queries = []

    # 1. Organization
    org = fixtures["organization"]
    queries.append(
        f"MERGE (o:Organization {{id: '{org['id']}'}}) "
        f"SET o.name = '{org['name']}', o.domain = '{org.get('domain', '')}', o.description = '{org.get('description', '')}'"
    )

    # 2. Teams & HAS_TEAM
    for team in fixtures["teams"]:
        queries.append(
            f"MERGE (t:Team {{id: '{team['id']}'}}) "
            f"SET t.name = '{team['name']}', t.mission = '{team.get('mission', '')}'"
        )
        queries.append(
            f"MATCH (o:Organization {{id: '{team['organization_id']}'}}), (t:Team {{id: '{team['id']}'}}) "
            f"MERGE (o)-[:HAS_TEAM]->(t)"
        )

    # 3. People & MEMBER_OF
    for person in fixtures["people"]:
        expertise_str = json.dumps(person.get("expertise", []))
        queries.append(
            f"MERGE (p:Person {{id: '{person['id']}'}}) "
            f"SET p.name = '{person['name']}', p.role = '{person.get('role', '')}', "
            f"p.email = '{person.get('email', '')}', p.expertise = '{expertise_str}'"
        )
        queries.append(
            f"MATCH (p:Person {{id: '{person['id']}'}}), (t:Team {{id: '{person['team_id']}'}}) "
            f"MERGE (p)-[:MEMBER_OF]->(t)"
        )

    # 4. Technologies
    for tech in fixtures["technologies"]:
        queries.append(
            f"MERGE (tech:Technology {{id: '{tech['id']}'}}) "
            f"SET tech.name = '{tech['name']}', tech.category = '{tech.get('category', '')}', tech.description = '{tech.get('description', '')}'"
        )

    # 5. Repositories
    for repo in fixtures["repositories"]:
        queries.append(
            f"MERGE (r:Repository {{id: '{repo['id']}'}}) "
            f"SET r.name = '{repo['name']}', r.url = '{repo.get('url', '')}', r.description = '{repo.get('description', '')}'"
        )

    # 6. Services, OWNS, USES, PRIMARY_IMPLEMENTATION_OF, DEPENDS_ON
    for svc in fixtures["services"]:
        queries.append(
            f"MERGE (s:Service {{id: '{svc['id']}'}}) "
            f"SET s.name = '{svc['name']}', s.description = '{svc.get('description', '')}', s.criticality = '{svc.get('criticality', '')}'"
        )
        # OWNS
        queries.append(
            f"MATCH (t:Team {{id: '{svc['owner_team_id']}'}}), (s:Service {{id: '{svc['id']}'}}) "
            f"MERGE (t)-[:OWNS]->(s)"
        )
        # PRIMARY_IMPLEMENTATION_OF
        queries.append(
            f"MATCH (r:Repository {{id: '{svc['repository_id']}'}}), (s:Service {{id: '{svc['id']}'}}) "
            f"MERGE (r)-[:PRIMARY_IMPLEMENTATION_OF]->(s)"
        )
        # USES technology
        for tech_id in svc.get("technology_ids", []):
            queries.append(
                f"MATCH (s:Service {{id: '{svc['id']}'}}), (tech:Technology {{id: '{tech_id}'}}) "
                f"MERGE (s)-[:USES]->(tech)"
            )
        # DEPENDS_ON services
        for dep_id in svc.get("dependency_ids", []):
            queries.append(
                f"MATCH (s:Service {{id: '{svc['id']}'}}), (dep:Service {{id: '{dep_id}'}}) "
                f"MERGE (s)-[:DEPENDS_ON]->(dep)"
            )

    # 7. Incidents & AFFECTS
    for inc in fixtures["incidents"]:
        queries.append(
            f"MERGE (i:Incident {{id: '{inc['id']}'}}) "
            f"SET i.title = '{inc['title']}', i.severity = '{inc.get('severity', '')}', "
            f"i.summary = '{inc.get('summary', '')}', i.occurred_at = '{inc.get('occurred_at', '')}'"
        )
        for aff_svc_id in inc.get("affected_service_ids", []):
            queries.append(
                f"MATCH (i:Incident {{id: '{inc['id']}'}}), (s:Service {{id: '{aff_svc_id}'}}) "
                f"MERGE (i)-[:AFFECTS]->(s)"
            )

    # 8. Decisions, DECIDED_BY, AFFECTS, LED_TO
    for dec in fixtures["decisions"]:
        queries.append(
            f"MERGE (d:Decision {{id: '{dec['id']}'}}) "
            f"SET d.title = '{dec['title']}', d.status = '{dec.get('status', '')}', "
            f"d.summary = '{dec.get('summary', '')}', d.alternatives = '{dec.get('alternatives', '')}', "
            f"d.decided_at = '{dec.get('decided_at', '')}'"
        )
        for person_id in dec.get("decided_by_person_ids", []):
            queries.append(
                f"MATCH (d:Decision {{id: '{dec['id']}'}}), (p:Person {{id: '{person_id}'}}) "
                f"MERGE (d)-[:DECIDED_BY]->(p)"
            )
        for team_id in dec.get("decided_by_team_ids", []):
            queries.append(
                f"MATCH (d:Decision {{id: '{dec['id']}'}}), (t:Team {{id: '{team_id}'}}) "
                f"MERGE (d)-[:DECIDED_BY]->(t)"
            )
        for aff_svc in dec.get("affected_service_ids", []):
            queries.append(
                f"MATCH (d:Decision {{id: '{dec['id']}'}}), (s:Service {{id: '{aff_svc}'}}) "
                f"MERGE (d)-[:AFFECTS]->(s)"
            )

    # Link Incidents to Decisions (LED_TO)
    for inc in fixtures["incidents"]:
        if inc.get("led_to_decision_id"):
            queries.append(
                f"MATCH (i:Incident {{id: '{inc['id']}'}}), (d:Decision {{id: '{inc['led_to_decision_id']}'}}) "
                f"MERGE (i)-[:LED_TO]->(d)"
            )

    # 9. Documents, DOCUMENTS, SUPPORTED_BY
    for doc in fixtures["documents"]:
        queries.append(
            f"MERGE (doc:Document {{id: '{doc['id']}'}}) "
            f"SET doc.title = '{doc['title']}', doc.type = '{doc.get('type', '')}', "
            f"doc.url = '{doc.get('url', '')}', doc.excerpt = '{doc.get('excerpt', '')}', "
            f"doc.created_at = '{doc.get('created_at', '')}'"
        )
        if doc.get("author_id"):
            queries.append(
                f"MATCH (p:Person {{id: '{doc['author_id']}'}}), (doc:Document {{id: '{doc['id']}'}}) "
                f"MERGE (p)-[:AUTHORED]->(doc)"
            )
        for entity_id in doc.get("documents_entity_ids", []):
            queries.append(
                f"MATCH (doc:Document {{id: '{doc['id']}'}}), (n {{id: '{entity_id}'}}) "
                f"MERGE (doc)-[:DOCUMENTS]->(n)"
            )

    # Decision SUPPORTED_BY Documents
    for dec in fixtures["decisions"]:
        for doc_id in dec.get("supported_by_doc_ids", []):
            queries.append(
                f"MATCH (d:Decision {{id: '{dec['id']}'}}), (doc:Document {{id: '{doc_id}'}}) "
                f"MERGE (d)-[:SUPPORTED_BY]->(doc)"
            )

    # 10. Pull Requests & IMPLEMENTS
    for pr in fixtures["pull_requests"]:
        queries.append(
            f"MERGE (pr:PullRequest {{id: '{pr['id']}'}}) "
            f"SET pr.title = '{pr['title']}', pr.url = '{pr.get('url', '')}', pr.merged_at = '{pr.get('merged_at', '')}'"
        )
        if pr.get("author_id"):
            queries.append(
                f"MATCH (p:Person {{id: '{pr['author_id']}'}}), (pr:PullRequest {{id: '{pr['id']}'}}) "
                f"MERGE (p)-[:AUTHORED]->(pr)"
            )
        if pr.get("repository_id"):
            queries.append(
                f"MATCH (pr:PullRequest {{id: '{pr['id']}'}}), (r:Repository {{id: '{pr['repository_id']}'}}) "
                f"MERGE (pr)-[:TARGETS_REPOSITORY]->(r)"
            )
        if pr.get("implements_decision_id"):
            queries.append(
                f"MATCH (pr:PullRequest {{id: '{pr['id']}'}}), (d:Decision {{id: '{pr['implements_decision_id']}'}}) "
                f"MERGE (pr)-[:IMPLEMENTS]->(d)"
            )

    # 11. Tickets & IMPLEMENTS
    for ticket in fixtures["tickets"]:
        queries.append(
            f"MERGE (tk:Ticket {{id: '{ticket['id']}'}}) "
            f"SET tk.title = '{ticket['title']}', tk.status = '{ticket.get('status', '')}', tk.url = '{ticket.get('url', '')}'"
        )
        if ticket.get("implements_decision_id"):
            queries.append(
                f"MATCH (tk:Ticket {{id: '{ticket['id']}'}}), (d:Decision {{id: '{ticket['implements_decision_id']}'}}) "
                f"MERGE (tk)-[:IMPLEMENTS]->(d)"
            )

    # 12. Onboarding Topics & RECOMMENDED_FOR & LEARN_ABOUT
    for topic in fixtures["onboarding_topics"]:
        resources_str = json.dumps(topic.get("resources", []))
        queries.append(
            f"MERGE (ot:OnboardingTopic {{id: '{topic['id']}'}}) "
            f"SET ot.title = '{topic['title']}', ot.sequence = {topic.get('sequence', 1)}, "
            f"ot.summary = '{topic.get('summary', '')}', ot.resources = '{resources_str}'"
        )
        queries.append(
            f"MATCH (ot:OnboardingTopic {{id: '{topic['id']}'}}), (t:Team {{id: '{topic['team_id']}'}}) "
            f"MERGE (ot)-[:RECOMMENDED_FOR]->(t)"
        )
        for entity_id in topic.get("learn_about_entity_ids", []):
            queries.append(
                f"MATCH (ot:OnboardingTopic {{id: '{topic['id']}'}}), (n {{id: '{entity_id}'}}) "
                f"MERGE (ot)-[:LEARN_ABOUT]->(n)"
            )

    # Add CONTRIBUTED_TO connections for demo persons
    queries.append(
        "MATCH (p:Person {id: 'person_sarah_chen'}), (s:Service {id: 'svc_checkout'}) "
        "MERGE (p)-[:CONTRIBUTED_TO]->(s)"
    )
    queries.append(
        "MATCH (p:Person {id: 'person_marcus_vance'}), (s:Service {id: 'svc_token_service'}) "
        "MERGE (p)-[:CONTRIBUTED_TO]->(s)"
    )
    queries.append(
        "MATCH (p:Person {id: 'person_alex_rivera'}), (s:Service {id: 'svc_checkout'}) "
        "MERGE (p)-[:CONTRIBUTED_TO]->(s)"
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
