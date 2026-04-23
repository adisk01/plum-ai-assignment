"""LangGraph pipeline tests — same scenarios as test_orchestrator, run via graph."""

import json
from pathlib import Path

from claims_processor.models.decision import DecisionStatus
from claims_processor.orchestrator.graph import build_graph, run_graph

TEST_CASES = json.loads(
    (Path(__file__).resolve().parent.parent / "PROBLEM_STATEMENT" / "test_cases.json").read_text()
)["test_cases"]


def _case(case_id):
    return next(tc for tc in TEST_CASES if tc["case_id"] == case_id)


def test_graph_compiles():
    g = build_graph()
    assert g is not None
    # nodes present
    nodes = g.get_graph().nodes
    for n in ("parse", "assemble", "rules", "fraud", "finalize"):
        assert n in nodes


def test_graph_tc004_approved():
    final = run_graph(_case("TC004")["input"], claim_id="TC004")
    assert final.status == DecisionStatus.APPROVED
    assert final.decision.payable.payable > 0


def test_graph_tc005_waiting_period():
    final = run_graph(_case("TC005")["input"], claim_id="TC005")
    assert final.status == DecisionStatus.REJECTED


def test_graph_tc008_per_claim_limit():
    final = run_graph(_case("TC008")["input"], claim_id="TC008")
    assert final.status == DecisionStatus.REJECTED


def test_graph_tc009_fraud_manual_review():
    final = run_graph(_case("TC009")["input"], claim_id="TC009")
    assert final.status == DecisionStatus.MANUAL_REVIEW
    assert final.decision.fraud is not None
    assert final.decision.fraud.needs_manual_review


def test_graph_tc010_network_discount():
    final = run_graph(_case("TC010")["input"], claim_id="TC010")
    assert final.status == DecisionStatus.APPROVED
    p = final.decision.payable
    assert p.after_network_discount == 3600
    assert p.payable == 1800
