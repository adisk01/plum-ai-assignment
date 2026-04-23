"""Fraud detection models."""

from pydantic import BaseModel, Field


class FraudSignal(BaseModel):
    code: str              # e.g. SAME_DAY_CLAIMS, HIGH_VALUE_AUTO_REVIEW
    severity: str = "info" # "info" | "warning" | "error"
    weight: float = 0.0    # contribution to the overall fraud score (0..1)
    message: str = ""
    evidence: dict = Field(default_factory=dict)


class FraudReport(BaseModel):
    score: float = 0.0             # 0..1
    needs_manual_review: bool = False
    signals: list[FraudSignal] = Field(default_factory=list)
