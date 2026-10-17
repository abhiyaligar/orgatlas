"""Prompts that constrain the model to the evidence it was given.

The model is told what it may use and how to mark it. It is not asked to
decide what is true — that already happened during retrieval.
"""

from __future__ import annotations

from typing import Dict, List

from app.llm.client import SynthesisRequest, evidence_package_payload

SYSTEM_PROMPT = (
    "You are OrgAtlas, an engineering knowledge synthesizer. Answer ONLY using the "
    "provided evidence graph records and source documents. Every factual claim MUST "
    "cite a source identifier in square brackets, exactly as written in the evidence, "
    "for example [doc_rfp_kafka]. If the evidence does not contain the answer, say "
    "explicitly that insufficient evidence was found. Never invent a source "
    "identifier, a person, a system, or an incident that is not in the evidence."
)

NO_EVIDENCE_PROMPT = (
    "You are OrgAtlas. The retrieval step found no evidence for this question. "
    "Reply with exactly one short sentence stating that insufficient evidence was "
    "found, and do not speculate."
)


def build_synthesis_messages(request: SynthesisRequest) -> List[Dict[str, str]]:
    """Build the chat messages for one synthesis request."""
    if not request.citations:
        return [
            {"role": "system", "content": NO_EVIDENCE_PROMPT},
            {"role": "user", "content": f"Question: {request.question}"},
        ]

    payload = evidence_package_payload(request)
    user = (
        f"Question: {request.question}\n\n"
        f"Retrieved facts:\n{request.facts}\n\n"
        "Citable sources (these identifiers are the only ones you may cite):\n"
        f"{payload}"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]