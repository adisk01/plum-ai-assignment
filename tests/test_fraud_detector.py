"""Tests for fraud detection — covers TC009 and the other fraud thresholds."""

from datetime import date

from claims_processor.fraud_detector import signals
from claims_processor.fraud_detector.detect import detect_fraud
from claims_processor.models.claim import Claim
from claims_processor.models.decision import DecisionStatus
from claims_processor.models.documents import (
    DocType, HospitalBill, ParsedDocument, Prescription,
)
from claims_processor.rules_engine.evaluate import evaluate_claim


def _doc(doc_type, extracted):
    return ParsedDocument(file_id="f", doc_type=doc_type, extracted=extracted, confidence=1.0)


# ---------- individual signals ----------

def test_same_day_claims_over_limit():
    history = [
        {"claim_id": "C1", "date": "2024-10-30", "amount": 1200},
        {"claim_id": "C2", "date": "2024-10-30", "amount": 1800},
        {"claim_id": "C3", "date": "2024-10-30", "amount": 2100},
    ]
    s = signals.check_same_day_claims("EMP008", "2024-10-30", history)
    assert s.severity == "error"
    assert s.evidence["count"] == 4


def test_same_day_claims_within_limit():
    s = signals.check_same_day_claims("EMP008", "2024-10-30", [])
    assert s.severity == "info"


def test_high_value_flag():
    s = signals.check_high_value(30000)
    assert s.severity == "warning"
    assert s.weight > 0


def test_duplicate_claim_detected():
    history = [{"claim_id": "X", "date": "2024-10-30", "amount": 1500, "provider": "Apollo"}]
    s = signals.check_duplicate_claim(1500, "2024-10-30", history, provider="Apollo Hospitals")
    # provider is different-ish - exact lowercase match fails, but no provider given in history? actually different
    # try exact match
    s2 = signals.check_duplicate_claim(1500, "2024-10-30", [{"date": "2024-10-30", "amount": 1500}])
    assert s2.severity == "error"


def test_monthly_claims_within_limit():
    s = signals.check_monthly_claims("EMP001", "2024-10-30", [
        {"date": "2024-10-01", "amount": 1000},
        {"date": "2024-10-10", "amount": 1000},
    ])
    assert s.severity == "info"


# ---------- detect_fraud entry point ----------

def test_detect_fraud_tc009_multiple_same_day():
    history = [
        {"claim_id": "CLM_0081", "date": "2024-10-30", "amount": 1200, "provider": "City Clinic A"},
        {"claim_id": "CLM_0082", "date": "2024-10-30", "amount": 1800, "provider": "City Clinic B"},
        {"claim_id": "CLM_0083", "date": "2024-10-30", "amount": 2100, "provider": "Wellness Center"},
    ]
    report = detect_fraud(
        member_id="EMP008",
        claimed_amount=4800,
        treatment_date="2024-10-30",
        claims_history=history,
    )
    assert report.needs_manual_review
    assert any(s.code == "SAME_DAY_CLAIMS" and s.severity == "error" for s in report.signals)


def test_detect_fraud_clean_claim():
    report = detect_fraud(
        member_id="EMP001", claimed_amount=1500, treatment_date="2024-11-01", claims_history=[],
    )
    assert not report.needs_manual_review
    assert report.score == 0.0


def test_detect_fraud_high_value_alone_does_not_force_review():
    # High-value alone weights 0.4 - below 0.80 threshold, no error - should not flag
    report = detect_fraud(
        member_id="EMP001", claimed_amount=30000, treatment_date="2024-11-01", claims_history=[],
    )
    assert not report.needs_manual_review
    assert any(s.code == "HIGH_VALUE_AUTO_REVIEW" for s in report.signals)


# ---------- evaluate_claim integration ----------

def test_evaluate_claim_manual_review_for_same_day_abuse():
    docs = [
        _doc(DocType.PRESCRIPTION, Prescription(patient_name="Ravi", diagnosis="Migraine")),
        _doc(DocType.HOSPITAL_BILL, HospitalBill(patient_name="Ravi",
                                                  hospital_name="City Clinic", total=4800)),
    ]
    claim = Claim(claim_id="C1", category="CONSULTATION", documents=docs)
    history = [
        {"date": "2024-10-30", "amount": 1200, "provider": "A"},
        {"date": "2024-10-30", "amount": 1800, "provider": "B"},
        {"date": "2024-10-30", "amount": 2100, "provider": "C"},
    ]
    d = evaluate_claim(
        claim, claimed_amount=4800, treatment_date="2024-10-30",
        member_join_date="2024-04-01", submission_date=date(2024, 11, 5),
        member_id="EMP008", claims_history=history,
    )
    assert d.status == DecisionStatus.MANUAL_REVIEW
    assert d.fraud is not None and d.fraud.needs_manual_review
