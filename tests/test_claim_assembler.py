"""Tests for claim assembler. No LLM calls — feeds ParsedDocuments directly."""

from claims_processor.claim_assembler.assemble import assemble_claim
from claims_processor.models.documents import (
    DocType,
    HospitalBill,
    LabReport,
    LabTest,
    LineItem,
    Medicine,
    ParsedDocument,
    PharmacyBill,
    Prescription,
)


def _rx(patient="Rajesh Kumar", date="2024-11-01", meds=None, tests=None):
    return ParsedDocument(
        file_id="F001",
        doc_type=DocType.PRESCRIPTION,
        extracted=Prescription(
            patient_name=patient,
            date=date,
            medicines=[Medicine(name=m) for m in (meds or ["Paracetamol"])],
            tests_ordered=tests or [],
        ),
    )


def _bill(patient="Rajesh Kumar", date="2024-11-01", total=1500):
    return ParsedDocument(
        file_id="F002",
        doc_type=DocType.HOSPITAL_BILL,
        extracted=HospitalBill(
            patient_name=patient, date=date, total=total,
            line_items=[LineItem(description="Consultation", amount=total)],
        ),
    )


def _pharmacy(patient="Rajesh Kumar", items=None):
    return ParsedDocument(
        file_id="F003",
        doc_type=DocType.PHARMACY_BILL,
        extracted=PharmacyBill(
            patient_name=patient, total=500,
            line_items=[LineItem(description=d, amount=100) for d in (items or ["Paracetamol"])],
        ),
    )


def test_happy_path_consultation():
    claim = assemble_claim("C001", "CONSULTATION", [_rx(), _bill()])
    assert claim.issues == []
    assert claim.missing_documents == []
    assert not claim.has_errors()


def test_patient_name_mismatch_flagged():
    claim = assemble_claim("C002", "CONSULTATION", [_rx(), _bill(patient="Ramesh Gupta")])
    codes = [i.code for i in claim.issues]
    assert "PATIENT_NAME_MISMATCH" in codes
    assert claim.has_errors()


def test_missing_required_document():
    claim = assemble_claim("C003", "CONSULTATION", [_rx()])
    assert "HOSPITAL_BILL" in claim.missing_documents
    assert any(i.code == "MISSING_REQUIRED_DOCUMENT" for i in claim.issues)


def test_pharmacy_item_not_prescribed():
    rx = _rx(meds=["Paracetamol"])
    pb = _pharmacy(items=["Paracetamol", "Amoxicillin"])
    claim = assemble_claim("C004", "PHARMACY", [rx, pb])
    codes = [i.code for i in claim.issues]
    assert "PHARMACY_ITEM_NOT_PRESCRIBED" in codes


def test_lab_test_not_ordered():
    rx = _rx(tests=["CBC"])
    lab = ParsedDocument(
        file_id="F004",
        doc_type=DocType.LAB_REPORT,
        extracted=LabReport(
            patient_name="Rajesh Kumar",
            tests=[LabTest(name="CBC"), LabTest(name="Thyroid Panel")],
        ),
    )
    claim = assemble_claim("C005", "CONSULTATION", [_rx(tests=["CBC"]), _bill(), lab])
    assert any(i.code == "LAB_TEST_NOT_ORDERED" for i in claim.issues)


def test_date_before_prescription_flagged():
    claim = assemble_claim(
        "C006", "CONSULTATION",
        [_rx(date="2024-11-05"), _bill(date="2024-10-30")],
    )
    assert any(i.code == "DATE_BEFORE_PRESCRIPTION" for i in claim.issues)


def test_fuzzy_name_match_passes():
    # Minor variation (extra space) should NOT flag
    claim = assemble_claim("C007", "CONSULTATION", [_rx(patient="Rajesh  Kumar"), _bill(patient="Rajesh Kumar")])
    assert not any(i.code == "PATIENT_NAME_MISMATCH" for i in claim.issues)
