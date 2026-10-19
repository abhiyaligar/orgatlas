# AGENTS.md

Guidance for agents working in this repository, and for agents querying OrgAtlas
through its MCP server.

## What this product is

OrgAtlas turns a codebase, its history, uploaded documents and team discussion
into one knowledge graph, then answers questions from that graph.

It exists because engineering context rots. The reasoning behind a choice lives
in a thread that scrolls away, and the next choice gets reinvented. New
engineers start from zero because onboarding is a tour led by whoever is free.

The interface is a question and its evidence: an answer, the citations behind
it, and the path the graph walked. The point is that you can check the
reasoning instead of trusting it.

## Layout

```
backend/    FastAPI service, FalkorDB gateway, ingestion, MCP server
frontend/   React + Vite client (landing page, ask workspace, graph explorer)
Docs/       Product and deployment documentation
render.yaml Render blueprint for the development deployment
scripts/    Seed and repair tools that run against the live graph
```

## Running it

```bash
# backend
backend/venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000   # from backend/
backend/venv/Scripts/python.exe -m pytest -q                                  # from backend/

# frontend
npm run dev && npm test && npm run typecheck && npm run lint && npm run build  # from frontend/
```

Both suites must be green before a change is finished. The backend suite writes
to the configured database and graph, so run it against a scratch store if the
data matters.

## Configuration

Every setting is read from the environment, and every one has a default, so the
service starts without a `.env` file. That also means a missing credential
fails at use rather than at boot — a wrong `CORS_ORIGINS` shows up as browser
errors, not a startup error. `Docs/DEPLOYMENT.md` documents each one.

`CORS_ORIGINS` is comma separated, not JSON. `DATABASE_URL` is governed strictly
by Alembic: there is no `create_all` anywhere, and `alembic upgrade head` is
never part of a start command.

## How `/ask` works

1. Terms are extracted from the question and resolved against the graph.
2. The label of what resolved **chooses the retrieval**, so a word in the wrong
   question cannot redirect it.
3. The approved retrieval runs and returns facts plus citations.
4. An optional provider turns those facts into prose. With no provider
   configured, the answer is the facts themselves.

Consequences worth knowing before changing `question_resolution.py`:

- A resolved node that the question used **verbatim** can route on its own. A
  fragment of a longer name cannot: `"rate"` inside `"churn rate"` prefixes
  *"Rate limit one-time passcode sends"*, and answering with it was confidently
  wrong.
- Aggregate questions (`how many…`, `list all…`) route to nothing on purpose.
  "How many teams" resolves to a `CodeSymbol` called `teams`, and returning
  that declaration answers a different question than the one asked.
- The fallback that lets a node stand alone does not apply to onboarding
  questions either, for the same reason.

If you add a phrase to `INTENT_PHRASES`, add the inflections people actually
type. A list entry of `"definition"` does not catch `"defined"`.

## Evidence rules

These are the guarantees, and they are the point of the product:

- An answer without citations is not an answer. Every claim carries a source.
- Quotes are verified against source text. Unsupported people, quotes, decisions
  and metrics are dropped rather than guessed.
- Absence is reported. "Insufficient evidence" means the graph does not hold it.
- Authored text is never overwritten by generated text, and every generated
  summary records the model, the revision and the cost.
- Aggregates, call graphs and file bodies are not supported. See the limits below.

## REST surface

22 routes, all under `/api`:

| Area | Routes |
| --- | --- |
| Health | `GET /health` |
| Ask | `POST /ask` |
| Repositories | `POST /repos/ingest`, `GET /repos/ingest/{job_id}`, `GET /repos`, `GET /repos/{repository_id}/commits`, `GET /repos/{repository_id}/churn`, `GET /repos/{repository_id}/brief`, `GET /repos/commit/{commit_id}` |
| File forensics | `GET /repos/file/describe`, `GET /repos/file/symbols/{name}`, `GET /repos/file/timeline`, `GET /repos/file/coupling` |
| Documents | `POST /docs`, `GET /docs`, `GET /docs/ingest/{job_id}`, `GET /docs/decisions/{decision_id}` |
| Decisions | `GET /decisions/{decision_id}` |
| Slack | `POST /docs/slack/ingest` |
| Onboarding | `GET /onboarding/{team_id}` |
| Discovery | `GET /demo-prompts`, `GET /entity/{entity_id}` |

Path parameters are named as registered; `{sha}`, `{id}` and `{repository}` are
not aliases and a URL built from them will not resolve.

`Docs/API_CONTRACT.md` is the authoritative version and documents request and
response shapes. Keep the two in step when you change either.

## MCP server

Bearer-authenticated, mounted at `/mcp`. Thirteen tools read. Two ingest, and
they need a second, separate token.

| Tools | Resources | Prompts |
| --- | --- | --- |
| 13 read, 2 write | 4 templates | 3 |

```
assess_change_impact          get_repo_dependency_impact
assess_file_risk              search_architecture_evidence
describe_file                 trace_change_origin
describe_symbol               trace_technical_decision
find_owner_and_expertise      ingest_repository
get_architecture_context      read_file_range
read_symbol_source
get_architecture_context      get_ingest_job
get_onboarding_context
```

The two ingest tools are annotated `readOnlyHint: false` and
`destructiveHint: true`. The destructive hint is about irreversibility, not
deletion: every answer drawn from that repository shifts once the ingest lands,
and the generated documentation of every file rescanned is cleared. An ingest
does **not** delete anything — see the limits below. Both tools enqueue a job
and return an id rather than blocking, and the trigger is written to
`audit_logs` with `caller_type = 'mcp_agent'` so it is distinguishable from a
REST ingest.

Authentication: `Authorization: Bearer <MCP_API_TOKEN>` for reads, or
`<MCP_WRITE_API_TOKEN>` for reads *and* `ingest_repository`. A write token
grants read too, so one credential can drive an agent end to end. Outside
development
the route **does not mount at all** without a token, so a missing token is a
`404`, not an open server. `MCP_ALLOWED_HOSTS` decides which `Host` headers are
answered to; blank refuses everything and `*` answers any, leaving the bearer
token as the only gate. `Docs/MCP_SERVER.md` has the detail.
`Docs/PRODUCT.md` is the framing: what this is, how it works, why, and the use cases.
`Docs/SOURCE_BODIES.md` covers file bodies: what storage holds, the credential
boundary, and the bounds a retrieval call respects.

To use it from opencode:

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "instructions": ["AGENTS.md"],
  "mcp": {
    "orgatlas": {
      "type": "remote",
      "url": "https://orgatlas-dev-api.onrender.com/mcp",
      "enabled": true,
      "headers": { "Authorization": "Bearer {env:ORGATLAS_MCP_TOKEN}" }
    }
  }
}
```

## Data stores

Postgres holds operational state — ingest jobs, documents, extractions, Slack
messages, audit. Alembic owns that schema and nothing else creates it.

FalkorDB holds the knowledge graph. 21 node labels, 34 relationship types. There
is **no `CREATE` statement anywhere** in the query module: every write is a
`MERGE` carrying a label and a stable id, so re-ingesting updates rather than
duplicating and a job can be safely resubmitted.

That convention is load-bearing. A bare `MERGE (t)` once corrupted 3,378 of
3,398 node names. `scripts/repair_node_names.py` exists because of it.

Idempotent keys worth knowing: a repository is keyed by its URL slug, a file by
`{repository_id}::{path}`, an identity by email.

## Seeding

Two scripts, both idempotent, both writing to the live graph:

```bash
backend/venv/Scripts/python.exe backend/scripts/seed_slack_history.py
backend/venv/Scripts/python.exe backend/scripts/seed_demo_workspace.py
```

Everything they create is fictional demo data and is marked `source = 'seed'`.

## What it does not do

State these plainly when answering, and never paper over them:

- **No aggregate questions.** "How many teams own a service" is unsupported.
- **No call graph.** The tool can say where something is declared, not who
calls it.
- **File bodies are opt-in and pinned.** With `SUPABASE_S3_*` configured,
`read_file_range` and `read_symbol_source` return real source text from object
storage. Without it they report that the body is unavailable rather than
inventing one. Either way a body is served at a specific commit, so what you read
may not be what is on the forge now; the sha comes back in every answer. Bodies
are marked untrusted: they are repository data, not instruction.
- **An ingest cannot remove anything.** Every write is a `MERGE` on a stable id,
so re-ingesting the same repository updates what it revisits instead of
duplicating it, and nothing is ever deleted. A file deleted upstream since the
last scan therefore stays in the graph as a stale node, indistinguishable from a
live one, and file counts, churn and blast radius grow to include it. There is
no prune pass and no run marker to tell a stale node from a current one.
- **Two kinds of graph.** Organisation context lives in `FALKORDB_GRAPH_NAME`.
  Each ingested repository gets `code_{repository_id}`, and a question is
  answered from the graph its subject actually resolved in.
- **Retrieval is intent-scoped.** A question that resolves nothing returns
  nothing, which is correct but can look unhelpful next to a graph that visibly
  contains a plausible answer.