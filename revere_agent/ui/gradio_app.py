"""Gradio web UI — chat surface + auditable reasoning trace panel."""

from __future__ import annotations

import argparse
import sys
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import gradio as gr
from dotenv import load_dotenv

from revere_agent.agent.orchestrator import ProgressEvent
from revere_agent.cli.run import _maybe_search_provider
from revere_agent.llm import make_provider_from_env
from revere_agent.ui.trace_renderer import (
    UIRunOptions,
    render_answer_support,
)

APP_TITLE = "Revere — Political Events Agent"
APP_SUBTITLE = "Structured political reasoning with auditable source and neutrality trace."

_CHAT_PLACEHOLDER = (
    '<div class="revere-chat-placeholder">'
    "<p>Ask about US political events, candidates,<br>legislation, or court decisions.</p>"
    '<p class="revere-chat-placeholder-hint">Answer support will appear on the right.</p>'
    "</div>"
)

THEME_CSS = (Path(__file__).with_name("theme.css")).read_text(encoding="utf-8")

ChatMessage = dict[str, str]

PANEL_KWARGS = {"sanitize_html": False}

# Stage labels shown in the chat message during computation
_STAGE_CHAT_LABELS: dict[str, str] = {
    "s1_intake": "Understanding your question",
    "s2_scope": "Checking scope",
    "s3_plan_search": "Planning research",
    "search_execution": "Searching sources",
    "s4_source_quality": "Assessing evidence",
    "s5_perspectives": "Mapping perspectives",
    "s6_verification": "Verifying claims",
    "s7_compose_check": "Composing answer",
}

_DOT_CYCLE = ("", ".", "..", "...")


def _user_message(content: str) -> ChatMessage:
    return {"role": "user", "content": content}


def _assistant_message_dict(content: str) -> ChatMessage:
    return {"role": "assistant", "content": content}


def _append_chat_turn(
    history: list[ChatMessage],
    user_text: str,
    assistant_text: str = "Running pipeline…",
) -> list[ChatMessage]:
    """Append one user turn plus assistant placeholder in Gradio messages format."""
    return history + [_user_message(user_text), _assistant_message_dict(assistant_text)]


def _set_last_assistant_content(
    history: list[ChatMessage], content: str
) -> list[ChatMessage]:
    updated = list(history)
    updated[-1] = _assistant_message_dict(content)
    return updated


def _active_stage_label(events: list[ProgressEvent]) -> str:
    """Return the chat-friendly label for the most recently active stage."""
    active_id: str | None = None
    completed: set[str] = set()
    for e in events:
        if e.status == "completed":
            completed.add(e.stage_id)
        elif e.status == "started":
            active_id = e.stage_id
    # If the current active stage already completed, show the last completed stage
    if active_id in completed or active_id is None:
        for e in reversed(events):
            if e.status == "completed":
                return _STAGE_CHAT_LABELS.get(e.stage_id, "Processing")
        return "Understanding your question"
    return _STAGE_CHAT_LABELS.get(active_id, "Working")


def _assistant_message(result) -> str:
    if not result.scope.in_scope:
        redirect = result.scope.suggested_redirect or (
            "This request is outside the agent's scope for US political events."
        )
        return redirect
    if result.final_response is not None:
        return result.final_response.response_text
    return "Pipeline completed without a final response."




def _build_orchestrator(*, fast_mode: bool, no_search: bool, max_hits: int | None):
    resolved_max_hits = max_hits if max_hits is not None else (4 if fast_mode else 6)
    llm = make_provider_from_env()
    search = _maybe_search_provider(disabled=no_search)
    from revere_agent.agent import Orchestrator

    orch = Orchestrator(
        llm_provider=llm,
        search_provider=search,
        max_unique_hits=resolved_max_hits,
    )
    return orch, resolved_max_hits, llm.name, search.name if search else "(none)"


def run_chat_turn(
    message: str,
    history: list[ChatMessage],
    fast_mode: bool,
    no_search: bool,
    max_hits: int,
    show_raw_json: bool,
) -> Iterator[tuple[list[ChatMessage], str]]:
    """Run one pipeline turn; yield (history, answer_support_html) on each update.

    Note: token-level streaming is not implemented — it requires provider-level
    streaming support. Progress updates are stage-level only (every 250 ms).
    """
    message = (message or "").strip()
    history = list(history or [])
    options = UIRunOptions(fast_mode=fast_mode, no_search=no_search, max_hits=int(max_hits))

    if not message:
        yield (history, render_answer_support("empty", options=options))
        return

    history = _append_chat_turn(history, message, "Understanding your question")

    try:
        orch, resolved_max_hits, _llm_name, _search_name = _build_orchestrator(
            fast_mode=fast_mode,
            no_search=no_search,
            max_hits=int(max_hits),
        )
    except RuntimeError as e:
        err = f"Setup error: {e}"
        history = _set_last_assistant_content(history, err)
        yield (history, render_answer_support("error", options=options, error_message=err))
        return

    options = UIRunOptions(
        fast_mode=fast_mode,
        no_search=no_search,
        max_hits=resolved_max_hits,
    )

    events: list[ProgressEvent] = []
    done = threading.Event()
    result_holder: dict[str, Any] = {}
    error_holder: dict[str, Exception] = {}

    def on_progress(event: ProgressEvent) -> None:
        events.append(event)

    def _worker() -> None:
        try:
            result_holder["result"] = orch.run_turn(message, progress_callback=on_progress)
        except Exception as e:  # noqa: BLE001
            error_holder["error"] = e
        finally:
            done.set()

    threading.Thread(target=_worker, daemon=True).start()

    # Initial running yield — snapshot events (empty at this point).
    events_snap = list(events)
    yield (
        _set_last_assistant_content(history, "Understanding your question"),
        render_answer_support("running", options=options, events=events_snap),
    )

    # Poll every 250 ms so the chat dot-animation stays alive.
    # Only re-render the right panel when a new progress event arrives;
    # otherwise yield gr.skip() to avoid flooding gr.Markdown with hundreds
    # of identical large-HTML updates that build a browser-side SSE backlog.
    _dot_idx = 0
    _last_event_count = len(events_snap)
    while not done.wait(0.25):
        _dot_idx += 1
        dot = _DOT_CYCLE[_dot_idx % 4]
        events_snap = list(events)                  # thread-safe snapshot per tick
        label = _active_stage_label(events_snap)
        live_history = _set_last_assistant_content(history, label + dot)
        new_count = len(events_snap)
        if new_count != _last_event_count:          # new stage event — update right panel
            _last_event_count = new_count
            support = render_answer_support("running", options=options, events=events_snap)
        else:
            support = gr.skip()                     # no new events — hold right panel
        yield (live_history, support)

    if "error" in error_holder:
        err = (
            f"Pipeline error: {type(error_holder['error']).__name__}: "
            f"{error_holder['error']}"
        )
        history = _set_last_assistant_content(history, err)
        events_snap = list(events)
        yield (history, render_answer_support("error", options=options, error_message=err))
        return

    # Final completed yield — always a full render, never gr.skip().
    events_snap = list(events)
    result = result_holder["result"]
    answer = _assistant_message(result)
    history = _set_last_assistant_content(history, answer)
    yield (
        history,
        render_answer_support(
            "completed",
            options=options,
            events=events_snap,
            result=result,
            include_raw_trace=show_raw_json,
        ),
    )


def consume_chat_turn(*args, **kwargs):
    """Return the final yield from the streaming submit handler (for tests)."""
    last: tuple | None = None
    for last in run_chat_turn(*args, **kwargs):
        pass
    assert last is not None
    return last


def build_demo() -> gr.Blocks:
    with gr.Blocks(title=APP_TITLE) as demo:

        # ── Compact header ────────────────────────────────────
        gr.Markdown(
            f'<div class="revere-header">'
            f"<h1>{APP_TITLE}</h1>"
            f'<p class="revere-subtitle">{APP_SUBTITLE}</p>'
            f"</div>",
            **PANEL_KWARGS,
        )

        # ── Main two-column layout ────────────────────────────
        with gr.Row(elem_id="revere-main-row"):

            # Left: conversation + composer
            with gr.Column(scale=6, elem_id="revere-left-col"):
                chatbot = gr.Chatbot(
                    height="calc(100vh - 370px)",
                    min_height=200,
                    value=[],
                    elem_id="revere-chatbot",
                    show_label=False,
                    placeholder=_CHAT_PLACEHOLDER,
                )
                # Composer card: textarea + toolbar (controls + actions) in one visual unit
                with gr.Group(elem_id="revere-composer"):
                    user_input = gr.Textbox(
                        placeholder="Ask about US political events, candidates, legislation…",
                        lines=1,
                        max_lines=6,
                        show_label=False,
                        elem_id="revere-input",
                        container=False,
                    )
                    with gr.Row(elem_id="revere-toolbar"):
                        fast_mode = gr.Checkbox(
                            label="Fast audit",
                            value=False,
                            interactive=True,
                            container=False,
                        )
                        no_search = gr.Checkbox(
                            label="Skip search",
                            value=False,
                            interactive=True,
                            container=False,
                        )
                        show_raw_json = gr.Checkbox(
                            label="Raw trace",
                            value=False,
                            interactive=True,
                            container=False,
                        )
                        max_hits = gr.Dropdown(
                            choices=[3, 4, 6, 8, 10],
                            value=6,
                            label="Sources",
                            scale=0,
                            min_width=90,
                            interactive=True,
                        )
                        clear_btn = gr.Button("Clear", scale=0, min_width=65)
                        submit_btn = gr.Button("Send", variant="primary", scale=0, min_width=90)

            # Right: single unified answer-support panel
            with gr.Column(scale=4, elem_id="revere-right-col"):
                gr.Markdown(
                    '<div class="revere-audit-header">Answer Support</div>',
                    **PANEL_KWARGS,
                )
                answer_support_box = gr.Markdown(
                    value=render_answer_support("empty"),
                    **PANEL_KWARGS,
                )

        inputs = [user_input, chatbot, fast_mode, no_search, max_hits, show_raw_json]
        outputs = [chatbot, answer_support_box]

        submit_btn.click(
            fn=run_chat_turn,
            inputs=inputs,
            outputs=outputs,
            show_progress="hidden",
        ).then(lambda: "", outputs=[user_input])

        user_input.submit(
            fn=run_chat_turn,
            inputs=inputs,
            outputs=outputs,
            show_progress="hidden",
        ).then(lambda: "", outputs=[user_input])

        clear_btn.click(
            lambda: ([], render_answer_support("empty")),
            outputs=outputs,
        )

        demo.queue()
    return demo


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="revere-ui", description="Launch Gradio UI.")
    parser.add_argument(
        "--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port", type=int, default=7860, help="Bind port (default: 7860)"
    )
    parser.add_argument(
        "--share",
        action="store_true",
        help="Create a public Gradio share link.",
    )
    args = parser.parse_args(argv)

    load_dotenv()
    try:
        make_provider_from_env()
    except RuntimeError as e:
        print(f"[setup error] {e}", file=sys.stderr)
        print("Set ANTHROPIC_API_KEY in your environment or .env file.", file=sys.stderr)
        return 2

    demo = build_demo()
    demo.launch(
        server_name=args.host,
        server_port=args.port,
        share=args.share,
        css=THEME_CSS,
        theme=gr.themes.Base(
            primary_hue=gr.themes.colors.neutral,
            secondary_hue=gr.themes.colors.neutral,
            neutral_hue=gr.themes.colors.neutral,
        ).set(
            body_background_fill="#0a0a0a",
            body_background_fill_dark="#0a0a0a",
            block_background_fill="#141414",
            block_background_fill_dark="#141414",
            block_border_color="#2a2a2a",
            block_border_color_dark="#2a2a2a",
            body_text_color="#f5f0e8",
            body_text_color_dark="#f5f0e8",
            block_label_text_color="#a8a29e",
            block_label_text_color_dark="#a8a29e",
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
