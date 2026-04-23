"""Tests for parse_document.

LLM calls are mocked. Covers the happy path and the two error gates.
"""

import pytest

from claims_processor.document_extractor import parse
from claims_processor.document_extractor.exceptions import (
    UnreadableDocumentError,
    UnsupportedFileTypeError,
    WrongDocumentTypeError,
)
from claims_processor.models.documents import (
    ClassifierResponse,
    DocType,
    HospitalBill,
    Prescription,
)


def test_unsupported_extension():
    with pytest.raises(UnsupportedFileTypeError):
        parse.parse_document(b"x", ".tiff", file_id="F001")


def test_wrong_document_type(mocker):
    mocker.patch.object(
        parse.classifier,
        "classify_from_image",
        return_value=ClassifierResponse(doc_type=DocType.PRESCRIPTION, confidence=0.9),
    )
    with pytest.raises(WrongDocumentTypeError):
        parse.parse_document(b"x", ".jpg", file_id="F001", expected_type=DocType.HOSPITAL_BILL)


def test_unreadable_document(mocker):
    mocker.patch.object(
        parse.classifier,
        "classify_from_image",
        return_value=ClassifierResponse(
            doc_type=DocType.PHARMACY_BILL, confidence=0.3, readable=False, reason="blurry"
        ),
    )
    with pytest.raises(UnreadableDocumentError):
        parse.parse_document(b"x", ".jpg", file_id="F004")


def test_happy_path_image(mocker):
    mocker.patch.object(
        parse.classifier,
        "classify_from_image",
        return_value=ClassifierResponse(doc_type=DocType.PRESCRIPTION, confidence=0.9),
    )
    mocker.patch.object(
        parse.extractor,
        "extract_from_image",
        return_value=Prescription(patient_name="Rajesh Kumar", diagnosis="Viral Fever"),
    )
    result = parse.parse_document(b"x", ".jpg", file_id="F007")
    assert result.doc_type == DocType.PRESCRIPTION
    assert result.extracted.patient_name == "Rajesh Kumar"


def test_parse_from_dict():
    result = parse.parse_from_dict(
        file_id="F008",
        doc_type=DocType.HOSPITAL_BILL,
        content={
            "hospital_name": "City Clinic",
            "patient_name": "Rajesh Kumar",
            "total": 1500,
            "line_items": [
                {"description": "Consultation", "amount": 1000},
                {"description": "CBC", "amount": 500},
            ],
        },
    )
    assert isinstance(result.extracted, HospitalBill)
    assert result.extracted.total == 1500
    assert len(result.extracted.line_items) == 2


def test_parse_from_dict_wrong_expected():
    with pytest.raises(WrongDocumentTypeError):
        parse.parse_from_dict(
            file_id="F001",
            doc_type=DocType.PRESCRIPTION,
            content={},
            expected_type=DocType.HOSPITAL_BILL,
        )
