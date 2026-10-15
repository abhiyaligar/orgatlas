# API contract (planned)

This document describes product-facing interfaces, not implementation code. All endpoints are served by FastAPI over HTTPS and exchange JSON.

The coding-agent interface is specified separately in [MCP server design](MCP_SERVER.md); it is not a browser REST API.

## Endpoint inventory

| Operation | Purpose | Response must include |
| --- | --- | --- |
| Ask question | Answer a relationship-based company question | Answer, citations, evidence path, graph subgraph, follow-ups |
| Get onboarding map | Generate/read an engineering team onboarding guide | Ordered topics, relevant people/services, sources, graph subgraph |
| Get entity details | Inspect a selected graph entity | Entity summary, connections, ownership, sources |
| Get demo prompts | List reliable questions for the seeded graph | Prompt text, intent, expected entities |
| Health check | Confirm API and graph connectivity | Service health only; no secrets |

## Ask-question request fields

| Field | Required | Description |
| --- | --- | --- |
| question | Yes | Natural-language user request |
| context | No | Selected team, service, repository, person, or engineering role |
| session_id | No | Client-side conversation grouping identifier |

## Ask-question response fields

| Field | Description |
| --- | --- |
| answer | Grounded natural-language response |
| evidence_summary | Human-readable explanation of why the answer is supported |
| citations | Source identifiers, titles, types, and links/excerpts |
| graph | Bounded visualization-ready nodes and edges |
| confidence | Supported, partial, or insufficient evidence |
| suggested_questions | Relevant next questions |

## Contract rules

- Never expose connection strings, provider keys, raw stack traces, or arbitrary Cypher execution.
- Keep graph payloads bounded; return only the answer-relevant subgraph.
- Preserve stable identifiers so the UI can select a citation and highlight its graph node.
- Version the API before making breaking changes.
