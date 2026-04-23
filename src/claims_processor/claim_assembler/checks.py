"""Cross-document consistency checks.

Each function takes a list of ParsedDocument and returns list[ConsistencyIssue].
Keep each check small and independent so the assembler just chains them.
"""

from difflib import SequenceMatcher

from claims_processor.core import config
from claims_processor.models.claim import ConsistencyIssue
from claims_processor.models.documents import DocType


def _get(doc, *fields):
    """Read the first non-None field from a ParsedDocument's extracted body."""
    body = doc.extracted
    if body is None:
        return None
    for f in fields:
        v = getattr(body, f, None)
        if v:
            return v
    return None


def _names_match(a, b, threshold=0.8):
    if not a or not b:
        return True  # can't compare → don't flag
    a = a.strip().lower()
    b = b.strip().lower()
    if a == b:
        return True
    return SequenceMatcher(None, a, b).ratio() >= threshold


def check_patient_name_match(docs):
    """TC003: patient name should match across all documents."""
    names = [(d.file_id, _get(d, "patient_name")) for d in docs]
    names = [(fid, n) for fid, n in names if n]
    if len(names) < 2:
        return []

    baseline_fid, baseline = names[0]
    issues = []
    for fid, name in names[1:]:
        if not _names_match(baseline, name):
            issues.append(ConsistencyIssue(
                code="PATIENT_NAME_MISMATCH",
                severity="error",
                message=f"Patient name on {fid} ('{name}') does not match {baseline_fid} ('{baseline}')",
                evidence={"baseline": baseline, "found": name, "file_id": fid},
            ))
    return issues


def check_dates_consistent(docs):
    """Prescription date should not be after any bill/report date."""
    rx_date = next((_get(d, "date") for d in docs if d.doc_type == DocType.PRESCRIPTION), None)
    if not rx_date:
        return []

    issues = []
    for d in docs:
        if d.doc_type == DocType.PRESCRIPTION:
            continue
        other_date = _get(d, "date", "report_date", "sample_date", "discharge_date")
        if other_date and other_date < rx_date:
            issues.append(ConsistencyIssue(
                code="DATE_BEFORE_PRESCRIPTION",
                severity="warning",
                message=f"{d.file_id} date ({other_date}) is before prescription date ({rx_date})",
                evidence={"rx_date": rx_date, "other_date": other_date, "file_id": d.file_id},
            ))
    return issues


def check_prescription_vs_pharmacy(docs):
    """TC008: every medicine on the pharmacy bill should appear on the prescription."""
    rx = next((d for d in docs if d.doc_type == DocType.PRESCRIPTION), None)
    pb = next((d for d in docs if d.doc_type == DocType.PHARMACY_BILL), None)
    if not rx or not pb or not rx.extracted or not pb.extracted:
        return []

    rx_meds = [m.name.lower() for m in (rx.extracted.medicines or []) if m.name]
    issues = []
    for item in pb.extracted.line_items or []:
        desc = (item.description or "").lower()
        if not desc:
            continue
        if not any(med in desc or desc in med for med in rx_meds):
            issues.append(ConsistencyIssue(
                code="PHARMACY_ITEM_NOT_PRESCRIBED",
                severity="warning",
                message=f"Pharmacy item '{item.description}' not found on prescription",
                evidence={"item": item.description, "prescribed": rx_meds},
            ))
    return issues


def check_prescription_vs_lab(docs):
    """Every test on a lab report should have been ordered on the prescription."""
    rx = next((d for d in docs if d.doc_type == DocType.PRESCRIPTION), None)
    lab = next((d for d in docs if d.doc_type == DocType.LAB_REPORT), None)
    if not rx or not lab or not rx.extracted or not lab.extracted:
        return []

    ordered = [t.lower() for t in (rx.extracted.tests_ordered or [])]
    issues = []
    for t in lab.extracted.tests or []:
        name = (t.name or "").lower()
        if not name:
            continue
        if not any(o in name or name in o for o in ordered):
            issues.append(ConsistencyIssue(
                code="LAB_TEST_NOT_ORDERED",
                severity="warning",
                message=f"Lab test '{t.name}' was not ordered on the prescription",
                evidence={"test": t.name, "ordered": ordered},
            ))
    return issues


def check_required_documents(category, docs):
    """TC006: verify every policy-required doc type is present."""
    try:
        reqs = config.get_document_requirements(category)
    except KeyError:
        return [], []

    present = {d.doc_type.value for d in docs}
    missing = [r for r in reqs["required"] if r not in present]
    issues = []
    for m in missing:
        issues.append(ConsistencyIssue(
            code="MISSING_REQUIRED_DOCUMENT",
            severity="error",
            message=f"Required document '{m}' missing for category {category}",
            evidence={"category": category, "missing": m},
        ))
    return issues, missing
