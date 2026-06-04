"""Stage 2 — Scope Reasoning.

The anti-keyword-matching stage. Receives the IntakeAnalysis and decides
whether the request falls within the agent's charter, with full reasoning.
"""

from __future__ import annotations

from revere_agent.llm.provider import LLMProvider
from revere_agent.schemas import IntakeAnalysis, ScopeDecision

from ._common import run_llm_stage
from .s1_intake import _format_history


def run_s2_scope(
    provider: LLMProvider,
    intake: IntakeAnalysis,
    history: list[tuple[str, str]] | None = None,
    *,
    max_tokens: int = 1024,
) -> ScopeDecision:
    """Decide in-scope by reasoning about charter clauses, not keywords.

    Intentionally stays on the default model (sonnet-main). Scope decisions
    warrant the stronger model: a false refusal on a valid political question
    is a hard failure. Do not pass a haiku alias here.
    """
    user_content = (
        f"Intake analysis (S1 output):\n{intake.model_dump_json(indent=2)}\n\n"
        f"Recent conversation history:\n{_format_history(history)}\n\n"
        "Apply the Scope Reasoning instructions above. Return a "
        "ScopeDecision."
    )
    return run_llm_stage(
        provider=provider,
        stage_id="s2_scope",
        user_content=user_content,
        output_schema=ScopeDecision,
        max_tokens=max_tokens,
    )
