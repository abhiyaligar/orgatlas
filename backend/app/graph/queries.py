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
GET_REPOSITORY_FILES = """
  MATCH (f:File)
  WHERE f.repository_id = $repository_id
    AND coalesce(f.is_test, false) = false
  RETURN coalesce(f.language, 'Unknown') AS language,
         count(f) AS files,
         [x IN collect({
            path: coalesce(f.path, ''),
            summary: coalesce(f.summary, ''),
            docs_source: coalesce(f.docs_source, '')
         })[0..$per_language] | x] AS samples
  ORDER BY files DESC
"""

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
  AND ($file_prefix = '' OR s.id STARTS WITH $file_prefix)
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

# --- Document, Slack and Metric writes --------------------------------------
# Every write is a MERGE on a stable id, so re-ingesting the same document
# updates its node rather than creating a second copy with different contents.

# 28. Upsert one ingested document.
UPSERT_DOCUMENT = """
MERGE (d:Document {id: $id})
SET d.title = $title,
    d.kind = $kind,
    d.uri = $uri,
    d.sha256 = $sha256,
    d.char_count = $char_count,
    d.summary = $summary,
    d.author = $author,
    d.source_at = $source_at,
    d.ingested_at = $ingested_at,
    d.extraction_model = $extraction_model
RETURN d.id
"""

# 29. Link a document to the entities it talks about.
UPSERT_DOCUMENT_EDGES = """
UNWIND $edges AS edge
MATCH (d:Document {id: $document_id})
MATCH (t) WHERE t.id = edge.target_id
MERGE (d)-[r:DOCUMENTS]->(t)
SET r.role = edge.role
RETURN count(r)
"""

# 30. Decisions extracted from a document.
# Direction matters and follows the seed: a Decision is SUPPORTED_BY a
# Document. Writing it the other way round produces an edge that no reader
# traverses, which looks like a missing document rather than a wrong arrow.
UPSERT_EXTRACTED_DECISIONS = """
UNWIND $decisions AS row
MERGE (d:Decision {id: $document_id + ':' + row.key})
SET d.title = row.title,
    d.summary = row.summary,
    d.rationale = row.rationale,
    d.alternatives = row.alternatives,
    d.status = row.status,
    d.decided_at = row.decided_at,
    d.quote = row.quote,
    d.source_document_id = $document_id
WITH d, row
MATCH (doc:Document {id: $document_id})
MERGE (d)-[:SUPPORTED_BY]->(doc)
RETURN d.id
"""

# 31. Who was involved in a decision, and in what role.
# One query per involvement, because a relationship's type cannot be computed in
# Cypher. The caller groups by involvement and issues one of these per group.
# Every MERGE carries a label and an id: a bare MERGE (p) has no pattern to
# match and silently binds an arbitrary node from the graph.
UPSERT_DECISION_PROPOSERS = """
UNWIND $people AS row
MATCH (d:Decision {id: $decision_id})
MERGE (p:Person {id: row.person_id})
SET p.name = row.name
MERGE (p)-[r:PROPOSED]->(d)
SET r.quote = row.quote, r.role = row.role
RETURN count(p)
"""

UPSERT_DECISION_APPROVERS = """
UNWIND $people AS row
MATCH (d:Decision {id: $decision_id})
MERGE (p:Person {id: row.person_id})
SET p.name = row.name
MERGE (p)-[r:APPROVED]->(d)
SET r.quote = row.quote, r.role = row.role
RETURN count(p)
"""

UPSERT_DECISION_OBJECTORS = """
UNWIND $people AS row
MATCH (d:Decision {id: $decision_id})
MERGE (p:Person {id: row.person_id})
SET p.name = row.name
MERGE (p)-[r:OBJECTED]->(d)
SET r.quote = row.quote, r.role = row.role
RETURN count(p)
"""

UPSERT_DECISION_DISCUSSANTS = """
UNWIND $people AS row
MATCH (d:Decision {id: $decision_id})
MERGE (p:Person {id: row.person_id})
SET p.name = row.name
MERGE (p)-[r:DISCUSSED]->(d)
SET r.quote = row.quote, r.role = row.role
RETURN count(p)
"""

UPSERT_DECISION_IMPLEMENTERS = """
UNWIND $people AS row
MATCH (d:Decision {id: $decision_id})
MERGE (p:Person {id: row.person_id})
SET p.name = row.name
MERGE (p)-[r:IMPLEMENTED_IN]->(d)
SET r.quote = row.quote, r.role = row.role
RETURN count(p)
"""

# 32. Metrics a document states, kept with the sentence that stated them.
UPSERT_METRICS = """
UNWIND $metrics AS row
MERGE (m:Metric {id: $document_id + ':' + row.key})
SET m.name = row.name,
    m.value = row.value,
    m.unit = row.unit,
    m.baseline = row.baseline,
    m.direction = row.direction,
    m.quote = row.quote,
    m.source_document_id = $document_id
WITH m, row
MATCH (doc:Document {id: $document_id})
MERGE (doc)-[r:STATES_METRIC]->(m)
RETURN m.id
"""

# 33. A Slack message, kept as an excerpt rather than a transcript.
UPSERT_SLACK_MESSAGE = """
MERGE (m:SlackMessage {id: $id})
SET m.channel_id = $channel_id,
    m.channel_name = $channel_name,
    m.author = $author,
    m.slack_user_id = $slack_user_id,
    m.posted_at = $posted_at,
    m.excerpt = $excerpt,
    m.permalink = $permalink,
    m.thread_ts = $thread_ts
RETURN m.id
"""

# 34. What a Slack message was about, and who said it.
UPSERT_SLACK_MESSAGE_EDGES = """
UNWIND $edges AS edge
MATCH (m:SlackMessage {id: $message_id})
MATCH (t) WHERE t.id = edge.target_id
MERGE (m)-[r:ABOUT]->(t)
RETURN count(r)
"""

# 35. Attribute a Slack message to the person who sent it, where that person is
# already in the graph. An unknown Slack identity is left unattributed rather
# than invented as a new person.
LINK_SLACK_AUTHOR = """
MATCH (p) WHERE p.id IN $person_ids
MATCH (m:SlackMessage {id: $message_id})
MERGE (p)-[:QUOTED]->(m)
RETURN count(p)
"""

# 36. Record that a decision moved from one technology to another.
UPSERT_MIGRATION = """
UNWIND $migrations AS row
MATCH (d:Decision {id: $decision_id})
MERGE (t:Technology {id: row.id})
SET t.name = row.name
MERGE (d)-[r:MIGRATED_FROM]->(t)
RETURN count(t)
"""

# 37. The technology a decision moved to, as distinct from what it left.
UPSERT_MIGRATION_TO = """
UNWIND $migrations AS row
MATCH (d:Decision {id: $decision_id})
MERGE (t:Technology {id: row.id})
SET t.name = row.name
MERGE (d)-[r:MIGRATED_TO]->(t)
RETURN count(t)
"""

# --- Decision evidence reads -------------------------------------------------
# One traversal for the whole question. The reader wants a single story -- why,
# who, what was said, what it achieved, what shipped it -- and six separate
# calls is how a part of it gets left out.

# 38. The decision itself. Documents, people, discussion, metrics and the
# migration are separate queries: folding them into one aggregation with
# OPTIONAL MATCH and a list filter loses rows on this engine, and a missing
# document is worse than an extra round trip.
GET_DECISION_EVIDENCE = """
MATCH (d:Decision {id: $decision_id})
RETURN d.id AS decision_id,
       coalesce(d.title, '') AS title,
       coalesce(d.summary, '') AS summary,
       coalesce(d.rationale, '') AS rationale,
       coalesce(d.alternatives, '') AS alternatives,
       coalesce(d.status, 'unknown') AS status,
       coalesce(d.decided_at, '') AS decided_at,
       coalesce(d.quote, '') AS quote
LIMIT 1
"""

# 39. Documents that support a decision, with the sentence that supports it.
GET_DECISION_DOCUMENTS = """
MATCH (d:Decision {id: $decision_id})-[:SUPPORTED_BY]->(doc:Document)
RETURN doc.id AS id,
       coalesce(doc.title, doc.name, '') AS title,
       coalesce(doc.uri, '') AS uri,
       coalesce(doc.author, '') AS author,
       coalesce(doc.excerpt, '') AS excerpt
ORDER BY title
LIMIT $limit
"""

# 39b. Incidents that led to a decision.
GET_DECISION_INCIDENTS = """
MATCH (i:Incident)-[:LED_TO]->(d:Decision {id: $decision_id})
RETURN i.id AS id,
       coalesce(i.title, i.name, '') AS title,
       coalesce(i.uri, '') AS uri,
       coalesce(i.severity, '') AS severity
ORDER BY title
LIMIT $limit
"""

# 39c. Who was involved, and in what role, with the sentence that says so.
# The relationship types are matched by prefix rather than by `type(r) IN [...]`,
# which this engine does not accept in a WHERE clause.
GET_DECISION_PEOPLE = """
MATCH (p)-[r]->(d:Decision {id: $decision_id})
WHERE type(r) = 'PROPOSED' OR type(r) = 'APPROVED' OR type(r) = 'OBJECTED'
   OR type(r) = 'DISCUSSED' OR type(r) = 'IMPLEMENTED_IN'
RETURN p.id AS person_id,
       coalesce(p.name, '') AS name,
       type(r) AS involvement,
       coalesce(r.role, '') AS role,
       coalesce(r.quote, '') AS quote
ORDER BY involvement, name
LIMIT $limit
"""

# 40. Slack messages about this decision, as excerpts.
GET_DECISION_DISCUSSION = """
MATCH (m:SlackMessage)-[:ABOUT]->(d:Decision {id: $decision_id})
OPTIONAL MATCH (p)-[:QUOTED]->(m)
RETURN m.id AS source_id,
       coalesce(p.name, m.author, 'unknown') AS speaker,
       coalesce(m.excerpt, '') AS text,
       coalesce(m.channel_name, m.channel_id, '') AS channel,
       m.posted_at AS posted_at,
       coalesce(m.permalink, '') AS permalink
ORDER BY m.posted_at
LIMIT $limit
"""

# 41. Numbers the documents state, kept with the sentence that stated them.
GET_DECISION_METRICS = """
MATCH (d:Decision {id: $decision_id})-[:SUPPORTED_BY]->(doc:Document)
MATCH (doc:Document)-[:STATES_METRIC]->(m:Metric)
RETURN m.id AS id,
       m.name AS name,
       m.value AS value,
       coalesce(m.unit, 'unknown') AS unit,
       coalesce(m.baseline, '') AS baseline,
       coalesce(m.direction, 'unknown') AS direction,
       coalesce(m.quote, '') AS quote,
       coalesce(doc.id, '') AS document_id
LIMIT $limit
"""

# 42. The technologies a decision moved between.
GET_DECISION_MIGRATION = """
MATCH (d:Decision {id: $decision_id})-[r:MIGRATED_FROM|MIGRATED_TO]->(t:Technology)
RETURN type(r) AS direction, coalesce(t.name, '') AS name
ORDER BY direction, name
LIMIT $limit
"""

# 43. Commits by the people involved, newest first. This is the evidence behind
# "who actually built it", as opposed to who spoke about it.
GET_PEOPLE_COMMITS = """
UNWIND $person_ids AS person_id
MATCH (p {id: person_id})<-[:AUTHORED]-(c:Commit)
RETURN c.id AS sha,
       coalesce(c.message, '') AS message,
       c.authored_at AS authored_at,
       coalesce(c.pr_number, 0) AS pr_number,
       coalesce(p.name, '') AS author,
       coalesce(c.repository_id, '') AS repository_id
ORDER BY c.authored_at DESC
LIMIT $limit
"""

# 44. Decisions ranked by how much of the question they actually cover.
#
# Picking the best textual match is not enough when several decisions mention the
# same technology: asking about a Kafka-to-Redis migration must not resolve to a
# decision about adopting Kafka. What separates them is that only one of them
# mentions Redis at all, so the candidate is ranked by how many of the
# question's terms appear in its own text.
GET_DECISIONS_BY_TERM_COVERAGE = """
UNWIND $terms AS term
MATCH (d:Decision)
WHERE toLower(
        coalesce(d.title, '') + ' ' +
        coalesce(d.summary, '') + ' ' +
        coalesce(d.rationale, '') + ' ' +
        coalesce(d.alternatives, '')
      ) CONTAINS toLower(term)
WITH d, collect(DISTINCT term) AS hits
RETURN d.id AS id,
       coalesce(d.title, '') AS title,
       size(hits) AS coverage,
       hits
ORDER BY coverage DESC, title
LIMIT $limit
"""
