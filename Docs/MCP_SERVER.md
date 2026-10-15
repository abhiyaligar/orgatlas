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
- Every external client is authenticated and authorized separately from the public demo UI.
- Tool descriptions must clearly disclose that results are advisory context, not change approval.
- Access logging records tool name, requested entity identifiers, caller identity, latency, and errors; it excludes secrets and unnecessary source content.

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
