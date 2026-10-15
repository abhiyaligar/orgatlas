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
