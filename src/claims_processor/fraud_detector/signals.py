"""Fraud signal checks.

Each function receives inputs and returns a FraudSignal.
Weights are used to compute an overall score; any "error" signal also
flags the claim for manual review regardless of score.
"""

from datetime import date, datetime, timedelta

from claims_processor.core import config
from claims_processor.models.fraud import FraudSignal


def _parse(s):
    if isinstance(s, date):
        return s
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def check_same_day_claims(member_id, treatment_date, claims_history, policy=None):
    """TC009: more than `same_day_claims_limit` claims on the same day -> error."""
    policy = policy or config.load_policy_terms()
    limit = policy["fraud_thresholds"]["same_day_claims_limit"]
    td = _parse(treatment_date)
    same_day = [c for c in (claims_history or []) if _parse(c.get("date")) == td]
    count = len(same_day) + 1  # include the current claim
    over = count > limit
    return FraudSignal(
        code="SAME_DAY_CLAIMS",
        severity="error" if over else "info",
        weight=0.6 if over else 0.0,
        message=f"{count} claims on {td} (limit {limit})" if over
                else f"Same-day claim count ok ({count}/{limit})",
        evidence={"count": count, "limit": limit, "same_day": same_day},
    )


def check_monthly_claims(member_id, treatment_date, claims_history, policy=None):
    policy = policy or config.load_policy_terms()
    limit = policy["fraud_thresholds"]["monthly_claims_limit"]
    td = _parse(treatment_date)
    if not td:
        return FraudSignal(code="MONTHLY_CLAIMS", message="treatment date unknown")
    month_start = td.replace(day=1)
    in_month = [c for c in (claims_history or [])
                if (d := _parse(c.get("date"))) and d >= month_start and d <= td]
    count = len(in_month) + 1
    over = count > limit
    return FraudSignal(
        code="MONTHLY_CLAIMS",
        severity="warning" if over else "info",
        weight=0.3 if over else 0.0,
        message=f"{count} claims in {td.strftime('%b %Y')} (limit {limit})" if over
                else f"Monthly claim count ok ({count}/{limit})",
        evidence={"count": count, "limit": limit},
    )


def check_high_value(claimed_amount, policy=None):
    policy = policy or config.load_policy_terms()
    threshold = policy["fraud_thresholds"]["high_value_claim_threshold"]
    over = claimed_amount > threshold
    return FraudSignal(
        code="HIGH_VALUE_AUTO_REVIEW",
        severity="warning" if over else "info",
        weight=0.4 if over else 0.0,
        message=f"Claim ₹{claimed_amount} > high-value threshold ₹{threshold}" if over
                else "Claim within normal value range",
        evidence={"claimed": claimed_amount, "threshold": threshold},
    )


def check_duplicate_claim(claimed_amount, treatment_date, claims_history, provider=None):
    """Same date + same amount (+ same provider if known) in history = likely duplicate."""
    td = _parse(treatment_date)
    hits = []
    for c in claims_history or []:
        if _parse(c.get("date")) == td and abs(c.get("amount", 0) - claimed_amount) < 1:
            if provider and c.get("provider") and provider.lower() != c["provider"].lower():
                continue
            hits.append(c)
    dup = bool(hits)
    return FraudSignal(
        code="DUPLICATE_CLAIM",
        severity="error" if dup else "info",
        weight=0.7 if dup else 0.0,
        message=f"{len(hits)} possible duplicate(s) found" if dup else "No duplicates",
        evidence={"matches": hits},
    )
