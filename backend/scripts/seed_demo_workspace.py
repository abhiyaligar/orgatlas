"""Seed the org around the EstateX repository so /ask has something to answer.

A repository ingest gives you files, symbols and commits. It does not give you
teams, services, technologies, decisions or incidents, so questions about
ownership, onboarding and "why" have nothing to resolve to and answer
"insufficient evidence" on an empty graph.

Everything here is fictional demo data for the workspace the EstateX build
happened in. It is written to match the shapes the retrieval queries already
expect, and every node is merged on a label and a stable id so re-running does
not duplicate anything.

    python -m scripts.seed_demo_workspace
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.graph.connection import graph_manager  # noqa: E402

REPO_ID = "repo_abhiyaligar_estatex"
NOW = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc).isoformat()

TEAMS = [
    ("team_payments", "Payments Core", "Settlement, reconciliation and payouts."),
    ("team_platform", "Cloud Infrastructure", "Runtime, data and shared services."),
    ("team_frontend", "Web Experience", "The browser surface customers use."),
    ("team_governance", "Governance and Risk", "Audit, KYC and the officer tools."),
]

PEOPLE_TEAMS = {
    "person_priya": "team_payments",
    "person_daniel": "team_platform",
    "person_mei": "team_frontend",
    "person_joel": "team_platform",
    "person_sana": "team_governance",
    "person_tom": "team_platform",
    "person_ines": "team_payments",
}

SERVICES = [
    ("svc_listing", "Listing Service", "team_frontend",
     "Property and unit listings shown to buyers."),
    ("svc_exchange", "Exchange Service", "team_platform",
     "Valuations against exchange rates, and the rate fetcher."),
    ("svc_settlement", "Settlement Service", "team_payments",
     "Payout state machine and the manual reconciliation queue."),
    ("svc_auth", "Auth Service", "team_platform",
     "Registration, login and one-time passcode verification."),
    ("svc_admin", "Admin Portal", "team_governance",
     "The tools a governance officer uses to review activity."),
]

TECHNOLOGIES = [
    ("tech_postgres", "PostgreSQL"),
    ("tech_fastapi", "FastAPI"),
    ("tech_react", "React"),
    ("tech_vite", "Vite"),
    ("tech_sms_otp", "SMS one-time passcodes"),
    ("tech_cache", "In-process cache"),
    ("tech_password", "Passwords"),
]

SERVICE_USES = {
    "svc_listing": ["tech_react", "tech_fastapi"],
    "svc_exchange": ["tech_fastapi", "tech_postgres", "tech_cache"],
    "svc_settlement": ["tech_fastapi", "tech_postgres"],
    "svc_auth": ["tech_fastapi", "tech_postgres", "tech_sms_otp"],
    "svc_admin": ["tech_react", "tech_fastapi"],
}

SERVICE_DEPENDS_ON = [
    ("svc_listing", "svc_exchange"),
    ("svc_settlement", "svc_exchange"),
    ("svc_admin", "svc_auth"),
]

DOCUMENTS = [
    ("doc_adr_otp", "ADR: One-time passcodes instead of passwords", "adr", "Daniel Okafor",
     "Records the authentication decision and the objection raised against it."),
    ("doc_adr_rates", "ADR: Snapshot exchange rates", "adr", "Ines Duarte",
     "Why rates are stored as snapshots rather than held live."),
    ("doc_arch", "Technical architecture", "design", "Priya Raman",
     "How the platform is arranged, and what was deliberately left out."),
    ("doc_audit", "How audit works", "design", "Sana Qureshi",
     "What is recorded, who can see it, and what is still missing."),
]

DECISIONS = [
    {
        "id": "doc_adr_otp:otp_auth",
        "title": "Use OTP one-time passcodes instead of passwords",
        "status": "accepted",
        "summary": (
            "Authentication moved to OTP one-time passcodes delivered by SMS, so "
            "the platform stores no password credential to reset or breach."
        ),
        "rationale": (
            "Passwords mean owning a credential store and a self-service reset "
            "flow indefinitely. An OTP is one tap for a mobile-first user and "
            "removes the stored secret entirely."
        ),
        "alternatives": "Passwords with self-service reset, or a third-party identity provider.",
        "decided_at": "2026-04-08T10:15:00+00:00",
        "document": "doc_adr_otp",
        "proposed": ("person_mei", "Our users are mostly on mobile. OTP is one tap, a password reset is four screens."),
        "approved": ("person_priya", "This is the decision worth writing down. OTP for now, passwords revisit at scale."),
        "objected": ("person_sana", "Governance officers will want passwords. OTP-only is a support burden at 3am."),
        "discussed": ["person_daniel", "person_joel", "person_ines"],
        "implemented_by": ("person_daniel", "register_user, login_user and verify_auth_otp all go through this path."),
        "migrated_from": "tech_password",
        "migrated_to": "tech_sms_otp",
    },
    {
        "id": "doc_adr_rates:snapshot_rates",
        "title": "Store exchange rates as snapshots rather than a live feed",
        "status": "accepted",
        "rationale": (
            "Holding live rates turns us into a market data provider, which is a "
            "different business with different obligations. One row per fetch is "
            "enough to answer what a valuation was based on."
        ),
        "alternatives": "Subscribe to a live rate feed, or fetch on every request with no history.",
        "decided_at": "2026-04-09T15:40:00+00:00",
        "document": "doc_adr_rates",
        "proposed": ("person_ines", "Snapshot. If we store live we are a market data provider."),
        "approved": ("person_priya", "Agreed. One row per fetch, timestamped."),
        "objected": None,
        "discussed": ["person_tom", "person_daniel"],
        "implemented_by": ("person_daniel", "The fetcher writes a new snapshot row on every successful fetch."),
        "migrated_from": None,
        "migrated_to": None,
    },
    {
        "id": "doc_arch:settlement_state",
        "title": "Model settlement as an explicit state machine",
        "status": "accepted",
        "rationale": (
            "A boolean paid flag cannot express a payout that is approved, queued, "
            "failed and retried. Audit needs to see each transition and who made it."
        ),
        "alternatives": "Keep a paid flag and rely on the ledger.",
        "decided_at": "2026-04-11T11:00:00+00:00",
        "document": "doc_arch",
        "proposed": ("person_sana", "A reviewer has to see who approved a payout and when."),
        "approved": ("person_priya", "Agreed, and every transition gets an actor."),
        "objected": None,
        "discussed": ["person_daniel", "person_ines"],
        "implemented_by": ("person_daniel", "State and actor columns on every payout row."),
        "migrated_from": None,
        "migrated_to": None,
    },
    {
        "id": "doc_arch:lazy_charts",
        "title": "Lazy-load the trading charts",
        "status": "accepted",
        "rationale": (
            "The chart library was the weight behind an eleven second cold load. "
            "It sits below the fold for most visitors, so deferring it costs "
            "nothing and bought back about five seconds."
        ),
        "alternatives": "Ship it bundled, or rewrite the charts.",
        "decided_at": "2026-04-15T09:30:00+00:00",
        "document": "doc_arch",
        "proposed": ("person_joel", "Lazy load the chart. It is below the fold for most people anyway."),
        "approved": ("person_priya", "Six seconds is still a number I would have to explain."),
        "objected": None,
        "discussed": ["person_mei", "person_tom", "person_ines"],
        "implemented_by": ("person_mei", "TradingRoom loads the chart on demand."),
        "migrated_from": None,
        "migrated_to": None,
    },
    {
        "id": "doc_adr_otp:otp_rate_limit",
        "title": "Rate limit one-time passcode sends",
        "status": "accepted",
        "rationale": (
            "Without a limit, anyone can burn the SMS budget in an afternoon and "
            "drown real users in messages they did not ask for."
        ),
        "alternatives": "No limit, or a captcha.",
        "decided_at": "2026-04-17T16:05:00+00:00",
        "document": "doc_adr_otp",
        "proposed": ("person_sana", "Rate limit before launch. That is the real finding."),
        "approved": ("person_priya", "Added. Per number, five an hour."),
        "objected": None,
        "discussed": ["person_daniel"],
        "implemented_by": ("person_daniel", "Limit applied in the OTP send path."),
        "migrated_from": None,
        "migrated_to": None,
    },
]

INCIDENTS = [
    ("inc_stale_rates", "Stale exchange rates served wrong quotes for an hour",
     "high", "svc_exchange"),
    ("inc_otp_spend", "One-time passcode sends had no rate limit",
     "medium", "svc_auth"),
]

INCIDENT_TO_DECISION = [
    ("inc_stale_rates", "doc_adr_rates:snapshot_rates"),
    ("inc_otp_spend", "doc_adr_otp:otp_rate_limit"),
]

METRICS = [
    # The reader casts value to a float and formats it, so the unit belongs in
    # ``unit``. Putting "4.5 hours" in the value crashes the whole answer.
    ("metric_time_to_first_listing", "doc_arch", "Time to first listing", "4.5",
     "hours", "9 hours", "down", "Down from nine hours once the wizard was cut to three steps."),
    ("metric_manual_settlement_share", "doc_audit", "Settlements needing manual help", "62",
     "percent", "n/a", "unknown", "High because reconciliation is still a person reading a queue."),
]

ONBOARDING_TOPICS = [
    ("ot_first_week", "Your first week", "What to read and who to meet, in order.",
     ["team_payments", "team_platform", "team_frontend", "team_governance"]),
    ("ot_auth", "How authentication works", "Registration, login and passcode verification.",
     ["team_platform"]),
    ("ot_exchange", "How exchange rates are fetched", "The rate fetcher, the cache, and why they are snapshots.",
     ["team_platform"]),
    ("ot_audit", "How audit works", "What is recorded and who can see it.",
     ["team_governance"]),
]

TOPIC_LEARN_ABOUT = [
    ("ot_first_week", "svc_listing"),
    ("ot_first_week", "svc_settlement"),
    ("ot_auth", "svc_auth"),
    ("ot_exchange", "svc_exchange"),
    ("ot_audit", "svc_admin"),
]

# Distinctive phrases from the seeded Slack history, so a decision cites the
# discussion that actually happened rather than a summary invented here.
DECISION_QUOTES = {
    "doc_adr_otp:otp_auth": [
        "Passwords mean we own a credential store",
        "This is the decision worth writing down",
        "Governance officers will want passwords",
        "OTP for now, passwords revisit",
    ],
    "doc_adr_rates:snapshot_rates": [
        "Snapshot. If we store live",
        "One row per fetch",
        "Are rates live or snapshot",
    ],
    "doc_arch:settlement_state": [
        "Settlement needs an explicit state",
        "Every payout row gets an actor",
    ],
    "doc_arch:lazy_charts": [
        "Lazy load the chart",
        "eleven seconds on a cold load",
    ],
    "doc_adr_otp:otp_rate_limit": [
        "rate limit on the OTP send",
        "Rate limit before launch",
    ],
}

TRACKED_WORK = [
    ("pr_lazy_charts", "PullRequest", "Lazy-load the trading charts", "merged"),
    ("tkt_tradingroom_split", "Ticket", "Split TradingRoom into charts and filters", "open"),
]


def _run(graph):
    for team_id, name, mission in TEAMS:
        graph.query(
            "MERGE (t:Team {id: $id}) SET t.name = $name, t.mission = $mission, t.source = 'seed'",
            {"id": team_id, "name": name, "mission": mission},
        )

    for person_id, team_id in PEOPLE_TEAMS.items():
        graph.query(
            """MATCH (p:Person {id: $person_id}), (t:Team {id: $team_id})
               MERGE (p)-[:MEMBER_OF]->(t)""",
            {"person_id": person_id, "team_id": team_id},
        )

    for service_id, name, team_id, description in SERVICES:
        graph.query(
            """MERGE (s:Service {id: $id})
               SET s.name = $name, s.description = $description, s.source = 'seed'
               WITH s MATCH (t:Team {id: $team_id}) MERGE (t)-[:OWNS]->(s)""",
            {"id": service_id, "name": name, "description": description, "team_id": team_id},
        )

    for tech_id, name in TECHNOLOGIES:
        graph.query(
            "MERGE (t:Technology {id: $id}) SET t.name = $name, t.source = 'seed'",
            {"id": tech_id, "name": name},
        )

    for service_id, tech_ids in SERVICE_USES.items():
        graph.query(
            """UNWIND $tech_ids AS tech_id
               MATCH (s:Service {id: $service_id}), (t:Technology {id: tech_id})
               MERGE (s)-[:USES]->(t)""",
            {"service_id": service_id, "tech_ids": tech_ids},
        )

    for source, target in SERVICE_DEPENDS_ON:
        graph.query(
            """MATCH (a:Service {id: $source}), (b:Service {id: $target})
               MERGE (a)-[:DEPENDS_ON]->(b)""",
            {"source": source, "target": target},
        )

    # The repository is where these services actually live.
    for service_id, *_ in SERVICES:
        graph.query(
            """MATCH (r:Repository {id: $repo}), (s:Service {id: $service_id})
               MERGE (r)-[:PRIMARY_IMPLEMENTATION_OF]->(s)""",
            {"repo": REPO_ID, "service_id": service_id},
        )

    for doc_id, title, kind, author, summary in DOCUMENTS:
        graph.query(
            """MERGE (d:Document {id: $id})
               SET d.title = $title, d.kind = $kind, d.author = $author,
                   d.summary = $summary, d.source_at = $now, d.source = 'seed'""",
            {"id": doc_id, "title": title, "kind": kind, "author": author,
             "summary": summary, "now": NOW},
        )

    for service_id, *_ in SERVICES:
        graph.query(
            """MATCH (d:Document), (s:Service {id: $service_id})
               WHERE d.id IN $doc_ids
               MERGE (d)-[:DOCUMENTS]->(s)""",
            {"doc_ids": [d[0] for d in DOCUMENTS], "service_id": service_id},
        )

    for decision in DECISIONS:
        graph.query(
            """MERGE (d:Decision {id: $id})
               SET d.title = $title, d.status = $status, d.summary = $summary,
                   d.rationale = $rationale, d.alternatives = $alternatives,
                   d.decided_at = $decided_at, d.source = 'seed'
               WITH d MATCH (doc:Document {id: $document_id})
               MERGE (d)-[:SUPPORTED_BY]->(doc)""",
            {
                "id": decision["id"],
                "title": decision["title"],
                "status": decision["status"],
                "summary": decision.get("summary") or decision["title"],
                "rationale": decision["rationale"],
                "alternatives": decision["alternatives"],
                "decided_at": decision["decided_at"],
                "document_id": decision["document"],
            },
        )

        for role, key in (("PROPOSED", "proposed"), ("APPROVED", "approved"),
                          ("OBJECTED", "objected"), ("IMPLEMENTED_IN", "implemented_by")):
            entry = decision.get(key)
            if not entry:
                continue
            person_id, quote = entry
            graph.query(
                f"""MATCH (p:Person {{id: $person_id}}), (d:Decision {{id: $decision_id}})
                    MERGE (p)-[r:{role}]->(d)
                    SET r.role = $role, r.quote = $quote""",
                {"person_id": person_id, "decision_id": decision["id"], "role": role,
                 "quote": quote},
            )

        if decision.get("discussed"):
            graph.query(
                """UNWIND $person_ids AS person_id
                   MATCH (p:Person {id: person_id}), (d:Decision {id: $decision_id})
                   MERGE (p)-[:DISCUSSED]->(d)""",
                {"person_ids": decision["discussed"], "decision_id": decision["id"]},
            )

        for edge, key in (("MIGRATED_FROM", "migrated_from"), ("MIGRATED_TO", "migrated_to")):
            tech_id = decision.get(key)
            if not tech_id:
                continue
            graph.query(
                f"""MATCH (d:Decision {{id: $decision_id}}), (t:Technology {{id: $tech_id}})
                    MERGE (d)-[:{edge}]->(t)""",
                {"decision_id": decision["id"], "tech_id": tech_id},
            )

    for metric_id, doc_id, name, value, unit, baseline, direction, quote in METRICS:
        graph.query(
            """MERGE (m:Metric {id: $id})
               SET m.name = $name, m.value = $value, m.unit = $unit,
                   m.baseline = $baseline, m.direction = $direction, m.quote = $quote
               WITH m MATCH (d:Document {id: $doc_id}) MERGE (d)-[:STATES_METRIC]->(m)""",
            {"id": metric_id, "doc_id": doc_id, "name": name, "value": value,
             "unit": unit, "baseline": baseline, "direction": direction, "quote": quote},
        )

    for incident_id, title, severity, service_id in INCIDENTS:
        graph.query(
            """MERGE (i:Incident {id: $id})
               SET i.title = $title, i.severity = $severity, i.source = 'seed'
               WITH i MATCH (s:Service {id: $service_id}) MERGE (i)-[:AFFECTS]->(s)""",
            {"id": incident_id, "title": title, "severity": severity,
             "service_id": service_id},
        )

    for incident_id, decision_id in INCIDENT_TO_DECISION:
        graph.query(
            """MATCH (i:Incident {id: $incident_id}), (d:Decision {id: $decision_id})
               MERGE (i)-[:LED_TO]->(d)""",
            {"incident_id": incident_id, "decision_id": decision_id},
        )

    for sequence, (topic_id, name, summary, team_ids) in enumerate(ONBOARDING_TOPICS, start=1):
        # Both name and title are set: name is the convention the graph uses
        # everywhere else, and the onboarding reader renders title. Sequence
        # orders the reading path, which would otherwise be arbitrary.
        graph.query(
            """MERGE (o:OnboardingTopic {id: $id})
               SET o.name = $name, o.title = $name, o.summary = $summary,
                   o.sequence = $sequence, o.source = 'seed'
               WITH o UNWIND $team_ids AS team_id
               MATCH (t:Team {id: team_id}) MERGE (o)-[:RECOMMENDED_FOR]->(t)""",
            {"id": topic_id, "name": name, "summary": summary,
             "sequence": sequence, "team_ids": team_ids},
        )

    for topic_id, target_id in TOPIC_LEARN_ABOUT:
        graph.query(
            """MATCH (o:OnboardingTopic {id: $topic_id}), (s:Service {id: $target_id})
               MERGE (o)-[:LEARN_ABOUT]->(s)""",
            {"topic_id": topic_id, "target_id": target_id},
        )

    for node_id, label, title, status in TRACKED_WORK:
        graph.query(
            f"""MERGE (n:{label} {{id: $id}})
                SET n.title = $title, n.status = $status, n.source = 'seed'""",
            {"id": node_id, "title": title, "status": status},
        )

    linked = 0
    for decision_id, phrases in DECISION_QUOTES.items():
        for phrase in phrases:
            rows = graph.query(
                """MATCH (m:SlackMessage) WHERE m.excerpt CONTAINS $phrase
                   RETURN m.id""",
                {"phrase": phrase},
            ).result_set
            for row in rows:
                graph.query(
                    """MATCH (m:SlackMessage {id: $message_id}),
                              (d:Decision {id: $decision_id})
                       MERGE (m)-[:ABOUT]->(d)""",
                    {"message_id": row[0], "decision_id": decision_id},
                )
                linked += 1

    return linked


def main() -> int:
    graph = graph_manager.get_or_create_graph()
    linked = _run(graph)
    counts = {}
    for label in ("Team", "Person", "Service", "Technology", "Document",
                  "Decision", "Metric", "Incident", "OnboardingTopic",
                  "PullRequest", "Ticket"):
        counts[label] = graph.query(
            f"MATCH (n:{label}) RETURN count(n)"
        ).result_set[0][0]
    print("  " + "  ".join(f"{label}={value}" for label, value in counts.items()))
    print(f"  decision <-> discussion links: {linked}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())