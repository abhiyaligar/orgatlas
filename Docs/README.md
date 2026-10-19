# OrgAtlas documentation

This directory is the source of truth for product and technical decisions. Implementation follows these documents rather than preceding them.

What is currently built is described by the code and its tests rather than by a separate status document, because a status file drifts the moment anything ships. Read `backend/tests/` for what is actually covered.

| Document | Purpose | Update when |
| --- | --- | --- |
| [Product](PRODUCT.md) | What the system is, how it works, why, and what it is for | The framing changes, not the wiring |
| [PRD](PRD.md) | User problem, scope, success criteria, and requirements | Product scope changes |
| [Architecture](ARCHITECTURE.md) | End-to-end system design and data flow | A service or responsibility changes |
| [Frontend architecture](FRONTEND_ARCHITECTURE.md) | React structure, user flows, UI system | A screen, state boundary, or component convention changes |
| [Backend architecture](BACKEND_ARCHITECTURE.md) | API, agent boundaries, orchestration, and safety | A tool, workflow, or server responsibility changes |
| [FalkorDB design](FALKORDB.md) | Why and how FalkorDB is central to the product | Retrieval, graph modeling, or graph operations change |
| [Database schema](DATABASE_SCHEMA.md) | Graph labels, relationships, properties, and constraints | The graph model changes |
| [API contract](API_CONTRACT.md) | Browser-to-API and repository forensics interfaces | A request or response changes |
| [MCP server design](MCP_SERVER.md) | Context tools, resources, prompts, and the read/write safety boundary | An agent capability, authorization boundary, or graph-context contract changes |
| [Source bodies](SOURCE_BODIES.md) | File contents in object storage; the credential boundary and read bounds | The storage provider, upload path, or retrieval bounds change |
| [Documents](DOCUMENTS.md) | Ingesting PDFs, markdown and CSV; verified extraction; decision evidence | A document format, extraction rule, or graph relationship changes |
| [Slack bot](SLACK.md) | Answering questions in a channel, from the same graph the API uses | A Slack behaviour, scope, or safety rule changes |
| [Deployment](DEPLOYMENT.md) | Render/FalkorDB Cloud environments and release checklist | Infrastructure or environment configuration changes |
| [Decisions](DECISIONS.md) | Architecture Decision Records (ADRs) | A material choice is made or reversed |

## Change protocol

1. Describe the intended change in the relevant document.
2. Add an ADR when it changes a significant technology, boundary, or tradeoff.
3. Update affected contracts and schema before implementation.
4. Implement only after documentation and acceptance criteria agree.

## Terminology

- **Evidence path:** the ordered nodes and edges supporting an answer.
- **Source:** a document, ticket, PR, chat extract, or incident record from which a graph fact originated.
- **Decision:** a record of a company choice, its alternatives, rationale, owner, and sources.
- **Onboarding map:** an engineering-role-specific guided view of systems, owners, dependencies, incidents, and reading material.
- **Architecture context:** the source-backed system, dependency, ownership, decision, and change-impact information returned to a coding agent.
- **Declaration:** an exported function, type, or method parsed from source, stored as `CodeSymbol` and reachable through `describe_symbol`.
- **Authored vs generated:** every stored description is one or the other. Authored text came from the file's own documentation; generated text came from the model fallback and records which model, which revision, and at what token cost.

## Surfaces

The same graph answers through several faces. For a given question they return
the same evidence; they differ in who they serve and, in one case, in whether
they may write.

| Surface | Who it is for | Auth | Writes? | Notes |
| --- | --- | --- | --- | --- |
| [HTTP API](API_CONTRACT.md) | The browser, scripts | None yet | No | `/api/ask`, repository forensics, document upload |
| [MCP server](MCP_SERVER.md) | Coding agents | Bearer token | Yes, with a write token | 13 read tools; 2 ingest tools need `MCP_WRITE_API_TOKEN` |
| [Source bodies](SOURCE_BODIES.md) | Agents reading code | Served through MCP | No | Object storage; optional — the graph stays complete without it |
| [Documents](DOCUMENTS.md) | People supplying evidence | Via upload | Yes (writes to the graph) | Extraction is verified against source text |
| [Slack bot](SLACK.md) | People in a channel, agents that only have Slack | Slack tokens | No | Answers on mention; silent elsewhere |
| Frontend | A person exploring | None | No | Onboarding, Ask, Repositories, Graph |

Routing is shared. `AskService.answer()` is the single entry point, and the HTTP
route and the Slack bot are both thin wrappers over it, so the surfaces cannot
drift into disagreeing about what a question means.
