"""Prompt builder for the document classifier.

Adapted from fs-v2/agentic_search/prompts.py SKELETON_PROMPT pattern, but
retargeted at the 7 claim document types instead of financial doc types.
"""

from __future__ import annotations


CLASSIFIER_PROMPT = """You are classifying a medical document submitted with a health insurance claim in India.

Given the document content below (text or image), decide which of these types it is:

- PRESCRIPTION       — Doctor's prescription (Rx). Contains patient name, diagnosis, medicines with dosage, doctor's name and registration number. May be handwritten.
- HOSPITAL_BILL      — Itemized bill or invoice from a hospital or clinic. Contains hospital name, line items with amounts, and a total. May include GST.
- PHARMACY_BILL      — Bill from a pharmacy / chemist. Contains medicine names with batch, expiry, MRP. Usually has drug licence number.
- LAB_REPORT         — Pathology / blood test / diagnostic lab report. Contains test names, results, units, normal ranges, pathologist signature.
- DIAGNOSTIC_REPORT  — Imaging report: MRI, CT, ultrasound, X-ray findings + impression. NOT a bill for the imaging.
- DENTAL_REPORT      — Dentist's report describing dental procedures performed.
- DISCHARGE_SUMMARY  — Hospital discharge summary. Contains admission/discharge dates, final diagnosis, procedures performed.
- UNKNOWN            — The document does not fit any of the above or is not a medical document.

## Output format

Return ONLY a JSON object with these fields:
- "doc_type"   : one of PRESCRIPTION | HOSPITAL_BILL | PHARMACY_BILL | LAB_REPORT | DIAGNOSTIC_REPORT | DENTAL_REPORT | DISCHARGE_SUMMARY | UNKNOWN
- "confidence" : number between 0.0 and 1.0
- "reason"     : short (≤ 20 words) justification for your classification
- "readable"   : boolean — true if the document's key fields (amounts, names, dates) are legible; false if the document is too blurry, dark, or damaged to extract reliably

## Rules
- Base your decision on document structure and content, not the filename.
- A PRESCRIPTION that also lists test orders is still a PRESCRIPTION, not a LAB_REPORT.
- A bill from a pharmacy is PHARMACY_BILL, not HOSPITAL_BILL, even if it mentions a hospital.
- If the image is too degraded to read, set readable=false but still pick the most likely doc_type.

Do not wrap your answer in markdown fences.

Document content:
{content}
"""


def build_classifier_prompt(content: str) -> str:
    return CLASSIFIER_PROMPT.format(content=content or "[binary image — analyze visually]")
