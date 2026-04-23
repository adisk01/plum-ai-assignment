"""PDF text extraction via pypdfium2."""

from dataclasses import dataclass
from io import BytesIO

import pypdfium2


@dataclass
class PageText:
    page_number: int
    text: str


def extract_pages_from_pdf_bytes(data):
    pdf = pypdfium2.PdfDocument(BytesIO(data))
    pages = []
    try:
        for i in range(len(pdf)):
            text = pdf[i].get_textpage().get_text_range().strip()
            pages.append(PageText(page_number=i + 1, text=text))
    finally:
        pdf.close()
    return pages
