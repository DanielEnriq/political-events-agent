"""Conversation state.

Day 2 only needs a minimal shape: a session ID and a list of
(role, content) turns for S1 to use when resolving references like "that
ruling" or "tell me more." Multi-turn memory and session persistence are
deferred to later days.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Literal

Role = Literal["user", "assistant"]


@dataclass
class ConversationState:
    """Lightweight per-session state passed into each orchestrator run."""

    session_id: str = field(default_factory=lambda: f"sess-{uuid.uuid4().hex[:12]}")
    history: list[tuple[Role, str]] = field(default_factory=list)

    def record(self, role: Role, content: str) -> None:
        self.history.append((role, content))
