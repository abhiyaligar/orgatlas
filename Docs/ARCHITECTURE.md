# System architecture

## Overview

OrgAtlas has five runtime boundaries: a browser client, a private API/agent service, a read-only MCP server for coding agents, an isolated ingestion sandbox, and FalkorDB Cloud. Nebius is used only by the API service, to synthesise a user's question into a clear answer and to fill documentation gaps the authors themselves left.

```text
Browser: React application
  ├─ Ask question / select onboarding flow
  ├─ Render answer, sources, and graph path
  └─ Call public API over HTTPS
                │
                ▼
Render: FastAPI service
  ├─ Validate request and select approved tools
  ├─ Query FalkorDB using controlled Cypher
  ├─ Build evidence package and graph-path payload
  ├─ Ask Nebius to synthesise a grounded response
  ├─ Orchestrate ingestion and run the description fallback
  └─ Return answer + citations + visualisation data
                │                       │
                ▼                       ▼
      FalkorDB Cloud                  Nebius API
      knowledge graph                 inference only

Coding agent (MCP host)
          │
          ▼
Render: OrgAtlas MCP server
  ├─ Expose architecture-context resources and prompts
  ├─ Execute approved read-only context tools
  └─ Return citations, risk signals, and bounded graph paths
          │
          ▼
     FalkorDB Cloud

Ingestion (on request)
  API ──▶ E2B sandbox: git clone + parse + tree-sitter
           no graph credentials, no model credentials,
           no dependency clones, no submodules
             │
             ▼ payload (metadata + bounded excerpts)
          API ──▶ FalkorDB write, then optional model fallback
```

## Responsibility boundaries

| Boundary | Responsibilities | Must not do |
| --- | --- | --- |
| React client | Interaction, presentation, local UI state, graph rendering | Hold provider/database secrets or query FalkorDB directly |
| FastAPI | Input validation, retrieval, tool selection, response grounding, ingestion orchestration, description fallback | Return uncited claims or expose unrestricted database queries |
| MCP server | Give coding agents source-backed architecture context through approved read-only tools | Write code, alter repositories/deployments, or expose arbitrary Cypher |
| Ingestion sandbox | Clone one public repository, parse its history, extract declarations | Receive graph or model credentials; clone dependency repositories; touch the graph |
| FalkorDB Cloud | Persistent graph, traversal, indexes, and source relationships | Generate natural-language answers |
| Nebius | Grounded answer synthesis and documentation fallback for undescribed files | Connect to the graph or receive credentials from the client |

## Request flow

1. The client submits a question and optional team/person context.
2. The API classifies the request into an approved retrieval intent.
3. The API executes parameterised, intent-specific graph queries.
4. The API converts result records into an evidence package: claims, source references, and a bounded subgraph.
5. Nebius produces a concise answer only from that package.
6. The API validates the response includes cited evidence and returns it with graph-rendering data.

## Coding-agent MCP flow

1. A compatible coding agent connects to the OrgAtlas MCP server.
2. It requests a specific context tool, such as change impact, decision rationale, or the description of a function.
3. The MCP server validates input and executes the same approved, parameterised graph retrieval layer as the API.
4. The server returns structured, bounded evidence: relevant systems, repositories, owners, dependency paths, decisions, incidents, sources, and uncertainty.
5. The coding agent uses this context in its own planning and implementation workflow. Any code-edit approval remains with the MCP host and the user.

## Ingestion flow

1. The API resolves the include and exclude filters for the target repository and passes only those to the sandbox.
2. The sandbox clones that one repository, with no submodules, and parses its git log.
3. Files outside the filters are dropped before any node or edge is created, so excluded paths never reach the graph.
4. Each retained file is read once: authored documentation and exported declarations are extracted from its own text, and the revision is recorded with both.
5. The API writes nodes and edges in batches.
6. Files whose authors wrote nothing usable ship a bounded excerpt; the API decides whether to call the model and records the full provenance of anything generated.
7. Dependency edges come from manifest text only. No dependency repository is cloned or ingested.

## Documentation provenance

Every stored description is attributable. `docs_source` records whether the text came from the file's own `//!`/`///` comments, from its declarations, from a structured format, from the model, or not at all. Generated text additionally records the model, generation time, input revision, trigger, prompt version, token usage, and the untouched provider response, so any answer can be traced back to the revision it describes. A failed generation leaves the file undescribed and records why, rather than presenting a gap as an answer.

## Security principles

- Store FalkorDB and Nebius credentials only as Render server environment variables.
- Permit browser access only to the API's public, documented endpoints.
- Use parameterised graph queries and an allowlist of retrieval tools.
- Keep the MCP surface read-only, least-privileged, rate-limited, and separately authenticated from the browser demo.
- Give the ingestion sandbox no credential of any kind.
- Log request metadata and failures; never log secrets.
- Use fictional seed data for the organisation graph, and only public open-source code for ingestion.
