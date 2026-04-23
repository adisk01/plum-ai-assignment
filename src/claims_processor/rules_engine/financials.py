"""Financial computation for a claim.

Order (matters for TC010):
  1. Network discount (if in-network)
  2. Apply category sub-limit
  3. Copay
"""

from claims_processor.core import config
from claims_processor.models.decision import PayableBreakdown


def compute_payable(claimed_amount, category, is_network=False, policy=None):
    policy = policy or config.load_policy_terms()
    cat = policy["opd_categories"].get(category.lower(), {})
    notes = []

    amount = float(claimed_amount)

    # 1. Network discount
    discount_pct = cat.get("network_discount_percent", 0) if is_network else 0
    after_discount = round(amount * (1 - discount_pct / 100), 2)
    if discount_pct:
        notes.append(f"Applied {discount_pct}% network discount")

    # 2. Sub-limit
    sub_limit = cat.get("sub_limit")
    after_sub = after_discount
    if sub_limit is not None and after_discount > sub_limit:
        after_sub = float(sub_limit)
        notes.append(f"Capped at category sub-limit ₹{sub_limit}")

    # 3. Copay
    copay_pct = cat.get("copay_percent", 0)
    copay_amt = round(after_sub * copay_pct / 100, 2)
    payable = round(after_sub - copay_amt, 2)
    if copay_pct:
        notes.append(f"Applied {copay_pct}% copay (₹{copay_amt})")

    return PayableBreakdown(
        claimed_amount=amount,
        after_network_discount=after_discount,
        after_sub_limit=after_sub,
        copay_amount=copay_amt,
        payable=payable,
        notes=notes,
    )
