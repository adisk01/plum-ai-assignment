"""Unit tests for extractor helper modules (no external APIs)."""

import pytest

from claims_processor.document_extractor import exceptions as ex
from claims_processor.document_extractor import image_utils as iu
from claims_processor.document_extractor import tables


# ---- image_utils ---------------------------------------------------------


def test_normalize_ext():
    assert iu.normalize_ext("JPG") == ".jpg"
    assert iu.normalize_ext(".PDF") == ".pdf"
    assert iu.normalize_ext("png") == ".png"


def test_is_supported_ext():
    assert iu.is_supported_ext(".pdf")
    assert iu.is_supported_ext("JPG")
    assert iu.is_supported_ext(".webp")
    assert not iu.is_supported_ext(".tiff")
    assert not iu.is_supported_ext(".exe")


def test_is_image_vs_pdf():
    assert iu.is_image_ext(".png")
    assert not iu.is_image_ext(".pdf")
    assert iu.is_pdf_ext(".pdf")
    assert not iu.is_pdf_ext(".jpg")


# ---- exceptions ----------------------------------------------------------


def test_unsupported_file_type_error_mentions_ext():
    err = ex.UnsupportedFileTypeError(".tiff")
    assert ".tiff" in str(err)


def test_wrong_document_type_error_default_message():
    err = ex.WrongDocumentTypeError(
        file_id="F001", expected="HOSPITAL_BILL", got="PRESCRIPTION"
    )
    assert err.expected == "HOSPITAL_BILL"
    assert err.got == "PRESCRIPTION"
    assert "HOSPITAL_BILL" in err.user_message
    assert "PRESCRIPTION" in err.user_message


def test_unreadable_document_error_has_suggestion():
    err = ex.UnreadableDocumentError(file_id="F004", reason="blurry photo")
    assert err.suggestion
    assert err.file_id == "F004"


# ---- tables ---------------------------------------------------------------


def test_extract_line_items_empty_on_bad_bytes():
    # pdfplumber opening garbage bytes must not crash
    assert tables.extract_line_items_from_pdf_bytes(b"not a pdf") == []


def test_looks_like_billing_table_positive():
    assert tables._looks_like_billing_table(["description", "qty", "rate", "amount"])
    assert tables._looks_like_billing_table(["medicine", "mrp", "amt"])


def test_looks_like_billing_table_negative():
    assert not tables._looks_like_billing_table(["date", "time", "note"])


def test_row_to_line_item_minimal():
    row = tables._row_to_line_item(
        ["description", "amount"], ["Consultation Fee", "1000"]
    )
    assert row == {
        "description": "Consultation Fee",
        "quantity": None,
        "rate": None,
        "amount": 1000.0,
    }


def test_row_to_line_item_rejects_missing_amount():
    row = tables._row_to_line_item(
        ["description", "amount"], ["Consultation", ""]
    )
    assert row is None


def test_try_number_handles_rupee_and_commas():
    assert tables._try_number("₹1,500.00") == 1500.0
    assert tables._try_number("bad") is None
    assert tables._try_number("") is None
