"""Financial computation for a claim.

Order (matters for TC010):
  1. Filter excluded line items (if any line-item info is provided)
  2. Network discount (if in-network)
  3. Apply category sub-limit
  4. Copay

If `line_items` + `excluded_descriptions` are supplied, the breakdown
itemises each one (covered=True/False + reason) so the ops reviewer can
see exactly which items were paid and which were declined. The basic
signature `compute_payable(amount, category, is_network)` is preserved
for call sites that don't have per-line information.
"""

from claims_processor.core import config
from claims_processor.models.decision import LineItemDecision, PayableBreakdown


def compute_payable(
    claimed_amount,
    category,
    is_network=False,
    line_items=None,
    excluded_descriptions=None,
    policy=None,
):
    """Compute payable amount + per-line-item breakdown.

    Args:
        claimed_amount: gross claim amount (used when no line_items given).
        category: claim category key (e.g. "DENTAL").
        is_network: whether treatment was at a network hospital.
        line_items: iterable of objects/dicts with `description` + `amount`.
                    When provided, per-item filtering is performed.
        excluded_descriptions: set/list of line-item descriptions (lowercased)
                    that were flagged as excluded by the rules engine.
        policy: optional preloaded policy dict.
    """
    policy = policy or config.load_policy_terms()
    cat = policy["opd_categories"].get(category.lower(), {})
    notes = []

    excluded_set = {d.lower() for d in (excluded_descriptions or [])}
    item_decisions: list[LineItemDecision] = []

    # 1. Filter excluded line items (if any provided)
    if line_items:
        covered_sum = 0.0
        gross_sum = 0.0
        for li in line_items:
            desc = getattr(li, "description", None) or (li.get("description") if isinstance(li, dict) else "") or ""
            amt = float(getattr(li, "amount", None) or (li.get("amount") if isinstance(li, dict) else 0) or 0)
            gross_sum += amt
            if desc.lower() in excluded_set:
                item_decisions.append(LineItemDecision(
                    description=desc, amount=amt, covered=False,
                    reason="Excluded under policy",
                ))
            else:
                covered_sum += amt
                item_decisions.append(LineItemDecision(
                    description=desc, amount=amt, covered=True,
                ))
        amount = covered_sum
        gross = gross_sum or float(claimed_amount or 0)
        after_exclusions = covered_sum
        if item_decisions and any(not d.covered for d in item_decisions):
            dropped = sum(d.amount for d in item_decisions if not d.covered)
            notes.append(f"Excluded ₹{dropped:.0f} across {sum(1 for d in item_decisions if not d.covered)} item(s)")
    else:
        gross = float(claimed_amount or 0)
        amount = gross
        after_exclusions = None

    # 2. Network discount
    discount_pct = cat.get("network_discount_percent", 0) if is_network else 0
    after_discount = round(amount * (1 - discount_pct / 100), 2)
    if discount_pct:
        notes.append(f"Applied {discount_pct}% network discount")

    # 3. Sub-limit
    sub_limit = cat.get("sub_limit")
    after_sub = after_discount
    if sub_limit is not None and after_discount > sub_limit:
        after_sub = float(sub_limit)
        notes.append(f"Capped at category sub-limit ₹{sub_limit}")

    # 4. Copay
    copay_pct = cat.get("copay_percent", 0)
    copay_amt = round(after_sub * copay_pct / 100, 2)
    payable = round(after_sub - copay_amt, 2)
    if copay_pct:
        notes.append(f"Applied {copay_pct}% copay (₹{copay_amt})")

    return PayableBreakdown(
        claimed_amount=gross,
        after_exclusions=after_exclusions,
        after_network_discount=after_discount,
        after_sub_limit=after_sub,
        copay_amount=copay_amt,
        payable=payable,
        line_items=item_decisions,
        notes=notes,
    )
