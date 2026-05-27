"""Stage 3 — Plan & Search Decision."""

from __future__ import annotations

from revere_agent.llm.provider import LLMProvider
from revere_agent.schemas import IntakeAnalysis, SearchPlan

from ._common import run_llm_stage


def run_s3_plan_search(
    provider: LLMProvider,
    intake: IntakeAnalysis,
) -> SearchPlan:
    """Decide whether external grounding is needed; emit up to 3 queries."""
    user_content = (
        f"Canonical query:\n{intake.canonical_query}\n\n"
        f"Intake notes (S1):\n{intake.notes}\n\n"
        f"Modality: {intake.modality}\n\n"
        "Apply the Plan & Search Decision instructions above. Return a "
        "SearchPlan."
    )
    return run_llm_stage(
        provider=provider,
        stage_id="s3_plan_search",
        user_content=user_content,
        output_schema=SearchPlan,
    )
