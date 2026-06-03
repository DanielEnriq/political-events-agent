"""EvidenceSufficiency — deterministic post-S4 constraint summary.

Derived from S3 plan + S4 evidence + search execution stats.
No LLM call, no search call. Passed into S5/S6/S7 as a compact binding note
so they can apply evidence-proportional wording without re-reading the full
evidence base.

Design principle:
  Deterministic code performs bookkeeping only — it reads typed fields,
  compares enum values, and propagates structured booleans. All semantic
  judgments (does this source qualify as primary? is coverage asymmetric?)
  are made by S4 and emitted as structured EvidenceCoverage fields.

When evidence.coverage is None (legacy sessions or schema migration in flight),
a degraded fallback runs: Flag 1 unchanged, Flags 2–3 use simple source_type
comparison, Flag 4 is skipped. This fallback contains no domain heuristics or
gap-text keyword scanning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from revere_agent.schemas import EvidenceBase, SearchPlan

# Enum values that qualify as "primary-class" sources for the fallback path.
# Used only when evidence.coverage is None. No domain expansion — typed field
# comparison only.
_PRIMARY_TYPES: frozenset[str] = frozenset({"primary", "government", "court"})


@dataclass
class EvidenceSufficiency:
    """Compact evidence constraint object derived deterministically after S4."""

    primary_sources_missing: bool = False
    requested_source_types_missing: list[str] = field(default_factory=list)
    perspective_coverage_asymmetric: bool = False
    restricted_empirical_claims_required: bool = False
    confidence_in_evidence: int | None = None
    reasons: list[str] = field(default_factory=list)

    @property
    def has_constraints(self) -> bool:
        return (
            self.restricted_empirical_claims_required
            or self.primary_sources_missing
            or bool(self.requested_source_types_missing)
            or self.perspective_coverage_asymmetric
        )

    def as_prompt_note(self) -> str | None:
        """Return a compact multi-line string for inclusion in S5/S6/S7 user_content.

        Returns None when no constraints are active so clean queries add no tokens.
        """
        if not self.has_constraints:
            return None
        lines = ["Evidence sufficiency constraints (binding):"]
        if self.restricted_empirical_claims_required:
            conf = (
                f" (confidence {self.confidence_in_evidence}/5)"
                if self.confidence_in_evidence is not None
                else ""
            )
            lines.append(f"- Restricted empirical-claim mode: YES{conf}")
        if self.primary_sources_missing:
            lines.append(
                "- Primary/government/court sources: not retrieved despite search"
            )
        if self.requested_source_types_missing:
            types_str = ", ".join(self.requested_source_types_missing)
            lines.append(f"- Missing requested source types: {types_str}")
        if self.perspective_coverage_asymmetric:
            lines.append(
                "- Perspective coverage: asymmetric "
                "(one or more perspectives lack retrieved source support)"
            )
        if self.reasons:
            lines.append("- Context: " + "; ".join(self.reasons))
        lines.append(
            "- Downstream requirement: attribute or hedge empirical claims from "
            "underserved perspectives; do not present model-reconstructed allegations "
            "as verified facts."
        )
        return "\n".join(lines)


def derive_evidence_sufficiency(
    plan: "SearchPlan",
    evidence: "EvidenceBase",
    search_executed: bool,
) -> EvidenceSufficiency:
    """Derive an EvidenceSufficiency from S3 plan + S4 evidence. Zero LLM calls.

    When evidence.coverage is populated (the normal path), all semantic judgments
    are read directly from S4-emitted structured booleans. When coverage is None
    (legacy fallback), a simplified path runs with no domain heuristics.
    """
    reasons: list[str] = []
    conf = evidence.confidence_in_evidence
    cov = evidence.coverage

    # ── Flag 1: restricted mode from low confidence ───────────────────────────
    # Bookkeeping: numerical comparison on a typed int field.
    restricted = conf <= 3
    if restricted:
        reasons.append(f"Evidence confidence {conf}/5 is low")

    # ── Flag 2: primary sources missing when search ran ───────────────────────
    primary_missing = False
    if search_executed:
        if cov is not None:
            # Structured path: read S4's judgment directly.
            primary_present = cov.has_primary_sources
        else:
            # Fallback: compare source_type enum values; no domain expansion.
            primary_present = any(
                a.source_type in _PRIMARY_TYPES for a in evidence.assessments
            )
        if not primary_present:
            primary_missing = True
            restricted = True
            reasons.append(
                "No primary/government/court sources retrieved despite search execution"
            )

    # ── Flag 3: requested source types not satisfied ──────────────────────────
    # S3 names target source types; we check whether S4 found them.
    # Structured path reads S4's coverage booleans directly.
    # Fallback uses exact source_type enum comparison only.
    missing_types: list[str] = []
    if cov is not None:
        _coverage_by_type: dict[str, bool] = {
            "primary": cov.has_primary_sources,
            "government": cov.has_government_sources,
            "court": cov.has_court_sources,
        }
        for stype in plan.target_source_types:
            if stype in _coverage_by_type and not _coverage_by_type[stype]:
                missing_types.append(stype)
    else:
        # Fallback: exact type match, no equivalence expansion.
        retrieved_types = {a.source_type for a in evidence.assessments}
        for stype in plan.target_source_types:
            if stype in _PRIMARY_TYPES and stype not in retrieved_types:
                missing_types.append(stype)

    if missing_types:
        restricted = True
        reasons.append(
            f"S3 requested {', '.join(missing_types)} sources but none retrieved"
        )

    # ── Flag 4: asymmetric perspective coverage ───────────────────────────────
    # Structured path: read S4's judgment directly (no gap-text scanning).
    # Fallback: skip — cannot determine asymmetry without either structured field
    # or semantic text interpretation.
    asymmetric = False
    if cov is not None:
        asymmetric = cov.perspective_coverage_asymmetric
        if asymmetric:
            note = cov.asymmetry_note or "Evidence gaps indicate asymmetric perspective coverage"
            reasons.append(note)

    return EvidenceSufficiency(
        primary_sources_missing=primary_missing,
        requested_source_types_missing=missing_types,
        perspective_coverage_asymmetric=asymmetric,
        restricted_empirical_claims_required=restricted,
        confidence_in_evidence=conf,
        reasons=reasons,
    )
