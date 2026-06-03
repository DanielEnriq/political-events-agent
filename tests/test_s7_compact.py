"""Tests for the compact S7 input helpers in s7_compose_check.py.

Verifies three properties for each helper:
1. Verbose fields (authority_reasoning, recency_assessment, slant_evidence,
   steelman_quality_self_assessment) are NOT present in the compact output.
2. Fields S7 needs for composition ARE present (URLs, claim text, hedging
   instructions, evidence_coverage, unsupported empirical claims, gaps).
3. The compact output is substantially smaller than a full model_dump_json.
"""

from __future__ import annotations

from revere_agent.agent.stages.s7_compose_check import (
    _compact_evidence_for_s7,
    _compact_perspectives_for_s7,
    _compact_verification_for_s7,
)
from revere_agent.schemas import (
    EvidenceBase,
    FactualClaim,
    Perspective,
    PerspectiveAnalysis,
    SourceAssessment,
    VerificationReport,
)


# ── Fixtures ──────────────────────────────────────────────────────────


def _make_evidence_with_sources() -> EvidenceBase:
    return EvidenceBase(
        assessments=[
            SourceAssessment(
                url="https://www.fec.gov/introduction-campaign-finance/election-results-and-voting-information/",
                source_type="government",
                authority_reasoning=(
                    "The FEC is the primary federal authority on election finance "
                    "and provides official certified vote totals. Highly authoritative "
                    "for this query about 2020 election results."
                ),
                recency_assessment=(
                    "Published post-election 2020; directly covers the relevant "
                    "certification period and is current."
                ),
                likely_editorial_slant="n/a_primary",
                slant_evidence="Government primary source; no editorial slant applies.",
                primary_vs_secondary="primary",
                relevance_to_query=5,
                confidence_in_source=5,
            ),
            SourceAssessment(
                url="https://www.brennancenter.org/our-work/research-reports/election-officials-under-attack",
                source_type="think_tank",
                authority_reasoning=(
                    "Brennan Center is a well-regarded legal policy institute "
                    "specializing in voting rights and election law; relevant "
                    "but has a center-left orientation."
                ),
                recency_assessment="2021 report covering events shortly after the 2020 election cycle.",
                likely_editorial_slant="center_left",
                slant_evidence="Brennan Center is broadly categorized as center-left by media-bias monitors.",
                primary_vs_secondary="secondary",
                relevance_to_query=4,
                confidence_in_source=4,
            ),
        ],
        confidence_in_evidence=4,
        conflicting_claims=["Source A claims X; Source B claims Y on mail-in ballot security."],
        gaps=[
            "No primary court opinions retrieved despite search.",
            "No sources representing fraud-proponent perspective directly.",
        ],
    )


def _make_evidence_no_sources() -> EvidenceBase:
    return EvidenceBase(
        assessments=[],
        confidence_in_evidence=3,
        conflicting_claims=[],
        gaps=["Answer relies on model training knowledge; no sources retrieved."],
    )


def _make_perspectives() -> PerspectiveAnalysis:
    return PerspectiveAnalysis(
        perspectives=[
            Perspective(
                label="certified-result-accepted",
                core_claims=[
                    "Biden won 306 electoral votes certified by all 50 states.",
                    "Over 60 courts dismissed fraud lawsuits for lack of evidence.",
                    "CISA described it as the most secure election in American history.",
                ],
                strongest_evidence=[
                    "State-level certifications and Electoral College certification on Jan 7, 2021.",
                    "Court dismissals across federal and state jurisdictions.",
                ],
                key_concerns_about_other_views=[
                    "Fraud allegations were litigated and uniformly rejected.",
                    "Accepting unsubstantiated claims undermines democratic legitimacy.",
                ],
                representative_sources=[
                    "https://www.cisa.gov/sites/default/files/publications/CISA_Rumor_vs_Reality.pdf",
                ],
                steelman_quality_self_assessment=(
                    "A thoughtful proponent of the certified-result view would "
                    "likely recognize this framing as fair and accurate."
                ),
                evidence_coverage="sourced",
                unsupported_empirical_claims=[],
            ),
            Perspective(
                label="election-integrity-questioned",
                core_claims=[
                    "Proponents allege statistical anomalies in vote-count patterns.",
                    "Some argue rapid mail-in ballot expansion created verification gaps.",
                    "Claims of observer access restrictions are cited as procedural irregularities.",
                ],
                strongest_evidence=[
                    "Affidavit collections from poll watchers (this run did not retrieve direct validation).",
                    "State legislative hearings on election processes.",
                ],
                key_concerns_about_other_views=[
                    "Courts dismissed cases on procedural grounds rather than evaluating evidence on the merits.",
                    "Speed of certification prevented adequate review, some proponents argue.",
                ],
                representative_sources=[],
                steelman_quality_self_assessment=(
                    "This framing may underrepresent the most sophisticated legal arguments; "
                    "the perspective is mostly reconstructed from model prior knowledge."
                ),
                evidence_coverage="thin",
                unsupported_empirical_claims=[
                    "Specific statistical anomalies indicating coordinated fraud (not retrieved).",
                    "Widespread observer exclusions materially affecting outcomes (not retrieved).",
                ],
            ),
        ],
        areas_of_consensus=[
            "The election was held on November 3, 2020 and results were officially certified.",
        ],
        areas_of_disagreement=[
            "Whether mail-in voting created meaningful fraud risk.",
            "Whether courts evaluated fraud claims on the merits.",
        ],
        empirical_vs_normative={
            "Whether mail-in voting created meaningful fraud risk.": "empirical",
            "Whether courts evaluated fraud claims on the merits.": "mixed",
        },
    )


def _make_verification() -> VerificationReport:
    return VerificationReport(
        claims=[
            FactualClaim(
                claim="Biden won 306 electoral votes certified by all 50 states and Congress.",
                confidence=5,
                verification_basis="evidence_base",
                suggested_hedging=None,
                drop_if_uncorroborated=False,
                claim_type="verified_fact",
                support_level="directly_sourced",
                attribution=None,
                outcome_relevance="direct",
            ),
            FactualClaim(
                claim="Over 60 courts dismissed 2020 election fraud lawsuits.",
                confidence=5,
                verification_basis="evidence_base",
                suggested_hedging=None,
                drop_if_uncorroborated=False,
                claim_type="verified_fact",
                support_level="indirectly_sourced",
                attribution=None,
                outcome_relevance="indirect",
            ),
            FactualClaim(
                claim="Widespread coordinated voter fraud changed the 2020 presidential outcome.",
                confidence=1,
                verification_basis="uncertain",
                suggested_hedging=(
                    "Alleged by some proponents but rejected by courts and not "
                    "substantiated in retrieved sources."
                ),
                drop_if_uncorroborated=True,
                claim_type="reported_claim",
                support_level="unsupported",
                attribution="fraud-allegation proponents",
                outcome_relevance="direct",
            ),
        ],
        overall_calibration_note=(
            "Certified-outcome claims are strongly sourced; fraud-allegation "
            "specifics should be attributed as reported claims, not stated as fact."
        ),
        things_i_should_not_assert=[
            "Do not assert specific fraud evidence as established fact.",
            "Do not assert statistical anomaly claims as verified.",
        ],
    )


# ── Evidence compact tests ─────────────────────────────────────────────


def test_compact_evidence_excludes_verbose_reasoning_fields() -> None:
    """authority_reasoning, recency_assessment, slant_evidence must not appear."""
    evidence = _make_evidence_with_sources()
    compact = _compact_evidence_for_s7(evidence)

    assert "authority_reasoning" not in compact
    assert "recency_assessment" not in compact
    assert "slant_evidence" not in compact
    # Spot-check that the verbose text itself is gone too.
    assert "primary federal authority on election finance" not in compact
    assert "Published post-election 2020" not in compact


def test_compact_evidence_includes_urls_for_citations() -> None:
    """S7 constructs citations from URLs; they must be present."""
    evidence = _make_evidence_with_sources()
    compact = _compact_evidence_for_s7(evidence)

    assert "https://www.fec.gov" in compact
    assert "https://www.brennancenter.org" in compact


def test_compact_evidence_includes_key_metadata() -> None:
    """Source type, relevance, confidence, and overall confidence must appear."""
    evidence = _make_evidence_with_sources()
    compact = _compact_evidence_for_s7(evidence)

    assert "4/5" in compact            # confidence_in_evidence
    assert "government" in compact     # source_type of FEC
    assert "think_tank" in compact     # source_type of Brennan
    assert "rel 5/5" in compact        # relevance of FEC
    assert "conf 5/5" in compact       # confidence of FEC


def test_compact_evidence_includes_gaps() -> None:
    """Gaps tell S7 what to acknowledge as uncertain in the answer."""
    evidence = _make_evidence_with_sources()
    compact = _compact_evidence_for_s7(evidence)

    assert "No primary court opinions retrieved" in compact
    assert "fraud-proponent perspective" in compact


def test_compact_evidence_includes_conflicting_claims() -> None:
    """Conflicting claims inform S7's residual uncertainty framing."""
    evidence = _make_evidence_with_sources()
    compact = _compact_evidence_for_s7(evidence)

    assert "mail-in ballot security" in compact


def test_compact_evidence_no_sources_labels_model_only() -> None:
    """When assessments is empty, the compact output should note model knowledge."""
    evidence = _make_evidence_no_sources()
    compact = _compact_evidence_for_s7(evidence)

    assert "model knowledge only" in compact
    assert "none" in compact or "model knowledge" in compact


def test_compact_evidence_is_smaller_than_full_json() -> None:
    """The compact helper must produce substantially fewer characters than the raw dump."""
    evidence = _make_evidence_with_sources()
    full_json = evidence.model_dump_json(indent=2)
    compact = _compact_evidence_for_s7(evidence)

    assert len(compact) < len(full_json) * 0.5, (
        f"Expected compact ({len(compact)} chars) to be less than 50% "
        f"of full JSON ({len(full_json)} chars)"
    )


# ── Perspectives compact tests ─────────────────────────────────────────


def test_compact_perspectives_excludes_steelman_assessment() -> None:
    """steelman_quality_self_assessment is S5's internal self-critique; S7 doesn't need it."""
    perspectives = _make_perspectives()
    compact = _compact_perspectives_for_s7(perspectives)

    assert "steelman_quality_self_assessment" not in compact
    # The actual text of the self-assessment should not appear either.
    assert "thoughtful proponent of the certified-result view" not in compact
    assert "underrepresent the most sophisticated legal arguments" not in compact


def test_compact_perspectives_preserves_core_claims() -> None:
    """All core_claims must appear so S7 can steelman each side."""
    perspectives = _make_perspectives()
    compact = _compact_perspectives_for_s7(perspectives)

    assert "Biden won 306 electoral votes" in compact
    assert "mail-in ballot expansion" in compact


def test_compact_perspectives_preserves_evidence_coverage() -> None:
    """evidence_coverage tells S7 when to use attribution-first wording."""
    perspectives = _make_perspectives()
    compact = _compact_perspectives_for_s7(perspectives)

    assert "sourced" in compact   # first perspective coverage
    assert "thin" in compact      # second perspective coverage


def test_compact_perspectives_preserves_unsupported_empirical_claims() -> None:
    """unsupported_empirical_claims are binding: S7 must not state them as fact."""
    perspectives = _make_perspectives()
    compact = _compact_perspectives_for_s7(perspectives)

    assert "unsupported_empirical_claims" in compact or "do NOT state as fact" in compact
    assert "statistical anomalies" in compact
    assert "widespread observer exclusions" in compact.lower() or "Widespread observer" in compact


def test_compact_perspectives_preserves_representative_sources() -> None:
    """URLs from representative_sources are needed for citation matching."""
    perspectives = _make_perspectives()
    compact = _compact_perspectives_for_s7(perspectives)

    assert "https://www.cisa.gov" in compact


def test_compact_perspectives_preserves_consensus_and_disagreement() -> None:
    """areas_of_consensus and areas_of_disagreement structure S7's response."""
    perspectives = _make_perspectives()
    compact = _compact_perspectives_for_s7(perspectives)

    assert "November 3, 2020" in compact       # consensus
    assert "mail-in voting" in compact          # disagreement
    assert "empirical" in compact or "mixed" in compact  # dispute types


def test_compact_perspectives_is_smaller_than_full_json() -> None:
    """The compact helper must produce fewer characters than the raw dump."""
    perspectives = _make_perspectives()
    full_json = perspectives.model_dump_json(indent=2)
    compact = _compact_perspectives_for_s7(perspectives)

    assert len(compact) < len(full_json) * 0.7, (
        f"Expected compact ({len(compact)} chars) to be less than 70% "
        f"of full JSON ({len(full_json)} chars)"
    )


# ── Verification compact tests ────────────────────────────────────────


def test_compact_verification_excludes_internal_classification_fields() -> None:
    """support_level and outcome_relevance are S6 internals; S7 doesn't need them."""
    verification = _make_verification()
    compact = _compact_verification_for_s7(verification)

    assert "support_level" not in compact
    assert "outcome_relevance" not in compact
    assert "directly_sourced" not in compact
    assert "indirectly_sourced" not in compact


def test_compact_verification_preserves_do_not_assert_rules() -> None:
    """things_i_should_not_assert are prescriptive rules S7 must follow."""
    verification = _make_verification()
    compact = _compact_verification_for_s7(verification)

    assert "do_not_assert" in compact or "Do not assert" in compact
    assert "specific fraud evidence" in compact.lower() or "fraud evidence" in compact
    assert "statistical anomaly" in compact


def test_compact_verification_preserves_drop_flags() -> None:
    """drop_if_uncorroborated=True claims must be visibly flagged."""
    verification = _make_verification()
    compact = _compact_verification_for_s7(verification)

    assert "DROP IF UNCORROBORATED" in compact


def test_compact_verification_preserves_hedging_instructions() -> None:
    """suggested_hedging text must appear so S7 knows how to soften claims."""
    verification = _make_verification()
    compact = _compact_verification_for_s7(verification)

    assert "Alleged by some proponents" in compact or "alleged by some" in compact.lower()


def test_compact_verification_preserves_claim_text() -> None:
    """S7 needs the full claim text to know which statement to hedge or drop."""
    verification = _make_verification()
    compact = _compact_verification_for_s7(verification)

    assert "Biden won 306 electoral votes" in compact
    assert "Widespread coordinated voter fraud" in compact


def test_compact_verification_preserves_attribution() -> None:
    """attribution on reported_claims tells S7 who made the claim."""
    verification = _make_verification()
    compact = _compact_verification_for_s7(verification)

    assert "fraud-allegation proponents" in compact


def test_compact_verification_preserves_claim_type() -> None:
    """claim_type is present and meaningful for reported/disputed claims."""
    verification = _make_verification()
    compact = _compact_verification_for_s7(verification)

    assert "verified_fact" in compact
    assert "reported_claim" in compact


def test_compact_verification_preserves_calibration_note() -> None:
    """overall_calibration_note gives S7 the one-sentence epistemic stance."""
    verification = _make_verification()
    compact = _compact_verification_for_s7(verification)

    assert "Certified-outcome claims are strongly sourced" in compact


def test_compact_verification_is_smaller_than_full_json() -> None:
    """The compact helper must produce fewer characters than the raw dump."""
    verification = _make_verification()
    full_json = verification.model_dump_json(indent=2)
    compact = _compact_verification_for_s7(verification)

    assert len(compact) < len(full_json) * 0.75, (
        f"Expected compact ({len(compact)} chars) to be less than 75% "
        f"of full JSON ({len(full_json)} chars)"
    )
