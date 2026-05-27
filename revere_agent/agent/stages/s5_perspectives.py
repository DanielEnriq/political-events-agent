"""Stage 5 — Multi-Perspective Synthesis.

The highest-leverage stage for evaluation. The prompt itself does the
heavy lifting (perspective symmetry, steelmanning, neutral labels,
empirical-vs-normative tagging). This module's only job is to assemble
the right inputs.
"""

from __future__ import annotations

from revere_agent.llm.provider import LLMProvider
from revere_agent.schemas import EvidenceBase, IntakeAnalysis, PerspectiveAnalysis

from ._common import run_llm_stage

_MAX_ITEMS = 5
_MAX_TEXT = 180


def _short(text: str, limit: int = _MAX_TEXT) -> str:
    return text if len(text) <= limit else f"{text[:limit].rstrip()}..."


def _compact_evidence_for_s5(evidence: EvidenceBase) -> str:
    """Provide S5 only the highest-value evidence signals to reduce token load."""
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
                    f"  type={a.source_type}; primacy={a.primary_vs_secondary}; slant={a.likely_editorial_slant}",
                    f"  relevance={a.relevance_to_query}; confidence={a.confidence_in_source}",
                    f"  authority={_short(a.authority_reasoning)}",
                    f"  recency={_short(a.recency_assessment)}",
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


def run_s5_perspectives(
    provider: LLMProvider,
    intake: IntakeAnalysis,
    evidence: EvidenceBase,
) -> PerspectiveAnalysis:
    """Produce a balanced, steelmanned multi-perspective analysis."""
    compact_evidence = _compact_evidence_for_s5(evidence)
    user_content = (
        f"Canonical query:\n{intake.canonical_query}\n\n"
        f"Intake notes (S1):\n{intake.notes}\n\n"
        f"Evidence summary (S4):\n{compact_evidence}\n\n"
        "Apply the Multi-Perspective Synthesis instructions above. "
        "Return a PerspectiveAnalysis. Symmetry checks are non-negotiable: "
        "before returning, verify equal core_claims count and roughly equal "
        "depth across perspectives, and revise if either fails."
    )
    return run_llm_stage(
        provider=provider,
        stage_id="s5_perspectives",
        user_content=user_content,
        output_schema=PerspectiveAnalysis,
    )
