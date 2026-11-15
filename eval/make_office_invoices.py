"""Sample invoices in office / text / email formats (same content: a small Lebanese supplier invoice),
to test that every file type an invoice can arrive in is accepted and read.

  python eval/make_office_invoices.py   -> eval/dev/office/*
"""
import csv
import io
from email.message import EmailMessage
from pathlib import Path

OUT = Path(__file__).resolve().parent / "dev" / "office"
OUT.mkdir(parents=True, exist_ok=True)

SUP = "Rizk Paper & Packaging s.a.r.l."
NO, DATE = "RP-2026-311", "10/11/2026"
LINES = [("Carton box 40x30", 50, 0.80), ("Packing tape 48mm", 24, 1.25), ("Kraft paper roll", 5, 7.00)]
SUB = round(sum(q * p for _, q, p in LINES), 2)
VAT = round(SUB * 0.11, 2)
TOTAL = round(SUB + VAT, 2)
TRUTH = {"supplier_name": SUP, "invoice_number": NO, "invoice_date": "2026-11-10", "currency": "USD",
         "subtotal": SUB, "vat_amount": VAT, "total": TOTAL}


def docx():
    from docx import Document
    d = Document()
    d.add_heading(SUP, 1)
    d.add_paragraph("Sin el Fil, Beirut - Tel: +961 1 499 120")
    d.add_heading("INVOICE", 2)
    d.add_paragraph(f"Invoice No: {NO}\nDate: {DATE}\nBill to: Mini Market Al Amal, Byblos")
    t = d.add_table(rows=1, cols=4)
    for c, h in zip(t.rows[0].cells, ["Description", "Qty", "Unit price ($)", "Amount ($)"]):
        c.text = h
    for desc, q, p in LINES:
        for c, v in zip(t.add_row().cells, [desc, str(q), f"{p:.2f}", f"{q * p:.2f}"]):
            c.text = v
    d.add_paragraph(f"Subtotal: ${SUB:.2f}\nVAT 11%: ${VAT:.2f}\nTOTAL: ${TOTAL:.2f}")
    d.save(OUT / "invoice.docx")


def xlsx():
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Invoice"
    rows = [[SUP], ["Sin el Fil, Beirut - Tel: +961 1 499 120"], [], ["INVOICE"], ["Invoice No", NO], ["Date", DATE],
            [], ["Description", "Qty", "Unit price ($)", "Amount ($)"]]
    rows += [[d, q, p, round(q * p, 2)] for d, q, p in LINES]
    rows += [[], ["", "", "Subtotal", SUB], ["", "", "VAT 11%", VAT], ["", "", "TOTAL ($)", TOTAL]]
    for r in rows:
        ws.append(r)
    ws.column_dimensions["A"].width = 30
    for col in "BCD":
        ws.column_dimensions[col].width = 16
    wb.save(OUT / "invoice.xlsx")


def html():
    rows = "".join(f"<tr><td>{d}</td><td>{q}</td><td>{p:.2f}</td><td>{q * p:.2f}</td></tr>" for d, q, p in LINES)
    (OUT / "invoice.html").write_text(f"""<!doctype html><html><body style="font-family:Arial">
<h1>{SUP}</h1><p>Sin el Fil, Beirut - Tel: +961 1 499 120</p><h2>INVOICE</h2>
<p>Invoice No: {NO}<br>Date: {DATE}</p>
<table border=1 cellpadding=6><tr><th>Description</th><th>Qty</th><th>Unit price ($)</th><th>Amount ($)</th></tr>{rows}</table>
<p>Subtotal: ${SUB:.2f}<br>VAT 11%: ${VAT:.2f}<br><b>TOTAL: ${TOTAL:.2f}</b></p></body></html>""", encoding="utf-8")


def text_files():
    lines = "\n".join(f"{d:<24}{q:>5}{p:>10.2f}{q * p:>12.2f}" for d, q, p in LINES)
    txt = (f"{SUP}\nSin el Fil, Beirut - Tel: +961 1 499 120\n\nINVOICE\nInvoice No: {NO}\nDate: {DATE}\n\n"
           f"{'Description':<24}{'Qty':>5}{'Price $':>10}{'Amount $':>12}\n{lines}\n\n"
           f"Subtotal: {SUB:.2f} USD\nVAT 11%: {VAT:.2f} USD\nTOTAL: {TOTAL:.2f} USD\n")
    (OUT / "invoice.txt").write_text(txt, encoding="utf-8")
    with open(OUT / "invoice.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerows([["Supplier", SUP], ["Invoice No", NO], ["Date", DATE], [], ["Description", "Qty", "Unit price USD", "Amount USD"]])
        w.writerows([[d, q, p, round(q * p, 2)] for d, q, p in LINES])
        w.writerows([[], ["", "", "Subtotal", SUB], ["", "", "VAT 11%", VAT], ["", "", "TOTAL USD", TOTAL]])
    rtf_lines = r"\par ".join(f"{d}    {q}    {p:.2f}    {q * p:.2f}" for d, q, p in LINES)
    (OUT / "invoice.rtf").write_text(
        r"{\rtf1\ansi\deff0 {\fonttbl {\f0 Arial;}}\f0\fs24 " + rf"\b {SUP}\b0\par Sin el Fil, Beirut\par\par "
        rf"\b INVOICE\b0\par Invoice No: {NO}\par Date: {DATE}\par\par Description    Qty    Price    Amount\par "
        + rtf_lines + rf"\par\par Subtotal: {SUB:.2f} USD\par VAT 11%: {VAT:.2f} USD\par \b TOTAL: {TOTAL:.2f} USD\b0" + "}",
        encoding="ascii")


def eml():
    pdf = (OUT.parent / "rich-01.pdf")
    m = EmailMessage()
    m["From"] = "accounts@khourydist.com.lb"
    m["To"] = "shop@example.com"
    m["Subject"] = "Invoice KD-24-07731"
    m.set_content("Dear customer,\nplease find attached our invoice.\nRegards")
    m.add_attachment(pdf.read_bytes(), maintype="application", subtype="pdf", filename="KD-24-07731.pdf")
    (OUT / "email-with-pdf.eml").write_bytes(bytes(m))
    m2 = EmailMessage()
    m2["From"] = "sales@rizkpaper.com.lb"
    m2["To"] = "shop@example.com"
    m2["Subject"] = f"Invoice {NO}"
    m2.set_content((OUT / "invoice.txt").read_text(encoding="utf-8"))
    (OUT / "email-body-only.eml").write_bytes(bytes(m2))


def heic():
    import pillow_heif
    from PIL import Image
    pillow_heif.register_heif_opener()
    Image.open(OUT.parent / "syn-01-clean.jpg").save(OUT / "photo.heic", quality=80)


if __name__ == "__main__":
    for f in (docx, xlsx, html, text_files, eml, heic):
        f()
    import json
    (OUT / "truth.json").write_text(json.dumps(TRUTH, indent=2), encoding="utf-8")
    for p in sorted(OUT.iterdir()):
        print(f"{p.name:28s} {p.stat().st_size // 1024:>5} KB")
