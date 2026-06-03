"""FastAPI SSE backend — wraps Orchestrator.run_turn() for the Next.js UI."""

from __future__ import annotations

import json
import queue
import sys
import threading
from typing import Any, Literal
from urllib.parse import urlparse

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from revere_agent.agent.orchestrator import ProgressEvent
from revere_agent.agent.state import ConversationState
from revere_agent.cli.run import _maybe_search_provider
from revere_agent.llm import make_provider_from_env

app = FastAPI(title="Revere API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

_STAGE_LABELS: dict[str, str] = {
    "s1_intake": "Understanding request",
    "s2_scope": "Checking scope",
    "s3_plan_search": "Planning search",
    "search_execution": "Searching sources",
    "s4_source_quality": "Assessing evidence",
    "s5_perspectives": "Mapping perspectives",
    "s6_verification": "Verifying claims",
    "s7_compose_check": "Composing answer",
}


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str
    fast_mode: bool = False
    no_search: bool = False
    max_hits: int = 6
    history: list[HistoryMessage] = []


def _serialize_progress(event: ProgressEvent) -> dict[str, Any]:
    base: dict[str, Any] = {
        "stage_id": event.stage_id,
        "stage_num": event.stage_num,
        "total_stages": event.total_stages,
        "status": event.status,
        "label": _STAGE_LABELS.get(event.stage_id, event.stage_id),
        "duration_ms": event.duration_ms,
    }
    if event.status == "completed":
        output = event.output
        extra = event.extra
        summary = _build_stage_summary(event.stage_id, output, extra)
        micro_events = _build_micro_events(event.stage_id, output, extra)
        detail = _build_stage_detail_from_output(event.stage_id, output, extra)
        if summary:
            base["summary"] = summary
        if micro_events:
            base["micro_events"] = micro_events
        if detail:
            base["detail"] = detail
    return base


def _build_stage_details(result: Any) -> dict[str, Any]:
    """Extract compact per-stage output from TurnResult for Inspector rendering."""
    details: dict[str, Any] = {}

    # S1 — Intake
    intake = getattr(result, "intake", None)
    if intake:
        details["s1_intake"] = {
            "canonical_query": getattr(intake, "canonical_query", None),
            "modality": getattr(intake, "modality", None),
            "notes": getattr(intake, "notes", None),
        }

    # S2 — Scope
    scope = getattr(result, "scope", None)
    if scope:
        details["s2_scope"] = {
            "in_scope": getattr(scope, "in_scope", None),
            "confidence": getattr(scope, "confidence", None),
            "reasoning": getattr(scope, "reasoning", None),
            "matched_charter_categories": list(getattr(scope, "matched_charter_categories", None) or []),
            "suggested_redirect": getattr(scope, "suggested_redirect", None),
        }

    # S3 — Search Plan
    plan = getattr(result, "search_plan", None)
    if plan:
        details["s3_plan_search"] = {
            "needs_search": getattr(plan, "needs_search", None),
            "rationale": getattr(plan, "rationale", None),
            "queries": list(getattr(plan, "queries", None) or []),
            "target_source_types": list(getattr(plan, "target_source_types", None) or []),
            "why_model_knowledge_insufficient": getattr(plan, "why_model_knowledge_insufficient", None),
        }

    # Search Execution
    stats = getattr(result, "search_stats", None)
    hits = list(getattr(result, "search_hits", None) or [])
    if stats is not None or hits:
        details["search_execution"] = {
            "queries_run": getattr(stats, "search_calls_made", None),
            "raw_hits": getattr(stats, "raw_hits", None),
            "unique_hits": getattr(stats, "unique_hits_after_dedup", None),
            "hits_passed": getattr(stats, "hits_passed_to_s4", None),
            "results_capped": getattr(stats, "results_capped", None),
            "domains": [
                urlparse(getattr(h, "url", "")).netloc or getattr(h, "url", "")
                for h in hits[:8]
            ],
        }

    # S4 — Source Quality / Evidence
    evidence = getattr(result, "evidence", None)
    if evidence:
        assessments = list(getattr(evidence, "assessments", None) or [])
        suf = getattr(result, "evidence_sufficiency", None)
        cov = getattr(evidence, "coverage", None)
        details["s4_source_quality"] = {
            "confidence_in_evidence": getattr(evidence, "confidence_in_evidence", None),
            "gaps": list(getattr(evidence, "gaps", None) or []),
            "conflicting_claims": list(getattr(evidence, "conflicting_claims", None) or []),
            "sources": [
                {
                    "domain": urlparse(getattr(a, "url", "")).netloc or getattr(a, "url", ""),
                    "source_type": getattr(a, "source_type", None),
                    "slant": getattr(a, "likely_editorial_slant", None),
                    "relevance": getattr(a, "relevance_to_query", None),
                    "confidence": getattr(a, "confidence_in_source", None),
                }
                for a in assessments
            ],
            "coverage": {
                "has_primary_sources": getattr(cov, "has_primary_sources", None),
                "has_court_sources": getattr(cov, "has_court_sources", None),
                "has_government_sources": getattr(cov, "has_government_sources", None),
                "perspective_coverage_asymmetric": getattr(cov, "perspective_coverage_asymmetric", None),
                "asymmetry_note": getattr(cov, "asymmetry_note", None),
            } if cov is not None else None,
            "sufficiency": {
                "restricted_empirical_claims_required": getattr(suf, "restricted_empirical_claims_required", False),
                "primary_sources_missing": getattr(suf, "primary_sources_missing", False),
                "requested_source_types_missing": list(getattr(suf, "requested_source_types_missing", None) or []),
                "perspective_coverage_asymmetric": getattr(suf, "perspective_coverage_asymmetric", False),
                "confidence_in_evidence": getattr(suf, "confidence_in_evidence", None),
                "reasons": list(getattr(suf, "reasons", None) or []),
            } if suf is not None else None,
        }

    # S5 — Perspectives
    perspectives_obj = getattr(result, "perspectives", None)
    if perspectives_obj:
        persp_list = list(getattr(perspectives_obj, "perspectives", None) or [])
        emp_norm = getattr(perspectives_obj, "empirical_vs_normative", None) or {}
        details["s5_perspectives"] = {
            "perspectives": [
                {
                    "label": getattr(p, "label", None),
                    "core_claims": list(getattr(p, "core_claims", None) or []),
                    "strongest_evidence": list(getattr(p, "strongest_evidence", None) or []),
                    "concerns": list(getattr(p, "key_concerns_about_other_views", None) or []),
                    "evidence_coverage": getattr(p, "evidence_coverage", None),
                    "unsupported_empirical_claims": list(getattr(p, "unsupported_empirical_claims", None) or []),
                }
                for p in persp_list
            ],
            "areas_of_consensus": list(getattr(perspectives_obj, "areas_of_consensus", None) or []),
            "areas_of_disagreement": list(getattr(perspectives_obj, "areas_of_disagreement", None) or []),
            "empirical_vs_normative": [
                {"claim": k, "kind": str(v)} for k, v in emp_norm.items()
            ],
        }

    # S6 — Verification
    verification = getattr(result, "verification", None)
    if verification:
        claims = list(getattr(verification, "claims", None) or [])
        details["s6_verification"] = {
            "overall_calibration_note": getattr(verification, "overall_calibration_note", None),
            "things_i_should_not_assert": list(getattr(verification, "things_i_should_not_assert", None) or []),
            "factual_claims": [
                {
                    "claim": getattr(c, "claim", None),
                    "confidence": getattr(c, "confidence", None),
                    "verification_basis": getattr(c, "verification_basis", None),
                    "suggested_hedging": getattr(c, "suggested_hedging", None),
                    "drop_if_uncorroborated": getattr(c, "drop_if_uncorroborated", False),
                    "claim_type": getattr(c, "claim_type", None),
                    "support_level": getattr(c, "support_level", None),
                    "attribution": getattr(c, "attribution", None),
                    "outcome_relevance": getattr(c, "outcome_relevance", None),
                }
                for c in claims
            ],
        }

    # S7 — Compose & Self-check
    final = getattr(result, "final_response", None)
    if final:
        nsc = getattr(final, "neutrality_self_check", None)
        details["s7_compose_check"] = {
            "revisions_made": list(getattr(nsc, "revisions_made", None) or []) if nsc else [],
            "residual_uncertainty": getattr(final, "residual_uncertainty", None),
            "suggested_followups": list(getattr(final, "suggested_followups", None) or []),
        }

    return details


def _trunc(s: str | None, n: int) -> str:
    """Truncate string to n chars with ellipsis."""
    if not s:
        return ""
    s = s.strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _build_stage_summary(
    stage_id: str, output: dict[str, Any] | None, extra: dict[str, Any] | None
) -> str | None:
    """Return a one-line content-conditioned summary for a completed stage."""
    o = output or {}
    e = extra or {}

    if stage_id == "s1_intake":
        cq = o.get("canonical_query", "")
        modality = o.get("modality", "")
        if cq:
            return f'Normalized: "{_trunc(cq, 70)}". Modality: {modality}.'
        return None

    if stage_id == "s2_scope":
        in_scope = o.get("in_scope")
        confidence = o.get("confidence")
        cats = o.get("matched_charter_categories") or []
        conf_str = f" (confidence {confidence}/5)" if confidence is not None else ""
        if in_scope:
            cats_str = f" — {', '.join(cats[:2])}" if cats else ""
            return f"In scope{conf_str}{cats_str}."
        return f"Out of scope{conf_str}. Redirect prepared."

    if stage_id == "s3_plan_search":
        needs_search = o.get("needs_search")
        queries = o.get("queries") or []
        if needs_search:
            n = len(queries)
            return f"Planning {n} search quer{'y' if n == 1 else 'ies'}."
        return "No search needed — answering from model knowledge."

    if stage_id == "search_execution":
        calls = e.get("search_calls_made", 0)
        passed = e.get("hits_passed_to_s4", 0)
        return f"Collected {passed} source{'s' if passed != 1 else ''} from {calls} search{'es' if calls != 1 else ''}."

    if stage_id == "s4_source_quality":
        assessments = o.get("assessments") or []
        confidence = o.get("confidence_in_evidence")
        conf_str = f" Confidence: {confidence}/5." if confidence is not None else ""
        if not assessments:
            return f"Calibrating model-knowledge limitations.{conf_str}"
        return f"Assessed {len(assessments)} source{'s' if len(assessments) != 1 else ''}.{conf_str}"

    if stage_id == "s5_perspectives":
        perspectives = o.get("perspectives") or []
        consensus = o.get("areas_of_consensus") or []
        n = len(perspectives)
        c = len(consensus)
        cons_str = f" {c} area{'s' if c != 1 else ''} of consensus." if c else ""
        return f"Mapped {n} perspective{'s' if n != 1 else ''}.{cons_str}"

    if stage_id == "s6_verification":
        claims = o.get("claims") or []
        n = len(claims)
        return f"Verified {n} factual claim{'s' if n != 1 else ''}."

    if stage_id == "s7_compose_check":
        nsc = o.get("neutrality_self_check") or {}
        revisions = nsc.get("revisions_made") or []
        citations = o.get("citations") or []
        rev_str = f" {len(revisions)} revision{'s' if len(revisions) != 1 else ''} made." if revisions else ""
        return f"Drafted answer with {len(citations)} citation{'s' if len(citations) != 1 else ''}.{rev_str}"

    return None


def _build_micro_events(
    stage_id: str, output: dict[str, Any] | None, extra: dict[str, Any] | None
) -> list[dict[str, Any]]:
    """Return content-conditioned audit micro-events for a completed stage."""
    o = output or {}
    e = extra or {}
    events: list[dict[str, Any]] = []

    def add(text: str, kind: str = "summary") -> None:
        events.append({"id": f"{stage_id}_{len(events)}", "text": _trunc(text, 140), "kind": kind})

    if stage_id == "s1_intake":
        cq = o.get("canonical_query", "")
        modality = o.get("modality", "")
        notes = o.get("notes", "")
        if cq:
            add(f'Normalized to: "{_trunc(cq, 90)}"')
        if modality:
            add(f"Intent classified as {modality}.")
        if notes and notes.strip():
            add(f"Note: {_trunc(notes, 100)}", "warning")

    elif stage_id == "s2_scope":
        in_scope = o.get("in_scope")
        confidence = o.get("confidence")
        cats = o.get("matched_charter_categories") or []
        reasoning = o.get("reasoning", "")
        redirect = o.get("suggested_redirect", "")
        conf_str = f" (confidence {confidence}/5)" if confidence is not None else ""
        if in_scope:
            add(f"Classified in scope{conf_str}.")
            if cats:
                add(f"Categories: {', '.join(cats)}.")
            if reasoning:
                add("Requires balanced treatment across perspectives.")
        else:
            add(f"Classified out of scope{conf_str}.", "warning")
            if reasoning:
                add(_trunc(reasoning, 120), "warning")
            if redirect:
                add("Redirect to appropriate resources prepared.", "warning")

    elif stage_id == "s3_plan_search":
        needs_search = o.get("needs_search")
        queries = o.get("queries") or []
        rationale = o.get("rationale", "")
        if needs_search:
            for q in queries[:3]:
                add(f'Query: "{_trunc(q, 100)}"', "source")
        else:
            add("No search required — answering from model knowledge.")
        if rationale:
            add(_trunc(rationale, 120))

    elif stage_id == "search_execution":
        calls = e.get("search_calls_made", 0)
        raw = e.get("raw_hits", 0)
        unique = e.get("unique_hits", 0)
        passed = e.get("hits_passed_to_s4", 0)
        add(f"Ran {calls} search quer{'ies' if calls != 1 else 'y'}; found {raw} total results.", "source")
        add(f"{unique} unique results after deduplication; {passed} passed to evidence assessment.", "source")

    elif stage_id == "s4_source_quality":
        assessments = o.get("assessments") or []
        gaps = o.get("gaps") or []
        conflicting = o.get("conflicting_claims") or []
        if not assessments:
            add("No external retrieval used — answering from model knowledge.", "summary")
        for a in assessments[:5]:
            domain = urlparse(a.get("url", "")).netloc or a.get("url", "unknown")
            slant = a.get("likely_editorial_slant", "")
            src_type = a.get("source_type", "")
            conf = a.get("confidence_in_source")
            slant_str = f", {slant}" if slant and slant.lower() not in ("none", "neutral", "") else ""
            conf_str = f", conf {conf}/5" if conf is not None else ""
            add(f"Assessed {domain} ({src_type}{slant_str}{conf_str}).", "source")
        for gap in gaps[:2]:
            add(f"Evidence gap: {_trunc(gap, 100)}", "warning")
        if conflicting:
            add("Conflicting claims noted across sources.", "warning")

    elif stage_id == "s5_perspectives":
        perspectives = o.get("perspectives") or []
        consensus = o.get("areas_of_consensus") or []
        disagreement = o.get("areas_of_disagreement") or []
        for p in perspectives:
            label = p.get("label", "Unknown")
            core_claims = p.get("core_claims") or []
            first_claim = _trunc(core_claims[0], 70) if core_claims else ""
            claim_str = f" — {first_claim}" if first_claim else ""
            add(f"Perspective: {label}{claim_str}.", "perspective")
        for c in consensus[:1]:
            add(f"Consensus: {_trunc(c, 100)}")
        if disagreement:
            add("Separated factual consensus from normative disagreement.")

    elif stage_id == "s6_verification":
        claims = o.get("claims") or []
        things_not_assert = o.get("things_i_should_not_assert") or []
        note = o.get("overall_calibration_note", "")
        if note:
            add(_trunc(note, 120), "verification")
        for c in claims[:4]:
            conf = c.get("confidence")
            claim_text = c.get("claim", "")
            conf_str = f" (conf {conf}/5)" if conf is not None else ""
            add(f"Claim checked: {_trunc(claim_text, 75)}{conf_str}", "verification")
        for t in things_not_assert[:2]:
            add(f"Flagged as uncertain: {_trunc(t, 80)}", "warning")

    elif stage_id == "s7_compose_check":
        nsc = o.get("neutrality_self_check") or {}
        revisions = nsc.get("revisions_made") or []
        citations = o.get("citations") or []
        add(f"Drafted response with {len(citations)} citation{'s' if len(citations) != 1 else ''}.")
        check_keys = [
            "avoided_unsolicited_opinion",
            "factually_accurate_and_comprehensive",
            "steelmanned_each_perspective",
            "neutral_terminology_used",
            "equal_depth_across_perspectives",
            "respectful_tone",
            "evidence_proportional_to_sources",
        ]
        passed = sum(1 for k in check_keys if nsc.get(k, True))
        add(f"Neutrality self-check: {passed}/{len(check_keys)} criteria passed.", "neutrality")
        for r in revisions[:3]:
            add(f"Revised: {_trunc(r, 100)}", "neutrality")

    return events


def _build_stage_detail_from_output(
    stage_id: str, output: dict[str, Any] | None, extra: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Build compact inspector detail for a single stage from event output (streaming)."""
    o = output or {}
    e = extra or {}

    if stage_id == "s1_intake":
        if not o:
            return None
        return {
            "canonical_query": o.get("canonical_query"),
            "modality": o.get("modality"),
            "notes": o.get("notes"),
        }

    if stage_id == "s2_scope":
        if not o:
            return None
        return {
            "in_scope": o.get("in_scope"),
            "confidence": o.get("confidence"),
            "reasoning": o.get("reasoning"),
            "matched_charter_categories": o.get("matched_charter_categories") or [],
            "suggested_redirect": o.get("suggested_redirect"),
        }

    if stage_id == "s3_plan_search":
        if not o:
            return None
        return {
            "needs_search": o.get("needs_search"),
            "rationale": o.get("rationale"),
            "queries": o.get("queries") or [],
            "target_source_types": o.get("target_source_types") or [],
            "why_model_knowledge_insufficient": o.get("why_model_knowledge_insufficient"),
        }

    if stage_id == "search_execution":
        if not e:
            return None
        return {
            "queries_run": e.get("search_calls_made"),
            "raw_hits": e.get("raw_hits"),
            "unique_hits": e.get("unique_hits"),
            "hits_passed": e.get("hits_passed_to_s4"),
            "results_capped": None,
            "domains": [],
        }

    if stage_id == "s4_source_quality":
        if not o:
            return None
        assessments = o.get("assessments") or []
        cov = o.get("coverage")
        return {
            "confidence_in_evidence": o.get("confidence_in_evidence"),
            "gaps": o.get("gaps") or [],
            "conflicting_claims": o.get("conflicting_claims") or [],
            "sources": [
                {
                    "domain": urlparse(a.get("url", "")).netloc or a.get("url", ""),
                    "source_type": a.get("source_type"),
                    "slant": a.get("likely_editorial_slant"),
                    "relevance": a.get("relevance_to_query"),
                    "confidence": a.get("confidence_in_source"),
                }
                for a in assessments
            ],
            "coverage": {
                "has_primary_sources": cov.get("has_primary_sources"),
                "has_court_sources": cov.get("has_court_sources"),
                "has_government_sources": cov.get("has_government_sources"),
                "perspective_coverage_asymmetric": cov.get("perspective_coverage_asymmetric"),
                "asymmetry_note": cov.get("asymmetry_note"),
            } if cov else None,
        }

    if stage_id == "s5_perspectives":
        if not o:
            return None
        emp_norm = o.get("empirical_vs_normative") or {}
        return {
            "perspectives": [
                {
                    "label": p.get("label"),
                    "core_claims": p.get("core_claims") or [],
                    "strongest_evidence": p.get("strongest_evidence") or [],
                    "concerns": p.get("key_concerns_about_other_views") or [],
                    "evidence_coverage": p.get("evidence_coverage"),
                    "unsupported_empirical_claims": p.get("unsupported_empirical_claims") or [],
                }
                for p in (o.get("perspectives") or [])
            ],
            "areas_of_consensus": o.get("areas_of_consensus") or [],
            "areas_of_disagreement": o.get("areas_of_disagreement") or [],
            "empirical_vs_normative": [
                {"claim": k, "kind": str(v)} for k, v in emp_norm.items()
            ],
        }

    if stage_id == "s6_verification":
        if not o:
            return None
        return {
            "overall_calibration_note": o.get("overall_calibration_note"),
            "things_i_should_not_assert": o.get("things_i_should_not_assert") or [],
            "factual_claims": [
                {
                    "claim": c.get("claim"),
                    "confidence": c.get("confidence"),
                    "verification_basis": c.get("verification_basis"),
                    "suggested_hedging": c.get("suggested_hedging"),
                    "drop_if_uncorroborated": c.get("drop_if_uncorroborated", False),
                    "claim_type": c.get("claim_type"),
                    "support_level": c.get("support_level"),
                    "attribution": c.get("attribution"),
                    "outcome_relevance": c.get("outcome_relevance"),
                }
                for c in (o.get("claims") or [])
            ],
        }

    if stage_id == "s7_compose_check":
        if not o:
            return None
        nsc = o.get("neutrality_self_check") or {}
        return {
            "revisions_made": nsc.get("revisions_made") or [],
            "residual_uncertainty": o.get("residual_uncertainty"),
            "suggested_followups": o.get("suggested_followups") or [],
        }

    return None


def _sse(event_type: str, data: Any) -> str:
    payload = json.dumps(data) if not isinstance(data, str) else data
    return f"event: {event_type}\ndata: {payload}\n\n"


def _stream_turn(req: ChatRequest):
    load_dotenv()
    try:
        llm = make_provider_from_env()
    except RuntimeError as e:
        yield _sse("error", {"message": str(e)})
        return

    resolved_max_hits = req.max_hits if req.max_hits else (4 if req.fast_mode else 6)
    search = _maybe_search_provider(disabled=req.no_search)

    from revere_agent.agent import Orchestrator

    orch = Orchestrator(
        llm_provider=llm,
        search_provider=search,
        max_unique_hits=resolved_max_hits,
    )

    # Build ConversationState from bounded history sent by the frontend.
    state = ConversationState()
    for entry in req.history:
        state.record(entry.role, entry.content)

    event_q: queue.Queue[ProgressEvent | None] = queue.Queue()
    result_holder: dict[str, Any] = {}
    error_holder: dict[str, Exception] = {}

    def on_progress(event: ProgressEvent) -> None:
        event_q.put(event)

    def _worker() -> None:
        try:
            result_holder["result"] = orch.run_turn(
                req.message, state=state, progress_callback=on_progress
            )
        except Exception as e:  # noqa: BLE001
            error_holder["error"] = e
        finally:
            event_q.put(None)  # sentinel

    threading.Thread(target=_worker, daemon=True).start()

    yield _sse("start", {"message": req.message})

    while True:
        event = event_q.get()
        if event is None:
            break
        if event.status == "live_note":
            yield _sse("stage_note", {"stage_id": event.stage_id, "text": event.message})
        else:
            yield _sse("progress", _serialize_progress(event))

    if "error" in error_holder:
        err = error_holder["error"]
        yield _sse("error", {"message": f"{type(err).__name__}: {err}"})
        return

    result = result_holder["result"]
    scope = result.scope

    if not scope.in_scope:
        redirect = scope.suggested_redirect or "This is outside the agent's scope."
        yield _sse(
            "complete",
            {
                "in_scope": False,
                "answer": redirect,
                "citations": [],
                "neutrality": None,
                "residual_uncertainty": None,
                "suggested_followups": [],
                "stage_details": _build_stage_details(result),
            },
        )
        return

    final = result.final_response
    citations = []
    if final and final.citations:
        citations = [
            {"label": c.label, "url": c.url, "used_for_claim": c.used_for_claim}
            for c in final.citations
        ]

    neutrality = None
    if final and final.neutrality_self_check:
        nsc = final.neutrality_self_check
        neutrality = {
            "avoided_unsolicited_opinion": nsc.avoided_unsolicited_opinion,
            "factually_accurate_and_comprehensive": nsc.factually_accurate_and_comprehensive,
            "steelmanned_each_perspective": nsc.steelmanned_each_perspective,
            "neutral_terminology_used": nsc.neutral_terminology_used,
            "equal_depth_across_perspectives": nsc.equal_depth_across_perspectives,
            "respectful_tone": nsc.respectful_tone,
            "evidence_proportional_to_sources": nsc.evidence_proportional_to_sources,
            "revisions_made": nsc.revisions_made,
        }

    yield _sse(
        "complete",
        {
            "in_scope": True,
            "answer": final.response_text if final else "Pipeline completed without a final response.",
            "citations": citations,
            "neutrality": neutrality,
            "residual_uncertainty": final.residual_uncertainty if final else None,
            "suggested_followups": final.suggested_followups if final else [],
            "stage_details": _build_stage_details(result),
        },
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat")
def chat(req: ChatRequest) -> StreamingResponse:
    return StreamingResponse(
        _stream_turn(req),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def main() -> None:
    load_dotenv()
    uvicorn.run("api.server:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
