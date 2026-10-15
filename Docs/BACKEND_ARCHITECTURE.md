# Backend architecture

## Objective

The FastAPI service is a thin, reliable boundary between the React client, FalkorDB Cloud, and Nebius. Its main job is evidence-first retrieval—not open-ended autonomous agency.

## Planned modules

| Module | Responsibility |
| --- | --- |
| API router | Validate requests and serialize responses |
| Intent router | Map a question to an approved retrieval intent |
| Graph service | Execute parameterized FalkorDB queries and map graph records |
| Evidence builder | Assemble sources, claims, and visualization-ready nodes/edges |
| LLM service | Call Nebius with only retrieved evidence and response constraints |
| Ingestion service | Transform curated seed files into the graph |
| Evaluation service | Run expected demo questions and validate cited outputs |
| MCP adapter | Expose only approved architecture-context queries as MCP resources, prompts, and tools |

## Approved retrieval intents

| Intent | Example |
| --- | --- |
| Decision rationale | “Why did we choose Kafka?” |
| Service ownership | “Who owns Token Service?” |
| Dependency impact | “What is affected by changing this service?” |
| Expertise discovery | “Who has worked on this system?” |
| Team onboarding | “What should I learn and who should I meet during my first week?” |
| Source lookup | “Show the documents behind this decision.” |

## Grounding rules

1. The LLM receives only user-safe query context plus retrieved evidence.
2. A claim without a source identifier must be removed or marked uncertain.
3. The system responds with an explicit insufficient-evidence result when retrieval is empty.
4. The LLM cannot create, modify, or directly query graph data.
5. Every response includes the evidence nodes and edges used by the UI.
6. MCP tool results are structured and source-backed; they never return raw unrestricted Cypher capability.

## Error strategy

| Condition | Client outcome |
| --- | --- |
| Invalid question/context | Inline validation message |
| No matching graph evidence | Helpful “no evidence found” response and suggested follow-up |
| Nebius unavailable | Return retrieved facts and sources without a generated narrative |
| FalkorDB unavailable | Clear temporary-error state; do not fabricate an answer |

## Configuration inventory

The server will require a FalkorDB Cloud connection configuration, a graph name, Nebius API credentials/model selection, allowed frontend origin, and environment mode. Exact values belong in Render’s secret environment configuration, never in the repository.

The MCP deployment additionally needs its own authentication/authorization configuration and an allowlist of approved MCP clients or users. It must not reuse the browser’s public access boundary.
