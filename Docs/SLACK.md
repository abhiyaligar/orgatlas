# Slack

OrgAtlas answers questions in a Slack channel from the same graph the API uses,
so a decision gets made against evidence rather than against whoever remembers
the most.

The bot is read-only. It cannot write to the graph, open a ticket, or change a
deployment. It answers, and it cites.

## Why this exists

An agent asked "why is it Kafka here?" and guessed, because guessing is cheaper
than digging. A teammate asked the same thing in Slack and got a citation. The
point of this integration is to make the cheap, sourced answer the path of least
resistance in the channel where those questions are already asked.

## How a dev sets it up

Socket Mode is used rather than an Events API webhook, because Socket Mode opens
an **outbound** WebSocket to Slack. You can run this from a laptop with no public
URL, no TLS certificate, and no inbound firewall rule. The trade-off is that it
is a long-running local process rather than a serverless function.

### 1. Create a Slack app

At [api.slack.com/apps](https://api.slack.com/apps) → *Create New App* →
*From scratch*. Name it `OrgAtlas`.

### 2. Generate the tokens

Under **Basic Information**:

- **Bot Token** — *OAuth & Permissions* → *Install to Workspace*. Scopes needed:
  - `app_mentions:read` — to see when it is mentioned
  - `channels:history` — to read the message it was mentioned in
  - `chat:write` — to reply
- **App Token** — *Settings* → *Basic Information* → *App-Level Tokens* →
  *Generate* with the `connections:write` scope. This one starts the Socket Mode
  connection.

### 3. Subscribe to events

*Event Subscriptions* → *Enable Events*, then under *Subscribe to bot events*:

- `app_mention`
- `message.channels`

### 4. Configure OrgAtlas

```bash
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
SLACK_ALLOWED_CHANNELS=C0123456789,C9876543210
```

`SLACK_ALLOWED_CHANNELS` is a comma-separated list of channel IDs. **Empty means
the bot stays silent in every channel.** A bot that has merely been invited to a
workspace must not start answering questions in it until someone has said where
that is wanted.

To find a channel ID, open the channel in Slack, copy the link, and take the last
segment: `https://app.slack.com/archives/C0123456789` gives `C0123456789`.

### 5. Run it

```bash
cd backend
python -m app.slack.bot
```

The bot prints the identity it connected as and the channels it will answer in:

```
Slack bot connecting as U0ORGATLAS, answering in ['C0123456789']
```

### 6. Ask it something

```
@OrgAtlas why does Checkout use Kafka instead of synchronous calls?
```

The bot replies in a thread under the mention.

## What a reply looks like

```
:large_green_circle: *supported*
*Short answer:* Checkout moved from synchronous REST calls to Kafka to eliminate
the cascading failure mode exposed during the March 2024 flash sale...

*Sources*
1. *RFC-042: Asynchronous Event-Driven Checkout Architecture* — <...|open>
2. *Incident Postmortem: SEV-1 Checkout Outage* — <...|open>
```

The confidence indicator is deliberately above the answer, not below it. A reader
who skims only the first line should still see whether the answer is load-bearing:

| Indicator | Meaning |
| --- | --- |
| 🟢 `supported` | Retrieved evidence backs the answer |
| 🟡 `partial` | Some claims are grounded, some are not |
| 🟠 `insufficient` | The graph does not support an answer |

An `insufficient` reply also says so in words and suggests what to ingest. It
never substitutes a guess, because a Slack answer gets acted on.

## Questions it answers well

The bot routes from the graph, so what it can answer is what is in the graph.

| Question | Example |
| --- | --- |
| Ownership | *who owns Token Service?* |
| Change impact | *what depends on Checkout Service?* |
| Decisions | *why did we choose Kafka?* |
| Onboarding | *what should a new engineer on Payments learn first?* |
| Declarations | *what does the RedisModule_OpenKey function do?* |
| Files | *describe the graph.rs module* |
| History | *how often has graph.rs changed?* |

**Aggregate questions do not work.** *"How many teams do we have?"* resolves to
nothing, because the graph is traversed for relationships rather than counted. The
bot reports insufficient evidence rather than counting declarations and hoping.

## For agents in Slack

An agent with Slack access can use this as a context source: ask it what a symbol
does, what a file is for, or who to talk to, and it returns the graph's answer
with a citation rather than a plausible summary. The MCP server serves the same
evidence to an agent directly, without Slack in the loop — see
[MCP_SERVER.md](MCP_SERVER.md). Slack is for the humans and for agents that only
have Slack.

## Safety properties

These are enforced in code and covered by tests in
`tests/test_slack_bot.py`:

- **Silent by default.** No allowlist, no replies, anywhere.
- **Mention-only.** A message the bot was not mentioned in is ignored.
- **No self-reply loop.** Message edits, joins, and the bot's own posts are ignored.
- **Failures read as failures.** If the graph is unreachable, the bot says it
  could not answer. It does not return a plausible answer instead.
- **Read-only.** No code path writes to the graph.

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| Connects, then never replies | `SLACK_ALLOWED_CHANNELS` does not contain the channel |
| Silent in a channel that looks right | Channel ID is wrong; use the archives URL, not the channel name |
| `invalid_auth` on start | Bot token was not installed to a workspace |
| `not_allowed_token_type` on start | App token lacks `connections:write` |
| Replies but says insufficient evidence | The graph does not cover it. Ingest the repository first. |

## Config reference

| Variable | Default | Meaning |
| --- | --- | --- |
| `SLACK_BOT_TOKEN` | unset | `xoxb-` token. Unset means the bot does not start. |
| `SLACK_APP_TOKEN` | unset | `xapp-` token with `connections:write`. Unset means the bot does not start. |
| `SLACK_ALLOWED_CHANNELS` | empty | Comma-separated channel IDs. Empty means silent everywhere. |
| `SLACK_MAX_QUESTION_CHARS` | 800 | Longer input is truncated and marked. |