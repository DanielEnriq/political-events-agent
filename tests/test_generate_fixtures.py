"""Tests for evals/generate_fixtures.py — Stage C3.

All tests use a stub agent_runner so no real LLM or network calls are made.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from evals.generate_fixtures import (
    GenerateReport,
    VariantResult,
    _POLITICAL_VARIANTS,
    _BOUNDARY_VARIANTS,
    _prompt_for_variant,
    _scenario_variants,
    generate_fixtures,
)

# ── Fixture helpers ────────────────────────────────────────────────────────────

_MINIMAL_PAYLOAD: dict[str, Any] = {
    "in_scope": True,
    "answer": "Test answer.",
    "citations": [],
    "neutrality": None,
    "residual_uncertainty": None,
    "suggested_followups": [],
    "stage_details": {},
}

_OUT_OF_SCOPE_PAYLOAD: dict[str, Any] = {
    "in_scope": False,
    "answer": "This is outside the agent's scope.",
    "citations": [],
    "neutrality": None,
    "residual_uncertainty": None,
    "suggested_followups": [],
    "stage_details": {},
}


def _stub_runner(answer: str = "Test answer.", in_scope: bool = True) -> Any:
    """Return a simple stub runner that always returns the same payload."""
    payload = {**_MINIMAL_PAYLOAD, "answer": answer, "in_scope": in_scope}
    if not in_scope:
        payload = {**_OUT_OF_SCOPE_PAYLOAD}

    def runner(prompt: str, state: Any) -> dict[str, Any]:
        return dict(payload)

    return runner


def _load_scenarios(scenarios_file: Path) -> list[dict[str, Any]]:
    with open(scenarios_file) as f:
        data = yaml.safe_load(f)
    return data.get("scenarios", [])


_SCENARIOS_FILE = Path(__file__).parent.parent / "evals" / "scenarios.yaml"


# ── Unit tests: variant helpers ────────────────────────────────────────────────


def test_scenario_variants_political() -> None:
    scenario = {"id": "debt_ceiling_2023", "type": "political"}
    assert _scenario_variants(scenario) == _POLITICAL_VARIANTS


def test_scenario_variants_boundary() -> None:
    scenario = {"id": "boundary_weather_homework", "type": "boundary"}
    assert _scenario_variants(scenario) == _BOUNDARY_VARIANTS


def test_prompt_for_variant_returns_correct_text() -> None:
    scenario = {
        "id": "debt_ceiling_2023",
        "type": "political",
        "prompt": "Neutral prompt.",
        "paired_prompt": "Lean-A prompt.",
        "paired_prompt_b": "Lean-B prompt.",
    }
    assert _prompt_for_variant(scenario, "neutral") == "Neutral prompt."
    assert _prompt_for_variant(scenario, "paired_a") == "Lean-A prompt."
    assert _prompt_for_variant(scenario, "paired_b") == "Lean-B prompt."
    assert _prompt_for_variant(scenario, "boundary_turn_1") == "Neutral prompt."
    assert _prompt_for_variant(scenario, "boundary_turn_2") == "Neutral prompt."


# ── Integration tests: generate_fixtures() ────────────────────────────────────


def test_generate_fixtures_writes_political_variants(tmp_path: Path) -> None:
    """All 3 political variants are written when runner succeeds."""
    scenarios = _load_scenarios(_SCENARIOS_FILE)
    debt = [s for s in scenarios if s["id"] == "debt_ceiling_2023"]

    report = generate_fixtures(
        scenarios_cfg=debt,
        force=True,
        fixtures_dir=tmp_path,
        scenarios_file=_SCENARIOS_FILE,
        agent_runner=_stub_runner(),
        verbose=False,
    )

    assert report.total == 3
    assert report.written == 3
    assert report.failed == 0
    written = [r for r in report.results if r.status == "written"]
    assert {r.variant for r in written} == {"neutral", "paired_a", "paired_b"}


def test_generate_fixtures_skipped_when_exists(tmp_path: Path) -> None:
    """Existing fixture files are skipped unless force=True."""
    scenarios = _load_scenarios(_SCENARIOS_FILE)
    debt = [s for s in scenarios if s["id"] == "debt_ceiling_2023"]

    # First run: write all three
    generate_fixtures(
        scenarios_cfg=debt,
        force=False,
        fixtures_dir=tmp_path,
        scenarios_file=_SCENARIOS_FILE,
        agent_runner=_stub_runner(),
        verbose=False,
    )

    # Second run without --force: all skipped
    report2 = generate_fixtures(
        scenarios_cfg=debt,
        force=False,
        fixtures_dir=tmp_path,
        scenarios_file=_SCENARIOS_FILE,
        agent_runner=_stub_runner(),
        verbose=False,
    )

    assert report2.written == 0
    assert report2.skipped == 3


def test_generate_fixtures_force_overwrites(tmp_path: Path) -> None:
    """force=True rewrites existing fixture files."""
    scenarios = _load_scenarios(_SCENARIOS_FILE)
    debt = [s for s in scenarios if s["id"] == "debt_ceiling_2023"]

    generate_fixtures(
        scenarios_cfg=debt,
        force=True,
        fixtures_dir=tmp_path,
        scenarios_file=_SCENARIOS_FILE,
        agent_runner=_stub_runner("first"),
        verbose=False,
    )

    report2 = generate_fixtures(
        scenarios_cfg=debt,
        force=True,
        fixtures_dir=tmp_path,
        scenarios_file=_SCENARIOS_FILE,
        agent_runner=_stub_runner("second"),
        verbose=False,
    )

    assert report2.written == 3
    assert report2.skipped == 0

    # Verify the content was overwritten
    fixture_path = tmp_path / "debt_ceiling_2023_neutral.yaml"
    with open(fixture_path) as f:
        content = f.read()
    assert "second" in content


def test_generate_fixtures_dry_run(tmp_path: Path) -> None:
    """dry_run=True shows plan but writes no files."""
    scenarios = _load_scenarios(_SCENARIOS_FILE)
    debt = [s for s in scenarios if s["id"] == "debt_ceiling_2023"]

    report = generate_fixtures(
        scenarios_cfg=debt,
        dry_run=True,
        fixtures_dir=tmp_path,
        scenarios_file=_SCENARIOS_FILE,
        agent_runner=None,  # should not be called
        verbose=False,
    )

    assert report.dry_run == 3
    assert report.written == 0
    # No files written
    assert list(tmp_path.glob("*.yaml")) == []


def test_generate_fixtures_unknown_scenario_raises(tmp_path: Path) -> None:
    """Unknown scenario_id raises ValueError immediately."""
    scenarios = _load_scenarios(_SCENARIOS_FILE)

    with pytest.raises(ValueError, match="Unknown scenario_id"):
        generate_fixtures(
            scenarios_cfg=scenarios,
            scenario_ids=["nonexistent_scenario_xyz"],
            force=True,
            dry_run=True,
            fixtures_dir=tmp_path,
            scenarios_file=_SCENARIOS_FILE,
            verbose=False,
        )


def test_generate_fixtures_failed_on_runner_error(tmp_path: Path) -> None:
    """Runner exception is caught and recorded as 'failed', not re-raised."""
    scenarios = _load_scenarios(_SCENARIOS_FILE)
    debt = [s for s in scenarios if s["id"] == "debt_ceiling_2023"]

    def bad_runner(prompt: str, state: Any) -> dict[str, Any]:
        raise RuntimeError("simulated LLM error")

    report = generate_fixtures(
        scenarios_cfg=debt,
        force=True,
        fixtures_dir=tmp_path,
        scenarios_file=_SCENARIOS_FILE,
        agent_runner=bad_runner,
        verbose=False,
    )

    assert report.failed == 3
    assert report.written == 0
    for r in report.results:
        assert r.status == "failed"
        assert "simulated LLM error" in (r.error or "")


def test_generate_fixtures_variants_filter(tmp_path: Path) -> None:
    """variants_filter limits which variants are run."""
    scenarios = _load_scenarios(_SCENARIOS_FILE)
    debt = [s for s in scenarios if s["id"] == "debt_ceiling_2023"]

    report = generate_fixtures(
        scenarios_cfg=debt,
        variants_filter=["neutral"],
        force=True,
        fixtures_dir=tmp_path,
        scenarios_file=_SCENARIOS_FILE,
        agent_runner=_stub_runner(),
        verbose=False,
    )

    assert report.total == 1
    assert report.written == 1
    assert report.results[0].variant == "neutral"


def test_generate_boundary_turn2_receives_turn1_state(tmp_path: Path) -> None:
    """boundary_turn_2 runner is called with turn-1 history in ConversationState."""
    scenarios = _load_scenarios(_SCENARIOS_FILE)
    boundary = [s for s in scenarios if s["id"] == "boundary_weather_homework"]

    captured_states: list[list[tuple]] = []

    def recording_runner(prompt: str, state: Any) -> dict[str, Any]:
        captured_states.append(list(state.history))
        return dict(_OUT_OF_SCOPE_PAYLOAD)

    generate_fixtures(
        scenarios_cfg=boundary,
        force=True,
        fixtures_dir=tmp_path,
        scenarios_file=_SCENARIOS_FILE,
        agent_runner=recording_runner,
        verbose=False,
    )

    assert len(captured_states) == 2, "Expected exactly 2 runner calls (turn_1, turn_2)"

    # Turn 1: fresh state — no prior history
    assert captured_states[0] == [], "Turn 1 should start with empty state"

    # Turn 2: should carry turn 1's user + assistant messages
    assert len(captured_states[1]) == 2, "Turn 2 should have 2 history entries"
    assert captured_states[1][0][0] == "user"
    assert captured_states[1][1][0] == "assistant"
    assert captured_states[1][1][1] == _OUT_OF_SCOPE_PAYLOAD["answer"]
