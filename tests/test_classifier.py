"""Tests for the document classifier.

The LLM is mocked. We verify:
  1. Response normalization (doc_type enum, clamped confidence, defaults)
  2. Routing: text path vs vision path
"""

import pytest

from claims_processor.document_extractor import classifier
from claims_processor.models.documents import DocType


def test_normalize_valid_response():
    raw = {"doc_type": "PRESCRIPTION", "confidence": 0.92, "reason": "has Rx", "readable": True}
    out = classifier._normalize_classifier_response(raw)
    assert out["doc_type"] == DocType.PRESCRIPTION
    assert out["confidence"] == 0.92
    assert out["readable"] is True
    assert out["reason"] == "has Rx"


def test_normalize_unknown_type_defaults():
    raw = {"doc_type": "BOGUS", "confidence": 1.5}
    out = classifier._normalize_classifier_response(raw)
    assert out["doc_type"] == DocType.UNKNOWN
    assert out["confidence"] == 1.0


def test_normalize_missing_fields_defaults():
    out = classifier._normalize_classifier_response({})
    assert out["doc_type"] == DocType.UNKNOWN
    assert out["confidence"] == 0.0
    assert out["reason"] == ""
    assert out["readable"] is True


def test_classify_from_text_routes_to_text_llm(mocker):
    mock_call = mocker.patch.object(
        classifier.llm_adapters,
        "call_text_json",
        return_value={"doc_type": "HOSPITAL_BILL", "confidence": 0.88, "readable": True},
    )
    result = classifier.classify_from_text("Bill No. CMC/2024/08321 Total: 1500")
    assert result["doc_type"] == DocType.HOSPITAL_BILL
    mock_call.assert_called_once()
    # Ensure the prompt contains the document content
    args, _ = mock_call.call_args
    assert "1500" in args[0]


def test_classify_from_image_routes_to_vision_llm(mocker):
    mock_call = mocker.patch.object(
        classifier.llm_adapters,
        "call_vision_json",
        return_value={"doc_type": "PRESCRIPTION", "confidence": 0.77, "readable": True},
    )
    result = classifier.classify_from_image(b"\x89PNGfake", ".png")
    assert result["doc_type"] == DocType.PRESCRIPTION
    mock_call.assert_called_once()
    # Verify the image tuple was passed
    _, kwargs = mock_call.call_args
    assert kwargs["images"] == [(b"\x89PNGfake", ".png")]


def test_classify_from_image_flags_unreadable(mocker):
    mocker.patch.object(
        classifier.llm_adapters,
        "call_vision_json",
        return_value={
            "doc_type": "PHARMACY_BILL",
            "confidence": 0.3,
            "readable": False,
            "reason": "severe blur",
        },
    )
    result = classifier.classify_from_image(b"x", ".jpg")
    assert result["doc_type"] == DocType.PHARMACY_BILL
    assert result["readable"] is False
