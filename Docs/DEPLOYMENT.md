# Deployment and environments

## Target deployment

| Component | Platform | Type |
| --- | --- | --- |
| React/Vite client | Render | Static Site |
| FastAPI service | Render | Web Service |
| OrgAtlas MCP server | Render | Separately authenticated Web Service or isolated MCP route |
| Knowledge graph | FalkorDB Cloud | Managed graph database |
| LLM and embeddings | Nebius | Inference API |
| Repository ingestion | E2B | Ephemeral sandbox per scan, killed when finished |

## Environment separation

| Environment | Purpose | Data |
| --- | --- | --- |
| Local | Fast feedback and schema/seed validation | Local or cloud development graph; fictional organisation data |
| Preview | Optional pull-request checks | Disposable fictional organisation data |
| Demo/production | Judge-facing deployment | Stable curated fictional organisation data |

## Secret ownership

| Secret/configuration | Stored in |
| --- | --- |
| FalkorDB Cloud connection configuration | Render API service environment variables |
| Nebius API key and selected model | Render API service environment variables |
| E2B API key and template id | Render API service environment variables |
| Allowed frontend origin | Render API service environment variables |
| MCP authentication/authorization configuration | Render MCP service environment variables |
| Public API base URL | Render Static Site environment/build configuration |

No secrets may be included in the React bundle, source control, screenshots, demo videos, or logs. The ingestion sandbox receives **no** credential of any kind: it clones and parses, and the API process performs every graph write and every provider call.

## Ingestion image

The sandbox template is built by `e2b_template.py` and is referenced by `E2B_INGEST_TEMPLATE`. It supplies the operating system, git, Python, and the pinned tree-sitter grammars. Grammar versions live in `tree_sitter_deps.py` and are shared with `backend/requirements.txt`, so the image and the local environment cannot diverge.

Two consequences worth knowing:

- **Rebuild the template after changing anything the scanner imports.** The application package is uploaded into each sandbox at run time, but third-party packages are baked in at build time. A build-time smoke test constructs and parses with every grammar, so a template that cannot extract symbols fails to build rather than silently reporting none.
- **Build to a new name before switching.** `TEMPLATE_NAME` in `e2b_template.py` names the built image. Change it, verify, then update `E2B_INGEST_TEMPLATE`, so the working template survives a failed build.

## Operational notes

- FalkorDB Cloud caps a result set at 10,000 rows. Bulk work uses keyset pagination or predicate-based deletion rather than enumerating and deleting row by row.
- `FLUSHDB` is not available to the configured FalkorDB Cloud user. A full clean drops the graph with the client's graph-level delete and recreates it.
- A scan is a one-shot on request. The payload cache is written for inspection but is not read back, so a re-ingest always pays for a fresh sandbox run.

## Release checklist

1. Confirm the schema and seed data produce every required demo path.
2. Verify the API health endpoint can reach FalkorDB.
3. Run all planned demo prompts against the deployed graph.
4. Confirm citations and graph highlights match the returned answer.
5. Verify CORS permits only the deployed client origin, and that the MCP route is absent from it.
6. Check that the UI has useful loading, empty, and provider-failure states.
7. Verify MCP tools are read-only and return structured citations for every demo query.
8. Confirm the ingestion template is current and its grammar smoke test passed at build time.
9. Record a fallback demo video before submission.
