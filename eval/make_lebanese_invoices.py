"""Generate Lebanese-style test invoices (Arabic / French / English, LBP and dual USD+LBP) with known truth.
For testing currency + language handling; NOT the 20 real cases.

  python eval/make_lebanese_invoices.py      -> eval/dev/leb-*.jpg + *.expected.json
"""
import json
import sys
from pathlib import Path

import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_dev_invoices import as_photo  # noqa: E402

OUT = Path(__file__).resolve().parent / "dev"
F = "C:/Windows/Fonts/"
RATE = 89500


def ar(t):
    return get_display(arabic_reshaper.reshape(t))


def font(name, size):
    return ImageFont.truetype(F + name, size)


def money(v, cur):
    return f"{v:,.0f}" if cur == "LBP" else f"{v:,.2f}"


INVOICES = [
    {   # Arabic supplier, prices in Lebanese pounds (ل.ل)
        "name": "leb-01-arabic-lbp", "rtl": True, "cur": "LBP", "cur_label": "ل.ل",
        "supplier": "شركة الأرز للمواد الغذائية ش.م.م", "phone": "03 456 789", "addr": "طرابلس - شارع عزمي",
        "no": "2026/1187", "date": "2026-11-11", "title": "فاتورة", "no_label": "رقم الفاتورة", "date_label": "التاريخ",
        "head": ["الصنف", "الكمية", "السعر", "المجموع"],
        "lines": [("سكر ١ كلغ", 20, 98500), ("أرز مصري ٥ كلغ", 5, 712000), ("زيت دوار الشمس ١.٨ ل", 10, 285000)],
        "vat": True, "labels": {"sub": "المجموع", "vat": "ض.ق.م 11%", "total": "المجموع الإجمالي"}, "dual": False,
    },
    {   # French supplier, dual currency USD + LBP with printed rate
        "name": "leb-02-french-dual", "rtl": False, "cur": "USD", "cur_label": "$",
        "supplier": "Établissements Haddad & Fils S.A.R.L.", "phone": "+961 1 234 567", "addr": "Jdeideh, Metn - Liban",
        "no": "FA-00942", "date": "2026-11-09", "title": "FACTURE", "no_label": "Facture N°", "date_label": "Date",
        "head": ["Désignation", "Qté", "P.U. ($)", "Montant ($)"],
        "lines": [("Café moulu 500g", 12, 6.50), ("Thé noir 100 sachets", 8, 3.75), ("Sucre en morceaux 1kg", 10, 1.40)],
        "vat": True, "labels": {"sub": "Total HT", "vat": "TVA 11%", "total": "Total TTC ($)"}, "dual": True,
    },
    {   # English supplier, LBP written "L.L." and no VAT
        "name": "leb-03-english-ll", "rtl": False, "cur": "LBP", "cur_label": "L.L.",
        "supplier": "Saad Bakery Supplies", "phone": "70 112 233", "addr": "Zahle, Bekaa",
        "no": "SB-5531", "date": "2026-11-13", "title": "INVOICE", "no_label": "Invoice No", "date_label": "Date",
        "head": ["Item", "Qty", "Price (L.L.)", "Amount (L.L.)"],
        "lines": [("Flour 25kg bag", 4, 1790000), ("Yeast 500g", 6, 223750), ("Sesame 1kg", 3, 447500)],
        "vat": False, "labels": {"sub": "Subtotal", "vat": "", "total": "TOTAL (L.L.)"}, "dual": False,
    },
]


def render(inv):
    W, H = 1240, 1500
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    ar_font = lambda s: font("arialbd.ttf" if s > 30 else "arial.ttf", s)  # Arial has Arabic glyphs
    T = (lambda t: ar(t)) if inv["rtl"] else (lambda t: t)
    big, r = ar_font(42), ar_font(26)
    x_left, x_right = 80, 1160

    def text(x, y, t, f, anchor_right=False, fill="black"):
        t = T(t)
        if anchor_right:
            x = x - d.textlength(t, font=f)
        d.text((x, y), t, font=f, fill=fill)

    rtl = inv["rtl"]
    # header: supplier on the start side, invoice block on the other side
    text(x_right if rtl else x_left, 70, inv["supplier"], big, anchor_right=rtl)
    text(x_right if rtl else x_left, 130, inv["addr"], r, anchor_right=rtl, fill="#333")
    text(x_right if rtl else x_left, 165, ("هاتف: " if rtl else "Tel: ") + inv["phone"], r, anchor_right=rtl, fill="#333")
    bx = x_left if rtl else 800
    text(bx, 230, inv["title"], big, fill="#9b1b30")
    text(bx, 290, f"{inv['no_label']}: {inv['no']}", r)
    y_, m_, d_ = inv["date"].split("-")
    text(bx, 325, f"{inv['date_label']}: {d_}/{m_}/{y_}", r)
    if inv["dual"]:
        text(bx, 360, f"Taux: 1 $ = {RATE:,} L.L.", r)
    y = 420
    d.rectangle((x_left, y, x_right, y + 50), fill="#eee")
    cols = [x_right - 20, 560, 420, 230] if rtl else [95, 640, 780, 990]
    for x, h in zip(cols, inv["head"]):
        text(x, y + 12, h, ar_font(24), anchor_right=rtl and x == cols[0])
    y += 62
    sub = 0
    for desc, q, p in inv["lines"]:
        amt = q * p
        sub += amt
        text(cols[0], y, desc, r, anchor_right=rtl)
        for x, v in zip(cols[1:], (str(q), money(p, inv["cur"]), money(amt, inv["cur"]))):
            d.text((x, y), v, font=r, fill="black")
        y += 50
        d.line((x_left, y - 8, x_right, y - 8), fill="#ddd")
    sub = round(sub, 2)
    vat = round(sub * 0.11, 2 if inv["cur"] == "USD" else 0) if inv["vat"] else None
    total = round(sub + (vat or 0), 2)
    total_lbp = round(total * RATE) if inv["dual"] else None
    y += 30
    rows = [(inv["labels"]["sub"], sub)] + ([(inv["labels"]["vat"], vat)] if vat is not None else []) + \
           [(inv["labels"]["total"], total)]
    lx, vx = (520, 230) if rtl else (720, 990)
    for lab, v in rows:
        f = ar_font(30) if lab == inv["labels"]["total"] else r
        text(lx, y, lab, f)
        d.text((vx, y), f"{money(v, inv['cur'])} {inv['cur_label'] if not rtl else ''}".strip(), font=f, fill="black")
        if rtl:
            text(vx - 20, y, inv["cur_label"], f, anchor_right=True)
        y += 48
    if inv["dual"]:
        d.text((720, y), "Total TTC (L.L.)", font=ar_font(30), fill="black")
        d.text((990, y), f"{total_lbp:,}", font=ar_font(30), fill="black")
        y += 48
    footer = "شكراً لتعاملكم معنا" if rtl else ("Merci pour votre confiance" if inv["dual"] else "Thank you")
    text(x_right if rtl else x_left, H - 110, footer, font("arial.ttf", 22), anchor_right=rtl, fill="#777")
    truth = {"is_invoice": True, "supplier_name": inv["supplier"], "invoice_number": inv["no"],
             "invoice_date": inv["date"], "currency": inv["cur"], "subtotal": sub, "vat_amount": vat, "total": total,
             "lines": [{"description": a, "quantity": q, "unit_price": p, "line_total": q * p} for a, q, p in inv["lines"]]}
    if inv["dual"]:
        truth["total_lbp"] = total_lbp
    return im, truth


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for i, inv in enumerate(INVOICES):
        im, truth = render(inv)
        as_photo(im, 10 + i).save(OUT / f"{inv['name']}.jpg", quality=88)
        (OUT / f"{inv['name']}.expected.json").write_text(json.dumps(truth, indent=2, ensure_ascii=False),
                                                         encoding="utf-8")
        print("wrote", inv["name"], "total", truth["total"], inv["cur"])
