# Plum AI — Health Insurance Claims Processing

End-to-end claims processing system for the Plum AI Engineer assignment. Given a claim submission and uploaded documents, produces an explainable decision (`APPROVED`, `PARTIAL`, `REJECTED`, `MANUAL_REVIEW`, or `NEEDS_REUPLOAD`) with the approved amount, reason, confidence, and a full per-stage trace.

See [`PROBLEM_STATEMENT/assignment.md`](PROBLEM_STATEMENT/assignment.md) for the brief.

## Docs

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — how the system is built, design decisions, scaling notes
- [`docs/CONTRACTS.md`](docs/CONTRACTS.md) — per-component interfaces, inputs, outputs, errors
- [`docs/EVAL_REPORT.md`](docs/EVAL_REPORT.md) — results across all 12 official test cases (12/12 match)

## Pipeline

```
parse → assemble → rules → fraud → finalize
  │         │
  └─ NEEDS_REUPLOAD   └─ REJECTED (consistency errors)
```

Five LangGraph nodes with two conditional short-circuits. A thread-local `Tracer` records a span per stage and events for every LLM call, rule evaluation, fraud signal, and payable computation — attached to `FinalDecision.trace`.

## Quickstart

```bash
# 1. Clone + create a virtualenv
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure an LLM provider (any one of OpenAI / Anthropic / Groq)
cp .env.example .env
# edit .env and set OPENAI_API_KEY / ANTHROPIC_API_KEY / GROQ_API_KEY

# 3. Run the test suite — should show 55 passed
pytest

# 4. Run the eval harness against all 12 official test cases
python scripts/run_evals.py          # writes evals/report.{json,md} — 12/12 match

# 5. Launch the UI
python scripts/ui.py                 # http://127.0.0.1:7860
python scripts/ui.py --share         # public Gradio tunnel for demo
```

The UI and the eval harness both go through the same entry point (`run_graph`), so there is no "demo mode" — what you see in the UI is the production pipeline.

## Other useful commands

```bash
# Run one specific test case
python scripts/run_evals.py --case TC006

# Print the LangGraph diagram (mermaid)
python scripts/run_graph.py --mermaid

# Parse a single document end-to-end (real LLM call)
python scripts/parse_one.py tests/fixtures/sample_docs/prescription.pdf --pretty

# Run the pipeline on a single claim JSON file
python scripts/run_graph.py path/to/claim.json --pretty
```

## UI

The Gradio app at `scripts/ui.py` wraps `run_graph`. Choose one of the 12 official test cases from the dropdown (or edit the JSON) and hit **Run pipeline** to see:

- decision status + reason + confidence
- payable breakdown (claimed → exclusions → network discount → sub-limit → copay → payable) with per-line-item covered/excluded table
- every rule fired, with severity and message
- fraud signals with weights and risk level
- stage errors (if any)
- full per-stage audit trace (spans + events)
- full `FinalDecision` JSON

## LangSmith (optional — engineering-level tracing)

The claim-level audit trace on `FinalDecision.trace` is always on. For engineering-level tracing of LLM calls and graph-node runs, set:

```bash
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=ls__...
LANGSMITH_PROJECT=plum-claims-dev
```

Every `run_graph` call, every node (`parse`, `assemble`, `rules`, `fraud`, `finalize`), and every LLM provider call (`openai` / `anthropic` / `groq`) is wrapped in `@langsmith.traceable` and will appear in the project, grouped by `claim_id` via run tags/metadata. When the env vars are unset the decorator is a no-op.

## Layout

```
src/claims_processor/
  clients/              # LLM adapters (OpenAI / Anthropic / Groq), traced
  core/                 # config + policy_terms loader
  models/               # Pydantic schemas (documents, claim, decision, fraud, final, trace)
  prompts/              # prompt templates
  document_extractor/   # layer 1 — parse / classify / extract
  claim_assembler/      # layer 2 — cross-document consistency
  rules_engine/         # layer 3 — policy rules + financials
  fraud_detector/       # layer 4 — anomaly signals
  observability/        # Tracer, Trace, TraceSpan, TraceEvent
  orchestrator/
    graph.py            # LangGraph wiring (5 nodes, 2 routers)
    pipeline.py         # function-based equivalent
scripts/
  run_evals.py          # all 12 cases → evals/report.{json,md}
  run_graph.py          # CLI for the LangGraph pipeline
  parse_one.py          # single-doc parser CLI
  ui.py                 # Gradio UI over run_graph
tests/                  # 55 tests
docs/                   # ARCHITECTURE, CONTRACTS, EVAL_REPORT
evals/                  # generated eval output
PROBLEM_STATEMENT/      # assignment brief + policy + test cases
```
