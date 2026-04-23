# Architecture

## What this system does

Takes a claim submission (member details, treatment category, amount, and one or more uploaded documents) and produces a decision — `APPROVED`, `PARTIAL`, `REJECTED`, `MANUAL_REVIEW`, or `NEEDS_REUPLOAD` — with the approved amount (if any), a reason, a confidence score, and a full trace of every rule, LLM call, and stage that produced the outcome.

## High-level flow

```
             ┌────────┐   ok    ┌──────────┐   ok    ┌───────┐    ┌───────┐    ┌──────────┐
 claim in ──►│ parse  ├────────►│ assemble ├────────►│ rules ├───►│ fraud ├───►│ finalize │──► FinalDecision
             └────┬───┘         └────┬─────┘         └───────┘    └───────┘    └──────────┘
                  │ wrong-type / unreadable       │ consistency errors
                  └───────── NEEDS_REUPLOAD ──────┴────────────── REJECTED (via finalize)
```

All five stages are LangGraph nodes. Two conditional routers short-circuit to `finalize` early:

1. **After parse** — if any document is the wrong type (e.g. prescription where bill is required) or is unreadable, the graph jumps to `finalize` and returns `NEEDS_REUPLOAD` with a specific error message. This is assignment requirement #2 ("catch document problems early").
2. **After assemble** — if cross-document checks surface a hard error (patient name mismatch, treatment-date-before-prescription, etc.), the graph skips rules/fraud and returns `REJECTED`. This is a defence-in-depth cheaper gate than running the rules engine.

The happy path runs all five stages. A single `Tracer` is attached via thread-local for the duration of one graph invocation and collects a span per stage plus fine-grained events (LLM call, rule evaluation, fraud signal, payable computation). The trace is serialized into `FinalDecision.trace`.

## Components

### `document_extractor` — turn files into typed dicts
- `classifier.py` — LLM classifies a document into one of 7 doc types; returns `ClassifierResponse(type, confidence)`
- `extractor.py` — given a known type, LLM extracts the schema for that type (Pydantic model)
- `parse.py` — orchestrates classify → (verify against expected) → extract; also supports `parse_from_dict` for tests that already have the content as a dict
- `pdf_utils.py` — pdfium-backed text extraction (fast path) with image-fallback for scans
- `exceptions.py` — typed errors (`WrongDocumentTypeError`, `UnreadableDocumentError`, `UnsupportedFileTypeError`) that drive the short-circuit router

### `claim_assembler` — cross-document consistency
- Checks patient name matches across documents, treatment/prescription dates are ordered correctly, prescribed medicines appear on the pharmacy bill, ordered tests appear in the lab report
- Checks required documents are present for the claim category (read from `policy_terms.json`)
- Returns `Claim(documents, issues, missing_documents, has_errors())`

### `rules_engine` — policy checks + financial calculation
- Eight rule checks, all in `rules.py`: category covered, min amount, per-claim limit, submission deadline, waiting period, pre-authorization, exclusions, network hospital
- `financials.py` computes `PayableBreakdown` in this order: **network discount → sub-limit → copay**
- `evaluate.py` (used by the non-graph pipeline) combines rules + fraud into a `Decision`
- Status precedence: any error → `REJECTED`; otherwise fraud-manual-review wins; otherwise any warning → `NEEDS_REVIEW`; otherwise `APPROVED`

### `fraud_detector` — anomaly signals
- Four signals: same-day claim burst, monthly claim volume, high-value auto-review, duplicate claim (same date+amount)
- Weighted score (capped at 1.0), threshold read from `policy_terms.json.fraud_thresholds`
- Returns `FraudReport(score, needs_manual_review, signals[])`

### `orchestrator/graph.py` — LangGraph wiring
- `GraphState` is a `TypedDict` carrying `claim_input`, `parsed_docs`, `claim`, `decision`, `fraud`, `final`, `stage_errors`, `blocking`
- 5 nodes, 2 conditional routers, 1 end — no inner loops, retries, or reflection (kept deliberately linear)
- `run_graph(claim_input, claim_id, trace=True)` creates a `Tracer`, sets it thread-local, invokes the compiled graph, attaches the finished trace to `FinalDecision`

### `observability/trace.py` — tracing
- `Tracer` collects `TraceSpan`s (stage-level) and `TraceEvent`s (LLM call, rule eval, fraud signal, payable computation, doc parse/error, consistency issue)
- Thread-local access (`get_tracer()`) lets the LLM adapters emit events without the adapter knowing anything about the pipeline
- The full `Trace` is attached to `FinalDecision.trace` — so every ops-team review of a decision has latency-per-stage, token usage per LLM call, every rule that passed or failed, and every fraud signal with its weight

### `clients/llm_adapters.py`
- One function per provider: OpenAI, Anthropic, Groq
- Two dispatchers: `call_text` (prefers Groq for speed), `call_vision` (prefers Anthropic for stronger vision)
- Every call is wrapped in `_traced(...)` which records provider/model/kind, latency, token usage, error string (if any)
- All three support structured outputs via Pydantic → JSON schema (OpenAI/Groq use `response_format=json_schema`, Anthropic gets schema in prompt text)

### `core/config.py`
- Loads `.env` and `policy_terms.json`
- Helpers: `get_document_requirements(category)`, `list_claim_categories()`, `get_member(member_id)`
- Single source of truth — no policy value is hardcoded elsewhere

## Design decisions

| Decision | Why | What we rejected |
|---|---|---|
| LangGraph over hand-rolled orchestration | Built-in conditional routing, visualization (`draw_mermaid`), checkpointing is one config flag away | Plain function-chain (loses the "why can't we add retry/reflection later" story); Airflow/Prefect (overkill) |
| Function-based nodes, no node classes | Each node is a pure function over `GraphState`; easy to test, easy to read | Class-based agents with `.run()` — more abstractions for no gain |
| Thread-local tracer | Lets LLM adapters emit events without plumbing a tracer through 5 layers of function args | Passing tracer everywhere (noisy), contextvar (same thing but more typing), external APM (no offline story, needs infra) |
| JSON-schema-enforced LLM outputs | OpenAI and Groq both support it natively; removes an entire class of "LLM returned malformed JSON" bugs | Prompt-and-pray with retries |
| Pydantic v2 everywhere | `model_json_schema()` feeds straight into the LLM call; `@model_serializer` for nested typed dumps; validators are free | dataclasses + manual JSON (loses schema, loses validation) |
| Short-circuit routers vs running every stage | Per the brief: wrong document must stop immediately; consistency errors are cheaper to surface than running rules/fraud | Always running all stages (wastes LLM tokens on claims that were going to `REJECTED` anyway) |
| `parse_from_dict` test path | The official `test_cases.json` carries extracted content inline; this lets us test rules/fraud/assembler end-to-end without paying for LLM calls or shipping sample PDFs | Mocking every LLM call (brittle, ties tests to adapter internals) |

## Failure handling

The assignment requires that individual component failures don't crash the pipeline. Three layers of defence:

1. **Per-document try/except in `parse` node** — any one doc can blow up and the rest continue; the error lands in `stage_errors` and the document is dropped from the claim
2. **Short-circuit on blocking errors** — `WrongDocumentTypeError` and `UnreadableDocumentError` go straight to `NEEDS_REUPLOAD` with a specific message
3. **Confidence is a first-class degraded-state signal** — every `StageError` subtracts 0.3, every consistency issue subtracts 0.1; reviewers see a low-confidence `APPROVED` and know the trace is worth reading

TC011 explicitly exercises this via `simulate_component_failure` in the input, which appends a synthetic `StageError` and drops confidence by 0.3 while still producing an `APPROVED` decision.

## Scaling to 10x

Today this is a single-process synchronous pipeline. At 10x scale:

- **LLM calls are the bottleneck.** Document extraction dominates latency (3-5 seconds per doc typical). Parallelize the `parse` node across documents — LangGraph's async mode plus `asyncio.gather` is a 10-line change because `parse_document` is already stateless per doc.
- **Move the pipeline behind a queue.** A claim submission becomes an enqueue; workers pull from SQS/Kafka and invoke `run_graph`. Graceful degradation semantics already match queue-friendly behaviour (failures are recorded, not raised).
- **Persist traces.** The current `FinalDecision.trace` is fine for one-off review but at 10x we'd emit each span as an OTEL span to Honeycomb/Grafana Tempo — the `Tracer` API is close enough to OTEL that the swap is isolated to `observability/trace.py`.
- **Cache policy.** `policy_terms.json` is loaded on every `config.load_policy_terms()` — add LRU cache keyed by mtime. Cheap, and lets the policy be hot-reloaded without restart.
- **LLM provider diversity.** `call_text` and `call_vision` already fall back across providers; at 10x we'd add per-provider rate limiting and a circuit breaker so a Groq outage can't starve the pipeline.

## Limitations (honest list)

- **TC006 — partial approval of mixed line items.** The rules engine currently treats a bill containing one excluded line item (teeth whitening) as `REJECTED` for the whole claim. The brief expects `PARTIAL` with the covered portion paid. Would need to split `PayableBreakdown` across line items and mark excluded items explicitly. Tracked in the eval report.
- **No UI.** Assignment asks for one; not built yet. A thin Gradio app over `run_graph` is the obvious next step.
- **OCR for real scans.** Vision LLMs handle clean phone photos well; rubber-stamped handwritten prescriptions from tier-3 clinics would need a dedicated OCR pre-pass. Not implemented.
- **No eval regression harness in CI.** The eval runs locally via `scripts/run_evals.py`. For production, the 11/12 match rate becomes a CI gate.
- **Fraud history is synthetic.** We read `claims_history` off the input; at scale this is a database query. Contract-wise this is just a dependency injection change in `detect_fraud`.
