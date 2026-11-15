"""The shop's Excel ledger: the tool this job really uses.

Sheets: Invoices (one row per invoice), Lines (one row per item), Suppliers.
Writing is ONLY possible through commit_invoice(), which requires an approval
record created by a human click in the web UI (see server.py /api/approve).
"""
import os
import threading
from datetime import datetime

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill

from .config import LEDGER_XLSX
from .textnorm import key, supplier_key

_LOCK = threading.RLock()  # one reader/writer at a time (web requests run in parallel)

INVOICE_COLS = ["Invoice date", "Supplier", "Invoice no.", "Currency", "Subtotal", "Discount",
                "VAT", "Total", "Lines", "Approved by", "Approved at", "Human edits", "Run id", "Image",
                "Total LBP", "Rate (LBP/USD)",
                # general invoice data (added later: appended so older ledgers stay compatible)
                "Document type", "Due date", "Delivery date", "PO / order no.", "Supplier address", "Supplier phone",
                "Supplier email", "Supplier tax ID", "Customer", "Customer address", "Customer tax ID", "VAT rate %",
                "Other charges", "Payment terms", "Payment method", "Amount paid", "Balance due", "Bank / IBAN",
                "Other fields", "Notes"]
LINE_COLS = ["Run id", "Invoice date", "Supplier", "Invoice no.", "Description", "Qty", "Unit price",
             "Line total", "Currency", "Item code", "Unit", "Line discount"]
SUPPLIER_COLS = ["Supplier", "Phone", "First seen"]


def norm(s) -> str:
    """Normalize text for matching (Arabic / French / English, see textnorm.py)."""
    return key(s)


def _style_header(ws):
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="9B1B30")
    ws.freeze_panes = "A2"


def _save(wb):
    """Write to a temp file then swap, so a reader never sees a half-written file."""
    tmp = LEDGER_XLSX.with_suffix(".tmp.xlsx")
    wb.save(tmp)
    os.replace(tmp, LEDGER_XLSX)


def _open():
    if LEDGER_XLSX.exists():
        wb = load_workbook(LEDGER_XLSX)
        for name, cols in (("Invoices", INVOICE_COLS), ("Lines", LINE_COLS)):
            ws = wb[name]
            header = [c.value for c in ws[1]]
            if header[:len(cols)] != cols:  # ledger made by an older version: add the new columns
                for i, col in enumerate(cols, 1):
                    ws.cell(row=1, column=i, value=col)
                _style_header(ws)
        return wb
    wb = Workbook()
    ws = wb.active
    ws.title = "Invoices"
    ws.append(INVOICE_COLS)
    _style_header(ws)
    for name, cols in (("Lines", LINE_COLS), ("Suppliers", SUPPLIER_COLS)):
        w = wb.create_sheet(name)
        w.append(cols)
        _style_header(w)
    for w in wb.worksheets:
        from openpyxl.utils import get_column_letter
        for i in range(1, 40):
            w.column_dimensions[get_column_letter(i)].width = 16
    _save(wb)
    return wb


def _rows(ws):
    header = [c.value for c in ws[1]]
    return [dict(zip(header, r)) for r in ws.iter_rows(min_row=2, values_only=True) if any(r)]


def read_all() -> dict:
    with _LOCK:
        wb = _open()
        return {name: _rows(wb[name]) for name in ("Invoices", "Lines", "Suppliers")}


def known_suppliers() -> list:
    return read_all()["Suppliers"]


def last_prices(supplier) -> dict:
    """{normalized item description: (unit_price, currency, invoice date)} from the latest approved invoice lines."""
    out = {}
    for r in read_all()["Lines"]:
        if supplier_key(r["Supplier"]) == supplier_key(supplier) and r["Unit price"] is not None:
            out[norm(r["Description"])] = (float(r["Unit price"]), r["Currency"], r["Invoice date"])
    return out


class LedgerLocked(Exception):
    pass


def commit_invoice(run_id: str, inv: dict, approval: dict, image_name: str):
    """Append an approved invoice. Refuses without a human approval record."""
    if not approval or not approval.get("approved_by") or approval.get("decision") != "approve":
        raise PermissionError("ledger write requires a human approval")
    with _LOCK:
        info = _commit(run_id, inv, approval, image_name)
        info.update(verify_saved(run_id, info))
        return info


class SaveNotVerified(Exception):
    pass


def verify_saved(run_id: str, info: dict) -> dict:
    """Re-open ledger.xlsx from disk and check the invoice row and its lines are really there."""
    wb = load_workbook(LEDGER_XLSX, read_only=True)
    try:
        ws = wb["Invoices"]
        header = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
        row = next(ws.iter_rows(min_row=info["row"], max_row=info["row"], values_only=True))
        rec = dict(zip(header, row))
        lines_found = sum(1 for r in wb["Lines"].iter_rows(min_row=2, values_only=True) if r and r[0] == run_id)
    finally:
        wb.close()
    if rec.get("Run id") != run_id or lines_found != info["lines_written"]:
        raise SaveNotVerified(f"ledger.xlsx check failed: row {info['row']} has run {rec.get('Run id')!r}, "
                              f"{lines_found}/{info['lines_written']} lines found")
    return {"verified": True, "verified_total": rec.get("Total"), "verified_supplier": rec.get("Supplier"),
            "file_bytes": LEDGER_XLSX.stat().st_size}


def _commit(run_id, inv, approval, image_name):
    wb = _open()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    wb["Invoices"].append([
        inv.get("invoice_date"), inv.get("supplier_name"), inv.get("invoice_number"), inv.get("currency"),
        inv.get("subtotal"), inv.get("discount"), inv.get("vat_amount"), inv.get("total"), len(inv.get("lines") or []),
        approval["approved_by"], now, approval.get("edits", 0), run_id, image_name,
        inv.get("total_lbp"), inv.get("exchange_rate"),
        inv.get("document_type"), inv.get("due_date"), inv.get("delivery_date"), inv.get("order_number"),
        inv.get("supplier_address"), inv.get("supplier_phone"), inv.get("supplier_email"), inv.get("supplier_tax_id"),
        inv.get("customer_name"), inv.get("customer_address"), inv.get("customer_tax_id"), inv.get("vat_rate"),
        inv.get("other_charges"), inv.get("payment_terms"), inv.get("payment_method"), inv.get("amount_paid"),
        inv.get("balance_due"), inv.get("bank_details"),
        "; ".join(f"{e['label']}: {e['value']}" for e in inv.get("extra_fields") or []) or None,
        " | ".join(inv.get("notes") or []) or None,
    ])
    for ln in inv.get("lines") or []:
        wb["Lines"].append([run_id, inv.get("invoice_date"), inv.get("supplier_name"), inv.get("invoice_number"),
                            ln.get("description"), ln.get("quantity"), ln.get("unit_price"), ln.get("line_total"),
                            inv.get("currency"), ln.get("item_code"), ln.get("unit"), ln.get("line_discount")])
    supplier_added = supplier_key(inv.get("supplier_name")) not in {supplier_key(r["Supplier"]) for r in _rows(wb["Suppliers"])}
    if supplier_added:
        wb["Suppliers"].append([inv.get("supplier_name"), inv.get("supplier_phone"), now])
    row = wb["Invoices"].max_row
    try:
        _save(wb)
    except PermissionError as e:
        raise LedgerLocked("ledger.xlsx is open in Excel - close it and approve again") from e
    return {"file": LEDGER_XLSX.name, "sheet": "Invoices", "row": row, "lines_written": len(inv.get("lines") or []),
            "lines_sheet_rows": wb["Lines"].max_row, "supplier_added": supplier_added, "saved_at": now}


def delete_runs(run_ids=None) -> dict:
    """Remove test entries from the ledger. run_ids=None empties every sheet (headers kept); otherwise the
    Invoices/Lines rows of those runs go, plus Suppliers rows that no remaining invoice uses."""
    with _LOCK:
        wb = _open()
        removed = {}
        for name in ("Invoices", "Lines", "Suppliers"):
            ws = wb[name]
            header = [c.value for c in ws[1]]
            if run_ids is None:
                drop = list(range(2, ws.max_row + 1))
            elif name == "Suppliers":
                left = {supplier_key(r.get("Supplier")) for r in _rows(wb["Invoices"])}
                drop = [i for i, r in enumerate(ws.iter_rows(min_row=2, values_only=True), 2)
                        if any(r) and supplier_key(r[0]) not in left]
            else:
                col = header.index("Run id")
                drop = [i for i, r in enumerate(ws.iter_rows(min_row=2, values_only=True), 2) if r[col] in run_ids]
            for i in reversed(drop):
                ws.delete_rows(i)
            removed[name] = len(drop)
        try:
            _save(wb)
        except PermissionError as e:
            raise LedgerLocked("ledger.xlsx is open in Excel - close it and try again") from e
        return removed
