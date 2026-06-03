"""Structural tests for the Stage B eval harness.

These tests use stub data only — no LLM calls, no agent calls, no network.
They verify schema construction, TraceSummary extraction, and report rendering.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from evals.judge_schemas import (
    BoundaryResult,
    EvalReport,
    EvenHandednessResult,
    PerspectiveQualityResult,
    RefusalResult,
    ScenarioEvalResult,
    SourceGroundingResult,
)
from evals.run_evals import render_report_md, run_fixtures
from evals.trace_summary import TraceSummary

_SAMPLE_FIXTURE = Path(__file__).parent.parent / "evals" / "fixtures" / "sample_minimal.yaml"


# ── 1. TraceSummary: well-formed payload ──────────────────────────────────────


def test_trace_summary_from_full_payload():
    payload = {
        "in_scope": True,
        "answer": "Test answer.",
        "citations": [{"label": "Reuters", "url": "https://reuters.com", "used_for_claim": "x"}],
        "stage_details": {
            "s2_scope": {"in_scope": True, "reasoning": "Political event.", "matched_charter_categories": ["us_politics"], "suggested_redirect": None},
            "s5_perspectives": {
                "perspectives": [{"label": "Left", "core_claims": ["claim A"]}, {"label": "Right", "core_claims": ["claim B"]}],
                "areas_of_consensus": ["Both agree default is bad"],
                "areas_of_disagreement": ["Spending cuts"],
                "empirical_vs_normative": [{"claim": "Default raises rates", "kind": "empirical"}],
            },
            "s6_verification": {
                "factual_claims": [{"claim": "Signed June 3", "confidence": 0.98}],
                "things_i_should_not_assert": [],
                "overall_calibration_note": "High confidence.",
            },
        },
    }
    ts = TraceSummary.from_complete_payload(payload)
    assert ts.in_scope is True
    assert ts.answer == "Test answer."
    assert len(ts.perspectives) == 2
    assert ts.perspectives[0]["label"] == "Left"
    assert ts.overall_calibration_note == "High confidence."
    assert len(ts.factual_claims) == 1
    assert len(ts.citations) == 1


# ── 2. TraceSummary: empty / missing keys ────────────────────────────────────


def test_trace_summary_empty_payload():
    ts = TraceSummary.from_complete_payload({})
    assert ts.in_scope is None
    assert ts.answer is None
    assert ts.perspectives == []
    assert ts.factual_claims == []
    assert ts.source_gaps == []


def test_trace_summary_partial_stage_details():
    payload = {"stage_details": {"s2_scope": {"in_scope": False}}}
    ts = TraceSummary.from_complete_payload(payload)
    assert ts.in_scope is False
    assert ts.perspectives == []
    assert ts.needs_search is None


# ── 3. Judge schema construction ─────────────────────────────────────────────


def test_even_handedness_result_defaults():
    r = EvenHandednessResult()
    assert r.score is None
    assert r.framing_asymmetry_detected is None
    assert r.favored_side is None
    assert r.notes is None


def test_scenario_eval_result_minimal():
    r = ScenarioEvalResult(scenario_id="debt_ceiling_2023", scenario_type="political")
    assert r.overall_pass is None
    assert r.even_handedness is None
    assert r.boundary is None


def test_eval_report_defaults():
    report = EvalReport(run_id="test-001", mode="fixtures")
    assert report.scenarios_evaluated == 0
    assert report.judge_status == "not yet implemented"
    assert report.results == []


# ── 4. Boundary result: structural S2 check ──────────────────────────────────


def test_boundary_result_out_of_scope():
    r = BoundaryResult(scope_correct=True, redirect_offered=True, tone_appropriate=True)
    assert r.scope_correct is True
    assert r.redirect_offered is True


def test_boundary_result_missed_refusal():
    r = BoundaryResult(scope_correct=False, redirect_offered=False, tone_appropriate=None)
    assert r.scope_correct is False


# ── 5. Fixture loading and report generation ─────────────────────────────────


def test_run_fixtures_loads_sample():
    assert _SAMPLE_FIXTURE.exists(), f"Fixture not found: {_SAMPLE_FIXTURE}"
    report = run_fixtures(_SAMPLE_FIXTURE)
    assert report.mode == "fixtures"
    assert report.scenarios_evaluated == 2
    assert report.judge_status == "not yet implemented"


def test_run_fixtures_boundary_scenario_has_boundary_result():
    report = run_fixtures(_SAMPLE_FIXTURE)
    boundary_results = [r for r in report.results if r.scenario_type == "boundary"]
    assert len(boundary_results) == 1
    r = boundary_results[0]
    assert r.boundary is not None
    assert r.boundary.scope_correct is True


def test_run_fixtures_political_scenario_pass_is_none():
    report = run_fixtures(_SAMPLE_FIXTURE)
    political_results = [r for r in report.results if r.scenario_type == "political"]
    assert len(political_results) == 1
    r = political_results[0]
    assert r.overall_pass is None


# ── 6. Report rendering ───────────────────────────────────────────────────────


def test_render_report_md_contains_header():
    report = EvalReport(run_id="abc123", mode="fixtures", scenarios_evaluated=0)
    md = render_report_md(report)
    assert "# Revere Behavioral Eval Report" in md
    assert "abc123" in md
    assert "not yet implemented" in md


def test_render_report_md_contains_scenario_rows():
    report = run_fixtures(_SAMPLE_FIXTURE)
    md = render_report_md(report)
    assert "debt_ceiling_2023" in md
    assert "boundary_weather_homework" in md
    assert "synthetic sample" in md.lower()
