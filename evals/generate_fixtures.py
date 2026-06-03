"""Generate real Revere agent fixtures for all scenario variants.

Drives the Revere orchestrator directly (no SSE layer) for each scenario
variant defined in evals/scenarios.yaml and saves the outputs as eval
fixture YAML files via capture_fixture.

Usage:
    # Run all 17 variants (5 political × 3 + 1 boundary × 2):
    uv run python -m evals.generate_fixtures --all

    # Run a single scenario (all its variants):
    uv run python -m evals.generate_fixtures --scenario debt_ceiling_2023

    # Run specific variants only:
    uv run python -m evals.generate_fixtures --scenario debt_ceiling_2023 --variants neutral,paired_a

    # Disable Tavily (faster, uses model knowledge only):
    uv run python -m evals.generate_fixtures --all --no-search

    # Overwrite existing fixtures:
    uv run python -m evals.generate_fixtures --all --force

    # Show plan without running the agent:
    uv run python -m evals.generate_fixtures --all --dry-run

After generating, run the LLM judges:
    uv run python -m evals.run_evals --mode fixtures --judge
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

from evals.capture_fixture import capture_fixture

_SCENARIOS_FILE = Path(__file__).parent / "scenarios.yaml"
_FIXTURES_DIR = Path(__file__).parent / "fixtures"

_POLITICAL_VARIANTS: list[str] = ["neutral", "paired_a", "paired_b"]
_BOUNDARY_VARIANTS: list[str] = ["boundary_turn_1", "boundary_turn_2"]

# Type alias: (prompt, state) -> complete_payload dict
AgentRunner = Callable[..., dict[str, Any]]


# ── Report dataclasses ─────────────────────────────────────────────────────────


@dataclass
class VariantResult:
    scenario_id: str
    variant: str
    status: Literal["written", "skipped", "failed", "dry_run"]
    output_path: Path | None = None
    error: str | None = None


@dataclass
class GenerateReport:
    total: int = 0
    written: int = 0
    skipped: int = 0
    failed: int = 0
    dry_run: int = 0
    results: list[VariantResult] = field(default_factory=list)


# ── Variant / prompt helpers ───────────────────────────────────────────────────


def _scenario_variants(scenario: dict[str, Any]) -> list[str]:
    """Return the ordered default variant list for a scenario."""
    if scenario.get("type") == "boundary":
        return list(_BOUNDARY_VARIANTS)
    return list(_POLITICAL_VARIANTS)


def _prompt_for_variant(scenario: dict[str, Any], variant: str) -> str:
    """Return the prompt text to send to the agent for a given variant."""
    if variant == "paired_a":
        return (scenario.get("paired_prompt") or "").strip()
    if variant == "paired_b":
        return (scenario.get("paired_prompt_b") or "").strip()
    # neutral, boundary_turn_1, boundary_turn_2 all use the base prompt
    return (scenario.get("prompt") or "").strip()


# ── Default agent runner ───────────────────────────────────────────────────────


def _make_default_runner(no_search: bool = False, max_hits: int = 6) -> AgentRunner:
    """Build a runner closure backed by the real Revere orchestrator.

    Loads .env, constructs the LLM + search providers, and serializes each
    TurnResult into the same complete_payload shape the FastAPI /chat endpoint
    emits. This ensures fixtures produced here are identical in structure to
    those captured from the live API.
    """
    from dotenv import load_dotenv

    from api.server import _build_stage_details
    from revere_agent.agent import Orchestrator
    from revere_agent.cli.run import _maybe_search_provider
    from revere_agent.llm import make_provider_from_env

    load_dotenv()
    llm = make_provider_from_env()
    search = _maybe_search_provider(disabled=no_search)
    orch = Orchestrator(
        llm_provider=llm,
        search_provider=search,
        max_unique_hits=max_hits,
    )

    def runner(prompt: str, state: Any) -> dict[str, Any]:
        result = orch.run_turn(prompt, state=state)
        scope = result.scope

        if not scope.in_scope:
            redirect = scope.suggested_redirect or "This is outside the agent's scope."
            return {
                "in_scope": False,
                "answer": redirect,
                "citations": [],
                "neutrality": None,
                "residual_uncertainty": None,
                "suggested_followups": [],
                "stage_details": _build_stage_details(result),
            }

        final = result.final_response
        citations = []
        if final and final.citations:
            citations = [
                {"label": c.label, "url": c.url, "used_for_claim": c.used_for_claim}
                for c in final.citations
            ]

        neutrality = None
        if final and final.neutrality_self_check:
            nsc = final.neutrality_self_check
            neutrality = {
                "avoided_unsolicited_opinion": nsc.avoided_unsolicited_opinion,
                "factually_accurate_and_comprehensive": nsc.factually_accurate_and_comprehensive,
                "steelmanned_each_perspective": nsc.steelmanned_each_perspective,
                "neutral_terminology_used": nsc.neutral_terminology_used,
                "equal_depth_across_perspectives": nsc.equal_depth_across_perspectives,
                "respectful_tone": nsc.respectful_tone,
                "evidence_proportional_to_sources": nsc.evidence_proportional_to_sources,
                "revisions_made": list(nsc.revisions_made or []),
            }

        return {
            "in_scope": True,
            "answer": final.response_text if final else "",
            "citations": citations,
            "neutrality": neutrality,
            "residual_uncertainty": final.residual_uncertainty if final else None,
            "suggested_followups": list(final.suggested_followups or []) if final else [],
            "stage_details": _build_stage_details(result),
        }

    return runner


# ── Core generate logic ────────────────────────────────────────────────────────


def generate_fixtures(
    scenarios_cfg: list[dict[str, Any]],
    scenario_ids: list[str] | None = None,
    variants_filter: list[str] | None = None,
    force: bool = False,
    dry_run: bool = False,
    fixtures_dir: Path = _FIXTURES_DIR,
    scenarios_file: Path = _SCENARIOS_FILE,
    agent_runner: AgentRunner | None = None,
    verbose: bool = True,
) -> GenerateReport:
    """Run the agent for each scenario variant and write fixture YAML files.

    Args:
        scenarios_cfg:   Loaded scenario list from scenarios.yaml.
        scenario_ids:    If set, only process these scenario IDs.
        variants_filter: If set, only process these variant names.
        force:           Overwrite existing fixture files.
        dry_run:         Show the plan without running the agent.
        fixtures_dir:    Directory to write fixture files into.
        scenarios_file:  Path to scenarios.yaml (passed to capture_fixture).
        agent_runner:    Callable(prompt, state) -> complete_payload. Must be
                         provided unless dry_run=True. Inject a stub in tests.
        verbose:         Print progress to stdout.

    Returns:
        GenerateReport summarising counts and per-variant status.

    Raises:
        ValueError: if an unknown scenario_id is requested.
        RuntimeError: if agent_runner is None and dry_run is False.
    """
    from revere_agent.agent.state import ConversationState

    if not dry_run and agent_runner is None:
        raise RuntimeError(
            "agent_runner must be provided when dry_run=False. "
            "Pass --all or --scenario with provider env vars configured, "
            "or inject a stub runner in tests."
        )

    report = GenerateReport()

    # Filter and validate scenarios
    scenarios = list(scenarios_cfg)
    if scenario_ids:
        id_set = set(scenario_ids)
        scenarios = [s for s in scenarios if s["id"] in id_set]
        missing = id_set - {s["id"] for s in scenarios}
        if missing:
            raise ValueError(f"Unknown scenario_id(s): {', '.join(sorted(missing))}")

    for scenario in scenarios:
        scenario_id = scenario["id"]
        scenario_type = scenario.get("type", "political")
        variants = _scenario_variants(scenario)

        if variants_filter:
            variants = [v for v in variants if v in variants_filter]
            if not variants:
                continue

        if verbose:
            print(f"\nScenario: {scenario_id} ({scenario_type})")

        # Cached turn-1 output for boundary state propagation
        t1_answer: str | None = None

        for variant in variants:
            output_path = fixtures_dir / f"{scenario_id}_{variant}.yaml"
            report.total += 1

            if dry_run:
                prompt = _prompt_for_variant(scenario, variant)
                if verbose:
                    print(f"  [dry-run] {variant}: {output_path}")
                    print(f"    prompt: {prompt[:80]}{'...' if len(prompt) > 80 else ''}")
                report.dry_run += 1
                report.results.append(
                    VariantResult(
                        scenario_id=scenario_id,
                        variant=variant,
                        status="dry_run",
                        output_path=output_path,
                    )
                )
                continue

            if output_path.exists() and not force:
                if verbose:
                    print(f"  [skip] {variant}: already exists (--force to overwrite)")
                report.skipped += 1
                report.results.append(
                    VariantResult(
                        scenario_id=scenario_id,
                        variant=variant,
                        status="skipped",
                        output_path=output_path,
                    )
                )
                continue

            prompt = _prompt_for_variant(scenario, variant)

            try:
                if verbose:
                    print(f"  [run] {variant}: {prompt[:60]}{'...' if len(prompt) > 60 else ''}")

                # Build ConversationState — populate history for boundary turn 2
                state = ConversationState()
                if variant == "boundary_turn_2" and t1_answer is not None:
                    t1_prompt = _prompt_for_variant(scenario, "boundary_turn_1")
                    state.record("user", t1_prompt)
                    state.record("assistant", t1_answer)

                complete_payload = agent_runner(prompt, state)  # type: ignore[misc]

                # Cache turn-1 answer so turn 2 can build a realistic state
                if variant == "boundary_turn_1":
                    t1_answer = complete_payload.get("answer", "") or ""

                capture_fixture(
                    scenario_id=scenario_id,
                    variant=variant,
                    complete_payload=complete_payload,
                    output_path=output_path,
                    force=force,
                    scenarios_file=scenarios_file,
                )

                if verbose:
                    print(f"    -> written: {output_path}")
                report.written += 1
                report.results.append(
                    VariantResult(
                        scenario_id=scenario_id,
                        variant=variant,
                        status="written",
                        output_path=output_path,
                    )
                )

            except Exception as exc:
                msg = f"{type(exc).__name__}: {exc}"
                if verbose:
                    print(f"    -> FAILED: {msg}", file=sys.stderr)
                report.failed += 1
                report.results.append(
                    VariantResult(
                        scenario_id=scenario_id,
                        variant=variant,
                        status="failed",
                        output_path=output_path,
                        error=msg,
                    )
                )

    return report


# ── CLI ────────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run the Revere agent for each scenario variant and capture fixture files. "
            "Requires ANTHROPIC_API_KEY (or PROVIDER=bedrock) in .env or environment."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:

  # Run all 17 variants (5 political × 3 + 1 boundary × 2):
  uv run python -m evals.generate_fixtures --all

  # Run a single scenario:
  uv run python -m evals.generate_fixtures --scenario debt_ceiling_2023

  # Run specific variants:
  uv run python -m evals.generate_fixtures --scenario debt_ceiling_2023 --variants neutral,paired_a

  # Disable Tavily (faster, uses model knowledge only):
  uv run python -m evals.generate_fixtures --all --no-search

  # Overwrite existing fixtures:
  uv run python -m evals.generate_fixtures --all --force

  # Preview the plan without running:
  uv run python -m evals.generate_fixtures --all --dry-run

After generating, run the LLM judges:
  uv run python -m evals.run_evals --mode fixtures --judge
""",
    )

    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--all",
        action="store_true",
        help="Generate fixtures for all scenarios and variants.",
    )
    mode_group.add_argument(
        "--scenario",
        metavar="SCENARIO_ID",
        help="Generate fixtures for a single scenario (all its variants).",
    )

    parser.add_argument(
        "--variants",
        metavar="VARIANT_LIST",
        default=None,
        help=(
            "Comma-separated variants to run (e.g. neutral,paired_a). "
            "Default: all variants for the scenario type."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing fixture files.",
    )
    parser.add_argument(
        "--no-search",
        action="store_true",
        dest="no_search",
        help="Disable Tavily search; answers from model knowledge only.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Show the plan without calling the agent or writing files.",
    )
    parser.add_argument(
        "--max-hits",
        type=int,
        default=6,
        dest="max_hits",
        metavar="N",
        help="Maximum search hits per query (default: 6).",
    )
    parser.add_argument(
        "--scenarios-file",
        type=Path,
        default=_SCENARIOS_FILE,
        metavar="FILE",
        help="Path to scenarios.yaml (default: evals/scenarios.yaml).",
    )
    parser.add_argument(
        "--fixtures-dir",
        type=Path,
        default=_FIXTURES_DIR,
        metavar="DIR",
        help="Directory to write fixture files into (default: evals/fixtures/).",
    )

    args = parser.parse_args()

    # Load scenarios
    with open(args.scenarios_file) as fh:
        data = yaml.safe_load(fh)
    scenarios_cfg: list[dict[str, Any]] = data.get("scenarios", [])

    scenario_ids: list[str] | None = None if args.all else [args.scenario]

    variants_filter: list[str] | None = None
    if args.variants:
        variants_filter = [v.strip() for v in args.variants.split(",") if v.strip()]

    # Build runner (skipped for dry-run)
    agent_runner: AgentRunner | None = None
    if not args.dry_run:
        try:
            agent_runner = _make_default_runner(no_search=args.no_search, max_hits=args.max_hits)
        except Exception as exc:
            print(f"error: failed to initialize agent runner: {exc}", file=sys.stderr)
            sys.exit(1)

    try:
        report = generate_fixtures(
            scenarios_cfg=scenarios_cfg,
            scenario_ids=scenario_ids,
            variants_filter=variants_filter,
            force=args.force,
            dry_run=args.dry_run,
            fixtures_dir=args.fixtures_dir,
            scenarios_file=args.scenarios_file,
            agent_runner=agent_runner,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"\n{'─' * 50}")
    print("Generate fixtures summary")
    print(f"  total:   {report.total}")
    print(f"  written: {report.written}")
    print(f"  skipped: {report.skipped}")
    print(f"  failed:  {report.failed}")
    if report.dry_run:
        print(f"  dry-run: {report.dry_run}")

    if report.failed > 0:
        print("\nFailed variants:")
        for r in report.results:
            if r.status == "failed":
                print(f"  {r.scenario_id}/{r.variant}: {r.error}")
        sys.exit(1)

    if report.written > 0:
        print("\nNext step:")
        print("  uv run python -m evals.run_evals --mode fixtures --judge")


if __name__ == "__main__":
    main()
