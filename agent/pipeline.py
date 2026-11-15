"""The agent's job, start to finish:

  trigger (camera capture / photo upload)
   -> 1. read the invoice (Claude vision, extract.py)
   -> 2. check it (math, duplicates, new supplier, price jumps; checks.py)
   -> 3. prepare the ledger entry + WhatsApp draft, wait for the owner
   -> 4. owner clicks Approve  -> written to ledger.xlsx   (the only irreversible step)
        owner clicks Reject   -> nothing written
"""
import json
import queue
import threading
import shutil
import uuid
from datetime import datetime

from . import dedupe, ledger
from .fields import KEYS, LINE_FIELDS
from .textnorm import currency_code
from .checks import run_checks
from .config import CASES, IMAGES, PENDING, RUNS_LOG
from .extract import extract_invoice

KEY_FIELDS = list(KEYS) + ["extra_fields", "notes"]   # every field of the data model (agent/fields.py)
LINE_KEYS = [f[0] for f in LINE_FIELDS]


def _normalize_edit(rec: dict, edited: dict) -> dict:
    """The human may type the currency as 'ل.ل', 'L.L.', 'livres', '$'... -> ISO code. A guessed currency stays
    'guessed' only while the human leaves it unchanged."""
    out = dict(edited)
    typed = out.get("currency")
    out["currency"] = currency_code(typed) or (typed.upper() if isinstance(typed, str) and typed else None)
    ext = rec.get("extracted") or {}
    out["currency_guessed"] = bool(ext.get("currency_guessed")) and out["currency"] == ext.get("currency")
    return out


def _save(rec):
    (PENDING / f"{rec['run_id']}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")


def _log(event):
    with RUNS_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def load(run_id) -> dict:
    p = PENDING / f"{run_id}.json"
    if not p.exists() or not run_id.replace("-", "").isalnum():
        raise KeyError(run_id)
    return json.loads(p.read_text(encoding="utf-8"))


def _safe_phash(image_bytes):
    try:
        return dedupe.photo_hash(image_bytes)
    except Exception:  # noqa: BLE001 - unreadable image: the model step will report it
        return None


def _ctx(rec):
    return {"run_id": rec["run_id"], "sha": rec.get("image_sha256"), "phash": rec.get("image_phash")}


def _create(image_bytes: bytes, media_type: str, source: str, meta: dict | None = None, mode: str = "full",
            doc: dict | None = None) -> dict:
    """Store the photo/document instantly (the camera is free again) and create the run record.
    doc (from documents.to_pages): {"kind", "pages": [jpeg...], "total_pages", "skipped_pages", "original": bytes}"""
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    ext = {"image/png": ".png", "image/webp": ".webp"}.get(media_type, ".jpg")
    image_name = run_id + ext
    (IMAGES / image_name).write_bytes(image_bytes)
    pages, original = [image_name], None
    if doc:
        for i, pg in enumerate(doc["pages"][1:], 2):        # pages 2..n as their own images
            name = f"{run_id}-p{i}.jpg"
            (IMAGES / name).write_bytes(pg)
            pages.append(name)
        orig_kind = doc.get("container") or doc["kind"]
        if orig_kind not in ("jpeg", "png", "webp"):          # keep the original PDF/Word/Excel/email... for audit
            original = f"{run_id}-original.{orig_kind}"
            (IMAGES / original).write_bytes(doc["original"])
    fingerprint_src = doc["original"] if doc else image_bytes
    rec = {"run_id": run_id, "created": datetime.now().isoformat(timespec="seconds"), "source": source,
           "meta": meta or {}, "image": image_name, "pages": pages, "original": original,
           "doc_kind": doc["kind"] if doc else None, "container": doc.get("container") if doc else None,
           "via": doc.get("via") if doc else None, "inner_name": doc.get("inner_name") if doc else None, "total_pages": doc["total_pages"] if doc else 1,
           "skipped_pages": doc["skipped_pages"] if doc else 0,
           "state": "queued", "media_type": media_type, "mode": mode,
           # fingerprints for duplicate detection (same file / same paper photographed again)
           "image_sha256": dedupe.file_hash(fingerprint_src), "image_phash": _safe_phash(image_bytes)}
    _save(rec)  # saved now, so a second copy uploaded while this one is still being read is detected too
    return rec


def _read(rec: dict) -> dict:
    """The slow part (AI on the Jetson, ~15-25 s), then the checks."""
    run_id = rec["run_id"]
    image_bytes = (IMAGES / rec["image"]).read_bytes()
    rec["state"] = "reading"
    rec["started"] = datetime.now().isoformat(timespec="seconds")
    _save(rec)
    try:
        page_names = rec.get("pages") or [rec["image"]]
        if len(page_names) == 1:
            out = extract_invoice(image_bytes, rec.get("media_type", "image/jpeg"), rec.get("mode", "full"))
        else:   # multi-page document: read every page, then merge into one invoice
            outs = []
            for i, name in enumerate(page_names, 1):
                rec["reading_page"] = i
                _save(rec)
                outs.append(extract_invoice((IMAGES / name).read_bytes(), "image/jpeg", rec.get("mode", "full")))
            out = merge_pages(outs)
    except Exception as e:  # noqa: BLE001 - surface any failure to the UI, never crash the station
        rec.update(state="failed", error=f"{type(e).__name__}: {e}")
        _save(rec)
        _log({"run_id": run_id, "event": "failed", "error": rec["error"]})
        return rec
    rec["extracted"] = out["invoice"]
    rec["usage"] = out["usage"]
    rec["check"] = run_checks(out["invoice"], _ctx(rec))
    if rec.get("skipped_pages"):
        rec["check"]["findings"].insert(0, {"level": "warn", "code": "pages_skipped",
            "msg": f"This document has {rec['total_pages']} pages; only the first {len(rec['pages'])} were read. "
                   f"Check the remaining lines and totals by hand."})
        if rec["check"]["status"] == "ready":
            rec["check"]["status"] = "needs_review"
    rec["state"] = "blocked" if rec["check"]["status"] == "blocked" else "awaiting_approval"
    _save(rec)
    _log({"run_id": run_id, "event": "extracted", "status": rec["check"]["status"], **out["usage"]})
    return rec


def merge_pages(outs: list) -> dict:
    """One invoice from several pages: header fields from the first page that has them, item lines from all
    pages in order (repeated lines dropped), totals/payment from the LAST page that prints them."""
    from .fields import KEYS
    last_wins = {"subtotal", "discount", "vat_amount", "vat_rate", "other_charges", "total", "total_lbp",
                 "amount_paid", "balance_due"}
    invs = [o["invoice"] for o in outs]
    merged = dict(invs[0])
    for k in KEYS:
        vals = [i.get(k) for i in invs if i.get(k) not in (None, "")]
        if vals:
            merged[k] = vals[-1] if k in last_wins else vals[0]
    lines, seen = [], set()
    for inv in invs:
        for ln in inv.get("lines") or []:
            key = (str(ln.get("description", "")).strip().lower(), ln.get("quantity"), ln.get("line_total"))
            if key not in seen:
                seen.add(key)
                lines.append(ln)
    merged["lines"] = lines
    # a page read on its own can mislabel a number (e.g. the VAT read as the subtotal on a totals-only page):
    # if one of the pages' subtotals matches the sum of all item lines, prefer that one
    line_sum = sum(ln.get("line_total") or 0 for ln in lines)
    subs = [i.get("subtotal") for i in invs if isinstance(i.get("subtotal"), (int, float))]
    if lines and subs:
        match = [x for x in subs if abs(x - line_sum) <= max(0.06, 0.005 * line_sum)]
        if match:
            merged["subtotal"] = match[-1]
    extras, labels = [], set()
    for inv in invs:
        for e in inv.get("extra_fields") or []:
            if e.get("label") not in labels:
                labels.add(e.get("label"))
                extras.append(e)
    merged["extra_fields"] = extras
    merged["notes"] = list(dict.fromkeys(n for inv in invs for n in inv.get("notes") or []))
    merged["instructions_in_image"] = " | ".join(i["instructions_in_image"] for i in invs if i.get("instructions_in_image")) or None
    merged["is_invoice"] = any(i.get("is_invoice", True) for i in invs)
    u = [o["usage"] for o in outs]
    usage = {"model": u[0]["model"], "pages": len(outs),
             "input_tokens": sum(x.get("input_tokens", 0) for x in u), "output_tokens": sum(x.get("output_tokens", 0) for x in u),
             "cost_usd": round(sum(x.get("cost_usd", 0) for x in u), 5), "seconds": round(sum(x.get("seconds", 0) for x in u), 1)}
    return {"invoice": merged, "usage": usage}


def process(image_bytes: bytes, media_type: str, source: str, meta: dict | None = None, mode: str = "full",
            doc: dict | None = None) -> dict:
    """Synchronous: photo -> result (used by tests and scripts)."""
    return _read(_create(image_bytes, media_type, source, meta, mode, doc))


# --- Scanner mode: the photo is taken instantly, the reading happens in the background, one at a time
# (the Jetson GPU reads one invoice at a time), so the user can capture the next invoice right away.
_QUEUE: "queue.Queue[str]" = queue.Queue()
_worker_started = threading.Event()


def _worker():
    while True:
        run_id = _QUEUE.get()
        try:
            _read(load(run_id))
        except Exception as e:  # noqa: BLE001 - never let the worker die
            try:
                rec = load(run_id)
                rec.update(state="failed", error=f"{type(e).__name__}: {e}")
                _save(rec)
            except Exception:  # noqa: BLE001
                pass
        finally:
            _QUEUE.task_done()


def submit(image_bytes: bytes, media_type: str, source: str, meta: dict | None = None, mode: str = "full",
           doc: dict | None = None) -> dict:
    """Asynchronous: returns at once with state "queued"; poll load(run_id) for the result."""
    if not _worker_started.is_set():
        _worker_started.set()
        threading.Thread(target=_worker, daemon=True, name="invoice-reader").start()
        for p in PENDING.glob("*.json"):   # runs interrupted by a restart: read them again
            r = json.loads(p.read_text(encoding="utf-8"))
            if r.get("state") in ("queued", "reading"):
                _QUEUE.put(r["run_id"])
    rec = _create(image_bytes, media_type, source, meta, mode, doc)
    rec["queue_position"] = _QUEUE.qsize() + 1
    _QUEUE.put(rec["run_id"])
    return rec


def recheck(run_id: str, edited: dict) -> dict:
    rec = load(run_id)
    return run_checks(_normalize_edit(rec, edited) | {"is_invoice": rec["extracted"].get("is_invoice", True)}, _ctx(rec))


def count_edits(before: dict, after: dict) -> int:
    n = sum(1 for k in KEY_FIELDS if (before.get(k) or None) != (after.get(k) or None))
    bl, al = before.get("lines") or [], after.get("lines") or []
    n += abs(len(bl) - len(al))
    for a, b in zip(bl, al):
        n += sum(1 for k in LINE_KEYS if (a.get(k) or None) != (b.get(k) or None))
    return n


def approve(run_id: str, edited: dict, approved_by: str) -> dict:
    """Called ONLY from the web UI's Approve button (human click)."""
    rec = load(run_id)
    if rec["state"] not in ("awaiting_approval", "blocked"):
        raise ValueError(f"run is {rec['state']}, cannot approve")
    final = rec["extracted"] | {k: edited.get(k) for k in KEY_FIELDS + ["lines"] if k in edited}
    final = _normalize_edit(rec, final)
    check = run_checks(final, _ctx(rec))
    if check["status"] == "blocked":
        raise ValueError("still blocked: " + "; ".join(x["msg"] for x in check["findings"] if x["level"] == "error"))
    edits = count_edits(rec["extracted"], final)
    approval = {"decision": "approve", "approved_by": approved_by.strip(),
                "at": datetime.now().isoformat(timespec="seconds"), "edits": edits}
    saved = ledger.commit_invoice(run_id, final, approval, rec["image"])   # writes + reads back to verify
    rec.update(state="approved", final=final, approval=approval, final_check=check, saved=saved)
    _save(rec)
    _log({"run_id": run_id, "event": "approved", "edits": edits, "human_needed": edits > 0})
    return rec


def reject(run_id: str, by: str, reason: str) -> dict:
    rec = load(run_id)
    if rec["state"] == "approved":
        raise ValueError("already approved")
    rec.update(state="rejected", rejection={"by": by, "reason": reason, "at": datetime.now().isoformat(timespec="seconds")})
    _save(rec)
    _log({"run_id": run_id, "event": "rejected", "reason": reason})
    return rec


def save_as_case(run_id: str, corrected: dict, name: str) -> str:
    """Store the photo + human-verified values as an eval case (ground truth)."""
    rec = load(run_id)
    safe = "".join(c for c in name if c.isalnum() or c in "-_") or run_id
    src = IMAGES / rec["image"]
    shutil.copy(src, CASES / (safe + src.suffix))
    truth = {k: corrected.get(k) for k in KEY_FIELDS + ["lines"]}
    truth["is_invoice"] = rec["extracted"].get("is_invoice", True)
    (CASES / f"{safe}.expected.json").write_text(json.dumps(truth, ensure_ascii=False, indent=2), encoding="utf-8")
    return safe


def recent(limit=30):
    recs = sorted(PENDING.glob("*.json"), reverse=True)[:limit]
    out = []
    for p in recs:
        r = json.loads(p.read_text(encoding="utf-8"))
        inv = r.get("final") or r.get("extracted") or {}
        out.append({"run_id": r["run_id"], "state": r["state"], "created": r["created"],
                    "supplier": inv.get("supplier_name"), "total": inv.get("total"), "currency": inv.get("currency"),
                    "status": (r.get("check") or {}).get("status"), "cost": (r.get("usage") or {}).get("cost_usd")})
    return out


def stats():
    runs, approved, human, cost, failed = 0, 0, 0, 0.0, 0
    if RUNS_LOG.exists():
        # errors="replace" + skip bad lines: a power cut mid-write leaves a broken (e.g. NUL-filled) line
        for line in RUNS_LOG.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                e = json.loads(line.replace(chr(0), "").strip())
            except ValueError:
                continue
            if not isinstance(e, dict):
                continue
            if e.get("event") == "extracted":
                runs += 1
                cost += e.get("cost_usd", 0)
            elif e.get("event") == "approved":
                approved += 1
                human += 1 if e.get("human_needed") else 0
            elif e.get("event") == "failed":
                failed += 1
    return {"runs": runs, "approved": approved, "approved_without_edits": approved - human,
            "needed_human_edit": human, "failed": failed, "total_cost_usd": round(cost, 4),
            "avg_cost_usd": round(cost / runs, 4) if runs else None}


# --- Deleting test data (asked for in the UI; irreversible for the user, so the server keeps a backup copy
# in data/deleted/ and refuses while an invoice is still being read).
_DEL_LOCK = threading.Lock()


def _backup_dir(tag: str):
    from .config import DATA
    d = DATA / "deleted" / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{tag}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _drop_log_lines(run_ids=None, bak=None):
    if not RUNS_LOG.exists():
        return
    lines = RUNS_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
    if bak is not None:
        (bak / "runs.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    keep = []
    if run_ids is not None:
        for line in lines:
            try:
                rid = json.loads(line.replace(chr(0), "").strip()).get("run_id")
            except ValueError:
                continue
            if rid not in run_ids:
                keep.append(line)
    RUNS_LOG.write_text("".join(x + "\n" for x in keep), encoding="utf-8")


def delete_run(run_id: str) -> dict:
    """Forget one invoice test: its run, files, log lines and (if it was approved) its ledger rows."""
    with _DEL_LOCK:
        rec = load(run_id)
        if rec.get("state") in ("queued", "reading"):
            raise ValueError("This invoice is still being read - wait until it finishes, then delete it.")
        bak = _backup_dir(run_id)
        from .config import LEDGER_XLSX
        if LEDGER_XLSX.exists():
            shutil.copy2(LEDGER_XLSX, bak / "ledger.xlsx")
        removed = ledger.delete_runs({run_id})
        files = [f for f in IMAGES.glob(f"{run_id}*") if f.is_file()]
        for f in files:
            shutil.move(str(f), bak / f.name)
        shutil.move(str(PENDING / f"{run_id}.json"), bak / f"{run_id}.json")
        _drop_log_lines({run_id}, bak)
        return {"deleted": run_id, "files": len(files), "ledger_rows": removed, "backup": bak.name}


def clear_all() -> dict:
    """Forget every invoice test: all runs, files, the run log and every ledger row (headers kept)."""
    with _DEL_LOCK:
        recs = [json.loads(p.read_text(encoding="utf-8")) for p in PENDING.glob("*.json")]
        if any(r.get("state") in ("queued", "reading") for r in recs):
            raise ValueError("An invoice is still being read - wait until it finishes, then clear.")
        bak = _backup_dir("all")
        from .config import LEDGER_XLSX
        if LEDGER_XLSX.exists():
            shutil.copy2(LEDGER_XLSX, bak / "ledger.xlsx")
        removed = ledger.delete_runs(None)
        n_files = 0
        for folder in (PENDING, IMAGES):
            for f in folder.iterdir():
                if f.is_file():
                    shutil.move(str(f), bak / f.name)
                    n_files += 1
        _drop_log_lines(None, bak)
        return {"runs": len(recs), "files": n_files, "ledger_rows": removed, "backup": bak.name}
