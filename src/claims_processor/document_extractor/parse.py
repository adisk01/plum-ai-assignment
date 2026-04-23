"""Entry point for the document extractor.

    parsed = parse_document(
        file_bytes=open("bill.pdf", "rb").read(),
        file_ext=".pdf",
        file_id="F001",
        expected_type=DocType.HOSPITAL_BILL,
    )
"""

from claims_processor.document_extractor import classifier, extractor, pdf_utils
from claims_processor.document_extractor.exceptions import (
    UnreadableDocumentError,
    UnsupportedFileTypeError,
    WrongDocumentTypeError,
)
from claims_processor.models.documents import DocType, ParsedDocument, SCHEMA_FOR_DOC_TYPE


SUPPORTED_EXTS = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".gif"}


def parse_document(file_bytes, file_ext, file_id, expected_type=None):
    ext = file_ext.lower()
    if not ext.startswith("."):
        ext = "." + ext
    if ext not in SUPPORTED_EXTS:
        raise UnsupportedFileTypeError(ext)

    # Use text path for text-native PDFs, vision otherwise
    text = ""
    use_vision = True
    if ext == ".pdf":
        pages = pdf_utils.extract_pages_from_pdf_bytes(file_bytes)
        text = "\n\n".join(p.text for p in pages if p.text)
        if len(text) >= 50:
            use_vision = False

    if use_vision:
        cls = classifier.classify_from_image(file_bytes, ext)
    else:
        cls = classifier.classify_from_text(text)

    if cls.doc_type == DocType.UNKNOWN:
        raise UnreadableDocumentError(file_id, cls.reason or "could not classify")

    if expected_type and cls.doc_type != expected_type:
        raise WrongDocumentTypeError(file_id, expected_type.value, cls.doc_type.value)

    if not cls.readable:
        raise UnreadableDocumentError(file_id, cls.reason or "document unreadable")

    if use_vision:
        body = extractor.extract_from_image(cls.doc_type, file_bytes, ext)
    else:
        body = extractor.extract_from_text(cls.doc_type, text)

    return ParsedDocument(
        file_id=file_id,
        doc_type=cls.doc_type,
        extracted=body,
        confidence=cls.confidence,
    )


def parse_from_dict(file_id, doc_type, content, expected_type=None):
    """Build a ParsedDocument from pre-extracted content (for test_cases.json).

    Tolerant of simplified shapes: e.g. medicines as ["name 500mg", ...] become
    [{"name": "..."}], tests as plain strings become {"name": "..."}.
    """
    if expected_type and doc_type != expected_type:
        raise WrongDocumentTypeError(file_id, expected_type.value, doc_type.value)
    schema = SCHEMA_FOR_DOC_TYPE[doc_type]

    def _coerce(key, val):
        if key == "medicines" and isinstance(val, list):
            return [{"name": v} if isinstance(v, str) else v for v in val]
        if key == "tests" and isinstance(val, list):
            return [{"name": v} if isinstance(v, str) else v for v in val]
        if key == "line_items" and isinstance(val, list):
            # require description + amount; pass through dicts as-is
            return [v for v in val if isinstance(v, dict)]
        return val

    kwargs = {k: _coerce(k, v) for k, v in content.items() if k in schema.model_fields}
    body = schema(**kwargs)
    return ParsedDocument(file_id=file_id, doc_type=doc_type, extracted=body, confidence=1.0)
