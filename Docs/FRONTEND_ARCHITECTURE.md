# Frontend architecture

## Technical direction

Build a client-side dashboard with **React, TypeScript, Vite, Tailwind CSS, and shadcn/ui**. This is intentionally not a Next.js application: the product does not need SEO or server rendering, while Vite keeps the dashboard workflow simple. The API remains a separate FastAPI service.

## Why shadcn/ui

Yes—use shadcn/ui to move fast. It provides accessible, composable primitives that live in the project rather than locking the app into a remote component runtime. Use it for standard interface patterns; retain custom work for the evidence graph and any distinctive product interaction.

| Use shadcn/ui for | Build/customize separately |
| --- | --- |
| Buttons, inputs, dialogs, sheets, tabs, cards, tables, badges, tooltips, skeletons, toasts | Cytoscape graph canvas, evidence-path highlighting, source-to-node linking |
| Command menu, select/filter controls, scroll areas, empty/error states | Answer-citation interactions and onboarding journey visualization |

## Primary screens

| Screen | Purpose |
| --- | --- |
| Home / Ask | Submit an engineering-context question and browse examples about systems, ownership, dependencies, incidents, and decisions |
| Answer workspace | Read answer, inspect citations, and view selected evidence path |
| Onboarding map | Show a first-week engineering journey: team, services, owners, dependencies, incidents, reading, and first tasks |
| Graph explorer | Inspect the bounded returned subgraph and node details |
| Demo data guide | Explain the fictional organization and available scenarios |

## Layout for the answer workspace

```text
Top bar: OrgAtlas · engineering team context · demo data indicator
Left panel: question history / suggested questions
Main panel: answer, confidence state, sources, follow-up prompts
Right panel: interactive evidence-path graph and selected-node details
```

## State boundaries

| State type | Examples | Location |
| --- | --- | --- |
| Server state | Answers, graph subgraphs, onboarding maps | Query/cache layer at the API boundary |
| Local UI state | Open panels, selected source/node, graph zoom | Component/page state |
| URL state | Active question/session and selected view | Client router/search parameters |

## UI rules

- Display sources beside the claims they support.
- Make graph interaction optional; the answer must remain useful as text.
- Show an explicit data/demo badge so fictional data is never confused with production data.
- Maintain keyboard access, visible focus states, and readable empty/loading/error states.
- Avoid a generic chatbot-only interface; the evidence panel is the product’s signature.
