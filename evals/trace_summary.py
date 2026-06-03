"""TraceSummary — compact view of an agent run's structured stage outputs.

Extracted from a CompletePayload (the SSE 'complete' event body) or a
fixture dict. All fields are optional so old fixtures and partial runs
degrade gracefully without raising KeyError or ValidationError.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TraceSummary:
    """Flat projection of stage-detail fields used by eval judges."""

    # S2 scope
    in_scope: bool | None = None
    scope_reasoning: str | None = None
    suggested_redirect: str | None = None
    matched_charter_categories: list[str] = field(default_factory=list)

    # S3 search plan
    needs_search: bool | None = None
    search_rationale: str | None = None
    target_source_types: list[str] = field(default_factory=list)

    # Search execution
    queries_run: int | None = None
    hits_passed: int | None = None

    # S4 source quality
    confidence_in_evidence: int | None = None
    source_gaps: list[str] = field(default_factory=list)
    conflicting_claims: list[str] = field(default_factory=list)
    source_domains: list[str] = field(default_factory=list)

    # S5 perspectives
    perspectives: list[dict[str, Any]] = field(default_factory=list)
    areas_of_consensus: list[str] = field(default_factory=list)
    areas_of_disagreement: list[str] = field(default_factory=list)
    empirical_vs_normative: list[dict[str, str]] = field(default_factory=list)

    # S6 verification
    factual_claims: list[dict[str, Any]] = field(default_factory=list)
    things_i_should_not_assert: list[str] = field(default_factory=list)
    overall_calibration_note: str | None = None

    # S7 compose check
    revisions_made: list[str] = field(default_factory=list)
    residual_uncertainty: str | None = None
    suggested_followups: list[str] = field(default_factory=list)

    # Final answer
    answer: str | None = None
    citations: list[dict[str, str]] = field(default_factory=list)

    @classmethod
    def from_complete_payload(cls, payload: dict[str, Any]) -> "TraceSummary":
        """Build a TraceSummary from a CompletePayload dict.

        Handles missing keys gracefully at every level — fixtures need not
        populate every field.
        """
        sd: dict[str, Any] = payload.get("stage_details") or {}

        s2 = sd.get("s2_scope") or {}
        s3 = sd.get("s3_plan_search") or {}
        se = sd.get("search_execution") or {}
        s4 = sd.get("s4_source_quality") or {}
        s5 = sd.get("s5_perspectives") or {}
        s6 = sd.get("s6_verification") or {}
        s7 = sd.get("s7_compose_check") or {}

        return cls(
            # S2
            in_scope=s2.get("in_scope"),
            scope_reasoning=s2.get("reasoning"),
            suggested_redirect=s2.get("suggested_redirect"),
            matched_charter_categories=s2.get("matched_charter_categories") or [],
            # S3
            needs_search=s3.get("needs_search"),
            search_rationale=s3.get("rationale"),
            target_source_types=s3.get("target_source_types") or [],
            # Search execution
            queries_run=se.get("queries_run"),
            hits_passed=se.get("hits_passed"),
            # S4
            confidence_in_evidence=s4.get("confidence_in_evidence"),
            source_gaps=s4.get("gaps") or [],
            conflicting_claims=s4.get("conflicting_claims") or [],
            source_domains=[
                src.get("domain", "") for src in (s4.get("sources") or [])
            ],
            # S5
            perspectives=s5.get("perspectives") or [],
            areas_of_consensus=s5.get("areas_of_consensus") or [],
            areas_of_disagreement=s5.get("areas_of_disagreement") or [],
            empirical_vs_normative=s5.get("empirical_vs_normative") or [],
            # S6
            factual_claims=s6.get("factual_claims") or [],
            things_i_should_not_assert=s6.get("things_i_should_not_assert") or [],
            overall_calibration_note=s6.get("overall_calibration_note"),
            # S7
            revisions_made=s7.get("revisions_made") or [],
            residual_uncertainty=s7.get("residual_uncertainty"),
            suggested_followups=s7.get("suggested_followups") or [],
            # Answer
            answer=payload.get("answer"),
            citations=payload.get("citations") or [],
        )
