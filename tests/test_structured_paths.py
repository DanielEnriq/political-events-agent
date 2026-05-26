"""Path-coverage test for llm/structured.py.

Proves — without a network call — that both the native structured-outputs
beta path and the forced-tool-use fallback path return Pydantic-validated
objects. Uses mocks for the Anthropic client.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from revere_agent.llm.structured import call_with_structured_output
from revere_agent.schemas import IntakeAnalysis


# A valid IntakeAnalysis payload reused by both tests.
VALID_INTAKE = {
    "canonical_query": "What happened with the 2023 debt ceiling deal?",
    "modality": "factual",
    "user_stated_stance": None,
    "multi_turn_dependency": False,
    "notes": "Direct factual question.",
}


def test_native_structured_outputs_path_returns_parsed_model() -> None:
    """When client.beta.messages.parse returns a parsed Pydantic object,
    the helper returns it directly.
    """
    parsed_obj = IntakeAnalysis(**VALID_INTAKE)
    fake_response = SimpleNamespace(parsed=parsed_obj)

    client = MagicMock()
    client.beta.messages.parse.return_value = fake_response

    result = call_with_structured_output(
        client,
        model="claude-sonnet-4-5",
        system="charter…",
        user="question…",
        output_schema=IntakeAnalysis,
    )

    assert isinstance(result, IntakeAnalysis)
    assert result.canonical_query == VALID_INTAKE["canonical_query"]
    client.beta.messages.parse.assert_called_once()


def test_tool_use_fallback_path_parses_tool_input() -> None:
    """When the native beta path raises, the helper falls back to forced
    tool-use and parses the tool's `input` field as the Pydantic model.
    """
    # Make the native path explode.
    client = MagicMock()
    client.beta.messages.parse.side_effect = RuntimeError("beta not available")

    # Construct a fake messages.create response containing a tool_use block.
    tool_use_block = SimpleNamespace(
        type="tool_use",
        name="emit_IntakeAnalysis",
        input=VALID_INTAKE,
    )
    fake_response = SimpleNamespace(
        content=[tool_use_block],
        stop_reason="tool_use",
    )
    client.messages.create.return_value = fake_response

    result = call_with_structured_output(
        client,
        model="claude-sonnet-4-5",
        system="charter…",
        user="question…",
        output_schema=IntakeAnalysis,
    )

    assert isinstance(result, IntakeAnalysis)
    assert result.modality == "factual"

    # Verify the fallback forced the right tool with tool_choice.
    call_kwargs = client.messages.create.call_args.kwargs
    assert call_kwargs["tool_choice"] == {
        "type": "tool",
        "name": "emit_IntakeAnalysis",
    }
    assert call_kwargs["tools"][0]["name"] == "emit_IntakeAnalysis"
    # The tool's input_schema must be the Pydantic JSON Schema for IntakeAnalysis.
    schema = call_kwargs["tools"][0]["input_schema"]
    assert schema["type"] == "object"
    assert schema.get("additionalProperties") is False
    assert "canonical_query" in schema["properties"]
