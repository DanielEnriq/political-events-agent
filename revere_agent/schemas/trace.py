"""ReasoningTrace — the auditable record of one turn through the pipeline.

The trace is a first-class deliverable, not a debug log. It's what gets
rendered in the Gradio UI (Day 4) and what the eval harness (Day 5)
inspects for reasoning-quality scoring.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .response import FinalResponse

StrictModel = ConfigDict(extra="forbid")


class StageTraceEntry(BaseModel):
    """One row in the trace: the structured output of a single stage."""

    model_config = StrictModel

    stage_id: str = Field(
        description="Stable identifier like 's1_intake', 's2_scope', etc."
    )
    prompt_version: str = Field(
        description="Hash or version tag of the prompt file used. Lets us "
        "tie behavior changes back to prompt changes."
    )
    model_alias: str = Field(
        description="Logical model name (e.g. 'sonnet-main'), not the concrete "
        "provider-specific model ID."
    )
    duration_ms: int
    output: dict[str, Any] = Field(
        description="The stage's Pydantic output, serialized to dict via "
        ".model_dump(). Kept as dict so the trace itself remains schema-agnostic."
    )


class ReasoningTrace(BaseModel):
    model_config = StrictModel

    turn_id: str
    session_id: str
    user_message: str
    started_at: datetime
    entries: list[StageTraceEntry] = Field(default_factory=list)
    final_response: FinalResponse | None = None
