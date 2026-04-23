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

Supported providers: **Anthropic** (default for vision), **OpenAI**, **Groq**. You only need one configured to run.

### 3. Run tests

```bash
pytest
```

---

## Project Structure

```
src/claims_processor/
  clients/             # LLM adapter functions (OpenAI / Anthropic / Groq)
  core/                # Config + policy_terms loader
  models/              # Pydantic schemas (documents, claims)
  prompts/             # Prompt templates per task
  document_extractor/  # Layer 1 — document parsing & extraction
```

---

## Status

Layer 1 — Document Extractor — in progress on branch `feat/document-extractor`.

Downstream layers (cross-document consistency, rules engine, decision agent, workflow orchestration, UI) will land on subsequent feature branches.
