"""Lightweight tests for the FastAPI SSE backend."""

from __future__ import annotations

from api.server import _serialize_progress, app
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
