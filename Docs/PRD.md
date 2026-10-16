# Product requirements document — OrgAtlas

## 1. Product summary

OrgAtlas is an AI engineering onboarding and knowledge agent for SaaS teams. It combines an engineering onboarding navigator with a decision archaeologist: new hires learn their team’s systems, ownership, dependencies, incidents, and essential reading, then trace key architecture decisions through the evidence that informed them.

It also exposes the same verified context through Model Context Protocol (MCP), so coding agents can check architectural boundaries and likely change impact before proposing or making code changes.

## 2. Problem

Engineering knowledge is fragmented across repositories, architecture documents, tickets, pull requests, incidents, chats, and people. New engineers struggle to understand a team’s systems and dependencies; established engineers struggle to reconstruct why an architecture decision was made. Traditional search returns disconnected documents and cannot reliably answer relationship-driven questions.

## 3. Target users

| User | Primary need |
| --- | --- |
| New engineer | Learn their team’s domain, services, owners, dependencies, incidents, and essential reading |
| Existing engineer | Investigate the rationale, impacts, and current ownership of an architecture decision |
| Engineering lead | Give new hires consistent system context and find expertise across teams |

## 4. Core user journeys

### Decision archaeology

A user asks: “Why does Checkout use Kafka instead of synchronous calls?” OrgAtlas returns the answer, rationale, alternatives considered, decision owner, supporting sources, and a visual evidence path.

### Onboarding navigation

A user asks: “I joined Payments. What should I learn in my first week, which services do we own, and who should I meet?” OrgAtlas generates a role/team-specific path containing systems, key people, dependencies, prior incidents, and ranked reading.

### Ownership and impact discovery

A user asks: “Who owns Token Service, what depends on it, and whom should I contact before changing it?” OrgAtlas traverses the graph and returns an explainable path.

### Coding-agent architecture guardrail

A coding agent asks: “I plan to change Checkout authentication. What services, owners, dependencies, prior incidents, and decisions are relevant?” OrgAtlas returns a bounded, cited architecture-context package. The coding agent uses this information to plan safely; OrgAtlas does not write code or approve a change.

## 5. MVP requirements

1. Search/ask interface for natural-language questions.
2. Engineering onboarding map covering a team’s systems, ownership, dependencies, incidents, and first-week tasks.
3. Controlled graph retrieval for architecture decisions, ownership, dependencies, incidents, repositories, and sources.
4. An answer panel containing citations and an evidence-path explanation.
5. Interactive graph visualization for the selected evidence path.
6. Curated seed dataset representing a fictional SaaS engineering organization across at least two teams.
7. Clear empty/error states and a reproducible demo flow.
8. Read-only MCP tools that give compatible coding agents architecture context, ownership, change impact, decision rationale, and source references.
9. Repository ingestion that turns one real public repository into answerable change history: who changed a file, when, through which pull request, and what else changes with it.
10. Function-level context parsed from source, so "what does this function do" returns a signature, the documentation its authors wrote, its file and line — or states plainly that it carries no doc comment.

## 6. Non-goals for the hackathon MVP

- Production Slack, GitHub, Jira, Notion, or Google Drive integrations. **Superseded in part by [ADR-010](DECISIONS.md#adr-010-ingest-real-repository-code-into-the-knowledge-graph)**, which admits one-shot ingestion of real public GitHub repositories into the knowledge graph. Other integrations and all write-back remain out of scope.
- Authentication, organization administration, billing, or role-based access management.
- Autonomous actions that modify external systems.
- Unrestricted LLM-generated Cypher.
- MCP tools that write source code, alter repositories, trigger deployments, or modify graph data.
- Enterprise-scale ingestion and real customer/company data.

## 7. Success criteria

| Area | Success condition |
| --- | --- |
| Graph centrality | At least three demo questions require multi-hop graph traversal to answer correctly |
| Explainability | Every answer exposes sources and a human-readable evidence path |
| Onboarding value | A demo user can reach services, owners, dependencies, incidents, and reading materials from one onboarding query |
| Reliability | The planned demo questions work from a clean deployment with deterministic seeded data |
| FalkorDB use | FalkorDB stores the central knowledge graph and directly powers retrieval and explanation |
| Agent usefulness | A coding agent receives a source-backed change-context package for each planned demo change |
| Code-level usefulness | A named function resolves to its signature, authored documentation, file, and line, or an explicit statement that it is undocumented |
| Provenance honesty | Every stored description is attributable to authored text or to a named model revision, never blurred together |

## 8. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| LLM invents unsupported statements | Answer only from tool-returned evidence; require sources; allow “insufficient evidence” |
| Free-tier graph capacity is limited | Use a compact curated dataset and defer vector indexing |
| Graph is hard to understand visually | Visualize only the selected evidence path, not the full graph |
| Live demo network failure | Prepare a screen recording and maintain a local development fallback |
| A generated summary is mistaken for the authors' own words | Authored documentation always wins; generated text is labelled with model, revision, and usage, and a failed generation leaves the gap visible |
| Extraction invents a declaration that does not exist | Parse with tree-sitter rather than matching text, and return no symbols at all for a file that fails to parse |
