"""Image helpers for vision-LLM calls."""

from __future__ import annotations


_SUPPORTED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
_SUPPORTED_ALL_EXTS = _SUPPORTED_IMAGE_EXTS | {".pdf"}


def normalize_ext(ext: str) -> str:
    """Return a lowercased extension with a leading dot."""
    e = ext.lower()
    if not e.startswith("."):
        e = "." + e
    return e


def is_supported_ext(ext: str) -> bool:
    return normalize_ext(ext) in _SUPPORTED_ALL_EXTS


def is_image_ext(ext: str) -> bool:
    return normalize_ext(ext) in _SUPPORTED_IMAGE_EXTS


def is_pdf_ext(ext: str) -> bool:
    return normalize_ext(ext) == ".pdf"
