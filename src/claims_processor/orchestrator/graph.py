"""LangGraph wiring for the claims pipeline.

Nodes:
    parse -> assemble -> rules -> fraud -> finalize
    with short-circuit edges on parse errors and consistency errors.
"""

from typing import Any, Optional, TypedDict

from langgraph.graph import END, StateGraph
from langsmith import traceable

from claims_processor.claim_assembler.assemble import assemble_claim
from claims_processor.core import config
from claims_processor.document_extractor import parse
from claims_processor.document_extractor.exceptions import (
    UnreadableDocumentError,
    UnsupportedFileTypeError,
    WrongDocumentTypeError,
)
from claims_processor.fraud_detector.detect import detect_fraud
from claims_processor.models.claim import Claim
from claims_processor.models.decision import Decision, DecisionStatus
from claims_processor.models.documents import DocType, ParsedDocument
from claims_processor.models.final import FinalDecision, StageError
from claims_processor.models.fraud import FraudReport
from claims_processor.observability import Tracer, get_tracer, set_tracer
from claims_processor.rules_engine import financials, rules
from claims_processor.rules_engine.evaluate import _all_line_items, _extract


class GraphState(TypedDict, total=False):
    claim_input: dict
    claim_id: str
    parsed_docs: list[ParsedDocument]
    claim: Optional[Claim]
    decision: Optional[Decision]
    fraud: Optional[FraudReport]
    final: Optional[FinalDecision]
    stage_errors: list[StageError]
    blocking: Optional[str]  # "NEEDS_REUPLOAD" | "REJECTED" | None


# ------------------------------- nodes -------------------------------

@traceable(run_type="chain", name="parse")
def parse_node(state: GraphState) -> dict:
    tracer = get_tracer()
    parsed, errors = [], []
    docs = state["claim_input"].get("documents", [])

    def _run():
        for d in docs:
            file_id = d.get("file_id", "F000")
            expected = DocType(d["actual_type"]) if d.get("actual_type") else None
            try:
                if "content" in d and expected is not None:
                    parsed.append(parse.parse_from_dict(file_id, expected, d["content"]))
                    if tracer:
                        tracer.event("doc_parsed", file_id=file_id, doc_type=expected.value,
                                     source="dict")
                elif "file_path" in d:
                    from pathlib import Path
                    p = Path(d["file_path"])
                    parsed.append(parse.parse_document(
                        file_bytes=p.read_bytes(), file_ext=p.suffix,
                        file_id=file_id, expected_type=expected,
                    ))
                    if tracer:
                        tracer.event("doc_parsed", file_id=file_id,
                                     doc_type=expected.value if expected else None,
                                     source=p.suffix.lstrip("."))
                else:
                    errors.append(StageError(stage="parse", file_id=file_id,
                                             error_type="InvalidInput",
                                             message="document has neither content nor file_path"))
                    if tracer:
                        tracer.event("doc_error", file_id=file_id, error_type="InvalidInput")
            except (WrongDocumentTypeError, UnreadableDocumentError, UnsupportedFileTypeError) as e:
                errors.append(StageError(stage="parse", file_id=file_id,
                                         error_type=type(e).__name__, message=str(e)))
                if tracer:
                    tracer.event("doc_error", file_id=file_id,
                                 error_type=type(e).__name__, message=str(e))
            except Exception as e:
                errors.append(StageError(stage="parse", file_id=file_id,
                                         error_type=type(e).__name__, message=str(e)))
                if tracer:
                    tracer.event("doc_error", file_id=file_id,
                                 error_type=type(e).__name__, message=str(e))

    if tracer:
        with tracer.span("parse", doc_count=len(docs)):
            _run()
            tracer.annotate(parsed=len(parsed), errors=len(errors))
    else:
        _run()

    blocking = None
    if any(e.error_type in ("WrongDocumentTypeError", "UnreadableDocumentError") for e in errors):
        blocking = "NEEDS_REUPLOAD"

    return {"parsed_docs": parsed, "stage_errors": errors, "blocking": blocking}


@traceable(run_type="chain", name="assemble")
def assemble_node(state: GraphState) -> dict:
    tracer = get_tracer()
    ci = state["claim_input"]

    def _run():
        return assemble_claim(
            claim_id=state["claim_id"],
            category=ci.get("claim_category") or ci.get("category"),
            parsed_docs=state["parsed_docs"],
        )

    if tracer:
        with tracer.span("assemble"):
            claim = _run()
            for iss in claim.issues:
                tracer.event("consistency_issue",
                             code=iss.code, severity=iss.severity, message=iss.message)
            if claim.missing_documents:
                tracer.event("missing_documents", missing=claim.missing_documents)
            tracer.annotate(
                issue_count=len(claim.issues),
                missing_docs=len(claim.missing_documents),
                has_errors=claim.has_errors(),
            )
    else:
        claim = _run()

    blocking = "REJECTED" if claim.has_errors() else None
    return {"claim": claim, "blocking": blocking}


def _run_rules(state: GraphState, tracer):
    ci = state["claim_input"]
    claim = state["claim"]

    category = claim.category
    diagnosis = _extract(claim.documents, DocType.PRESCRIPTION, "diagnosis") or ""
    modality = _extract(claim.documents, DocType.DIAGNOSTIC_REPORT, "modality") or ""
    hospital = _extract(claim.documents, DocType.HOSPITAL_BILL, "hospital_name") or ""
    tests_ordered = _extract(claim.documents, DocType.PRESCRIPTION, "tests_ordered") or []
    line_items = _all_line_items(claim.documents)
    pre_auth_text = " | ".join([modality, diagnosis, *tests_ordered,
                                *(getattr(li, "description", "") or "" for li in line_items)])

    member_join_date = ci.get("member_join_date")
    if not member_join_date and ci.get("member_id"):
        m = config.get_member(ci["member_id"])
        if m:
            member_join_date = m.get("join_date")

    claimed_amount = ci.get("claimed_amount")
    pre_auth_provided = ci.get("pre_auth_provided", False)
    submission_date = ci.get("submission_date") or ci.get("treatment_date")
    treatment_date = ci.get("treatment_date")

    # Exclusions run first so the per-claim-limit check can operate on
    # covered-only amount and so financials can itemise the bill.
    exclusion_rule = rules.check_exclusions(category, line_items, diagnosis)
    excluded_descs = exclusion_rule.evidence.get("excluded_descriptions", []) or []
    excluded_set = {d.lower() for d in excluded_descs}

    if line_items:
        covered_amount = sum(
            float(getattr(li, "amount", 0) or 0)
            for li in line_items
            if (getattr(li, "description", "") or "").lower() not in excluded_set
        )
    else:
        covered_amount = None

    results = [
        rules.check_category_covered(category),
        rules.check_minimum_amount(claimed_amount),
        rules.check_per_claim_limit(claimed_amount, category=category, covered_amount=covered_amount),
        rules.check_submission_deadline(treatment_date, submission_date),
    ]
    if member_join_date:
        results.append(rules.check_waiting_period(member_join_date, treatment_date, diagnosis))
    results.append(rules.check_pre_auth(category, claimed_amount, pre_auth_text, pre_auth_provided))
    results.append(exclusion_rule)
    network_rule = rules.check_network_hospital(hospital)
    results.append(network_rule)

    is_network = network_rule.evidence.get("in_network", False)
    payable = financials.compute_payable(
        claimed_amount, category, is_network=is_network,
        line_items=line_items, excluded_descriptions=excluded_descs,
    )

    if tracer:
        for r in results:
            tracer.event(
                "rule_eval",
                code=r.code, passed=r.passed, severity=r.severity, message=r.message,
            )
        tracer.event("payable_computed",
                     claimed=payable.claimed_amount,
                     after_exclusions=payable.after_exclusions,
                     after_network_discount=payable.after_network_discount,
                     after_sub_limit=payable.after_sub_limit,
                     copay=payable.copay_amount,
                     payable=payable.payable,
                     is_network=is_network,
                     excluded_items=[d for d in excluded_descs])

    has_error = any((not r.passed) and r.severity == "error" for r in results)
    has_partial = any((not r.passed) and r.severity == "partial" for r in results)
    has_warning = any((not r.passed) and r.severity == "warning" for r in results)

    if has_error:
        status = DecisionStatus.REJECTED
        reason = next(r.message for r in results if not r.passed and r.severity == "error")
    elif has_partial:
        status = DecisionStatus.PARTIAL
        reason = (
            f"{next(r.message for r in results if not r.passed and r.severity == 'partial')}. "
            f"Approved ₹{payable.payable}."
        )
    elif has_warning:
        status = DecisionStatus.NEEDS_REVIEW
        reason = next(r.message for r in results if not r.passed and r.severity == "warning")
    else:
        status = DecisionStatus.APPROVED
        reason = f"All rules passed. Payable ₹{payable.payable}."

    return Decision(
        claim_id=state["claim_id"], status=status, reason=reason,
        rules=results, payable=payable,
    )


@traceable(run_type="chain", name="rules")
def rules_node(state: GraphState) -> dict:
    tracer = get_tracer()
    if tracer:
        with tracer.span("rules"):
            decision = _run_rules(state, tracer)
            tracer.annotate(status=decision.status.value,
                            payable=decision.payable.payable)
    else:
        decision = _run_rules(state, None)
    return {"decision": decision}


@traceable(run_type="chain", name="fraud")
def fraud_node(state: GraphState) -> dict:
    tracer = get_tracer()
    ci = state["claim_input"]
    hospital = _extract(state["claim"].documents, DocType.HOSPITAL_BILL, "hospital_name") or ""

    def _run():
        return detect_fraud(
            member_id=ci.get("member_id"),
            claimed_amount=ci.get("claimed_amount"),
            treatment_date=ci.get("treatment_date"),
            claims_history=ci.get("claims_history"),
            provider=hospital,
        )

    if tracer:
        with tracer.span("fraud"):
            report = _run()
            for sig in report.signals:
                tracer.event("fraud_signal",
                             code=sig.code, severity=sig.severity,
                             weight=sig.weight, message=sig.message)
            tracer.annotate(score=report.score,
                            needs_manual_review=report.needs_manual_review)
    else:
        report = _run()
    return {"fraud": report}


def _build_final(state: GraphState) -> FinalDecision:
    blocking = state.get("blocking")
    stage_errors = state.get("stage_errors") or []
    claim = state.get("claim")
    decision = state.get("decision")
    fraud = state.get("fraud")
    notes = []

    if blocking == "NEEDS_REUPLOAD":
        err = next(e for e in stage_errors
                   if e.error_type in ("WrongDocumentTypeError", "UnreadableDocumentError"))
        return FinalDecision(
            claim_id=state["claim_id"],
            status=DecisionStatus.NEEDS_REUPLOAD,
            reason=err.message,
            confidence=0.0,
            stage_errors=stage_errors,
        )

    if blocking == "REJECTED":
        return FinalDecision(
            claim_id=state["claim_id"],
            status=DecisionStatus.REJECTED,
            reason="Claim has consistency errors; rejecting before policy rules.",
            confidence=0.5,
            claim=claim,
            stage_errors=stage_errors,
        )

    if decision and fraud:
        decision = decision.model_copy(update={"fraud": fraud})
        if decision.status == DecisionStatus.APPROVED and fraud.needs_manual_review:
            top = max(fraud.signals, key=lambda s: s.weight)
            decision = decision.model_copy(update={
                "status": DecisionStatus.MANUAL_REVIEW,
                "reason": f"Flagged for manual review: {top.message}",
            })

    confidence = 1.0
    if stage_errors:
        confidence -= 0.3 * len(stage_errors)
    if claim and claim.issues:
        confidence -= 0.1 * len(claim.issues)
    if state["claim_input"].get("simulate_component_failure"):
        stage_errors = list(stage_errors) + [StageError(
            stage="simulated", error_type="SimulatedFailure",
            message="component failure simulated",
        )]
        notes.append("Component failure simulated; manual review recommended")
        confidence -= 0.3
    confidence = max(0.0, min(1.0, confidence))

    return FinalDecision(
        claim_id=state["claim_id"],
        status=decision.status if decision else DecisionStatus.MANUAL_REVIEW,
        reason=decision.reason if decision else "No decision produced.",
        confidence=round(confidence, 2),
        claim=claim,
        decision=decision,
        stage_errors=stage_errors,
        notes=notes,
    )


@traceable(run_type="chain", name="finalize")
def finalize_node(state: GraphState) -> dict:
    tracer = get_tracer()
    if tracer:
        with tracer.span("finalize"):
            final = _build_final(state)
            tracer.annotate(status=final.status.value,
                            confidence=final.confidence,
                            stage_errors=len(final.stage_errors))
    else:
        final = _build_final(state)
    return {"final": final}


# ------------------------------- routers -------------------------------

def after_parse(state: GraphState) -> str:
    return "finalize" if state.get("blocking") == "NEEDS_REUPLOAD" else "assemble"


def after_assemble(state: GraphState) -> str:
    return "finalize" if state.get("blocking") == "REJECTED" else "rules"


# ------------------------------- graph -------------------------------

def build_graph():
    g = StateGraph(GraphState)
    g.add_node("parse", parse_node)
    g.add_node("assemble", assemble_node)
    g.add_node("rules", rules_node)
    g.add_node("fraud", fraud_node)
    g.add_node("finalize", finalize_node)

    g.set_entry_point("parse")
    g.add_conditional_edges("parse", after_parse,
                            {"assemble": "assemble", "finalize": "finalize"})
    g.add_conditional_edges("assemble", after_assemble,
                            {"rules": "rules", "finalize": "finalize"})
    g.add_edge("rules", "fraud")
    g.add_edge("fraud", "finalize")
    g.add_edge("finalize", END)

    return g.compile()


_graph = None


@traceable(run_type="chain", name="run_graph")
def run_graph(claim_input: dict, claim_id: str = "CLAIM",
              trace: bool = True) -> FinalDecision:
    """Run the claims pipeline. Set trace=False to skip tracing entirely.

    LangSmith tracing (optional, engineering-level) is attached via
    `@traceable` on this function and on each node. It activates when
    `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY` are set; otherwise the
    decorator is a no-op passthrough. Unrelated to the `Tracer` below,
    which is always on and surfaces to `FinalDecision.trace`.
    """
    global _graph
    if _graph is None:
        _graph = build_graph()

    tracer = Tracer(claim_id=claim_id) if trace else None
    prev = get_tracer()
    set_tracer(tracer)
    try:
        result = _graph.invoke(
            {"claim_input": claim_input, "claim_id": claim_id},
            config={
                "metadata": {
                    "claim_id": claim_id,
                    "category": claim_input.get("claim_category"),
                    "member_id": claim_input.get("member_id"),
                },
                "tags": ["plum-claims", f"claim:{claim_id}"],
                "run_name": f"claim.{claim_id}",
            },
        )
    finally:
        set_tracer(prev)

    final = result["final"]
    if tracer is not None:
        final = final.model_copy(update={"trace": tracer.finish()})
    return final
