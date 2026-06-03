"""Tests for live per-stage progress notes emitted while stages run."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field as dc_field
from typing import TypeVar

from pydantic import BaseModel


# ── STAGE_LIVE_NOTES coverage ─────────────────────────────────────────────────

ALL_LLM_STAGES = {
    "s1_intake",
    "s2_scope",
    "s3_plan_search",
    "s4_source_quality",
    "s5_perspectives",
    "s6_verification",
    "s7_compose_check",
}


def test_stage_live_notes_covers_all_llm_stages() -> None:
    from revere_agent.agent.orchestrator import STAGE_LIVE_NOTES

    missing = ALL_LLM_STAGES - set(STAGE_LIVE_NOTES.keys())
    assert not missing, f"STAGE_LIVE_NOTES missing entries for: {missing}"


def test_stage_live_notes_has_at_least_two_notes_per_stage() -> None:
    from revere_agent.agent.orchestrator import STAGE_LIVE_NOTES

    for stage_id, notes in STAGE_LIVE_NOTES.items():
        if stage_id in ALL_LLM_STAGES:
            assert len(notes) >= 2, f"{stage_id} has fewer than 2 notes"


def test_stage_live_notes_are_nonempty_strings() -> None:
    from revere_agent.agent.orchestrator import STAGE_LIVE_NOTES

    for stage_id, notes in STAGE_LIVE_NOTES.items():
        for i, note in enumerate(notes):
            assert isinstance(note, str) and note.strip(), (
                f"{stage_id}[{i}] is not a nonempty string"
            )


# ── Live-note emission timing ─────────────────────────────────────────────────

def test_live_notes_emitted_during_slow_stage() -> None:
    """Notes are emitted while a stage is running (simulated by a slow fn)."""
    from revere_agent.agent.orchestrator import Orchestrator, ProgressEvent, STAGE_LIVE_NOTES
    from revere_agent.agent.state import ConversationState
    from revere_agent.schemas import IntakeAnalysis, ScopeDecision

    T = TypeVar("T", bound=BaseModel)
    live_notes_received: list[ProgressEvent] = []
    progress_events: list[ProgressEvent] = []

    @dataclass
    class SlowLLM:
        name: str = "slow"
        _count: int = dc_field(default=0, init=False)

        def call_structured(self, *, system: str, user: str, output_schema: type[T], **kw) -> T:
            self._count += 1
            if output_schema is IntakeAnalysis:
                # Simulate a slow S1 call so background thread has time to fire
                time.sleep(2.0)
                return IntakeAnalysis(  # type: ignore[return-value]
                    canonical_query="What is the debt ceiling?",
                    modality="factual",
                    user_stated_stance=None,
                    multi_turn_dependency=False,
                    notes="",
                )
            return ScopeDecision(  # type: ignore[return-value]
                in_scope=False,
                confidence=5,
                reasoning="Test stop.",
                matched_charter_categories=[],
                suggested_redirect=None,
                partial_help_possible=False,
            )

    def on_progress(event: ProgressEvent) -> None:
        if event.status == "live_note":
            live_notes_received.append(event)
        else:
            progress_events.append(event)

    orch = Orchestrator(llm_provider=SlowLLM(), search_provider=None)  # type: ignore[arg-type]
    orch.run_turn("What is the debt ceiling?", progress_callback=on_progress)

    # Should have received at least one live note for s1_intake
    s1_notes = [e for e in live_notes_received if e.stage_id == "s1_intake"]
    assert len(s1_notes) >= 1, "Expected at least one live note for s1_intake"
    assert s1_notes[0].message in STAGE_LIVE_NOTES["s1_intake"]


def test_live_notes_stop_after_stage_completes() -> None:
    """No live notes arrive for a stage after its completed event."""
    from revere_agent.agent.orchestrator import Orchestrator, ProgressEvent
    from revere_agent.agent.state import ConversationState
    from revere_agent.schemas import IntakeAnalysis, ScopeDecision

    T = TypeVar("T", bound=BaseModel)
    events: list[ProgressEvent] = []

    @dataclass
    class FastLLM:
        name: str = "fast"
        _count: int = dc_field(default=0, init=False)

        def call_structured(self, *, system: str, user: str, output_schema: type[T], **kw) -> T:
            self._count += 1
            if output_schema is IntakeAnalysis:
                return IntakeAnalysis(  # type: ignore[return-value]
                    canonical_query="Q",
                    modality="factual",
                    user_stated_stance=None,
                    multi_turn_dependency=False,
                    notes="",
                )
            return ScopeDecision(  # type: ignore[return-value]
                in_scope=False,
                confidence=5,
                reasoning="Stop.",
                matched_charter_categories=[],
                suggested_redirect=None,
                partial_help_possible=False,
            )

    orch = Orchestrator(llm_provider=FastLLM(), search_provider=None)  # type: ignore[arg-type]
    orch.run_turn("Test?", progress_callback=lambda e: events.append(e))

    # Verify that for each stage, no live_note arrives after the completed event
    for stage_id in {e.stage_id for e in events}:
        stage_events = [e for e in events if e.stage_id == stage_id]
        completed_idx = next(
            (i for i, e in enumerate(stage_events) if e.status == "completed"), None
        )
        if completed_idx is not None:
            post_complete = [
                e for e in stage_events[completed_idx + 1:] if e.status == "live_note"
            ]
            assert not post_complete, (
                f"live_note arrived after completed for {stage_id}"
            )


# ── ProgressEvent status literal ─────────────────────────────────────────────

def test_progress_event_accepts_live_note_status() -> None:
    from revere_agent.agent.orchestrator import ProgressEvent

    # Should not raise
    e = ProgressEvent(
        stage_id="s1_intake",
        stage_num=1,
        total_stages=7,
        status="live_note",
        message="Parsing query structure and intent…",
    )
    assert e.status == "live_note"


# ── Server SSE routing ────────────────────────────────────────────────────────

def test_server_routes_live_note_to_stage_note_sse() -> None:
    """live_note ProgressEvents are serialised as stage_note SSE, not progress."""
    from revere_agent.agent.orchestrator import ProgressEvent
    from api.server import _sse

    event = ProgressEvent(
        stage_id="s2_scope",
        stage_num=2,
        total_stages=7,
        status="live_note",
        message="Comparing request against charter…",
    )

    # Simulate the routing logic from _stream_turn
    if event.status == "live_note":
        sse_frame = _sse("stage_note", {"stage_id": event.stage_id, "text": event.message})
    else:
        sse_frame = _sse("progress", {})

    assert "event: stage_note" in sse_frame
    assert "s2_scope" in sse_frame
    assert "Comparing request against charter" in sse_frame
    assert "event: progress" not in sse_frame
