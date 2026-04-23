"""Public entry point for the claim assembler.

Usage:
    from claims_processor.claim_assembler.assemble import assemble_claim

    claim = assemble_claim(
        claim_id="C001",
        category="CONSULTATION",
        parsed_docs=[rx, bill],
    )
"""

from claims_processor.claim_assembler import checks
from claims_processor.models.claim import Claim


def assemble_claim(claim_id, category, parsed_docs):
    issues = []
    issues += checks.check_patient_name_match(parsed_docs)
    issues += checks.check_dates_consistent(parsed_docs)
    issues += checks.check_prescription_vs_pharmacy(parsed_docs)
    issues += checks.check_prescription_vs_lab(parsed_docs)

    req_issues, missing = checks.check_required_documents(category, parsed_docs)
    issues += req_issues

    return Claim(
        claim_id=claim_id,
        category=category,
        documents=parsed_docs,
        issues=issues,
        missing_documents=missing,
    )
