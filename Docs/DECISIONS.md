# Architecture Decision Records

Record decisions that materially affect product scope, technology, or system boundaries. New entries should use the format: context, decision, consequences, and status.

## ADR-001: Use FalkorDB Cloud as the primary graph store

- **Status:** Accepted
- **Context:** The hackathon requires FalkorDB to be central to the project. Managed cloud hosting reduces setup time and enables a shareable demo.
- **Decision:** Store the OrgAtlas knowledge graph in FalkorDB Cloud. The backend is the only service that connects to it.
- **Consequences:** Faster deployment and persistence for the demo; external service availability and free-tier capacity must be considered. A compact curated dataset avoids memory pressure.

## ADR-002: Use React/Vite rather than Next.js

- **Status:** Accepted
- **Context:** OrgAtlas is an authenticated/dashboard-style experience with no MVP SEO or server-rendering requirement.
- **Decision:** Use React, TypeScript, Vite, Tailwind CSS, and shadcn/ui for the browser client; keep the API as a separate FastAPI service.
- **Consequences:** A simpler UI workflow and independent deployment; the project must manage CORS and cannot use Next.js API routes.

## ADR-003: Make responses evidence-first

- **Status:** Accepted
- **Context:** The product’s value and the hackathon brief both require decision traceability.
- **Decision:** Restrict model interaction to approved backend tools, require citations in answers, and return the graph subgraph behind every substantive response.
- **Consequences:** More predictable demos and clearer trust boundaries; more up-front schema and retrieval design.

## ADR-004: Use shadcn/ui for standard interface primitives

- **Status:** Accepted
- **Context:** The project needs a polished accessible UI within hackathon time constraints.
- **Decision:** Adopt shadcn/ui for standard primitives and reserve custom implementation for the graph/evidence experience.
- **Consequences:** Faster visual consistency; project-owned components still need disciplined design-token and accessibility upkeep.

## ADR-005: Support onboarding for every employee, not only developers

- **Status:** Superseded by ADR-006
- **Context:** Every new employee needs company purpose, customer, organization, process, policy, and role context. Technical onboarding alone would make the product narrower and less representative of a true company brain.
- **Decision:** Make universal onboarding the primary product journey. Engineering systems and technical-decision archaeology remain rich specialized paths within the same graph.
- **Consequences:** The seed graph and onboarding experience span multiple departments and include customers, products, processes, policies, roles, and decisions. The MVP remains bounded by using curated fictional data.

## ADR-006: Focus the hackathon MVP on engineering onboarding

- **Status:** Accepted
- **Context:** Universal employee onboarding is a valid future direction, but it broadens the seed data, user journeys, and graph model beyond what is needed for a strong hackathon submission.
- **Decision:** Focus OrgAtlas on new engineering hires at a SaaS company. The core graph covers engineers, teams, services, repositories, pull requests, incidents, documents, technologies, and architecture decisions.
- **Consequences:** The product has a sharp user, deterministic demo questions, and naturally graph-shaped evidence paths. Broader company onboarding is explicitly deferred as a future extension.

## ADR-007: Expose read-only architecture context through MCP

- **Status:** Accepted
- **Context:** Coding agents often lack the repository, dependency, ownership, incident, and decision context needed to make architecture-aligned changes. Giving them arbitrary database access or write capabilities would be unsafe and unnecessary.
- **Decision:** Expose a dedicated, read-only OrgAtlas MCP server. It provides approved architecture-context resources, prompts, and tools backed by the same controlled FalkorDB retrieval layer as the browser API.
- **Consequences:** Compatible coding agents can ground planning and implementation in verified architecture context. The server must enforce separate authentication, input validation, bounded results, citations, and no-write tool policy.

## ADR-008: Mandatory Alembic Migrations

- **Status:** Accepted
- **Context:** The relational metadata store (audit logs, session context, ingest jobs) is migrated by more than one process — the application at startup and the seed workflow before ingestion. Ad-hoc `CREATE TABLE` or raw SQL execution diverges silently between those callers and leaves no version record.
- **Decision:** All relational and metadata schema evolution, table creation, and schema-level data migrations must run through Alembic (`alembic upgrade head`). Direct SQL migration is prohibited unless Alembic is demonstrably incapable of the operation, and that exception must be recorded as an ADR.
- **Consequences:** A single ordered migration history, reproducible from any checkout. Schema changes require a migration file, which adds a small step to every change to the relational model.

## ADR-009: Strict Read-Only MCP Context Boundary

- **Status:** Accepted
- **Context:** The MCP surface is reachable by external coding agents. Giving an agent arbitrary Cypher, shell execution, or graph mutation would breach the same boundary the browser API holds, through a less supervised path.
- **Decision:** MCP tools are context providers only. The surface exposes no tool that writes files, edits code, executes shell commands, mutates tickets or repositories, or writes to the graph or any database. Inputs are validated and translated to parameterised allowlisted retrieval; outputs are bounded by traversal depth, result count, and response size. Tool descriptions must state that results are advisory context, not change approval.
- **Consequences:** Agents can ground their planning but cannot act through OrgAtlas. Adding any capability later requires a new ADR rather than a code change.

## ADR-010: Ingest Real Repository Code Into the Knowledge Graph

- **Status:** Accepted
- **Summary of Scope:** Supersedes the GitHub-integration non-goal in `PRD.md` §6.
- **Context:** The product answers "who changed this, and why did it change" from a graph of services, decisions, incidents, and documents. Those records describe *intent*, but not the *change history* that produced them. Ingesting a real repository makes change forensics answerable from evidence rather than inference, and gives the MCP surface a grounded answer to "what changed here and what broke".
- **Decision:** Ingest real public repositories into the existing FalkorDB property graph — one graph, with `Repository` as a root node and all code entities namespaced by `repository_id`. Ingestion is one-shot on connect, delegated to an isolated E2B sandbox that clones and parses only; the API process owns every database write and retains all credentials. Commit authors resolve to a seeded `Person` on email match and otherwise to a new `ExternalIdentity`; raw emails are never stored on `Commit` nodes and real contributors are never fabricated as employees.
- **Consequences:** The product gains a genuine "why" and "who" dimension grounded in real history, and cross-repository impact becomes traversable via `DEPENDS_ON_REPO`. It also introduces a new external dependency (E2B), an ingestion job lifecycle to operate, and unbounded repository input that must be bounded by depth and path limits. Note that ingested history does **not** retroactively implement the seeded fictional decisions, so forensics over real repositories are strong on "who and what changed" and weak on "why" until commits are linked to decisions.

## ADR-011: Parse Declarations With tree-sitter, Not Pattern Matching

- **Status:** Accepted
- **Context:** To answer "what does this function do", the graph needs declarations rather than filenames. The first implementation found them with a line-anchored regular expression, which cannot distinguish a declaration from the same text written inside a comment or a string literal. That defect is invisible at file level, where a wrong symbol name is harmless, and unacceptable at symbol level, where it would create phantom nodes that an agent would then treat as real API.
- **Options considered:** `rustdoc --output-format json` is nightly-only and would resolve dependencies, downloading crates, which the ingestion sandbox is explicitly forbidden from doing. `cargo metadata` yields packages rather than symbols. universal-ctags is regex-based underneath and so shares the original defect. A larger hand-written scanner would still have to track comments and strings by hand.
- **Decision:** Parse with tree-sitter, using a per-language grammar, and record only items on a file's reachable surface: those carrying an explicit `pub`-style visibility, plus members of a public trait, which have no modifier but form that trait's contract. Documentation attaches by walking real comment siblings, requires an outer doc marker so module-level `//!` is not attributed to the first item, and stops at a blank line. Each language's own rule for internal items is honoured. When a grammar is unavailable, the language is unmapped, or a file fails to parse, the file contributes no symbols rather than a partial list.
- **Consequences:** A declaration written inside a comment or string is now structurally impossible. Extraction costs no extra I/O because it reuses the read the scan already performs, and no model call. The cost is a third-party dependency in the ingestion image, which is installed at template build time from one pinned list shared with `requirements.txt` and verified by a smoke test during the build. Only Rust is verified against real repository files; the other nine grammars are verified against minimal snippets, so an unverified language yields missing symbols rather than wrong ones. Public trait members are included, which materially raises the symbol count above a plain `pub` scan would.

## ADR-012: Generate Documentation Only For Files Their Authors Left Undescribed

- **Status:** Accepted
- **Context:** A meaningful share of real source files carry no prose documentation at all. Those files would otherwise return nothing useful, which invites an agent to guess from the name. Generating a summary everywhere would be worse: it would overwrite the authors' own words with a model's paraphrase of them.
- **Decision:** Extraction prefers authored text, in order: a module's `//!` or `/*! */` inner documentation, then the `///` block on its first public item, then the public declarations themselves, then the structure of a Markdown, TOML, or YAML file. The model is consulted only for files where all of those yield nothing. It never runs for individual declarations; an undocumented function stays undocumented and is reported as such. Each generated description records the model, generation time, input revision, trigger, prompt version, token usage, and the untouched provider response. A failed call leaves the file undescribed and records the reason, so a gap stays visible instead of being quietly filled. A fresh scan clears every model-owned field, so a re-ingest can never inherit a previous model's answer.
- **Consequences:** Every stored description is attributable, and a reader can always tell authored text from generated text. Documentation gaps remain honest rather than being papered over. The fallback is deliberately small: on the seeded repository it covers four files. Because the configured model is a reasoning model that spends completion tokens before answering, the completion allowance must leave real headroom, and thinking tokens must be reported because they dominate the cost.
## ADR-013: Give MCP A Second, Write-Scoped Token Rather Than One Shared Secret

- **Status:** Accepted
- **Context:** ADR-009 made the context server strictly read-only, and for good reason: the first time an agent asks the knowledge graph what it is about to change, the graph is the thing it will change next. An ingest is the one operation that genuinely has to happen during an agent session, though, and forcing it back through a browser meant the token promised by that session could not do the job it was handed it for. Widening the single shared token to cover writes would have quietly undone ADR-009: every read-only agent, every client configured with the documented `Bearer` header, would inherit the ability to rewrite the graph.
- **Options considered:** Grant writes to `MCP_API_TOKEN` and rely on documentation. Rejected: it makes the blast radius of every token equal to the blast radius of the server, and there is no configuration under which a leaked read token is merely a leak. Run the ingest as a second MCP server on a second port. Rejected: two surfaces means two mounts, two audit paths, and a client that has to be told which of its configured endpoints can write. Keep the token and reject the request. Rejected: it preserves a boundary the product needs broken.
- **Decision:** Two independent secrets. `MCP_API_TOKEN` grants the eleven retrieval tools and nothing else. `MCP_WRITE_API_TOKEN` grants `ingest_repository` and `get_ingest_job`, and also reads, so a single credential can drive an agent end to end. With no write token configured the server mounts read-only rather than refusing to mount, so an unconfigured deployment is merely limited. The route's existing fail-closed behaviour is unchanged: with neither token, `/mcp` still does not mount in production. Scope is resolved once in the ASGI middleware and published in a `ContextVar`; each write tool re-checks it on entry, so the guard holds even if a tool is reached without passing through HTTP. No scope in context is treated as no write.
- **Consequences:** A read-only credential is now meaningfully weaker than a write one, which is the point, and it can be issued to a tool that only needs to look at things. Rotation is independent per token. The cost is a second secret to manage and a failure mode where a caller has a valid write token that is refused as unreadable elsewhere; the startup log reports only how many tokens are configured, never their values, so that failure is diagnosed by re-issuing rather than by reading a log. The tools declare `readOnlyHint: false` and `destructiveHint: true`, because an ingest replaces what the previous scan left for that repository, so a client that trusts the annotation asks a human first. Writes are attributed: an `audit_logs` row records the trigger with `caller_type = 'mcp_agent'`, which distinguishes an agent-initiated ingest from the identical job started over REST.
