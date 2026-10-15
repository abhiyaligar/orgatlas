# System architecture

## Overview

OrgAtlas has four runtime boundaries: a browser client, a private API/agent service, a read-only MCP server for coding agents, and FalkorDB Cloud. Nebius is used only by the API service to convert a user request and verified graph evidence into a clear response.

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
  ├─ Ask Nebius to synthesize a grounded response
  └─ Return answer + citations + visualization data
                │                       │
                ▼                       ▼
     FalkorDB Cloud                  Nebius API
     knowledge graph                 LLM inference only

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
```

## Responsibility boundaries

| Boundary | Responsibilities | Must not do |
| --- | --- | --- |
| React client | Interaction, presentation, local UI state, graph rendering | Hold provider/database secrets or query FalkorDB directly |
| FastAPI | Input validation, retrieval, tool selection, response grounding, ingestion orchestration | Return uncited claims or expose unrestricted database queries |
| MCP server | Give coding agents source-backed architecture context through approved read-only tools | Write code, alter repositories/deployments, or expose arbitrary Cypher |
| FalkorDB Cloud | Persistent graph, traversal, indexes, and source relationships | Generate natural-language answers |
| Nebius | Structured tool selection and grounded answer synthesis | Connect to the graph or receive credentials from the client |

## Request flow

1. The client submits a question and optional team/person context.
2. The API classifies the request into an approved retrieval intent.
3. The API executes parameterized, intent-specific graph queries.
4. The API converts result records into an evidence package: claims, source references, and a bounded subgraph.
5. Nebius produces a concise answer only from that package.
6. The API validates the response includes cited evidence and returns it with graph-rendering data.

## Coding-agent MCP flow

1. A compatible coding agent connects to the OrgAtlas MCP server.
2. It requests a specific context tool, such as change impact or decision rationale.
3. The MCP server validates input and executes the same approved, parameterized graph retrieval layer as the API.
4. The server returns structured, bounded evidence: relevant systems, repositories, owners, dependency paths, decisions, incidents, sources, and uncertainty.
5. The coding agent uses this context in its own planning and implementation workflow. Any code-edit approval remains with the MCP host and the user.

## Data ingestion flow

1. Curated fictional source files are parsed into normalized entities.
2. Entity names and stable identifiers are resolved.
3. Nodes and relationships are created or updated in FalkorDB.
4. Every derived relationship retains its source and confidence metadata.
5. Seed verification checks expected nodes, edges, and key demo paths.

## Security principles

- Store FalkorDB and Nebius credentials only as Render server environment variables.
- Permit browser access only to the API’s public, documented endpoints.
- Use parameterized graph queries and an allowlist of retrieval tools.
- Keep the MCP surface read-only, least-privileged, rate-limited, and separately authenticated from the browser demo.
- Log request metadata and failures; never log secrets.
- Use fictional seed data for the hackathon.
