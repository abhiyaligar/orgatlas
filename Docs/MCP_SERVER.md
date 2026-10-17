# MCP server design — OrgAtlas Context Server

## Purpose

The OrgAtlas Context Server exposes source-backed engineering architecture context to compatible coding agents through Model Context Protocol (MCP). Its purpose is to help an agent make relevant, architecture-aligned changes by revealing the systems, repositories, owners, dependencies, incidents, decisions, and documents surrounding a proposed change.

It is a context service—not a code-generation, repository-editing, deployment, or database-writing service.

MCP supports prompts, resources, and tools. OrgAtlas uses each primitive intentionally: stable context is exposed as resources, reusable planning guidance as prompts, and parameterized graph retrieval as tools. [MCP server primitives](https://modelcontextprotocol.io/specification/draft/server/index)

## User promise

Before changing a service, a coding agent can ask OrgAtlas:

> “What should I understand before changing Checkout authentication?”

The returned package identifies the service and repository, direct and bounded multi-hop dependencies, owners and relevant contributors, previous incidents, architecture decisions, source documents, recommended investigation steps, and any missing evidence.

This reduces avoidable irrelevant changes and accidental breakage. It does **not** guarantee a change is safe; the agent and user must still inspect the code, run tests, and approve edits.

## Initial MCP surface

### Resources — stable, readable context

| Resource | Provides |
| --- | --- |
| Service architecture context | Service summary, repository, owners, dependencies, runbooks, and linked decisions |
| Team onboarding context | Team systems, key people, required reading, and recent incidents |
| Decision record | Rationale, alternatives, effects, and supporting sources |
| Repository context | Linked services, owners, contributors, and relevant decisions/incidents |

### Prompts — user-invoked planning templates

| Prompt | Purpose |
| --- | --- |
| Plan an architecture-aligned change | Guides an agent to retrieve context, state assumptions, identify risk, and propose validation |
| Investigate a production issue | Guides impact, ownership, incident-history, and runbook retrieval |
| Onboard to a team | Guides an agent through systems, dependencies, documents, and suggested first tasks |

### Tools — parameterized read-only retrieval

| Tool | Inputs | Returns |
| --- | --- | --- |
| `get_architecture_context`<br>Get architecture context | Service, repository, or feature identifier | Relevant systems, repos, owners, documents, sources, and bounded graph |
| `assess_change_impact`<br>Assess change impact | Target service/repository plus change summary | Direct/multi-hop dependencies, affected owners, prior incidents, risks, and evidence |
| `trace_technical_decision`<br>Trace a technical decision | Decision, technology, or service | Rationale, alternatives, decision-makers, affected systems, and sources |
| `find_owner_and_expertise`<br>Find owner and expertise | Service/repository/technology | Accountable team, maintainers, experienced contributors, and sources |
| `get_onboarding_context`<br>Get onboarding context | Engineering team or role | Systems, learning path, people, reading, incidents, and sources |
| `search_architecture_evidence`<br>Search architecture evidence | Narrow text query and optional entity type | Ranked source-linked graph entities; not arbitrary database access |
| `trace_change_origin`<br>Trace change origin | Ingested file node id (`repo_<name>::<path>`) | Change history, linked pull request and decision, coupled files, and provenance gaps |
| `assess_file_risk`<br>Assess file risk | Path or prefix plus repository | Tracked files, churn hotspots, contributors, and test-churn signals |
| `get_repo_dependency_impact`<br>Get repository dependency impact | Ingested repository id | Declared dependent repositories and the limits of that evidence |
| `describe_file`<br>Describe a file | Ingested file node id (`repo_<name>::<path>`) | What the file's authors documented, its public symbols, whether that description is current, and whether it was authored or generated |
| `describe_symbol`<br>Describe a declaration | Symbol name, optional file id | Doc comment, signature, kind, container, file, line, and whether the file has drifted since the scan |

The final three tools are the repository-ingest work added in Track A: two
forensics tools and the declaration tools. They use the same response contract
and the same read-only boundary as the six originally specified tools.

## Response contract

Every tool returns structured content containing:

1. A concise summary.
2. Stable entity identifiers and types.
3. Source references for each material claim.
4. A bounded evidence graph: nodes, edges, and readable paths.
5. Risk notes and explicit missing/uncertain information.
6. Suggested validation actions, such as reviewing a linked runbook or testing an affected dependency.

A tool whose answer *is* a declaration carries that detail on its entities — signature, doc comment, kind, container, line, and provenance — rather than returning an identifier and expecting the agent to fetch it again.

## Safety and authorization requirements

- All MCP tools are read-only.
- No tool can write code, files, repositories, deployments, tickets, graph data, or external systems.
- The server never exposes raw Cypher, database credentials, or an arbitrary query executor.
- Tool inputs are validated and translated to parameterized allowlisted graph retrieval.
- Outputs are bounded by traversal depth, result count, and response size.
- Every external client is authenticated and authorized separately from the public demo UI. Until that authorization layer exists, the `/mcp` route mounts **only** when `ENVIRONMENT` is `development`, it is never added to the browser CORS allowlist, and startup fails loudly if `MCP_API_TOKEN` is configured without a verifier.
- Tool descriptions must clearly disclose that results are advisory context, not change approval.
- Access logging records tool name, requested entity identifiers, caller identity, latency, and errors; it excludes secrets and unnecessary source content.

## Implementation notes

- The server uses `mcp.server.mcpserver.MCPServer` (the `FastMCP` name was removed in the 2.x SDK).
- `MCPServer.streamable_http_app()` already routes `/mcp` internally, so it is mounted at the host root and requests for `/mcp` fall through to it. Mounting it *under* `/mcp` would produce `/mcp/mcp`.
- Starlette does not forward lifespan events to mounted applications, so the MCP session-manager lifespan is composed into the host application's lifespan.
- DNS-rebinding protection stays enabled; only loopback hosts and origins are allowed on the development route.
- All eleven tools declare `readOnlyHint` with `destructiveHint` false, and each description carries the advisory-not-approval disclosure.
- Declaration data comes from the ingestion sandbox's tree-sitter pass. The MCP surface reads it only; it never parses source or calls a provider.

## Current surface

| Tools | Resources | Prompts |
| --- | --- | --- |
| 11, all read-only | 4 templates | 3 |

Verified over real JSON-RPC: `initialize`, `tools/list`, `prompts/list`, and `resources/templates/list` all answer, and the browser API continues to serve alongside the mounted MCP app.

## Deployment boundary

Deploy the MCP server as a separately authenticated service on Render, or isolate it behind a dedicated MCP route with equivalent controls. It shares the internal graph-retrieval library with the FastAPI product API but has an independent authorization boundary. The browser never calls the MCP endpoint.

## MVP acceptance checks

1. A compatible coding agent can discover the server's read-only capabilities.
2. It can retrieve context for Checkout or Token Service.
3. A change-impact query returns owners, dependencies, a decision/incident link where available, and sources.
4. No tool accepts or executes arbitrary Cypher or a write action.
5. A response with missing evidence says so explicitly rather than guessing.
6. A question about a named function returns its signature, documentation, file, and line — or states that the declaration carries no doc comment.

## Authentication

The HTTP route requires a bearer token read from `MCP_API_TOKEN` in `.env`.

```bash
# .env -- comma-separated, so a secret can be rotated by running both
MCP_API_TOKEN=old-token,new-token
MCP_ALLOWED_HOSTS=orgatlas.example.com
```

| Environment | `MCP_API_TOKEN` set | Result |
| --- | --- | --- |
| development | no | Mounts open, logs a warning on every start |
| development | yes | Mounts, **requires** the token |
| production | no | **Not mounted.** `/mcp` returns 404 |
| production | yes | Mounts, **requires** the token |

Absent rather than open is the deliberate choice: a context server exposes
decision history, incident records and repository structure, and a route that
exists without a boundary will eventually be reached without one.

**`MCP_ALLOWED_HOSTS` is also required in production.** With DNS-rebinding
protection on and no allowed host, every request is refused. That is the correct
failure but a confusing one, so startup warns about it.

### What the check guarantees

- **Constant-time comparison.** `secrets.compare_digest` for every configured
  token, none short-circuiting, so timing does not reveal the secret or which
  token matched.
- **No token is ever logged** ? not at startup, not on rejection. The startup
  line reports how many tokens are configured, never their values.
- **A rejection is undifferentiated.** An unknown token and a missing header
  produce the same 401, because that distinction is free for an attacker to probe.
- **Every method is covered.** The check is ASGI middleware wrapping the mounted
  app, so a method added to the server later is guarded without anyone
  remembering to add it.
- **Read-only regardless.** Authentication gates *who* may ask; it does not grant
  anything new. Every tool remains read-only.

### What it is not

This is one shared secret, not OAuth 2.1. It suits a single self-hosted server
with one known client. A deployment serving several independent clients needs
per-client credentials, expiry, and revocation, which is a different piece of
work. `StaticTokenVerifier` in earlier drafts of this module wrapped the SDK's
token provider; the shipped implementation is deliberately simpler.

The stdio transport used by local agent hosts is unaffected: it inherits the
user's own filesystem and process permissions and is not reachable over a socket.

---

## Deferred work

- Real authentication and authorization for MCP clients.
- Per-organization tenancy and enterprise identity integration.
- Live repository/issue-tracker synchronization.
- Repository-diff-aware impact analysis.
- Call-graph extraction, so a tool can answer "who calls this" rather than only "where is this declared".
- Automated pull-request review or code editing.
- Change-approval workflow.
