"""Thin, function-based adapters over OpenAI, Anthropic, and Groq SDKs.

Design rules:
- One function per (provider, modality). No classes, no registries.
- All functions return a validated Python dict (JSON-parsed LLM output).
- Vision inputs are `list[tuple[bytes, str]]` where str is the file extension
  (e.g. ".jpg", ".png", ".pdf"). Adapters convert to the provider-specific
  data-URL / image-block format internally.
- On parse failure the adapter retries once with a stricter instruction,
  then raises LLMAdapterError.

Environment variables read:
  ANTHROPIC_API_KEY, ANTHROPIC_MODEL (default: claude-3-5-sonnet-latest)
  OPENAI_API_KEY,    OPENAI_MODEL    (default: gpt-4o-mini)
  GROQ_API_KEY,      GROQ_MODEL      (default: llama-3.3-70b-versatile)
"""

import base64
import json
import logging
import os
from typing import Any

from claims_processor.core import config

log = logging.getLogger(__name__)


class LLMAdapterError(Exception):
    """Raised when an LLM call fails to return valid JSON after retries."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ext_to_media_type(ext: str) -> str:
    ext = ext.lower().lstrip(".")
    return {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
        "gif": "image/gif",
        "pdf": "application/pdf",
    }.get(ext, "application/octet-stream")


def _b64(data: bytes) -> str:
    return base64.standard_b64encode(data).decode("ascii")


def _strip_json_fences(text: str) -> str:
    """Remove ```json ... ``` fences if the model added them."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        if t.endswith("```"):
            t = t[: -3]
    return t.strip()


def _parse_json_or_raise(text: str, provider: str) -> dict[str, Any]:
    try:
        return json.loads(_strip_json_fences(text))
    except json.JSONDecodeError as e:
        raise LLMAdapterError(
            f"{provider} returned invalid JSON: {e}. Raw: {text[:500]}"
        ) from e


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------


def call_anthropic_json(
    prompt: str,
    model: str | None = None,
    images: list[tuple[bytes, str]] | None = None,
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """Call Anthropic Claude and return parsed JSON.

    `images` is a list of (bytes, ext). If provided, switches to a vision call.
    """
    config.load_env()
    api_key = config.get_env("ANTHROPIC_API_KEY", required=True)
    model = model or config.get_env("ANTHROPIC_MODEL", default="claude-3-5-sonnet-latest")

    from anthropic import Anthropic

    client = Anthropic(api_key=api_key)

    content: list[dict[str, Any]] = []
    for img_bytes, img_ext in images or []:
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": _ext_to_media_type(img_ext),
                    "data": _b64(img_bytes),
                },
            }
        )
    content.append({"type": "text", "text": prompt})

    def _send(instruction_suffix: str = "") -> str:
        msg = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[
                {
                    "role": "user",
                    "content": [
                        *content[:-1],
                        {"type": "text", "text": content[-1]["text"] + instruction_suffix},
                    ],
                }
            ],
        )
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")

    raw = _send()
    try:
        return _parse_json_or_raise(raw, "anthropic")
    except LLMAdapterError:
        log.warning("Anthropic returned invalid JSON; retrying with stricter prompt")
        raw = _send("\n\nReturn ONLY a valid JSON object. No prose, no markdown fences.")
        return _parse_json_or_raise(raw, "anthropic")


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------


def call_openai_json(
    prompt: str,
    model: str | None = None,
    images: list[tuple[bytes, str]] | None = None,
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """Call OpenAI chat completions with JSON response format."""
    config.load_env()
    api_key = config.get_env("OPENAI_API_KEY", required=True)
    model = model or config.get_env("OPENAI_MODEL", default="gpt-4o-mini")

    from openai import OpenAI

    client = OpenAI(api_key=api_key)

    image_parts: list[dict[str, Any]] = []
    for img_bytes, img_ext in images or []:
        data_url = f"data:{_ext_to_media_type(img_ext)};base64,{_b64(img_bytes)}"
        image_parts.append({"type": "image_url", "image_url": {"url": data_url}})

    def _send(instruction_suffix: str = "") -> str:
        content = [
            {"type": "text", "text": prompt + instruction_suffix},
            *image_parts,
        ]
        resp = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": content}],
        )
        return resp.choices[0].message.content or ""

    raw = _send()
    try:
        return _parse_json_or_raise(raw, "openai")
    except LLMAdapterError:
        log.warning("OpenAI returned invalid JSON; retrying with stricter prompt")
        raw = _send("\n\nReturn ONLY a valid JSON object. No prose, no markdown fences.")
        return _parse_json_or_raise(raw, "openai")


# ---------------------------------------------------------------------------
# Groq (text-only; no vision support)
# ---------------------------------------------------------------------------


def call_groq_json(
    prompt: str,
    model: str | None = None,
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """Call Groq for text-only JSON completion."""
    config.load_env()
    api_key = config.get_env("GROQ_API_KEY", required=True)
    model = model or config.get_env("GROQ_MODEL", default="llama-3.3-70b-versatile")

    from groq import Groq

    client = Groq(api_key=api_key)

    def _send(instruction_suffix: str = "") -> str:
        resp = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt + instruction_suffix}],
        )
        return resp.choices[0].message.content or ""

    raw = _send()
    try:
        return _parse_json_or_raise(raw, "groq")
    except LLMAdapterError:
        log.warning("Groq returned invalid JSON; retrying with stricter prompt")
        raw = _send("\n\nReturn ONLY a valid JSON object. No prose, no markdown fences.")
        return _parse_json_or_raise(raw, "groq")


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def call_vision_json(
    prompt: str,
    images: list[tuple[bytes, str]],
    provider: str | None = None,
) -> dict[str, Any]:
    """Route a vision call to Anthropic or OpenAI based on availability.

    Preference order:
      1. Explicit `provider` argument
      2. VISION_PROVIDER env var
      3. Anthropic if ANTHROPIC_API_KEY present, else OpenAI
    """
    config.load_env()
    provider = (provider or os.environ.get("VISION_PROVIDER") or "").lower()

    if not provider:
        provider = "anthropic" if os.environ.get("ANTHROPIC_API_KEY") else "openai"

    if provider == "anthropic":
        return call_anthropic_json(prompt, images=images)
    if provider == "openai":
        return call_openai_json(prompt, images=images)
    raise ValueError(f"Unsupported vision provider: {provider!r}")


def call_text_json(prompt: str, provider: str | None = None) -> dict[str, Any]:
    """Route a text-only call. Preference: groq > openai > anthropic."""
    config.load_env()
    provider = (provider or os.environ.get("TEXT_PROVIDER") or "").lower()

    if not provider:
        if os.environ.get("GROQ_API_KEY"):
            provider = "groq"
        elif os.environ.get("OPENAI_API_KEY"):
            provider = "openai"
        elif os.environ.get("ANTHROPIC_API_KEY"):
            provider = "anthropic"
        else:
            raise RuntimeError(
                "No LLM provider API key found. Set ANTHROPIC_API_KEY, "
                "OPENAI_API_KEY, or GROQ_API_KEY."
            )

    if provider == "groq":
        return call_groq_json(prompt)
    if provider == "openai":
        return call_openai_json(prompt)
    if provider == "anthropic":
        return call_anthropic_json(prompt)
    raise ValueError(f"Unsupported text provider: {provider!r}")
