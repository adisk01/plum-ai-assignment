"""Claim assembly models."""

from typing import Optional

from pydantic import BaseModel, Field

from claims_processor.models.documents import ParsedDocument


class ConsistencyIssue(BaseModel):
    code: str              # e.g. PATIENT_NAME_MISMATCH
    severity: str          # "error" | "warning"
    message: str
    evidence: dict = Field(default_factory=dict)


class Claim(BaseModel):
    claim_id: str
    category: str          # CONSULTATION | PHARMACY | DIAGNOSTIC | ...
    documents: list[ParsedDocument] = Field(default_factory=list)
    issues: list[ConsistencyIssue] = Field(default_factory=list)
    missing_documents: list[str] = Field(default_factory=list)

    def has_errors(self) -> bool:
        return any(i.severity == "error" for i in self.issues)
