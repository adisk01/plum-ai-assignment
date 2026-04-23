"""Eval harness: run all 12 test cases through the graph and write a report.

Outputs:
    evals/report.json  — full decision + trace for every case
    evals/report.md    — human-readable table + per-case detail

Usage:
    python scripts/run_evals.py
    python scripts/run_evals.py --case TC010        # single case
    python scripts/run_evals.py --no-trace          # skip trace collection
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from claims_processor.core import config
from claims_processor.orchestrator.graph import run_graph

TESTS_FILE = ROOT / "PROBLEM_STATEMENT" / "test_cases.json"
OUT_DIR = ROOT / "evals"


def _expected_status(tc):
    exp = tc.get("expected_output") or tc.get("expected") or {}
    if isinstance(exp, dict):
        return exp.get("status") or exp.get("decision")
    return None


def _run_case(tc, trace):
    final = run_graph(tc["input"], claim_id=tc["case_id"], trace=trace)
    return final


def _row(tc, final):
    expected = _expected_status(tc)
    actual = final.status.value
    match = expected is None or expected == actual
    payable = final.decision.payable.payable if final.decision else None
    trace_ms = round(final.trace.duration_ms, 1) if final.trace else None
    span_count = len(final.trace.spans) if final.trace else 0
    return {
        "case_id": tc["case_id"],
        "description": tc.get("description", ""),
        "expected": expected,
        "actual": actual,
        "match": match,
        "payable": payable,
        "confidence": final.confidence,
        "reason": final.reason,
        "trace_ms": trace_ms,
        "span_count": span_count,
    }


def _render_markdown(rows, per_case):
    lines = [
        "# Eval Report",
        "",
        f"**{sum(1 for r in rows if r['match'])}/{len(rows)}** cases match expected outcomes.",
        "",
        "| case | expected | actual | match | payable | confidence | trace ms | reason |",
        "|------|----------|--------|-------|---------|------------|----------|--------|",
    ]
    for r in rows:
        mark = "✓" if r["match"] else "✗"
        exp = r["expected"] or "-"
        pay = r["payable"] if r["payable"] is not None else "-"
        tms = r["trace_ms"] if r["trace_ms"] is not None else "-"
        reason = (r["reason"] or "").replace("|", "\\|")[:80]
        lines.append(
            f"| {r['case_id']} | {exp} | {r['actual']} | {mark} | {pay} | "
            f"{r['confidence']} | {tms} | {reason} |"
        )
    lines.append("")
    lines.append("## Per-case detail")
    lines.append("")
    for r, detail in zip(rows, per_case):
        lines.append(f"### {r['case_id']} — {r['description']}")
        lines.append("")
        lines.append(f"- **Expected:** {r['expected'] or '-'}")
        lines.append(f"- **Actual:** {r['actual']} (match: {r['match']})")
        lines.append(f"- **Reason:** {r['reason']}")
        lines.append(f"- **Confidence:** {r['confidence']}")
        if r["payable"] is not None:
            lines.append(f"- **Payable:** ₹{r['payable']}")
        final = detail["final"]
        if final.get("claim") and final["claim"].get("issues"):
            lines.append("- **Consistency issues:**")
            for iss in final["claim"]["issues"]:
                lines.append(f"  - `{iss['code']}` ({iss['severity']}) — {iss['message']}")
        if final.get("claim") and final["claim"].get("missing_documents"):
            lines.append(f"- **Missing docs:** {final['claim']['missing_documents']}")
        if final.get("decision") and final["decision"].get("rules"):
            failed = [r for r in final["decision"]["rules"] if not r["passed"]]
            if failed:
                lines.append("- **Failed rules:**")
                for fr in failed:
                    lines.append(
                        f"  - `{fr['code']}` ({fr['severity']}) — {fr['message']}"
                    )
        if final.get("decision") and final["decision"].get("fraud"):
            fraud = final["decision"]["fraud"]
            if fraud.get("signals"):
                lines.append(f"- **Fraud score:** {fraud.get('score')} (manual review: {fraud.get('needs_manual_review')})")
                for sig in fraud["signals"]:
                    lines.append(
                        f"  - `{sig['code']}` ({sig['severity']}, w={sig['weight']}) — {sig['message']}"
                    )
        if final.get("stage_errors"):
            lines.append("- **Stage errors:**")
            for se in final["stage_errors"]:
                lines.append(f"  - `{se['stage']}` {se['error_type']}: {se['message']}")
        if final.get("trace"):
            lines.append("- **Trace spans:**")
            for sp in final["trace"]["spans"]:
                lines.append(
                    f"  - `{sp['stage']}` — {sp['status']} — {sp['duration_ms']} ms "
                    f"({len(sp['events'])} events)"
                )
        lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default=None, help="run one case, e.g. TC004")
    ap.add_argument("--no-trace", action="store_true")
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    args = ap.parse_args()

    config.load_env()
    tests = json.loads(TESTS_FILE.read_text())["test_cases"]
    if args.case:
        tests = [t for t in tests if t["case_id"] == args.case]
        if not tests:
            print(f"no case found: {args.case}", file=sys.stderr)
            return 1

    rows, per_case = [], []
    for tc in tests:
        final = _run_case(tc, trace=not args.no_trace)
        rows.append(_row(tc, final))
        per_case.append({
            "case_id": tc["case_id"],
            "description": tc.get("description", ""),
            "expected": _expected_status(tc),
            "final": final.model_dump(mode="json"),
        })

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(
        json.dumps({"summary": rows, "cases": per_case}, indent=2, default=str)
    )
    (out / "report.md").write_text(_render_markdown(rows, per_case))

    matched = sum(1 for r in rows if r["match"])
    print(f"{matched}/{len(rows)} cases match")
    print(f"wrote {out/'report.json'}")
    print(f"wrote {out/'report.md'}")
    return 0 if matched == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
