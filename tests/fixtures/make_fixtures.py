"""Generate tiny PDF fixtures for manual/CLI smoke testing.

Run once:
    python tests/fixtures/make_fixtures.py

Produces text-native PDFs under tests/fixtures/sample_docs/ so evaluators can
try `python scripts/parse_one.py tests/fixtures/sample_docs/prescription.pdf`
without supplying their own documents.
"""

from __future__ import annotations

from pathlib import Path

from fpdf import FPDF


OUT_DIR = Path(__file__).resolve().parent / "sample_docs"


def _pdf() -> FPDF:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    return pdf


def make_prescription() -> Path:
    pdf = _pdf()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, "Apollo Clinic, Bengaluru", ln=True)
    pdf.set_font("Helvetica", size=11)
    pdf.cell(0, 6, "Dr. Arun Sharma, MBBS MD (General Medicine)", ln=True)
    pdf.cell(0, 6, "Reg. No: KA/45678/2015", ln=True)
    pdf.cell(0, 6, "Date: 2024-11-01", ln=True)
    pdf.ln(4)
    pdf.cell(0, 6, "Patient: Rajesh Kumar, 42/M", ln=True)
    pdf.cell(0, 6, "Diagnosis: Viral Fever", ln=True)
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, "Rx:", ln=True)
    pdf.set_font("Helvetica", size=11)
    pdf.cell(0, 6, "1. Paracetamol 650mg - 1 tab TID x 5 days", ln=True)
    pdf.cell(0, 6, "2. Cetirizine 10mg - 1 tab HS x 3 days", ln=True)
    pdf.ln(2)
    pdf.cell(0, 6, "Tests advised: CBC, Dengue NS1", ln=True)

    out = OUT_DIR / "prescription.pdf"
    pdf.output(str(out))
    return out


def make_hospital_bill() -> Path:
    pdf = _pdf()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, "City Clinic, Bengaluru", ln=True)
    pdf.set_font("Helvetica", size=11)
    pdf.cell(0, 6, "GSTIN: 29AAACC1234A1Z5", ln=True)
    pdf.cell(0, 6, "Bill No: CC-2024-00871", ln=True)
    pdf.cell(0, 6, "Date: 2024-11-01", ln=True)
    pdf.cell(0, 6, "Patient: Rajesh Kumar, 42/M", ln=True)
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(90, 6, "Description", border=1)
    pdf.cell(25, 6, "Qty", border=1, align="R")
    pdf.cell(30, 6, "Rate", border=1, align="R")
    pdf.cell(30, 6, "Amount", border=1, align="R", ln=True)
    pdf.set_font("Helvetica", size=11)
    rows = [
        ("Consultation Fee", 1, 1000, 1000),
        ("CBC Test", 1, 300, 300),
        ("Dengue NS1 Test", 1, 200, 200),
    ]
    for desc, qty, rate, amt in rows:
        pdf.cell(90, 6, desc, border=1)
        pdf.cell(25, 6, str(qty), border=1, align="R")
        pdf.cell(30, 6, f"{rate}", border=1, align="R")
        pdf.cell(30, 6, f"{amt}", border=1, align="R", ln=True)
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(145, 6, "Total", border=1)
    pdf.cell(30, 6, "1500", border=1, align="R", ln=True)

    out = OUT_DIR / "hospital_bill.pdf"
    pdf.output(str(out))
    return out


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rx = make_prescription()
    bill = make_hospital_bill()
    print(f"wrote {rx}")
    print(f"wrote {bill}")


if __name__ == "__main__":
    main()
