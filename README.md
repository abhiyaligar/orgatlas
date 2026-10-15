# OrgAtlas

> A graph-powered engineering onboarding agent that explains how a SaaS company’s systems work and why key technical decisions were made.

OrgAtlas turns engineers, teams, services, repositories, documents, incidents, and decisions into a connected FalkorDB graph. It helps new engineering hires understand their team’s systems, ownership, dependencies, and essential learning path; it also traces architecture decisions back to the evidence that supports them. A read-only MCP server gives coding agents the same verified architecture context before they plan or change code.

## Stack

| Area | Choice |
| --- | --- |
| Web client | React, TypeScript, Vite, Tailwind CSS, shadcn/ui |
| API | Python and FastAPI |
| Model provider | Nebius, through its OpenAI-compatible API |
| Graph database | FalkorDB Cloud |
| Hosting | Render Static Site (web) and Render Web Service (API) |
| Graph view | Cytoscape.js |
| Coding-agent context | Read-only OrgAtlas MCP server |

## Documentation

Start with the [documentation index](Docs/README.md). The key implementation references are:

- [Product requirements](Docs/PRD.md)
- [System architecture](Docs/ARCHITECTURE.md)
- [FalkorDB design](Docs/FALKORDB.md)
- [Database schema](Docs/DATABASE_SCHEMA.md)
- [Frontend architecture](Docs/FRONTEND_ARCHITECTURE.md)
- [Backend architecture](Docs/BACKEND_ARCHITECTURE.md)
- [MCP server design](Docs/MCP_SERVER.md)

## Scope guardrails

- FalkorDB is the primary system of record for connected company knowledge.
- The model never has direct database access; it can use only approved graph tools.
- Coding agents receive architecture context through read-only MCP tools; MCP never writes code, repositories, or graph data.
- Every substantive answer must show its graph evidence and source documents.
- The first release uses curated fictional company data, not live Slack, GitHub, or customer data.

## Repository conventions

- Keep product and architecture changes synchronized with the relevant file in `Docs/`.
- Record meaningful technical decisions in [ADRs](Docs/DECISIONS.md).
- Update [the API contract](Docs/API_CONTRACT.md) before changing a client/server boundary.
- Update [the schema](Docs/DATABASE_SCHEMA.md) before adding or changing graph labels, properties, or relationships.
