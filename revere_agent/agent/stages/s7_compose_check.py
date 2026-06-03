"""Stage 7 — final composition plus neutrality self-check.

S7 is the only stage that writes user-facing prose, so it needs a richer
view of prior-stage outputs than S5 or S6 do. However, it does NOT need the
verbose prose-reasoning fields that S4/S5/S6 produced for their own use
(authority_reasoning, recency_assessment, slant_evidence, steelman_quality_
self_assessment). Those are trace artifacts; S7 acts on the structured
conclusions, not the reasoning paths.

The compact helpers below trim those artifacts and reduce S7's input from
~4,000–8,000 tokens (three full model_dump_json dumps) to ~500–900 tokens,
which meaningfully reduces TTFT on Sonnet while keeping all the information
S7 needs to compose a high-quality, evidence-proportional answer.
"""

from __future__ import annotations

from urllib.parse import urlparse

from revere_agent.agent.evidence_sufficiency import EvidenceSufficiency
from revere_agent.llm.provider import LLMProvider
from revere_agent.schemas import (
    EvidenceBase,
    FinalResponse,
    IntakeAnalysis,
    PerspectiveAnalysis,
    VerificationReport,
)

from ._common import run_llm_stage

# Maximum character length for free-text items in the compact packet.
# Keep long enough to be meaningful, short enough to stay compact.
_MAX_TEXT = 200


def _short(text: str, limit: int = _MAX_TEXT) -> str:
    """Truncate text to `limit` characters with an ellipsis marker."""
    return text if len(text) <= limit else f"{text[:limit].rstrip()}…"


def _domain(url: str) -> str:
    """Extract the netloc (domain) from a URL for compact display."""
    try:
        return urlparse(url).netloc or url
    except Exception:  # noqa: BLE001
        return url


def _compact_evidence_for_s7(evidence: EvidenceBase) -> str:
    """Compact S4 EvidenceBase for S7.

    S7 needs:
    - confidence_in_evidence (overall signal strength)
    - Each source's URL (to construct citations), source_type, relevance,
      confidence, and slant (for evidence-proportional framing)
    - conflicting_claims (for residual uncertainty framing)
    - gaps (for what to acknowledge as uncertain)

    S7 does NOT need:
    - authority_reasoning, recency_assessment, slant_evidence — these are
      verbose prose fields S4 wrote to explain its own judgments. S7 acts
      on the numeric scores and type labels, not the explanations.
    """
    lines: list[str] = [
        f"confidence_in_evidence: {evidence.confidence_in_evidence}/5",
        f"sources ({len(evidence.assessments)}):",
    ]

    if not evidence.assessments:
        lines.append("  (none — model knowledge only)")
    else:
        for i, a in enumerate(evidence.assessments, start=1):
            # Show slant only when it adds signal (not n/a or unclear).
            slant = a.likely_editorial_slant
            slant_str = f", {slant}" if slant not in ("n/a_primary", "unclear") else ""
            lines.append(
                f"  [{i}] {_domain(a.url)}"
                f" ({a.source_type}, {a.primary_vs_secondary}"
                f", rel {a.relevance_to_query}/5"
                f", conf {a.confidence_in_source}/5{slant_str})"
            )
            lines.append(f"      url: {a.url}")

    if evidence.conflicting_claims:
        lines.append("conflicting_claims:")
        for claim in evidence.conflicting_claims:
            lines.append(f"  - {_short(claim)}")
    else:
        lines.append("conflicting_claims: none")

    if evidence.gaps:
        lines.append("gaps:")
        for gap in evidence.gaps:
            lines.append(f"  - {_short(gap)}")
    else:
        lines.append("gaps: none")

    return "\n".join(lines)


def _compact_perspectives_for_s7(perspectives: PerspectiveAnalysis) -> str:
    """Compact S5 PerspectiveAnalysis for S7.

    S7 needs to steelman every perspective in its prose, so it gets all
    core_claims and strongest_evidence (not truncated). Evidence_coverage
    tells S7 when to use attribution-first wording. Unsupported_empirical_
    claims tells S7 exactly what NOT to assert as established fact.
    Representative_sources provide the URLs that back citations.

    Omitted: steelman_quality_self_assessment (S5's internal self-critique,
    not needed for composition). key_concerns_about_other_views is kept but
    capped at 2 items — S7 uses it to understand why each side contests the
    other, but full depth isn't needed.
    """
    lines: list[str] = [f"perspectives ({len(perspectives.perspectives)}):"]

    for i, p in enumerate(perspectives.perspectives, start=1):
        coverage = p.evidence_coverage or "unknown"
        lines.append(f"\nperspective {i}: [{p.label}]")
        lines.append(f"  evidence_coverage: {coverage}")

        lines.append("  core_claims:")
        for claim in p.core_claims:
            lines.append(f"    - {_short(claim)}")

        lines.append("  strongest_evidence:")
        for ev in p.strongest_evidence:
            lines.append(f"    - {_short(ev)}")

        # key_concerns help S7 understand the interpretive tension, but
        # two items capture the gist without bloating the packet.
        if p.key_concerns_about_other_views:
            lines.append("  key_concerns (up to 2):")
            for concern in p.key_concerns_about_other_views[:2]:
                lines.append(f"    - {_short(concern)}")

        # These are binding: S7 must NOT present them as established fact.
        if p.unsupported_empirical_claims:
            lines.append("  unsupported_empirical_claims (do NOT state as fact):")
            for uec in p.unsupported_empirical_claims:
                lines.append(f"    - {_short(uec)}")

        # Include URLs so S7 can construct citations pointing back to sources.
        if p.representative_sources:
            lines.append("  representative_sources:")
            for url in p.representative_sources[:3]:
                lines.append(f"    - {url}")

    if perspectives.areas_of_consensus:
        lines.append("\nareas_of_consensus:")
        for item in perspectives.areas_of_consensus:
            lines.append(f"  - {_short(item)}")

    if perspectives.areas_of_disagreement:
        lines.append("areas_of_disagreement:")
        for item in perspectives.areas_of_disagreement:
            kind = perspectives.empirical_vs_normative.get(item, "")
            kind_str = f" [{kind}]" if kind else ""
            lines.append(f"  - {_short(item)}{kind_str}")

    return "\n".join(lines)


def _compact_verification_for_s7(verification: VerificationReport) -> str:
    """Compact S6 VerificationReport for S7.

    Every field that affects how S7 phrases a claim is preserved:
    - overall_calibration_note: the one-sentence stance S7 should match
    - things_i_should_not_assert: prescriptive do-not-say rules
    - For each claim: text, confidence, basis, hedging, drop flag,
      claim_type, and attribution (when present)

    Omitted: support_level, outcome_relevance — internal S6 classification
    fields used during verification reasoning but not directly needed for
    deciding how to phrase or hedge a claim in the final answer.
    """
    lines: list[str] = [
        f"overall_calibration_note: {verification.overall_calibration_note}",
    ]

    if verification.things_i_should_not_assert:
        lines.append("do_not_assert:")
        for rule in verification.things_i_should_not_assert:
            lines.append(f"  - {rule}")

    lines.append(f"\nclaims ({len(verification.claims)}):")
    for c in verification.claims:
        # One-line claim header with all the metadata that drives phrasing.
        claim_type_str = f", {c.claim_type}" if c.claim_type else ""
        attr_str = f", attr: {c.attribution}" if c.attribution else ""
        drop_str = " → DROP IF UNCORROBORATED" if c.drop_if_uncorroborated else ""
        lines.append(
            f"  - [conf:{c.confidence}/5, {c.verification_basis}"
            f"{claim_type_str}{attr_str}]{drop_str}"
        )
        lines.append(f"    claim: {c.claim}")
        if c.suggested_hedging:
            lines.append(f"    hedge: {c.suggested_hedging}")

    return "\n".join(lines)


def run_s7_compose_check(
    provider: LLMProvider,
    intake: IntakeAnalysis,
    evidence: EvidenceBase,
    perspectives: PerspectiveAnalysis,
    verification: VerificationReport,
    *,
    sufficiency: EvidenceSufficiency | None = None,
) -> FinalResponse:
    """Compose user-facing answer with citation + self-check constraints.

    Prior-stage outputs are compacted before passing to the LLM. The compact
    helpers preserve everything S7 needs (URLs for citations, all claim hedging
    rules, full perspective material for steelmanning, gap acknowledgments)
    while dropping internal reasoning artifacts (verbose prose explanations
    that S4/S5/S6 wrote for their own reasoning steps, not for composition).
    """
    no_retrieved_sources = not evidence.assessments
    sufficiency_note = sufficiency.as_prompt_note() if sufficiency is not None else None

    compact_evidence = _compact_evidence_for_s7(evidence)
    compact_perspectives = _compact_perspectives_for_s7(perspectives)
    compact_verification = _compact_verification_for_s7(verification)

    user_content = (
        f"Canonical query:\n{intake.canonical_query}\n\n"
        f"No retrieved sources: {'YES' if no_retrieved_sources else 'NO'}\n\n"
        + (f"{sufficiency_note}\n\n" if sufficiency_note else "")
        + f"Evidence summary (S4):\n{compact_evidence}\n\n"
        f"Perspective analysis (S5):\n{compact_perspectives}\n\n"
        f"Verification report (S6):\n{compact_verification}\n\n"
        "Apply Stage 7 instructions and return a FinalResponse."
    )
    return run_llm_stage(
        provider=provider,
        stage_id="s7_compose_check",
        user_content=user_content,
        output_schema=FinalResponse,
        temperature=0.4,
    )
