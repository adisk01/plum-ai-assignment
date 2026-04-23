# Component Contracts

Every significant component's inputs, outputs, and errors. Precise enough that any single component could be reimplemented from this doc.

---

## `document_extractor.parse`

### `parse_document(file_bytes: bytes, file_ext: str, file_id: str, expected_type: DocType | None = None) -> ParsedDocument`

Classify and extract a single document from raw bytes.

- **Input**
  - `file_bytes` — the file contents
  - `file_ext` — `.pdf`, `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`
  - `file_id` — caller-assigned id (e.g. `F007`)
  - `expected_type` — if provided and the classifier disagrees, raises `WrongDocumentTypeError`
- **Output** — `ParsedDocument(file_id, doc_type, confidence, extracted)` where `extracted` is the typed schema for the detected doc type
- **Raises**
  - `UnsupportedFileTypeError` — extension not in the allowed set
  - `UnreadableDocumentError` — PDF has no text and no images extractable, or LLM returns zero-confidence classification
  - `WrongDocumentTypeError` — classifier output ≠ `expected_type`

### `parse_from_dict(file_id: str, doc_type: DocType, content: dict) -> ParsedDocument`

Skip LLM; validate `content` against the schema for `doc_type`. Used by the test harness (`test_cases.json` carries pre-extracted content). Raises the Pydantic `ValidationError` if content doesn't fit the schema.

---

## `document_extractor.classifier`

### `classify_from_text(text: str) -> ClassifierResponse`
### `classify_from_image(image_bytes: bytes, ext: str) -> ClassifierResponse`

Wraps an LLM call. Returns `ClassifierResponse(type: DocType, confidence: float)`. Raises upstream LLM errors (network, malformed JSON survives `response_format=json_schema`).

---

## `document_extractor.extractor`

### `extract_from_text(doc_type: DocType, text: str) -> BaseModel`
### `extract_from_image(doc_type: DocType, image_bytes: bytes, ext: str) -> BaseModel`

Given a known doc type, extract fields as per `SCHEMA_FOR_DOC_TYPE[doc_type]`. Return type is the specific Pydantic model (`Prescription`, `HospitalBill`, `PharmacyBill`, `LabReport`, `DiagnosticReport`, `Discharge`, `InsuranceClaim`).

---

## `claim_assembler.assemble`

### `assemble_claim(claim_id: str, category: str, parsed_docs: list[ParsedDocument]) -> Claim`

- **Input**
  - `claim_id` — unique id
  - `category` — one of the policy's claim categories (case-insensitive; coerced to upper)
  - `parsed_docs` — all documents for this claim
- **Output** — `Claim(claim_id, category, documents, issues, missing_documents)` where
  - `issues: list[ConsistencyIssue]` with codes like `PATIENT_NAME_MISMATCH`, `TREATMENT_DATE_BEFORE_PRESCRIPTION`, `RX_NOT_ON_BILL`, `TEST_NOT_IN_REPORT`
  - `missing_documents: list[str]` — required doc types from `policy_terms.json.document_requirements[category]` that aren't in `parsed_docs`
  - `has_errors() -> bool` — any `severity == "error"` issue or any missing required doc
- **Raises** — `ValueError` if `category` is not in `policy_terms.json.document_requirements`

---

## `rules_engine.rules` (per-check functions)

All return `RuleResult(code, passed, severity, message, evidence)`. `severity` is `"error"` or `"warning"`. `evidence` is a free-form dict used by downstream steps (e.g. `check_network_hospital` returns `evidence.in_network: bool` consumed by `financials`).

| Function | Inputs | Fails with |
|---|---|---|
| `check_category_covered(category)` | claim category | error — category not in policy |
| `check_minimum_amount(amount)` | claimed amount | warning — under floor |
| `check_per_claim_limit(amount, category, covered_amount)` | claimed or covered amount + category | **error** — over `max(per_claim_limit, category.sub_limit)` |
| `check_submission_deadline(treatment_date, submission_date)` | ISO dates | warning — submitted after window |
| `check_waiting_period(join_date, treatment_date, diagnosis)` | dates + diagnosis string | error — condition still in waiting period |
| `check_pre_auth(category, amount, text, provided)` | category, amount, concatenated doc text, flag | error — pre-auth required but not provided |
| `check_exclusions(category, line_items, diagnosis)` | category, bill line items, diagnosis | error — diagnosis excluded or all items excluded; **partial** — some items excluded; passes with `evidence.excluded_descriptions` |
| `check_network_hospital(name)` | hospital name | info — always passes; sets `evidence.in_network` |

---

## `rules_engine.financials`

### `compute_payable(claimed_amount, category, is_network, line_items=None, excluded_descriptions=None) -> PayableBreakdown`

Applies **per-item exclusion filter → network discount → sub-limit → copay** in that order. When `line_items` is supplied, each item is itemised into `LineItemDecision(description, amount, covered, reason)` and excluded items are dropped before network/sub-limit/copay math runs on the covered subtotal.

Returns `PayableBreakdown(claimed_amount, after_exclusions, after_network_discount, after_sub_limit, copay_amount, payable, line_items, notes)`. Never raises on valid inputs; returns `payable=0` for unknown categories.

---

## `rules_engine.evaluate` (non-graph pipeline)

### `evaluate_claim(claim: Claim, claimed_amount: float, treatment_date: str, member_join_date: str | None, pre_auth_provided: bool, submission_date: str, member_id: str | None, claims_history: list | None) -> Decision`

- Short-circuits with `REJECTED` if `claim.has_errors()`
- Runs all rule checks, computes payable, runs fraud detection
- Returns `Decision(claim_id, status, reason, rules, payable, fraud)`
- Status precedence: error → `REJECTED`; fraud.needs_manual_review + no error → `MANUAL_REVIEW`; partial → `PARTIAL`; warning → `NEEDS_REVIEW`; else `APPROVED`
- **Raises** — never; failures surface as failed `RuleResult`s or come out through the orchestrator's `StageError` wrapper

---

## `fraud_detector.detect`

### `detect_fraud(member_id: str | None, claimed_amount: float | None, treatment_date: str | None, claims_history: list | None, provider: str | None, policy: dict | None = None) -> FraudReport`

- Runs 4 signals (same-day burst, monthly volume, high-value, duplicate)
- Returns `FraudReport(score, needs_manual_review, signals)`; `score` is capped at 1.0; `needs_manual_review` = any error-severity signal OR `score >= policy.fraud_thresholds.fraud_score_manual_review_threshold`
- Never raises on missing input — missing data just means fewer signals fire

---

## `orchestrator.graph`

### `run_graph(claim_input: dict, claim_id: str = "CLAIM", trace: bool = True) -> FinalDecision`

- **Input** `claim_input` shape:
  ```python
  {
    "member_id": "EMP001",
    "claim_category": "CONSULTATION",
    "treatment_date": "2024-11-01",
    "submission_date": "2024-11-05",       # optional; defaults to treatment_date
    "claimed_amount": 1500,
    "pre_auth_provided": False,             # optional
    "member_join_date": "2024-01-01",       # optional; falls back to policy.members[].join_date
    "claims_history": [...],                # optional; list of {date, amount} or similar
    "simulate_component_failure": False,    # optional; TC011
    "documents": [
      {"file_id": "F001", "actual_type": "PRESCRIPTION", "content": {...}},  # test path
      # or
      {"file_id": "F002", "actual_type": "HOSPITAL_BILL", "file_path": "/path/x.pdf"},
    ],
  }
  ```
- **Output** — `FinalDecision(claim_id, status, reason, confidence, claim, decision, stage_errors, notes, trace)` where
  - `status: DecisionStatus` ∈ `APPROVED | PARTIAL | REJECTED | MANUAL_REVIEW | NEEDS_REVIEW | NEEDS_REUPLOAD`
  - `confidence` ∈ `[0.0, 1.0]`, reduced by `0.3 × stage_errors + 0.1 × consistency_issues`
  - `trace: Trace | None` — full per-stage timing + events; `None` if called with `trace=False`
- **Raises** — never; all errors are captured into `stage_errors` and the final status degrades accordingly

### `build_graph() -> CompiledGraph`

Returns the compiled LangGraph. Pure; safe to call multiple times; cached in `run_graph`.

---

## `observability.trace`

### `Tracer(claim_id: str)`

- `span(stage, **attrs) -> context manager` — creates a `TraceSpan`, times it, sets it as the current span for `event()` calls; captures exceptions into `span.error` and re-raises
- `event(name, **attrs)` — appends a `TraceEvent` to the current span (or a synthetic `_root` span if none active)
- `annotate(**attrs)` — merges attrs into the current span's `attrs`
- `mark_skipped(stage, reason)` — records a zero-duration skipped span (for documenting "rules node didn't run because consistency errors")
- `finish() -> Trace` — closes out and returns the immutable `Trace` object

### `get_tracer() / set_tracer(tracer)`

Thread-local accessor for the current tracer. Used by `llm_adapters._traced` and the graph nodes so instrumentation doesn't need to be threaded through function args.

---

## `clients.llm_adapters`

### `call_text(prompt: str, schema: type[BaseModel] | dict | None = None) -> dict`
### `call_vision(prompt: str, images: list[tuple[bytes, str]], schema=None) -> dict`

- Dispatchers that pick a provider based on which API key is in the env
- Every call emits an `llm_call` trace event with `provider, model, kind, latency_ms, ok, error, input_tokens, output_tokens`
- **Raises** `RuntimeError` if no provider API key is set; propagates SDK errors otherwise

---

## Error inventory

| Error | Where raised | How handled |
|---|---|---|
| `UnsupportedFileTypeError` | `parse_document` | `parse` node captures → `StageError` → continues with other docs |
| `UnreadableDocumentError` | `parse_document` | **blocking** — graph routes to `finalize` → `NEEDS_REUPLOAD` |
| `WrongDocumentTypeError` | `parse_document` when expected type disagrees with classifier | **blocking** — graph routes to `finalize` → `NEEDS_REUPLOAD` |
| `ValidationError` (Pydantic) | `parse_from_dict`, extractor output parsing | `parse` node captures → `StageError` → document dropped |
| `ValueError` | `assemble_claim` on unknown category | `assemble` node would propagate; caller should validate category first |
| LLM SDK errors | any `call_text` / `call_vision` | Caller wraps in try/except; trace records `ok=false` with error string |
| `RuntimeError("No LLM API key set")` | `call_text` / `call_vision` dispatchers | Process-level config error; surfaces to the stage's `StageError` |
