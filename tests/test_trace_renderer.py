"""Tests for the Gradio trace renderer (no live API calls)."""

from __future__ import annotations

from datetime import datetime, timezone

from revere_agent.agent.orchestrator import SearchExecutionStats, TurnResult
from revere_agent.schemas import (
    Citation,
    FinalResponse,
    IntakeAnalysis,
    ReasoningTrace,
    ScopeDecision,
    SelfCheckReport,
    StageTraceEntry,
)
from revere_agent.ui.trace_renderer import (
    UIRunOptions,
    render_citations_markdown,
    render_search_budget_markdown,
    render_timing_markdown,
    render_trace_markdown,
)


def _intake() -> IntakeAnalysis:
    return IntakeAnalysis(
        canonical_query="What happened with the 2023 debt ceiling deal?",
        modality="factual",
        user_stated_stance=None,
        multi_turn_dependency=False,
        notes="Factual legislative question.",
    )


def _scope_in() -> ScopeDecision:
    return ScopeDecision(
        in_scope=True,
        confidence=5,
        reasoning="Maps to legislation and policy debate.",
        matched_charter_categories=["legislation"],
        suggested_redirect=None,
        partial_help_possible=False,
    )


def _scope_out() -> ScopeDecision:
    return ScopeDecision(
        in_scope=False,
        confidence=5,
        reasoning="Weather is out of scope.",
        matched_charter_categories=[],
        suggested_redirect="Try weather.gov.",
        partial_help_possible=False,
    )


def _full_trace() -> ReasoningTrace:
    started = datetime(2026, 5, 27, tzinfo=timezone.utc)
    final = FinalResponse(
        response_text="The economy and immigration were major 2024 primary issues.",
        citations=[
            Citation(
                label="Gallup",
                url="https://news.gallup.com/poll/example",
                used_for_claim="Economy ranked as top voter issue.",
            )
        ],
        neutrality_self_check=SelfCheckReport(
            avoided_unsolicited_opinion=True,
            factually_accurate_and_comprehensive=True,
            steelmanned_each_perspective=True,
            neutral_terminology_used=True,
            equal_depth_across_perspectives=True,
            respectful_tone=True,
            revisions_made=["Softened one uncorroborated claim."],
        ),
        residual_uncertainty="Primary-specific emphasis varies by source.",
        suggested_followups=["Want party-by-party breakdown?"],
    )
    return ReasoningTrace(
        turn_id="turn-test-full",
        session_id="sess-test",
        user_message="2024 primary issues?",
        started_at=started,
        entries=[
            StageTraceEntry(
                stage_id="s1_intake",
                prompt_version="abc123",
                model_alias="sonnet-main",
                duration_ms=1000,
                output=_intake().model_dump(mode="json"),
            ),
            StageTraceEntry(
                stage_id="s2_scope",
                prompt_version="def456",
                model_alias="sonnet-main",
                duration_ms=2000,
                output=_scope_in().model_dump(mode="json"),
            ),
            StageTraceEntry(
                stage_id="s3_plan_search",
                prompt_version="ghi789",
                model_alias="sonnet-main",
                duration_ms=1500,
                output={
                    "needs_search": True,
                    "rationale": "Recent event.",
                    "queries": ["2024 primary issues"],
                    "target_source_types": ["polling"],
                    "why_model_knowledge_insufficient": "Need verification.",
                },
            ),
            StageTraceEntry(
                stage_id="s4_source_quality",
                prompt_version="jkl012",
                model_alias="sonnet-main",
                duration_ms=3000,
                output={
                    "assessments": [
                        {
                            "url": "https://example.org/poll",
                            "source_type": "polling",
                            "authority_reasoning": "Authoritative pollster.",
                            "recency_assessment": "2024 data.",
                            "likely_editorial_slant": "center",
                            "slant_evidence": "Nonpartisan.",
                            "primary_vs_secondary": "primary",
                            "relevance_to_query": 5,
                            "confidence_in_source": 5,
                        }
                    ],
                    "confidence_in_evidence": 4,
                    "conflicting_claims": [],
                    "gaps": [],
                },
            ),
            StageTraceEntry(
                stage_id="s5_perspectives",
                prompt_version="mno345",
                model_alias="sonnet-main",
                duration_ms=4000,
                output={
                    "perspectives": [
                        {
                            "label": "economy-first",
                            "core_claims": ["Inflation mattered."],
                            "strongest_evidence": ["Polling data."],
                            "key_concerns_about_other_views": ["Other side ignored costs."],
                            "representative_sources": ["https://example.org/poll"],
                            "steelman_quality_self_assessment": "Reasonable framing.",
                        }
                    ],
                    "areas_of_consensus": ["Economy was salient."],
                    "areas_of_disagreement": ["Immigration emphasis differed."],
                    "empirical_vs_normative": {"Immigration emphasis": "mixed"},
                },
            ),
            StageTraceEntry(
                stage_id="s6_verification",
                prompt_version="pqr678",
                model_alias="sonnet-main",
                duration_ms=2500,
                output={
                    "claims": [
                        {
                            "claim": "Economy was top issue.",
                            "confidence": 5,
                            "verification_basis": "evidence_base",
                            "suggested_hedging": None,
                            "drop_if_uncorroborated": False,
                        }
                    ],
                    "overall_calibration_note": "Most claims corroborated.",
                    "things_i_should_not_assert": [],
                },
            ),
            StageTraceEntry(
                stage_id="s7_compose_check",
                prompt_version="stu901",
                model_alias="sonnet-main",
                duration_ms=3500,
                output=final.model_dump(mode="json"),
            ),
        ],
        final_response=final,
    )


def _out_of_scope_trace() -> ReasoningTrace:
    started = datetime(2026, 5, 27, tzinfo=timezone.utc)
    return ReasoningTrace(
        turn_id="turn-test-oos",
        session_id="sess-test",
        user_message="What's the weather?",
        started_at=started,
        entries=[
            StageTraceEntry(
                stage_id="s1_intake",
                prompt_version="abc123",
                model_alias="sonnet-main",
                duration_ms=800,
                output={
                    "canonical_query": "What is the weather like today?",
                    "modality": "factual",
                    "user_stated_stance": None,
                    "multi_turn_dependency": False,
                    "notes": "Weather query.",
                },
            ),
            StageTraceEntry(
                stage_id="s2_scope",
                prompt_version="def456",
                model_alias="sonnet-main",
                duration_ms=1200,
                output=_scope_out().model_dump(mode="json"),
            ),
        ],
        final_response=None,
    )


def _full_turn_result() -> TurnResult:
    trace = _full_trace()
    return TurnResult(
        trace=trace,
        intake=_intake(),
        scope=_scope_in(),
        search_plan=None,
        search_executed=True,
        search_hits=[],
        search_stats=SearchExecutionStats(
            s3_queries=1,
            search_calls_made=1,
            raw_hits=5,
            unique_hits_after_dedup=4,
            hits_passed_to_s4=4,
            results_capped=False,
        ),
        evidence=None,
        perspectives=None,
        verification=None,
        final_response=trace.final_response,
    )


def _out_of_scope_turn_result() -> TurnResult:
    return TurnResult(
        trace=_out_of_scope_trace(),
        intake=IntakeAnalysis(
            canonical_query="What is the weather like today?",
            modality="factual",
            user_stated_stance=None,
            multi_turn_dependency=False,
            notes="Weather query.",
        ),
        scope=_scope_out(),
    )


def test_trace_renderer_handles_full_trace() -> None:
    md = render_trace_markdown(
        _full_turn_result(),
        options=UIRunOptions(fast_mode=True, max_hits=4),
    )
    assert "Reasoning Trace" in md
    assert "Run Summary" in md
    assert "S1 — Intake" in md
    assert "S7 — Compose" in md
    assert "turn-test-full" in md
    assert "Fast Audit" in md
    assert "Timing Breakdown" in md
    assert "17,500 ms" in md
    assert "Gallup" in render_citations_markdown(_full_turn_result())


def test_trace_renderer_handles_out_of_scope_trace() -> None:
    md = render_trace_markdown(_out_of_scope_turn_result())
    assert "Boundary short-circuit" in md
    assert "S1 — Intake" in md
    assert "S2 — Scope" in md
    assert "S3 — Search Plan" not in md
    assert "Suggested redirect" in md
    assert "Search not run" in md


def test_trace_renderer_handles_missing_citations_and_search_stats() -> None:
    result = _out_of_scope_turn_result()
    citations = render_citations_markdown(result)
    assert "Sources" in citations
    assert "No citations" in citations
    assert "Search Budget" in render_search_budget_markdown(result)
    assert "Search not run" in render_search_budget_markdown(result)
    assert "800 ms" in render_timing_markdown(result)


def test_gradio_app_imports() -> None:
    from revere_agent.ui.gradio_app import build_demo, main

    assert callable(build_demo)
    assert callable(main)
