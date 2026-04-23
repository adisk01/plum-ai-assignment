"""CLI: parse a single document and print the ParsedDocument JSON.

Usage:
    python scripts/parse_one.py path/to/bill.pdf
    python scripts/parse_one.py path/to/rx.jpg --expected PRESCRIPTION --pretty
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from claims_processor.core import config
from claims_processor.document_extractor import parse
from claims_processor.document_extractor.exceptions import DocumentExtractorError
from claims_processor.models.documents import DocType


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--expected", default=None)
    ap.add_argument("--file-id", default="F000")
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()

    config.load_env()
    path = Path(args.file)
    expected = DocType(args.expected.upper()) if args.expected else None

    try:
        parsed = parse.parse_document(
            file_bytes=path.read_bytes(),
            file_ext=path.suffix,
            file_id=args.file_id,
            expected_type=expected,
        )
    except DocumentExtractorError as e:
        print(json.dumps({"error": type(e).__name__, "message": str(e)}))
        return 1

    indent = 2 if args.pretty else None
    print(json.dumps(parsed.model_dump(mode="json"), indent=indent, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
