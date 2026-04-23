# Plum AI — Health Insurance Claims Processing

Automated claims processing system for the Plum AI Engineer assignment. Processes health insurance claims end-to-end: document verification, field extraction, policy evaluation, and explainable decisions.

See [`PROBLEM_STATEMENT/assignment.md`](PROBLEM_STATEMENT/assignment.md) for the full brief.

---

## Setup

### 1. Python environment

Requires **Python 3.10+**.

```bash
python -m venv .venv
source .venv/bin/activate       # macOS / Linux
pip install -r requirements.txt
```

### 2. API keys

Copy `.env.example` to `.env` and fill in at least one LLM provider key:

```bash
cp .env.example .env
# edit .env and add your ANTHROPIC_API_KEY (recommended)
```

Supported providers: **Anthropic** (default for vision), **OpenAI**, **Groq** (text-only). You only need one configured to run.

### 3. Run tests

```bash
pytest
```

All LLM calls in tests are mocked, so no API key is needed for `pytest`.

---

## CLI — parse a single document

Generate small sample PDFs (one-time):

```bash
python tests/fixtures/make_fixtures.py
```

Parse end-to-end and print the `ParsedDocument` JSON:

```bash
python scripts/parse_one.py tests/fixtures/sample_docs/prescription.pdf --pretty
python scripts/parse_one.py tests/fixtures/sample_docs/hospital_bill.pdf --expected HOSPITAL_BILL --pretty
```

Flags:
- `--expected <DOC_TYPE>` — enforces the expected document type (raises `WrongDocumentTypeError` on mismatch, matching test case TC001).
- `--file-id <id>` — synthetic identifier for the output payload.
- `--pretty` — pretty-print JSON.

Supported inputs: `.pdf, .jpg, .jpeg, .png, .webp, .gif`.

---

## Project Structure

```
src/claims_processor/
  clients/             # LLM adapter functions (OpenAI / Anthropic / Groq)
  core/                # Config + policy_terms loader
  models/              # Pydantic schemas (documents, claims)
  prompts/             # Prompt templates per task
  document_extractor/  # Layer 1 — document parsing & extraction
scripts/               # CLI entry points
tests/                 # Unit tests + programmatic fixtures
  fixtures/
    make_fixtures.py   # generates sample PDFs
    sample_docs/       # generated artefacts (git-ignored content)
```

---

## Layer 1 — Document Extractor (done)

Entry point: `claims_processor.document_extractor.parse.parse_document`.

Flow:
1. Validate extension → `UnsupportedFileTypeError`
2. Text-native PDFs use pypdfium2 text; scanned PDFs and images go through a vision LLM
3. Classify into one of 7 medical doc types (the Pydantic `ClassifierResponse` schema is passed to the LLM as `response_format`)
4. Enforce expected type (TC001 → `WrongDocumentTypeError`)
5. Enforce readability (TC002 → `UnreadableDocumentError`)
6. Extract typed fields by passing the per-doc-type Pydantic schema to the LLM adapter

Supported doc types: `PRESCRIPTION, HOSPITAL_BILL, PHARMACY_BILL, LAB_REPORT, DIAGNOSTIC_REPORT, DENTAL_REPORT, DISCHARGE_SUMMARY`.

---

## Status

- **Layer 1 — Document Extractor** — done on branch `feat/document-extractor`.
- **Layer 2+** (cross-document consistency, rules engine, decision agent, workflow orchestration, API/UI) — pending on subsequent feature branches.
