"""Tests for multi-turn context: history wiring from API → orchestrator → S1."""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import TypeVar

from pydantic import BaseModel


# ── S1 unit tests ─────────────────────────────────────────────────────────────


def test_s1_format_history_none() -> None:
    from revere_agent.agent.stages.s1_intake import _format_history

    result = _format_history(None)
    assert "none" in result.lower() or "first turn" in result.lower()


def test_s1_format_history_empty_list() -> None:
    from revere_agent.agent.stages.s1_intake import _format_history

    result = _format_history([])
    assert "none" in result.lower() or "first turn" in result.lower()


def test_s1_format_history_multiple_turns() -> None:
    from revere_agent.agent.stages.s1_intake import _format_history

    history = [
        ("user", "Tell me about the debt ceiling."),
        ("assistant", "The 2023 debt ceiling crisis..."),
    ]
    result = _format_history(history)
    assert "USER:" in result
    assert "ASSISTANT:" in result
    assert "debt ceiling" in result


def test_s1_user_prompt_includes_history() -> None:
    """run_s1_intake injects history into the user content sent to the LLM."""
    from revere_agent.schemas import IntakeAnalysis

    T = TypeVar("T", bound=BaseModel)
    captured: list[str] = []

    @dataclass
    class CaptureLLM:
        name: str = "capture"

        def call_structured(self, *, system: str, user: str, output_schema: type[T], **kw) -> T:
            captured.append(user)
            return IntakeAnalysis(  # type: ignore[return-value]
                canonical_query="What part of Grutter v. Bollinger did Students for Fair Admissions v. Harvard/UNC (2023) overturn?",
                modality="factual",
                user_stated_stance=None,
                multi_turn_dependency=True,
                notes="Resolved 'this decision' to Students for Fair Admissions v. Harvard/UNC from previous turn.",
            )

    from revere_agent.agent.stages.s1_intake import run_s1_intake

    history = [
        ("user", "Explain the Supreme Court decision on affirmative action in college admissions."),
        ("assistant", "The court ruled in Students for Fair Admissions v. Harvard/UNC (2023) that race-conscious admissions programs at Harvard and UNC violated the Equal Protection Clause."),
    ]
    run_s1_intake(CaptureLLM(), "What was the precedent from Grutter v. Bollinger that this decision overturned?", history=history)  # type: ignore[arg-type]

    assert len(captured) == 1
    user_prompt = captured[0]
    assert "Recent conversation history" in user_prompt
    assert "Students for Fair Admissions" in user_prompt
    assert "this decision" in user_prompt or "Grutter" in user_prompt


# ── API request model tests ───────────────────────────────────────────────────


def test_chat_request_accepts_history() -> None:
    from api.server import ChatRequest

    req = ChatRequest(
        message="Follow-up question?",
        history=[
            {"role": "user", "content": "Prior user message"},
            {"role": "assistant", "content": "Prior assistant answer"},
        ],
    )
    assert len(req.history) == 2
    assert req.history[0].role == "user"
    assert req.history[1].role == "assistant"
    assert req.history[0].content == "Prior user message"


def test_chat_request_history_defaults_empty() -> None:
    from api.server import ChatRequest

    req = ChatRequest(message="Hello?")
    assert req.history == []


def test_chat_request_rejects_invalid_role() -> None:
    """history entries with invalid roles are rejected by Pydantic."""
    import pytest
    from pydantic import ValidationError
    from api.server import ChatRequest

    with pytest.raises(ValidationError):
        ChatRequest(
            message="Test",
            history=[{"role": "system", "content": "injected"}],
        )


# ── Orchestrator + ConversationState integration ──────────────────────────────


def test_orchestrator_passes_history_to_s1() -> None:
    """Orchestrator threads ConversationState.history into the S1 LLM call."""
    from revere_agent.agent import Orchestrator
    from revere_agent.agent.state import ConversationState
    from revere_agent.schemas import (
        IntakeAnalysis,
        ScopeDecision,
    )

    T = TypeVar("T", bound=BaseModel)
    s1_user_prompts: list[str] = []

    @dataclass
    class CaptureLLM:
        name: str = "capture"
        _count: int = dc_field(default=0, init=False)

        def call_structured(self, *, system: str, user: str, output_schema: type[T], **kw) -> T:
            self._count += 1
            if output_schema is IntakeAnalysis:
                s1_user_prompts.append(user)
                return IntakeAnalysis(  # type: ignore[return-value]
                    canonical_query="Q?",
                    modality="factual",
                    user_stated_stance=None,
                    multi_turn_dependency=True,
                    notes=".",
                )
            # S2 — return out-of-scope to stop the pipeline cheaply
            return ScopeDecision(  # type: ignore[return-value]
                in_scope=False,
                confidence=5,
                reasoning="Test stop.",
                matched_charter_categories=[],
                suggested_redirect=None,
                partial_help_possible=False,
            )

    state = ConversationState()
    state.record("user", "Explain the Supreme Court affirmative action ruling.")
    state.record("assistant", "The court ruled in Students for Fair Admissions v. Harvard/UNC (2023).")

    orch = Orchestrator(llm_provider=CaptureLLM(), search_provider=None)  # type: ignore[arg-type]
    orch.run_turn("What was overturned?", state=state)

    assert len(s1_user_prompts) == 1
    prompt = s1_user_prompts[0]
    assert "Students for Fair Admissions" in prompt
    assert "Explain the Supreme Court affirmative action ruling" in prompt


def test_conversation_state_records_correctly() -> None:
    from revere_agent.agent.state import ConversationState

    state = ConversationState()
    state.record("user", "First question.")
    state.record("assistant", "First answer.")
    state.record("user", "Second question.")

    assert len(state.history) == 3
    assert state.history[0] == ("user", "First question.")
    assert state.history[1] == ("assistant", "First answer.")
    assert state.history[2] == ("user", "Second question.")
