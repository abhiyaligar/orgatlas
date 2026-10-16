# Backend architecture

## Objective

The FastAPI service is a thin, reliable boundary between the React client, FalkorDB Cloud, and Nebius. Its main job is evidence-first retrieval—not open-ended autonomous agency.

## Modules

| Module | Responsibility |
| --- | --- |
| API router | Validate requests and serialise responses |
| Graph gateway | Execute parameterised FalkorDB queries and map graph records |
| Evidence service | Assemble sources, claims, and visualisation-ready nodes/edges |
| Ownership / decision / impact / onboarding services | Approved retrieval intents, one per intent |
| Forensics service | Change history, churn, coupling, file descriptions, declarations |
| Provenance service | Trace a commit to its pull request, decisions, and sources |
| Description fallback | Call the model only for files their authors left undescribed |
| LLM service | Call Nebius with only retrieved evidence and response constraints |
| Seed | Transform curated fixture files into the graph |
| Sandbox client | Sync code into the ingestion sandbox, run a scan, download the payload |
| Repository scanner | Runs in the sandbox: clone, parse history, extract documentation and declarations |
| Symbol extractor | tree-sitter grammars; exported declarations with doc comments and positions |
| Describer | Decide the fallback set, call the model, store full provenance |
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
7. Authored text is always preferred. A file with usable `//!`, `///`, headings, tables, or public declarations is described from its own text and is never overwritten by the model.
8. A generated description must record the model, the generation time, the input revision, the trigger, the prompt version, token usage, and the untouched provider response.
9. A failed generation leaves the file undescribed and records the reason. Absence must stay visible.

## Extraction rules

Declaration extraction is parser-backed, not text-matched. A `pub fn` written inside a comment or a string literal is never recorded, because comments and strings are nodes in the grammar rather than text.

Only items on a file's reachable surface are stored: those carrying an explicit `pub`-style visibility, plus members of a public trait, which have no modifier but form that trait's contract. Each language's own rule for internal items is honoured — Java `private` members, C file-local `static` functions, Python and JavaScript underscore-private names, and Go's lowercase-first unexported names are each excluded.

When a grammar is unavailable, the language is not mapped, or a file fails to parse, that file contributes **no** symbols. A missing symbol is recoverable; a wrong one is not.

## Error strategy

| Condition | Client outcome |
| --- | --- |
| Invalid question/context | Inline validation message |
| No matching graph evidence | Explicit "no evidence found" result and suggested follow-up |
| Nebius unavailable | Return retrieved facts and sources without a generated narrative |
| A fallback call fails | File stays undescribed; `docs_error` records the reason |
| FalkorDB unavailable | Clear temporary-error state; do not fabricate an answer |

## Configuration inventory

| Setting | Purpose |
| --- | --- |
| `FALKORDB_*` | Connection configuration and graph name |
| `NEBIUS_API_KEY`, `NEBIUS_API_BASE_URL`, `NEBIUS_MODEL_NAME` | Inference configuration for answer synthesis and the documentation fallback |
| `CORS_ORIGINS` | Allowed browser origin. The MCP route is never added to it |
| `ENVIRONMENT` | Gates whether the `/mcp` route mounts at all |
| `E2B_API_KEY`, `E2B_INGEST_TEMPLATE`, `E2B_SANDBOX_TIMEOUT` | Ingestion sandbox |
| `INGEST_COMMIT_DEPTH`, `INGEST_CACHE_DIR` | Scan depth and payload cache location |

Exact values belong in the service's secret environment configuration, never in the repository. Every Track A setting has no default, so a missing value surfaces as `None` instead of a silent fallback.

The MCP deployment additionally needs its own authentication/authorization configuration and an allowlist of approved MCP clients or users. It must not reuse the browser's public access boundary.
