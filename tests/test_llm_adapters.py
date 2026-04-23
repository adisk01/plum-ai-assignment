"""Tests for llm_adapters: helpers + routing logic.

Real SDK calls are avoided; provider selection is tested directly, and
parse helpers are tested on their own so we don't need API keys to run.
"""

import pytest

from claims_processor.clients import llm_adapters as la


def test_ext_to_media_type():
    assert la._ext_to_media_type(".jpg") == "image/jpeg"
    assert la._ext_to_media_type("JPEG") == "image/jpeg"
    assert la._ext_to_media_type(".png") == "image/png"
    assert la._ext_to_media_type(".pdf") == "application/pdf"
    assert la._ext_to_media_type(".xyz") == "application/octet-stream"


def test_b64_roundtrip():
    assert la._b64(b"hello") == "aGVsbG8="


def test_strip_json_fences_plain():
    assert la._strip_json_fences('{"a": 1}') == '{"a": 1}'


def test_strip_json_fences_with_marker():
    fenced = '```json\n{"a": 1}\n```'
    assert la._strip_json_fences(fenced) == '{"a": 1}'


def test_strip_json_fences_bare_ticks():
    fenced = '```\n{"a": 1}\n```'
    assert la._strip_json_fences(fenced) == '{"a": 1}'


def test_parse_json_or_raise_valid():
    assert la._parse_json_or_raise('{"x": 2}', "test") == {"x": 2}


def test_parse_json_or_raise_invalid():
    with pytest.raises(la.LLMAdapterError):
        la._parse_json_or_raise("not json", "test")


def test_call_vision_json_rejects_unknown_provider(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    with pytest.raises(ValueError):
        la.call_vision_json("prompt", images=[(b"x", ".jpg")], provider="cohere")


def test_call_text_json_raises_when_no_keys(monkeypatch):
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.delenv("TEXT_PROVIDER", raising=False)
    with pytest.raises(RuntimeError, match="No LLM provider"):
        la.call_text_json("prompt")


def test_call_text_json_prefers_groq(monkeypatch, mocker):
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "fake")
    monkeypatch.delenv("TEXT_PROVIDER", raising=False)
    mock_call = mocker.patch.object(la, "call_groq_json", return_value={"ok": True})
    result = la.call_text_json("hi")
    assert result == {"ok": True}
    mock_call.assert_called_once()


def test_call_vision_json_prefers_anthropic(monkeypatch, mocker):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    monkeypatch.delenv("VISION_PROVIDER", raising=False)
    mock_call = mocker.patch.object(la, "call_anthropic_json", return_value={"ok": True})
    result = la.call_vision_json("hi", images=[(b"x", ".jpg")])
    assert result == {"ok": True}
    mock_call.assert_called_once()
