"""Decision models produced by the rules engine."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from claims_processor.models.fraud import FraudReport


class DecisionStatus(str, Enum):
    APPROVED = "APPROVED"
    PARTIAL = "PARTIAL"
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


class LineItemDecision(BaseModel):
    description: str
    amount: float
    covered: bool
    reason: str = ""   # why this item was excluded (if covered=False)


class PayableBreakdown(BaseModel):
    claimed_amount: float                         # gross claim / sum of all line items
    after_exclusions: Optional[float] = None      # sum of covered line items only
    after_network_discount: float
    after_sub_limit: float
    copay_amount: float
    payable: float
    line_items: list[LineItemDecision] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class Decision(BaseModel):
    claim_id: str
    status: DecisionStatus
    reason: str = ""
    rules: list[RuleResult] = Field(default_factory=list)
    payable: Optional[PayableBreakdown] = None
    fraud: Optional[FraudReport] = None
