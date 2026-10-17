"""Seed the Slack history a team would have left while building EstateX.

The messages exist so "who said what" is answerable with a citation, and so a
decision question has discussion attached to it. They name real nodes that the
ingest created, so the ``about`` links resolve against the graph rather than
being decorative.

Run it directly:

    python -m scripts.seed_slack_history

It is idempotent in the sense that it refuses to run twice against the same
channel without being asked to, because a second run would double every
message in the graph.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import SlackMessage  # noqa: E402
from app.core.dependencies import SessionLocal  # noqa: E402
from app.ingestion.document_ingest import DocumentIngestor  # noqa: E402
from app.graph.connection import graph_manager  # noqa: E402
from app.graph.gateway import graph_gateway  # noqa: E402

CHANNEL = {
    "channel_id": "C0ESTATEX",
    "channel_name": "estatex-build",
}

# People the build actually had. The external identities are left unattributed
# unless a matching node exists, which is the ingest's deliberate behaviour.
PEOPLE = [
    ("U0PRIYA", "Priya Raman", "priya"),
    ("U0DANIEL", "Daniel Okafor", "daniel"),
    ("U0MEI", "Mei Lin", "mei"),
    ("U0JOEL", "Joel Barrett", "joel"),
    ("U0SANA", "Sana Qureshi", "sana"),
    ("U0TOM", "Tom Bradley", "tom"),
    ("U0INES", "Ines Duarte", "ines"),
]

START = datetime(2026, 4, 6, 9, 12, tzinfo=timezone.utc)

# (offset_minutes, user, text, [about entities])
SCRIPT: list[tuple[int, str, str, list[str]]] = [
    # --- kickoff ---------------------------------------------------------
    (0, "U0PRIYA",
     "Kicking off the EstateX build. Goal for the quarter: property listings, exchange listings, and the admin surface a governance officer needs.",
     []),
    (4, "U0DANIEL", "Backend or frontend first? I'd rather we agree the data model before anyone writes a migration.", []),
    (9, "U0PRIYA", "Data model first. Daniel owns it, one week, then we fork.",
     ["repo_abhiyaligar_estatex"]),
    (14, "U0MEI", "Frontend can build against a frozen OpenAPI schema. I'll stub the client so nobody waits.",
     []),
    (21, "U0SANA", "Governance surface needs audit fields from day one. If we add them later we backfill and get it wrong.",
     []),
    (27, "U0PRIYA", "Sana is right. created_at, updated_at and actor on every table we mutate. Not negotiable.",
     []),

    # --- stack decision --------------------------------------------------
    (52, "U0DANIEL", "For the stack: FastAPI on the backend, React and Vite on the frontend. Any objections?",
     ["repo_abhiyaligar_estatex"]),
    (58, "U0JOEL", "FastAPI yes. Vite over CRA is the right call, CRA is effectively dead.",
     []),
    (63, "U0PRIYA", "Agreed. Postgres for relational, no debate. We have real transactions in exchange.",
     []),
    (69, "U0TOM", "Are we doing anything exotic in the database? I'd rather not debug a NoSQL store at 2am.",
     []),
    (74, "U0DANIEL", "Plain Postgres. Alembic for migrations from the first commit.",
     ["backend/app/main.py"]),
    (81, "U0SANA", "Put the ADR in the repo so we can point at it later.",
     ["repo_abhiyaligar_estatex::01-TECHNICAL-ARCHITECTURE.md"]),

    # --- auth: the OTP decision ------------------------------------------
    (140, "U0DANIEL", "Auth is the interesting call. Passwords mean we own a credential store and a reset flow forever.",
     ["AuthService"]),
    (147, "U0SANA", "Governance officers will want passwords. OTP-only is a support burden at 3am.",
     ["AuthService"]),
    (153, "U0MEI", "Our users are mostly on mobile. OTP is one tap, a password reset is four screens.",
     ["send_auth_otp"]),
    (160, "U0PRIYA", "This is the decision worth writing down. OTP for now, passwords revisit at scale.",
     ["AuthService", "send_auth_otp"]),
    (166, "U0DANIEL", "Agreed. I'll note the rationale in the code so the next person doesn't undo it on a hunch.",
     ["login_user", "verify_auth_otp"]),
    (172, "U0SANA", "Please make sure the objection is recorded too. We argued both ways in here.",
     ["AuthService"]),

    # --- implementation --------------------------------------------------
    (240, "U0DANIEL", "register_user and login_user are in. Moving on to OTP verification.",
     ["register_user", "login_user"]),
    (247, "U0JOEL", "What happens when someone's OTP expires mid-entry?",
     ["verify_auth_otp"]),
    (252, "U0DANIEL", "verify_auth_otp returns a distinct error and we let them request a new code. Five minute window.",
     ["verify_auth_otp"]),
    (259, "U0INES", "Five minutes feels right. Longer and a leaked code is a bigger window.",
     ["verify_auth_otp"]),
    (266, "U0MEI", "Login form is done. ForgotPassword is the placeholder, I need the final copy.",
     ["Login.jsx", "ForgotPassword.jsx"]),
    (273, "U0SANA", "Copy should say contact support, not reset. We don't have self-service reset yet.",
     ["ForgotPassword.jsx"]),

    # --- frontend shell --------------------------------------------------
    (330, "U0MEI", "Landing page is up. Navbar is the next piece.",
     ["Navbar.jsx", "Landing.jsx"]),
    (337, "U0JOEL", "Navbar has been rewritten four times. Please don't let it become a monolith.",
     ["Navbar.jsx"]),
    (343, "U0MEI", "It's one component with a menu and a logout. It's fine.",
     ["Navbar.jsx"]),
    (349, "U0JOEL", "It is never fine.",
     ["Navbar.jsx"]),
    (355, "U0PRIYA", "Leave it. We can split it when it hurts.",
     ["Navbar.jsx"]),

    # --- trading room ----------------------------------------------------
    (410, "U0TOM", "TradingRoom.jsx is the biggest file in the repo and it's the messiest.",
     ["TradingRoom.jsx"]),
    (416, "U0INES", "How bad?",
     ["TradingRoom.jsx"]),
    (420, "U0TOM", "Twenty-four commits touching it. Chart rendering, filters and pagination in one file.",
     ["TradingRoom.jsx"]),
    (427, "U0JOEL", "Split it before we build on it. Charts and filters are independent.",
     ["TradingRoom.jsx"]),
    (434, "U0MEI", "Charts first. Filters can wait for the second sprint.",
     ["TradingRoom.jsx"]),
    (441, "U0PRIYA", "Charts only. Don't gold-plate. AdminPortal can stay as it is until it blocks someone.",
     ["TradingRoom.jsx", "AdminPortal.jsx"]),

    # --- payments / settlement ------------------------------------------
    (520, "U0SANA", "Settlement needs an audit trail. A reviewer has to see who approved a payout and when.",
     []),
    (527, "U0DANIEL", "Every payout row gets an actor and a state transition. No silent updates.",
     ["backend/app/main.py"]),
    (534, "U0INES", "Is there a reconciliation job or is that manual?",
     []),
    (539, "U0DANIEL", "Manual for now, and I don't love it. Flagging it as a risk.",
     []),
    (546, "U0SANA", "Then it's on the list for next quarter. Manual reconciliation doesn't survive an audit.",
     []),

    # --- incident --------------------------------------------------------
    (640, "U0PRIYA", "Incident: the exchange rates went stale on Saturday and quotes were wrong for about an hour.",
     []),
    (647, "U0TOM", "Confirmed. The cache had no expiry and nothing refreshed it.",
     ["backend/app/main.py"]),
    (653, "U0DANIEL", "Root cause is the fetch being fire and forget. Nothing noticed the failure.",
     ["backend/app/main.py"]),
    (660, "U0INES", "Did anyone see wrong numbers and act on them?",
     []),
    (666, "U0SANA", "One builder reported it within the hour. We got lucky.",
     []),
    (673, "U0PRIYA", "Fix is a bounded cache and an alert when a fetch fails. Adding it to this sprint.",
     ["backend/app/main.py"]),
    (680, "U0TOM", "I'll take it. Writing it down so we don't rediscover this in six months.",
     ["backend/app/main.py"]),

    # --- metrics ---------------------------------------------------------
    (750, "U0SANA", "What are we actually measuring for launch?",
     []),
    (757, "U0PRIYA", "Time to first listing, and the share of listings that reach settlement without manual help.",
     []),
    (764, "U0TOM", "Second one will be ugly early. Manual reconciliation means manual settlement.",
     []),
    (771, "U0INES", "Ugly and measured beats aspirational and unmeasured.",
     []),

    # --- onboarding / who owns what -------------------------------------
    (830, "U0PRIYA", "Onboarding notes: backend is Daniel, frontend is Mei, governance and audit is Sana.",
     []),
    (837, "U0DANIEL", "Add Tom for exchange and rates.",
     ["backend/app/main.py"]),
    (844, "U0MEI", "And me for the web surface. Joel is the person to ask about build tooling.",
     ["Navbar.jsx", "TradingRoom.jsx"]),
    (851, "U0JOEL", "I'll write the build doc so people stop fighting Vite config.",
     ["package.json"]),

    # --- trade-offs pushed back on -------------------------------------
    (920, "U0INES", "Reminder that we deliberately did not build a notification service this quarter.",
     []),
    (927, "U0SANA", "That was a real cost. Support finds out about failed payouts from the customer.",
     []),
    (933, "U0PRIYA", "It was scope, not a technical objection. Revisit when settlement volume justifies it.",
     []),
    (940, "U0DANIEL", "Worth noting what we gave up: no in-app alerts and no retry on failed webhooks.",
     []),

    # --- close -----------------------------------------------------------
    (1000, "U0PRIYA", "Good week. Auth decision is written down, TradingRoom is split, the rates bug has an owner.",
     ["AuthService", "TradingRoom.jsx"]),
    (1007, "U0MEI", "Landing and Navbar are ready for review whenever someone has a minute.",
     ["Landing.jsx", "Navbar.jsx"]),
    (1014, "U0JOEL", "I'll review this afternoon.",
     ["Landing.jsx", "Navbar.jsx"]),
    (1021, "U0SANA", "Reminder the ADR needs updating with the OTP rationale before we forget why.",
     ["01-TECHNICAL-ARCHITECTURE.md", "AuthService"]),
    (1028, "U0DANIEL", "Done. It's in the architecture doc with the objection recorded.",
     ["01-TECHNICAL-ARCHITECTURE.md"]),

    # --- data model ------------------------------------------------------
    (1100, "U0DANIEL", "Data model review. Property, Listing, Exchange, Settlement, User.",
     []),
    (1107, "U0SANA", "Settlement needs an explicit state, not a boolean paid flag.",
     []),
    (1114, "U0DANIEL", "Added a state column with the transitions written down.",
     ["backend/app/main.py"]),
    (1121, "U0TOM", "Exchange model: are rates live or snapshot? This decides whether we store a history table.",
     []),
    (1128, "U0INES", "Snapshot. If we store live we are a market data provider and that is a different business.",
     []),
    (1135, "U0DANIEL", "Snapshot agreed. One row per fetch, timestamped.",
     ["backend/app/main.py"]),

    # --- deployment ------------------------------------------------------
    (1200, "U0JOEL", "Build is green on the branch but the preview deploys are failing on env vars.",
     ["package.json"]),
    (1207, "U0MEI", "The client needs the API base URL at build time. I hardcoded it for staging once.",
     ["package.json"]),
    (1214, "U0JOEL", "Hardcoding a URL into a bundle is how you ship someone else's config.",
     ["package.json"]),
    (1221, "U0MEI", "Fair. It's an env var now and documented.",
     ["package.json"]),
    (1228, "U0PRIYA", "No credentials in the client, ever. The browser cannot hold a database password.",
     ["package.json"]),

    # --- performance -----------------------------------------------------
    (1300, "U0INES", "TradingRoom took eleven seconds on a cold load. That is not shippable.",
     ["TradingRoom.jsx"]),
    (1307, "U0TOM", "The chart library is the weight, not our code.",
     ["TradingRoom.jsx"]),
    (1314, "U0JOEL", "Lazy load the chart. It is below the fold for most people anyway.",
     ["TradingRoom.jsx"]),
    (1321, "U0MEI", "Done. Six seconds, still slow but tolerable.",
     ["TradingRoom.jsx"]),
    (1328, "U0INES", "Six is still a number I would have to explain to a customer.",
     ["TradingRoom.jsx"]),

    # --- security --------------------------------------------------------
    (1400, "U0SANA", "Security pass before launch. What is the rate limit on the OTP send?",
     ["send_auth_otp"]),
    (1407, "U0DANIEL", "None yet. That is a gap.",
     ["send_auth_otp"]),
    (1414, "U0SANA", "Then someone can burn our SMS budget in an afternoon. Rate limit before launch.",
     ["send_auth_otp"]),
    (1421, "U0DANIEL", "Per number, five an hour. Added.",
     ["send_auth_otp"]),
    (1428, "U0SANA", "Good. That was the real finding. Everything else was fine.",
     ["send_auth_otp"]),

    # --- bug bash --------------------------------------------------------
    (1500, "U0PRIYA", "Bug bash Thursday. Everyone logs what they find, no judgement on who wrote it.",
     []),
    (1507, "U0MEI", "Found two: the sidebar does not close on mobile, and empty states say nothing.",
     ["Sidebar.jsx"]),
    (1514, "U0TOM", "Found one. Dates render in UTC and look like yesterday for anyone east of here.",
     ["TradingRoom.jsx"]),
    (1521, "U0DANIEL", "That one is mine. Timestamps were stored naive.",
     ["backend/app/main.py"]),
    (1528, "U0JOEL", "And the favicon is still the default. Embarrassing.",
     ["index.html"]),
    (1535, "U0PRIYA", "The UTC one is the only real bug. Rest is polish.",
     ["backend/app/main.py"]),

    # --- docs ------------------------------------------------------------
    (1600, "U0SANA", "Can we stop answering the same onboarding questions in here every week?",
     []),
    (1607, "U0PRIYA", "Write it down properly instead. One page per area, linked from the README.",
     ["README.md"]),
    (1614, "U0MEI", "I will do the frontend page.",
     ["README.md"]),
    (1621, "U0DANIEL", "Backend page is mine.",
     ["README.md"]),
    (1628, "U0SANA", "And a page on how audit works, because support keeps asking me.",
     ["README.md"]),

    # --- retrospective ---------------------------------------------------
    (1700, "U0PRIYA", "Retro. What went well?",
     []),
    (1707, "U0MEI", "The data model week. We argued once, on paper, and avoided a month of rework.",
     []),
    (1714, "U0DANIEL", "Writing the auth decision down. That comment stopped two reversals.",
     ["AuthService"]),
    (1721, "U0JOEL", "Splitting TradingRoom early, before it got worse.",
     ["TradingRoom.jsx"]),
    (1728, "U0SANA", "What went badly?",
     ["AuthService"]),
    (1735, "U0SANA", "We argued OTP in here and nearly lost it. It should have been a decision thread, not a chat thread.",
     ["AuthService"]),
    (1742, "U0PRIYA", "Agreed. Decisions go in a doc from now on. Chat is for the arguing, not the record.",
     ["01-TECHNICAL-ARCHITECTURE.md"]),
    (1749, "U0TOM", "And the rates bug was ours to catch in review. Nobody looked at the cache.",
     ["backend/app/main.py"]),
    (1756, "U0DANIEL", "Cache expiry and a fetch alert. Both on me.",
     ["backend/app/main.py"]),
    (1763, "U0PRIYA", "Next quarter: notifications, self-service password reset, and automated reconciliation.",
     []),
    (1770, "U0SANA", "That is a good quarter. Those three are the ones support complains about.",
     []),
    (1777, "U0MEI", "Thanks all. Same time next week.",
     []),
]


def _build_messages() -> list[dict]:
    people = {user: (author, handle) for user, author, handle in PEOPLE}
    messages = []
    for offset, user, text, about in SCRIPT:
        author, handle = people[user]
        stamp = START + timedelta(minutes=offset)
        ts = f"{stamp.timestamp():.6f}"
        messages.append(
            {
                "channel_id": CHANNEL["channel_id"],
                "channel_name": CHANNEL["channel_name"],
                "text": text,
                "ts": ts,
                "user": user,
                # Plain name, because that is what the Person node is called and
                # the ingest attributes by resolving the author against the
                # graph. The handle lives on the message row instead.
                "author": author,
                "permalink": f"https://app.slack.com/archives/{CHANNEL['channel_id']}/p{ts.replace('.', '')}",
                "thread_ts": None,
                "posted_at": stamp.isoformat(),
                "about": about,
            }
        )
    return messages


def _ensure_people(graph) -> None:
    """Create the team as Person nodes so messages can be attributed.

    The ingestor deliberately leaves an author unattributed rather than
    inventing a person, so a message has to have someone to resolve to. These
    are the fictional team this dataset is built around, not discovered facts.
    """
    for user, name, handle in PEOPLE:
        graph.query(
            """
            MERGE (p:Person {id: $person_id})
            SET p.name = $name,
                p.handle = $handle,
                p.slack_user_id = $user,
                p.source = 'seed'
            """,
            {
                "person_id": f"person_{handle}",
                "name": name,
                "handle": handle,
                "user": user,
            },
        )


def main() -> int:
    session = SessionLocal()
    try:
        existing = session.query(SlackMessage).filter(
            SlackMessage.channel_id == CHANNEL["channel_id"]
        ).count()
    finally:
        session.close()

    if existing:
        print(
            f"{CHANNEL['channel_name']} already holds {existing} message(s). "
            "Re-running would double them; pass --force after a wipe if you mean it."
        )
        return 1

    messages = _build_messages()
    ingestor = DocumentIngestor(graph_gateway)
    _ensure_people(graph_manager.get_or_create_graph())
    summary = ingestor.ingest_slack_messages(messages)
    print(
        f"seeded {summary['messages']} message(s): "
        f"{summary['attributed']} attributed, {summary['linked']} linked, "
        f"{summary['skipped']} skipped"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())