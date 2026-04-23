"""Public entry point for the document extractor layer.

Usage:
    from claims_processor.document_extractor.parse import parse_document

    parsed = parse_document(
        file_bytes=open("bill.pdf", "rb").read(),
        file_ext=".pdf",
        file_id="F001",
        expected_type=DocType.HOSPITAL_BILL,
    )

Flow:
  1. Validate extension  → UnsupportedFileTypeError
  2. PDF: extract pages; Image: hold bytes as-is
  3. Classify            → DocumentClassificationError if UNKNOWN
  4. If expected_type set and actual != expected → WrongDocumentTypeError (TC001)
  5. If classifier says unreadable               → UnreadableDocumentError (TC002)
  6. Extract fields with the correct schema      → ParsedDocument
"""

from __future__ import annotations

from claims_processor.document_extractor import classifier as cls
from claims_processor.document_extractor import extractor as ext
from claims_processor.document_extractor import image_utils as iu
from claims_processor.document_extractor import pdf_utils
from claims_processor.document_extractor.exceptions import (
    DocumentClassificationError,
    UnreadableDocumentError,
    UnsupportedFileTypeError,
    WrongDocumentTypeError,
)
from claims_processor.models.documents import DocType, HospitalBill, ParsedDocument


# Pass pre-extracted dict content through these known test cases without
# invoking an LLM. Used by the eval harness (test_cases.json).
def parse_from_dict(
    file_id: str,
    doc_type: DocType,
    content: dict,
    expected_type: DocType | None = None,
) -> ParsedDocument:
    """Build a ParsedDocument from already-structured content (eval path)."""
    if expected_type and doc_type != expected_type:
        raise WrongDocumentTypeError(
            file_id=file_id, expected=expected_type.value, got=doc_type.value
        )
    from claims_processor.models.documents import SCHEMA_FOR_DOC_TYPE

    schema = SCHEMA_FOR_DOC_TYPE[doc_type]
    body = schema(**{k: v for k, v in content.items() if k in schema.model_fields})
    return ext.build_parsed_document(
        file_id=file_id,
        doc_type=doc_type,
        body=body,
        field_confidence={},
        classifier_confidence=1.0,
        readable=True,
    )


def parse_document(
    file_bytes: bytes,
    file_ext: str,
    file_id: str,
    expected_type: DocType | None = None,
) -> ParsedDocument:
    """End-to-end extraction for one uploaded document."""
    ext_norm = iu.normalize_ext(file_ext)
    if not iu.is_supported_ext(ext_norm):
        raise UnsupportedFileTypeError(ext_norm)

    warnings: list[str] = []
    raw_text_preview: str | None = None

    # Step 1 — get text (PDF) or prepare bytes (image)
    use_vision = True
    pdf_text = ""
    if iu.is_pdf_ext(ext_norm):
        pages = pdf_utils.extract_pages_from_pdf_bytes(file_bytes)
        if pdf_utils.is_text_native_pdf(pages):
            pdf_text = pdf_utils.concat_pages(pages)
            raw_text_preview = pdf_text[:500]
            use_vision = False

    # Step 2 — classify
    if use_vision:
        class_result = cls.classify_from_image(file_bytes, ext_norm)
    else:
        class_result = cls.classify_from_text(pdf_text)

    doc_type: DocType = class_result["doc_type"]
    readable: bool = class_result["readable"]
    classifier_conf: float = class_result["confidence"]

    if doc_type == DocType.UNKNOWN:
        raise DocumentClassificationError(
            file_id=file_id,
            reason=class_result.get("reason") or "document did not match any known type",
        )

    # Step 3 — wrong-type gate (TC001)
    if expected_type and doc_type != expected_type:
        raise WrongDocumentTypeError(
            file_id=file_id,
            expected=expected_type.value,
            got=doc_type.value,
        )

    # Step 4 — readability gate (TC002)
    if not readable:
        raise UnreadableDocumentError(
            file_id=file_id,
            reason=class_result.get("reason") or "document appears unreadable",
        )

    # Step 5 — extract fields
    if use_vision:
        body, field_confidence = ext.extract_from_image(doc_type, file_bytes, ext_norm)
    else:
        body, field_confidence = ext.extract_from_text(doc_type, pdf_text)

    # Step 6 — augment hospital bill line items from pdfplumber when empty
    if (
        doc_type == DocType.HOSPITAL_BILL
        and iu.is_pdf_ext(ext_norm)
        and isinstance(body, HospitalBill)
    ):
        body = ext.augment_bill_with_pdf_tables(body, file_bytes)

    return ext.build_parsed_document(
        file_id=file_id,
        doc_type=doc_type,
        body=body,
        field_confidence=field_confidence,
        classifier_confidence=classifier_conf,
        readable=readable,
        warnings=warnings,
        raw_text_preview=raw_text_preview,
    )
