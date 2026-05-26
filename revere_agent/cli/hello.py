"""Day 1 CLI: prove the stack works end-to-end.

Loads .env, constructs the configured LLMProvider, runs Stage 1 (intake)
on a sample query, prints the parsed IntakeAnalysis. This is the smallest
thing that exercises every piece built on Day 1:
  - provider abstraction & env-driven selection
  - structured-output helper (native beta or tool-use fallback)
  - prompt registry (load + hash)
  - Pydantic schema validation
"""

from __future__ import annotations

import sys

from dotenv import load_dotenv

from revere_agent.llm import make_provider_from_env
from revere_agent.prompts.registry import load_prompt, prompt_version
from revere_agent.schemas import IntakeAnalysis

# Default sample query — chosen so the IntakeAnalysis fields exercise:
# a real political topic, no pronouns, single modality, no stated stance.
DEFAULT_SAMPLE = (
    "What happened with the debt ceiling negotiations in 2023? "
    "What were the key positions of both parties?"
)


def main() -> int:
    load_dotenv()  # picks up .env in the cwd or any parent

    user_message = " ".join(sys.argv[1:]).strip() or DEFAULT_SAMPLE

    try:
        provider = make_provider_from_env()
    except RuntimeError as e:
        print(f"[setup error] {e}", file=sys.stderr)
        return 2

    # Assemble system prompt = charter + S1-specific instruction.
    charter = load_prompt("system_charter")
    intake_instr = load_prompt("s1_intake")
    system_prompt = f"{charter}\n\n---\n\n{intake_instr}"

    # The user-turn content given to the model is the user's actual message
    # plus the (empty) history. Future stages will pass richer state.
    user_turn = (
        f"User message:\n{user_message}\n\n"
        f"Conversation history: (none — this is the first turn)"
    )

    print("=" * 72)
    print(f"Provider:        {provider.name}")
    print(f"Prompt version:  s1_intake@{prompt_version('s1_intake')}")
    print(f"User message:    {user_message}")
    print("=" * 72)
    print("Calling model (Stage 1: intake)…")

    try:
        result: IntakeAnalysis = provider.call_structured(
            system=system_prompt,
            user=user_turn,
            output_schema=IntakeAnalysis,
            model_alias="sonnet-main",
            temperature=0.3,
            max_tokens=1024,
        )
    except Exception as e:  # noqa: BLE001 — surface any error clearly to the user
        print(f"\n[call error] {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    print("\nParsed IntakeAnalysis (Pydantic-validated):")
    print("-" * 72)
    print(result.model_dump_json(indent=2))
    print("-" * 72)
    print("OK ✓  Stack assembled end-to-end.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
