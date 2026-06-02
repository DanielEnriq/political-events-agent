"""Lightweight tests for the FastAPI SSE backend."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

from api.server import (
    _build_micro_events,
    _build_stage_detail_from_output,
    _build_stage_details,
    _build_stage_summary,
    _serialize_progress,
    _trunc,
    app,
)
from revere_agent.agent.orchestrator import ProgressEvent


def test_app_title() -> None:
    assert app.title == "Revere API"


def test_health_route_registered() -> None:
    routes = {r.path for r in app.routes}  # type: ignore[attr-defined]
    assert "/health" in routes
    assert "/chat" in routes


def test_serialize_progress_completed() -> None:
    event = ProgressEvent(
        stage_id="s1_intake",
        stage_num=1,
        total_stages=7,
        status="completed",
        message="done",
        duration_ms=1500,
    )
    data = _serialize_progress(event)
    assert data["stage_id"] == "s1_intake"
    assert data["status"] == "completed"
    assert data["label"] == "Understanding request"
    assert data["duration_ms"] == 1500


def test_serialize_progress_unknown_stage() -> None:
    event = ProgressEvent(
        stage_id="unknown_stage",
        stage_num=None,
        total_stages=7,
        status="started",
        message="starting",
    )
    data = _serialize_progress(event)
    assert data["label"] == "unknown_stage"


def test_build_stage_details_empty_result() -> None:
    """_build_stage_details handles a minimal result with only required fields."""

    @dataclass
    class FakeScope:
        in_scope: bool = True
        confidence: int = 5
        reasoning: str = "Clearly political"
        matched_charter_categories: list = field(default_factory=list)
        suggested_redirect: Any = None

    @dataclass
    class FakeTurnResult:
        scope: FakeScope = field(default_factory=FakeScope)
        intake: Any = None
        search_plan: Any = None
        search_hits: list = field(default_factory=list)
        search_stats: Any = None
        evidence: Any = None
        perspectives: Any = None
        verification: Any = None
        final_response: Any = None

    result = FakeTurnResult()
    details = _build_stage_details(result)

    assert "s2_scope" in details
    assert details["s2_scope"]["in_scope"] is True
    assert details["s2_scope"]["confidence"] == 5
    assert "s1_intake" not in details
    assert "s3_plan_search" not in details
    assert "search_execution" not in details


def test_build_stage_details_with_search() -> None:
    """_build_stage_details extracts search execution stats correctly."""

    @dataclass
    class FakeStats:
        search_calls_made: int = 3
        raw_hits: int = 18
        unique_hits_after_dedup: int = 12
        hits_passed_to_s4: int = 6
        results_capped: bool = False

    @dataclass
    class FakeHit:
        url: str = "https://example.com/article"

    @dataclass
    class FakeTurnResult:
        scope: Any = None
        intake: Any = None
        search_plan: Any = None
        search_hits: list = field(default_factory=lambda: [FakeHit()])
        search_stats: FakeStats = field(default_factory=FakeStats)
        evidence: Any = None
        perspectives: Any = None
        verification: Any = None
        final_response: Any = None

    result = FakeTurnResult()
    details = _build_stage_details(result)

    assert "search_execution" in details
    d = details["search_execution"]
    assert d["queries_run"] == 3
    assert d["raw_hits"] == 18
    assert d["hits_passed"] == 6
    assert d["results_capped"] is False
    assert d["domains"] == ["example.com"]


def test_trunc_short_string() -> None:
    assert _trunc("hello", 10) == "hello"


def test_trunc_long_string() -> None:
    result = _trunc("a" * 20, 10)
    assert len(result) == 10
    assert result.endswith("…")


def test_trunc_none() -> None:
    assert _trunc(None, 50) == ""  # type: ignore[arg-type]


def test_build_stage_summary_s1() -> None:
    output = {"canonical_query": "debt ceiling 2023", "modality": "factual"}
    summary = _build_stage_summary("s1_intake", output, None)
    assert summary is not None
    assert "debt ceiling 2023" in summary
    assert "factual" in summary


def test_build_stage_summary_s2_in_scope() -> None:
    output = {
        "in_scope": True,
        "confidence": 5,
        "matched_charter_categories": ["legislation"],
    }
    summary = _build_stage_summary("s2_scope", output, None)
    assert summary is not None
    assert "In scope" in summary
    assert "5/5" in summary


def test_build_stage_summary_s2_out_of_scope() -> None:
    output = {"in_scope": False, "confidence": 5}
    summary = _build_stage_summary("s2_scope", output, None)
    assert summary is not None
    assert "Out of scope" in summary


def test_build_stage_summary_search_execution() -> None:
    extra = {"search_calls_made": 3, "hits_passed_to_s4": 6}
    summary = _build_stage_summary("search_execution", None, extra)
    assert summary is not None
    assert "6" in summary
    assert "3" in summary


def test_build_micro_events_s2_in_scope() -> None:
    output = {
        "in_scope": True,
        "confidence": 5,
        "matched_charter_categories": ["legislation", "policy debate"],
        "reasoning": "Clearly within the charter.",
    }
    events = _build_micro_events("s2_scope", output, None)
    assert len(events) >= 1
    # Should have "in scope" event
    texts = [e["text"] for e in events]
    assert any("in scope" in t.lower() for t in texts)
    # All events should have id, text, kind
    for ev in events:
        assert "id" in ev
        assert "text" in ev
        assert "kind" in ev
    # No event text exceeds 140 chars
    for ev in events:
        assert len(ev["text"]) <= 140


def test_build_micro_events_s3_with_queries() -> None:
    output = {
        "needs_search": True,
        "queries": ["debt ceiling 2023", "Fiscal Responsibility Act provisions"],
        "rationale": "Recent legislative event requires current sources.",
    }
    events = _build_micro_events("s3_plan_search", output, None)
    texts = [e["text"] for e in events]
    assert any("debt ceiling 2023" in t for t in texts)
    assert any("Fiscal Responsibility Act" in t for t in texts)


def test_build_micro_events_search_execution() -> None:
    extra = {"search_calls_made": 2, "raw_hits": 14, "unique_hits": 10, "hits_passed_to_s4": 6}
    events = _build_micro_events("search_execution", None, extra)
    assert len(events) == 2
    texts = [e["text"] for e in events]
    assert any("2" in t and "quer" in t for t in texts)
    assert any("6" in t for t in texts)


def test_build_stage_detail_from_output_s2() -> None:
    output = {
        "in_scope": True,
        "confidence": 4,
        "reasoning": "Clearly political.",
        "matched_charter_categories": ["elections"],
        "suggested_redirect": None,
    }
    detail = _build_stage_detail_from_output("s2_scope", output, None)
    assert detail is not None
    assert detail["in_scope"] is True
    assert detail["confidence"] == 4
    assert detail["matched_charter_categories"] == ["elections"]


def test_serialize_progress_includes_summary_on_completed() -> None:
    output = {"in_scope": True, "confidence": 5, "matched_charter_categories": []}
    event = ProgressEvent(
        stage_id="s2_scope",
        stage_num=2,
        total_stages=7,
        status="completed",
        message="done",
        output=output,
        duration_ms=800,
    )
    data = _serialize_progress(event)
    assert "summary" in data
    assert "In scope" in data["summary"]
    assert "micro_events" in data
    assert "detail" in data


def test_serialize_progress_no_summary_on_started() -> None:
    event = ProgressEvent(
        stage_id="s2_scope",
        stage_num=2,
        total_stages=7,
        status="started",
        message="starting",
    )
    data = _serialize_progress(event)
    assert "summary" not in data
    assert "micro_events" not in data
    assert "detail" not in data


def test_serialize_progress_all_known_stages() -> None:
    stage_ids = [
        "s1_intake",
        "s2_scope",
        "s3_plan_search",
        "search_execution",
        "s4_source_quality",
        "s5_perspectives",
        "s6_verification",
        "s7_compose_check",
    ]
    for sid in stage_ids:
        event = ProgressEvent(
            stage_id=sid,
            stage_num=1,
            total_stages=7,
            status="started",
            message="",
        )
        data = _serialize_progress(event)
        assert data["label"] != sid, f"Missing label for {sid}"
