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
| Get architecture context | Service, repository, or feature identifier | Relevant systems, repos, owners, documents, sources, and bounded graph |
| Assess change impact | Target service/repository plus change summary | Direct/multi-hop dependencies, affected owners, prior incidents, risks, and evidence |
| Trace a technical decision | Decision, technology, or service | Rationale, alternatives, decision-makers, affected systems, and sources |
| Find owner and expertise | Service/repository/technology | Accountable team, maintainers, experienced contributors, and sources |
| Get onboarding context | Engineering team or role | Systems, learning path, people, reading, incidents, and sources |
| Search architecture evidence | Narrow text query and optional entity type | Ranked source-linked graph entities; not arbitrary database access |
| Trace change origin | Ingested file node id (`repo_<name>::<path>`) | Change history, linked pull request and decision, coupled files, and provenance gaps |
| Assess file risk | Path or prefix plus repository | Tracked files, churn hotspots, contributors, and test-churn signals |
| Get repository dependency impact | Ingested repository id | Declared dependent repositories and the limits of that evidence |
| Describe a file | Ingested file node id (`repo_<name>::<path>`) | What the file's authors documented, its public symbols, whether that description is current, and whether it was authored or generated |
| Describe a declaration | Symbol name, optional file id | Doc comment, signature, kind, container, file, line, and whether the file has drifted since the scan |

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

## Deployment boundary

Deploy the MCP server as a separately authenticated service on Render, or isolate it behind a dedicated MCP route with equivalent controls. It shares the internal graph-retrieval library with the FastAPI product API but has an independent authorization boundary. The browser never calls the MCP endpoint.

## MVP acceptance checks

1. A compatible coding agent can discover the server’s read-only capabilities.
2. It can retrieve context for Checkout or Token Service.
3. A change-impact query returns owners, dependencies, a decision/incident link where available, and sources.
4. No tool accepts or executes arbitrary Cypher or a write action.
5. A response with missing evidence says so explicitly rather than guessing.

## Deferred work

- Per-organization tenancy and enterprise identity integration.
- Live repository/issue-tracker synchronization.
- Repository-diff-aware impact analysis.
- Automated pull-request review or code editing.
- Change-approval workflow.
