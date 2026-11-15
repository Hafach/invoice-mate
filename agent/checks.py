"""Step 2: deterministic checks in plain code (no AI), so results are repeatable.

Each finding: {"level": "error"|"warn"|"info", "code": str, "msg": str}
Status: "blocked"      -> cannot be approved as-is (duplicate / not an invoice)
        "needs_review" -> a human must look at the flagged fields
        "ready"        -> all checks passed; still waits for the human Approve click
"""
import re

from . import dedupe, ledger
from .textnorm import fold
from .config import (LBP_MIN_PLAUSIBLE, PRICE_JUMP_PCT, RATE_TOLERANCE, USD_LBP_RATE, USD_MAX_PLAUSIBLE,
                     VAT_RATE)


def _close(a, b, tol_abs=0.02, tol_rel=0.005):
    return abs(a - b) <= max(tol_abs, tol_rel * max(abs(a), abs(b)))


def _fmt(x):
    return f"{x:,.2f}".rstrip("0").rstrip(".")


# Matched on fold()ed text: lowercase, no French accents, Arabic letters unified (ة->ه, أ->ا, ى->ي).
INJECTION_WORDS = re.compile(
    # English
    r"\b(ai|a\.i\.|assistant|chatbot|gpt|claude|llm|model|system prompt|instructions?|ignore|disregard|override|"
    r"approve|auto-?approve|automatically|skip|bypass|pre-?verified|do not check|without check|"
    # French
    r"ia|i\.a\.|intelligence artificielle|assistante?|modele|ignore[rz]?|ignorez|approuve[rz]?|"
    r"valide[rz]? automatiquement|automatiquement|sans (verification|controle)|ne pas (verifier|controler)|"
    r"deja verifiee?|contourne[rz]?)\b|"
    # Arabic (no \b: Arabic words take prefixes like و / ال)
    r"تجاهل|الذكاء الاصطناعي|ذكاء اصطناعي|المساعد|مساعد ذكي|وافق|الموافقه|موافقه تلقائيه|تلقائيا|بشكل تلقائي|"
    r"اعتمد|اعتماد تلقائي|بدون تدقيق|دون تدقيق|بدون مراجعه|لا تتحقق|تعليمات|تم التحقق مسبقا")


def looks_like_injection(text) -> bool:
    """The small model reports candidates (it over-reports footers like "Thank you"); code confirms them."""
    return bool(text) and bool(INJECTION_WORDS.search(fold(text)))


def currency_checks(inv: dict, add):
    """Lebanese pound / dollar plausibility. Lebanon prices in USD and LBP side by side (1 USD ~ 89,500 LBP)."""
    cur, total = inv.get("currency"), inv.get("total")
    total_lbp, rate = inv.get("total_lbp"), inv.get("exchange_rate")
    lo, hi = USD_LBP_RATE * (1 - RATE_TOLERANCE), USD_LBP_RATE * (1 + RATE_TOLERANCE)
    if inv.get("currency_guessed"):
        add("warn", "currency_guessed", f"No currency printed; the amounts ({_fmt(total)}) look like Lebanese pounds "
                                        f"(LBP). Confirm the currency.")
    if cur == "USD" and total is not None and total >= USD_MAX_PLAUSIBLE:
        add("warn", "currency_suspect", f"Total {_fmt(total)} is very large for US dollars: is it Lebanese pounds (LBP)?")
    if cur == "LBP" and total is not None and 0 < total < LBP_MIN_PLAUSIBLE:
        add("warn", "currency_suspect", f"Total {_fmt(total)} is very small for Lebanese pounds: is it US dollars?")
    if rate is not None and not (lo <= rate <= hi):
        add("warn", "rate_suspect", f"Printed dollar rate {_fmt(rate)} LBP is far from the usual {_fmt(USD_LBP_RATE)}.")
    if cur == "USD" and total and total_lbp:
        implied = total_lbp / total
        used = rate or USD_LBP_RATE
        if rate and not _close(implied, rate, tol_abs=1, tol_rel=0.01):
            add("warn", "rate_mismatch", f"USD total {_fmt(total)} x rate {_fmt(rate)} = {_fmt(total * rate)} LBP, "
                                         f"but the LBP total printed is {_fmt(total_lbp)}.")
        elif not rate and not (lo <= implied <= hi):
            add("warn", "rate_mismatch", f"The two totals imply 1 USD = {_fmt(implied)} LBP (usual {_fmt(used)}): "
                                         f"check the USD or LBP total.")
        else:
            add("info", "dual_currency", f"Dual-currency invoice: {_fmt(total)} USD = {_fmt(total_lbp)} LBP "
                                         f"(1 USD = {_fmt(implied)} LBP).")
    if cur == "LBP" and total:
        add("info", "usd_equivalent", f"≈ {_fmt(total / (rate or USD_LBP_RATE))} USD at "
                                      f"{_fmt(rate or USD_LBP_RATE)} LBP per dollar.")


def run_checks(inv: dict, ctx: dict | None = None) -> dict:
    """ctx: {"run_id", "sha", "phash"} of the current run, for duplicate detection."""
    f = []

    def add(level, code, msg):
        f.append({"level": level, "code": code, "msg": msg})

    if not inv.get("is_invoice"):
        add("error", "not_invoice", "This image does not look like an invoice or receipt.")
        return {"status": "blocked", "findings": f, "whatsapp_draft": None}

    if looks_like_injection(inv.get("instructions_in_image")):
        add("warn", "injection", f"Text addressed to the AI was found on the invoice and ignored: "
                                 f"“{inv['instructions_in_image'][:160]}”")

    for field, label in (("supplier_name", "Supplier"), ("invoice_number", "Invoice number"),
                         ("invoice_date", "Date"), ("total", "Total"), ("currency", "Currency")):
        if inv.get(field) in (None, ""):
            add("warn", f"missing_{field}", f"{label} not found on the invoice.")

    currency_checks(inv, add)

    if inv.get("readability") != "good":
        add("warn", "readability", f"Photo readability: {inv.get('readability')}. Check the values.")
    if inv.get("uncertain_fields"):
        add("warn", "uncertain", "AI not sure about: " + ", ".join(inv["uncertain_fields"]))

    lines = inv.get("lines") or []
    # line totals may be printed with tax included (unit price before tax): accept the invoice's own rate
    tax_rates = {0.0, VAT_RATE}
    if inv.get("vat_amount") and inv.get("subtotal"):
        sub0 = inv["subtotal"] - (inv.get("discount") or 0)
        for base in (sub0, sub0 - inv["vat_amount"]):
            if base > 0:
                tax_rates.add(round(inv["vat_amount"] / base, 4))
    if not lines:
        add("warn", "no_lines", "No item lines found.")
    for i, ln in enumerate(lines, 1):
        q, p, t = ln.get("quantity"), ln.get("unit_price"), ln.get("line_total")
        ld = ln.get("line_discount") or 0
        if q is not None and p is not None and t is not None and not any(
                _close((q * p - ld) * (1 + r), t, tol_abs=0.06) or _close(q * p * (1 - ld / 100) * (1 + r), t, tol_abs=0.06)
                for r in tax_rates):
            add("warn", "line_math", f"Line {i} ({ln['description'][:40]}): {_fmt(q)} x {_fmt(p)} = "
                                     f"{_fmt(q * p)}, invoice says {_fmt(t)}.")

    line_sum = sum(ln["line_total"] for ln in lines if ln.get("line_total") is not None)
    has_all_totals = lines and all(ln.get("line_total") is not None for ln in lines)
    sub, disc, vat, total = inv.get("subtotal"), inv.get("discount") or 0, inv.get("vat_amount"), inv.get("total")
    other = inv.get("other_charges") or 0
    # Accept VAT-exclusive (sub + VAT = total) and VAT-inclusive invoices ("total includes VAT"),
    # and cash rounding to 0.05.
    if has_all_totals:
        targets = [x for x in (sub, total, (total - (vat or 0) - other + disc) if total is not None else None) if x is not None]
        if targets and not any(_close(line_sum, t, tol_abs=0.06) for t in targets):
            add("warn", "sum_math", f"Item lines add up to {_fmt(line_sum)}, which matches neither the subtotal "
                                    f"({_fmt(sub) if sub is not None else '-'}) nor the total ({_fmt(total) if total is not None else '-'}).")
    if sub is not None and total is not None:
        exclusive = sub - disc + (vat or 0) + other
        inclusive = sub - disc + other
        if not (_close(exclusive, total, tol_abs=0.06) or _close(inclusive, total, tol_abs=0.06)):
            add("warn", "total_math", f"Subtotal {_fmt(sub)} - discount {_fmt(disc)} + VAT {_fmt(vat or 0)}"
                                      + (f" + other charges {_fmt(other)}" if other else "")
                                      + f" = {_fmt(exclusive)}, invoice total says {_fmt(total)}.")
    # printed VAT rate vs VAT amount
    rate = inv.get("vat_rate")
    if rate and vat and sub and (sub - disc) > 0 and not _close(vat, (sub - disc) * rate / 100, tol_abs=0.06, tol_rel=0.02):
        add("warn", "vat_mismatch", f"VAT {_fmt(vat)} is not {_fmt(rate)}% of {_fmt(sub - disc)} "
                                    f"(= {_fmt((sub - disc) * rate / 100)}).")
    # payment: total - paid = balance
    paid, bal = inv.get("amount_paid"), inv.get("balance_due")
    if total is not None and paid is not None and bal is not None and not _close(total - paid, bal, tol_abs=0.06):
        add("warn", "balance_math", f"Total {_fmt(total)} - paid {_fmt(paid)} = {_fmt(total - paid)}, "
                                    f"but the balance printed is {_fmt(bal)}.")
    if inv.get("document_type") == "credit_note":
        add("info", "credit_note", "This is a CREDIT NOTE (money owed back by the supplier), not a bill to pay.")
    if vat and sub and not _close(vat, (sub - disc) * VAT_RATE, tol_abs=1, tol_rel=0.02):
        add("info", "vat_rate", f"VAT is {100 * vat / (sub - disc):.1f}% of the subtotal "
                                f"(standard rate {VAT_RATE * 100:.0f}%).")

    supplier = inv.get("supplier_name")
    for d in dedupe.find_duplicates(inv, **(ctx or {})):
        add(d["level"], d["code"], d["msg"])

    if supplier and not any(dedupe.same_supplier(supplier, inv.get("supplier_phone"), r["Supplier"], r.get("Phone"))
                            for r in ledger.known_suppliers()):
        add("info", "new_supplier", f"New supplier “{supplier}”: it will be added to the Suppliers sheet.")

    jumps = []
    if supplier:
        prev = ledger.last_prices(supplier)
        for ln in lines:
            key = ledger.norm(ln.get("description"))  # Arabic/French-normalized item name
            if key in prev and ln.get("unit_price") is not None and prev[key][1] == inv.get("currency"):
                old = prev[key][0]
                if old and (ln["unit_price"] - old) / old * 100 > PRICE_JUMP_PCT:
                    pct = (ln["unit_price"] - old) / old * 100
                    jumps.append((ln["description"], old, ln["unit_price"], pct))
                    add("warn", "price_jump", f"{ln['description'][:40]}: price up {pct:.0f}% "
                                              f"({_fmt(old)} → {_fmt(ln['unit_price'])}) since {prev[key][2]}.")

    draft = None
    if jumps:
        items = "\n".join(f"- {d}: {_fmt(o)} → {_fmt(n)} (+{p:.0f}%)" for d, o, n, p in jumps)
        draft = (f"Hello {supplier}, regarding invoice {inv.get('invoice_number') or ''} "
                 f"dated {inv.get('invoice_date') or ''}: these prices are higher than last time:\n{items}\n"
                 f"Can you confirm the new prices? Thank you.")

    if any(x["level"] == "error" for x in f):
        status = "blocked"
    elif any(x["level"] == "warn" for x in f):
        status = "needs_review"
    else:
        status = "ready"
    return {"status": status, "findings": f, "whatsapp_draft": draft}
