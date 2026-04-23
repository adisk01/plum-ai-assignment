"""CLI: run every case in PROBLEM_STATEMENT/test_cases.json through the pipeline.

Usage:
    python scripts/run_test_cases.py
    python scripts/run_test_cases.py --case TC010 --pretty
    python scripts/run_test_cases.py --out results.json
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from claims_processor.core import config
from claims_processor.orchestrator.pipeline import process_claim

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "PROBLEM_STATEMENT" / "test_cases.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=str(DEFAULT_PATH))
    ap.add_argument("--case", default=None, help="run a single case by id (e.g. TC010)")
    ap.add_argument("--pretty", action="store_true")
    ap.add_argument("--out", default=None, help="optional path to dump all results as JSON")
    args = ap.parse_args()

    config.load_env()
    tests = json.loads(Path(args.file).read_text())["test_cases"]
    if args.case:
        tests = [t for t in tests if t["case_id"] == args.case]
        if not tests:
            print(f"No case matched {args.case}", file=sys.stderr)
            return 1

    results = []
    for tc in tests:
        final = process_claim(tc["input"], claim_id=tc["case_id"])
        results.append({
            "case_id": tc["case_id"],
            "case_name": tc["case_name"],
            "expected": tc.get("expected"),
            "actual": final.model_dump(mode="json"),
        })

    indent = 2 if args.pretty else None
    output = json.dumps(results, indent=indent, default=str)
    if args.out:
        Path(args.out).write_text(output)
        print(f"Wrote {len(results)} results to {args.out}")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
