"""VerificationReport — output of Stage 6 (Chain-of-Verification, lite).

Decomposes the planned response into atomic factual claims and scores each
for confidence. Stage 7 uses this to hedge ONLY where warranted — calibrated,
not blanket. Based on Dhuliawala et al., 2023 (CoVe) and the verbalized-
confidence line of work (Xiong 2023, Yang 2024).
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

StrictModel = ConfigDict(extra="forbid")

VerificationBasis = Literal["evidence_base", "model_prior", "uncertain"]

# Phase 2: optional claim-classification enums.
ClaimType = Literal[
    "verified_fact",
    "reported_claim",
    "disputed_interpretation",
    "unsupported_claim",
    "value_judgment",
]

SupportLevel = Literal[
    "directly_sourced",
    "indirectly_sourced",
    "model_prior",
    "unsupported",
]

OutcomeRelevance = Literal[
    "direct",
    "indirect",
    "none",
    "unclear",
]

# Known field names in FactualClaim — used by the normalization validator.
# Includes new optional Phase 2 fields so they are not accidentally remapped.
_FACTUAL_CLAIM_KNOWN_FIELDS = frozenset(
    {
        "claim",
        "confidence",
        "verification_basis",
        "suggested_hedging",
        "drop_if_uncorroborated",
        "claim_type",
        "support_level",
        "attribution",
        "outcome_relevance",
    }
)


class FactualClaim(BaseModel):
    model_config = StrictModel

    claim: str = Field(description="The atomic factual claim, as it would be stated.")
    confidence: Annotated[int, Field(ge=1, le=5)] = Field(
        description="Would you bet on this? 1 = no, 5 = yes."
    )
    verification_basis: VerificationBasis = Field(
        description="Where does this confidence come from?"
    )
    suggested_hedging: str | None = Field(
        default=None,
        description="If confidence < 4, suggest softening language to use in S7.",
    )
    drop_if_uncorroborated: bool = Field(
        description="If true, the composer should remove this claim entirely "
        "rather than hedge it."
    )

    # Phase 2 optional fields — all default to None for backward compatibility.
    claim_type: ClaimType | None = Field(
        default=None,
        description="Classification of the claim's epistemic status.",
    )
    support_level: SupportLevel | None = Field(
        default=None,
        description="How well the retrieved evidence supports this specific claim.",
    )
    attribution: str | None = Field(
        default=None,
        description="For reported_claim: who made the claim. Keep concise (≤ 10 words).",
    )
    outcome_relevance: OutcomeRelevance | None = Field(
        default=None,
        description="Whether this claim, if true, would affect the event's outcome.",
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_drop_field(cls, data: Any) -> Any:
        """Normalize near-miss spellings of drop_if_uncorroborated before strict validation.

        The model occasionally returns a misspelled key (e.g. 'drop_if_uncoroborated'
        with one 'r'). Since drop_if_uncorroborated is the only boolean field in
        FactualClaim, any unrecognized bool-valued key is remapped to the canonical name.
        extra="forbid" still applies after this normalization.
        """
        if not isinstance(data, dict) or "drop_if_uncorroborated" in data:
            return data
        for key, val in list(data.items()):
            if key not in _FACTUAL_CLAIM_KNOWN_FIELDS and isinstance(val, bool):
                data = dict(data)
                data["drop_if_uncorroborated"] = data.pop(key)
                break
        return data


class VerificationReport(BaseModel):
    model_config = StrictModel

    claims: list[FactualClaim]
    overall_calibration_note: str = Field(
        description="One- or two-sentence note about the response's overall "
        "epistemic posture (e.g. 'most facts are well-corroborated; figures "
        "on cost estimates vary by source')."
    )
    things_i_should_not_assert: list[str] = Field(
        default_factory=list,
        description="Claims the model considered making but couldn't justify.",
    )
