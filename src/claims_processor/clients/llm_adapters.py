"""LLM adapters for OpenAI, Anthropic and Groq.

Each adapter accepts an optional Pydantic `schema`. When provided we send
`response_format=json_schema` so the model returns a JSON object matching
the schema. The parsed dict is returned directly.

Env vars:
  OPENAI_API_KEY,    OPENAI_MODEL    (default: gpt-4o-mini)
  ANTHROPIC_API_KEY, ANTHROPIC_MODEL (default: claude-3-5-sonnet-latest)
  GROQ_API_KEY,      GROQ_MODEL      (default: llama-3.3-70b-versatile)
"""

import base64
import json
import os
import time

from pydantic import BaseModel

from claims_processor.core import config
from claims_processor.observability import get_tracer


MEDIA_TYPES = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg",
    "png": "image/png", "webp": "image/webp",
    "gif": "image/gif", "pdf": "application/pdf",
}


def _b64(data):
    return base64.standard_b64encode(data).decode("ascii")


def _media_type(ext):
    return MEDIA_TYPES.get(ext.lower().lstrip("."), "application/octet-stream")


def _schema_dict(schema):
    if schema is None:
        return None
    if isinstance(schema, dict):
        return schema
    if isinstance(schema, type) and issubclass(schema, BaseModel):
        return schema.model_json_schema()
    raise ValueError("schema must be a Pydantic model class or dict")


def _traced(provider, model, kind, fn):
    """Wrap an LLM call; emit a trace event with timing + token usage + errors."""
    tracer = get_tracer()
    t0 = time.perf_counter()
    usage = {}
    error = None
    try:
        resp, usage = fn()
        return resp
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
        raise
    finally:
        if tracer is not None:
            tracer.event(
                "llm_call",
                provider=provider,
                model=model,
                kind=kind,
                latency_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                ok=error is None,
                error=error,
                **usage,
            )


# --- OpenAI -----------------------------------------------------------------

def call_openai(prompt, schema=None, images=None, model=None):
    from openai import OpenAI

    config.load_env()
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    content = [{"type": "text", "text": prompt}]
    for img_bytes, ext in images or []:
        url = f"data:{_media_type(ext)};base64,{_b64(img_bytes)}"
        content.append({"type": "image_url", "image_url": {"url": url}})

    kwargs = {"model": model, "messages": [{"role": "user", "content": content}]}
    if schema is not None:
        kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "response", "schema": _schema_dict(schema)},
        }
    else:
        kwargs["response_format"] = {"type": "json_object"}

    def _do():
        resp = client.chat.completions.create(**kwargs)
        usage = {}
        u = getattr(resp, "usage", None)
        if u is not None:
            usage = {
                "input_tokens": getattr(u, "prompt_tokens", None),
                "output_tokens": getattr(u, "completion_tokens", None),
            }
        return json.loads(resp.choices[0].message.content or "{}"), usage

    kind = "vision" if images else "text"
    return _traced("openai", model, kind, _do)


# --- Anthropic --------------------------------------------------------------

def call_anthropic(prompt, schema=None, images=None, model=None):
    from anthropic import Anthropic

    config.load_env()
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    model = model or os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")

    content = []
    for img_bytes, ext in images or []:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": _media_type(ext),
                "data": _b64(img_bytes),
            },
        })
    full_prompt = prompt
    if schema is not None:
        full_prompt += (
            "\n\nReturn ONLY a JSON object matching this schema:\n"
            + json.dumps(_schema_dict(schema))
        )
    content.append({"type": "text", "text": full_prompt})

    def _do():
        msg = client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": content}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        usage = {}
        u = getattr(msg, "usage", None)
        if u is not None:
            usage = {
                "input_tokens": getattr(u, "input_tokens", None),
                "output_tokens": getattr(u, "output_tokens", None),
            }
        return json.loads(text), usage

    kind = "vision" if images else "text"
    return _traced("anthropic", model, kind, _do)


# --- Groq (text only) -------------------------------------------------------

def call_groq(prompt, schema=None, model=None):
    from groq import Groq

    config.load_env()
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    model = model or os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

    kwargs = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    if schema is not None:
        kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "response", "schema": _schema_dict(schema)},
        }
    else:
        kwargs["response_format"] = {"type": "json_object"}

    def _do():
        resp = client.chat.completions.create(**kwargs)
        usage = {}
        u = getattr(resp, "usage", None)
        if u is not None:
            usage = {
                "input_tokens": getattr(u, "prompt_tokens", None),
                "output_tokens": getattr(u, "completion_tokens", None),
            }
        return json.loads(resp.choices[0].message.content or "{}"), usage

    return _traced("groq", model, "text", _do)


# --- Dispatchers ------------------------------------------------------------

def call_vision(prompt, images, schema=None):
    """Vision call. Prefers Anthropic, falls back to OpenAI."""
    config.load_env()
    if os.environ.get("ANTHROPIC_API_KEY"):
        return call_anthropic(prompt, schema=schema, images=images)
    return call_openai(prompt, schema=schema, images=images)


def call_text(prompt, schema=None):
    """Text call. Prefers Groq, then OpenAI, then Anthropic."""
    config.load_env()
    if os.environ.get("GROQ_API_KEY"):
        return call_groq(prompt, schema=schema)
    if os.environ.get("OPENAI_API_KEY"):
        return call_openai(prompt, schema=schema)
    if os.environ.get("ANTHROPIC_API_KEY"):
        return call_anthropic(prompt, schema=schema)
    raise RuntimeError("No LLM API key set. Configure GROQ/OPENAI/ANTHROPIC.")
