# OrgAtlas documentation

This directory is the source of truth for product and technical decisions. Implementation follows these documents rather than preceding them.

| Document | Purpose | Update when |
| --- | --- | --- |
| [PRD](PRD.md) | User problem, scope, success criteria, and requirements | Product scope changes |
| [Architecture](ARCHITECTURE.md) | End-to-end system design and data flow | A service or responsibility changes |
| [Frontend architecture](FRONTEND_ARCHITECTURE.md) | React structure, user flows, UI system | A screen, state boundary, or component convention changes |
| [Backend architecture](BACKEND_ARCHITECTURE.md) | API, agent boundaries, orchestration, and safety | A tool, workflow, or server responsibility changes |
| [FalkorDB design](FALKORDB.md) | Why and how FalkorDB is central to the product | Retrieval, graph modeling, or graph operations change |
| [Database schema](DATABASE_SCHEMA.md) | Graph labels, relationships, properties, and constraints | The graph model changes |
| [API contract](API_CONTRACT.md) | Planned browser-to-API interfaces | A request or response changes |
| [MCP server design](MCP_SERVER.md) | Read-only context tools, resources, prompts, and safety rules for coding agents | An agent capability, authorization boundary, or graph-context contract changes |
| [Deployment](DEPLOYMENT.md) | Render/FalkorDB Cloud environments and release checklist | Infrastructure or environment configuration changes |
| [Demo plan](DEMO_PLAN.md) | Judge-facing story, seed data, and fallback plan | The demo scenario changes |
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
