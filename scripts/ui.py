"""Gradio UI over the claims pipeline (run_graph).

Run:
    python scripts/ui.py
    # or
    .venv/bin/python scripts/ui.py --share

Lets an ops reviewer:
  - pick one of the 12 provided test cases (or paste their own JSON),
  - run it through the full LangGraph pipeline,
  - see the decision, payable breakdown, rules fired, fraud signals,
    stage errors, and the audit trace.
"""

import argparse
import json
import sys
from pathlib import Path

import gradio as gr

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from claims_processor.core import config
from claims_processor.orchestrator.graph import run_graph

ROOT = Path(__file__).resolve().parent.parent
TESTS_PATH = ROOT / "PROBLEM_STATEMENT" / "test_cases.json"


def _load_cases():
    data = json.loads(TESTS_PATH.read_text())["test_cases"]
    return {t["case_id"]: t for t in data}


CASES = _load_cases()
CASE_CHOICES = [f"{cid} — {t['case_name']}" for cid, t in CASES.items()]
CASE_ID_BY_LABEL = {f"{cid} — {t['case_name']}": cid for cid, t in CASES.items()}


def load_case(label):
    if not label:
        return "", "", ""
    cid = CASE_ID_BY_LABEL.get(label, label)
    t = CASES.get(cid)
    if not t:
        return "", "", ""
    return (
        json.dumps(t["input"], indent=2),
        t.get("description", ""),
        json.dumps(t.get("expected", {}), indent=2),
    )


def _status_badge(status):
    palette = {
        "APPROVED": "#16a34a",
        "PARTIAL": "#ca8a04",
        "NEEDS_REVIEW": "#2563eb",
        "MANUAL_REVIEW": "#9333ea",
        "NEEDS_REUPLOAD": "#dc2626",
        "REJECTED": "#dc2626",
    }
    color = palette.get(str(status), "#6b7280")
    return (
        f'<div style="display:inline-block;padding:6px 14px;border-radius:999px;'
        f'background:{color};color:white;font-weight:600;font-size:16px;">'
        f"{status}</div>"
    )


def _payable_md(payable):
    if not payable:
        return "_No payable computed_"
    rows = [
        ("Claimed amount", payable.get("claimed_amount")),
        ("After exclusions", payable.get("after_exclusions")),
        ("After network discount", payable.get("after_network_discount")),
        ("After sub-limit", payable.get("after_sub_limit")),
        ("Copay", payable.get("copay_amount")),
        ("**Payable**", f"**₹{payable.get('payable')}**"),
    ]
    out = ["| Field | Amount |", "|---|---|"]
    for k, v in rows:
        if v is None:
            continue
        out.append(f"| {k} | {v} |")
    notes = payable.get("notes") or []
    if notes:
        out.append("")
        out.append("**Notes:** " + "; ".join(notes))
    line_items = payable.get("line_items") or []
    if line_items:
        out.append("")
        out.append("**Line items:**")
        out.append("| Description | Amount | Covered | Reason |")
        out.append("|---|---|---|---|")
        for li in line_items:
            covered = "Yes" if li.get("covered") else "No"
            reason = li.get("reason") or ""
            out.append(f"| {li.get('description','')} | ₹{li.get('amount',0)} | {covered} | {reason} |")
    return "\n".join(out)


def _rules_md(rules):
    if not rules:
        return "_No rules evaluated_"
    out = ["| Code | Passed | Severity | Message |", "|---|---|---|---|"]
    for r in rules:
        passed = "yes" if r.get("passed") else "no"
        out.append(f"| {r.get('code','')} | {passed} | {r.get('severity','')} | {r.get('message','')} |")
    return "\n".join(out)


def _fraud_md(fraud):
    if not fraud:
        return "_No fraud analysis_"
    lines = [
        f"- **Risk score:** {fraud.get('risk_score', 0)}",
        f"- **Risk level:** {fraud.get('risk_level','')}",
        f"- **Needs manual review:** {fraud.get('needs_manual_review', False)}",
    ]
    signals = fraud.get("signals") or []
    if signals:
        lines.append("")
        lines.append("**Signals:**")
        lines.append("| Code | Weight | Message |")
        lines.append("|---|---|---|")
        for s in signals:
            lines.append(f"| {s.get('code','')} | {s.get('weight',0)} | {s.get('message','')} |")
    return "\n".join(lines)


def _trace_md(trace):
    if not trace:
        return "_No trace_"
    lines = [
        f"**trace_id:** `{trace.get('trace_id')}`  ",
        f"**duration_ms:** {trace.get('duration_ms')}  ",
        "",
    ]
    for sp in trace.get("spans") or []:
        lines.append(
            f"### {sp.get('stage')}  ·  {sp.get('status')}  ·  {sp.get('duration_ms')}ms"
        )
        attrs = sp.get("attrs") or {}
        if attrs:
            lines.append(f"- attrs: `{json.dumps(attrs, default=str)}`")
        for ev in sp.get("events") or []:
            lines.append(f"  - **{ev.get('name')}** `{json.dumps(ev.get('attrs',{}), default=str)}`")
        lines.append("")
    return "\n".join(lines)


def _stage_errors_md(errors):
    if not errors:
        return "_No stage errors_"
    out = ["| Stage | File | Type | Message |", "|---|---|---|---|"]
    for e in errors:
        out.append(
            f"| {e.get('stage','')} | {e.get('file_id','') or ''} | "
            f"{e.get('error_type','')} | {e.get('message','')} |"
        )
    return "\n".join(out)


def run_claim(input_json, claim_id):
    if not input_json or not input_json.strip():
        return (
            _status_badge("ERROR"),
            "Please provide a claim JSON.",
            "", "", "", "", "", "{}",
        )
    try:
        claim_input = json.loads(input_json)
    except json.JSONDecodeError as e:
        return (
            _status_badge("ERROR"),
            f"Invalid JSON: {e}",
            "", "", "", "", "", "{}",
        )

    config.load_env()
    final = run_graph(claim_input, claim_id=(claim_id or "UI_CLAIM").strip() or "UI_CLAIM")
    data = final.model_dump(mode="json")

    status = data.get("status", "")
    reason = data.get("reason", "")
    decision = data.get("decision") or {}
    payable = decision.get("payable")
    rules = decision.get("rules") or []
    fraud = decision.get("fraud")
    trace = data.get("trace")
    stage_errors = data.get("stage_errors") or []

    header = f"**Claim:** `{data.get('claim_id')}`  ·  **Confidence:** {data.get('confidence')}  \n**Reason:** {reason}"

    return (
        _status_badge(status),
        header,
        _payable_md(payable),
        _rules_md(rules),
        _fraud_md(fraud),
        _stage_errors_md(stage_errors),
        _trace_md(trace),
        json.dumps(data, indent=2, default=str),
    )


def build_app():
    with gr.Blocks(title="Claims Processor") as demo:
        gr.Markdown(
            "# Claims Processor\n"
            "End-to-end health-insurance claim evaluation over the LangGraph "
            "pipeline: parse → assemble → rules → fraud → finalize."
        )

        with gr.Row():
            with gr.Column(scale=1):
                case_dd = gr.Dropdown(
                    choices=CASE_CHOICES,
                    label="Load test case",
                    value=CASE_CHOICES[0] if CASE_CHOICES else None,
                )
                case_desc = gr.Textbox(label="Description", lines=3, interactive=False)
                expected = gr.Code(label="Expected (from test_cases.json)", language="json", lines=6)
                claim_id = gr.Textbox(label="Claim ID", value="TC001")
                input_box = gr.Code(label="Claim input JSON", language="json", lines=24)
                run_btn = gr.Button("Run pipeline", variant="primary")

            with gr.Column(scale=2):
                status_html = gr.HTML(label="Status")
                header_md = gr.Markdown()
                with gr.Tabs():
                    with gr.TabItem("Payable"):
                        payable_md = gr.Markdown()
                    with gr.TabItem("Rules"):
                        rules_md = gr.Markdown()
                    with gr.TabItem("Fraud"):
                        fraud_md = gr.Markdown()
                    with gr.TabItem("Stage errors"):
                        errors_md = gr.Markdown()
                    with gr.TabItem("Trace"):
                        trace_md = gr.Markdown()
                    with gr.TabItem("Full JSON"):
                        full_json = gr.Code(language="json", lines=30)

        def _on_case_change(label):
            inp, desc, exp = load_case(label)
            cid = CASE_ID_BY_LABEL.get(label, "")
            return inp, desc, exp, cid

        case_dd.change(
            _on_case_change,
            inputs=[case_dd],
            outputs=[input_box, case_desc, expected, claim_id],
        )

        # Prefill on load
        if CASE_CHOICES:
            inp0, desc0, exp0 = load_case(CASE_CHOICES[0])
            cid0 = CASE_ID_BY_LABEL[CASE_CHOICES[0]]
            input_box.value = inp0
            case_desc.value = desc0
            expected.value = exp0
            claim_id.value = cid0

        run_btn.click(
            run_claim,
            inputs=[input_box, claim_id],
            outputs=[status_html, header_md, payable_md, rules_md, fraud_md, errors_md, trace_md, full_json],
        )

    return demo


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--share", action="store_true", help="Expose a public Gradio link")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7860)
    args = ap.parse_args()

    demo = build_app()
    demo.launch(
        share=args.share,
        server_name=args.host,
        server_port=args.port,
        theme=gr.themes.Soft(),
    )


if __name__ == "__main__":
    main()
