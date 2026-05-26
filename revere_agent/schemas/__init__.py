"""Public schema surface — all cross-stage contracts live here."""

from .intake import IntakeAnalysis, Modality
from .perspectives import Perspective, PerspectiveAnalysis
from .response import Citation, FinalResponse, SelfCheckReport
from .scope import ScopeDecision
from .search import ExtractedDoc, SearchHit, SearchPlan, SourceType
from .source_quality import (
    EditorialSlant,
    EvidenceBase,
    PrimacyTier,
    SourceAssessment,
)
from .trace import ReasoningTrace, StageTraceEntry
from .verification import FactualClaim, VerificationReport

__all__ = [
    "Citation",
    "EditorialSlant",
    "EvidenceBase",
    "ExtractedDoc",
    "FactualClaim",
    "FinalResponse",
    "IntakeAnalysis",
    "Modality",
    "Perspective",
    "PerspectiveAnalysis",
    "PrimacyTier",
    "ReasoningTrace",
    "ScopeDecision",
    "SearchHit",
    "SearchPlan",
    "SelfCheckReport",
    "SourceAssessment",
    "SourceType",
    "StageTraceEntry",
    "VerificationReport",
]
