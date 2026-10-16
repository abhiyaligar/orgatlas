"""User-invoked MCP prompt templates that guide an agent through retrieval."""

from __future__ import annotations


def register_prompts(server) -> None:
    """Attach planning prompts to an MCPServer instance."""

    @server.prompt(
        name="plan_architecture_aligned_change",
        title="Plan an architecture-aligned change",
        description=(
            "Retrieve ownership, dependencies and prior incidents before proposing a change."
        ),
    )
    def plan_architecture_aligned_change(change_summary: str, target: str = "") -> str:
        return f"""You are planning a change to {target or "an unspecified system"}.

Summary of the intended change:
{change_summary}

Before proposing an implementation, use these tools in order:

1. `get_architecture_context` — identify the system, its owner and linked decisions.
2. `find_owner_and_expertise` — find who owns it and who has worked on it recently.
3. `assess_change_impact` — get the bounded dependency and incident picture.
4. `trace_technical_decision` — read the rationale for any decision that constrains you.

Then state, explicitly:
* the assumptions you are making and which tool output does not support them;
* the risk areas and the prior incidents most relevant to this change;
* the validation you would run before proposing the change.

This server is read-only. It cannot edit code, create tickets, or approve a
change. Its output is advisory context, not change approval.
"""

    @server.prompt(
        name="investigate_service_incident",
        title="Investigate a production issue",
        description="Trace impact, ownership and change history for a failing service.",
    )
    def investigate_service_incident(
        service_identifier: str, symptoms: str = "", occurred_at: str = ""
    ) -> str:
        window = f" around {occurred_at}" if occurred_at else ""
        return f"""Investigate a production issue affecting {service_identifier}.

Reported symptoms:
{symptoms or "(not supplied)"}

Work in this order:

1. `assess_change_impact` — establish the blast radius and any associated incidents.
2. `get_repo_dependency_impact` — check whether a dependent repository is involved.
3. `assess_file_risk` — identify the most-changed code in the affected area.
4. `trace_change_origin` — read the most recent change to the suspicious file.

The investigation window{window} is important: correlate what changed with
when the symptoms started, and say so explicitly if the history does not cover
the window or if the evidence is inconclusive.

Report what the evidence shows, what it does not show, and what a human should
check next. Do not assert a root cause that the retrieved evidence does not
support.

This server is read-only: it cannot change code, roll back a deployment, or
open an incident. Recommend the action and let a human carry it out.
"""

    @server.prompt(
        name="onboard_to_engineering_team",
        title="Onboard to an engineering team",
        description="Walk an agent through a team's systems, owners and learning path.",
    )
    def onboard_to_engineering_team(team_id: str, role: str = "engineer") -> str:
        return f"""You are onboarding a new {role} onto {team_id}.

Use these tools in order:

1. `get_onboarding_context` — the learning path, owned systems, people and reading.
2. `get_architecture_context` on each service in scope — why it exists and who owns it.
3. `trace_technical_decision` on the decisions that shaped the main services.
4. `assess_file_risk` on the core code paths — what changes most and who knows them.

Then produce a short orientation covering:
* the systems this role owns and the boundaries between them;
* the people to talk to first and why;
* the decisions that a newcomer would otherwise violate;
* the first task that would give useful context.

Prefer recorded evidence over general software-engineering advice. If the
graph does not cover something, say so rather than filling the gap.

This server is read-only. Use it to orient, then read the actual code before
making any change.
"""