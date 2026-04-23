"""CLI: parse a single document end-to-end and print the ParsedDocument JSON.

Usage:
    python scripts/parse_one.py path/to/bill.pdf
    python scripts/parse_one.py path/to/rx.jpg --expected PRESCRIPTION
    python scripts/parse_one.py path/to/bill.pdf --file-id F008 --pretty

Requires an API key for whichever provider will be used. See .env.example.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running the script directly without `pip install -e .`
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))

from claims_processor.core import config  # noqa: E402
from claims_processor.document_extractor import parse  # noqa: E402
from claims_processor.document_extractor.exceptions import (  # noqa: E402
    DocumentExtractorError,
)
from claims_processor.models.documents import DocType  # noqa: E402


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Parse a single claim document.")
    p.add_argument("file", help="Path to a PDF / JPG / PNG document")
    p.add_argument(
        "--expected",
        help=f"Expected doc type. One of: {[t.value for t in DocType]}",
        default=None,
    )
    p.add_argument("--file-id", default="F000", help="Synthetic file_id for the output")
    p.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    config.load_env()

    path = Path(args.file)
    if not path.exists():
        print(f"error: file not found: {path}", file=sys.stderr)
        return 2

    expected = DocType(args.expected.upper()) if args.expected else None

    try:
        parsed = parse.parse_document(
            file_bytes=path.read_bytes(),
            file_ext=path.suffix,
            file_id=args.file_id,
            expected_type=expected,
        )
    except DocumentExtractorError as e:
        print(
            json.dumps(
                {"error": type(e).__name__, "message": str(e)},
                indent=2 if args.pretty else None,
            )
        )
        return 1

    payload = parsed.model_dump(mode="json")
    print(json.dumps(payload, indent=2 if args.pretty else None, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
