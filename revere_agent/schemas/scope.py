"""ScopeDecision — output of Stage 2 (the anti-keyword-matching stage).

The schema is shaped to force *reasoning* about charter clauses. The
`reasoning` field must reference what the user appears to want and which
charter categories apply — not keywords found in the message.
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

StrictModel = ConfigDict(extra="forbid")


class ScopeDecision(BaseModel):
    model_config = StrictModel

    in_scope: bool = Field(
        description="Whether the request falls within the agent's charter."
    )
    confidence: Annotated[int, Field(ge=1, le=5)] = Field(
        description="1 = very uncertain, 5 = certain."
    )
    reasoning: str = Field(
        description="Free-text reasoning. MUST reference charter clauses, "
        "not keywords. Explain what the user appears to want and why that "
        "does or does not map to the charter."
    )
    matched_charter_categories: list[str] = Field(
        default_factory=list,
        description="The charter categories this request matches, if any "
        "(e.g. 'legislation', 'court_decisions', 'elections').",
    )
    suggested_redirect: str | None = Field(
        default=None,
        description="If out of scope: a graceful suggestion of where the "
        "user could go for help. Otherwise null.",
    )
    partial_help_possible: bool = Field(
        description="True if part of the request is in scope (e.g. a homework "
        "question that happens to be about civics)."
    )
