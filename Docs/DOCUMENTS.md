# Document ingestion

Company documents go in, connections come out. A PDF of a design review, a
decision log in CSV, an ADR in markdown — upload it, and OrgAtlas extracts the
decisions, the people, the quotes and the numbers, links them to what is already
in the graph, and makes them answerable through `/ask`, MCP and Slack.

## The pipeline

```
upload → parsing → extracting → linking → writing → done | failed
```

Extraction runs **before** linking on purpose. The extractor names the entities
a document talks about; linking then resolves those names against nodes that
already exist. That is what turns a document into graph structure rather than a
stored blob.

Every write is a `MERGE` on a stable id derived from the content hash, so
uploading the same file twice updates its node instead of creating a second copy
that disagrees with the first.

## Supported files

| Type | Handling |
| --- | --- |
| `.pdf` | Text layer only. A scanned PDF has no text layer and is refused with that reason, not returned empty. |
| `.md` | Title from the first heading. |
| `.txt` | Title from the first line. |
| `.csv` | **One document per row**, titled from a `title`/`decision`/`summary`/`subject`/`name` column. |

A CSV becomes several documents because a decision log is a table of separate
records. Kept as one blob, the model would summarise the whole sheet and
attribute every decision to every row.

20 MB upload limit.

## Uploading

```bash
curl -X POST http://localhost:8000/api/docs \
  -F "file=@decision-log.csv" \
  -F "title=Q3 Decision Log" \
  -F "author=Sarah Chen"
```

| Field | Default | Meaning |
| --- | --- | --- |
| `file` | required | The document |
| `title` | from the file | Overrides the detected title |
| `author` | none | Recorded on the document and in citations |
| `extract` | `true` | `false` parses and links without calling the model |

Response is the job:

```json
{
  "id": 1, "status": "done", "kind": "csv",
  "documents_ingested": 12, "decisions_extracted": 9,
  "metrics_extracted": 4, "entities_linked": 23, "model_calls": 12
}
```

| Endpoint | Purpose |
| --- | --- |
| `POST /api/docs` | Upload and ingest |
| `GET /api/docs/ingest/{id}` | Poll a job |
| `GET /api/docs` | List ingested documents |
| `POST /api/docs/slack/ingest` | Ingest Slack history |
| `GET /api/docs/decisions/{id}` | One decision with every kind of evidence |

## How extraction is verified

This is the one place OrgAtlas asks a model to **add to the graph** rather than
phrase an answer, which changes the risk. So:

- Every extracted item must carry a `quote` — the exact sentence it came from.
- The quote is checked against the source. **Not found, item dropped.**
- A metric needs a verifiable quote containing a number. A document that states
  no number produces no metric, ever.
- The raw response is stored alongside the parsed result, so an extraction can
  be audited against what the model actually said.

The dropped-item counts are logged, so you can see how much of a model's output
survived verification rather than assuming all of it did.

## What lands in the graph

| Label | Holds |
| --- | --- |
| `Document` | Title, kind, hash, summary, provenance |
| `Metric` | Name, value, unit, baseline, direction, and the sentence stating it |
| `SlackMessage` | Channel, author, timestamp, permalink, **excerpt** |

| Relationship | Answers |
| --- | --- |
| `Decision -[:SUPPORTED_BY]-> Document` | which document backs this decision |
| `Person -[:PROPOSED]-> Decision` | who argued for it |
| `Person -[:APPROVED]-> Decision` | who signed off |
| `Person -[:OBJECTED]-> Decision` | who disagreed |
| `Document -[:STATES_METRIC]-> Metric` | what the documents claim was achieved |
| `SlackMessage -[:ABOUT]-> Entity` | what was discussed where |
| `Person -[:QUOTED]-> SlackMessage` | who said it |
| `Decision -[:MIGRATED_FROM|TO]-> Technology` | what it moved between |
| `Person -[:IMPLEMENTED_IN]-> Decision` | who built it |

A Slack message is stored as a **500-character excerpt**, not a transcript. The
full text stays in the relational store. A transcript in the graph gets read back
verbatim in an answer, which is noise with a citation attached.

A migration is recorded only when the document states **both ends** of it. Two
tools appearing in one file is not a migration, and nothing infers one.

## Answering with all of it

```
Why did we move Checkout from Kafka to Redis, and what did we get from it?
```

`/ask` routes to the decision and returns one narrative:

```
**Decision: Migrate Checkout from Kafka to Redis Streams**
**Status:** Accepted, decided 2024-06-01
**Why:** Consumer lag at peak season left orders unprocessed for up to four minutes.
**Alternatives considered:** Kafka Streams — rejected, consumer group could not be replayed safely
**Migration:** from Kafka to Redis Streams
**People involved:**
- Sarah Chen (proposed) — "Sarah Chen proposed the migration and Dvir Dukhan approved it."
- Dvir Dukhan (approved)
**In discussion:**
- "I think consumer lag is the real risk here." — Sarah Chen in #payments
**Stated outcomes:**
- Checkout p99 latency: 120ms (from 840ms) improvement
**Commits by those involved (8):**
- `a1b2c3d` perf(checkout): reduce publish latency — Sarah Chen
**Sources:**
- Migration Record: Checkout from Kafka to Redis Streams

**Not recorded:**
- No improvement figure is recorded in the documents.
```

That last section is the point. **Gaps are stated in words, not left as
absence.** A reader who sees no metric will assume there was no improvement; a
reader who sees "no improvement figure is recorded" will go and look. Every
section is bounded and every excerpt truncated: a decision answer that reads as
a wall of evidence is not read.

## Cost

Extraction is the expensive part, because the configured model is a reasoning
model and it reasons over prose before answering.

| Measure | Observed |
| --- | --- |
| Time, one document | 80-190s, noisy across runs |
| Completion tokens | ~7,800, most of it spent reasoning |
| Visible output | ~1,000 tokens of JSON |

`extract=false` skips it. A document uploaded that way is still parsed, stored
and linked; it simply contributes no extracted decisions or metrics.

### Choosing the extraction model

`NEBIUS_EXTRACTION_MODEL_NAME` defaults to the same model answers use. Extraction
was measured against `google/gemma-3-27b-it` on one migration document:

| Model | Completion tokens | Wall clock | Extracted |
| --- | --- | --- | --- |
| `zai-org/GLM-5.3-Flash` (default) | 7,764 | 80s | 2 decisions, 2 people, 3 metrics |
| `google/gemma-3-27b-it` | 4,493 | 115s | 1 decision, 2 people, 3 metrics |

The cheaper model used **42% fewer tokens** but was not faster in wall-clock, and
the extractions differed by one decision. That saving was not judged worth
changing the default over, so the setting exists for deployments that disagree.

One model tested, `deepseek-ai/DeepSeek-V4.1-Flash`, reasons heavily despite the
name: it consumed 16,384 tokens and returned nothing, exactly as the default
model does on a large enough document. A reasoning model on this task will
sometimes exhaust its budget and return empty output. The extractor grows its
token budget and retries when that happens, and records the failure rather than
storing an empty extraction as if it were a finding.

To switch:

```bash
NEBIUS_EXTRACTION_MODEL_NAME=google/gemma-3-27b-it
```

## Storage

Relational (SQLAlchemy + Alembic) for documents, extractions and messages;
FalkorDB for the structure. `DATABASE_URL` points at SQLite locally and can
point at Postgres in production — same code path.

```bash
python -m alembic upgrade head
```

Migration `003_document_ingestion_models` creates `documents`,
`document_extractions`, `slack_messages` and `document_ingest_jobs`.

## Slack ingestion

```bash
curl -X POST http://localhost:8000/api/docs/slack/ingest \
  -H 'Content-Type: application/json' \
  -d '{"messages":[
        {"channel_id":"C123","channel_name":"payments","text":"I think consumer lag is the real risk.",
         "author":"Sarah Chen","ts":"1717430400.000100",
         "about":["Migrate Checkout to Redis Streams"]}
      ]}'
```

A speaker who is not already in the graph is left unattributed rather than
invented as a person. `about` names what the message was about; those terms are
resolved against existing nodes the same way `/ask` resolves them.

## Safety

- **Extraction is verified, not trusted.** No quote, no graph node.
- **No invented metrics.** A document that states no number yields none.
- **No inferred migrations.** Both ends must be stated.
- **No invented people.** An unknown Slack speaker stays unattributed.
- **Excerpts, not transcripts.** The graph carries enough to cite, not enough to
  flood an answer.
- **Gaps are stated.** Every missing section says so explicitly.
- **Read-only retrieval.** Ingestion writes; asking never does.