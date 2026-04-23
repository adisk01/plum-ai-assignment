"""End-to-end tests for parse_document.

LLM calls are mocked. We verify:
  - TC001 parallel: wrong doc type raises WrongDocumentTypeError
  - TC002 parallel: unreadable doc raises UnreadableDocumentError
  - Happy path: classifies + extracts + returns a ParsedDocument
  - Unsupported extension raises UnsupportedFileTypeError
  - parse_from_dict: structured pass-through for test_cases.json
"""

import pytest

from claims_processor.document_extractor import parse
from claims_processor.document_extractor.exceptions import (
    DocumentClassificationError,
    UnreadableDocumentError,
    UnsupportedFileTypeError,
    WrongDocumentTypeError,
)
from claims_processor.models.documents import DocType


def test_unsupported_extension_raises():
    with pytest.raises(UnsupportedFileTypeError):
        parse.parse_document(b"irrelevant", ".tiff", file_id="F001")


def test_wrong_document_type_is_raised(mocker):
    # Force the image path and mock classifier
    mocker.patch.object(
        parse.cls,
        "classify_from_image",
        return_value={
            "doc_type": DocType.PRESCRIPTION,
            "confidence": 0.9,
            "readable": True,
            "reason": "has Rx",
        },
    )
    with pytest.raises(WrongDocumentTypeError) as err:
        parse.parse_document(
            file_bytes=b"\xff\xd8\xff\xe0fake",
            file_ext=".jpg",
            file_id="F001",
            expected_type=DocType.HOSPITAL_BILL,
        )
    assert err.value.expected == "HOSPITAL_BILL"
    assert err.value.got == "PRESCRIPTION"


def test_unreadable_document_is_raised(mocker):
    mocker.patch.object(
        parse.cls,
        "classify_from_image",
        return_value={
            "doc_type": DocType.PHARMACY_BILL,
            "confidence": 0.3,
            "readable": False,
            "reason": "blurry",
        },
    )
    with pytest.raises(UnreadableDocumentError) as err:
        parse.parse_document(
            file_bytes=b"\xff\xd8\xff\xe0",
            file_ext=".jpg",
            file_id="F004",
            expected_type=DocType.PHARMACY_BILL,
        )
    assert err.value.file_id == "F004"


def test_unknown_type_raises_classification_error(mocker):
    mocker.patch.object(
        parse.cls,
        "classify_from_image",
        return_value={
            "doc_type": DocType.UNKNOWN,
            "confidence": 0.1,
            "readable": True,
            "reason": "not a medical document",
        },
    )
    with pytest.raises(DocumentClassificationError):
        parse.parse_document(b"x", ".jpg", file_id="F009")


def test_happy_path_prescription_image(mocker):
    mocker.patch.object(
        parse.cls,
        "classify_from_image",
        return_value={
            "doc_type": DocType.PRESCRIPTION,
            "confidence": 0.92,
            "readable": True,
            "reason": "Rx layout detected",
        },
    )
    mocker.patch.object(
        parse.ext,
        "extract_from_image",
        return_value=(
            _fake_prescription_body(),
            {"patient_name": 0.95, "diagnosis": 0.88},
        ),
    )

    result = parse.parse_document(
        file_bytes=b"\xff\xd8\xff\xe0fake",
        file_ext=".jpg",
        file_id="F007",
        expected_type=DocType.PRESCRIPTION,
    )

    assert result.file_id == "F007"
    assert result.doc_type == DocType.PRESCRIPTION
    assert result.extracted.patient_name == "Rajesh Kumar"
    assert result.extracted.doctor_registration_valid is True
    assert result.extracted.doctor_registration_state == "KA"
    assert 0.0 < result.overall_confidence <= 1.0


def test_parse_from_dict_happy_path():
    result = parse.parse_from_dict(
        file_id="F008",
        doc_type=DocType.HOSPITAL_BILL,
        content={
            "hospital_name": "City Clinic, Bengaluru",
            "patient_name": "Rajesh Kumar",
            "date": "2024-11-01",
            "total": 1500,
            "line_items": [
                {"description": "Consultation Fee", "amount": 1000},
                {"description": "CBC Test", "amount": 300},
                {"description": "Dengue NS1 Test", "amount": 200},
            ],
        },
    )
    assert result.doc_type == DocType.HOSPITAL_BILL
    assert len(result.extracted.line_items) == 3
    assert result.extracted.total == 1500


def test_parse_from_dict_wrong_expected_type_raises():
    with pytest.raises(WrongDocumentTypeError):
        parse.parse_from_dict(
            file_id="F001",
            doc_type=DocType.PRESCRIPTION,
            content={},
            expected_type=DocType.HOSPITAL_BILL,
        )


# ---- helpers -------------------------------------------------------------


def _fake_prescription_body():
    from claims_processor.models.documents import Prescription

    rx = Prescription(
        doctor_name="Dr. Arun Sharma",
        doctor_registration="KA/45678/2015",
        patient_name="Rajesh Kumar",
        date="2024-11-01",
        diagnosis="Viral Fever",
    )
    rx.fill_registration_metadata()
    return rx
