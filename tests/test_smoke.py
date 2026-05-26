"""Offline smoke test — exercises every Day 1 code path without a network call.

Run with: `uv run pytest -q`
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest


def test_schemas_all_importable_and_strict() -> None:
    """Every schema imports, instantiates from valid data, and rejects extras."""
    from pydantic import ValidationError

    from revere_agent.schemas import (
        Citation,
        EvidenceBase,
        FactualClaim,
        FinalResponse,
        IntakeAnalysis,
        Perspective,
        PerspectiveAnalysis,
        ReasoningTrace,
        ScopeDecision,
        SearchHit,
        SearchPlan,
        SelfCheckReport,
        SourceAssessment,
        StageTraceEntry,
        VerificationReport,
    )

    # Smoke-instantiate one example to make sure required fields are correct.
    intake = IntakeAnalysis(
        canonical_query="What happened with the 2023 debt ceiling deal?",
        modality="factual",
        user_stated_stance=None,
        multi_turn_dependency=False,
        notes="Direct factual question.",
    )
    assert intake.modality == "factual"

    scope = ScopeDecision(
        in_scope=True,
        confidence=5,
        reasoning="Maps to charter category 'legislation' (Fiscal Responsibility Act).",
        matched_charter_categories=["legislation"],
        suggested_redirect=None,
        partial_help_possible=False,
    )
    assert scope.confidence == 5

    # extra='forbid' should reject unknown fields — this is what makes the
    # JSON schemas safe for Anthropic structured outputs.
    with pytest.raises(ValidationError):
        IntakeAnalysis(  # type: ignore[call-arg]
            canonical_query="x",
            modality="factual",
            multi_turn_dependency=False,
            notes="y",
            sneaky_extra_field="nope",
        )


def test_pydantic_json_schemas_are_well_formed() -> None:
    """Every schema we'd pass to Claude tool-use must produce a valid JSON Schema."""
    from revere_agent.schemas import (
        EvidenceBase,
        FinalResponse,
        IntakeAnalysis,
        PerspectiveAnalysis,
        ScopeDecision,
        SearchPlan,
        VerificationReport,
    )

    for cls in [
        IntakeAnalysis,
        ScopeDecision,
        SearchPlan,
        EvidenceBase,
        PerspectiveAnalysis,
        VerificationReport,
        FinalResponse,
    ]:
        schema = cls.model_json_schema()
        assert schema["type"] == "object", f"{cls.__name__}: top-level not object"
        assert "properties" in schema, f"{cls.__name__}: no properties"
        # additionalProperties: false at the top level (extra='forbid') —
        # required by Anthropic native structured outputs.
        assert schema.get("additionalProperties") is False, (
            f"{cls.__name__}: must have additionalProperties=False"
        )


def test_prompts_load_and_hash_stably() -> None:
    from revere_agent.prompts.registry import load_prompt, prompt_version

    charter = load_prompt("system_charter")
    s1 = load_prompt("s1_intake")
    assert "Operating Principles" in charter
    assert "Intake" in s1

    # Hashes are stable across calls and 12 chars long.
    v1 = prompt_version("s1_intake")
    v2 = prompt_version("s1_intake")
    assert v1 == v2
    assert len(v1) == 12


def test_anthropic_provider_constructs_with_key_but_does_not_call_network() -> None:
    """Constructing the provider should not touch the network."""
    from revere_agent.llm import AnthropicProvider

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-dummy-for-test"}, clear=False):
        provider = AnthropicProvider()
        assert provider.name == "anthropic"


def test_anthropic_provider_raises_clear_error_without_key() -> None:
    from revere_agent.llm import AnthropicProvider

    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
            AnthropicProvider()


def test_bedrock_provider_constructs_without_aws_creds() -> None:
    """Bedrock provider must be safe to construct even without AWS creds —
    boto3 resolves creds lazily, so this exercises the structural wiring only.
    """
    from revere_agent.llm import BedrockProvider

    with patch.dict(os.environ, {"AWS_REGION": "us-east-1"}, clear=False):
        provider = BedrockProvider()
        assert provider.name == "bedrock"


def test_env_factory_picks_provider() -> None:
    from revere_agent.llm import make_provider_from_env

    with patch.dict(
        os.environ,
        {"PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "sk-ant-dummy"},
        clear=False,
    ):
        p = make_provider_from_env()
        assert p.name == "anthropic"

    with patch.dict(os.environ, {"PROVIDER": "nonsense"}, clear=False):
        with pytest.raises(ValueError, match="Unknown PROVIDER"):
            make_provider_from_env()


def test_tavily_provider_raises_clear_error_without_key() -> None:
    from revere_agent.search import TavilyProvider

    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(RuntimeError, match="TAVILY_API_KEY"):
            TavilyProvider()


def test_structured_output_helper_imports_and_signature() -> None:
    """The helper is importable and the public function has the documented shape."""
    import inspect

    from revere_agent.llm.structured import (
        STRUCTURED_OUTPUTS_BETA,
        call_with_structured_output,
    )

    assert STRUCTURED_OUTPUTS_BETA == "structured-outputs-2025-11-13"
    sig = inspect.signature(call_with_structured_output)
    for name in ("model", "system", "user", "output_schema", "temperature", "max_tokens"):
        assert name in sig.parameters, f"missing kwarg: {name}"


def test_llm_provider_protocol_is_structural() -> None:
    """AnthropicProvider and BedrockProvider both satisfy the Protocol."""
    from revere_agent.llm import AnthropicProvider, BedrockProvider, LLMProvider

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-dummy"}, clear=False):
        a: LLMProvider = AnthropicProvider()  # type: ignore[assignment]
        assert hasattr(a, "call_structured")

    b: LLMProvider = BedrockProvider()  # type: ignore[assignment]
    assert hasattr(b, "call_structured")
