"""Tests for Stage C2: LLM judge infrastructure.

No real LLM calls. Uses a StubProvider that returns pre-built results.
Tests cover judge routing, prompt content, aggregate metrics, verdict logic,
and report rendering.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Type, TypeVar

import pytest
from pydantic import BaseModel

from evals.judge_prompts import (
    build_boundary_prompt,
    build_even_handedness_prompt,
    build_perspective_quality_prompt,
    build_refusal_prompt,
    build_source_grounding_prompt,
)
from evals.judge_schemas import (
    AggregateMetrics,
    BoundaryResult,
    EvalReport,
    EvenHandednessResult,
    PerspectiveQualityResult,
    RefusalResult,
    ScenarioEvalResult,
    SourceGroundingResult,
)
from evals.run_evals import (
    FixtureEntry,
    _compute_aggregate,
    _compute_verdict,
    _run_boundary_judges,
    _run_political_judges,
    build_judged_report,
    build_no_judge_report,
    group_by_scenario,
    render_report_md,
)
from evals.trace_summary import TraceSummary

T = TypeVar("T", bound=BaseModel)

_SCENARIOS_FILE = Path(__file__).parent.parent / "evals" / "scenarios.yaml"


# ── StubProvider ──────────────────────────────────────────────────────────────


@dataclass
class StubCall:
    """Records a call made to the StubProvider."""

    model_alias: str
    output_schema: type
    system: str
    user: str


class StubProvider:
    """A fake LLMProvider that returns pre-registered responses without network calls.

    Usage:
        provider = StubProvider()
        provider.register(EvenHandednessResult, EvenHandednessResult(score=0.8))
        result = provider.call_structured(system="...", user="...",
                                          output_schema=EvenHandednessResult)
        assert result.score == 0.8
    """

    name = "stub"

    def __init__(self) -> None:
        self._responses: dict[type, BaseModel] = {}
        self.calls: list[StubCall] = []

    def register(self, schema: type[T], response: T) -> None:
        self._responses[schema] = response

    def call_structured(
        self,
        *,
        system: str,
        user: str,
        output_schema: type[T],
        model_alias: str = "sonnet-judge",
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ) -> T:
        self.calls.append(StubCall(model_alias=model_alias, output_schema=output_schema, system=system, user=user))
        if output_schema in self._responses:
            return self._responses[output_schema]
        raise ValueError(f"StubProvider: no response registered for {output_schema.__name__}")


# ── Fixtures and helpers ──────────────────────────────────────────────────────


def _minimal_payload(in_scope: bool = True, answer: str = "Test answer.") -> dict[str, Any]:
    return {
        "in_scope": in_scope,
        "answer": answer,
        "citations": [{"label": "Reuters", "url": "https://reuters.com", "used_for_claim": "test"}],
        "neutrality": None,
        "residual_uncertainty": None,
        "suggested_followups": [],
        "stage_details": {
            "s2_scope": {
                "in_scope": in_scope,
                "reasoning": "Political event.",
                "matched_charter_categories": ["us_politics"],
                "suggested_redirect": None if in_scope else "Try a general search engine.",
            },
            "s5_perspectives": {
                "perspectives": [
                    {"label": "Democratic", "core_claims": ["Claim A"]},
                    {"label": "Republican", "core_claims": ["Claim B"]},
                ],
                "areas_of_consensus": ["Deficit matters"],
                "areas_of_disagreement": ["Spending cuts"],
                "empirical_vs_normative": [],
            },
            "s6_verification": {
                "factual_claims": [{"claim": "Act signed 2023", "confidence": 0.95}],
                "things_i_should_not_assert": [],
                "overall_calibration_note": "High confidence.",
            },
        },
    }


def _fixture_entry(
    scenario_id: str,
    variant: str,
    fixture_kind: str = "real_agent_run",
    in_scope: bool = True,
    answer: str = "Test answer.",
) -> FixtureEntry:
    return FixtureEntry(
        scenario_id=scenario_id,
        prompt_variant=variant,
        fixture_kind=fixture_kind,
        fixture_note="Test fixture.",
        complete_payload=_minimal_payload(in_scope=in_scope, answer=answer),
        judgment_status="pending_judgment",
        generated_at="2026-06-03T12:00:00Z",
        agent_git_sha="abc1234",
        source_file=Path("fake.yaml"),
    )


def _load_scenario(scenario_id: str) -> dict[str, Any]:
    import yaml
    with open(_SCENARIOS_FILE) as f:
        data = yaml.safe_load(f)
    for s in data.get("scenarios", []):
        if s["id"] == scenario_id:
            return s
    raise KeyError(f"Scenario not found: {scenario_id}")


# ── 1. EvenHandedness uses paired_a + paired_b, not neutral ───────────────────


def test_even_handedness_uses_paired_a_and_paired_b_not_neutral():
    """EvenHandedness judge must receive paired_a and paired_b payloads."""
    scenario = _load_scenario("debt_ceiling_2023")
    provider = StubProvider()
    provider.register(
        EvenHandednessResult,
        EvenHandednessResult(score=0.9, rationale="Both responses balanced."),
    )
    provider.register(PerspectiveQualityResult, PerspectiveQualityResult(score=0.8))
    provider.register(SourceGroundingResult, SourceGroundingResult(score=0.8))
    provider.register(RefusalResult, RefusalResult(refusal_type="n/a"))

    variants = {
        "neutral": _fixture_entry("debt_ceiling_2023", "neutral", answer="Neutral answer."),
        "paired_a": _fixture_entry("debt_ceiling_2023", "paired_a", answer="Lean-A answer."),
        "paired_b": _fixture_entry("debt_ceiling_2023", "paired_b", answer="Lean-B answer."),
    }
    result, _ = _run_political_judges(provider, scenario, variants)

    eh_calls = [c for c in provider.calls if c.output_schema is EvenHandednessResult]
    assert len(eh_calls) == 1, "EvenHandedness judge should be called exactly once"

    # The prompt must contain both lean-A and lean-B answers, NOT the neutral answer
    user_text = eh_calls[0].user
    assert "Lean-A answer" in user_text, "paired_a response must appear in EvenHandedness prompt"
    assert "Lean-B answer" in user_text, "paired_b response must appear in EvenHandedness prompt"
    assert "Neutral answer" not in user_text, "neutral response must NOT appear in EvenHandedness prompt"


# ── 2. Missing paired_b marks scenario pending ────────────────────────────────


def test_missing_paired_b_marks_scenario_pending():
    scenario = _load_scenario("debt_ceiling_2023")
    provider = StubProvider()
    provider.register(PerspectiveQualityResult, PerspectiveQualityResult(score=0.8))
    provider.register(SourceGroundingResult, SourceGroundingResult(score=0.8))
    provider.register(RefusalResult, RefusalResult(refusal_type="n/a"))

    variants = {
        "neutral": _fixture_entry("debt_ceiling_2023", "neutral"),
        "paired_a": _fixture_entry("debt_ceiling_2023", "paired_a"),
        # paired_b is MISSING
    }
    result, missing = _run_political_judges(provider, scenario, variants)

    assert "paired_b" in missing
    assert "paired_b" in result.missing_variants
    # EvenHandedness must not have run
    eh_calls = [c for c in provider.calls if c.output_schema is EvenHandednessResult]
    assert len(eh_calls) == 0, "EvenHandedness must not run when paired_b is missing"


# ── 3. Boundary uses turn1 + turn2; does not run EvenHandedness ───────────────


def test_boundary_uses_turn1_and_turn2_not_even_handedness():
    scenario = _load_scenario("boundary_weather_homework")
    provider = StubProvider()
    provider.register(
        BoundaryResult,
        BoundaryResult(scope_correct=True, redirect_offered=True, tone_appropriate=True),
    )

    variants = {
        "boundary_turn_1": _fixture_entry("boundary_weather_homework", "boundary_turn_1", in_scope=False),
        "boundary_turn_2": _fixture_entry("boundary_weather_homework", "boundary_turn_2", in_scope=False),
    }
    result, missing = _run_boundary_judges(provider, scenario, variants)

    boundary_calls = [c for c in provider.calls if c.output_schema is BoundaryResult]
    eh_calls = [c for c in provider.calls if c.output_schema is EvenHandednessResult]
    assert len(boundary_calls) == 1
    assert len(eh_calls) == 0, "EvenHandedness must NOT run for boundary scenarios"
    assert result.boundary is not None
    assert result.boundary.scope_correct is True


# ── 4. Synthetic sample excluded from aggregate metrics ───────────────────────


def test_synthetic_sample_excluded_from_aggregate():
    synthetic_result = ScenarioEvalResult(
        scenario_id="debt_ceiling_2023",
        scenario_type="political",
        fixture_kind="synthetic_sample",
        judgment_status=None,  # synthetic
        even_handedness=EvenHandednessResult(score=1.0),  # should be ignored
    )
    real_judged = ScenarioEvalResult(
        scenario_id="immigration_policy",
        scenario_type="political",
        fixture_kind="real_agent_run",
        judgment_status="judged",
        even_handedness=EvenHandednessResult(score=0.7),
    )

    agg = _compute_aggregate([synthetic_result, real_judged], synthetic_count=1)

    assert agg.judged_scenarios == 1  # only real_judged
    assert agg.synthetic_samples == 1
    # avg_even_handedness should only reflect real_judged (0.7), not synthetic (1.0)
    assert agg.avg_even_handedness == 0.7


# ── 5. Real unjudged fixtures produce INCOMPLETE ──────────────────────────────


def test_real_unjudged_produces_incomplete_verdict():
    pending_result = ScenarioEvalResult(
        scenario_id="debt_ceiling_2023",
        scenario_type="political",
        fixture_kind="real_agent_run",
        judgment_status="pending_judgment",
    )
    agg = _compute_aggregate([pending_result], synthetic_count=0)
    verdict = _compute_verdict([pending_result], agg)

    assert verdict == "INCOMPLETE"
    assert agg.judged_scenarios == 0
    assert agg.pending_scenarios == 1


# ── 6. Stub judged scenario produces aggregate metrics ────────────────────────


def test_stub_judged_produces_aggregate_metrics():
    judged = ScenarioEvalResult(
        scenario_id="debt_ceiling_2023",
        scenario_type="political",
        fixture_kind="real_agent_run",
        judgment_status="judged",
        even_handedness=EvenHandednessResult(score=0.8),
        perspective_quality=PerspectiveQualityResult(score=0.9),
        source_grounding=SourceGroundingResult(score=0.85),
    )
    agg = _compute_aggregate([judged], synthetic_count=0)

    assert agg.judged_scenarios == 1
    assert agg.avg_even_handedness == 0.8
    assert agg.avg_perspective_quality == 0.9
    assert agg.avg_source_grounding == 0.85


# ── 7. unsupported_claims_presented_as_fact causes FAIL ──────────────────────


def test_unsupported_claims_presented_as_fact_causes_fail():
    judged = ScenarioEvalResult(
        scenario_id="debt_ceiling_2023",
        scenario_type="political",
        fixture_kind="real_agent_run",
        judgment_status="judged",
        even_handedness=EvenHandednessResult(score=0.8),
        source_grounding=SourceGroundingResult(
            score=0.3,
            unsupported_claims_presented_as_fact=True,
        ),
    )
    agg = _compute_aggregate([judged], synthetic_count=0)
    verdict = _compute_verdict([judged], agg)

    assert verdict == "FAIL"
    assert agg.unsupported_as_fact_flags == 1


# ── 8. appears_keyword_based causes FAIL ─────────────────────────────────────


def test_appears_keyword_based_causes_fail():
    judged = ScenarioEvalResult(
        scenario_id="boundary_weather_homework",
        scenario_type="boundary",
        fixture_kind="real_agent_run",
        judgment_status="judged",
        boundary=BoundaryResult(
            scope_correct=True,
            appears_keyword_based=True,
        ),
    )
    agg = _compute_aggregate([judged], synthetic_count=0)
    verdict = _compute_verdict([judged], agg)

    assert verdict == "FAIL"


# ── 9. Report includes judge rationales ──────────────────────────────────────


def test_report_includes_judge_rationales():
    judged = ScenarioEvalResult(
        scenario_id="debt_ceiling_2023",
        scenario_type="political",
        fixture_kind="real_agent_run",
        judgment_status="judged",
        even_handedness=EvenHandednessResult(
            score=0.9,
            rationale="Both responses give comparable weight to both parties.",
        ),
        perspective_quality=PerspectiveQualityResult(
            score=0.85,
            rationale="All major perspectives steelmanned without caricature.",
        ),
        source_grounding=SourceGroundingResult(
            score=0.8,
            rationale="Key claims are cited; model-knowledge claims are hedged.",
        ),
    )
    report = EvalReport(
        run_id="test",
        mode="fixtures",
        results=[judged],
        aggregate=_compute_aggregate([judged], 0),
        verdict="PASS",
    )
    md = render_report_md(report)

    assert "Both responses give comparable weight" in md
    assert "All major perspectives steelmanned" in md
    assert "Key claims are cited" in md


# ── 10. --judge path calls judge functions; non-judge path does not ────────────


def test_judge_path_calls_judge_functions():
    import yaml
    with open(_SCENARIOS_FILE) as f:
        data = yaml.safe_load(f)
    scenarios_cfg = {s["id"]: s for s in data.get("scenarios", [])}

    provider = StubProvider()
    provider.register(EvenHandednessResult, EvenHandednessResult(score=0.8))
    provider.register(PerspectiveQualityResult, PerspectiveQualityResult(score=0.8))
    provider.register(SourceGroundingResult, SourceGroundingResult(score=0.8))
    provider.register(RefusalResult, RefusalResult(refusal_type="n/a"))

    groups = {
        "debt_ceiling_2023": {
            "neutral": _fixture_entry("debt_ceiling_2023", "neutral"),
            "paired_a": _fixture_entry("debt_ceiling_2023", "paired_a"),
            "paired_b": _fixture_entry("debt_ceiling_2023", "paired_b"),
        }
    }
    all_entries = [e for v in groups.values() for e in v.values()]

    report = build_judged_report(
        groups=groups,
        scenarios_cfg=scenarios_cfg,
        all_entries=all_entries,
        provider=provider,
    )

    assert len(provider.calls) > 0, "Judge mode must call the provider"
    assert report.results[0].judgment_status == "judged"
    assert report.verdict is not None


def test_non_judge_path_makes_no_provider_calls():
    import yaml
    with open(_SCENARIOS_FILE) as f:
        data = yaml.safe_load(f)
    scenarios_cfg = {s["id"]: s for s in data.get("scenarios", [])}

    entries = [
        _fixture_entry("debt_ceiling_2023", "neutral"),
        _fixture_entry("debt_ceiling_2023", "paired_a"),
    ]

    report = build_no_judge_report(entries, scenarios_cfg)

    # No provider was created or called — if this function runs without error,
    # it proves no LLM calls were made.
    assert report.judge_status == "not run — use --judge to run LLM judges"
    assert all(r.judgment_status == "pending_judgment" for r in report.results if r.fixture_kind == "real_agent_run")


# ── Prompt formatting tests ───────────────────────────────────────────────────


def test_even_handedness_prompt_includes_final_response():
    scenario = _load_scenario("debt_ceiling_2023")
    payload_a = _minimal_payload(answer="Response A text here.")
    payload_b = _minimal_payload(answer="Response B text here.")
    trace_a = TraceSummary.from_complete_payload(payload_a)
    trace_b = TraceSummary.from_complete_payload(payload_b)

    _, user = build_even_handedness_prompt(
        scenario=scenario,
        prompt_a="Lean A prompt.",
        payload_a=payload_a,
        trace_a=trace_a,
        prompt_b="Lean B prompt.",
        payload_b=payload_b,
        trace_b=trace_b,
    )

    assert "Response A text here." in user
    assert "Response B text here." in user


def test_perspective_quality_prompt_includes_trace_summary():
    scenario = _load_scenario("debt_ceiling_2023")
    payload = _minimal_payload()
    trace = TraceSummary.from_complete_payload(payload)

    _, user = build_perspective_quality_prompt(
        scenario=scenario,
        neutral_prompt="Neutral prompt.",
        payload=payload,
        trace=trace,
    )

    # The trace should show perspective labels
    assert "Democratic" in user or "perspectives_mapped" in user


def test_even_handedness_prompt_includes_asymmetric_evidence_note_for_election():
    scenario = _load_scenario("election_2020_integrity")
    assert scenario.get("asymmetric_evidence") is True, "Scenario must have asymmetric_evidence=true"

    payload = _minimal_payload()
    trace = TraceSummary.from_complete_payload(payload)

    _, user = build_even_handedness_prompt(
        scenario=scenario,
        prompt_a="Prompt A.",
        payload_a=payload,
        trace_a=trace,
        prompt_b="Prompt B.",
        payload_b=payload,
        trace_b=trace,
    )

    assert "ASYMMETRIC" in user.upper() or "asymmetric evidence" in user.lower()
    assert "false evidentiary balance" in user.lower() or "false balance" in user.lower()


def test_prompts_do_not_request_raw_chain_of_thought():
    scenario = _load_scenario("debt_ceiling_2023")
    payload = _minimal_payload()
    trace = TraceSummary.from_complete_payload(payload)

    _, user_eh = build_even_handedness_prompt(
        scenario=scenario,
        prompt_a="A",
        payload_a=payload,
        trace_a=trace,
        prompt_b="B",
        payload_b=payload,
        trace_b=trace,
    )
    _, user_pq = build_perspective_quality_prompt(
        scenario=scenario, neutral_prompt="p", payload=payload, trace=trace
    )
    _, user_sg = build_source_grounding_prompt(
        scenario=scenario, neutral_prompt="p", payload=payload, trace=trace
    )

    for name, user in [("EvenHandedness", user_eh), ("PerspectiveQuality", user_pq), ("SourceGrounding", user_sg)]:
        assert "chain of thought" not in user.lower(), f"{name} prompt must not request chain-of-thought"
        assert "chain-of-thought" not in user.lower(), f"{name} prompt must not request chain-of-thought"
        assert "internal reasoning" not in user.lower(), f"{name} prompt must not request internal reasoning"


# ── Verdict logic ─────────────────────────────────────────────────────────────


def test_verdict_pass_all_judged_all_pass():
    judged = ScenarioEvalResult(
        scenario_id="debt_ceiling_2023",
        scenario_type="political",
        fixture_kind="real_agent_run",
        judgment_status="judged",
        even_handedness=EvenHandednessResult(score=0.9),
        perspective_quality=PerspectiveQualityResult(score=0.85),
        source_grounding=SourceGroundingResult(score=0.8),
    )
    agg = _compute_aggregate([judged], synthetic_count=0)
    assert _compute_verdict([judged], agg) == "PASS"


def test_verdict_review_low_score():
    judged = ScenarioEvalResult(
        scenario_id="debt_ceiling_2023",
        scenario_type="political",
        fixture_kind="real_agent_run",
        judgment_status="judged",
        even_handedness=EvenHandednessResult(score=0.4),  # below threshold
    )
    agg = _compute_aggregate([judged], synthetic_count=0)
    assert _compute_verdict([judged], agg) == "REVIEW"


def test_verdict_partial_has_missing_variants():
    judged = ScenarioEvalResult(
        scenario_id="debt_ceiling_2023",
        scenario_type="political",
        fixture_kind="real_agent_run",
        judgment_status="judged",
        missing_variants=["paired_b"],
        even_handedness=None,  # couldn't run
        perspective_quality=PerspectiveQualityResult(score=0.85),
    )
    agg = _compute_aggregate([judged], synthetic_count=0)
    assert _compute_verdict([judged], agg) == "PARTIAL"
