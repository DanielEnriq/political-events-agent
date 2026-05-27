"""Day 2 CLI: run S1–S5 and print every stage's output plus the trace.

This is the "show the work" CLI. It exists so a reviewer (or you) can see
each reasoning stage's structured output, whether Tavily search was used,
and the serialized ReasoningTrace — all from one command.

Usage:
  uv run revere-run                              # default debt-ceiling query
  uv run revere-run "your question here"
  uv run revere-run --no-search "your question"  # force-disable search
"""

from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv

from revere_agent.agent import Orchestrator
from revere_agent.llm import make_provider_from_env
from revere_agent.search import TavilyProvider

DEFAULT_QUERY = (
    "What happened with the debt ceiling negotiations in 2023? "
    "What were the key positions of both parties?"
)


def _print_section(title: str, body: str) -> None:
    bar = "═" * 72
    print(f"\n{bar}\n{title}\n{bar}\n{body}")


def _maybe_search_provider(disabled: bool):
    """Construct Tavily only if we have a key AND the user didn't disable search.

    If TAVILY_API_KEY is absent, return None — the orchestrator handles
    that gracefully (no search runs; S4 documents the limitation).
    """
    if disabled:
        return None
    try:
        return TavilyProvider()
    except RuntimeError:
        # No key set. Run anyway; S4 will note the model-knowledge-only path.
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="revere-run",
        description="Run the S1→S5 reasoning pipeline on a single query.",
    )
    parser.add_argument(
        "query",
        nargs="*",
        help="User question (default: 2023 debt ceiling scenario).",
    )
    parser.add_argument(
        "--no-search",
        action="store_true",
        help="Disable Tavily even if a key is set (useful for offline runs).",
    )
    parser.add_argument(
        "--max-hits",
        type=int,
        default=None,
        help="Maximum unique deduplicated hits passed to S4 (default: 6; 4 in --fast mode).",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Faster demo mode: lowers max unique hits to 4 unless --max-hits is set.",
    )
    args = parser.parse_args(argv)
    resolved_max_hits = args.max_hits if args.max_hits is not None else (4 if args.fast else 6)
    if resolved_max_hits < 1:
        parser.error("--max-hits must be >= 1")

    load_dotenv()
    user_query = " ".join(args.query).strip() or DEFAULT_QUERY

    try:
        llm = make_provider_from_env()
    except RuntimeError as e:
        print(f"[setup error] {e}", file=sys.stderr)
        return 2

    search = _maybe_search_provider(disabled=args.no_search)
    if search is None and not args.no_search:
        print(
            "[note] TAVILY_API_KEY not set — running without search. S4 will "
            "document the model-knowledge-only limitation in its gaps field.",
            file=sys.stderr,
        )

    orch = Orchestrator(
        llm_provider=llm,
        search_provider=search,
        max_unique_hits=resolved_max_hits,
    )

    print(f"User query: {user_query}")
    print(f"LLM provider: {llm.name}")
    print(f"Search provider: {search.name if search else '(none)'}")
    print(f"Fast mode: {'on' if args.fast else 'off'}")
    print(f"Max unique hits to S4: {resolved_max_hits}")

    try:
        result = orch.run_turn(user_query)
    except Exception as e:  # noqa: BLE001 — surface clearly
        print(f"\n[pipeline error] {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    # ── S1 ────────────────────────────────────────────────────────────
    _print_section("S1 — IntakeAnalysis", result.intake.model_dump_json(indent=2))

    # ── S2 ────────────────────────────────────────────────────────────
    _print_section("S2 — ScopeDecision", result.scope.model_dump_json(indent=2))

    if not result.scope.in_scope:
        _print_section(
            "Boundary short-circuit",
            "S2 returned in_scope=False; pipeline stopped after S2.\n"
            f"Suggested redirect: {result.scope.suggested_redirect or '(none)'}",
        )
        _print_section(
            "ReasoningTrace (serialized)",
            result.trace.model_dump_json(indent=2),
        )
        return 0

    # ── S3 ────────────────────────────────────────────────────────────
    assert result.search_plan is not None  # ensured by orchestrator when in-scope
    _print_section("S3 — SearchPlan", result.search_plan.model_dump_json(indent=2))

    # ── Search execution ──────────────────────────────────────────────
    if result.search_executed:
        urls = [h.url for h in result.search_hits]
        _print_section(
            f"Search executed via {search.name if search else '(none)'} — {len(urls)} hit(s)",
            "\n".join(f"  - {u}" for u in urls) if urls else "(no hits)",
        )
    else:
        reason = (
            "Plan said search not needed."
            if result.search_plan and not result.search_plan.needs_search
            else "Search was needed but no SearchProvider was available."
        )
        _print_section("Search NOT executed", reason)

    if result.search_stats is not None:
        stats = result.search_stats
        _print_section(
            "Search budget stats",
            "\n".join(
                [
                    f"S3 queries: {stats.s3_queries}",
                    f"Search calls made: {stats.search_calls_made}",
                    f"Raw hits: {stats.raw_hits}",
                    f"Unique hits after dedup: {stats.unique_hits_after_dedup}",
                    f"Hits passed to S4: {stats.hits_passed_to_s4}",
                    f"Results capped: {'yes' if stats.results_capped else 'no'}",
                ]
            ),
        )

    # ── S4 ────────────────────────────────────────────────────────────
    assert result.evidence is not None
    _print_section("S4 — EvidenceBase", result.evidence.model_dump_json(indent=2))

    # ── S5 ────────────────────────────────────────────────────────────
    assert result.perspectives is not None
    _print_section(
        "S5 — PerspectiveAnalysis", result.perspectives.model_dump_json(indent=2)
    )

    # ── S6 ────────────────────────────────────────────────────────────
    assert result.verification is not None
    _print_section(
        "S6 — VerificationReport", result.verification.model_dump_json(indent=2)
    )

    # ── S7 ────────────────────────────────────────────────────────────
    assert result.final_response is not None
    _print_section(
        "S7 — FinalResponse", result.final_response.model_dump_json(indent=2)
    )
    _print_section("Final answer (user-facing)", result.final_response.response_text)

    # ── Trace ─────────────────────────────────────────────────────────
    _print_section(
        "ReasoningTrace (serialized)",
        result.trace.model_dump_json(indent=2),
    )

    stage_lines = []
    total_ms = 0
    for entry in result.trace.entries:
        total_ms += entry.duration_ms
        stage_lines.append(f"{entry.stage_id}: {entry.duration_ms} ms")
    _print_section(
        "Stage timing summary",
        "\n".join(stage_lines + [f"Total LLM stage time: {total_ms} ms"]),
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
