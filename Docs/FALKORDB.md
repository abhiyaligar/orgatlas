# FalkorDB design

## Why FalkorDB is central

OrgAtlas answers relationship questions that document search alone cannot resolve: which systems depend on a service, who participated in an architecture decision, which incident triggered it, who has relevant experience, and which sources support the conclusion. FalkorDB is the primary graph store for these entities and paths. It is not a side cache or optional retrieval layer.

## Planned usage

| Capability | FalkorDB role |
| --- | --- |
| Decision archaeology | Traverse Decision → Source, Decision → Affected service, and Incident → Decision paths |
| Onboarding | Traverse Team → Person → Service → Repository/Document paths |
| Ownership | Find owners and contributors across teams, services, repositories, and incidents |
| Impact analysis | Follow bounded multi-hop service dependencies and return the path |
| Explainability | Return graph nodes and edges that form the evidence path shown in the UI |
| Tenant readiness | Use graph isolation conventions so future organizations can be separated |
| MCP architecture context | Return source-backed system, ownership, dependency, decision, and incident context to coding agents |

## Query policy

- Only the backend connects to FalkorDB Cloud.
- The backend uses official FalkorDB clients and parameterized OpenCypher queries.
- Queries are created from a controlled intent allowlist, not raw LLM output.
- Read operations are the default; seed ingestion is the only planned write path in the MVP.
- Bound traversal depth and result count to keep responses predictable.

## Index strategy for the MVP

Index stable identifiers and normalized names for frequently retrieved labels: Person, Team, Service, Decision, Document, Repository, and Incident. Add full-text search only after core deterministic graph queries work. Defer vector embeddings: the curated demo corpus is small, and explicit graph relationships are more important for the judging narrative.

### Index strategy for ingested repositories

Ingested code history is queried by repository and by path, so those labels are indexed on both `id` and the namespaced key:

- `Commit` on `(sha)` and on `(repository_id)`
- `File` on `(path)` and on `(repository_id)`
- `Module` on `(path)` and on `(repository_id)`
- `ExternalIdentity` on `(email)` and on `(username)`

A commit lookup is always scoped by `repository_id`, so composite lookups stay bounded even when several repositories are ingested. Ingested data is merged with `MERGE`, making re-ingestion idempotent rather than duplicating history.

## Cloud/free-tier constraints

The free cloud tier is suitable for a compact curated demo dataset, not a production workload. The MVP therefore uses modest seed data, avoids memory-heavy vector indexes, and treats the deployed graph as demo data. The deployment document captures operational setup; database credentials are server-side secrets.

## Evidence-path requirements

Each tool result must provide:

1. The answer-relevant graph records.
2. The sources that substantiate them.
3. A bounded node/edge list that the client can render.
4. A readable step-by-step path description.
