"""Classifier prompt."""

CLASSIFIER_PROMPT = """Classify this Indian medical document into one of:
PRESCRIPTION, HOSPITAL_BILL, PHARMACY_BILL, LAB_REPORT, DIAGNOSTIC_REPORT,
DENTAL_REPORT, DISCHARGE_SUMMARY, UNKNOWN.

Rules:
- PRESCRIPTION: doctor Rx with medicines and diagnosis.
- HOSPITAL_BILL: itemized hospital/clinic bill.
- PHARMACY_BILL: chemist bill with medicines, drug licence.
- LAB_REPORT: pathology test results.
- DIAGNOSTIC_REPORT: imaging findings (MRI/CT/X-Ray/Ultrasound).
- DENTAL_REPORT: dentist report.
- DISCHARGE_SUMMARY: hospital discharge summary.
- UNKNOWN: none of the above.

Set readable=false only if the document is too blurry/damaged to read.

Document content:
{content}
"""


def build_classifier_prompt(content=""):
    return CLASSIFIER_PROMPT.format(content=content or "[image - analyze visually]")
