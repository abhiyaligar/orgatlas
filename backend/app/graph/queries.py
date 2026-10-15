"""Parameterized OpenCypher query templates with traversal depth and result limits."""

# 1. Onboarding Query
GET_ONBOARDING_TOPICS_BY_TEAM = """
MATCH (t:Team {id: $team_id})
OPTIONAL MATCH (ot:OnboardingTopic)-[:RECOMMENDED_FOR]->(t)
OPTIONAL MATCH (t)-[:OWNS]->(s:Service)
OPTIONAL MATCH (p:Person)-[:MEMBER_OF]->(t)
RETURN t.id AS team_id,
       t.name AS team_name,
       t.mission AS team_mission,
       collect(DISTINCT ot) AS topics,
       collect(DISTINCT s) AS services,
       collect(DISTINCT p) AS people
LIMIT 1
"""

# 2. Decision Trace Query with Evidence
GET_DECISION_TRACE = """
MATCH (d:Decision {id: $decision_id})
OPTIONAL MATCH (d)-[:DECIDED_BY]->(p:Person)
OPTIONAL MATCH (d)-[:DECIDED_BY]->(t:Team)
OPTIONAL MATCH (d)-[:AFFECTS]->(s:Service)
OPTIONAL MATCH (d)-[:SUPPORTED_BY]->(doc:Document)
OPTIONAL MATCH (i:Incident)-[:LED_TO]->(d)
OPTIONAL MATCH (pr:PullRequest)-[:IMPLEMENTS]->(d)
OPTIONAL MATCH (tk:Ticket)-[:IMPLEMENTS]->(d)
RETURN d,
       collect(DISTINCT p) AS people,
       collect(DISTINCT t) AS teams,
       collect(DISTINCT s) AS services,
       collect(DISTINCT doc) AS documents,
       collect(DISTINCT i) AS incidents,
       collect(DISTINCT pr) AS pull_requests,
       collect(DISTINCT tk) AS tickets
LIMIT 1
"""

# 3. Change Impact Query (Bounded 2-hop dependencies, incoming & outgoing)
GET_CHANGE_IMPACT = """
MATCH (s:Service {id: $service_id})
OPTIONAL MATCH (t:Team)-[:OWNS]->(s)
OPTIONAL MATCH (s)-[:DEPENDS_ON*1..2]->(downstream:Service)
OPTIONAL MATCH (upstream:Service)-[:DEPENDS_ON*1..2]->(s)
OPTIONAL MATCH (i:Incident)-[:AFFECTS]->(s)
OPTIONAL MATCH (d:Decision)-[:AFFECTS]->(s)
RETURN s AS target_service,
       t AS owner_team,
       collect(DISTINCT downstream) AS downstream_services,
       collect(DISTINCT upstream) AS upstream_services,
       collect(DISTINCT i) AS incidents,
       collect(DISTINCT d) AS decisions
LIMIT 1
"""

# 4. Service Ownership and Maintainers Query
GET_SERVICE_OWNERSHIP = """
MATCH (s:Service {id: $service_id})
OPTIONAL MATCH (t:Team)-[:OWNS]->(s)
OPTIONAL MATCH (p:Person)-[:MEMBER_OF]->(t)
OPTIONAL MATCH (c:Person)-[:CONTRIBUTED_TO]->(s)
OPTIONAL MATCH (r:Repository)-[:PRIMARY_IMPLEMENTATION_OF]->(s)
OPTIONAL MATCH (doc:Document)-[:DOCUMENTS]->(s)
RETURN s AS service,
       t AS team,
       collect(DISTINCT p) AS team_members,
       collect(DISTINCT c) AS contributors,
       r AS repository,
       collect(DISTINCT doc) AS documents
LIMIT 1
"""

# 5. Entity Detail and Immediate Neighbors
GET_ENTITY_DETAIL = """
MATCH (n {id: $entity_id})
OPTIONAL MATCH (n)-[r]->(target)
OPTIONAL MATCH (source)-[r_in]->(n)
RETURN n,
       collect(DISTINCT {rel: type(r), dir: 'outgoing', target: target}) AS outgoing,
       collect(DISTINCT {rel: type(r_in), dir: 'incoming', source: source}) AS incoming
LIMIT 1
"""

# 7. Fetch Documents by Stable Id List
GET_DOCUMENTS_BY_IDS = """
MATCH (doc:Document)
WHERE doc.id IN $doc_ids
RETURN doc
LIMIT 50
"""

# 8. Search Entities by Name / Substring
SEARCH_ENTITIES = """
MATCH (n)
WHERE (n.name IS NOT NULL AND toLower(n.name) CONTAINS toLower($query))
   OR (n.title IS NOT NULL AND toLower(n.title) CONTAINS toLower($query))
RETURN n.id AS id,
       labels(n)[0] AS label,
       coalesce(n.name, n.title) AS name,
       properties(n) AS properties
LIMIT 20
"""
