"""FastAPI SSE backend — wraps Orchestrator.run_turn() for the Next.js UI."""

from __future__ import annotations

import json
import queue
import sys
import threading
from typing import Any

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from revere_agent.agent.orchestrator import ProgressEvent
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


class ChatRequest(BaseModel):
    message: str
    fast_mode: bool = False
    no_search: bool = False
    max_hits: int = 6


def _serialize_progress(event: ProgressEvent) -> dict[str, Any]:
    return {
        "stage_id": event.stage_id,
        "stage_num": event.stage_num,
        "total_stages": event.total_stages,
        "status": event.status,
        "label": _STAGE_LABELS.get(event.stage_id, event.stage_id),
        "duration_ms": event.duration_ms,
    }


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

    event_q: queue.Queue[ProgressEvent | None] = queue.Queue()
    result_holder: dict[str, Any] = {}
    error_holder: dict[str, Exception] = {}

    def on_progress(event: ProgressEvent) -> None:
        event_q.put(event)

    def _worker() -> None:
        try:
            result_holder["result"] = orch.run_turn(
                req.message, progress_callback=on_progress
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
