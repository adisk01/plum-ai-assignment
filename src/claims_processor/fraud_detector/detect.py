"""Public entry point for fraud detection.

    report = detect_fraud(
        member_id="EMP008",
        claimed_amount=4800,
        treatment_date="2024-10-30",
        claims_history=[...],
        provider="City Clinic",
    )
"""

from claims_processor.core import config
from claims_processor.fraud_detector import signals
from claims_processor.models.fraud import FraudReport


def detect_fraud(member_id, claimed_amount, treatment_date,
                 claims_history=None, provider=None, policy=None):
    policy = policy or config.load_policy_terms()

    results = [
        signals.check_same_day_claims(member_id, treatment_date, claims_history, policy),
        signals.check_monthly_claims(member_id, treatment_date, claims_history, policy),
        signals.check_high_value(claimed_amount, policy),
        signals.check_duplicate_claim(claimed_amount, treatment_date, claims_history, provider),
    ]

    score = min(1.0, sum(s.weight for s in results))
    threshold = policy["fraud_thresholds"]["fraud_score_manual_review_threshold"]
    has_error = any(s.severity == "error" for s in results)
    needs_review = has_error or score >= threshold

    return FraudReport(
        score=round(score, 2),
        needs_manual_review=needs_review,
        signals=results,
    )
