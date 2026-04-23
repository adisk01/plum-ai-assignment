"""Pydantic schemas for every document type the extractor produces.

Design:
- Every field is Optional except a bill's `total` (without which the claim
  cannot be evaluated).
- Every typed document carries `field_confidence: dict[str, float]` so
  downstream layers can trace which fields the extractor was unsure about
  (e.g. a rubber stamp over a registration number).
- Doctor registration numbers follow Indian state-coded formats; a regex
  validator tags the parsed reg number with its state.
- Amounts use Decimal for exact rupee math (TC010 requires ₹3,240 exactly).
"""

from __future__ import annotations

import re
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums + small value objects
# ---------------------------------------------------------------------------


class DocType(str, Enum):
    PRESCRIPTION = "PRESCRIPTION"
    HOSPITAL_BILL = "HOSPITAL_BILL"
    LAB_REPORT = "LAB_REPORT"
    PHARMACY_BILL = "PHARMACY_BILL"
    DIAGNOSTIC_REPORT = "DIAGNOSTIC_REPORT"
    DENTAL_REPORT = "DENTAL_REPORT"
    DISCHARGE_SUMMARY = "DISCHARGE_SUMMARY"
    UNKNOWN = "UNKNOWN"


# Indian medical registration number formats.
# Source: PROBLEM_STATEMENT/sample_documents_guide.md
_REG_PATTERNS = {
    "KA": re.compile(r"^KA/\d{4,6}/\d{4}$"),
    "MH": re.compile(r"^MH/\d{4,6}/\d{4}$"),
    "DL": re.compile(r"^DL/\d{4,6}/\d{4}$"),
    "TN": re.compile(r"^TN/\d{4,6}/\d{4}$"),
    "GJ": re.compile(r"^GJ/\d{4,6}/\d{4}$"),
    "AP": re.compile(r"^AP/\d{4,6}/\d{4}$"),
    "UP": re.compile(r"^UP/\d{4,6}/\d{4}$"),
    "WB": re.compile(r"^WB/\d{4,6}/\d{4}$"),
    "KL": re.compile(r"^KL/\d{4,6}/\d{4}$"),
    "AYUR": re.compile(r"^AYUR/[A-Z]{2}/\d{3,6}/\d{4}$"),
}


def validate_doctor_registration(value: str | None) -> tuple[bool, str | None]:
    """Return (is_valid, state_code). Unknown state or garbled → (False, None)."""
    if not value:
        return (False, None)
    v = value.strip().upper()
    for state, pat in _REG_PATTERNS.items():
        if pat.match(v):
            return (True, state)
    return (False, None)


class Medicine(BaseModel):
    name: Optional[str] = None
    dosage: Optional[str] = None
    duration: Optional[str] = None


class LabTest(BaseModel):
    name: Optional[str] = None
    result: Optional[str] = None
    unit: Optional[str] = None
    normal_range: Optional[str] = None


class LineItem(BaseModel):
    description: str
    quantity: Optional[int] = None
    rate: Optional[Decimal] = None
    amount: Decimal

    @field_validator("amount", "rate", mode="before")
    @classmethod
    def _coerce_decimal(cls, v):
        if v is None or isinstance(v, Decimal):
            return v
        return Decimal(str(v))


# ---------------------------------------------------------------------------
# Typed documents
# ---------------------------------------------------------------------------


class Prescription(BaseModel):
    doctor_name: Optional[str] = None
    doctor_registration: Optional[str] = None
    doctor_registration_valid: bool = False
    doctor_registration_state: Optional[str] = None
    doctor_specialization: Optional[str] = None
    patient_name: Optional[str] = None
    patient_age: Optional[int] = None
    patient_gender: Optional[str] = None
    date: Optional[str] = None  # ISO date as string; parsed by callers when needed
    diagnosis: Optional[str] = None
    medicines: list[Medicine] = Field(default_factory=list)
    tests_ordered: list[str] = Field(default_factory=list)
    clinic_name: Optional[str] = None

    def fill_registration_metadata(self) -> None:
        valid, state = validate_doctor_registration(self.doctor_registration)
        self.doctor_registration_valid = valid
        self.doctor_registration_state = state


class HospitalBill(BaseModel):
    hospital_name: Optional[str] = None
    gstin: Optional[str] = None
    bill_number: Optional[str] = None
    date: Optional[str] = None
    patient_name: Optional[str] = None
    patient_age: Optional[int] = None
    patient_gender: Optional[str] = None
    line_items: list[LineItem] = Field(default_factory=list)
    subtotal: Optional[Decimal] = None
    gst_amount: Optional[Decimal] = None
    total: Decimal  # REQUIRED — claim cannot be evaluated without a total
    alterations_detected: bool = False

    @field_validator("total", "subtotal", "gst_amount", mode="before")
    @classmethod
    def _coerce_decimal(cls, v):
        if v is None or isinstance(v, Decimal):
            return v
        return Decimal(str(v))


class PharmacyBill(BaseModel):
    pharmacy_name: Optional[str] = None
    drug_license: Optional[str] = None
    bill_number: Optional[str] = None
    date: Optional[str] = None
    patient_name: Optional[str] = None
    prescribing_doctor: Optional[str] = None
    line_items: list[LineItem] = Field(default_factory=list)
    discount: Optional[Decimal] = None
    total: Decimal  # REQUIRED

    @field_validator("total", "discount", mode="before")
    @classmethod
    def _coerce_decimal(cls, v):
        if v is None or isinstance(v, Decimal):
            return v
        return Decimal(str(v))


class LabReport(BaseModel):
    lab_name: Optional[str] = None
    nabl_id: Optional[str] = None
    patient_name: Optional[str] = None
    patient_age: Optional[int] = None
    patient_gender: Optional[str] = None
    referring_doctor: Optional[str] = None
    sample_date: Optional[str] = None
    report_date: Optional[str] = None
    tests: list[LabTest] = Field(default_factory=list)
    pathologist_name: Optional[str] = None
    remarks: Optional[str] = None


class DiagnosticReport(BaseModel):
    """Radiology / imaging report — MRI, CT, ultrasound findings."""
    facility_name: Optional[str] = None
    patient_name: Optional[str] = None
    patient_age: Optional[int] = None
    referring_doctor: Optional[str] = None
    date: Optional[str] = None
    modality: Optional[str] = None  # "MRI" | "CT Scan" | "Ultrasound" | ...
    findings: Optional[str] = None
    impression: Optional[str] = None


class DentalReport(BaseModel):
    dentist_name: Optional[str] = None
    dentist_registration: Optional[str] = None
    patient_name: Optional[str] = None
    date: Optional[str] = None
    procedures: list[str] = Field(default_factory=list)
    notes: Optional[str] = None


class DischargeSummary(BaseModel):
    hospital_name: Optional[str] = None
    patient_name: Optional[str] = None
    admission_date: Optional[str] = None
    discharge_date: Optional[str] = None
    final_diagnosis: Optional[str] = None
    procedures_performed: list[str] = Field(default_factory=list)
    attending_doctor: Optional[str] = None


# ---------------------------------------------------------------------------
# Unified output wrapper
# ---------------------------------------------------------------------------


ExtractedBody = (
    Prescription
    | HospitalBill
    | PharmacyBill
    | LabReport
    | DiagnosticReport
    | DentalReport
    | DischargeSummary
)


class ParsedDocument(BaseModel):
    """Unified output of the document extractor.

    Every downstream layer consumes this — never the raw typed body directly.
    """

    file_id: str
    doc_type: DocType
    extracted: Optional[ExtractedBody] = None
    field_confidence: dict[str, float] = Field(default_factory=dict)
    overall_confidence: float = 0.0
    warnings: list[str] = Field(default_factory=list)
    raw_text_preview: Optional[str] = None

    @field_validator("overall_confidence")
    @classmethod
    def _clamp_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, float(v)))


# ---------------------------------------------------------------------------
# Type → schema mapping (used by the extractor)
# ---------------------------------------------------------------------------

SCHEMA_FOR_DOC_TYPE: dict[DocType, type[BaseModel]] = {
    DocType.PRESCRIPTION: Prescription,
    DocType.HOSPITAL_BILL: HospitalBill,
    DocType.PHARMACY_BILL: PharmacyBill,
    DocType.LAB_REPORT: LabReport,
    DocType.DIAGNOSTIC_REPORT: DiagnosticReport,
    DocType.DENTAL_REPORT: DentalReport,
    DocType.DISCHARGE_SUMMARY: DischargeSummary,
}
