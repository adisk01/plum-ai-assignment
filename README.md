# Plum AI — Health Insurance Claims Processing

End-to-end claims processing system for the Plum AI Engineer assignment. Given a claim submission and uploaded documents, produces an explainable decision (`APPROVED`, `PARTIAL`, `REJECTED`, `MANUAL_REVIEW`, or `NEEDS_REUPLOAD`) with the approved amount, reason, confidence, and a full per-stage trace.

See [`PROBLEM_STATEMENT/assignment.md`](PROBLEM_STATEMENT/assignment.md) for the brief.

## Docs

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — how the system is built, design decisions, scaling notes
- [`docs/CONTRACTS.md`](docs/CONTRACTS.md) — per-component interfaces, inputs, outputs, errors
- [`docs/EVAL_REPORT.md`](docs/EVAL_REPORT.md) — results across all 12 official test cases (11/12 match)

## Pipeline

```
parse → assemble → rules → fraud → finalize
  │         │
  └─ NEEDS_REUPLOAD   └─ REJECTED (consistency errors)
```

Five LangGraph nodes with two conditional short-circuits. A thread-local `Tracer` records a span per stage and events for every LLM call, rule evaluation, fraud signal, and payable computation — attached to `FinalDecision.trace`.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add an LLM key (Anthropic/OpenAI/Groq — any one)
```

## Run

```bash
# All 12 official test cases, writes evals/report.{json,md}
python scripts/run_evals.py

# Single case
python scripts/run_evals.py --case TC010

# Render graph
python scripts/run_graph.py --mermaid

# Parse a single document end-to-end
python scripts/parse_one.py tests/fixtures/sample_docs/prescription.pdf --pretty
```

## Tests

```bash
pytest            # 55 tests, LLM calls mocked
```

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
tests/                  # 55 tests
docs/                   # ARCHITECTURE, CONTRACTS, EVAL_REPORT
evals/                  # generated eval output
PROBLEM_STATEMENT/      # assignment brief + policy + test cases
```
