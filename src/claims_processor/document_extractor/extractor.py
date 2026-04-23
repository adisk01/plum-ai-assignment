"""Field extraction for a classified document.

For a given doc_type, builds the right prompt, calls the LLM, validates
the response against the typed Pydantic schema, and returns a
ParsedDocument wrapping the typed body + confidence metadata.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import ValidationError

from claims_processor.clients import llm_adapters
from claims_processor.document_extractor import tables as tbl
from claims_processor.models.documents import (
    DocType,
    HospitalBill,
    LineItem,
    ParsedDocument,
    Prescription,
    SCHEMA_FOR_DOC_TYPE,
)
from claims_processor.prompts.extractor_prompts import build_extract_prompt


def extract_from_text(doc_type: DocType, text: str) -> tuple[Any, dict[str, float]]:
    """Extract fields from a text-native document.

    Returns (typed_pydantic_body, field_confidence_dict).
    """
    return _extract(doc_type, text=text, images=None)


def extract_from_image(
    doc_type: DocType, image_bytes: bytes, ext: str
) -> tuple[Any, dict[str, float]]:
    return _extract(doc_type, text="", images=[(image_bytes, ext)])


def _extract(
    doc_type: DocType,
    text: str,
    images: list[tuple[bytes, str]] | None,
) -> tuple[Any, dict[str, float]]:
    prompt = build_extract_prompt(doc_type, text)

    if images:
        raw = llm_adapters.call_vision_json(prompt, images=images)
    else:
        raw = llm_adapters.call_text_json(prompt)

    return _validate_response(doc_type, raw)


def _validate_response(
    doc_type: DocType, raw: dict[str, Any]
) -> tuple[Any, dict[str, float]]:
    schema = SCHEMA_FOR_DOC_TYPE[doc_type]
    field_confidence = _extract_field_confidence(raw)

    # Drop field_confidence from the payload before pydantic validation
    payload = {k: v for k, v in raw.items() if k != "field_confidence"}

    try:
        body = schema(**payload)
    except ValidationError as e:
        # Attempt a lenient retry: strip unknown fields + default required numeric fields
        body = _lenient_validate(schema, payload, e)

    # Prescription: fill registration-number validation metadata
    if isinstance(body, Prescription):
        body.fill_registration_metadata()

    return body, field_confidence


def _extract_field_confidence(raw: dict[str, Any]) -> dict[str, float]:
    fc = raw.get("field_confidence") or {}
    out: dict[str, float] = {}
    if isinstance(fc, dict):
        for k, v in fc.items():
            try:
                out[str(k)] = max(0.0, min(1.0, float(v)))
            except (TypeError, ValueError):
                continue
    return out


def _lenient_validate(schema, payload: dict[str, Any], original_err: ValidationError):
    """Drop unknown fields and retry. If the schema requires `total` and it's
    missing / invalid, set it to 0 and rely on downstream checks to flag it.
    """
    allowed = set(schema.model_fields.keys())
    cleaned = {k: v for k, v in payload.items() if k in allowed}

    # Hospital / pharmacy bills require total; supply 0 if missing so callers
    # can still see the partially-parsed body rather than a hard crash.
    if "total" in allowed and "total" not in cleaned:
        cleaned["total"] = 0

    try:
        return schema(**cleaned)
    except ValidationError:
        # Fall back to constructing with defaults + zero total
        safe = {k: None for k in allowed}
        if "total" in allowed:
            safe["total"] = 0
        return schema(**{k: v for k, v in safe.items() if k != "line_items"})


# ---------------------------------------------------------------------------
# Line-item augmentation for HOSPITAL_BILL PDFs
# ---------------------------------------------------------------------------


def augment_bill_with_pdf_tables(bill: HospitalBill, pdf_bytes: bytes) -> HospitalBill:
    """If pdfplumber finds line items in the PDF, merge them into the bill.

    The LLM-extracted line items are trusted first; pdfplumber fills any gap
    when the LLM missed an itemization.
    """
    if bill.line_items:
        return bill

    pdf_items = tbl.extract_line_items_from_pdf_bytes(pdf_bytes)
    if not pdf_items:
        return bill

    merged: list[LineItem] = []
    for item in pdf_items:
        try:
            merged.append(
                LineItem(
                    description=item["description"],
                    quantity=item.get("quantity"),
                    rate=Decimal(str(item["rate"])) if item.get("rate") is not None else None,
                    amount=Decimal(str(item["amount"])),
                )
            )
        except Exception:
            continue
    bill.line_items = merged
    return bill


# ---------------------------------------------------------------------------
# Overall confidence scoring
# ---------------------------------------------------------------------------


def compute_overall_confidence(
    field_confidence: dict[str, float],
    classifier_confidence: float,
    readable: bool,
) -> float:
    """Blend per-field LLM confidence with classifier confidence + readability.

    Simple weighted average; favours field-level signals when present.
    """
    base = 0.0
    if field_confidence:
        base = sum(field_confidence.values()) / len(field_confidence)
    else:
        base = classifier_confidence

    score = 0.7 * base + 0.3 * classifier_confidence
    if not readable:
        score *= 0.5
    return max(0.0, min(1.0, score))


def build_parsed_document(
    file_id: str,
    doc_type: DocType,
    body: Any,
    field_confidence: dict[str, float],
    classifier_confidence: float,
    readable: bool,
    warnings: list[str] | None = None,
    raw_text_preview: str | None = None,
) -> ParsedDocument:
    overall = compute_overall_confidence(field_confidence, classifier_confidence, readable)
    return ParsedDocument(
        file_id=file_id,
        doc_type=doc_type,
        extracted=body,
        field_confidence=field_confidence,
        overall_confidence=overall,
        warnings=list(warnings or []),
        raw_text_preview=raw_text_preview,
    )
