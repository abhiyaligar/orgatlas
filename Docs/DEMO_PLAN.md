# Demo plan

## One-sentence pitch

“OrgAtlas gives new engineers a company memory: it shows what to learn, who owns each system, how services connect, and why important architecture decisions were made—with the graph path and original evidence visible.”

## Fictional company scenario

Use a fictional SaaS company with Payments and Platform teams. Checkout depends on Token Service and a Kafka event stream. A prior synchronous-call incident led the Payments team to adopt Kafka; the decision is represented by meeting notes, a design document, a ticket, a pull request, an incident, and named owners.

## Live-demo sequence

1. Open the Onboarding map for a new Payments engineer.
2. Show the first-week path: team members, owned services, required reading, and dependencies.
3. Ask: “Why does Checkout use Kafka instead of synchronous calls?”
4. Read the source-backed answer and click a citation.
5. Highlight the graph evidence path from Checkout through the decision and incident to source documents.
6. Ask: “Who should I contact before changing Token Service, and what could be affected?”
7. Connect a coding agent to OrgAtlas MCP and ask for the context needed to change Checkout authentication.
8. Show the returned services, owners, dependency paths, incident/decision history, source documents, and risk/uncertainty notes.
9. Close by showing that every result is a FalkorDB traversal, not generic document search or ungrounded agent advice.

## Required reliable prompts

- Why does Checkout use Kafka instead of synchronous calls?
- Who owns Token Service and which services depend on it?
- What should a new Payments engineer learn in their first week?
- Which incident led to the Kafka decision, and where was it documented?
- Who has relevant experience with the Checkout event pipeline?

## Fallback plan

- Keep a brief screen recording of the complete demo.
- Seed data before the presentation; do not rely on live ingestion.
- Have direct links to the deployed app, repository, architecture diagram, and FalkorDB Browser view where permitted.
- If LLM inference fails, show the API’s retrieved evidence/source mode to prove graph functionality.
