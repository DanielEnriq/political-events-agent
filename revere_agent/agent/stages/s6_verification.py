"""Stage 6 — Verification / calibration pass.

This stage converts S4+S5 material into a concrete VerificationReport that S7
can apply when composing the user-facing answer.
"""

from __future__ import annotations

from revere_agent.llm.provider import LLMProvider
from revere_agent.schemas import (
    EvidenceBase,
    IntakeAnalysis,
    PerspectiveAnalysis,
    VerificationReport,
)

from ._common import run_llm_stage

_MAX_ITEMS = 6
_MAX_TEXT = 220


def _short(text: str, limit: int = _MAX_TEXT) -> str:
    return text if len(text) <= limit else f"{text[:limit].rstrip()}..."


def _compact_evidence(evidence: EvidenceBase) -> str:
    lines: list[str] = [
        f"confidence_in_evidence: {evidence.confidence_in_evidence}",
        f"assessment_count: {len(evidence.assessments)}",
    ]
    if evidence.assessments:
        lines.append("assessments:")
        for i, a in enumerate(evidence.assessments[:_MAX_ITEMS], start=1):
            lines.extend(
                [
                    f"- [{i}] {a.url}",
                    f"  type={a.source_type}; primacy={a.primary_vs_secondary}",
                    f"  relevance={a.relevance_to_query}; confidence={a.confidence_in_source}",
                ]
            )
    if evidence.conflicting_claims:
        lines.append("conflicting_claims:")
        for claim in evidence.conflicting_claims[:_MAX_ITEMS]:
            lines.append(f"- {_short(claim)}")
    if evidence.gaps:
        lines.append("gaps:")
        for gap in evidence.gaps[:_MAX_ITEMS]:
            lines.append(f"- {_short(gap)}")
    return "\n".join(lines)


def _compact_perspectives(perspectives: PerspectiveAnalysis) -> str:
    lines: list[str] = [f"perspective_count: {len(perspectives.perspectives)}"]
    for i, p in enumerate(perspectives.perspectives[:4], start=1):
        lines.extend(
            [
                f"- [{i}] {p.label}",
                "  core_claims:",
                *[f"    - {_short(c)}" for c in p.core_claims[:4]],
                "  strongest_evidence:",
                *[f"    - {_short(e)}" for e in p.strongest_evidence[:4]],
            ]
        )
    if perspectives.areas_of_disagreement:
        lines.append("areas_of_disagreement:")
        for d in perspectives.areas_of_disagreement[:_MAX_ITEMS]:
            lines.append(f"- {_short(d)}")
    return "\n".join(lines)


def run_s6_verification(
    provider: LLMProvider,
    intake: IntakeAnalysis,
    evidence: EvidenceBase,
    perspectives: PerspectiveAnalysis,
) -> VerificationReport:
    """Generate a concrete claim-level verification/calibration report."""
    weak_evidence = (not evidence.assessments) or (evidence.confidence_in_evidence <= 3)
    weak_evidence_note = (
        "YES: evidence is weak. Treat precise numbers/dates/provisions as high-risk."
        if weak_evidence
        else "NO: evidence has some grounding."
    )
    user_content = (
        f"Canonical query:\n{intake.canonical_query}\n\n"
        f"Weak evidence mode: {weak_evidence_note}\n\n"
        f"Evidence summary (S4):\n{_compact_evidence(evidence)}\n\n"
        f"Perspective summary (S5):\n{_compact_perspectives(perspectives)}\n\n"
        "Apply Stage 6 instructions and return a VerificationReport."
    )
    return run_llm_stage(
        provider=provider,
        stage_id="s6_verification",
        user_content=user_content,
        output_schema=VerificationReport,
    )
