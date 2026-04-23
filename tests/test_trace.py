"""Verify tracing records spans and events for a pipeline run."""

import json
from pathlib import Path

from claims_processor.orchestrator.graph import run_graph

TEST_CASES = json.loads(
    (Path(__file__).resolve().parent.parent / "PROBLEM_STATEMENT" / "test_cases.json").read_text()
)["test_cases"]


def _case(cid):
    return next(t for t in TEST_CASES if t["case_id"] == cid)


def test_trace_has_all_stages_for_approved_claim():
    final = run_graph(_case("TC004")["input"], claim_id="TC004")
    assert final.trace is not None
    stages = [s.stage for s in final.trace.spans]
    for s in ("parse", "assemble", "rules", "fraud", "finalize"):
        assert s in stages, f"missing span {s} in {stages}"
    assert final.trace.duration_ms >= 0


def test_trace_short_circuits_on_consistency_error():
    final = run_graph(_case("TC003")["input"], claim_id="TC003")
    assert final.trace is not None
    stages = [s.stage for s in final.trace.spans]
    assert "parse" in stages
    assert "assemble" in stages
    assert "finalize" in stages
    # rules/fraud must have been skipped
    assert "rules" not in stages
    assert "fraud" not in stages


def test_trace_contains_rule_events():
    final = run_graph(_case("TC010")["input"], claim_id="TC010")
    rules_span = next(s for s in final.trace.spans if s.stage == "rules")
    rule_events = [e for e in rules_span.events if e.name == "rule_eval"]
    assert len(rule_events) >= 6
    payable_events = [e for e in rules_span.events if e.name == "payable_computed"]
    assert len(payable_events) == 1


def test_trace_off_returns_none():
    final = run_graph(_case("TC004")["input"], claim_id="TC004", trace=False)
    assert final.trace is None
