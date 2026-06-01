"""Lightweight tests for Gradio chat message formatting and live progress UI."""

from __future__ import annotations

from unittest.mock import MagicMock

from revere_agent.agent.orchestrator import ProgressEvent
from revere_agent.ui.gradio_app import (
    _active_stage_label,
    _append_chat_turn,
    _assistant_message,
    _set_last_assistant_content,
    consume_chat_turn,
)
from revere_agent.ui.trace_renderer import (
    compute_mode_label,
    format_progress_event,
    render_answer_support,
    render_stage_compact_summary,
    render_timeline_markdown,
)
from tests.test_trace_renderer import _out_of_scope_turn_result


def _is_messages_format(history: list[dict[str, str]]) -> bool:
    return all(
        isinstance(msg, dict) and msg.get("role") in {"user", "assistant"} and "content" in msg
        for msg in history
    )


def test_append_chat_turn_uses_messages_format() -> None:
    history = _append_chat_turn([], "What's the weather like today?")
    assert len(history) == 2
    assert history[0] == {"role": "user", "content": "What's the weather like today?"}
    assert history[1]["role"] == "assistant"
    assert history[1]["content"] == "Running pipeline…"


def test_set_last_assistant_content_preserves_messages_format() -> None:
    history = _append_chat_turn([], "Hello")
    updated = _set_last_assistant_content(history, "Hi there.")
    assert updated[-1] == {"role": "assistant", "content": "Hi there."}


def test_run_chat_turn_empty_message_returns_empty_history() -> None:
    history, *_rest = consume_chat_turn("", [], False, False, 6, False)
    assert history == []


def test_run_chat_turn_out_of_scope_returns_messages_format(monkeypatch) -> None:
    result = _out_of_scope_turn_result()
    mock_orch = MagicMock()
    mock_orch.run_turn.return_value = result
    monkeypatch.setattr(
        "revere_agent.ui.gradio_app._build_orchestrator",
        lambda **kwargs: (mock_orch, 6, "mock-llm", "(none)"),
    )

    history, support = consume_chat_turn(
        "What's the weather like today?",
        [],
        False,
        False,
        6,
        False,
    )

    assert _is_messages_format(history)
    assert history[0]["content"] == "What's the weather like today?"
    assert history[1]["content"] == _assistant_message(result)
    # The support panel must contain all key sections (never blank)
    assert "Sources" in support
    assert "Not applicable" in support  # trust panel: out-of-scope
    assert "Pipeline Timeline" in support
    assert "revere-card" in support


def test_format_progress_event_completed_s1() -> None:
    event = ProgressEvent(
        stage_id="s1_intake",
        stage_num=1,
        total_stages=7,
        status="completed",
        message="Stage 1/7 — Intake: normalizing request… — complete",
        output={
            "canonical_query": "2024 primary issues",
            "modality": "factual",
            "notes": "test",
            "multi_turn_dependency": False,
            "user_stated_stance": None,
        },
        duration_ms=1200,
    )
    html = format_progress_event(event)
    assert "revere-timeline-item is-complete" in html
    assert "2024 primary issues" in html
    assert "1,200 ms" in html


def test_render_stage_compact_summary_s2_out_of_scope() -> None:
    summary = render_stage_compact_summary(
        "s2_scope",
        {
            "in_scope": False,
            "confidence": 5,
            "matched_charter_categories": [],
            "reasoning": "Weather",
            "suggested_redirect": "Try weather.gov.",
            "partial_help_possible": False,
        },
    )
    assert "Out Of Scope" in summary
    assert "confidence 5/5" in summary


def test_render_timeline_markdown_running_state() -> None:
    md = render_timeline_markdown([], running=True)
    assert "Pipeline Timeline" in md
    assert "Pipeline running" in md


# ── _active_stage_label ───────────────────────────────────────────────────────


def test_active_stage_label_started_stage_returns_specific_label() -> None:
    events = [
        ProgressEvent(
            stage_id="s1_intake",
            stage_num=1,
            total_stages=7,
            status="started",
            message="Starting S1",
        ),
    ]
    label = _active_stage_label(events)
    assert label == "Understanding your question"


def test_active_stage_label_completed_stage_falls_back_to_completed() -> None:
    events = [
        ProgressEvent(
            stage_id="s3_plan_search",
            stage_num=3,
            total_stages=7,
            status="started",
            message="Starting S3",
        ),
        ProgressEvent(
            stage_id="s3_plan_search",
            stage_num=3,
            total_stages=7,
            status="completed",
            message="S3 done",
            duration_ms=900,
        ),
    ]
    label = _active_stage_label(events)
    assert label == "Planning research"


def test_active_stage_label_no_events_returns_fallback() -> None:
    label = _active_stage_label([])
    assert label == "Understanding your question"


# ── Panel structure consistency ───────────────────────────────────────────────


def test_run_chat_turn_support_panel_never_blank(monkeypatch) -> None:
    """Support panel must be non-empty after any completed run (single-output approach)."""
    result = _out_of_scope_turn_result()
    mock_orch = MagicMock()
    mock_orch.run_turn.return_value = result
    monkeypatch.setattr(
        "revere_agent.ui.gradio_app._build_orchestrator",
        lambda **kwargs: (mock_orch, 6, "mock-llm", "(none)"),
    )

    _history, support = consume_chat_turn(
        "What is the weather?",
        [],
        False,
        False,
        6,
        False,
    )

    assert support.strip()  # never blank
    assert "revere-card" in support
    assert "revere-mode-badge" in support


# ── compute_mode_label ────────────────────────────────────────────────────────


def test_compute_mode_label_full_audit() -> None:
    assert compute_mode_label(fast_mode=False, no_search=False) == "Full Audit"


def test_compute_mode_label_fast_audit() -> None:
    assert compute_mode_label(fast_mode=True, no_search=False) == "Fast Audit"


def test_compute_mode_label_no_search() -> None:
    assert compute_mode_label(fast_mode=False, no_search=True) == "No Search"


def test_compute_mode_label_fast_and_no_search() -> None:
    assert compute_mode_label(fast_mode=True, no_search=True) == "Fast Audit · No Search"


# ── render_answer_support ─────────────────────────────────────────────────────


def test_render_answer_support_empty_shows_mode_badge() -> None:
    html = render_answer_support("empty")
    assert "revere-mode-badge" in html
    assert "Full Audit" in html  # default options
    assert "Ask a question" in html


def test_render_answer_support_empty_fast_mode_label() -> None:
    from revere_agent.ui.trace_renderer import UIRunOptions
    html = render_answer_support("empty", options=UIRunOptions(fast_mode=True, no_search=False))
    assert "Fast Audit" in html


def test_render_answer_support_empty_no_search_label() -> None:
    from revere_agent.ui.trace_renderer import UIRunOptions
    html = render_answer_support("empty", options=UIRunOptions(fast_mode=False, no_search=True))
    assert "No Search" in html


def test_render_answer_support_running_has_timeline() -> None:
    events = [
        ProgressEvent(
            stage_id="s1_intake",
            stage_num=1,
            total_stages=7,
            status="started",
            message="S1 started",
        ),
    ]
    html = render_answer_support("running", events=events)
    assert "Pipeline Timeline" in html
    assert "In progress" in html


def test_render_answer_support_error_single_card_no_duplication() -> None:
    html = render_answer_support("error", error_message="Connection refused")
    assert "Error" in html
    assert "Connection refused" in html
    assert html.count("Connection refused") == 1  # not duplicated


def test_render_answer_support_completed_not_blank() -> None:
    result = _out_of_scope_turn_result()
    html = render_answer_support("completed", result=result)
    assert html.strip()
    assert "Pipeline Timeline" in html
    assert "Sources" in html
    assert "revere-card" in html
