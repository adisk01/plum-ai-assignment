"""CLI: run the full pipeline on a single claim JSON file.

Usage:
    python scripts/process_claim.py path/to/claim.json --pretty

The JSON file must match the input shape used in PROBLEM_STATEMENT/test_cases.json
(at minimum: member_id, claim_category, treatment_date, claimed_amount, documents).
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from claims_processor.core import config
from claims_processor.orchestrator.pipeline import process_claim


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()

    config.load_env()
    data = json.loads(Path(args.file).read_text())
    claim_input = data.get("input", data)  # allow wrapped format
    claim_id = data.get("case_id") or data.get("claim_id")

    final = process_claim(claim_input, claim_id=claim_id)
    indent = 2 if args.pretty else None
    print(json.dumps(final.model_dump(mode="json"), indent=indent, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
