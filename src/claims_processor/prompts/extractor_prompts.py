"""Prompt builders for per-doc-type field extraction.

Each doc type has an explicit list of fields the LLM must return, with
per-field confidence values so downstream layers can reason about partial
readability (e.g. a rubber stamp over a registration number).
"""

from __future__ import annotations

from claims_processor.models.documents import DocType


_COMMON_INSTRUCTIONS = """
Instructions:
- Return ONLY a JSON object matching the schema below. No prose, no markdown fences.
- For every top-level field, include a confidence in `field_confidence` between 0.0 and 1.0.
- Use null for fields you cannot read. Do not invent values.
- Do not copy these instructions into your answer.
"""


def _schema_prescription() -> str:
    return """{
  "doctor_name": string | null,
  "doctor_registration": string | null,
  "doctor_specialization": string | null,
  "patient_name": string | null,
  "patient_age": integer | null,
  "patient_gender": "M" | "F" | "O" | null,
  "date": "YYYY-MM-DD" | null,
  "diagnosis": string | null,
  "medicines": [{"name": string, "dosage": string | null, "duration": string | null}],
  "tests_ordered": [string],
  "clinic_name": string | null,
  "field_confidence": {"<field_name>": number}
}"""


def _schema_hospital_bill() -> str:
    return """{
  "hospital_name": string | null,
  "gstin": string | null,
  "bill_number": string | null,
  "date": "YYYY-MM-DD" | null,
  "patient_name": string | null,
  "patient_age": integer | null,
  "patient_gender": "M" | "F" | "O" | null,
  "line_items": [{"description": string, "quantity": integer | null, "rate": number | null, "amount": number}],
  "subtotal": number | null,
  "gst_amount": number | null,
  "total": number,
  "alterations_detected": boolean,
  "field_confidence": {"<field_name>": number}
}"""


def _schema_pharmacy_bill() -> str:
    return """{
  "pharmacy_name": string | null,
  "drug_license": string | null,
  "bill_number": string | null,
  "date": "YYYY-MM-DD" | null,
  "patient_name": string | null,
  "prescribing_doctor": string | null,
  "line_items": [{"description": string, "quantity": integer | null, "rate": number | null, "amount": number}],
  "discount": number | null,
  "total": number,
  "field_confidence": {"<field_name>": number}
}"""


def _schema_lab_report() -> str:
    return """{
  "lab_name": string | null,
  "nabl_id": string | null,
  "patient_name": string | null,
  "patient_age": integer | null,
  "patient_gender": "M" | "F" | "O" | null,
  "referring_doctor": string | null,
  "sample_date": "YYYY-MM-DD" | null,
  "report_date": "YYYY-MM-DD" | null,
  "tests": [{"name": string, "result": string | null, "unit": string | null, "normal_range": string | null}],
  "pathologist_name": string | null,
  "remarks": string | null,
  "field_confidence": {"<field_name>": number}
}"""


def _schema_diagnostic_report() -> str:
    return """{
  "facility_name": string | null,
  "patient_name": string | null,
  "patient_age": integer | null,
  "referring_doctor": string | null,
  "date": "YYYY-MM-DD" | null,
  "modality": "MRI" | "CT Scan" | "Ultrasound" | "X-Ray" | "PET Scan" | string | null,
  "findings": string | null,
  "impression": string | null,
  "field_confidence": {"<field_name>": number}
}"""


def _schema_dental_report() -> str:
    return """{
  "dentist_name": string | null,
  "dentist_registration": string | null,
  "patient_name": string | null,
  "date": "YYYY-MM-DD" | null,
  "procedures": [string],
  "notes": string | null,
  "field_confidence": {"<field_name>": number}
}"""


def _schema_discharge_summary() -> str:
    return """{
  "hospital_name": string | null,
  "patient_name": string | null,
  "admission_date": "YYYY-MM-DD" | null,
  "discharge_date": "YYYY-MM-DD" | null,
  "final_diagnosis": string | null,
  "procedures_performed": [string],
  "attending_doctor": string | null,
  "field_confidence": {"<field_name>": number}
}"""


_SCHEMA_BUILDERS = {
    DocType.PRESCRIPTION: _schema_prescription,
    DocType.HOSPITAL_BILL: _schema_hospital_bill,
    DocType.PHARMACY_BILL: _schema_pharmacy_bill,
    DocType.LAB_REPORT: _schema_lab_report,
    DocType.DIAGNOSTIC_REPORT: _schema_diagnostic_report,
    DocType.DENTAL_REPORT: _schema_dental_report,
    DocType.DISCHARGE_SUMMARY: _schema_discharge_summary,
}


def build_extract_prompt(doc_type: DocType, content: str = "") -> str:
    if doc_type not in _SCHEMA_BUILDERS:
        raise ValueError(f"No extraction schema for doc_type={doc_type}")

    schema = _SCHEMA_BUILDERS[doc_type]()
    return f"""You are extracting structured fields from an Indian medical document of type: {doc_type.value}.

Schema (return JSON matching this shape):
{schema}
{_COMMON_INSTRUCTIONS}
Document content:
{content or "[binary image — analyze visually]"}
"""
