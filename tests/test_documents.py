"""Tests for Pydantic document schemas."""

from decimal import Decimal

import pytest

from claims_processor.models import documents as d


def test_doctor_registration_karnataka():
    valid, state = d.validate_doctor_registration("KA/45678/2015")
    assert valid
    assert state == "KA"


def test_doctor_registration_ayurveda():
    valid, state = d.validate_doctor_registration("AYUR/KL/2345/2019")
    assert valid
    assert state == "AYUR"


def test_doctor_registration_invalid():
    assert d.validate_doctor_registration("random") == (False, None)
    assert d.validate_doctor_registration(None) == (False, None)
    assert d.validate_doctor_registration("") == (False, None)


def test_prescription_fills_registration_metadata():
    rx = d.Prescription(doctor_registration="MH/23456/2018")
    rx.fill_registration_metadata()
    assert rx.doctor_registration_valid is True
    assert rx.doctor_registration_state == "MH"


def test_hospital_bill_requires_total():
    with pytest.raises(ValueError):
        d.HospitalBill()  # total is required


def test_hospital_bill_coerces_decimal():
    bill = d.HospitalBill(total="1500")
    assert bill.total == Decimal("1500")
    assert isinstance(bill.total, Decimal)


def test_line_item_roundtrip():
    li = d.LineItem(description="Consultation", amount=1000)
    assert li.amount == Decimal("1000")


def test_parsed_document_clamps_confidence():
    p = d.ParsedDocument(
        file_id="F001",
        doc_type=d.DocType.PRESCRIPTION,
        overall_confidence=1.5,
    )
    assert p.overall_confidence == 1.0
    q = d.ParsedDocument(
        file_id="F002",
        doc_type=d.DocType.PRESCRIPTION,
        overall_confidence=-0.3,
    )
    assert q.overall_confidence == 0.0


def test_schema_for_doc_type_complete():
    # Every non-UNKNOWN doc type must have an extraction schema
    for dt in d.DocType:
        if dt == d.DocType.UNKNOWN:
            continue
        assert dt in d.SCHEMA_FOR_DOC_TYPE, f"Missing schema for {dt}"
