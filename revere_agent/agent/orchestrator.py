"""Orchestrator — deterministic Python that sequences the reasoning stages.

Design contract:
  - The orchestrator owns control flow (ordering, short-circuits, when to
    call SearchProvider).
  - Each stage function owns ONE LLM call and returns a Pydantic-typed
    output.
  - All reasoning is in the LLM; all branching is in this file.

There is exactly one allowed short-circuit on Day 2: if S2 returns
in_scope=False, the orchestrator stops after S2 and returns a result
whose later fields are None. The ScopeDecision's `suggested_redirect` IS
the graceful boundary output — we don't make an extra LLM call to compose
one. That keeps the boundary path cheap and the trace honest.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from revere_agent.llm.provider import LLMProvider, ModelAlias
from revere_agent.prompts.registry import prompt_version
from revere_agent.schemas import (
    EvidenceBase,
    FinalResponse,
    IntakeAnalysis,
    PerspectiveAnalysis,
    ReasoningTrace,
    ScopeDecision,
    SearchHit,
    SearchPlan,
    StageTraceEntry,
    VerificationReport,
)
from revere_agent.search.provider import SearchProvider

from .stages import (
    run_s1_intake,
    run_s2_scope,
    run_s3_plan_search,
    run_s4_source_quality,
    run_s5_perspectives,
    run_s6_verification,
    run_s7_compose_check,
)
from .state import ConversationState


@dataclass
class TurnResult:
    """The full payload of one orchestrator run, plus the reasoning trace.

    Fields after `scope` are Optional because the out-of-scope short-circuit
    stops the pipeline after S2. The trace is always populated with whatever
    stages actually ran.
    """

    trace: ReasoningTrace
    intake: IntakeAnalysis
    scope: ScopeDecision
    search_plan: SearchPlan | None = None
    search_executed: bool = False
    search_hits: list[SearchHit] = field(default_factory=list)
    search_stats: "SearchExecutionStats" | None = None
    evidence: EvidenceBase | None = None
    perspectives: PerspectiveAnalysis | None = None
    verification: VerificationReport | None = None
    final_response: FinalResponse | None = None


@dataclass
class SearchExecutionStats:
    """Budget/accounting metrics for S3 search execution."""

    s3_queries: int
    search_calls_made: int
    raw_hits: int
    unique_hits_after_dedup: int
    hits_passed_to_s4: int
    results_capped: bool


class Orchestrator:
    """Sequences S1→S7 and assembles a ReasoningTrace."""

    def __init__(
        self,
        llm_provider: LLMProvider,
        search_provider: SearchProvider | None = None,
        *,
        model_alias: ModelAlias = "sonnet-main",
        search_max_results: int = 5,
        max_unique_hits: int = 6,
    ) -> None:
        # Search is optional at construction. If S3 says we need search and
        # no provider is wired, we proceed with empty hits and let S4
        # document the limitation. This keeps the orchestrator usable in
        # unit tests and offline experiments.
        self.llm = llm_provider
        self.search = search_provider
        self.model_alias = model_alias
        self.search_max_results = search_max_results
        self.max_unique_hits = max_unique_hits

    # ── Public entry point ────────────────────────────────────────────

    def run_turn(
        self,
        user_message: str,
        state: ConversationState | None = None,
    ) -> TurnResult:
        state = state or ConversationState()
        trace = ReasoningTrace(
            turn_id=f"turn-{uuid.uuid4().hex[:12]}",
            session_id=state.session_id,
            user_message=user_message,
            started_at=datetime.now(timezone.utc),
            entries=[],
        )

        # ── S1 ────────────────────────────────────────────────────────
        intake = self._record(
            trace,
            "s1_intake",
            lambda: run_s1_intake(self.llm, user_message, state.history),
        )

        # ── S2 ────────────────────────────────────────────────────────
        scope = self._record(
            trace,
            "s2_scope",
            lambda: run_s2_scope(self.llm, intake, state.history),
        )

        # ── Short-circuit on out-of-scope ─────────────────────────────
        # This is the ONE deterministic branch allowed today. The
        # ScopeDecision already carries the graceful boundary content in
        # its suggested_redirect field; no additional LLM call needed.
        if not scope.in_scope:
            return TurnResult(trace=trace, intake=intake, scope=scope)

        # ── S3 ────────────────────────────────────────────────────────
        plan = self._record(
            trace,
            "s3_plan_search",
            lambda: run_s3_plan_search(self.llm, intake),
        )

        # ── Search execution (no LLM call; pure I/O) ──────────────────
        hits: list[SearchHit] = []
        unique_hits: list[SearchHit] = []
        search_executed = False
        search_calls_made = 0
        raw_hits_count = 0
        results_capped = False
        if plan.needs_search and self.search is not None and plan.queries:
            search_executed = True
            for query in plan.queries:
                query_hits = self.search.search(
                    query, max_results=self.search_max_results, advanced=True
                )
                search_calls_made += 1
                raw_hits_count += len(query_hits)
                hits.extend(query_hits)
            # De-dup by URL while preserving order.
            seen: set[str] = set()
            deduped: list[SearchHit] = []
            for h in hits:
                if h.url not in seen:
                    seen.add(h.url)
                    deduped.append(h)
            unique_hits = deduped
            results_capped = len(unique_hits) > self.max_unique_hits
            hits = unique_hits[: self.max_unique_hits]

        search_stats = SearchExecutionStats(
            s3_queries=len(plan.queries),
            search_calls_made=search_calls_made,
            raw_hits=raw_hits_count,
            unique_hits_after_dedup=len(unique_hits),
            hits_passed_to_s4=len(hits),
            results_capped=results_capped,
        )

        # ── S4 ────────────────────────────────────────────────────────
        evidence = self._record(
            trace,
            "s4_source_quality",
            lambda: run_s4_source_quality(
                self.llm,
                intake,
                hits,
                extracted=None,  # Day 3+ may add extract() for top hits
                search_was_performed=search_executed,
            ),
        )

        # ── S5 ────────────────────────────────────────────────────────
        perspectives = self._record(
            trace,
            "s5_perspectives",
            lambda: run_s5_perspectives(self.llm, intake, evidence),
        )

        # ── S6 ────────────────────────────────────────────────────────
        verification = self._record(
            trace,
            "s6_verification",
            lambda: run_s6_verification(self.llm, intake, evidence, perspectives),
        )

        # ── S7 ────────────────────────────────────────────────────────
        final_response = self._record(
            trace,
            "s7_compose_check",
            lambda: run_s7_compose_check(
                self.llm,
                intake,
                evidence,
                perspectives,
                verification,
            ),
        )
        trace.final_response = final_response

        return TurnResult(
            trace=trace,
            intake=intake,
            scope=scope,
            search_plan=plan,
            search_executed=search_executed,
            search_hits=hits,
            search_stats=search_stats,
            evidence=evidence,
            perspectives=perspectives,
            verification=verification,
            final_response=final_response,
        )

    # ── Internals ─────────────────────────────────────────────────────

    def _record(self, trace: ReasoningTrace, stage_id: str, fn):
        """Call a stage, time it, append a StageTraceEntry, return the output."""
        start = time.monotonic()
        output = fn()
        duration_ms = int((time.monotonic() - start) * 1000)
        trace.entries.append(
            StageTraceEntry(
                stage_id=stage_id,
                prompt_version=prompt_version(stage_id),
                model_alias=self.model_alias,
                duration_ms=duration_ms,
                output=output.model_dump(mode="json"),
            )
        )
        return output
