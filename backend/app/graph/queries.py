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

# 19. Authored description stored on a File during ingestion
GET_FILE_DESCRIPTION = """
MATCH (f:File {id: $file_id})
RETURN f.path AS path,
       coalesce(f.name, '') AS name,
       coalesce(f.language, '') AS language,
       coalesce(f.is_test, false) AS is_test,
       coalesce(f.summary, '') AS summary,
       coalesce(f.symbols, '[]') AS symbols,
       coalesce(f.docs_source, 'none') AS docs_source,
       coalesce(f.docs_at_sha, '') AS docs_at_sha,
       coalesce(f.repository_id, '') AS repository_id,
       coalesce(f.docs_model, '') AS docs_model,
       coalesce(f.docs_generated_at, '') AS docs_generated_at,
       coalesce(f.docs_input_sha, '') AS docs_input_sha,
       coalesce(f.docs_trigger, '') AS docs_trigger,
       coalesce(f.docs_usage, '') AS docs_usage,
       coalesce(f.docs_raw_response, '') AS docs_raw_response,
       coalesce(f.docs_prompt_version, '') AS docs_prompt_version,
       coalesce(f.docs_error, '') AS docs_error
LIMIT 1
"""

# 20. Authored timestamp of the commit a description was derived from
GET_COMMIT_AUTHORED_AT = """
MATCH (c:Commit {id: $sha})
RETURN c.authored_at AS authored_at
LIMIT 1
"""

# 21. Commits touching a file after the point its description was written
GET_FILE_CHANGES_AFTER = """
MATCH (c:Commit)-[:MODIFIES]->(f:File {id: $file_id})
WHERE c.authored_at > $since
RETURN count(c) AS changes,
       collect(DISTINCT c.id)[..5] AS recent_shas
"""
# 22. Look up a declaration by name, optionally scoped to one file
GET_CODE_SYMBOL = """
MATCH (s:CodeSymbol)
WHERE toLower(s.name) = toLower($name)
  AND ($file_id = '' OR s.id STARTS WITH $file_id + '::')
RETURN s.id AS id,
       s.name AS name,
       coalesce(s.kind, '') AS kind,
       coalesce(s.signature, '') AS signature,
       coalesce(s.doc_comment, '') AS doc_comment,
       coalesce(s.documented, false) AS documented,
       coalesce(s.line, 0) AS line,
       coalesce(s.visibility, '') AS visibility,
       coalesce(s.container, '') AS container,
       coalesce(s.language, '') AS language,
       coalesce(s.repository_id, '') AS repository_id,
       coalesce(s.docs_at_sha, '') AS docs_at_sha
ORDER BY s.documented DESC, size(s.doc_comment) DESC
LIMIT $limit
"""

# 23. Names of declarations matching a text query, for tool discovery
SEARCH_CODE_SYMBOLS = """
MATCH (s:CodeSymbol)
WHERE toLower(s.name) CONTAINS toLower($query)
RETURN s.name AS name,
       s.id AS id,
       coalesce(s.kind, '') AS kind,
       coalesce(s.container, '') AS container,
       coalesce(s.documented, false) AS documented
LIMIT $limit
"""

# 24. The file a declaration belongs to, with that file's history context
GET_SYMBOL_FILE = """
MATCH (f:File)-[:DECLARES]->(s:CodeSymbol {id: $symbol_id})
RETURN f.id AS file_id,
       f.path AS path,
       coalesce(f.repository_id, '') AS repository_id,
       coalesce(f.language, '') AS language,
       coalesce(f.is_test, false) AS is_test
LIMIT 1
"""

# 25. Resolve every term a question mentions in one round trip.
# Resolution runs per question, so one query per term would make ask latency
# scale with sentence length. UNWIND keeps it to a single call regardless.
# The match is reported back per term so the caller can tell which word in the
# question produced which node.
SEARCH_ENTITIES_BY_TERMS = """
UNWIND $terms AS term
MATCH (n)
WHERE toLower(coalesce(n.name, n.title, '')) CONTAINS toLower(term)
WITH term, n, toLower(coalesce(n.name, n.title, '')) AS lname
WITH term, n,
     CASE
       WHEN lname = toLower(term) THEN 0
       WHEN lname STARTS WITH toLower(term) THEN 1
       ELSE 2
     END AS quality
RETURN term AS term,
       n.id AS id,
       labels(n)[0] AS label,
       coalesce(n.name, n.title) AS name,
       quality AS quality
ORDER BY quality
LIMIT $limit
"""

# 26. Declaration lookup by several candidate names at once, with the file and
# line attached so an answer can cite where each symbol lives.
SEARCH_CODE_SYMBOLS_BY_TERMS = """
UNWIND $terms AS term
MATCH (s:CodeSymbol)
WHERE toLower(s.name) CONTAINS toLower(term)
OPTIONAL MATCH (f:File)-[:DECLARES]->(s)
RETURN term AS term,
       s.name AS name,
       s.id AS id,
       coalesce(s.kind, '') AS kind,
       coalesce(s.signature, '') AS signature,
       coalesce(s.doc_comment, '') AS doc_comment,
       coalesce(s.documented, false) AS documented,
       coalesce(s.line, 0) AS line,
       coalesce(s.visibility, '') AS visibility,
       coalesce(s.container, '') AS container,
       coalesce(s.language, '') AS language,
       coalesce(f.path, '') AS path,
       coalesce(f.id, '') AS file_id,
       coalesce(f.is_test, false) AS is_test
LIMIT $limit
"""

# 27. The decision a node led to, was made for, or is documented by.
# A "why" question usually resolves to the incident or the document rather than
# to the decision itself, so the decision is one hop away in the graph.
FIND_RELATED_DECISIONS = """
MATCH (n {id: $node_id})-[r]-(d:Decision)
RETURN d.id AS id,
       coalesce(d.title, '') AS title,
       type(r) AS via
LIMIT 5
"""
