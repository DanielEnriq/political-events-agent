"""Stage 7 — final composition plus neutrality self-check."""

from __future__ import annotations

from revere_agent.llm.provider import LLMProvider
from revere_agent.schemas import (
    EvidenceBase,
    FinalResponse,
    IntakeAnalysis,
    PerspectiveAnalysis,
    VerificationReport,
)

from ._common import run_llm_stage


def run_s7_compose_check(
    provider: LLMProvider,
    intake: IntakeAnalysis,
    evidence: EvidenceBase,
    perspectives: PerspectiveAnalysis,
    verification: VerificationReport,
) -> FinalResponse:
    """Compose user-facing answer with citation + self-check constraints."""
    no_retrieved_sources = not evidence.assessments
    user_content = (
        f"Canonical query:\n{intake.canonical_query}\n\n"
        f"No retrieved sources: {'YES' if no_retrieved_sources else 'NO'}\n\n"
        f"Evidence base (S4):\n{evidence.model_dump_json(indent=2)}\n\n"
        f"Perspective analysis (S5):\n{perspectives.model_dump_json(indent=2)}\n\n"
        f"Verification report (S6):\n{verification.model_dump_json(indent=2)}\n\n"
        "Apply Stage 7 instructions and return a FinalResponse."
    )
    return run_llm_stage(
        provider=provider,
        stage_id="s7_compose_check",
        user_content=user_content,
        output_schema=FinalResponse,
        temperature=0.4,
    )
