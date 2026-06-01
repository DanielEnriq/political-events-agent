"""Regression tests for schema validation edge cases."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from revere_agent.schemas.verification import FactualClaim, VerificationReport


def _valid_claim_data(**overrides) -> dict:
    base = {
        "claim": "The debt ceiling was raised in 2023.",
        "confidence": 4,
        "verification_basis": "evidence_base",
        "suggested_hedging": None,
        "drop_if_uncorroborated": False,
    }
    return {**base, **overrides}


# ── drop_if_uncorroborated normalization ──────────────────────────────────────


def test_factual_claim_correct_spelling_validates() -> None:
    """Baseline: correct field name validates without modification."""
    claim = FactualClaim.model_validate(_valid_claim_data(drop_if_uncorroborated=True))
    assert claim.drop_if_uncorroborated is True


def test_factual_claim_near_miss_single_r_normalized() -> None:
    """One missing 'r' — 'drop_if_uncoroborated' — is remapped to canonical key."""
    data = _valid_claim_data()
    data.pop("drop_if_uncorroborated")
    data["drop_if_uncoroborated"] = False  # common LLM misspelling
    claim = FactualClaim.model_validate(data)
    assert claim.drop_if_uncorroborated is False


def test_factual_claim_near_miss_true_value_normalized() -> None:
    """Misspelled key with True value is also normalized correctly."""
    data = _valid_claim_data()
    data.pop("drop_if_uncorroborated")
    data["drop_if_uncoroborated"] = True
    claim = FactualClaim.model_validate(data)
    assert claim.drop_if_uncorroborated is True


def test_factual_claim_extra_string_field_still_forbidden() -> None:
    """Non-boolean extra fields still raise ValidationError (extra='forbid' intact)."""
    data = _valid_claim_data(unknown_string_field="oops")
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        FactualClaim.model_validate(data)


def test_factual_claim_missing_drop_field_without_substitute_raises() -> None:
    """If drop_if_uncorroborated is absent and no substitute bool exists, validation fails."""
    data = _valid_claim_data()
    data.pop("drop_if_uncorroborated")
    with pytest.raises(ValidationError):
        FactualClaim.model_validate(data)


# ── Full VerificationReport round-trip ───────────────────────────────────────


def test_verification_report_round_trip() -> None:
    """VerificationReport with correct data validates and serializes cleanly."""
    report = VerificationReport(
        claims=[
            FactualClaim(
                claim="Congress passed the Fiscal Responsibility Act in 2023.",
                confidence=5,
                verification_basis="evidence_base",
                suggested_hedging=None,
                drop_if_uncorroborated=False,
            ),
            FactualClaim(
                claim="The deal suspended the debt ceiling until January 2025.",
                confidence=3,
                verification_basis="model_prior",
                suggested_hedging="Sources vary on the exact date; verify before asserting.",
                drop_if_uncorroborated=True,
            ),
        ],
        overall_calibration_note="Most facts are well-corroborated; exact legislative dates vary.",
        things_i_should_not_assert=["The exact vote margin in the Senate"],
    )
    dumped = report.model_dump(mode="json")
    recovered = VerificationReport.model_validate(dumped)
    assert recovered.claims[1].drop_if_uncorroborated is True
    assert recovered.overall_calibration_note == report.overall_calibration_note
