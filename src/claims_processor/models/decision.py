"""Decision models produced by the rules engine."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from claims_processor.models.fraud import FraudReport


class DecisionStatus(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    NEEDS_REUPLOAD = "NEEDS_REUPLOAD"


class RuleResult(BaseModel):
    code: str                 # CATEGORY_COVERED, WAITING_PERIOD, PRE_AUTH_MISSING ...
    passed: bool
    severity: str = "info"    # "error" (blocks approval) | "warning" | "info"
    message: str = ""
    evidence: dict = Field(default_factory=dict)


class PayableBreakdown(BaseModel):
    claimed_amount: float
    after_network_discount: float
    after_sub_limit: float
    copay_amount: float
    payable: float
    notes: list[str] = Field(default_factory=list)


class Decision(BaseModel):
    claim_id: str
    status: DecisionStatus
    reason: str = ""
    rules: list[RuleResult] = Field(default_factory=list)
    payable: Optional[PayableBreakdown] = None
    fraud: Optional[FraudReport] = None
