"""Stage 1 — Intake & Context Normalization."""

from __future__ import annotations

from revere_agent.llm.provider import LLMProvider
from revere_agent.schemas import IntakeAnalysis

from ._common import run_llm_stage


def _format_history(history: list[tuple[str, str]] | None) -> str:
    """Render history as a compact transcript. Empty marker if none."""
    if not history:
        return "(none — this is the first turn)"
    lines: list[str] = []
    for role, content in history:
        lines.append(f"{role.upper()}: {content}")
    return "\n".join(lines)


def run_s1_intake(
    provider: LLMProvider,
    user_message: str,
    history: list[tuple[str, str]] | None = None,
) -> IntakeAnalysis:
    """Normalize the query, classify modality, resolve references."""
    user_content = (
        f"User message:\n{user_message}\n\n"
        f"Recent conversation history:\n{_format_history(history)}"
    )
    return run_llm_stage(
        provider=provider,
        stage_id="s1_intake",
        user_content=user_content,
        output_schema=IntakeAnalysis,
    )
