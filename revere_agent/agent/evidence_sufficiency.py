"""EvidenceSufficiency — deterministic post-S4 constraint summary.

Derived from S3 plan + S4 evidence + search execution stats.
No LLM call, no search call. Passed into S5/S6/S7 as a compact binding note
so they can apply evidence-proportional wording without re-reading the full
evidence base.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from revere_agent.schemas import EvidenceBase, SearchPlan, SourceAssessment

# Source types that qualify as "primary" for gap detection.
_PRIMARY_TYPES: frozenset[str] = frozenset({"primary", "government", "court"})

# Domains that identify a court source regardless of the source_type label S4
# assigned. Handles cases where S4 labels supremecourt.gov as "primary" rather
# than "court".
_COURT_DOMAINS: frozenset[str] = frozenset({
    "supremecourt.gov",
    "scotus.gov",
    "uscourts.gov",
})


def _source_type_aliases(assessment: "SourceAssessment") -> frozenset[str]:
    """Return all source-type roles this assessment satisfies.

    Conservative equivalence rules:
    - 'court' and 'government' are inherently primary records → both also
      satisfy a request for 'primary'.
    - A URL on a recognised court domain satisfies 'court' + 'primary'
      regardless of the source_type label (handles S4 labelling
      supremecourt.gov as 'primary' rather than 'court').
    - Any other .gov domain satisfies 'government' + 'primary'.
    - Mirror / aggregator sites (justia.com, law.cornell.edu) are NOT treated
      as court-equivalent; they satisfy only their assigned source_type.
    """
    aliases: set[str] = {assessment.source_type}

    # Type-based expansions: court and government records are primary by nature.
    if assessment.source_type in ("court", "government"):
        aliases.add("primary")

    # Domain-based expansions — catch mislabelled authority sources.
    try:
        netloc = urlparse(assessment.url).netloc.lower().removeprefix("www.")
    except Exception:  # noqa: BLE001
        netloc = ""

    if netloc:
        if any(netloc == d or netloc.endswith("." + d) for d in _COURT_DOMAINS):
            # Recognised federal court domain → satisfies court + primary.
            aliases.update({"court", "primary"})
        elif netloc.endswith(".gov"):
            # Any other .gov TLD → satisfies government + primary.
            aliases.update({"government", "primary"})

    return frozenset(aliases)

# Structural terms in S4 gap text that indicate asymmetric perspective coverage.
# These are structural descriptors S4 uses, not political topic keywords.
_ASYMMETRY_TERMS: tuple[str, ...] = (
    "one-sided",
    "one side",
    "asymmetric",
    "perspective-representative",
    "missing perspective",
    "underrepresented perspective",
    "coverage gap",
    "sources for one",
    "sources only for",
)


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
    """Derive an EvidenceSufficiency from S3 plan + S4 evidence. Zero LLM calls."""
    reasons: list[str] = []
    conf = evidence.confidence_in_evidence

    # Flag 1: restricted mode from low confidence
    restricted = conf <= 3
    if restricted:
        reasons.append(f"Evidence confidence {conf}/5 is low")

    # Flag 2: primary sources missing when search ran.
    # Uses alias expansion so a court/gov URL satisfies "primary" even if S4
    # labelled it with an adjacent type (e.g. supremecourt.gov as "primary").
    primary_missing = False
    if search_executed:
        primary_present = any(
            bool(_PRIMARY_TYPES & _source_type_aliases(a))
            for a in evidence.assessments
        )
        if not primary_present:
            primary_missing = True
            restricted = True
            reasons.append(
                "No primary/government/court sources retrieved despite search execution"
            )

    # Flag 3: requested source types (S3 target_source_types) not found in S4.
    # Uses alias expansion to avoid false positives from equivalent types:
    # - requested "primary", retrieved "court" → satisfied (court is primary)
    # - requested "primary", retrieved "government" → satisfied
    # - requested "court", domain is supremecourt.gov → satisfied regardless of label
    missing_types: list[str] = []
    for stype in plan.target_source_types:
        if stype in _PRIMARY_TYPES:
            satisfied = any(stype in _source_type_aliases(a) for a in evidence.assessments)
            if not satisfied:
                missing_types.append(stype)
    if missing_types:
        restricted = True
        reasons.append(
            f"S3 requested {', '.join(missing_types)} sources but none retrieved"
        )

    # Flag 4: asymmetric coverage from S4 gap text
    asymmetric = False
    gap_text_lower = " ".join(evidence.gaps).lower()
    if any(term in gap_text_lower for term in _ASYMMETRY_TERMS):
        asymmetric = True
        reasons.append("Evidence gaps indicate asymmetric perspective coverage")

    return EvidenceSufficiency(
        primary_sources_missing=primary_missing,
        requested_source_types_missing=missing_types,
        perspective_coverage_asymmetric=asymmetric,
        restricted_empirical_claims_required=restricted,
        confidence_in_evidence=conf,
        reasons=reasons,
    )
