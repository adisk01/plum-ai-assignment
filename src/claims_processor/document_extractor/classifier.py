"""Classify a document into one of the 7 claim doc types.

Routes to the text LLM for text-native PDFs and to the vision LLM for
images and scanned PDFs.
"""

from __future__ import annotations

from typing import Any

from claims_processor.clients import llm_adapters
from claims_processor.models.documents import DocType
from claims_processor.prompts.classifier_prompt import build_classifier_prompt


def _coerce_doc_type(value: str | None) -> DocType:
    if not value:
        return DocType.UNKNOWN
    try:
        return DocType(value.upper())
    except ValueError:
        return DocType.UNKNOWN


def _coerce_confidence(value: Any) -> float:
    try:
        c = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, c))


def classify_from_text(text: str) -> dict[str, Any]:
    """Classify a text-native document.

    Returns {doc_type: DocType, confidence: float, reason: str, readable: bool}.
    """
    prompt = build_classifier_prompt(text)
    raw = llm_adapters.call_text_json(prompt)
    return _normalize_classifier_response(raw)


def classify_from_image(image_bytes: bytes, ext: str) -> dict[str, Any]:
    """Classify a document from its image bytes via the vision LLM."""
    prompt = build_classifier_prompt(content="")
    raw = llm_adapters.call_vision_json(prompt, images=[(image_bytes, ext)])
    return _normalize_classifier_response(raw)


def _normalize_classifier_response(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "doc_type": _coerce_doc_type(raw.get("doc_type")),
        "confidence": _coerce_confidence(raw.get("confidence")),
        "reason": str(raw.get("reason") or "").strip(),
        "readable": bool(raw.get("readable", True)),
    }
