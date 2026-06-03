"""Tests for EvidenceSufficiency derivation and its integration with stage runners."""

from __future__ import annotations

from revere_agent.agent.evidence_sufficiency import (
    EvidenceSufficiency,
    derive_evidence_sufficiency,
)
from revere_agent.schemas import EvidenceBase, EvidenceCoverage, SearchPlan


# ── Helpers ───────────────────────────────────────────────────────────────────


def _plan(
    needs_search: bool = True,
    target_types: list[str] | None = None,
) -> SearchPlan:
    return SearchPlan(
        needs_search=needs_search,
        rationale="Test plan.",
        queries=["q1"] if needs_search else [],
        target_source_types=target_types or [],
        why_model_knowledge_insufficient="Test." if needs_search else None,
    )


def _coverage(
    has_primary: bool = False,
    has_court: bool = False,
    has_government: bool = False,
    asymmetric: bool = False,
    asymmetry_note: str | None = None,
) -> EvidenceCoverage:
    return EvidenceCoverage(
        has_primary_sources=has_primary,
        has_court_sources=has_court,
        has_government_sources=has_government,
        perspective_coverage_asymmetric=asymmetric,
        asymmetry_note=asymmetry_note,
    )


def _evidence(
    confidence: int = 4,
    gaps: list[str] | None = None,
    source_types: list[str] | None = None,
    coverage: EvidenceCoverage | None = None,
) -> EvidenceBase:
    from revere_agent.schemas import SourceAssessment

    assessments = []
    for i, stype in enumerate(source_types or []):
        assessments.append(
            SourceAssessment(
                url=f"https://example.org/{i}",
                source_type=stype,  # type: ignore[arg-type]
                authority_reasoning="Test.",
                recency_assessment="Recent.",
                likely_editorial_slant="center",
                slant_evidence="Test.",
                primary_vs_secondary="secondary",
                relevance_to_query=3,
                confidence_in_source=3,
            )
        )
    return EvidenceBase(
        assessments=assessments,
        confidence_in_evidence=confidence,
        conflicting_claims=[],
        gaps=gaps or [],
        coverage=coverage,
    )


# ── Unit tests: Flag 1 — confidence threshold ─────────────────────────────────


def test_restricted_when_low_confidence() -> None:
    suf = derive_evidence_sufficiency(
        plan=_plan(needs_search=False),
        evidence=_evidence(confidence=3),
        search_executed=False,
    )
    assert suf.restricted_empirical_claims_required is True
    assert suf.confidence_in_evidence == 3
    assert any("confidence" in r.lower() for r in suf.reasons)


def test_unrestricted_when_clean_evidence() -> None:
    suf = derive_evidence_sufficiency(
        plan=_plan(needs_search=False),
        evidence=_evidence(confidence=4, coverage=_coverage()),
        search_executed=False,
    )
    assert suf.restricted_empirical_claims_required is False
    assert suf.primary_sources_missing is False
    assert suf.requested_source_types_missing == []
    assert suf.perspective_coverage_asymmetric is False
    assert suf.has_constraints is False
    assert suf.as_prompt_note() is None


# ── Unit tests: Flag 2 — primary sources missing (structured path) ────────────


def test_primary_missing_when_search_executed_and_coverage_says_no_primary() -> None:
    suf = derive_evidence_sufficiency(
        plan=_plan(needs_search=True, target_types=["mainstream_news"]),
        evidence=_evidence(
            confidence=4,
            source_types=["mainstream_news"],
            coverage=_coverage(has_primary=False),
        ),
        search_executed=True,
    )
    assert suf.primary_sources_missing is True
    assert suf.restricted_empirical_claims_required is True
    assert any("primary" in r.lower() for r in suf.reasons)


def test_primary_not_missing_when_coverage_says_has_primary() -> None:
    suf = derive_evidence_sufficiency(
        plan=_plan(needs_search=True, target_types=["government"]),
        evidence=_evidence(
            confidence=4,
            coverage=_coverage(has_primary=True, has_government=True),
        ),
        search_executed=True,
    )
    assert suf.primary_sources_missing is False


def test_primary_not_missing_when_coverage_says_has_court() -> None:
    """Court sources satisfy primary-source presence check."""
    suf = derive_evidence_sufficiency(
        plan=_plan(needs_search=True),
        evidence=_evidence(
            confidence=4,
            coverage=_coverage(has_primary=True, has_court=True),
        ),
        search_executed=True,
    )
    assert suf.primary_sources_missing is False


def test_no_primary_missing_check_when_search_not_executed() -> None:
    suf = derive_evidence_sufficiency(
        plan=_plan(needs_search=False),
        evidence=_evidence(confidence=4, coverage=_coverage(has_primary=False)),
        search_executed=False,
    )
    assert suf.primary_sources_missing is False


# ── Unit tests: Flag 3 — missing requested source types (structured path) ─────


def test_requested_primary_missing_when_coverage_says_no_primary() -> None:
    suf = derive_evidence_sufficiency(
        plan=_plan(needs_search=True, target_types=["primary"]),
        evidence=_evidence(confidence=4, coverage=_coverage(has_primary=False)),
        search_executed=True,
    )
    assert "primary" in suf.requested_source_types_missing
    assert suf.restricted_empirical_claims_required is True


def test_requested_court_missing_when_coverage_says_no_court() -> None:
    suf = derive_evidence_sufficiency(
        plan=_plan(needs_search=True, target_types=["court"]),
        evidence=_evidence(confidence=4, coverage=_coverage(has_court=False)),
        search_executed=True,
    )
    assert "court" in suf.requested_source_types_missing


def test_requested_government_missing_when_coverage_says_no_government() -> None:
    suf = derive_evidence_sufficiency(
        plan=_plan(needs_search=True, target_types=["government"]),
        evidence=_evidence(confidence=4, coverage=_coverage(has_government=False)),
        search_executed=True,
    )
    assert "government" in suf.requested_source_types_missing


def test_requested_primary_satisfied_when_coverage_says_has_primary() -> None:
    suf = derive_evidence_sufficiency(
        plan=_plan(needs_search=True, target_types=["primary", "mainstream_news"]),
        evidence=_evidence(
            confidence=4,
            coverage=_coverage(has_primary=True),
        ),
        search_executed=True,
    )
    assert "primary" not in suf.requested_source_types_missing
    assert suf.primary_sources_missing is False


def test_requested_court_satisfied_when_coverage_says_has_court() -> None:
    """S3 requested 'court'; coverage.has_court_sources=True → not missing."""
    suf = derive_evidence_sufficiency(
        plan=_plan(needs_search=True, target_types=["court"]),
        evidence=_evidence(
            confidence=4,
            coverage=_coverage(has_primary=True, has_court=True),
        ),
        search_executed=True,
    )
    assert "court" not in suf.requested_source_types_missing


def test_requested_government_satisfied_when_coverage_says_has_government() -> None:
    suf = derive_evidence_sufficiency(
        plan=_plan(needs_search=True, target_types=["government"]),
        evidence=_evidence(
            confidence=4,
            coverage=_coverage(has_primary=True, has_government=True),
        ),
        search_executed=True,
    )
    assert "government" not in suf.requested_source_types_missing


def test_multiple_requested_types_partial_missing() -> None:
    suf = derive_evidence_sufficiency(
        plan=_plan(needs_search=True, target_types=["government", "court", "mainstream_news"]),
        evidence=_evidence(
            confidence=4,
            source_types=["mainstream_news"],
            coverage=_coverage(has_primary=False, has_court=False, has_government=False),
        ),
        search_executed=True,
    )
    assert "government" in suf.requested_source_types_missing
    assert "court" in suf.requested_source_types_missing
    assert "mainstream_news" not in suf.requested_source_types_missing
    assert suf.restricted_empirical_claims_required is True


# ── Unit tests: Flag 4 — asymmetric coverage (structured path) ───────────────


def test_asymmetry_detected_from_structured_coverage_flag() -> None:
    suf = derive_evidence_sufficiency(
        plan=_plan(needs_search=False),
        evidence=_evidence(
            confidence=4,
            coverage=_coverage(
                asymmetric=True,
                asymmetry_note="Sources favour the enforcement-first perspective.",
            ),
        ),
        search_executed=False,
    )
    assert suf.perspective_coverage_asymmetric is True
    assert suf.has_constraints is True
    assert any("enforcement-first" in r for r in suf.reasons)


def test_no_asymmetry_when_coverage_flag_is_false() -> None:
    suf = derive_evidence_sufficiency(
        plan=_plan(needs_search=False),
        evidence=_evidence(
            confidence=4,
            coverage=_coverage(asymmetric=False),
        ),
        search_executed=False,
    )
    assert suf.perspective_coverage_asymmetric is False


def test_asymmetry_reason_uses_generic_note_when_asymmetry_note_absent() -> None:
    suf = derive_evidence_sufficiency(
        plan=_plan(needs_search=False),
        evidence=_evidence(
            confidence=4,
            coverage=_coverage(asymmetric=True, asymmetry_note=None),
        ),
        search_executed=False,
    )
    assert suf.perspective_coverage_asymmetric is True
    assert any("asymmetric" in r.lower() for r in suf.reasons)


# ── Unit tests: fallback path (coverage=None) ─────────────────────────────────


def test_fallback_primary_missing_uses_source_type_comparison() -> None:
    """When coverage is None, Flag 2 uses source_type enum comparison (no domain expansion)."""
    suf = derive_evidence_sufficiency(
        plan=_plan(needs_search=True, target_types=["mainstream_news"]),
        evidence=_evidence(confidence=4, source_types=["mainstream_news"]),
        search_executed=True,
    )
    assert suf.primary_sources_missing is True


def test_fallback_primary_not_missing_when_court_type_retrieved() -> None:
    """Fallback: source_type='court' satisfies primary-class check."""
    suf = derive_evidence_sufficiency(
        plan=_plan(needs_search=True, target_types=["mainstream_news"]),
        evidence=_evidence(confidence=4, source_types=["court"]),
        search_executed=True,
    )
    assert suf.primary_sources_missing is False


def test_fallback_primary_not_missing_when_government_type_retrieved() -> None:
    """Fallback: source_type='government' satisfies primary-class check."""
    suf = derive_evidence_sufficiency(
        plan=_plan(needs_search=True),
        evidence=_evidence(confidence=4, source_types=["government"]),
        search_executed=True,
    )
    assert suf.primary_sources_missing is False


def test_fallback_no_asymmetry_detection() -> None:
    """Fallback (coverage=None) does not detect asymmetry — skip, not misfire."""
    suf = derive_evidence_sufficiency(
        plan=_plan(needs_search=False),
        evidence=_evidence(confidence=4, gaps=["Sources are one-sided."]),
        search_executed=False,
    )
    assert suf.perspective_coverage_asymmetric is False


def test_fallback_missing_requested_types_exact_match() -> None:
    """Fallback uses exact source_type match for requested primary-class types."""
    suf = derive_evidence_sufficiency(
        plan=_plan(needs_search=True, target_types=["government", "court"]),
        evidence=_evidence(confidence=4, source_types=["mainstream_news"]),
        search_executed=True,
    )
    assert "government" in suf.requested_source_types_missing
    assert "court" in suf.requested_source_types_missing


def test_fallback_requested_court_satisfied_when_court_type_retrieved() -> None:
    """Fallback: exact source_type='court' satisfies requested 'court'."""
    suf = derive_evidence_sufficiency(
        plan=_plan(needs_search=True, target_types=["court"]),
        evidence=_evidence(confidence=4, source_types=["court"]),
        search_executed=True,
    )
    assert "court" not in suf.requested_source_types_missing


# ── Prompt note format ────────────────────────────────────────────────────────


def test_prompt_note_includes_key_fields_when_restricted() -> None:
    suf = EvidenceSufficiency(
        primary_sources_missing=True,
        requested_source_types_missing=["government"],
        perspective_coverage_asymmetric=False,
        restricted_empirical_claims_required=True,
        confidence_in_evidence=3,
        reasons=["Evidence confidence 3/5 is low"],
    )
    note = suf.as_prompt_note()
    assert note is not None
    assert "Restricted empirical-claim mode: YES" in note
    assert "government" in note
    assert "Downstream requirement" in note


def test_prompt_note_is_none_when_no_constraints() -> None:
    suf = EvidenceSufficiency(
        restricted_empirical_claims_required=False,
        primary_sources_missing=False,
        requested_source_types_missing=[],
        perspective_coverage_asymmetric=False,
        confidence_in_evidence=4,
        reasons=[],
    )
    assert suf.as_prompt_note() is None


# ── Integration: sufficiency note in stage user_content ──────────────────────


def test_sufficiency_note_injected_into_s5_user_content(monkeypatch) -> None:
    """When sufficiency has constraints, the note appears in S5's user prompt."""
    from dataclasses import dataclass, field
    from typing import TypeVar

    from pydantic import BaseModel

    from revere_agent.agent.stages.s5_perspectives import run_s5_perspectives
    from revere_agent.schemas import (
        IntakeAnalysis,
        Perspective,
        PerspectiveAnalysis,
    )

    T = TypeVar("T", bound=BaseModel)

    captured: list[str] = []

    @dataclass
    class CaptureLLM:
        name: str = "capture"

        def call_structured(self, *, system: str, user: str, output_schema: type[T], **kw) -> T:
            captured.append(user)
            return PerspectiveAnalysis(  # type: ignore[return-value]
                perspectives=[
                    Perspective(
                        label="a",
                        core_claims=["c"],
                        strongest_evidence=["e"],
                        key_concerns_about_other_views=["w"],
                        steelman_quality_self_assessment="ok",
                    ),
                    Perspective(
                        label="b",
                        core_claims=["c"],
                        strongest_evidence=["e"],
                        key_concerns_about_other_views=["w"],
                        steelman_quality_self_assessment="ok",
                    ),
                ]
            )

    intake = IntakeAnalysis(
        canonical_query="Test?",
        modality="factual",
        user_stated_stance=None,
        multi_turn_dependency=False,
        notes="Test.",
    )
    evidence = _evidence(confidence=2)
    suf = derive_evidence_sufficiency(_plan(needs_search=False), evidence, False)
    assert suf.restricted_empirical_claims_required is True

    run_s5_perspectives(CaptureLLM(), intake, evidence, sufficiency=suf)  # type: ignore[arg-type]

    assert len(captured) == 1
    assert "Evidence sufficiency constraints" in captured[0]
    assert "Restricted empirical-claim mode: YES" in captured[0]


def test_no_note_injected_into_s5_when_clean(monkeypatch) -> None:
    """When evidence is clean, no constraint note is added to S5's prompt."""
    from dataclasses import dataclass
    from typing import TypeVar

    from pydantic import BaseModel

    from revere_agent.agent.stages.s5_perspectives import run_s5_perspectives
    from revere_agent.schemas import IntakeAnalysis, Perspective, PerspectiveAnalysis

    T = TypeVar("T", bound=BaseModel)
    captured: list[str] = []

    @dataclass
    class CaptureLLM:
        name: str = "capture"

        def call_structured(self, *, system: str, user: str, output_schema: type[T], **kw) -> T:
            captured.append(user)
            return PerspectiveAnalysis(  # type: ignore[return-value]
                perspectives=[
                    Perspective(label="a", core_claims=["c"], strongest_evidence=["e"],
                                key_concerns_about_other_views=["w"],
                                steelman_quality_self_assessment="ok"),
                    Perspective(label="b", core_claims=["c"], strongest_evidence=["e"],
                                key_concerns_about_other_views=["w"],
                                steelman_quality_self_assessment="ok"),
                ]
            )

    intake = IntakeAnalysis(
        canonical_query="Test?", modality="factual", user_stated_stance=None,
        multi_turn_dependency=False, notes="Test.",
    )
    evidence = _evidence(confidence=4, coverage=_coverage())
    suf = derive_evidence_sufficiency(_plan(needs_search=False), evidence, False)
    assert suf.has_constraints is False

    run_s5_perspectives(CaptureLLM(), intake, evidence, sufficiency=suf)  # type: ignore[arg-type]

    assert "Evidence sufficiency constraints" not in captured[0]


def test_sufficiency_note_in_s6_user_content() -> None:
    """Sufficiency note appears after weak-evidence line in S6."""
    from dataclasses import dataclass
    from typing import TypeVar

    from pydantic import BaseModel

    from revere_agent.agent.stages.s6_verification import run_s6_verification
    from revere_agent.schemas import FactualClaim, Perspective, PerspectiveAnalysis, VerificationReport

    T = TypeVar("T", bound=BaseModel)
    captured: list[str] = []

    @dataclass
    class CaptureLLM:
        name: str = "capture"

        def call_structured(self, *, system: str, user: str, output_schema: type[T], **kw) -> T:
            captured.append(user)
            return VerificationReport(  # type: ignore[return-value]
                claims=[FactualClaim(claim="x", confidence=3, verification_basis="uncertain",
                                     suggested_hedging="hedge", drop_if_uncorroborated=True)],
                overall_calibration_note="Test.",
            )

    persp = PerspectiveAnalysis(
        perspectives=[
            Perspective(label="a", core_claims=["c"], strongest_evidence=["e"],
                        key_concerns_about_other_views=["w"], steelman_quality_self_assessment="ok"),
        ]
    )
    evidence = _evidence(confidence=2)
    suf = derive_evidence_sufficiency(_plan(needs_search=True, target_types=["government"]),
                                       evidence, True)

    from revere_agent.schemas import IntakeAnalysis
    intake = IntakeAnalysis(canonical_query="Test?", modality="factual", user_stated_stance=None,
                             multi_turn_dependency=False, notes=".")

    run_s6_verification(CaptureLLM(), intake, evidence, persp, sufficiency=suf)  # type: ignore[arg-type]

    assert "Evidence sufficiency constraints" in captured[0]


# ── Integration: TurnResult carries sufficiency ───────────────────────────────


def test_turn_result_carries_evidence_sufficiency() -> None:
    """Orchestrator populates TurnResult.evidence_sufficiency after S4."""
    from dataclasses import dataclass, field as dc_field
    from typing import TypeVar

    from pydantic import BaseModel

    from revere_agent.agent import Orchestrator
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

    @dataclass
    class StubLLM:
        responses: dict[type[BaseModel], BaseModel]
        name: str = "stub"
        calls: list = dc_field(default_factory=list)

        def call_structured(self, *, system: str, user: str, output_schema: type[T], **kw) -> T:
            self.calls.append(output_schema)
            return self.responses[output_schema]  # type: ignore[return-value]

    llm = StubLLM(
        responses={
            IntakeAnalysis: IntakeAnalysis(canonical_query="Q?", modality="factual",
                                           user_stated_stance=None, multi_turn_dependency=False,
                                           notes="Test."),
            ScopeDecision: ScopeDecision(in_scope=True, confidence=5, reasoning="ok",
                                          matched_charter_categories=[], suggested_redirect=None,
                                          partial_help_possible=False),
            SearchPlan: SearchPlan(needs_search=False, rationale="ok", queries=[],
                                   target_source_types=[], why_model_knowledge_insufficient=None),
            EvidenceBase: EvidenceBase(assessments=[], confidence_in_evidence=2,
                                       conflicting_claims=[], gaps=["No sources."]),
            PerspectiveAnalysis: PerspectiveAnalysis(
                perspectives=[
                    Perspective(label="a", core_claims=["c"], strongest_evidence=["e"],
                                key_concerns_about_other_views=["w"], steelman_quality_self_assessment="ok"),
                    Perspective(label="b", core_claims=["c"], strongest_evidence=["e"],
                                key_concerns_about_other_views=["w"], steelman_quality_self_assessment="ok"),
                ]
            ),
            VerificationReport: VerificationReport(
                claims=[FactualClaim(claim="x", confidence=3, verification_basis="uncertain",
                                     suggested_hedging="h", drop_if_uncorroborated=False)],
                overall_calibration_note="ok.",
            ),
            FinalResponse: FinalResponse(
                response_text="Answer.",
                citations=[],
                neutrality_self_check=SelfCheckReport(
                    avoided_unsolicited_opinion=True, factually_accurate_and_comprehensive=True,
                    steelmanned_each_perspective=True, neutral_terminology_used=True,
                    equal_depth_across_perspectives=True, respectful_tone=True,
                    evidence_proportional_to_sources=True,
                ),
                residual_uncertainty="None.",
            ),
        }
    )

    orch = Orchestrator(llm_provider=llm, search_provider=None)  # type: ignore[arg-type]
    result = orch.run_turn("Test query?")

    assert result.evidence_sufficiency is not None
    assert isinstance(result.evidence_sufficiency, EvidenceSufficiency)
    # confidence=2 → restricted mode
    assert result.evidence_sufficiency.restricted_empirical_claims_required is True


# ── EvidenceCoverage schema ───────────────────────────────────────────────────


def test_evidence_coverage_roundtrips_via_pydantic() -> None:
    """EvidenceCoverage is a valid Pydantic model that serialises cleanly."""
    cov = EvidenceCoverage(
        has_primary_sources=True,
        has_court_sources=True,
        has_government_sources=False,
        perspective_coverage_asymmetric=False,
    )
    dumped = cov.model_dump()
    assert dumped["has_primary_sources"] is True
    assert dumped["has_court_sources"] is True
    assert dumped["has_government_sources"] is False
    assert dumped["perspective_coverage_asymmetric"] is False
    assert dumped["asymmetry_note"] is None


def test_evidence_base_coverage_field_defaults_to_none() -> None:
    """EvidenceBase.coverage is optional and defaults to None for backward compat."""
    eb = EvidenceBase(
        assessments=[],
        confidence_in_evidence=3,
        conflicting_claims=[],
        gaps=["No sources retrieved."],
    )
    assert eb.coverage is None


def test_evidence_base_accepts_coverage_when_provided() -> None:
    cov = _coverage(has_primary=True, has_court=True, asymmetric=False)
    eb = _evidence(confidence=4, coverage=cov)
    assert eb.coverage is not None
    assert eb.coverage.has_primary_sources is True
    assert eb.coverage.has_court_sources is True
