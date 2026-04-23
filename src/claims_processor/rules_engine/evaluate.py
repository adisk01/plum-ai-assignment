"""Public entry point for the rules engine.

Usage:
    decision = evaluate_claim(
        claim=claim,
        claimed_amount=5000,
        treatment_date="2024-11-01",
        member_join_date="2024-04-01",
        pre_auth_provided=False,
        submission_date=date.today(),
    )
"""

from claims_processor.fraud_detector.detect import detect_fraud
from claims_processor.models.decision import Decision, DecisionStatus
from claims_processor.models.documents import DocType
from claims_processor.rules_engine import financials, rules


def _extract(docs, dtype, *fields):
    for d in docs:
        if d.doc_type == dtype and d.extracted:
            for f in fields:
                v = getattr(d.extracted, f, None)
                if v:
                    return v
    return None


def _all_line_items(docs):
    items = []
    for d in docs:
        body = d.extracted
        if body and hasattr(body, "line_items"):
            items.extend(body.line_items or [])
    return items


def evaluate_claim(
    claim,
    claimed_amount,
    treatment_date,
    member_join_date=None,
    pre_auth_provided=False,
    submission_date=None,
    member_id=None,
    claims_history=None,
):
    results = []

    # Blocking claim-assembler errors short-circuit the whole thing
    if claim.has_errors():
        return Decision(
            claim_id=claim.claim_id,
            status=DecisionStatus.REJECTED,
            reason="Claim has consistency errors; rejecting before policy rules.",
            rules=[],
            payable=None,
        )

    category = claim.category
    diagnosis = _extract(claim.documents, DocType.PRESCRIPTION, "diagnosis") or ""
    modality = _extract(claim.documents, DocType.DIAGNOSTIC_REPORT, "modality") or ""
    hospital = _extract(claim.documents, DocType.HOSPITAL_BILL, "hospital_name") or ""

    results.append(rules.check_category_covered(category))
    results.append(rules.check_minimum_amount(claimed_amount))
    results.append(rules.check_per_claim_limit(claimed_amount))
    results.append(rules.check_submission_deadline(treatment_date, submission_date))
    if member_join_date:
        results.append(rules.check_waiting_period(member_join_date, treatment_date, diagnosis))
    results.append(rules.check_pre_auth(category, claimed_amount, modality or diagnosis, pre_auth_provided))
    results.append(rules.check_exclusions(category, _all_line_items(claim.documents), diagnosis))
    network_rule = rules.check_network_hospital(hospital)
    results.append(network_rule)

    has_error = any((not r.passed) and r.severity == "error" for r in results)
    has_warning = any((not r.passed) and r.severity == "warning" for r in results)

    is_network = network_rule.evidence.get("in_network", False)
    payable = financials.compute_payable(claimed_amount, category, is_network=is_network)

    fraud = detect_fraud(
        member_id=member_id,
        claimed_amount=claimed_amount,
        treatment_date=treatment_date,
        claims_history=claims_history,
        provider=hospital,
    )

    if has_error:
        status = DecisionStatus.REJECTED
        reason = next(r.message for r in results if not r.passed and r.severity == "error")
    elif fraud.needs_manual_review:
        status = DecisionStatus.MANUAL_REVIEW
        top = max(fraud.signals, key=lambda s: s.weight)
        reason = f"Flagged for manual review: {top.message}"
    elif has_warning:
        status = DecisionStatus.NEEDS_REVIEW
        reason = next(r.message for r in results if not r.passed and r.severity == "warning")
    else:
        status = DecisionStatus.APPROVED
        reason = f"All rules passed. Payable ₹{payable.payable}."

    return Decision(
        claim_id=claim.claim_id,
        status=status,
        reason=reason,
        rules=results,
        payable=payable,
        fraud=fraud,
    )
