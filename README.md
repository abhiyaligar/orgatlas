# OrgAtlas

> A graph-powered engineering onboarding agent that explains how a SaaS company’s systems work and why key technical decisions were made.

OrgAtlas turns engineers, teams, services, repositories, documents, incidents, and decisions into a connected FalkorDB graph. It helps new engineering hires understand their team’s systems, ownership, dependencies, and essential learning path; it also traces architecture decisions back to the evidence that supports them. An MCP server gives coding agents the same verified architecture context before they plan or change code, and can read the source text of a declaration without the agent re-reading the repository.

It also ingests a real open-source repository. Git history is parsed inside an isolated sandbox, exported declarations are extracted with tree-sitter, and every stored description records whether it was written by the file’s own authors or generated as a fallback. “What does this function do” and “who changed it, and why” are then answered from evidence rather than inference.

## Stack

| Area | Choice |
| --- | --- |
| Web client | React, TypeScript, Vite, Tailwind CSS, shadcn/ui |
| API | Python and FastAPI |
| Graph database | FalkorDB Cloud |
| Repository ingestion | E2B sandbox: git only, no database or model credentials |
| Declaration parsing | tree-sitter, ten grammars, pinned per environment |
| Model provider | Nebius, through its OpenAI-compatible API |
| Hosting | Render Static Site (web) and Render Web Service (API) |
| Graph view | Cytoscape.js |
| Coding-agent context | OrgAtlas MCP server ? 13 read tools, 2 ingest tools behind a write token |
| File bodies | Supabase Storage over its S3-compatible endpoint, content-addressed and commit-pinned |

## Documentation

Start with the [documentation index](Docs/README.md). The key implementation references are:

- [What it is, how it works, why, and use cases](Docs/PRODUCT.md)
- [Product requirements](Docs/PRD.md)
- [System architecture](Docs/ARCHITECTURE.md)
- [FalkorDB design](Docs/FALKORDB.md)
- [Database schema](Docs/DATABASE_SCHEMA.md)
- [Frontend architecture](Docs/FRONTEND_ARCHITECTURE.md)
- [Backend architecture](Docs/BACKEND_ARCHITECTURE.md)
- [MCP server design](Docs/MCP_SERVER.md)
- [Source bodies](Docs/SOURCE_BODIES.md)

## Scope guardrails

- FalkorDB is the primary system of record for connected company knowledge.
- The model never has direct database access; it can use only approved graph tools.
- Coding agents receive architecture context through read-only MCP tools; MCP never writes code, repositories, or graph data.
- Every substantive answer must show its graph evidence and source documents.
- Organisation data is curated and fictional. Repository ingestion reads only public open-source code, clones no dependency repository, and records no credentials inside the sandbox.
- Authored documentation always wins. A generated description is used only where the file's authors wrote nothing usable, and it is labelled as generated with the model, revision, and raw response retained.

## Repository conventions

- Keep product and architecture changes synchronized with the relevant file in `Docs/`.
- Record meaningful technical decisions in [ADRs](Docs/DECISIONS.md).
- Update [the API contract](Docs/API_CONTRACT.md) before changing a client/server boundary.
- Update [the schema](Docs/DATABASE_SCHEMA.md) before adding or changing graph labels, properties, or relationships.

## Getting started

```bash
# Backend
cd backend && python -m venv venv && venv\Scripts\activate   # Windows
pip install -r requirements.txt
python scripts/seed_database.py                               # fixtures -> graph
pytest -q                                                    # test suite

# E2B ingestion template (only needed after changing scanner or parser code)
pip install e2b && python e2b_template.py
```

`data/repos.json` holds the include and exclude filters applied during a scan, and `scripts/prune_graph.py` removes nodes a current filter set would no longer admit. Both are dry-run by default.
