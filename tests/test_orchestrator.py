"""End-to-end pipeline tests — exercises test_cases.json input shape."""

import json
from pathlib import Path

from claims_processor.models.decision import DecisionStatus
from claims_processor.orchestrator.pipeline import process_claim

TEST_CASES = json.loads(
    (Path(__file__).resolve().parent.parent / "PROBLEM_STATEMENT" / "test_cases.json").read_text()
)["test_cases"]


def _case(case_id):
    return next(tc for tc in TEST_CASES if tc["case_id"] == case_id)


def test_tc001_wrong_document_uploaded():
    tc = _case("TC001")
    # Both docs are PRESCRIPTION but category=CONSULTATION needs HOSPITAL_BILL.
    # The assembler will flag the missing required doc.
    final = process_claim(tc["input"], claim_id="TC001")
    # Missing required HOSPITAL_BILL -> consistency error -> short-circuits to REJECTED
    assert final.status in (DecisionStatus.REJECTED, DecisionStatus.NEEDS_REUPLOAD)
    # The claim should report a missing document
    assert final.claim is None or "HOSPITAL_BILL" in final.claim.missing_documents


def test_tc004_clean_consultation_approval():
    tc = _case("TC004")
    final = process_claim(tc["input"], claim_id="TC004")
    assert final.status == DecisionStatus.APPROVED
    assert final.decision.payable.payable > 0
    assert final.confidence >= 0.85


def test_tc005_waiting_period_diabetes():
    tc = _case("TC005")
    ci = dict(tc["input"])
    ci["member_join_date"] = "2024-09-01"  # policy member data
    final = process_claim(ci, claim_id="TC005")
    assert final.status == DecisionStatus.REJECTED
    assert any(r.code == "WAITING_PERIOD" and not r.passed for r in final.decision.rules)


def test_tc007_mri_without_preauth():
    tc = _case("TC007")
    ci = dict(tc["input"])
    ci["member_join_date"] = "2024-04-01"
    ci["pre_auth_provided"] = False
    final = process_claim(ci, claim_id="TC007")
    assert final.status == DecisionStatus.REJECTED
    assert any(r.code == "PRE_AUTH" and not r.passed for r in final.decision.rules)


def test_tc009_same_day_fraud_manual_review():
    tc = _case("TC009")
    ci = dict(tc["input"])
    ci["member_join_date"] = "2024-04-01"
    final = process_claim(ci, claim_id="TC009")
    assert final.status == DecisionStatus.MANUAL_REVIEW
    assert final.decision.fraud is not None
    assert final.decision.fraud.needs_manual_review


def test_tc010_network_discount_before_copay():
    tc = _case("TC010")
    ci = dict(tc["input"])
    ci["member_join_date"] = "2024-04-01"
    final = process_claim(ci, claim_id="TC010")
    assert final.status == DecisionStatus.APPROVED
    # 4500 @ network: 20% off -> 3600 -> sub_limit 2000 -> 10% copay -> 1800
    # (policy sub-limit 2000 caps the 3600 down to 2000 first)
    p = final.decision.payable
    assert p.after_network_discount == 3600
    assert p.after_sub_limit == 2000
    assert p.payable == 1800


def test_tc011_simulated_failure_reduces_confidence():
    tc = _case("TC011")
    ci = dict(tc["input"])
    ci["member_join_date"] = "2024-04-01"
    final = process_claim(ci, claim_id="TC011")
    # Should not crash, confidence should be lower than a clean run
    assert final.confidence < 1.0
    assert any(e.error_type == "SimulatedFailure" for e in final.stage_errors)


def test_tc012_excluded_obesity():
    tc = _case("TC012")
    ci = dict(tc["input"])
    ci["member_join_date"] = "2024-04-01"
    final = process_claim(ci, claim_id="TC012")
    assert final.status == DecisionStatus.REJECTED
    assert any(r.code == "EXCLUSIONS" and not r.passed for r in final.decision.rules)
