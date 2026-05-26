"""VerificationReport — output of Stage 6 (Chain-of-Verification, lite).

Decomposes the planned response into atomic factual claims and scores each
for confidence. Stage 7 uses this to hedge ONLY where warranted — calibrated,
not blanket. Based on Dhuliawala et al., 2023 (CoVe) and the verbalized-
confidence line of work (Xiong 2023, Yang 2024).
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

StrictModel = ConfigDict(extra="forbid")

VerificationBasis = Literal["evidence_base", "model_prior", "uncertain"]


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
