"""Tests for the rules engine — covers the key scenarios from test_cases.json."""

from datetime import date

from claims_processor.models.claim import Claim, ConsistencyIssue
from claims_processor.models.decision import DecisionStatus
from claims_processor.models.documents import (
    DocType,
    HospitalBill,
    LineItem,
    ParsedDocument,
    Prescription,
    DiagnosticReport,
    DentalReport,
)
from claims_processor.rules_engine import financials, rules
from claims_processor.rules_engine.evaluate import evaluate_claim


def _doc(doc_type, extracted):
    return ParsedDocument(file_id="f", doc_type=doc_type, extracted=extracted, confidence=1.0)


def _claim(category, docs, issues=None):
    return Claim(claim_id="C1", category=category, documents=docs, issues=issues or [])


# ---------- financial calc ----------

def test_financials_tc010_consultation_network():
    # 5000 @ network: 20% off -> 4000 -> capped to 2000 -> 10% copay -> 1800
    b = financials.compute_payable(5000, "CONSULTATION", is_network=True)
    assert b.after_network_discount == 4000
    assert b.after_sub_limit == 2000
    assert b.copay_amount == 200
    assert b.payable == 1800


def test_financials_out_of_network_no_discount():
    b = financials.compute_payable(1500, "CONSULTATION", is_network=False)
    assert b.after_network_discount == 1500
    assert b.after_sub_limit == 1500
    assert b.payable == 1350  # 10% copay


# ---------- individual rules ----------

def test_category_not_covered():
    r = rules.check_category_covered("COSMETIC")
    assert not r.passed and r.severity == "error"


def test_minimum_amount_below_floor():
    r = rules.check_minimum_amount(200)
    assert not r.passed and r.severity == "error"


def test_per_claim_limit_warns_not_rejects():
    r = rules.check_per_claim_limit(8000)
    assert not r.passed and r.severity == "warning"


def test_waiting_period_diabetes():
    r = rules.check_waiting_period("2024-04-01", "2024-05-15", "Type 2 diabetes mellitus")
    assert not r.passed and r.severity == "error"


def test_pre_auth_missing_for_mri():
    r = rules.check_pre_auth("DIAGNOSTIC", 15000, "MRI Brain", pre_auth_provided=False)
    assert not r.passed and r.severity == "error"


def test_pre_auth_provided_passes():
    r = rules.check_pre_auth("DIAGNOSTIC", 15000, "MRI Brain", pre_auth_provided=True)
    assert r.passed


def test_exclusion_dental_whitening():
    items = [LineItem(description="Teeth Whitening procedure", amount=5000)]
    r = rules.check_exclusions("DENTAL", items, diagnosis="")
    assert not r.passed and r.severity == "error"


def test_network_hospital_matches():
    r = rules.check_network_hospital("Apollo Hospitals, Bangalore")
    assert r.evidence["in_network"] is True


# ---------- end-to-end evaluate_claim ----------

def test_evaluate_happy_path_consultation():
    docs = [
        _doc(DocType.PRESCRIPTION, Prescription(patient_name="A", diagnosis="Fever")),
        _doc(DocType.HOSPITAL_BILL, HospitalBill(patient_name="A", hospital_name="Apollo Hospitals", total=1500)),
    ]
    claim = _claim("CONSULTATION", docs)
    d = evaluate_claim(
        claim, claimed_amount=1500, treatment_date="2024-11-01",
        member_join_date="2024-04-01", submission_date=date(2024, 11, 10),
    )
    assert d.status == DecisionStatus.APPROVED
    assert d.payable.payable > 0


def test_evaluate_short_circuits_on_consistency_errors():
    claim = _claim("CONSULTATION", [], issues=[
        ConsistencyIssue(code="PATIENT_NAME_MISMATCH", severity="error", message="names differ"),
    ])
    d = evaluate_claim(claim, claimed_amount=1500, treatment_date="2024-11-01")
    assert d.status == DecisionStatus.REJECTED
    assert "consistency" in d.reason.lower()


def test_evaluate_per_claim_limit_needs_review():
    docs = [
        _doc(DocType.PRESCRIPTION, Prescription(patient_name="A", diagnosis="Fever")),
        _doc(DocType.HOSPITAL_BILL, HospitalBill(patient_name="A", hospital_name="Apollo Hospitals", total=8000)),
    ]
    claim = _claim("CONSULTATION", docs)
    d = evaluate_claim(
        claim, claimed_amount=8000, treatment_date="2024-11-01",
        member_join_date="2024-04-01", submission_date=date(2024, 11, 10),
    )
    assert d.status == DecisionStatus.NEEDS_REVIEW


def test_evaluate_rejects_mri_without_preauth():
    docs = [
        _doc(DocType.PRESCRIPTION, Prescription(patient_name="A", diagnosis="Headache")),
        _doc(DocType.DIAGNOSTIC_REPORT, DiagnosticReport(patient_name="A", modality="MRI")),
        _doc(DocType.HOSPITAL_BILL, HospitalBill(patient_name="A", hospital_name="Apollo Hospitals", total=15000)),
    ]
    claim = _claim("DIAGNOSTIC", docs)
    d = evaluate_claim(
        claim, claimed_amount=15000, treatment_date="2024-11-01",
        member_join_date="2024-04-01", pre_auth_provided=False,
        submission_date=date(2024, 11, 10),
    )
    assert d.status == DecisionStatus.REJECTED


def test_evaluate_rejects_dental_whitening():
    docs = [
        _doc(DocType.DENTAL_REPORT, DentalReport(patient_name="A", procedures=["Teeth Whitening"])),
        _doc(DocType.HOSPITAL_BILL, HospitalBill(
            patient_name="A", hospital_name="Apollo Hospitals",
            line_items=[LineItem(description="Teeth Whitening", amount=5000)],
            total=5000,
        )),
    ]
    claim = _claim("DENTAL", docs)
    d = evaluate_claim(
        claim, claimed_amount=5000, treatment_date="2024-11-01",
        member_join_date="2024-04-01", submission_date=date(2024, 11, 10),
    )
    assert d.status == DecisionStatus.REJECTED
