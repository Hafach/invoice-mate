"""A deliberately 'unusual', data-rich Lebanese tax invoice to test the general data model:
item codes, units, line discount, due date, PO, customer + tax ids, delivery fee, partial payment, IBAN,
and extra info with no standard field (driver, vehicle, warehouse).

  python eval/make_rich_invoice.py   -> eval/dev/rich-01-full.jpg + .expected.json
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_dev_invoices import as_photo  # noqa: E402

OUT = Path(__file__).resolve().parent / "dev"
F = "C:/Windows/Fonts/"


def font(bold, size):
    return ImageFont.truetype(F + ("arialbd.ttf" if bold else "arial.ttf"), size)


LINES = [("CL-1101", "Detergent Clean+ 3L", 24, "pcs", 4.50, 0), ("PT-2040", "Paper towels 6 rolls", 15, "pack", 3.20, 5.00),
         ("SB-0007", "Garbage bags 50L x20", 30, "roll", 1.10, 0), ("DS-5512", "Dish soap 1L", 40, "pcs", 1.25, 0)]


def render():
    W, H = 1240, 1754
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    t = lambda x, y, s, f=font(False, 24), c="black": d.text((x, y), s, font=f, fill=c)
    t(80, 70, "Khoury Distribution S.A.L.", font(True, 40))
    t(80, 125, "Dora Highway, Bldg 14, Beirut - Lebanon")
    t(80, 158, "Tel: +961 1 245 870   Email: sales@khourydist.com.lb")
    t(80, 191, "VAT / MOF No: 3348271-601")
    t(820, 70, "TAX INVOICE", font(True, 38), "#9b1b30")
    t(820, 130, "Invoice No: KD-24-07731")
    t(820, 163, "Date: 12/11/2026")
    t(820, 196, "Due date: 12/12/2026")
    t(820, 229, "PO No: AA-0458")
    d.rectangle((80, 280, 600, 420), outline="#999")
    t(95, 290, "Bill to:", font(True, 24))
    t(95, 325, "Mini Market Al Amal")
    t(95, 358, "Main Street, Byblos")
    t(95, 391, "MOF No: 1187420-601", font(False, 22))
    t(660, 300, "Driver: Samir H.")
    t(660, 335, "Vehicle: M 482915")
    t(660, 370, "Warehouse: Dora WH-2")
    y = 460
    d.rectangle((80, y, 1160, y + 48), fill="#eee")
    cols = [(95, "Code"), (230, "Description"), (610, "Qty"), (690, "Unit"), (790, "Price"), (900, "Disc."), (1020, "Amount")]
    for x, h in cols:
        t(x, y + 12, h, font(True, 22))
    y += 60
    sub = 0
    for code, desc, q, unit, p, disc in LINES:
        amt = round(q * p - disc, 2)
        sub += amt
        for x, v in zip([c[0] for c in cols], [code, desc, str(q), unit, f"{p:.2f}", f"{disc:.2f}" if disc else "-", f"{amt:.2f}"]):
            t(x, y, v, font(False, 22))
        y += 44
        d.line((80, y - 8, 1160, y - 8), fill="#ddd")
    sub = round(sub, 2)
    vat = round(sub * 0.11, 2)
    delivery = 5.00
    total = round(sub + vat + delivery, 2)
    paid = 100.00
    y += 25
    for lab, v in [("Subtotal", sub), ("VAT 11%", vat), ("Delivery fee", delivery), ("TOTAL USD", total),
                   ("Paid (cash)", paid), ("Balance due", round(total - paid, 2))]:
        f = font(True, 26) if lab in ("TOTAL USD", "Balance due") else font(False, 24)
        t(760, y, lab, f)
        t(1000, y, f"$ {v:,.2f}", f)
        y += 42
    t(80, y + 30, "Payment terms: 30 days net. Bank transfer to IBAN LB62 0999 0000 0001 0019 0122 9114", font(False, 22))
    t(80, y + 65, "Goods remain property of Khoury Distribution until full payment.", font(False, 20), "#555")
    truth = {"is_invoice": True, "document_type": "tax_invoice", "supplier_name": "Khoury Distribution S.A.L.",
             "invoice_number": "KD-24-07731", "invoice_date": "2026-11-12", "due_date": "2026-12-12",
             "order_number": "AA-0458", "supplier_tax_id": "3348271-601", "customer_name": "Mini Market Al Amal",
             "customer_tax_id": "1187420-601", "currency": "USD", "subtotal": sub, "vat_rate": 11, "vat_amount": vat,
             "other_charges": delivery, "total": total, "amount_paid": paid, "balance_due": round(total - paid, 2),
             "lines": [{"item_code": c, "description": ds, "quantity": q, "unit": u, "unit_price": p,
                        "line_discount": disc or None, "line_total": round(q * p - disc, 2)} for c, ds, q, u, p, disc in LINES],
             "extra_fields_expected": ["Driver", "Vehicle", "Warehouse"]}
    return im, truth


if __name__ == "__main__":
    im, truth = render()
    as_photo(im, 42).save(OUT / "rich-01-full.jpg", quality=90)
    (OUT / "rich-01-full.expected.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")
    print("wrote rich-01-full: total", truth["total"], "balance", truth["balance_due"])
