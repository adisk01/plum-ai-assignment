"""End-to-end pipeline result."""

from typing import Optional

from pydantic import BaseModel, Field

from claims_processor.models.claim import Claim
from claims_processor.models.decision import Decision, DecisionStatus
from claims_processor.observability.trace import Trace


class StageError(BaseModel):
    stage: str                 # "parse" | "assemble" | "evaluate" | "fraud"
    file_id: Optional[str] = None
    error_type: str
    message: str


class FinalDecision(BaseModel):
    claim_id: str
    status: DecisionStatus
    reason: str = ""
    confidence: float = 1.0
    claim: Optional[Claim] = None
    decision: Optional[Decision] = None
    stage_errors: list[StageError] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    trace: Optional[Trace] = None
