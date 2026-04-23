"""Policy rule checks.

Each function takes a small set of inputs and returns a RuleResult.
Uses policy_terms.json via the config loader.
"""

from datetime import date, datetime, timedelta

from claims_processor.core import config
from claims_processor.models.decision import RuleResult
from claims_processor.models.documents import DocType


def _category_config(category, policy=None):
    policy = policy or config.load_policy_terms()
    return policy["opd_categories"].get(category.lower(), {})


def _parse_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def check_category_covered(category, policy=None):
    cat = _category_config(category, policy)
    covered = bool(cat.get("covered", False))
    return RuleResult(
        code="CATEGORY_COVERED",
        passed=covered,
        severity="error" if not covered else "info",
        message=f"Category {category} covered={covered}",
    )


def check_minimum_amount(claimed_amount, policy=None):
    policy = policy or config.load_policy_terms()
    minimum = policy["submission_rules"]["minimum_claim_amount"]
    ok = claimed_amount >= minimum
    return RuleResult(
        code="MINIMUM_AMOUNT",
        passed=ok,
        severity="error" if not ok else "info",
        message=f"Claim {claimed_amount} vs minimum {minimum}",
        evidence={"minimum": minimum, "claimed": claimed_amount},
    )


def check_per_claim_limit(claimed_amount, policy=None):
    """TC008: if amount > per_claim_limit we flag for review but don't reject."""
    policy = policy or config.load_policy_terms()
    limit = policy["coverage"]["per_claim_limit"]
    ok = claimed_amount <= limit
    return RuleResult(
        code="PER_CLAIM_LIMIT",
        passed=ok,
        severity="warning" if not ok else "info",
        message=f"Claim {claimed_amount} vs per-claim limit {limit}",
        evidence={"limit": limit, "claimed": claimed_amount},
    )


def check_submission_deadline(treatment_date, submission_date=None, policy=None):
    policy = policy or config.load_policy_terms()
    days = policy["submission_rules"]["deadline_days_from_treatment"]
    td = _parse_date(treatment_date) if isinstance(treatment_date, str) else treatment_date
    sd = submission_date or date.today()
    if isinstance(sd, str):
        sd = _parse_date(sd) or date.today()
    if not td:
        return RuleResult(code="SUBMISSION_DEADLINE", passed=True, severity="warning",
                          message="Treatment date unknown; cannot verify deadline")
    ok = (sd - td) <= timedelta(days=days)
    return RuleResult(
        code="SUBMISSION_DEADLINE",
        passed=ok,
        severity="error" if not ok else "info",
        message=f"Submitted {(sd - td).days} days after treatment (limit {days})",
        evidence={"treatment_date": str(td), "submission_date": str(sd), "limit_days": days},
    )


def check_waiting_period(member_join_date, treatment_date, diagnosis, policy=None):
    """TC005: e.g. diabetes has 90-day waiting from join date."""
    policy = policy or config.load_policy_terms()
    waiting = policy["waiting_periods"]
    jd = _parse_date(member_join_date)
    td = _parse_date(treatment_date) if isinstance(treatment_date, str) else treatment_date
    if not jd or not td:
        return RuleResult(code="WAITING_PERIOD", passed=True, severity="warning",
                          message="Dates missing; cannot verify waiting period")

    # Generic initial waiting period
    if (td - jd).days < waiting["initial_waiting_period_days"]:
        return RuleResult(
            code="WAITING_PERIOD", passed=False, severity="error",
            message=f"Initial waiting period not met "
                    f"({(td - jd).days}d < {waiting['initial_waiting_period_days']}d)",
            evidence={"join_date": str(jd), "treatment_date": str(td)},
        )

    # Condition-specific (word-boundary match to avoid "hernia" matching "herniation")
    import re
    dx = (diagnosis or "").lower()
    for cond, days in waiting.get("specific_conditions", {}).items():
        pattern = r"\b" + re.escape(cond.replace("_", " ")) + r"\b"
        if re.search(pattern, dx):
            if (td - jd).days < days:
                return RuleResult(
                    code="WAITING_PERIOD", passed=False, severity="error",
                    message=f"{cond} waiting period not met "
                            f"({(td - jd).days}d < {days}d)",
                    evidence={"condition": cond, "required_days": days,
                              "actual_days": (td - jd).days},
                )

    return RuleResult(code="WAITING_PERIOD", passed=True, message="Waiting period satisfied")


def check_pre_auth(category, claimed_amount, diagnosis_or_modality, pre_auth_provided, policy=None):
    """TC007: MRI/CT above threshold require pre-authorisation."""
    cat = _category_config(category, policy)
    threshold = cat.get("pre_auth_threshold")
    high_value = [x.lower() for x in cat.get("high_value_tests_requiring_pre_auth", [])]
    needs = False
    reason = ""
    text = (diagnosis_or_modality or "").lower()
    if threshold and claimed_amount > threshold and any(h in text for h in high_value):
        needs = True
        reason = f"{diagnosis_or_modality} above ₹{threshold}"

    ok = not needs or pre_auth_provided
    return RuleResult(
        code="PRE_AUTH",
        passed=ok,
        severity="error" if not ok else "info",
        message=f"Pre-auth required: {needs} (provided: {pre_auth_provided})" + (f" — {reason}" if reason else ""),
        evidence={"threshold": threshold, "high_value_list": high_value,
                  "claimed": claimed_amount, "pre_auth_provided": pre_auth_provided},
    )


_STOPWORDS = {"and", "or", "of", "the", "non", "medically", "necessary",
              "programs", "treatment", "treatments", "assisted", "surgery"}


def _keywords(phrase):
    """Pull significant tokens out of an exclusion phrase for substring matching."""
    toks = [t.strip("()[],.").lower() for t in phrase.split()]
    return [t for t in toks if t and t not in _STOPWORDS and len(t) > 3]


def check_exclusions(category, line_items, diagnosis, policy=None):
    """TC006/TC012: reject if any line item or the diagnosis matches an
    excluded procedure (category-specific) or exclusion keyword (general).
    """
    policy = policy or config.load_policy_terms()
    cat = _category_config(category, policy)
    # Category-specific lists are short phrases — match by full-phrase substring.
    cat_excluded = [x.lower() for x in cat.get("excluded_procedures", []) + cat.get("excluded_items", [])]
    # General lists are long phrases — break into keywords.
    general_phrases = policy["exclusions"].get("conditions", [])
    general_kw = [(p, _keywords(p)) for p in general_phrases]

    hits = []
    for item in line_items or []:
        desc = (getattr(item, "description", "") or "").lower()
        for ex in cat_excluded:
            if ex and ex in desc:
                hits.append({"item": item.description, "matched": ex})
                break
        else:
            for phrase, kws in general_kw:
                if kws and any(k in desc for k in kws):
                    hits.append({"item": item.description, "matched": phrase})
                    break

    dx = (diagnosis or "").lower()
    for phrase, kws in general_kw:
        if kws and any(k in dx for k in kws):
            hits.append({"diagnosis": diagnosis, "matched": phrase})

    ok = not hits
    return RuleResult(
        code="EXCLUSIONS",
        passed=ok,
        severity="error" if not ok else "info",
        message=f"{len(hits)} excluded item(s) found" if hits else "No excluded items",
        evidence={"hits": hits},
    )


def check_network_hospital(hospital_name, policy=None):
    policy = policy or config.load_policy_terms()
    network = [n.lower() for n in policy.get("network_hospitals", [])]
    name = (hospital_name or "").lower()
    in_network = any(n in name or name in n for n in network)
    return RuleResult(
        code="NETWORK_HOSPITAL",
        passed=True,  # never blocks — just informs the financial calc
        message=f"{'In-network' if in_network else 'Out-of-network'}: {hospital_name}",
        evidence={"in_network": in_network},
    )
