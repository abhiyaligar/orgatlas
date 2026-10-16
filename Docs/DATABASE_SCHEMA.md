# Database schema — FalkorDB property graph

## Modeling rules

- Every node has a stable `id`, a human-readable `name` or `title`, and source metadata where applicable.
- Every relationship has an `id` or deterministic identity, `source_ids`, and optional confidence/time fields.
- Names are normalized for lookup but display values are preserved.
- The MVP uses one fictional organization graph. Future tenant isolation is represented through an `Organization` root and graph-per-tenant deployment convention.

## Node labels

| Label | Meaning | Essential properties |
| --- | --- | --- |
| Organization | Fictional SaaS company | id, name |
| Team | Organizational team | id, name, mission |
| Person | Employee/contributor | id, name, role, expertise |
| Service | Deployable/internal system | id, name, description, criticality |
| Repository | Source repository | id, name, url |
| Document | Design doc, meeting note, chat extract, runbook | id, title, type, url, excerpt, created_at |
| Decision | Architectural/product choice | id, title, status, summary, decided_at |
| Incident | Operational incident | id, title, severity, summary, occurred_at |
| PullRequest | Change proposal/implementation | id, title, url, merged_at |
| Ticket | Planned or tracked work | id, title, status, url |
| Technology | Tool or platform, such as Kafka | id, name, category |
| OnboardingTopic | A learning step | id, title, sequence, summary |
| Commit | A single revision in an ingested repository | sha, message, author_name, authored_at, additions, deletions, pr_number, repository_id |
| File | A tracked file in an ingested repository | path, language, loc, repository_id, is_test |
| Module | A directory grouping files in an ingested repository | path, repository_id |
| ExternalIdentity | A contributor identity outside the seeded organization | provider, username, email, external_id |

## Relationship types

| Relationship | From → To | Meaning |
| --- | --- | --- |
| HAS_TEAM | Organization → Team | Organization contains a team |
| MEMBER_OF | Person → Team | Person belongs to a team |
| OWNS | Team/Person → Service/Repository/Document | Accountability or stewardship |
| DEPENDS_ON | Service → Service/Technology | Runtime or architectural dependency |
| USES | Service → Technology | Service uses a technology |
| AFFECTS | Decision/Incident/PullRequest → Service | Record affects a service |
| DECIDED_BY | Decision → Person/Team | Decision owner |
| SUPPORTED_BY | Decision → Document/PullRequest/Ticket/Incident | Direct evidence for a decision |
| DISCUSSED_IN | Decision → Document | Decision discussion record. Defined but not exercised by the current seed. |
| LED_TO | Incident → Decision/Ticket | Incident prompted a change or decision |
| IMPLEMENTS | PullRequest/Ticket/Commit → Decision | Change implements a decision |
| PRIMARY_IMPLEMENTATION_OF | Repository → Service | Repository contains the primary implementation of a service |
| CONTRIBUTED_TO | Person → Repository/Service/Incident/Decision | Contributor experience |
| DOCUMENTS | Document → Service/Repository/Decision/Technology | Source describes an entity |
| RECOMMENDED_FOR | OnboardingTopic → Team/Person | Topic is relevant to a team or engineer |
| LEARN_ABOUT | OnboardingTopic → Service/Repository/Document/Technology | Topic directs a learner to material |
| AUTHORED | Person → Document/PullRequest | Person wrote the record |
| TARGETS_REPOSITORY | PullRequest → Repository | Pull request proposes changes to a repository |
| HAS_COMMIT | Repository → Commit | Repository contains a revision |
| MODIFIES | Commit → File | Commit changed a tracked file |
| REVERTS | Commit → Commit | Commit undid an earlier commit |
| HAS_IDENTITY | Person → ExternalIdentity | Seeded employee also known by an external account |
| CODE_OWNS | Person/ExternalIdentity → Repository | Accountable owner from a CODEOWNERS file or contributor record |
| DEPENDS_ON_REPO | Repository → Repository | Repository declares a dependency on another repository |

## Identity resolution for ingested repositories

A commit author is resolved by email before anything is written:

1. Match `Person.email` → the commit is attributed to that seeded employee.
2. Otherwise create an `ExternalIdentity` and attribute the commit through `AUTHORED`.

Raw author emails are **never** stored on `Commit` nodes; they exist only transiently during
resolution and persist solely on `ExternalIdentity`. Real repository contributors are never
fabricated as seeded employees.

## Minimum demo graph

The initial seed should include Payments and Platform teams; 8–12 people; 6–10 services linked to their repositories; one Kafka decision; two incidents; 12–20 documents; a handful of pull requests and tickets; and one Payments onboarding path. This is large enough to prove multi-hop reasoning and coding-agent context, but small enough for deterministic verification.

Ingested repositories are added to the **same** graph rather than to a graph per repository, so that cross-repository traversal over `DEPENDS_ON_REPO` remains possible. Every ingested entity carries a `repository_id` that namespaces it to its source repository.

## Example evidence path in domain terms

For “Why does Checkout use Kafka?”, the graph should support a path such as: Checkout service → uses Kafka; the Kafka decision → affects Checkout; an incident → led to the decision; the decision → is supported by a design document and pull request; named people → decided/implemented it.

For “Who changed this file and why?”, the graph should support a path such as: a file → was modified by a commit → attributed to an identity → that commit implements a decision → the decision is supported by a design document; plus any incident that led to that decision and the runbook that describes recovery.

## Schema-change checklist

Before changing the graph model, update this document, the FalkorDB design, seed-data specification, API contract, and any demo questions that depend on the changed path.
