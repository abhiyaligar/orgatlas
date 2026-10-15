# Deployment and environments

## Target deployment

| Component | Platform | Type |
| --- | --- | --- |
| React/Vite client | Render | Static Site |
| FastAPI service | Render | Web Service |
| OrgAtlas MCP server | Render | Separately authenticated Web Service or isolated MCP route |
| Knowledge graph | FalkorDB Cloud | Managed graph database |
| LLM and embeddings (if used) | Nebius | Inference API |

## Environment separation

| Environment | Purpose | Data |
| --- | --- | --- |
| Local | Fast feedback and schema/seed validation | Local or cloud development graph; fictional data only |
| Preview | Optional pull-request checks | Disposable fictional seed data |
| Demo/production | Judge-facing deployment | Stable curated fictional seed data |

## Secret ownership

| Secret/configuration | Stored in |
| --- | --- |
| FalkorDB Cloud connection configuration | Render API service environment variables |
| Nebius API key and selected model | Render API service environment variables |
| Allowed frontend origin | Render API service environment variables |
| MCP authentication/authorization configuration | Render MCP service environment variables |
| Public API base URL | Render Static Site environment/build configuration |

No secrets may be included in the React bundle, source control, screenshots, demo videos, or logs.

## Release checklist

1. Confirm the schema and seed data produce every required demo path.
2. Verify the API health endpoint can reach FalkorDB.
3. Run all planned demo prompts against the deployed graph.
4. Confirm citations and graph highlights match the returned answer.
5. Verify CORS permits only the deployed client origin.
6. Check that the UI has useful loading, empty, and provider-failure states.
7. Verify MCP tools are read-only and return structured citations for every demo query.
8. Record a fallback demo video before submission.

## Operational note

Render credits fund the web and API deployment. FalkorDB Cloud and Nebius are independently managed accounts, so their quotas and keys must be checked separately before the final demo.
