"""Common stage-runner helper.

Every reasoning stage has the same outer shape:
  1. Load the charter + the stage-specific instruction.
  2. Format the inputs from prior stages into a user-turn message.
  3. Call the LLM with structured output bound to the stage's Pydantic schema.
  4. Return the validated Pydantic object.

This helper extracts (1) and (3) so each stage module only owns (2) — the
stage-specific framing of inputs. It keeps the stage files tiny and makes
the orchestrator-vs-LLM responsibility split obvious: orchestrator owns
control flow; stages own how to ask; the LLM owns what to think.
"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from revere_agent.llm.provider import LLMProvider, ModelAlias
from revere_agent.prompts.registry import load_prompt

T = TypeVar("T", bound=BaseModel)


def run_llm_stage(
    *,
    provider: LLMProvider,
    stage_id: str,
    user_content: str,
    output_schema: type[T],
    model_alias: ModelAlias = "sonnet-main",
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> T:
    """Run a single LLM reasoning stage and return its validated output.

    Composes the system message as `<charter>\\n\\n---\\n\\n<stage_instr>`.
    The charter is the agent's identity; the stage instruction is what to
    do right now. Keeping the charter in every system prompt means each
    stage operates with the same six political-neutrality principles in
    context.
    """
    charter = load_prompt("system_charter")
    stage_instr = load_prompt(stage_id)
    system = f"{charter}\n\n---\n\n{stage_instr}"

    return provider.call_structured(
        system=system,
        user=user_content,
        output_schema=output_schema,
        model_alias=model_alias,
        temperature=temperature,
        max_tokens=max_tokens,
    )
