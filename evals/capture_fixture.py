"""Fixture capture: save a real Revere agent output as an eval fixture YAML.

Usage:
    # With explicit output path:
    uv run python -m evals.capture_fixture \\
        --scenario debt_ceiling_2023 \\
        --variant neutral \\
        --input path/to/complete_payload.json \\
        --output evals/fixtures/debt_ceiling_2023_neutral.yaml

    # Auto-name output (evals/fixtures/{scenario_id}_{variant}.yaml):
    uv run python -m evals.capture_fixture \\
        --scenario debt_ceiling_2023 \\
        --variant neutral \\
        --input path/to/complete_payload.json

    # Overwrite an existing fixture:
    uv run python -m evals.capture_fixture ... --force

Input format:
    The --input JSON must be the complete_payload emitted by the FastAPI /chat
    endpoint's 'complete' SSE event. You can capture it by:

        curl -N -s -X POST http://localhost:8000/chat \\
            -H "Content-Type: application/json" \\
            -d '{"message": "...", "fast_mode": false}' \\
            | grep '^data:' | grep '"in_scope"' \\
            | sed 's/^data: //' > complete_payload.json

    Alternatively, copy the complete event payload from the browser DevTools
    EventSource stream, or use the Next.js /api/chat proxy.

Valid variants by scenario type:
    political  : neutral, paired_a, paired_b
    boundary   : neutral, boundary_turn_1, boundary_turn_2
"""

from __future__ import annotations

import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

from evals.trace_summary import TraceSummary

_SCENARIOS_FILE = Path(__file__).parent / "scenarios.yaml"
_FIXTURES_DIR = Path(__file__).parent / "fixtures"

_POLITICAL_VARIANTS: frozenset[str] = frozenset({"neutral", "paired_a", "paired_b"})
_BOUNDARY_VARIANTS: frozenset[str] = frozenset({"neutral", "boundary_turn_1", "boundary_turn_2"})


# ── Helpers ────────────────────────────────────────────────────────────────────


def _load_scenarios_index(scenarios_file: Path) -> dict[str, dict[str, Any]]:
    with open(scenarios_file) as f:
        data = yaml.safe_load(f)
    return {s["id"]: s for s in data.get("scenarios", [])}


def _valid_variants(scenario_type: str) -> frozenset[str]:
    return _BOUNDARY_VARIANTS if scenario_type == "boundary" else _POLITICAL_VARIANTS


def _detect_payload(raw: dict[str, Any]) -> dict[str, Any]:
    """Extract the complete_payload from the raw input dict.

    Accepts two shapes:
    1. Direct payload: top level has 'in_scope', 'answer', or 'stage_details'.
    2. Wrapped payload: top level has a 'complete_payload' key.
    """
    if "complete_payload" in raw:
        return raw["complete_payload"]
    if any(k in raw for k in ("in_scope", "answer", "stage_details")):
        return raw
    raise ValueError(
        "Cannot detect complete_payload shape. Expected top-level 'in_scope'/'answer'/"
        "'stage_details' keys, or a 'complete_payload' wrapper key."
    )


def _get_git_sha() -> str | None:
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        return sha if sha else None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _default_output_path(scenario_id: str, variant: str) -> Path:
    return _FIXTURES_DIR / f"{scenario_id}_{variant}.yaml"


# ── Core capture logic ────────────────────────────────────────────────────────


def capture_fixture(
    scenario_id: str,
    variant: str,
    complete_payload: dict[str, Any],
    output_path: Path,
    force: bool = False,
    scenarios_file: Path = _SCENARIOS_FILE,
) -> None:
    """Validate and write a real-agent-run fixture YAML.

    Raises:
        ValueError: on unknown scenario_id, invalid variant, or existing output
            path without force=True.
    """
    # ── Validate scenario ────────────────────────────────────────────────────
    index = _load_scenarios_index(scenarios_file)
    if scenario_id not in index:
        known = ", ".join(sorted(index))
        raise ValueError(
            f"Unknown scenario_id '{scenario_id}'. Known scenarios: {known}"
        )
    scenario = index[scenario_id]
    scenario_type = scenario["type"]

    # ── Validate variant ─────────────────────────────────────────────────────
    valid = _valid_variants(scenario_type)
    if variant not in valid:
        raise ValueError(
            f"Invalid variant '{variant}' for {scenario_type} scenario '{scenario_id}'. "
            f"Valid variants: {', '.join(sorted(valid))}"
        )

    # ── Check output path ────────────────────────────────────────────────────
    if output_path.exists() and not force:
        raise ValueError(
            f"Output path already exists: {output_path}. "
            "Pass --force to overwrite."
        )

    # ── Resolve prompt text for this variant ─────────────────────────────────
    if variant == "neutral":
        prompt_used = scenario.get("prompt", "").strip()
    elif variant == "paired_a":
        prompt_used = (scenario.get("paired_prompt") or "").strip()
    elif variant == "paired_b":
        prompt_used = (scenario.get("paired_prompt_b") or "").strip()
    elif variant in ("boundary_turn_1", "boundary_turn_2"):
        prompt_used = scenario.get("prompt", "").strip()
    else:
        prompt_used = ""

    # ── Build trace summary (for human readability in the fixture) ────────────
    ts = TraceSummary.from_complete_payload(complete_payload)

    # ── Build compact trace summary dict ─────────────────────────────────────
    trace_summary: dict[str, Any] = {}
    if ts.in_scope is not None:
        trace_summary["in_scope"] = ts.in_scope
    if ts.confidence_in_evidence is not None:
        trace_summary["confidence_in_evidence"] = ts.confidence_in_evidence
    if ts.perspectives:
        trace_summary["perspective_labels"] = [
            p.get("label") for p in ts.perspectives if p.get("label")
        ]
    if ts.things_i_should_not_assert:
        trace_summary["things_i_should_not_assert_count"] = len(ts.things_i_should_not_assert)
    if ts.factual_claims:
        trace_summary["factual_claims_count"] = len(ts.factual_claims)
    if ts.revisions_made:
        trace_summary["revisions_made"] = ts.revisions_made

    # ── Build fixture dict ────────────────────────────────────────────────────
    ts_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    git_sha = _get_git_sha()

    fixture: dict[str, Any] = {
        "fixture_kind": "real_agent_run",
        "fixture_note": (
            "Real Revere agent run. Suitable for behavioral evaluation. "
            "Not a synthetic sample."
        ),
        "scenario_id": scenario_id,
        "prompt_variant": variant,
        "prompt_used": prompt_used or None,
        "generated_at": ts_str,
        "agent_git_sha": git_sha,
        "judgment_status": "pending_judgment",
        "trace_summary": trace_summary or None,
        "run": {
            "complete_payload": complete_payload,
        },
    }

    # ── Write ─────────────────────────────────────────────────────────────────
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        # YAML header comment
        f.write(
            f"# Real Revere agent run fixture\n"
            f"# Scenario: {scenario_id} / Variant: {variant}\n"
            f"# Generated: {ts_str}\n"
            f"# Git SHA: {git_sha or 'unknown'}\n"
            f"# judgment_status: pending_judgment — judges not yet run\n"
            f"#\n"
            f"# Do not edit the complete_payload by hand.\n"
            f"# To re-capture, run: uv run python -m evals.capture_fixture ...\n\n"
        )
        yaml.dump(
            fixture,
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
            width=120,
        )


# ── CLI ────────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Capture a real Revere agent output as an eval fixture YAML. "
            "The input must be the complete_payload JSON from a /chat SSE 'complete' event."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:

  # Capture a neutral run for debt_ceiling_2023:
  uv run python -m evals.capture_fixture \\
      --scenario debt_ceiling_2023 \\
      --variant neutral \\
      --input /tmp/complete_payload.json

  # Capture a paired variant with explicit output path:
  uv run python -m evals.capture_fixture \\
      --scenario election_2020_integrity \\
      --variant paired_a \\
      --input /tmp/payload_leaning.json \\
      --output evals/fixtures/election_2020_integrity_paired_a.yaml

  # Re-capture (overwrite existing):
  uv run python -m evals.capture_fixture \\
      --scenario immigration_policy \\
      --variant neutral \\
      --input /tmp/payload.json \\
      --force

How to get the input JSON from the running API:

  curl -N -s -X POST http://localhost:8000/chat \\
      -H "Content-Type: application/json" \\
      -d '{"message": "What happened with the debt ceiling..."}' \\
  | grep '^data:' | grep '"in_scope"' \\
  | sed 's/^data: //' > /tmp/complete_payload.json
""",
    )
    parser.add_argument(
        "--scenario",
        required=True,
        metavar="SCENARIO_ID",
        help="Scenario ID from evals/scenarios.yaml (e.g. debt_ceiling_2023).",
    )
    parser.add_argument(
        "--variant",
        required=True,
        choices=sorted(_POLITICAL_VARIANTS | _BOUNDARY_VARIANTS),
        metavar="VARIANT",
        help=(
            "Prompt variant. Political: neutral|paired_a|paired_b. "
            "Boundary: neutral|boundary_turn_1|boundary_turn_2."
        ),
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        metavar="JSON_FILE",
        help="Path to JSON file containing the complete_payload from the /chat SSE stream.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        metavar="YAML_FILE",
        help=(
            "Output fixture path. Defaults to "
            "evals/fixtures/{scenario_id}_{variant}.yaml."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing output file.",
    )

    args = parser.parse_args()

    # Load input JSON
    if not args.input.exists():
        print(f"error: input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    try:
        raw = json.loads(args.input.read_text())
    except json.JSONDecodeError as e:
        print(f"error: invalid JSON in {args.input}: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        complete_payload = _detect_payload(raw)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    output_path = args.output or _default_output_path(args.scenario, args.variant)

    try:
        capture_fixture(
            scenario_id=args.scenario,
            variant=args.variant,
            complete_payload=complete_payload,
            output_path=output_path,
            force=args.force,
        )
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Fixture written to {output_path}")
    print(f"  scenario: {args.scenario} / variant: {args.variant}")
    print(f"  judgment_status: pending_judgment")
    print(f"  Next step: run LLM judges (Stage C2) to evaluate this fixture.")


if __name__ == "__main__":
    main()
