"""LLM-as-judge functions for Revere behavioral evaluation.

Stage C2: real judges using the existing LLMProvider abstraction.

Model: sonnet-judge (maps to claude-sonnet-4-5 in AnthropicProvider).
Temperature: 0.0 for deterministic scoring.

Limitation: judges evaluate trace-relative grounding only. They do not
independently verify source web pages or access the internet.
"""

from __future__ import annotations

from typing import Any

from evals.judge_prompts import (
    build_boundary_prompt,
    build_even_handedness_prompt,
    build_perspective_quality_prompt,
    build_refusal_prompt,
    build_source_grounding_prompt,
)
from evals.judge_schemas import (
    BoundaryResult,
    EvenHandednessResult,
    PerspectiveQualityResult,
    RefusalResult,
    SourceGroundingResult,
)
from evals.trace_summary import TraceSummary

# Judge model alias. Maps to claude-sonnet-4-5 in the Anthropic provider.
# Kept separate from sonnet-main so the judge model can be swapped independently.
_JUDGE_ALIAS = "sonnet-judge"
_JUDGE_TEMP = 0.0
_JUDGE_MAX_TOKENS = 2048


def judge_even_handedness(
    provider: Any,
    scenario: dict[str, Any],
    payload_a: dict[str, Any],
    payload_b: dict[str, Any],
) -> EvenHandednessResult:
    """Compare paired_a and paired_b responses for even-handedness.

    paired_a = response to lean-A prompt (e.g., left-leaning framing).
    paired_b = response to lean-B prompt (e.g., right-leaning framing).

    Does NOT compare neutral vs leaning — that would conflate response quality
    with framing robustness.
    """
    trace_a = TraceSummary.from_complete_payload(payload_a)
    trace_b = TraceSummary.from_complete_payload(payload_b)

    prompt_a = scenario.get("paired_prompt") or ""
    prompt_b = scenario.get("paired_prompt_b") or ""

    system, user = build_even_handedness_prompt(
        scenario=scenario,
        prompt_a=prompt_a,
        payload_a=payload_a,
        trace_a=trace_a,
        prompt_b=prompt_b,
        payload_b=payload_b,
        trace_b=trace_b,
    )

    return provider.call_structured(
        system=system,
        user=user,
        output_schema=EvenHandednessResult,
        model_alias=_JUDGE_ALIAS,
        temperature=_JUDGE_TEMP,
        max_tokens=_JUDGE_MAX_TOKENS,
    )


def judge_perspective_quality(
    provider: Any,
    scenario: dict[str, Any],
    neutral_payload: dict[str, Any],
) -> PerspectiveQualityResult:
    """Evaluate quality of steelmanning and perspective coverage."""
    trace = TraceSummary.from_complete_payload(neutral_payload)
    neutral_prompt = scenario.get("prompt") or ""

    system, user = build_perspective_quality_prompt(
        scenario=scenario,
        neutral_prompt=neutral_prompt,
        payload=neutral_payload,
        trace=trace,
    )

    return provider.call_structured(
        system=system,
        user=user,
        output_schema=PerspectiveQualityResult,
        model_alias=_JUDGE_ALIAS,
        temperature=_JUDGE_TEMP,
        max_tokens=_JUDGE_MAX_TOKENS,
    )


def judge_refusal(
    provider: Any,
    scenario: dict[str, Any],
    payload: dict[str, Any],
) -> RefusalResult:
    """Check for over-refusal on an in-scope political question."""
    trace = TraceSummary.from_complete_payload(payload)
    prompt = scenario.get("prompt") or ""

    system, user = build_refusal_prompt(
        scenario=scenario,
        prompt=prompt,
        payload=payload,
        trace=trace,
    )

    return provider.call_structured(
        system=system,
        user=user,
        output_schema=RefusalResult,
        model_alias=_JUDGE_ALIAS,
        temperature=_JUDGE_TEMP,
        max_tokens=_JUDGE_MAX_TOKENS,
    )


def judge_source_grounding(
    provider: Any,
    scenario: dict[str, Any],
    neutral_payload: dict[str, Any],
) -> SourceGroundingResult:
    """Evaluate trace-relative source grounding and hedging adequacy."""
    trace = TraceSummary.from_complete_payload(neutral_payload)
    neutral_prompt = scenario.get("prompt") or ""

    system, user = build_source_grounding_prompt(
        scenario=scenario,
        neutral_prompt=neutral_prompt,
        payload=neutral_payload,
        trace=trace,
    )

    return provider.call_structured(
        system=system,
        user=user,
        output_schema=SourceGroundingResult,
        model_alias=_JUDGE_ALIAS,
        temperature=_JUDGE_TEMP,
        max_tokens=_JUDGE_MAX_TOKENS,
    )


def judge_boundary(
    provider: Any,
    scenario: dict[str, Any],
    payload_t1: dict[str, Any],
    payload_t2: dict[str, Any],
) -> BoundaryResult:
    """Evaluate boundary handling across two turns."""
    trace_t1 = TraceSummary.from_complete_payload(payload_t1)
    trace_t2 = TraceSummary.from_complete_payload(payload_t2)

    # For boundary scenarios, "prompt" is used for both turns unless
    # separate prompts are defined per variant.
    prompt_t1 = scenario.get("prompt") or ""
    prompt_t2 = scenario.get("prompt") or ""

    system, user = build_boundary_prompt(
        scenario=scenario,
        prompt_t1=prompt_t1,
        payload_t1=payload_t1,
        trace_t1=trace_t1,
        prompt_t2=prompt_t2,
        payload_t2=payload_t2,
        trace_t2=trace_t2,
    )

    return provider.call_structured(
        system=system,
        user=user,
        output_schema=BoundaryResult,
        model_alias=_JUDGE_ALIAS,
        temperature=_JUDGE_TEMP,
        max_tokens=_JUDGE_MAX_TOKENS,
    )
