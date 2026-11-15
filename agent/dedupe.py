"""Duplicate detection: is this invoice (or this exact photo) already in the system?

Compared against BOTH the approved ledger and invoices still waiting for approval, so two
copies of the same paper can't both be approved.

1. same supplier + same invoice number           -> approved: BLOCK        pending: warn
2. same supplier + same date + same total        -> warn (no / different invoice number printed)
3. the exact same file uploaded again (SHA-256)  -> approved: BLOCK        pending: warn
4. the same image sent again (re-compressed / resized, e.g. forwarded on WhatsApp) -> warn (perceptual hash)

"Same supplier" = same name after Arabic/French/English normalization (fuzzy), OR the same phone number
(works when one invoice prints the name in Arabic and another in Latin letters).
"""
import hashlib
import io
import json
from difflib import SequenceMatcher

from PIL import Image, ImageOps

from . import ledger
from .config import PENDING
from .textnorm import invoice_no_key, phone_key, supplier_key

PHASH_MAX_DISTANCE = 12  # of 256 bits. Measured: same image re-compressed/resized <= 13, two DIFFERENT invoices
                         # of the same template >= 18, unrelated invoices >= 72. A NEW camera shot of the same
                         # paper (moved/rotated) is NOT caught here; rules 1-2 catch it by its content.


def file_hash(image_bytes: bytes) -> str:
    return hashlib.sha256(image_bytes).hexdigest()


def photo_hash(image_bytes: bytes) -> str:
    """Difference hash 16x16 (256 bits) of the grayscale photo: robust to re-compression, small light changes."""
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(image_bytes))).convert("L")
    im = ImageOps.autocontrast(im).resize((17, 16), Image.LANCZOS)
    px = list(im.getdata())
    bits = "".join("1" if px[r * 17 + c] > px[r * 17 + c + 1] else "0" for r in range(16) for c in range(16))
    return f"{int(bits, 2):064x}"


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def same_supplier(name_a, phone_a, name_b, phone_b) -> bool:
    pa, pb = phone_key(phone_a), phone_key(phone_b)
    if pa and pb and pa == pb:
        return True
    ka, kb = supplier_key(name_a), supplier_key(name_b)
    if not ka or not kb:
        return False
    return ka == kb or SequenceMatcher(None, ka, kb).ratio() >= 0.88


def _close(a, b):
    try:
        return a is not None and b is not None and abs(float(a) - float(b)) <= 0.011
    except (TypeError, ValueError):
        return False


def _candidates(exclude_run_id=None):
    """Every invoice already known: approved ledger rows + pending runs. Yields dicts with a common shape."""
    data = ledger.read_all()
    phones = {supplier_key(r["Supplier"]): r.get("Phone") for r in data["Suppliers"]}
    approved_runs = set()
    for r in data["Invoices"]:
        approved_runs.add(r.get("Run id"))
        yield {"where": "approved", "run_id": r.get("Run id"), "supplier": r["Supplier"],
               "phone": phones.get(supplier_key(r["Supplier"])), "number": r["Invoice no."],
               "date": r["Invoice date"], "total": r["Total"], "when": r.get("Approved at"),
               "sha": None, "phash": None}
    for p in PENDING.glob("*.json"):
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if rec.get("run_id") == exclude_run_id or rec.get("state") in ("rejected", "failed"):
            continue
        inv = rec.get("final") or rec.get("extracted") or {}
        approved = rec.get("state") == "approved" or rec.get("run_id") in approved_runs
        yield {"where": "approved" if approved else "pending", "run_id": rec.get("run_id"),
               "supplier": inv.get("supplier_name"), "phone": inv.get("supplier_phone"),
               "number": inv.get("invoice_number"), "date": inv.get("invoice_date"), "total": inv.get("total"),
               "when": rec.get("created"), "sha": rec.get("image_sha256"), "phash": rec.get("image_phash"),
               "from_run": True}


def find_duplicates(inv: dict, run_id=None, sha=None, phash=None) -> list:
    """Returns findings [{level, code, msg}] (at most one per earlier invoice, the strongest)."""
    out, seen = [], set()
    num = invoice_no_key(inv.get("invoice_number"))
    for c in _candidates(exclude_run_id=run_id):
        ident = c["run_id"] or (c["supplier"], c["number"])
        if ident in seen:
            continue
        where = "already in the ledger" if c["where"] == "approved" else "still waiting for approval"
        ref = f"{c['supplier'] or '?'} #{c['number'] or '-'} ({c['date'] or 'no date'}, {where}, {c['when'] or ''})"
        same_sup = same_supplier(inv.get("supplier_name"), inv.get("supplier_phone"), c["supplier"], c["phone"])
        finding = None
        if sha and c["sha"] and sha == c["sha"]:
            finding = ("error" if c["where"] == "approved" else "warn", "same_file",
                       f"This exact photo/file was already processed: {ref}.")
        elif same_sup and num and num == invoice_no_key(c["number"]):
            finding = ("error" if c["where"] == "approved" else "warn",
                       "duplicate" if c["where"] == "approved" else "duplicate_pending",
                       f"Same supplier and invoice number as {ref}. Possible double payment.")
        elif same_sup and inv.get("invoice_date") and inv.get("invoice_date") == c["date"] and _close(inv.get("total"), c["total"]):
            finding = ("warn", "possible_duplicate",
                       f"Same supplier, date and total as {ref}: check it is not the same invoice.")
        elif phash and c["phash"] and hamming(phash, c["phash"]) <= PHASH_MAX_DISTANCE:
            finding = ("warn", "same_photo", f"This looks like the same image as {ref} (sent again / re-compressed).")
        if finding:
            seen.add(ident)
            out.append({"level": finding[0], "code": finding[1], "msg": finding[2]})
    if not out:
        return []
    # show only the strongest match, and how many other earlier copies exist
    rank = ["duplicate", "same_file", "duplicate_pending", "possible_duplicate", "same_photo"]
    out.sort(key=lambda f: (f["level"] != "error", rank.index(f["code"])))
    best = out[0]
    if len(out) > 1:
        best["msg"] += f" ({len(out) - 1} other earlier cop{'y' if len(out) == 2 else 'ies'} also match.)"
    return [best]
