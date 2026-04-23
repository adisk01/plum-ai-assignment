# Eval Report

**12/12** cases match expected outcomes.

| case | expected | actual | match | payable | confidence | trace ms | reason |
|------|----------|--------|-------|---------|------------|----------|--------|
| TC001 | - | REJECTED | ✓ | - | 0.5 | 1.4 | Claim has consistency errors; rejecting before policy rules. |
| TC002 | - | REJECTED | ✓ | - | 0.5 | 0.7 | Claim has consistency errors; rejecting before policy rules. |
| TC003 | - | REJECTED | ✓ | - | 0.5 | 0.6 | Claim has consistency errors; rejecting before policy rules. |
| TC004 | APPROVED | APPROVED | ✓ | 1350.0 | 1.0 | 2.1 | All rules passed. Payable ₹1350.0. |
| TC005 | REJECTED | REJECTED | ✓ | 1800.0 | 1.0 | 3.0 | diabetes waiting period not met (44d < 90d) |
| TC006 | PARTIAL | PARTIAL | ✓ | 8000.0 | 1.0 | 1.5 | 1 of 2 line item(s) excluded; remainder payable. Approved ₹8000.0. |
| TC007 | REJECTED | REJECTED | ✓ | 10000.0 | 1.0 | 1.4 | Covered ₹15000.0 exceeds effective per-claim limit ₹10000 |
| TC008 | REJECTED | REJECTED | ✓ | 1800.0 | 1.0 | 1.4 | Covered ₹7500.0 exceeds effective per-claim limit ₹5000 |
| TC009 | MANUAL_REVIEW | MANUAL_REVIEW | ✓ | 1800.0 | 1.0 | 1.4 | Flagged for manual review: 4 claims on 2024-10-30 (limit 2) |
| TC010 | APPROVED | APPROVED | ✓ | 1800.0 | 1.0 | 1.4 | All rules passed. Payable ₹1800.0. |
| TC011 | APPROVED | APPROVED | ✓ | 4000.0 | 0.7 | 1.4 | All rules passed. Payable ₹4000.0. |
| TC012 | REJECTED | REJECTED | ✓ | 1800.0 | 1.0 | 1.4 | Diagnosis matches policy exclusion: Obesity and weight loss programs |

## Per-case detail

### TC001 — Member submits two prescriptions for a consultation claim that requires a prescription and a hospital bill.

- **Expected:** -
- **Actual:** REJECTED (match: True)
- **Reason:** Claim has consistency errors; rejecting before policy rules.
- **Confidence:** 0.5
- **Consistency issues:**
  - `MISSING_REQUIRED_DOCUMENT` (error) — Required document 'PRESCRIPTION' missing for category CONSULTATION
  - `MISSING_REQUIRED_DOCUMENT` (error) — Required document 'HOSPITAL_BILL' missing for category CONSULTATION
- **Missing docs:** ['PRESCRIPTION', 'HOSPITAL_BILL']
- **Stage errors:**
  - `parse` InvalidInput: document has neither content nor file_path
  - `parse` InvalidInput: document has neither content nor file_path
- **Trace spans:**
  - `parse` — ok — 0.02 ms (2 events)
  - `assemble` — ok — 0.11 ms (3 events)
  - `finalize` — ok — 0.01 ms (0 events)

### TC002 — Member uploads a valid prescription but a blurry, unreadable photo of their pharmacy bill.

- **Expected:** -
- **Actual:** REJECTED (match: True)
- **Reason:** Claim has consistency errors; rejecting before policy rules.
- **Confidence:** 0.5
- **Consistency issues:**
  - `MISSING_REQUIRED_DOCUMENT` (error) — Required document 'PRESCRIPTION' missing for category PHARMACY
  - `MISSING_REQUIRED_DOCUMENT` (error) — Required document 'PHARMACY_BILL' missing for category PHARMACY
- **Missing docs:** ['PRESCRIPTION', 'PHARMACY_BILL']
- **Stage errors:**
  - `parse` InvalidInput: document has neither content nor file_path
  - `parse` InvalidInput: document has neither content nor file_path
- **Trace spans:**
  - `parse` — ok — 0.01 ms (2 events)
  - `assemble` — ok — 0.09 ms (3 events)
  - `finalize` — ok — 0.01 ms (0 events)

### TC003 — The prescription is for Rajesh Kumar but the hospital bill is for a different patient, Arjun Mehta.

- **Expected:** -
- **Actual:** REJECTED (match: True)
- **Reason:** Claim has consistency errors; rejecting before policy rules.
- **Confidence:** 0.5
- **Consistency issues:**
  - `MISSING_REQUIRED_DOCUMENT` (error) — Required document 'PRESCRIPTION' missing for category CONSULTATION
  - `MISSING_REQUIRED_DOCUMENT` (error) — Required document 'HOSPITAL_BILL' missing for category CONSULTATION
- **Missing docs:** ['PRESCRIPTION', 'HOSPITAL_BILL']
- **Stage errors:**
  - `parse` InvalidInput: document has neither content nor file_path
  - `parse` InvalidInput: document has neither content nor file_path
- **Trace spans:**
  - `parse` — ok — 0.01 ms (2 events)
  - `assemble` — ok — 0.07 ms (3 events)
  - `finalize` — ok — 0.0 ms (0 events)

### TC004 — Complete, valid consultation claim with correct documents, valid member, covered treatment, within all limits.

- **Expected:** APPROVED
- **Actual:** APPROVED (match: True)
- **Reason:** All rules passed. Payable ₹1350.0.
- **Confidence:** 1.0
- **Payable:** ₹1350.0
- **Fraud score:** 0.0 (manual review: False)
  - `SAME_DAY_CLAIMS` (info, w=0.0) — Same-day claim count ok (1/2)
  - `MONTHLY_CLAIMS` (info, w=0.0) — Monthly claim count ok (1/6)
  - `HIGH_VALUE_AUTO_REVIEW` (info, w=0.0) — Claim within normal value range
  - `DUPLICATE_CLAIM` (info, w=0.0) — No duplicates
- **Trace spans:**
  - `parse` — ok — 0.04 ms (2 events)
  - `assemble` — ok — 0.07 ms (0 events)
  - `rules` — ok — 1.14 ms (9 events)
  - `fraud` — ok — 0.09 ms (4 events)
  - `finalize` — ok — 0.01 ms (0 events)

### TC005 — Member joined 2024-09-01. Claims for diabetes treatment on 2024-10-15, which is within the 90-day waiting period for diabetes.

- **Expected:** REJECTED
- **Actual:** REJECTED (match: True)
- **Reason:** diabetes waiting period not met (44d < 90d)
- **Confidence:** 1.0
- **Payable:** ₹1800.0
- **Failed rules:**
  - `WAITING_PERIOD` (error) — diabetes waiting period not met (44d < 90d)
- **Fraud score:** 0.0 (manual review: False)
  - `SAME_DAY_CLAIMS` (info, w=0.0) — Same-day claim count ok (1/2)
  - `MONTHLY_CLAIMS` (info, w=0.0) — Monthly claim count ok (1/6)
  - `HIGH_VALUE_AUTO_REVIEW` (info, w=0.0) — Claim within normal value range
  - `DUPLICATE_CLAIM` (info, w=0.0) — No duplicates
- **Trace spans:**
  - `parse` — ok — 0.02 ms (2 events)
  - `assemble` — ok — 0.09 ms (0 events)
  - `rules` — ok — 0.57 ms (9 events)
  - `fraud` — ok — 0.08 ms (4 events)
  - `finalize` — ok — 0.01 ms (0 events)

### TC006 — Bill includes root canal treatment (covered) and teeth whitening (cosmetic, excluded). System must approve only the covered procedure.

- **Expected:** PARTIAL
- **Actual:** PARTIAL (match: True)
- **Reason:** 1 of 2 line item(s) excluded; remainder payable. Approved ₹8000.0.
- **Confidence:** 1.0
- **Payable:** ₹8000.0
- **Failed rules:**
  - `EXCLUSIONS` (partial) — 1 of 2 line item(s) excluded; remainder payable
- **Fraud score:** 0.0 (manual review: False)
  - `SAME_DAY_CLAIMS` (info, w=0.0) — Same-day claim count ok (1/2)
  - `MONTHLY_CLAIMS` (info, w=0.0) — Monthly claim count ok (1/6)
  - `HIGH_VALUE_AUTO_REVIEW` (info, w=0.0) — Claim within normal value range
  - `DUPLICATE_CLAIM` (info, w=0.0) — No duplicates
- **Trace spans:**
  - `parse` — ok — 0.01 ms (1 events)
  - `assemble` — ok — 0.06 ms (0 events)
  - `rules` — ok — 0.55 ms (9 events)
  - `fraud` — ok — 0.08 ms (4 events)
  - `finalize` — ok — 0.01 ms (0 events)

### TC007 — MRI scan costing ₹15,000 submitted without pre-authorization. Policy requires pre-auth for MRI above ₹10,000.

- **Expected:** REJECTED
- **Actual:** REJECTED (match: True)
- **Reason:** Covered ₹15000.0 exceeds effective per-claim limit ₹10000
- **Confidence:** 1.0
- **Payable:** ₹10000.0
- **Failed rules:**
  - `PER_CLAIM_LIMIT` (error) — Covered ₹15000.0 exceeds effective per-claim limit ₹10000
  - `PRE_AUTH` (error) — Pre-auth required: True (provided: False) —  | Suspected Lumbar Disc Herniation | MRI Lumbar Spine | MRI Lumbar Spine above ₹10000
- **Fraud score:** 0.0 (manual review: False)
  - `SAME_DAY_CLAIMS` (info, w=0.0) — Same-day claim count ok (1/2)
  - `MONTHLY_CLAIMS` (info, w=0.0) — Monthly claim count ok (1/6)
  - `HIGH_VALUE_AUTO_REVIEW` (info, w=0.0) — Claim within normal value range
  - `DUPLICATE_CLAIM` (info, w=0.0) — No duplicates
- **Trace spans:**
  - `parse` — ok — 0.02 ms (3 events)
  - `assemble` — ok — 0.06 ms (0 events)
  - `rules` — ok — 0.53 ms (9 events)
  - `fraud` — ok — 0.08 ms (4 events)
  - `finalize` — ok — 0.01 ms (0 events)

### TC008 — Claimed amount of ₹7,500 exceeds the per-claim limit of ₹5,000.

- **Expected:** REJECTED
- **Actual:** REJECTED (match: True)
- **Reason:** Covered ₹7500.0 exceeds effective per-claim limit ₹5000
- **Confidence:** 1.0
- **Payable:** ₹1800.0
- **Failed rules:**
  - `PER_CLAIM_LIMIT` (error) — Covered ₹7500.0 exceeds effective per-claim limit ₹5000
- **Fraud score:** 0.0 (manual review: False)
  - `SAME_DAY_CLAIMS` (info, w=0.0) — Same-day claim count ok (1/2)
  - `MONTHLY_CLAIMS` (info, w=0.0) — Monthly claim count ok (1/6)
  - `HIGH_VALUE_AUTO_REVIEW` (info, w=0.0) — Claim within normal value range
  - `DUPLICATE_CLAIM` (info, w=0.0) — No duplicates
- **Trace spans:**
  - `parse` — ok — 0.02 ms (2 events)
  - `assemble` — ok — 0.06 ms (0 events)
  - `rules` — ok — 0.53 ms (9 events)
  - `fraud` — ok — 0.07 ms (4 events)
  - `finalize` — ok — 0.01 ms (0 events)

### TC009 — Member EMP008 has already submitted 3 claims today before this one arrives. This is the 4th claim from the same member on the same day.

- **Expected:** MANUAL_REVIEW
- **Actual:** MANUAL_REVIEW (match: True)
- **Reason:** Flagged for manual review: 4 claims on 2024-10-30 (limit 2)
- **Confidence:** 1.0
- **Payable:** ₹1800.0
- **Fraud score:** 0.6 (manual review: True)
  - `SAME_DAY_CLAIMS` (error, w=0.6) — 4 claims on 2024-10-30 (limit 2)
  - `MONTHLY_CLAIMS` (info, w=0.0) — Monthly claim count ok (4/6)
  - `HIGH_VALUE_AUTO_REVIEW` (info, w=0.0) — Claim within normal value range
  - `DUPLICATE_CLAIM` (info, w=0.0) — No duplicates
- **Trace spans:**
  - `parse` — ok — 0.01 ms (2 events)
  - `assemble` — ok — 0.06 ms (0 events)
  - `rules` — ok — 0.5 ms (9 events)
  - `fraud` — ok — 0.1 ms (4 events)
  - `finalize` — ok — 0.01 ms (0 events)

### TC010 — Valid claim at Apollo Hospitals, a network hospital. Network discount must be applied before co-pay.

- **Expected:** APPROVED
- **Actual:** APPROVED (match: True)
- **Reason:** All rules passed. Payable ₹1800.0.
- **Confidence:** 1.0
- **Payable:** ₹1800.0
- **Fraud score:** 0.0 (manual review: False)
  - `SAME_DAY_CLAIMS` (info, w=0.0) — Same-day claim count ok (1/2)
  - `MONTHLY_CLAIMS` (info, w=0.0) — Monthly claim count ok (1/6)
  - `HIGH_VALUE_AUTO_REVIEW` (info, w=0.0) — Claim within normal value range
  - `DUPLICATE_CLAIM` (info, w=0.0) — No duplicates
- **Trace spans:**
  - `parse` — ok — 0.02 ms (2 events)
  - `assemble` — ok — 0.06 ms (0 events)
  - `rules` — ok — 0.55 ms (9 events)
  - `fraud` — ok — 0.08 ms (4 events)
  - `finalize` — ok — 0.01 ms (0 events)

### TC011 — One component of your system fails mid-processing (simulate with the flag below). The overall pipeline must continue, produce a decision, and make the failure visible in the output with an appropriately reduced confidence score.

- **Expected:** APPROVED
- **Actual:** APPROVED (match: True)
- **Reason:** All rules passed. Payable ₹4000.0.
- **Confidence:** 0.7
- **Payable:** ₹4000.0
- **Fraud score:** 0.0 (manual review: False)
  - `SAME_DAY_CLAIMS` (info, w=0.0) — Same-day claim count ok (1/2)
  - `MONTHLY_CLAIMS` (info, w=0.0) — Monthly claim count ok (1/6)
  - `HIGH_VALUE_AUTO_REVIEW` (info, w=0.0) — Claim within normal value range
  - `DUPLICATE_CLAIM` (info, w=0.0) — No duplicates
- **Stage errors:**
  - `simulated` SimulatedFailure: component failure simulated
- **Trace spans:**
  - `parse` — ok — 0.02 ms (2 events)
  - `assemble` — ok — 0.06 ms (0 events)
  - `rules` — ok — 0.52 ms (9 events)
  - `fraud` — ok — 0.07 ms (4 events)
  - `finalize` — ok — 0.01 ms (0 events)

### TC012 — Member claims for bariatric consultation and a diet program. Obesity treatment is explicitly excluded under the policy.

- **Expected:** REJECTED
- **Actual:** REJECTED (match: True)
- **Reason:** Diagnosis matches policy exclusion: Obesity and weight loss programs
- **Confidence:** 1.0
- **Payable:** ₹1800.0
- **Failed rules:**
  - `EXCLUSIONS` (error) — Diagnosis matches policy exclusion: Obesity and weight loss programs
- **Fraud score:** 0.0 (manual review: False)
  - `SAME_DAY_CLAIMS` (info, w=0.0) — Same-day claim count ok (1/2)
  - `MONTHLY_CLAIMS` (info, w=0.0) — Monthly claim count ok (1/6)
  - `HIGH_VALUE_AUTO_REVIEW` (info, w=0.0) — Claim within normal value range
  - `DUPLICATE_CLAIM` (info, w=0.0) — No duplicates
- **Trace spans:**
  - `parse` — ok — 0.02 ms (2 events)
  - `assemble` — ok — 0.06 ms (0 events)
  - `rules` — ok — 0.6 ms (9 events)
  - `fraud` — ok — 0.08 ms (4 events)
  - `finalize` — ok — 0.01 ms (0 events)
