"""Pydantic schemas for claim documents.

Kept simple: all fields optional except bill totals. Numbers are floats,
dates are ISO strings. Downstream layers validate against policy rules.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DocType(str, Enum):
    PRESCRIPTION = "PRESCRIPTION"
    HOSPITAL_BILL = "HOSPITAL_BILL"
    LAB_REPORT = "LAB_REPORT"
    PHARMACY_BILL = "PHARMACY_BILL"
    DIAGNOSTIC_REPORT = "DIAGNOSTIC_REPORT"
    DENTAL_REPORT = "DENTAL_REPORT"
    DISCHARGE_SUMMARY = "DISCHARGE_SUMMARY"
    UNKNOWN = "UNKNOWN"


class ClassifierResponse(BaseModel):
    doc_type: DocType
    confidence: float = 0.0
    readable: bool = True
    reason: Optional[str] = None


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
    rate: Optional[float] = None
    amount: float


class Prescription(BaseModel):
    doctor_name: Optional[str] = None
    doctor_registration: Optional[str] = None
    doctor_specialization: Optional[str] = None
    patient_name: Optional[str] = None
    patient_age: Optional[int] = None
    patient_gender: Optional[str] = None
    date: Optional[str] = None
    diagnosis: Optional[str] = None
    medicines: list[Medicine] = Field(default_factory=list)
    tests_ordered: list[str] = Field(default_factory=list)
    clinic_name: Optional[str] = None


class HospitalBill(BaseModel):
    hospital_name: Optional[str] = None
    gstin: Optional[str] = None
    bill_number: Optional[str] = None
    date: Optional[str] = None
    patient_name: Optional[str] = None
    patient_age: Optional[int] = None
    patient_gender: Optional[str] = None
    line_items: list[LineItem] = Field(default_factory=list)
    subtotal: Optional[float] = None
    gst_amount: Optional[float] = None
    total: Optional[float] = None


class PharmacyBill(BaseModel):
    pharmacy_name: Optional[str] = None
    drug_license: Optional[str] = None
    bill_number: Optional[str] = None
    date: Optional[str] = None
    patient_name: Optional[str] = None
    prescribing_doctor: Optional[str] = None
    line_items: list[LineItem] = Field(default_factory=list)
    discount: Optional[float] = None
    total: Optional[float] = None


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
    facility_name: Optional[str] = None
    patient_name: Optional[str] = None
    patient_age: Optional[int] = None
    referring_doctor: Optional[str] = None
    date: Optional[str] = None
    modality: Optional[str] = None
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


class ParsedDocument(BaseModel):
    file_id: str
    doc_type: DocType
    extracted: Optional[BaseModel] = None
    confidence: float = 0.0


SCHEMA_FOR_DOC_TYPE = {
    DocType.PRESCRIPTION: Prescription,
    DocType.HOSPITAL_BILL: HospitalBill,
    DocType.PHARMACY_BILL: PharmacyBill,
    DocType.LAB_REPORT: LabReport,
    DocType.DIAGNOSTIC_REPORT: DiagnosticReport,
    DocType.DENTAL_REPORT: DentalReport,
    DocType.DISCHARGE_SUMMARY: DischargeSummary,
}
