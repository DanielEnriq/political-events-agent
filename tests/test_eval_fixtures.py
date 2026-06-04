"""Tests for Stage C1: real fixture capture and loading.

No LLM calls, no agent calls, no network. All tests use stub data or
write to a temporary directory.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from evals.capture_fixture import (
    _default_output_path,
    _detect_payload,
    _valid_variants,
    capture_fixture,
)
from evals.judge_schemas import ScenarioEvalResult
from evals.run_evals import render_report_md, run_fixtures
from evals.trace_summary import TraceSummary

_SCENARIOS_FILE = Path(__file__).parent.parent / "evals" / "scenarios.yaml"
_SAMPLE_FIXTURE = Path(__file__).parent.parent / "evals" / "fixtures" / "sample_minimal.yaml"

# Minimal complete_payload that the capture script will accept.
_MINIMAL_PAYLOAD: dict = {
    "in_scope": True,
    "answer": "Test answer text.",
    "citations": [],
    "neutrality": None,
    "residual_uncertainty": None,
    "suggested_followups": [],
    "stage_details": {
        "s2_scope": {
            "in_scope": True,
            "confidence": 0.9,
            "reasoning": "Political event.",
            "matched_charter_categories": ["us_politics"],
            "suggested_redirect": None,
        },
        "s5_perspectives": {
            "perspectives": [
                {"label": "Left", "core_claims": ["A"]},
                {"label": "Right", "core_claims": ["B"]},
            ],
            "areas_of_consensus": [],
            "areas_of_disagreement": ["Spending cuts"],
            "empirical_vs_normative": [],
        },
        "s6_verification": {
            "factual_claims": [{"claim": "Test claim", "confidence": 0.9}],
            "things_i_should_not_assert": [],
            "overall_calibration_note": "Moderate confidence.",
        },
    },
}

_BOUNDARY_PAYLOAD: dict = {
    "in_scope": False,
    "answer": "Out of scope.",
    "citations": [],
    "neutrality": None,
    "residual_uncertainty": None,
    "suggested_followups": [],
    "stage_details": {
        "s2_scope": {
            "in_scope": False,
            "confidence": 0.99,
            "reasoning": "Weather query is out of scope.",
            "matched_charter_categories": [],
            "suggested_redirect": "Try a weather service.",
        },
    },
}


# ── 1. Reject unknown scenario_id ─────────────────────────────────────────────


def test_capture_rejects_unknown_scenario_id(tmp_path):
    out = tmp_path / "out.yaml"
    with pytest.raises(ValueError, match="Unknown scenario_id"):
        capture_fixture(
            scenario_id="nonexistent_scenario",
            variant="neutral",
            complete_payload=_MINIMAL_PAYLOAD,
            output_path=out,
            scenarios_file=_SCENARIOS_FILE,
        )


# ── 2. Reject invalid variant ─────────────────────────────────────────────────


def test_capture_rejects_invalid_variant_for_political_scenario(tmp_path):
    out = tmp_path / "out.yaml"
    with pytest.raises(ValueError, match="Invalid variant"):
        capture_fixture(
            scenario_id="debt_ceiling_2023",
            variant="boundary_turn_1",  # only valid for boundary scenarios
            complete_payload=_MINIMAL_PAYLOAD,
            output_path=out,
            scenarios_file=_SCENARIOS_FILE,
        )


def test_capture_rejects_invalid_variant_for_boundary_scenario(tmp_path):
    out = tmp_path / "out.yaml"
    with pytest.raises(ValueError, match="Invalid variant"):
        capture_fixture(
            scenario_id="boundary_weather_homework",
            variant="paired_a",  # only valid for political scenarios
            complete_payload=_BOUNDARY_PAYLOAD,
            output_path=out,
            scenarios_file=_SCENARIOS_FILE,
        )


# ── 3. Writes YAML from a minimal complete payload ────────────────────────────


def test_capture_writes_yaml(tmp_path):
    out = tmp_path / "debt_ceiling_2023_neutral.yaml"
    capture_fixture(
        scenario_id="debt_ceiling_2023",
        variant="neutral",
        complete_payload=_MINIMAL_PAYLOAD,
        output_path=out,
        scenarios_file=_SCENARIOS_FILE,
    )
    assert out.exists()
    content = yaml.safe_load(out.read_text())
    assert content["fixture_kind"] == "real_agent_run"
    assert content["scenario_id"] == "debt_ceiling_2023"
    assert content["prompt_variant"] == "neutral"
    assert content["judgment_status"] == "pending_judgment"
    assert "run" in content
    assert "complete_payload" in content["run"]
    assert content["run"]["complete_payload"]["in_scope"] is True


def test_capture_includes_trace_summary(tmp_path):
    out = tmp_path / "out.yaml"
    capture_fixture(
        scenario_id="debt_ceiling_2023",
        variant="neutral",
        complete_payload=_MINIMAL_PAYLOAD,
        output_path=out,
        scenarios_file=_SCENARIOS_FILE,
    )
    content = yaml.safe_load(out.read_text())
    ts = content.get("trace_summary") or {}
    assert ts.get("in_scope") is True
    assert ts.get("perspective_labels") == ["Left", "Right"]


# ── 4. Refuses to overwrite without --force ───────────────────────────────────


def test_capture_refuses_overwrite_without_force(tmp_path):
    out = tmp_path / "out.yaml"
    out.write_text("existing content")
    with pytest.raises(ValueError, match="already exists"):
        capture_fixture(
            scenario_id="debt_ceiling_2023",
            variant="neutral",
            complete_payload=_MINIMAL_PAYLOAD,
            output_path=out,
            force=False,
            scenarios_file=_SCENARIOS_FILE,
        )


def test_capture_overwrites_with_force(tmp_path):
    out = tmp_path / "out.yaml"
    out.write_text("old content")
    capture_fixture(
        scenario_id="debt_ceiling_2023",
        variant="neutral",
        complete_payload=_MINIMAL_PAYLOAD,
        output_path=out,
        force=True,
        scenarios_file=_SCENARIOS_FILE,
    )
    content = yaml.safe_load(out.read_text())
    assert content["fixture_kind"] == "real_agent_run"


# ── 5. Real fixture loads in run_evals ────────────────────────────────────────


def test_real_fixture_loads_in_run_evals(tmp_path):
    out = tmp_path / "debt_ceiling_2023_neutral.yaml"
    capture_fixture(
        scenario_id="debt_ceiling_2023",
        variant="neutral",
        complete_payload=_MINIMAL_PAYLOAD,
        output_path=out,
        scenarios_file=_SCENARIOS_FILE,
    )
    report = run_fixtures(out)
    assert report.scenarios_evaluated == 1
    assert report.results[0].scenario_id == "debt_ceiling_2023"
    assert report.results[0].fixture_kind == "real_agent_run"
    assert report.results[0].prompt_variant == "neutral"


# ── 6. Real fixture without judges is marked pending_judgment ─────────────────


def test_real_fixture_marked_pending_judgment(tmp_path):
    out = tmp_path / "debt_ceiling_2023_neutral.yaml"
    capture_fixture(
        scenario_id="debt_ceiling_2023",
        variant="neutral",
        complete_payload=_MINIMAL_PAYLOAD,
        output_path=out,
        scenarios_file=_SCENARIOS_FILE,
    )
    report = run_fixtures(out)
    r = report.results[0]
    assert r.judgment_status == "pending_judgment"
    assert r.overall_pass is None

    md = render_report_md(report)
    assert "pending" in md


# ── 7. TraceSummary extraction from complete payload shape ────────────────────


def test_trace_summary_from_real_payload_shape():
    ts = TraceSummary.from_complete_payload(_MINIMAL_PAYLOAD)
    assert ts.in_scope is True
    assert ts.answer == "Test answer text."
    assert len(ts.perspectives) == 2
    assert ts.perspectives[0]["label"] == "Left"
    assert ts.overall_calibration_note == "Moderate confidence."


def test_trace_summary_from_boundary_payload_shape():
    ts = TraceSummary.from_complete_payload(_BOUNDARY_PAYLOAD)
    assert ts.in_scope is False
    assert ts.suggested_redirect == "Try a weather service."
    assert ts.perspectives == []


# ── 8. Synthetic sample remains clearly marked as synthetic ───────────────────


def test_synthetic_sample_fixture_kind():
    report = run_fixtures(_SAMPLE_FIXTURE)
    for r in report.results:
        assert r.fixture_kind == "synthetic_sample"


def test_synthetic_sample_has_no_pending_judgment():
    report = run_fixtures(_SAMPLE_FIXTURE)
    political = [r for r in report.results if r.scenario_type == "political"]
    for r in political:
        assert r.judgment_status is None, (
            f"Synthetic sample should not have judgment_status='pending_judgment', "
            f"got {r.judgment_status!r} for {r.scenario_id}"
        )


def test_synthetic_sample_report_says_synthetic(tmp_path):
    report = run_fixtures(_SAMPLE_FIXTURE)
    md = render_report_md(report)
    assert "synthetic" in md.lower()


# ── Helper: _detect_payload ───────────────────────────────────────────────────


def test_detect_payload_direct():
    payload = _detect_payload(_MINIMAL_PAYLOAD)
    assert payload["in_scope"] is True


def test_detect_payload_wrapped():
    wrapped = {"complete_payload": _MINIMAL_PAYLOAD}
    payload = _detect_payload(wrapped)
    assert payload["in_scope"] is True


def test_detect_payload_rejects_unknown_shape():
    with pytest.raises(ValueError, match="Cannot detect"):
        _detect_payload({"foo": "bar"})


# ── Helper: _valid_variants ───────────────────────────────────────────────────


def test_valid_variants_political():
    v = _valid_variants("political")
    assert "neutral" in v
    assert "paired_a" in v
    assert "boundary_turn_1" not in v


def test_valid_variants_boundary():
    v = _valid_variants("boundary")
    assert "neutral" in v
    assert "boundary_turn_1" in v
    assert "paired_a" not in v
