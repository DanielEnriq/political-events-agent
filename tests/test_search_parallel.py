"""Tests for parallel search query execution in the orchestrator.

Strategy:
- Use a slow fake SearchProvider (sleeps per call) to confirm that 3 concurrent
  queries complete faster than they would serially.
- Verify result ordering, deduplication, and cap behavior are unchanged.
- Import _run_search_queries directly so we can test the helper in isolation.
"""

from __future__ import annotations

import time
import threading
from dataclasses import dataclass, field
from typing import TypeVar

import pytest
from pydantic import BaseModel

from revere_agent.agent.orchestrator import Orchestrator, _run_search_queries
from revere_agent.schemas import (
    EvidenceBase,
    FinalResponse,
    FactualClaim,
    IntakeAnalysis,
    Citation,
    Perspective,
    PerspectiveAnalysis,
    ScopeDecision,
    SearchHit,
    SearchPlan,
    SelfCheckReport,
    VerificationReport,
)

T = TypeVar("T", bound=BaseModel)


# ── Helpers ───────────────────────────────────────────────────────────


def _make_hit(url: str, query: str = "") -> SearchHit:
    return SearchHit(
        url=url,
        title=f"Result for {url}",
        snippet="A snippet.",
        published_date="2024-01-01",
        domain=url.split("/")[2] if "/" in url else url,
        raw_score=0.9,
    )


class SlowSearchProvider:
    """Returns one hit per query after a configurable delay.

    Records the precise wall-clock time each search call started so tests
    can verify that concurrent calls overlapped.
    """

    name = "slow-search"

    def __init__(self, delay: float = 0.2) -> None:
        self.delay = delay
        self.call_log: list[tuple[str, float]] = []
        self._lock = threading.Lock()

    def search(self, query: str, *, max_results: int = 5, advanced: bool = True) -> list[SearchHit]:
        start = time.monotonic()
        with self._lock:
            self.call_log.append((query, start))
        time.sleep(self.delay)
        return [_make_hit(f"https://example.org/{query.replace(' ', '-')}")]

    def extract(self, urls: list[str], *, advanced: bool = True) -> list:
        return []


class OrderedSlowSearch:
    """Returns hits with distinct URLs per query, in deterministic order."""

    name = "ordered-slow-search"

    def __init__(self, hits_by_query: dict[str, list[SearchHit]], delay: float = 0.05) -> None:
        self.hits_by_query = hits_by_query
        self.delay = delay

    def search(self, query: str, *, max_results: int = 5, advanced: bool = True) -> list[SearchHit]:
        time.sleep(self.delay)
        return self.hits_by_query.get(query, [])

    def extract(self, urls: list[str], *, advanced: bool = True) -> list:
        return []


# ── Tests for _run_search_queries directly ───────────────────────────


def test_parallel_is_faster_than_serial() -> None:
    """Three queries with 0.2s delay each should complete well under 0.6s."""
    provider = SlowSearchProvider(delay=0.2)
    queries = ["query-alpha", "query-beta", "query-gamma"]

    start = time.monotonic()
    hits = _run_search_queries(provider, queries, max_results=5)
    elapsed = time.monotonic() - start

    # Serial would take at least 0.6s; concurrent should finish in <0.45s.
    assert elapsed < 0.45, (
        f"Expected parallel completion in <0.45s, got {elapsed:.3f}s. "
        "This may indicate the queries are running serially."
    )
    # All three queries returned a hit.
    assert len(hits) == 3


def test_result_order_matches_query_order() -> None:
    """Hits must come back in query order, not completion order.

    executor.map() guarantees this even when the fastest query finishes last.
    We verify by having the second query return a distinct URL and checking
    its position in the output.
    """
    hits_by_query = {
        "q1": [_make_hit("https://example.org/q1-result")],
        "q2": [_make_hit("https://example.org/q2-result")],
        "q3": [_make_hit("https://example.org/q3-result")],
    }
    provider = OrderedSlowSearch(hits_by_query)
    queries = ["q1", "q2", "q3"]

    hits = _run_search_queries(provider, queries, max_results=5)

    assert len(hits) == 3
    assert hits[0].url == "https://example.org/q1-result"
    assert hits[1].url == "https://example.org/q2-result"
    assert hits[2].url == "https://example.org/q3-result"


def test_all_queries_are_called() -> None:
    """Every query in the list must produce a search call."""
    provider = SlowSearchProvider(delay=0.05)
    queries = ["topic-a", "topic-b", "topic-c"]

    _run_search_queries(provider, queries, max_results=5)

    called_queries = {q for q, _ in provider.call_log}
    assert called_queries == set(queries)


def test_single_query_still_works() -> None:
    """Edge case: a single query must not cause errors."""
    provider = SlowSearchProvider(delay=0.05)
    hits = _run_search_queries(provider, ["only-query"], max_results=5)
    assert len(hits) == 1


def test_multiple_hits_per_query_are_all_returned() -> None:
    """When each query returns multiple hits, all of them appear in output."""
    hits_by_query = {
        "q1": [_make_hit(f"https://example.org/q1-{i}") for i in range(3)],
        "q2": [_make_hit(f"https://example.org/q2-{i}") for i in range(2)],
    }
    provider = OrderedSlowSearch(hits_by_query)
    hits = _run_search_queries(provider, ["q1", "q2"], max_results=5)
    assert len(hits) == 5  # 3 + 2


# ── Integration tests through Orchestrator ───────────────────────────


@dataclass
class StubLLMProvider:
    responses: dict[type[BaseModel], BaseModel]
    name: str = "stub-llm"
    calls: list = field(default_factory=list)

    def call_structured(self, *, system, user, output_schema, model_alias="sonnet-main", temperature=0.3, max_tokens=4096):
        self.calls.append((output_schema, {"user_len": len(user)}))
        return self.responses[output_schema]  # type: ignore[return-value]


def _build_full_llm(plan: SearchPlan) -> StubLLMProvider:
    return StubLLMProvider(
        responses={
            IntakeAnalysis: IntakeAnalysis(
                canonical_query="What is the filibuster?",
                modality="factual",
                user_stated_stance=None,
                multi_turn_dependency=False,
                notes="",
            ),
            ScopeDecision: ScopeDecision(
                in_scope=True,
                confidence=5,
                reasoning="In scope.",
                matched_charter_categories=["political_institutions"],
                suggested_redirect=None,
                partial_help_possible=False,
            ),
            SearchPlan: plan,
            EvidenceBase: EvidenceBase(
                assessments=[],
                confidence_in_evidence=3,
                conflicting_claims=[],
                gaps=["Model knowledge only."],
            ),
            PerspectiveAnalysis: PerspectiveAnalysis(
                perspectives=[
                    Perspective(
                        label="perspective-a",
                        core_claims=["Claim A"],
                        strongest_evidence=["Evidence A"],
                        key_concerns_about_other_views=[],
                        representative_sources=[],
                        steelman_quality_self_assessment="Good.",
                    )
                ],
                areas_of_consensus=[],
                areas_of_disagreement=[],
                empirical_vs_normative={},
            ),
            VerificationReport: VerificationReport(
                claims=[
                    FactualClaim(
                        claim="Some claim.",
                        confidence=3,
                        verification_basis="model_prior",
                        suggested_hedging="Use caution.",
                        drop_if_uncorroborated=False,
                    )
                ],
                overall_calibration_note="Reasonable confidence.",
                things_i_should_not_assert=[],
            ),
            FinalResponse: FinalResponse(
                response_text="The filibuster is a Senate procedure.",
                citations=[],
                neutrality_self_check=SelfCheckReport(
                    avoided_unsolicited_opinion=True,
                    factually_accurate_and_comprehensive=True,
                    steelmanned_each_perspective=True,
                    neutral_terminology_used=True,
                    equal_depth_across_perspectives=True,
                    respectful_tone=True,
                    evidence_proportional_to_sources=True,
                    revisions_made=[],
                ),
                residual_uncertainty="Standard civic knowledge.",
                suggested_followups=["Learn more?"],
            ),
        }
    )


def test_orchestrator_parallel_search_dedup_and_cap() -> None:
    """Deduplication and cap logic work correctly after parallel query execution."""
    plan = SearchPlan(
        needs_search=True,
        rationale="Needs search.",
        queries=["q1", "q2", "q3"],
        target_source_types=["mainstream_news"],
        why_model_knowledge_insufficient="Needs checking.",
    )
    # q1 and q2 share a URL — dedup should remove it.
    shared_url = "https://shared.example.org/article"
    hits_by_query = {
        "q1": [_make_hit(shared_url), _make_hit("https://a.example.org/1")],
        "q2": [_make_hit(shared_url), _make_hit("https://b.example.org/2")],
        "q3": [_make_hit("https://c.example.org/3"), _make_hit("https://d.example.org/4")],
    }
    search = OrderedSlowSearch(hits_by_query, delay=0.05)
    llm = _build_full_llm(plan)
    orch = Orchestrator(llm_provider=llm, search_provider=search, max_unique_hits=4)  # type: ignore[arg-type]

    result = orch.run_turn("Any query")

    assert result.search_executed is True
    stats = result.search_stats
    assert stats is not None
    assert stats.search_calls_made == 3
    assert stats.raw_hits == 6
    assert stats.unique_hits_after_dedup == 5  # shared_url counted once
    assert stats.hits_passed_to_s4 == 4       # capped at max_unique_hits=4
    assert stats.results_capped is True
    assert len(result.search_hits) == 4


def test_orchestrator_parallel_search_stats_match_query_count() -> None:
    """search_calls_made must equal the number of queries, not accumulate per hit."""
    plan = SearchPlan(
        needs_search=True,
        rationale="Needs search.",
        queries=["query-one", "query-two"],
        target_source_types=["mainstream_news"],
        why_model_knowledge_insufficient="Specifics need checking.",
    )
    search = SlowSearchProvider(delay=0.05)
    llm = _build_full_llm(plan)
    orch = Orchestrator(llm_provider=llm, search_provider=search)  # type: ignore[arg-type]

    result = orch.run_turn("Any query")

    stats = result.search_stats
    assert stats is not None
    assert stats.s3_queries == 2
    assert stats.search_calls_made == 2
    # Both queries were actually called.
    called_queries = {q for q, _ in search.call_log}
    assert called_queries == {"query-one", "query-two"}
