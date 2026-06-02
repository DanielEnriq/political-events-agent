"""Tests for EvidenceSufficiency derivation and its integration with stage runners."""

from __future__ import annotations

from revere_agent.agent.evidence_sufficiency import (
    EvidenceSufficiency,
    derive_evidence_sufficiency,
)
from revere_agent.schemas import EvidenceBase, SearchPlan


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


def _evidence(
    confidence: int = 4,
    gaps: list[str] | None = None,
    source_types: list[str] | None = None,
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
    )


# ── Unit tests: derivation logic ──────────────────────────────────────────────


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
        evidence=_evidence(confidence=4),
        search_executed=False,
    )
    assert suf.restricted_empirical_claims_required is False
    assert suf.primary_sources_missing is False
    assert suf.requested_source_types_missing == []
    assert suf.perspective_coverage_asymmetric is False
    assert suf.has_constraints is False
    assert suf.as_prompt_note() is None


def test_primary_missing_when_search_executed_and_no_primary() -> None:
    suf = derive_evidence_sufficiency(
        plan=_plan(needs_search=True, target_types=["mainstream_news"]),
        evidence=_evidence(confidence=4, source_types=["mainstream_news"]),
        search_executed=True,
    )
    assert suf.primary_sources_missing is True
    assert suf.restricted_empirical_claims_required is True
    assert any("primary" in r.lower() for r in suf.reasons)


def test_no_primary_missing_when_search_not_executed() -> None:
    suf = derive_evidence_sufficiency(
        plan=_plan(needs_search=False),
        evidence=_evidence(confidence=4, source_types=[]),
        search_executed=False,
    )
    assert suf.primary_sources_missing is False


def test_primary_not_missing_when_government_retrieved() -> None:
    suf = derive_evidence_sufficiency(
        plan=_plan(needs_search=True, target_types=["government"]),
        evidence=_evidence(confidence=4, source_types=["government"]),
        search_executed=True,
    )
    assert suf.primary_sources_missing is False


def test_requested_source_types_missing() -> None:
    suf = derive_evidence_sufficiency(
        plan=_plan(needs_search=True, target_types=["government", "court", "mainstream_news"]),
        evidence=_evidence(confidence=4, source_types=["mainstream_news"]),
        search_executed=True,
    )
    assert "government" in suf.requested_source_types_missing
    assert "court" in suf.requested_source_types_missing
    assert "mainstream_news" not in suf.requested_source_types_missing
    assert suf.restricted_empirical_claims_required is True


def test_perspective_asymmetry_detected_from_gap_text() -> None:
    suf = derive_evidence_sufficiency(
        plan=_plan(needs_search=False),
        evidence=_evidence(
            confidence=4,
            gaps=["Coverage gap: no perspective-representative sources found."],
        ),
        search_executed=False,
    )
    assert suf.perspective_coverage_asymmetric is True
    assert suf.has_constraints is True


def test_asymmetry_detected_from_one_sided_gap() -> None:
    suf = derive_evidence_sufficiency(
        plan=_plan(needs_search=False),
        evidence=_evidence(
            confidence=4,
            gaps=["Sources are one-sided; only mainstream media retrieved."],
        ),
        search_executed=False,
    )
    assert suf.perspective_coverage_asymmetric is True


def test_no_asymmetry_on_unrelated_gaps() -> None:
    suf = derive_evidence_sufficiency(
        plan=_plan(needs_search=False),
        evidence=_evidence(
            confidence=4,
            gaps=["No data on exact vote counts."],
        ),
        search_executed=False,
    )
    assert suf.perspective_coverage_asymmetric is False


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
    evidence = _evidence(confidence=4)
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
