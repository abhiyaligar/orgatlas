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
9. **Code-level follow-up.** Ask the agent to explain a named function in the ingested repository. Show the signature, the doc comment its authors wrote, the file and line, and how often it has changed. Then ask about a function that has no doc comment, and show that OrgAtlas says so rather than inventing an explanation.
10. Show a file whose authors wrote nothing usable at all, and point out that its description is labelled as generated, with the model and revision recorded.
11. Open the **Repositories** view in the browser. Ingest a public repository and let the stage track move from queued through cloning, parsing, and writing to describing and done. Then select it and show the orientation brief, the churn hotspots, a file's history beside its description and provenance, a symbol lookup, and the declared dependencies labelled as manifest-derived rather than resolved.
12. Close by showing that every result is a FalkorDB traversal, not generic document search or ungrounded agent advice.

Steps 9, 10, and 11 are the part judges tend to probe, because "the agent understands the code" is easy to claim and easy to fake. The honest version is: the description came from a doc comment, or it did not exist and we said so. Step 11 matters for the same reason from the product side: the ingestion pipeline is real work, and the browser shows it happening rather than asking anyone to take it on faith.

If the live ingest in step 11 is too slow for the slot, run it before the demo and use the view to walk the already-ingested repository, then say plainly that the run was recorded earlier.

## Required reliable prompts

- Why does Checkout use Kafka instead of synchronous calls?
- Who owns Token Service and which services depend on it?
- What should a new Payments engineer learn in their first week?
- Which incident led to the Kafka decision, and where was it documented?
- Who has relevant experience with the Checkout event pipeline?
- What does this function do, and who has changed it?

## Fallback plan

- Keep a brief screen recording of the complete demo.
- Seed data before the presentation; do not rely on live ingestion.
- Pre-ingest the repository and cache the payload, so a failed sandbox never blocks the demo.
- Have direct links to the deployed app, repository, architecture diagram, and FalkorDB Browser view where permitted.
- If LLM inference fails, show the API's retrieved evidence/source mode to prove graph functionality. Authored documentation and code-level context still work without inference, because neither depends on the model.
