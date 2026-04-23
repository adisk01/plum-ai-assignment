"""Run the LangGraph-based pipeline on a single claim JSON or all test cases.

Usage:
    python scripts/run_graph.py path/to/claim.json --pretty
    python scripts/run_graph.py --all
    python scripts/run_graph.py --case TC010
    python scripts/run_graph.py --mermaid      # print the graph as mermaid
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from claims_processor.core import config
from claims_processor.orchestrator.graph import build_graph, run_graph

TESTS = Path(__file__).resolve().parent.parent / "PROBLEM_STATEMENT" / "test_cases.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--case", default=None)
    ap.add_argument("--pretty", action="store_true")
    ap.add_argument("--mermaid", action="store_true")
    args = ap.parse_args()

    if args.mermaid:
        print(build_graph().get_graph().draw_mermaid())
        return 0

    config.load_env()
    indent = 2 if args.pretty else None

    if args.all or args.case:
        tests = json.loads(TESTS.read_text())["test_cases"]
        if args.case:
            tests = [t for t in tests if t["case_id"] == args.case]
        results = [{
            "case_id": t["case_id"],
            "actual": run_graph(t["input"], claim_id=t["case_id"]).model_dump(mode="json"),
        } for t in tests]
        print(json.dumps(results, indent=indent, default=str))
        return 0

    if not args.file:
        ap.error("pass a file path, --all, --case, or --mermaid")

    data = json.loads(Path(args.file).read_text())
    ci = data.get("input", data)
    final = run_graph(ci, claim_id=data.get("case_id") or data.get("claim_id") or "CLAIM")
    print(json.dumps(final.model_dump(mode="json"), indent=indent, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
