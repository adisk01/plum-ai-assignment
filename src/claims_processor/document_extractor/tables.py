"""Bill line-item extraction via pdfplumber.

Adapted from fs-v2/agentic_search/ingestion.py but stripped down — we don't
need section-aware merging or chunking here, just line items from bill tables.
"""

from __future__ import annotations

from io import BytesIO


def extract_line_items_from_pdf_bytes(data: bytes) -> list[dict]:
    """Return flat list of {description, quantity, rate, amount} dicts.

    Falls back to an empty list on any pdfplumber error — callers treat
    this as "no structured line items found, fall back to LLM extraction".
    """
    try:
        import pdfplumber
    except ImportError:
        return []

    line_items: list[dict] = []
    try:
        with pdfplumber.open(BytesIO(data)) as pdf:
            for page in pdf.pages:
                for raw_table in page.extract_tables() or []:
                    if not raw_table or len(raw_table) < 2:
                        continue
                    cleaned = [
                        [(cell or "").strip() for cell in row] for row in raw_table
                    ]
                    headers = [h.lower() for h in cleaned[0]]
                    if not _looks_like_billing_table(headers):
                        continue
                    for row in cleaned[1:]:
                        item = _row_to_line_item(headers, row)
                        if item:
                            line_items.append(item)
    except Exception:
        return []
    return line_items


def _looks_like_billing_table(headers: list[str]) -> bool:
    """Heuristic: a billing table has an 'amount' column and a description column."""
    has_amount = any("amount" in h or "amt" in h or "total" in h for h in headers)
    has_desc = any(
        "description" in h or "item" in h or "medicine" in h or "service" in h
        for h in headers
    )
    return has_amount and has_desc


def _row_to_line_item(headers: list[str], row: list[str]) -> dict | None:
    """Map a table row to a line-item dict using header names."""
    if len(row) != len(headers):
        return None

    desc = qty = rate = amount = None
    for h, cell in zip(headers, row):
        if not cell:
            continue
        if "description" in h or "item" in h or "medicine" in h or "service" in h:
            desc = desc or cell
        elif h in ("qty", "quantity") or h.endswith(" qty"):
            qty = _try_int(cell)
        elif "rate" in h or h == "mrp":
            rate = _try_number(cell)
        elif "amount" in h or "amt" in h or "total" in h:
            amount = _try_number(cell)

    if not desc or amount is None:
        return None

    return {
        "description": desc,
        "quantity": qty,
        "rate": rate,
        "amount": amount,
    }


def _try_int(value: str) -> int | None:
    try:
        return int(value.replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def _try_number(value: str) -> float | None:
    cleaned = (value or "").replace(",", "").replace("₹", "").strip()
    try:
        return float(cleaned)
    except (ValueError, AttributeError):
        return None
