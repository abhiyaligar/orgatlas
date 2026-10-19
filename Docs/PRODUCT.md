# Product

What OrgAtlas is, how it works, why it is built this way, and what it is for.
This document is deliberately free of implementation detail — that lives in
[Architecture](ARCHITECTURE.md) and [FalkorDB](FALKORDB.md). It is the document to
read when asking "what is this for" rather than "how is it wired".

---

## What

**A knowledge graph holding the context a coding agent cannot cheaply derive.**

Every agent session starts from zero. It opens the repository, rediscovers what
it learned last week, and the same tokens are paid for again. The code did not
change — the session did.

OrgAtlas sits outside the session. Ingest a repository once, and any harness —
Cursor, an editor, a script — calls one interface and gets architecture context
back, cited.

It holds the **why**. Not what the code says: that is in the repository and git
already serves it well. *Why it is that way*, who decided, what broke, who owns
it, and where the reasoning is recorded. Those answers are spread across commit
history, design documents, incident write-ups and chat, and no single one of
those systems contains the answer on its own.

---

## How

**Ingest once → resolve → traverse → cite.**

### 1. Ingest

Repositories are parsed for structure, history and declarations. Documents are
parsed for decisions, rationale and dissent. Chat is parsed for the discussion
where something was settled and the objections raised.

Every entity becomes a typed node with a stable id. Every relationship becomes a
typed edge. File bodies are stored as immutable, content-addressed objects;
the graph holds pointers to them, the line ranges of each declaration, and the
commit revision each description was written against.

Ingest is idempotent by construction. Every write merges on a stable id, so a
second scan updates what it revisits rather than duplicating it.

### 2. Resolve

The question is mapped onto a graph entity — the service, the decision, the
declaration, the file.

**The label of whatever it resolves to chooses the retrieval.** This matters more
than it sounds: a resolved node that the question used verbatim can route on its
own, but a fragment of a longer name cannot. The word "rate" inside "churn rate"
must not send the agent to *"Rate limit one-time passcode sends"*. Label-directed
routing is what makes that impossible rather than merely unlikely.

### 3. Traverse

Facts come from the subgraph around the resolved entity: the declaration, the
commit that changed it, the decision it implements, the incident behind that
decision, the people who did the work.

Retrieval is bounded. A call cannot flood an answer, a file read cannot download
a whole repository, and a truncated result says it was truncated.

### 4. Cite

Every claim carries its source, its revision, and a confidence grade. Retrieved
source is marked untrusted, because repository content is data and may contain
text aimed at the model reading it.

Retrieval is **intent-scoped**: a question that resolves nothing returns
nothing, and says so.

---

## Why

### Why a graph, and not search

| | |
| --- | --- |
| **Relationships are first-class** | Commit → implements → Decision → caused_by → Incident is one traversal, not four searches a reader must correlate by hand. |
| **Memory outlives the session** | Discovery is paid once at ingest, not re-paid by every session that touches the repository. |
| **Provenance is structural** | A claim that cannot name its source cannot be made. This is a property of the model, not a discipline bolted on afterwards. |
| **Cross-system by construction** | Repository, documents, incidents and chat are joined. The answer lives in the join. |
| **Refusal is a first-class answer** | "Insufficient evidence" is a result the system is built to produce, not a failure it tolerates. |

### The deepest reason

An agent acting on wrong architecture context is **worse** than an agent with
none. Fluency without provenance is the failure mode of every tool an agent
calls. Building the system so that absence is reportable, and so that every claim
carries where it came from, is the point — not a feature added to the list.

### What this is not

It is not a cheaper git. Measured on a real repository, git answers *"who changed
this file"* for a fraction of the tokens, and will continue to: git returns nine
clean lines where a graph tool returns entities, citations, a subgraph and a
revision pin. That is not a defect, it is the cost of provenance, and it is worth
paying where the answer is architectural rather than textual.

What git cannot do is answer *"why is it built this way"*, because the answer is
not in the repository.

---

## Use cases

| # | Question it answers | Who asks |
| --- | --- | --- |
| 1 | **Onboarding** — where do I start in this area? Volatile files, owners, what to read first. | New engineer or agent |
| 2 | **Change safety** — what breaks if I change this? Blast radius, dependents, who is affected, which decisions constrain it. | Engineer before a change |
| 3 | **Decision archaeology** — why is it built this way? The decision, the rationale, the incident that forced it, the discussion where it was settled. | Anyone inheriting a system |
| 4 | **Ownership** — who owns this, and who has actually worked on it? Derived from history and documents, not a stale README. | New team member, agent |
| 5 | **Agent memory** — one endpoint, every harness, identical answers, because they come from the graph rather than a transcript. | Tooling |
| 6 | **Documentation drift** — documentation written against an older revision, flagged while the diff is still open. | Reviewer |
| 7 | **First-session competence** — an agent that has never seen the repository can ask architectural questions immediately. | Agent, in its first session |

---

## The one sentence

git tells you what changed. OrgAtlas tells you **why it is like that**, who
decided, and what happens if you touch it — and it either cites or refuses.