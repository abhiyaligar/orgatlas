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

# --- Repository forensics queries -------------------------------------------
# Every value is parameterised and every traversal is bounded.

# 9. Change history for one file, newest first, with its attributed author
GET_FILE_HISTORY = """
MATCH (f:File {id: $file_id})<-[:MODIFIES]-(c:Commit)
OPTIONAL MATCH (a)-[:AUTHORED]->(c)
RETURN c.id AS sha,
       c.message AS message,
       c.authored_at AS authored_at,
       c.pr_number AS pr_number,
       coalesce(a.id, '') AS author_id,
       coalesce(a.username, c.author_name, '') AS author
ORDER BY c.authored_at DESC
LIMIT $limit
"""

# 10. Churn ranking: which files changed most, optionally within a path prefix
GET_FILE_CHURN = """
MATCH (r:Repository {id: $repository_id})-[:HAS_COMMIT]->(c:Commit)-[:MODIFIES]->(f:File)
WHERE $path_prefix = '' OR f.path STARTS WITH $path_prefix
RETURN f.id AS file_id,
       f.path AS path,
       f.is_test AS is_test,
       count(c) AS changes
ORDER BY changes DESC
LIMIT $limit
"""

# 11. Files touched since a point in time, for correlating with an incident
GET_FILES_CHANGED_SINCE = """
MATCH (r:Repository {id: $repository_id})-[:HAS_COMMIT]->(c:Commit)-[:MODIFIES]->(f:File)
WHERE c.authored_at >= $since
RETURN f.id AS file_id,
       f.path AS path,
       count(c) AS changes
ORDER BY changes DESC
LIMIT $limit
"""

# 12. Who has worked on a path
GET_PATH_CONTRIBUTORS = """
MATCH (r:Repository {id: $repository_id})-[:HAS_COMMIT]->(c:Commit)-[:MODIFIES]->(f:File)
WHERE f.path STARTS WITH $path_prefix
OPTIONAL MATCH (a)-[:AUTHORED]->(c)
RETURN coalesce(a.id, '') AS author_id,
       coalesce(a.username, c.author_name, '') AS author,
       count(DISTINCT c) AS commits
ORDER BY commits DESC
LIMIT $limit
"""

# 13. Commits touching a module or file path
GET_COMMITS_FOR_PATH = """
MATCH (r:Repository {id: $repository_id})-[:HAS_COMMIT]->(c:Commit)-[:MODIFIES]->(f:File)
WHERE f.path STARTS WITH $path_prefix
RETURN c.id AS sha,
       c.message AS message,
       c.authored_at AS authored_at,
       c.pr_number AS pr_number,
       collect(DISTINCT f.path) AS paths
ORDER BY c.authored_at DESC
LIMIT $limit
"""

# 14. Bounded cross-repository blast radius
GET_DEPENDENCY_IMPACT = """
MATCH (r:Repository {id: $repository_id})-[:DEPENDS_ON_REPO*1..2]->(dep:Repository)
RETURN dep.id AS id,
       dep.name AS name,
       coalesce(dep.url, '') AS url
LIMIT $limit
"""

# 15. Single commit with its author, for provenance tracing
GET_COMMIT_DETAIL = """
MATCH (c:Commit {id: $commit_id})
OPTIONAL MATCH (a)-[:AUTHORED]->(c)
OPTIONAL MATCH (r:Repository)-[:HAS_COMMIT]->(c)
RETURN c.id AS sha,
       c.message AS message,
       c.authored_at AS authored_at,
       c.pr_number AS pr_number,
       coalesce(a.id, '') AS author_id,
       coalesce(a.username, c.author_name, '') AS author,
       coalesce(r.id, '') AS repository_id
LIMIT 1
"""

# 16. Files sharing the most commits with a given file (change coupling)
GET_CHANGE_COUPLING = """
MATCH (f:File {id: $file_id})<-[:MODIFIES]-(c:Commit)-[:MODIFIES]->(other:File)
WHERE other.id <> $file_id
RETURN other.id AS file_id, other.path AS path, count(c) AS shared_commits
ORDER BY shared_commits DESC
LIMIT $limit
"""

# 17. Ingested repositories with their commit and file counts
LIST_REPOSITORIES = """
MATCH (r:Repository)
OPTIONAL MATCH (r)-[:HAS_COMMIT]->(c:Commit)
OPTIONAL MATCH (c)-[:MODIFIES]->(f:File)
RETURN r.id AS id,
       coalesce(r.name, '') AS name,
       coalesce(r.url, '') AS url,
       coalesce(r.source, '') AS source,
       count(DISTINCT c) AS commits,
       count(DISTINCT f) AS files
ORDER BY commits DESC
LIMIT $limit
"""

# 18. Existence check for a repository
GET_REPOSITORY = """
MATCH (r:Repository {id: $repository_id})
RETURN r.id AS id, coalesce(r.name, '') AS name
LIMIT 1
"""
