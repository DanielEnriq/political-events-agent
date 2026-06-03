"""Stage 3 — Plan & Search Decision."""

from __future__ import annotations

from revere_agent.llm.provider import LLMProvider, ModelAlias
from revere_agent.schemas import IntakeAnalysis, SearchPlan

from ._common import run_llm_stage


def run_s3_plan_search(
    provider: LLMProvider,
    intake: IntakeAnalysis,
    *,
    model_alias: ModelAlias = "sonnet-main",
    max_tokens: int = 1024,
) -> SearchPlan:
    """Decide whether external grounding is needed; emit up to 3 queries.

    model_alias defaults to "sonnet-main" for backward compatibility.
    The orchestrator passes "haiku-fast" because S3 is a structured planning
    decision (binary needs_search + a short query list) with bounded output.
    Rollback: remove the model_alias override in orchestrator.py.
    """
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
        model_alias=model_alias,
        max_tokens=max_tokens,
    )
