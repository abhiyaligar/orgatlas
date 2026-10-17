# Deployment and environments

Every value in this document is a placeholder. No real credential appears here,
in `.env.example`, or anywhere else in the repository. Secrets are read from
environment variables and never from source.

## Target deployment

| Component | Platform | Type |
| --- | --- | --- |
| React/Vite client | Render | Static Site |
| FastAPI service | Render | Web Service |
| MCP context server | Same Render Web Service | Isolated `/mcp` route, bearer-authenticated |
| Knowledge graph | FalkorDB Cloud | Managed graph database |
| Answer synthesis and extraction | Nebius | Inference API |
| Repository ingestion | E2B | Ephemeral sandbox per scan, killed when finished |
| Slack bot | Any long-running host | Socket Mode, outbound connection only |

## Environment separation

| Environment | `ENVIRONMENT` | Purpose | Data |
| --- | --- | --- | --- |
| Local | `development` | Fast feedback | Local or cloud development graph |
| Demo/production | `production` | Judge-facing deployment | Curated graph, MCP requires a token |

`FALKORDB_GRAPH_NAME` must differ between the two. The development graph is
disposable; the production graph is not, and a scan writing into the wrong one
is not recoverable by re-seeding.

## Required in production

| Variable | Why |
| --- | --- |
| `MCP_API_TOKEN` | `/mcp` **does not mount** without it. Without a token the route returns 404 rather than serving an open context server. |
| `MCP_ALLOWED_HOSTS` | With DNS-rebinding protection on and no allowed host, every request is refused as a rebinding attempt. |
| `ENVIRONMENT=production` | Selects the strict mount behaviour. |
| `CORS_ORIGINS` | The deployed client origin only. MCP is never included. |

## Placeholder configuration

Copy `.env.example` and replace every placeholder. The values below are shapes,
not working credentials.

```bash
# --- Application ------------------------------------------------------------
ENVIRONMENT=production
DEBUG=false
API_V1_PREFIX=/api
CORS_ORIGINS=https://your-frontend.example.com

# --- Knowledge graph (FalkorDB Cloud) ---------------------------------------
FALKORDB_HOST=your-instance.falkordb.example.com
FALKORDB_PORT=6379
FALKORDB_USERNAME=your-graph-username
FALKORDB_PASSWORD=your-graph-password
FALKORDB_GRAPH_NAME=your-graph-name

# --- Relational store -------------------------------------------------------
# SQLite locally; point at Postgres in production.
DATABASE_URL=postgresql+psycopg://user:password@host:5432/orgatlas

# --- Inference --------------------------------------------------------------
NEBIUS_API_KEY=your-nebius-api-key
NEBIUS_API_BASE_URL=https://your-nebius-endpoint.example.com/v1
NEBIUS_MODEL_NAME=your-answer-model
# Optional. Defaults to NEBIUS_MODEL_NAME. See DOCUMENTS.md for measured cost.
NEBIUS_EXTRACTION_MODEL_NAME=your-extraction-model
ASK_SYNTHESIS_ENABLED=true
ASK_SYNTHESIS_TIMEOUT_SECONDS=45

# --- MCP context server -----------------------------------------------------
# Comma-separated, so a secret can be rotated by running both at once.
MCP_API_TOKEN=replace-with-a-long-random-string
MCP_ALLOWED_HOSTS=your-api.example.com

# --- Repository ingestion (E2B) --------------------------------------------
E2B_API_KEY=your-e2b-api-key
E2B_INGEST_TEMPLATE=your-built-template-id
E2B_SANDBOX_TIMEOUT=600
INGEST_COMMIT_DEPTH=600
INGEST_CACHE_DIR=data/ingest_cache

# --- Slack (optional) -------------------------------------------------------
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token
# Empty means the bot is silent in every channel.
SLACK_ALLOWED_CHANNELS=C0000000000,C1111111111
SLACK_MAX_QUESTION_CHARS=800
```

Generate the MCP token rather than typing one:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### Frontend

The client needs one build-time variable, and it is not a secret:

```bash
VITE_API_BASE_URL=https://your-api.example.com/api
```

It is compiled into the static bundle, so it must never be a credential. See
[FALKORDB.md](FALKORDB.md) for why no secret may reach the browser.

## What each setting does

The block above shows the *shape* of each value. This table says what it is for, because
several names are not self-explanatory.

| Variable | What it does |
| --- | --- |
| `API_V1_PREFIX` | Prefix for REST routes. `/api` by default. |
| `ASK_SYNTHESIS_ENABLED` | `false` answers from graph facts only, with no provider call at all. |
| `ASK_SYNTHESIS_TIMEOUT_SECONDS` | Per-answer synthesis timeout. A reasoning model needs headroom. |
| `CORS_ORIGINS` | Browser origins allowed. MCP is never included, in any environment. |
| `DATABASE_URL` | Relational store for jobs, documents, extractions, Slack messages. |
| `DEBUG` | FastAPI debug flag. Leave false outside local development. |
| `E2B_API_KEY` | Repository ingestion sandboxes. Secret, and never sent to a sandbox. |
| `E2B_INGEST_TEMPLATE` | Built sandbox template id. |
| `E2B_SANDBOX_TIMEOUT` | Sandbox lifetime in seconds. |
| `ENVIRONMENT` | `development` mounts MCP open with a warning; `production` requires a token and refuses to mount without one. |
| `FALKORDB_GRAPH_NAME` | Graph name. Must differ between development and production. |
| `FALKORDB_HOST` | Graph host. |
| `FALKORDB_PASSWORD` | Graph password. Secret. |
| `FALKORDB_PORT` | Graph port. |
| `FALKORDB_USERNAME` | Graph username. |
| `INGEST_CACHE_DIR` | Where scan payloads are written for inspection. Never read back. |
| `INGEST_COMMIT_DEPTH` | How many commits of history to walk. Deeper costs sandbox time and graph size. |
| `MCP_ALLOWED_HOSTS` | Host headers MCP answers to. Required in production. |
| `MCP_API_TOKEN` | Bearer token for `/mcp`. Comma-separated to allow rotation. Secret. |
| `NEBIUS_API_BASE_URL` | Provider base URL. |
| `NEBIUS_API_KEY` | Answer synthesis, document extraction, and the file-description fallback. Secret. |
| `NEBIUS_EXTRACTION_MODEL_NAME` | Model used for document extraction. Defaults to `NEBIUS_MODEL_NAME`; see [DOCUMENTS.md](DOCUMENTS.md) for measured differences. |
| `NEBIUS_MODEL_NAME` | Model used for answers. A reasoning model is expected but not required. |
| `SLACK_ALLOWED_CHANNELS` | Channels the bot answers in. Empty means silent in every channel. |
| `SLACK_APP_TOKEN` | Socket Mode app token, needs `connections:write`. Secret. |
| `SLACK_BOT_TOKEN` | Slack bot token. Secret. |
| `SLACK_MAX_QUESTION_CHARS` | Longer questions are truncated and marked as such. |

## Secret ownership

| Secret | Stored in | Notes |
| --- | --- | --- |
| FalkorDB connection | API service environment variables | Development and production use different graphs |
| Nebius API key | API service environment variables | Also used for the file-description fallback |
| E2B API key | API service environment variables | Never sent to a sandbox |
| MCP bearer token | API service environment variables | Rotate by running both tokens, then dropping the old |
| Slack tokens | The host running the bot | The bot is optional and runs outside the API service |

No secret may appear in the React bundle, source control, screenshots, demo
videos, or logs. **The ingestion sandbox receives no credential of any kind:** it
clones and parses, and the API process performs every graph write and every
provider call.

## Ingestion image

The sandbox template is built by `e2b_template.py` and referenced by
`E2B_INGEST_TEMPLATE`. It supplies the operating system, git, Python, and the
pinned tree-sitter grammars. Grammar versions live in `tree_sitter_deps.py` and
are shared with `backend/requirements.txt`, so the image and the local
environment cannot diverge.

- **Rebuild the template after changing anything the scanner imports.** The
  application package is uploaded into each sandbox at run time, but third-party
  packages are baked in at build time. A build-time smoke test constructs and
  parses with every grammar, so a template that cannot extract symbols fails to
  build rather than silently reporting none.
- **Build to a new name before switching.** `TEMPLATE_NAME` in
  `e2b_template.py` names the built image. Change it, verify, then update
  `E2B_INGEST_TEMPLATE`, so the working template survives a failed build.

## Slack bot

Socket Mode opens an **outbound** WebSocket to Slack, so the bot needs no public
URL and no inbound firewall rule. It is therefore a long-running process on a
host that can stay connected, not a serverless function and not part of the API
service. See [SLACK.md](SLACK.md).

Without `SLACK_ALLOWED_CHANNELS` the bot stays silent in every channel. That is
the default, deliberately: a bot that has merely been invited to a workspace must
not start answering in it.

## Operational notes

- FalkorDB Cloud caps a result set at 10,000 rows. Bulk work uses keyset
  pagination or predicate-based deletion rather than enumerating and deleting
  row by row.
- `FLUSHDB` is not available to the configured FalkorDB Cloud user. A full clean
  drops the graph with the client's graph-level delete and recreates it.
- The scan payload cache is written for inspection but is never read back, so a
  re-ingest always pays for a fresh sandbox run.
- Document extraction costs roughly 8,000 completion tokens per document, because
  the configured model is a reasoning model run over prose. `extract=false` on
  upload skips it. See [DOCUMENTS.md](DOCUMENTS.md).

## Release checklist

1. Confirm the schema and seed data produce every required demo path.
2. Verify `GET /api/health` reaches FalkorDB.
3. Run the demo prompts against the deployed graph.
4. Confirm citations and graph highlights match the returned answer.
5. Verify `CORS_ORIGINS` contains only the deployed client origin.
6. With `MCP_API_TOKEN` set, confirm `/mcp` returns **401** without it and
   **200** with it. With it unset and `ENVIRONMENT=production`, confirm `/mcp`
   returns **404**.
7. Confirm `MCP_ALLOWED_HOSTS` matches the deployed host, and that a request with
   a different `Host` header is refused.
8. Confirm the frontend has loading, empty, and provider-failure states.
9. Confirm MCP tools are read-only and return structured citations for every demo
   query.
10. Confirm the ingestion template is current and its grammar smoke test passed.
11. If Slack is deployed, confirm the bot is silent outside
    `SLACK_ALLOWED_CHANNELS`.
12. Record a fallback demo video before submission.