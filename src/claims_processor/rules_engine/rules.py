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


def check_per_claim_limit(claimed_amount, policy=None, category=None, covered_amount=None):
    """TC008: amount over the effective per-claim cap -> REJECTED.

    Effective cap = max(coverage.per_claim_limit, category.sub_limit).
    Rationale: a category's explicit sub-limit (e.g. DENTAL=10000) signals
    intent to allow larger claims than the generic coverage cap; the
    generic cap is only binding when it exceeds the category sub-limit
    (e.g. CONSULTATION sub_limit=2000 < per_claim_limit=5000, so 5000 wins).

    When `covered_amount` is supplied (sum of line items after exclusions),
    the cap is evaluated against that rather than the gross claim — so a
    mixed bill where the covered portion fits but the gross doesn't can
    still PARTIAL-approve.
    """
    policy = policy or config.load_policy_terms()
    base_limit = policy["coverage"]["per_claim_limit"]
    sub_limit = None
    if category:
        cat = policy["opd_categories"].get(category.lower(), {})
        sub_limit = cat.get("sub_limit")

    effective = max(base_limit, sub_limit) if sub_limit is not None else base_limit
    check_amount = covered_amount if covered_amount is not None else claimed_amount
    ok = check_amount <= effective
    scope = "covered" if covered_amount is not None else "claimed"
    return RuleResult(
        code="PER_CLAIM_LIMIT",
        passed=ok,
        severity="error" if not ok else "info",
        message=(
            f"{scope.capitalize()} ₹{check_amount} exceeds effective per-claim limit ₹{effective}"
            if not ok else
            f"{scope.capitalize()} ₹{check_amount} within effective per-claim limit ₹{effective}"
        ),
        evidence={
            "per_claim_limit": base_limit,
            "category_sub_limit": sub_limit,
            "effective_limit": effective,
            "checked": check_amount,
            "scope": scope,
        },
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
    """TC006/TC012: detect excluded line items or diagnoses.

    Semantics:
      - No hits → passed=True (info).
      - Diagnosis matches general exclusion → passed=False, severity=error
        (whole treatment uncovered regardless of bill composition).
      - All line items excluded → passed=False, severity=error (nothing payable).
      - Some items excluded, others covered → passed=False, severity=partial.
        This is a non-blocking signal; `compute_payable` uses the evidence
        list to pay only the covered items, producing a PARTIAL decision.
    `evidence.excluded_descriptions` is consumed by the financial layer.
    """
    policy = policy or config.load_policy_terms()
    cat = _category_config(category, policy)
    # Category-specific lists are short phrases — match by full-phrase substring.
    cat_excluded = [x.lower() for x in cat.get("excluded_procedures", []) + cat.get("excluded_items", [])]
    # General lists are long phrases — break into keywords.
    general_phrases = policy["exclusions"].get("conditions", [])
    general_kw = [(p, _keywords(p)) for p in general_phrases]

    item_hits = []
    excluded_descs = []
    for item in line_items or []:
        desc_orig = getattr(item, "description", "") or ""
        desc = desc_orig.lower()
        matched = None
        for ex in cat_excluded:
            if ex and ex in desc:
                matched = ex
                break
        if matched is None:
            for phrase, kws in general_kw:
                if kws and any(k in desc for k in kws):
                    matched = phrase
                    break
        if matched:
            item_hits.append({"item": desc_orig, "matched": matched})
            excluded_descs.append(desc_orig)

    dx_hits = []
    dx = (diagnosis or "").lower()
    for phrase, kws in general_kw:
        if kws and any(k in dx for k in kws):
            dx_hits.append({"diagnosis": diagnosis, "matched": phrase})

    total_items = len(line_items or [])
    excluded_count = len(item_hits)

    if not item_hits and not dx_hits:
        return RuleResult(
            code="EXCLUSIONS", passed=True, severity="info",
            message="No excluded items",
            evidence={"hits": [], "excluded_descriptions": []},
        )

    if dx_hits:
        return RuleResult(
            code="EXCLUSIONS", passed=False, severity="error",
            message=f"Diagnosis matches policy exclusion: {dx_hits[0]['matched']}",
            evidence={"hits": item_hits + dx_hits, "excluded_descriptions": excluded_descs},
        )

    if total_items > 0 and excluded_count == total_items:
        return RuleResult(
            code="EXCLUSIONS", passed=False, severity="error",
            message=f"All {total_items} line item(s) are excluded",
            evidence={"hits": item_hits, "excluded_descriptions": excluded_descs},
        )

    return RuleResult(
        code="EXCLUSIONS", passed=False, severity="partial",
        message=f"{excluded_count} of {total_items} line item(s) excluded; remainder payable",
        evidence={"hits": item_hits, "excluded_descriptions": excluded_descs},
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
