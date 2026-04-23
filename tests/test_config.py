"""Tests for core.config: env loading + policy_terms parsing."""

import os

import pytest

from claims_processor.core import config


def test_policy_terms_loads():
    policy = config.load_policy_terms()
    assert policy["policy_id"] == "PLUM_GHI_2024"
    assert "document_requirements" in policy
    assert "members" in policy


def test_consultation_requirements():
    reqs = config.get_document_requirements("CONSULTATION")
    assert reqs["required"] == ["PRESCRIPTION", "HOSPITAL_BILL"]
    assert "LAB_REPORT" in reqs["optional"]


def test_claim_category_is_case_insensitive():
    upper = config.get_document_requirements("PHARMACY")
    lower = config.get_document_requirements("pharmacy")
    assert upper == lower


def test_unknown_category_raises():
    with pytest.raises(KeyError):
        config.get_document_requirements("UNKNOWN_CATEGORY")


def test_list_claim_categories():
    categories = config.list_claim_categories()
    assert "CONSULTATION" in categories
    assert "DENTAL" in categories
    assert "PHARMACY" in categories


def test_get_env_required_missing(monkeypatch):
    monkeypatch.delenv("DEFINITELY_NOT_SET_XYZ", raising=False)
    with pytest.raises(RuntimeError, match="DEFINITELY_NOT_SET_XYZ"):
        config.get_env("DEFINITELY_NOT_SET_XYZ", required=True)


def test_get_env_returns_default_when_missing(monkeypatch):
    monkeypatch.delenv("DEFINITELY_NOT_SET_XYZ", raising=False)
    assert config.get_env("DEFINITELY_NOT_SET_XYZ", default="fallback") == "fallback"
