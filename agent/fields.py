"""The invoice data model: ONE list that drives the AI schema, the cleanup, the web form and the Excel columns.

Covers what appears on supplier invoices, tax invoices, receipts, credit notes, delivery notes and proformas
(UBL / e-invoicing field set, simplified). Anything printed on the invoice that fits none of these goes into
`extra_fields` as label -> value pairs, so unusual invoices lose nothing.

core=True  -> the model must always answer it (null if absent); missing ones are flagged by the checks.
core=False -> optional: the model only writes it when it is printed (saves generation time on the Jetson).
"""

DOC_TYPES = ["invoice", "tax_invoice", "receipt", "credit_note", "debit_note", "delivery_note", "proforma",
             "quotation", "purchase_order", "statement", "other"]

# key, label shown to the user, group, type (str | num | date | enum), core
FIELDS = [
    ("document_type", "Document type", "Document", "enum", True),
    ("invoice_number", "Invoice no.", "Document", "str", True),
    ("invoice_date", "Date", "Document", "date", True),
    ("due_date", "Due date", "Document", "date", False),
    ("delivery_date", "Delivery date", "Document", "date", False),
    ("order_number", "PO / order no.", "Document", "str", False),

    ("supplier_name", "Supplier", "Supplier", "str", True),
    ("supplier_address", "Supplier address", "Supplier", "str", False),
    ("supplier_phone", "Supplier phone", "Supplier", "str", False),
    ("supplier_email", "Supplier email", "Supplier", "str", False),
    ("supplier_tax_id", "Supplier tax / MOF no.", "Supplier", "str", False),

    ("customer_name", "Customer (billed to)", "Customer", "str", False),
    ("customer_address", "Customer address", "Customer", "str", False),
    ("customer_tax_id", "Customer tax / MOF no.", "Customer", "str", False),

    ("currency", "Currency", "Amounts", "str", True),
    ("subtotal", "Subtotal", "Amounts", "num", True),
    ("discount", "Discount", "Amounts", "num", False),
    ("vat_rate", "VAT rate %", "Amounts", "num", False),
    ("vat_amount", "VAT", "Amounts", "num", True),
    ("other_charges", "Other charges (delivery, service, stamp)", "Amounts", "num", False),
    ("total", "Total", "Amounts", "num", True),
    ("total_lbp", "Total in LBP (if also printed)", "Amounts", "num", False),
    ("exchange_rate", "Rate (LBP per $)", "Amounts", "num", False),

    ("payment_terms", "Payment terms", "Payment", "str", False),
    ("payment_method", "Payment method", "Payment", "str", False),
    ("amount_paid", "Amount paid", "Payment", "num", False),
    ("balance_due", "Balance due", "Payment", "num", False),
    ("bank_details", "Bank / IBAN", "Payment", "str", False),
]

LINE_FIELDS = [  # key, label, type, core
    ("item_code", "Code", "str", False),
    ("description", "Item", "str", True),
    ("quantity", "Qty", "num", True),
    ("unit", "Unit", "str", False),
    ("unit_price", "Unit price", "num", True),
    ("line_discount", "Disc.", "num", False),
    ("line_total", "Line total", "num", True),
]

KEYS = [f[0] for f in FIELDS]
NUM_KEYS = [f[0] for f in FIELDS if f[3] == "num"]
DATE_KEYS = [f[0] for f in FIELDS if f[3] == "date"]
CORE_KEYS = [f[0] for f in FIELDS if f[4]]
LINE_NUM_KEYS = [f[0] for f in LINE_FIELDS if f[2] == "num"]


def json_schema(all_required: bool = True) -> dict:
    """all_required=True: the model must answer every field (null if absent). Measured on the Jetson: with optional
    fields the 3B model skipped nearly all of them; requiring them costs a few seconds but fills far more."""
    num = {"anyOf": [{"type": "number"}, {"type": "null"}]}
    s = {"anyOf": [{"type": "string"}, {"type": "null"}]}
    types = {"num": num, "str": s, "date": s, "enum": {"anyOf": [{"type": "string", "enum": DOC_TYPES}, {"type": "null"}]}}
    props = {"is_invoice": {"type": "boolean"}}
    props.update({k: types[t] for k, _, _, t, _ in FIELDS})
    props["lines"] = {"type": "array", "items": {
        "type": "object",
        "properties": {k: (num if t == "num" else {"type": "string"} if k == "description" else s)
                       for k, _, t, _ in LINE_FIELDS},
        # line extras stay optional: forcing them made the 3B model split "Sugar 1kg" into code + item
        "required": [k for k, _, _, core in LINE_FIELDS if core],
    }}
    props["extra_fields"] = {"type": "array", "items": {
        "type": "object", "properties": {"label": {"type": "string"}, "value": {"type": "string"}},
        "required": ["label", "value"]}}
    props["notes"] = {"type": "array", "items": {"type": "string"}}
    return {"type": "object", "properties": props,
            "required": ["is_invoice"] + (KEYS if all_required else CORE_KEYS) + ["lines", "extra_fields", "notes"]}


def ui_spec() -> dict:
    """What the web page needs to draw the form dynamically."""
    groups = []
    for k, label, group, typ, core in FIELDS:
        if not groups or groups[-1]["name"] != group:
            groups.append({"name": group, "fields": []})
        groups[-1]["fields"].append({"key": k, "label": label, "type": typ, "core": core})
    return {"groups": groups, "doc_types": DOC_TYPES,
            "line_fields": [{"key": k, "label": label, "type": t, "core": core} for k, label, t, core in LINE_FIELDS]}
