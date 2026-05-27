"""Day 2 tests for the orchestrator.

Strategy: stub both the LLMProvider and the SearchProvider so we exercise
every control-flow branch in the orchestrator without making a single
network call.

Covers:
- Out-of-scope query short-circuits after S2 (only 2 LLM calls, no search).
- In-scope query with needs_search=False reaches S5 and does NOT call search.
- In-scope query with needs_search=True reaches S5 AND calls search per query.
- The trace records one StageTraceEntry per LLM stage that ran.
- Stage entries carry the correct prompt_version hash from the registry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypeVar

from pydantic import BaseModel

from revere_agent.agent import Orchestrator
from revere_agent.agent.stages.s6_verification import run_s6_verification
from revere_agent.prompts.registry import prompt_version
from revere_agent.schemas import (
    Citation,
    EvidenceBase,
    FinalResponse,
    FactualClaim,
    IntakeAnalysis,
    Perspective,
    PerspectiveAnalysis,
    ScopeDecision,
    SearchHit,
    SearchPlan,
    SelfCheckReport,
    VerificationReport,
)

T = TypeVar("T", bound=BaseModel)


# ── Stub providers ────────────────────────────────────────────────────


@dataclass
class StubLLMProvider:
    """LLM provider that returns canned outputs keyed by output_schema.

    The orchestrator never calls a model — every stage receives a
    pre-built Pydantic object. This isolates orchestrator behavior from
    LLM behavior.
    """

    responses: dict[type[BaseModel], BaseModel]
    name: str = "stub-llm"
    calls: list[tuple[type[BaseModel], dict]] = field(default_factory=list)

    def call_structured(  # noqa: D401 — matches Protocol
        self,
        *,
        system: str,
        user: str,
        output_schema: type[T],
        model_alias: str = "sonnet-main",
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> T:
        self.calls.append(
            (
                output_schema,
                {
                    "system_len": len(system),
                    "user_len": len(user),
                    "user": user,
                    "model_alias": model_alias,
                    "temperature": temperature,
                },
            )
        )
        if output_schema not in self.responses:
            raise KeyError(
                f"StubLLMProvider has no canned response for {output_schema.__name__}"
            )
        return self.responses[output_schema]  # type: ignore[return-value]


@dataclass
class StubSearchProvider:
    """Search provider that returns canned hits and records every call."""

    hits_by_query: dict[str, list[SearchHit]] = field(default_factory=dict)
    default_hits: list[SearchHit] = field(default_factory=list)
    name: str = "stub-search"
    search_calls: list[tuple[str, int, bool]] = field(default_factory=list)
    extract_calls: list[tuple[list[str], bool]] = field(default_factory=list)

    def search(
        self, query: str, *, max_results: int = 5, advanced: bool = True
    ) -> list[SearchHit]:
        self.search_calls.append((query, max_results, advanced))
        return self.hits_by_query.get(query, self.default_hits)

    def extract(self, urls: list[str], *, advanced: bool = True):
        self.extract_calls.append((urls, advanced))
        return []


# ── Canned schema instances ───────────────────────────────────────────


def _intake() -> IntakeAnalysis:
    return IntakeAnalysis(
        canonical_query="What happened with the 2023 debt ceiling deal?",
        modality="factual",
        user_stated_stance=None,
        multi_turn_dependency=False,
        notes="Two-part factual ask: events + party positions.",
    )


def _scope_in() -> ScopeDecision:
    return ScopeDecision(
        in_scope=True,
        confidence=5,
        reasoning="Maps clearly to charter category 'legislation' "
        "(Fiscal Responsibility Act of 2023).",
        matched_charter_categories=["legislation"],
        suggested_redirect=None,
        partial_help_possible=False,
    )


def _scope_out() -> ScopeDecision:
    return ScopeDecision(
        in_scope=False,
        confidence=5,
        reasoning="The user is asking about meteorological information. "
        "The charter explicitly excludes weather.",
        matched_charter_categories=[],
        suggested_redirect="For weather, try weather.gov or your phone's "
        "built-in weather app.",
        partial_help_possible=False,
    )


def _plan_search_yes() -> SearchPlan:
    return SearchPlan(
        needs_search=True,
        rationale="Specific recent legislative event; vote counts and "
        "exact provisions warrant primary-source verification.",
        queries=["Fiscal Responsibility Act 2023 provisions"],
        target_source_types=["government", "primary", "mainstream_news"],
        why_model_knowledge_insufficient="I recall the general outline "
        "but not the exact vote counts.",
    )


def _plan_search_no() -> SearchPlan:
    return SearchPlan(
        needs_search=False,
        rationale="Stable civic-knowledge question; answer is the same "
        "regardless of recent events.",
        queries=[],
        target_source_types=[],
        why_model_knowledge_insufficient=None,
    )


def _evidence_with_sources() -> EvidenceBase:
    return EvidenceBase(
        assessments=[],  # tests don't depend on the per-source content
        confidence_in_evidence=4,
        conflicting_claims=[],
        gaps=[],
    )


def _evidence_model_only() -> EvidenceBase:
    return EvidenceBase(
        assessments=[],
        confidence_in_evidence=3,
        conflicting_claims=[],
        gaps=[
            "Answer relies on model training knowledge; no external "
            "sources were retrieved.",
        ],
    )


def _perspectives_two() -> PerspectiveAnalysis:
    return PerspectiveAnalysis(
        perspectives=[
            Perspective(
                label="fiscal-restraint-first",
                core_claims=["Spending caps are essential.", "Work requirements are appropriate.", "IRS expansion was unwarranted."],
                strongest_evidence=["FY24/25 discretionary caps were enacted."],
                key_concerns_about_other_views=["Worry about deficit growth."],
                representative_sources=[],
                steelman_quality_self_assessment="Proponent would likely endorse this framing.",
            ),
            Perspective(
                label="program-protection-first",
                core_claims=["Clean ceiling raises are the norm.", "IRS funding improves compliance.", "Cuts harm vulnerable groups."],
                strongest_evidence=["CBO estimates on IRS revenue."],
                key_concerns_about_other_views=["Hostage-taking sets a bad precedent."],
                representative_sources=[],
                steelman_quality_self_assessment="Proponent would likely endorse this framing.",
            ),
        ],
        areas_of_consensus=["A default would have caused economic damage."],
        areas_of_disagreement=["Whether the deal's net effect favored either side."],
        empirical_vs_normative={
            "Whether the deal's net effect favored either side.": "mixed",
        },
    )


def _hit(url: str) -> SearchHit:
    return SearchHit(
        url=url,
        title=f"Source for {url}",
        snippet="Snippet",
        published_date="2024-01-01",
        domain="example.org",
        raw_score=0.8,
    )


def _verification_report_weak() -> VerificationReport:
    return VerificationReport(
        claims=[
            FactualClaim(
                claim="The final law passed the House by 314-117.",
                confidence=2,
                verification_basis="uncertain",
                suggested_hedging="Commonly reported vote margins would need verification.",
                drop_if_uncorroborated=True,
            ),
            FactualClaim(
                claim="Both parties framed the compromise as partial wins.",
                confidence=4,
                verification_basis="model_prior",
                suggested_hedging=None,
                drop_if_uncorroborated=False,
            ),
        ],
        overall_calibration_note="Precise figures should be treated cautiously without verified sources.",
        things_i_should_not_assert=["Exact vote counts without corroboration."],
    )


def _final_response() -> FinalResponse:
    return FinalResponse(
        response_text="The major issues were the economy, immigration, abortion, and democratic process concerns.",
        citations=[
            Citation(
                label="Pew 2024 issues",
                url="https://www.pewresearch.org/politics/2024/09/09/issues-and-the-2024-election",
                used_for_claim="Issue salience in 2024 campaign cycle",
            )
        ],
        neutrality_self_check=SelfCheckReport(
            avoided_unsolicited_opinion=True,
            factually_accurate_and_comprehensive=True,
            steelmanned_each_perspective=True,
            neutral_terminology_used=True,
            equal_depth_across_perspectives=True,
            respectful_tone=True,
            revisions_made=["Softened one uncorroborated numeric claim."],
        ),
        residual_uncertainty="Primary-specific issue emphasis varies by source and timing.",
        suggested_followups=[
            "Want a party-by-party issue breakdown?",
            "Want only primary-period sources (pre-convention)?",
        ],
    )


# ── Tests ─────────────────────────────────────────────────────────────


def test_out_of_scope_short_circuits_after_s2() -> None:
    llm = StubLLMProvider(
        responses={
            IntakeAnalysis: _intake(),  # content doesn't matter for this test
            ScopeDecision: _scope_out(),
        }
    )
    search = StubSearchProvider()
    orch = Orchestrator(llm_provider=llm, search_provider=search)  # type: ignore[arg-type]

    result = orch.run_turn("What's the weather like today?")

    # Only S1 + S2 ran.
    assert len(llm.calls) == 2
    assert llm.calls[0][0] is IntakeAnalysis
    assert llm.calls[1][0] is ScopeDecision

    # No search.
    assert search.search_calls == []

    # Result reflects the short-circuit.
    assert result.scope.in_scope is False
    assert result.search_plan is None
    assert result.search_executed is False
    assert result.evidence is None
    assert result.perspectives is None
    assert result.verification is None
    assert result.final_response is None

    # Trace has only S1 + S2 entries.
    assert [e.stage_id for e in result.trace.entries] == ["s1_intake", "s2_scope"]


def test_in_scope_no_search_reaches_s7_and_skips_search() -> None:
    llm = StubLLMProvider(
        responses={
            IntakeAnalysis: _intake(),
            ScopeDecision: _scope_in(),
            SearchPlan: _plan_search_no(),
            EvidenceBase: _evidence_model_only(),
            PerspectiveAnalysis: _perspectives_two(),
            VerificationReport: _verification_report_weak(),
            FinalResponse: _final_response(),
        }
    )
    search = StubSearchProvider()
    orch = Orchestrator(llm_provider=llm, search_provider=search)  # type: ignore[arg-type]

    result = orch.run_turn("What is the filibuster?")

    # All seven LLM stages ran.
    assert len(llm.calls) == 7
    assert [c[0] for c in llm.calls] == [
        IntakeAnalysis,
        ScopeDecision,
        SearchPlan,
        EvidenceBase,
        PerspectiveAnalysis,
        VerificationReport,
        FinalResponse,
    ]

    # Search did NOT run.
    assert search.search_calls == []
    assert result.search_executed is False

    # Full pipeline result.
    assert result.scope.in_scope is True
    assert result.search_plan is not None and result.search_plan.needs_search is False
    assert result.evidence is not None and "model training knowledge" in " ".join(
        result.evidence.gaps
    )
    assert result.perspectives is not None
    assert len(result.perspectives.perspectives) == 2
    assert result.verification is not None
    assert result.final_response is not None
    assert result.trace.final_response is not None

    # Trace has all seven entries in order.
    assert [e.stage_id for e in result.trace.entries] == [
        "s1_intake",
        "s2_scope",
        "s3_plan_search",
        "s4_source_quality",
        "s5_perspectives",
        "s6_verification",
        "s7_compose_check",
    ]


def test_in_scope_with_search_calls_search_provider_per_query() -> None:
    plan = SearchPlan(
        needs_search=True,
        rationale="Specific recent event; verify via primary sources.",
        queries=[
            "Fiscal Responsibility Act 2023 provisions",
            "debt ceiling 2023 House vote count",
        ],
        target_source_types=["government", "mainstream_news"],
        why_model_knowledge_insufficient="Specific vote counts uncertain.",
    )
    hit = SearchHit(
        url="https://www.congress.gov/bill/118th-congress/house-bill/3746",
        title="H.R.3746 - 118th Congress (2023-2024): Fiscal Responsibility Act",
        snippet="Suspends the debt limit through January 1, 2025…",
        published_date="2023-06-03",
        domain="www.congress.gov",
        raw_score=0.92,
    )
    llm = StubLLMProvider(
        responses={
            IntakeAnalysis: _intake(),
            ScopeDecision: _scope_in(),
            SearchPlan: plan,
            EvidenceBase: _evidence_with_sources(),
            PerspectiveAnalysis: _perspectives_two(),
            VerificationReport: _verification_report_weak(),
            FinalResponse: _final_response(),
        }
    )
    search = StubSearchProvider(default_hits=[hit])
    orch = Orchestrator(llm_provider=llm, search_provider=search)  # type: ignore[arg-type]

    result = orch.run_turn(
        "What happened with the debt ceiling negotiations in 2023?"
    )

    # Search ran once per query.
    assert len(search.search_calls) == 2
    assert [c[0] for c in search.search_calls] == plan.queries

    assert result.search_executed is True
    # De-dup leaves a single hit (same URL twice).
    assert len(result.search_hits) == 1
    assert result.search_hits[0].domain == "www.congress.gov"

    # Pipeline reached S7.
    assert result.perspectives is not None
    assert result.verification is not None
    assert result.final_response is not None
    assert result.trace.final_response is not None
    assert result.search_stats is not None
    assert result.search_stats.s3_queries == 2
    assert result.search_stats.search_calls_made == 2
    assert result.search_stats.raw_hits == 2
    assert result.search_stats.unique_hits_after_dedup == 1
    assert result.search_stats.hits_passed_to_s4 == 1
    assert result.search_stats.results_capped is False


def test_search_hit_capping_limits_hits_passed_to_s4() -> None:
    plan = SearchPlan(
        needs_search=True,
        rationale="Needs external grounding.",
        queries=["q1", "q2"],
        target_source_types=["mainstream_news"],
        why_model_knowledge_insufficient="Specifics need checking.",
    )
    hits_q1 = [_hit(f"https://example.org/a{i}") for i in range(1, 6)]
    hits_q2 = [_hit(f"https://example.org/b{i}") for i in range(1, 6)]
    llm = StubLLMProvider(
        responses={
            IntakeAnalysis: _intake(),
            ScopeDecision: _scope_in(),
            SearchPlan: plan,
            EvidenceBase: _evidence_with_sources(),
            PerspectiveAnalysis: _perspectives_two(),
            VerificationReport: _verification_report_weak(),
            FinalResponse: _final_response(),
        }
    )
    search = StubSearchProvider(hits_by_query={"q1": hits_q1, "q2": hits_q2})
    orch = Orchestrator(  # type: ignore[arg-type]
        llm_provider=llm,
        search_provider=search,
        max_unique_hits=6,
    )

    result = orch.run_turn("Any query")

    assert result.search_stats is not None
    assert result.search_stats.raw_hits == 10
    assert result.search_stats.unique_hits_after_dedup == 10
    assert result.search_stats.hits_passed_to_s4 == 6
    assert result.search_stats.results_capped is True
    assert len(result.search_hits) == 6

    # Verify S4 received only the capped set.
    evidence_calls = [c for c in llm.calls if c[0] is EvidenceBase]
    assert len(evidence_calls) == 1
    assert "Retrieved sources (6 hit(s))" in evidence_calls[0][1]["user"]


def test_search_needed_but_no_provider_proceeds_gracefully() -> None:
    """If S3 says search is needed but no SearchProvider is wired, the
    orchestrator must NOT crash. It proceeds with empty hits; S4 will
    document the limitation (we stub the EvidenceBase here)."""
    llm = StubLLMProvider(
        responses={
            IntakeAnalysis: _intake(),
            ScopeDecision: _scope_in(),
            SearchPlan: _plan_search_yes(),
            EvidenceBase: _evidence_model_only(),
            PerspectiveAnalysis: _perspectives_two(),
            VerificationReport: _verification_report_weak(),
            FinalResponse: _final_response(),
        }
    )
    orch = Orchestrator(llm_provider=llm, search_provider=None)  # type: ignore[arg-type]

    result = orch.run_turn("Specific factual question…")

    assert result.search_executed is False
    assert result.search_hits == []
    assert result.final_response is not None  # pipeline still finished


def test_trace_entries_carry_prompt_version_hashes() -> None:
    llm = StubLLMProvider(
        responses={
            IntakeAnalysis: _intake(),
            ScopeDecision: _scope_in(),
            SearchPlan: _plan_search_no(),
            EvidenceBase: _evidence_model_only(),
            PerspectiveAnalysis: _perspectives_two(),
            VerificationReport: _verification_report_weak(),
            FinalResponse: _final_response(),
        }
    )
    orch = Orchestrator(llm_provider=llm, search_provider=None)  # type: ignore[arg-type]

    result = orch.run_turn("What is the filibuster?")

    # Every entry's prompt_version matches the registry's current hash.
    for entry in result.trace.entries:
        assert entry.prompt_version == prompt_version(entry.stage_id)
        assert len(entry.prompt_version) == 12  # short SHA1
        assert entry.model_alias == "sonnet-main"


def test_s6_weak_evidence_can_mark_precise_claims_uncertain_drop() -> None:
    """Stage runner should pass weak-evidence context and accept uncertain/drop claims."""
    llm = StubLLMProvider(
        responses={VerificationReport: _verification_report_weak()}
    )

    report = run_s6_verification(
        provider=llm,  # type: ignore[arg-type]
        intake=_intake(),
        evidence=_evidence_model_only(),
        perspectives=_perspectives_two(),
    )
    assert any(
        c.verification_basis == "uncertain" and c.drop_if_uncorroborated
        for c in report.claims
    )
    s6_calls = [c for c in llm.calls if c[0] is VerificationReport]
    assert len(s6_calls) == 1
    assert "Weak evidence mode: YES" in s6_calls[0][1]["user"]


def test_s7_schema_round_trip_in_orchestrator() -> None:
    llm = StubLLMProvider(
        responses={
            IntakeAnalysis: _intake(),
            ScopeDecision: _scope_in(),
            SearchPlan: _plan_search_no(),
            EvidenceBase: _evidence_model_only(),
            PerspectiveAnalysis: _perspectives_two(),
            VerificationReport: _verification_report_weak(),
            FinalResponse: _final_response(),
        }
    )
    orch = Orchestrator(llm_provider=llm, search_provider=None)  # type: ignore[arg-type]
    result = orch.run_turn("What happened?")
    assert result.final_response is not None
    assert isinstance(result.final_response, FinalResponse)
    assert result.final_response.response_text


def test_existing_day1_tests_still_pass_via_import() -> None:
    """Day 1 modules still import without breakage after Day 2 additions."""
    from revere_agent.llm import (  # noqa: F401
        AnthropicProvider,
        BedrockProvider,
        make_provider_from_env,
    )
    from revere_agent.schemas import IntakeAnalysis as _Intake  # noqa: F401
    from revere_agent.search import TavilyProvider  # noqa: F401

    # A representative Day 1 invariant: every schema we'd hand to Claude is
    # still extra-forbidden.
    assert IntakeAnalysis.model_json_schema()["additionalProperties"] is False
