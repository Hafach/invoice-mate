"""Turn any file an invoice can arrive in into page images the vision model can read.

  Images      JPG, PNG, WEBP, BMP, GIF, TIFF (multi-page scans), HEIC (iPhone)
  PDF         emailed or scanned invoices (rendered with PDFium, the PDF engine of Chrome)
  Office      DOCX, DOC, XLSX, XLS, PPTX, PPT, ODT, ODS, ODP, RTF  -> LibreOffice (headless) -> PDF
  Text / web  HTML, TXT, CSV, XML (e-invoices), JSON                -> LibreOffice -> PDF
  Email       EML: the invoice attachment (PDF, image, Word, Excel...), else the email text
  Archive     ZIP: the first invoice-like file inside

The type is detected from the CONTENT (magic bytes), the file name only breaks ties (e.g. old .doc vs .xls).
"""
import email
import email.policy
import io
import os
import shutil
import subprocess
import tempfile
import threading
import zipfile
from pathlib import Path

from PIL import Image, ImageOps, ImageSequence

MAX_PAGES = 3            # pages read by the model (each page = one AI pass of ~20-45 s on the Jetson)
RENDER_LONG_SIDE = 2000  # px of a rendered PDF page (the model step shrinks it further)
MAX_UPLOAD_BYTES = 25_000_000
SOFFICE_TIMEOUT = 150

IMAGE_KINDS = {"jpeg", "png", "webp", "bmp", "gif", "tiff", "heic"}
OFFICE_EXT = {"docx": "docx", "doc": "doc", "xlsx": "xlsx", "xls": "xls", "pptx": "pptx", "ppt": "ppt",
              "odt": "odt", "ods": "ods", "odp": "odp", "rtf": "rtf", "html": "html", "txt": "txt", "csv": "csv",
              "xml": "txt", "json": "txt"}   # xml/json are shown as text (e-invoices are readable as text)
# preference when an email or a zip contains several files
PRIORITY = ["pdf", "jpeg", "png", "heic", "tiff", "webp", "docx", "doc", "xlsx", "xls", "odt", "ods", "rtf", "html",
            "pptx", "ppt", "odp", "bmp", "gif", "csv", "xml", "txt", "json"]


class UnsupportedDocument(ValueError):
    pass


# ---------------------------------------------------------------- detection
def kind_of(data: bytes, filename: str | None = None) -> str:
    head = data[:16]
    ext = (Path(filename).suffix.lower().lstrip(".") if filename else "")
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"\xff\xd8"):
        return "jpeg"
    if head.startswith(b"\x89PNG"):
        return "png"
    if head[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return "tiff"
    if head[:2] == b"BM":
        return "bmp"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[4:8] == b"ftyp" and data[8:12] in (b"heic", b"heix", b"mif1", b"msf1", b"hevc", b"heim", b"heis"):
        return "heic"
    if head.startswith(b"PK\x03\x04"):
        return _zip_kind(data)
    if head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):   # old Office (OLE): name decides
        return {"xls": "xls", "ppt": "ppt", "msg": "msg"}.get(ext, "doc")
    if head.startswith(b"{\\rtf"):
        return "rtf"
    text = _as_text(data)
    if text is None:
        return "unknown"
    low = text.lstrip("﻿ \r\n\t")[:600].lower()
    if low.startswith(("<!doctype html", "<html")) or "<body" in low[:400]:
        return "html"
    if low.startswith("<?xml") or ext == "xml":
        return "xml"
    if ext == "eml" or _looks_like_email(text):
        return "eml"
    if ext == "csv":
        return "csv"
    if ext == "json" or low.startswith(("{", "[")):
        return "json"
    return "txt"


def _zip_kind(data: bytes) -> str:
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        names = set(z.namelist())
    except zipfile.BadZipFile:
        return "unknown"
    if "word/document.xml" in names:
        return "docx"
    if "xl/workbook.xml" in names:
        return "xlsx"
    if "ppt/presentation.xml" in names:
        return "pptx"
    if "mimetype" in names:
        mt = z.read("mimetype").decode("ascii", "ignore")
        for suffix, kind in (("text", "odt"), ("spreadsheet", "ods"), ("presentation", "odp")):
            if mt.endswith(suffix):
                return kind
    return "zip"


def _as_text(data: bytes):
    sample = data[:20000]
    if b"\x00" in sample:
        return None
    for enc in ("utf-8-sig", "cp1256", "latin-1"):   # cp1256 = Arabic Windows
        try:
            t = sample.decode(enc)
        except UnicodeDecodeError:
            continue
        printable = sum(c.isprintable() or c in "\r\n\t" for c in t)
        return t if printable / max(1, len(t)) > 0.95 else None
    return None


def _looks_like_email(text: str) -> bool:
    head = text[:3000]
    keys = sum(head.startswith(k) or f"\n{k}" in head for k in ("From:", "To:", "Subject:", "Date:", "MIME-Version:", "Received:"))
    return keys >= 3


# ---------------------------------------------------------------- converters
def _jpeg(im: Image.Image) -> bytes:
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=90)
    return buf.getvalue()


def _render_pdf(data: bytes):
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(data)
    try:
        total = len(pdf)
        pages = []
        for i in range(min(total, MAX_PAGES)):
            page = pdf[i]
            w, h = page.get_size()
            pages.append(_jpeg(page.render(scale=RENDER_LONG_SIDE / max(w, h)).to_pil()))
            page.close()
        return pages, total
    finally:
        pdf.close()


def _images(data: bytes, kind: str):
    if kind == "heic":
        try:
            import pillow_heif
        except ImportError as e:
            raise UnsupportedDocument("HEIC photo: the HEIC reader is not installed on this device") from e
        try:   # direct decode: works with any Pillow (the Jetson's Pillow 9 can't use the plugin)
            h = pillow_heif.open_heif(io.BytesIO(data))
            im = Image.frombytes(h.mode, h.size, bytes(h.data), "raw", h.mode, h.stride)
        except Exception as e:  # noqa: BLE001
            raise UnsupportedDocument("Could not read this HEIC image (damaged or incomplete file?)") from e
        return [_jpeg(im)], 1
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception as e:  # noqa: BLE001 - truncated / damaged / fake image
        raise UnsupportedDocument(f"Could not read this {kind.upper()} image (damaged or incomplete file?)") from e
    frames = list(ImageSequence.Iterator(im)) if kind == "tiff" else [im]
    if kind == "jpeg" and len(frames) == 1:
        return [data], 1
    return [_jpeg(ImageOps.exif_transpose(f.copy())) for f in frames[:MAX_PAGES]], len(frames)


_SOFFICE_LOCK = threading.Lock()   # one LibreOffice conversion at a time (it uses one profile)


def _soffice() -> str | None:
    return shutil.which("soffice") or shutil.which("libreoffice")


def _profile_dir() -> Path:
    from .config import DATA
    d = DATA / "lo_profile"   # permanent: LibreOffice's first start (~60 s) happens only once
    d.mkdir(parents=True, exist_ok=True)
    return d


def office_to_pdf(data: bytes, kind: str) -> bytes:
    exe = _soffice()
    if not exe:
        raise UnsupportedDocument(f"{kind.upper()} files need LibreOffice, which is not installed on this device")
    with _SOFFICE_LOCK, tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / f"invoice.{OFFICE_EXT.get(kind, kind)}"
        src.write_bytes(data)
        def run(fmt, path):
            cmd = [exe, f"-env:UserInstallation={_profile_dir().resolve().as_uri()}", "--headless", "--norestore",
                   "--convert-to", fmt, "--outdir", tmp, str(path)]
            try:
                subprocess.run(cmd, capture_output=True, timeout=SOFFICE_TIMEOUT, env={**os.environ, "HOME": tmp})
            except subprocess.TimeoutExpired as e:
                raise UnsupportedDocument(f"Converting the {kind.upper()} file took too long") from e

        if kind in ("xlsx", "xls", "ods", "csv"):
            # spreadsheets: "fit each sheet to one page" (like Excel's page setup), otherwise columns spill
            # onto extra PDF pages and the AI sees half a table per page. Works with any LibreOffice version.
            if kind != "xlsx":
                run("xlsx", src)
                src = src.with_suffix(".xlsx")
            if src.exists():
                _fit_sheets_to_page(src)
        run("pdf", src)
        out = src.with_suffix(".pdf")
        if not out.exists() or out.stat().st_size == 0:
            raise UnsupportedDocument(f"Could not convert this {kind.upper()} file (damaged or password-protected?)")
        return out.read_bytes()


def _fit_sheets_to_page(path: Path):
    from openpyxl import load_workbook
    try:
        wb = load_workbook(path)
    except Exception:  # noqa: BLE001 - keep LibreOffice's default if the file can't be opened
        return
    for ws in wb.worksheets:
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 1
        if (ws.max_column or 0) > 6:
            ws.page_setup.orientation = "landscape"
    wb.save(path)


def warmup():
    """Start LibreOffice once in the background so the first real document isn't slow (~60 s cold start)."""
    if _soffice():
        try:
            office_to_pdf(b"warm-up", "txt")
        except Exception:  # noqa: BLE001
            pass


def _pick_best(files):
    """files: [(name, bytes)] -> the most invoice-like one (PDF first, then images, then office files...)."""
    ranked = []
    for name, data in files:
        k = kind_of(data, name)
        if k in PRIORITY:
            ranked.append((PRIORITY.index(k), name, data))
    ranked.sort(key=lambda r: r[0])
    return ranked[0][1:] if ranked else None


def _from_email(data: bytes) -> tuple[bytes, str, dict]:
    msg = email.message_from_bytes(data, policy=email.policy.default)
    attachments = [(part.get_filename() or "attachment", part.get_payload(decode=True) or b"")
                   for part in msg.iter_attachments()]
    info = {"email_subject": str(msg.get("subject", "")), "email_from": str(msg.get("from", ""))}
    best = _pick_best(attachments)
    if best:
        info["email_attachment"] = best[0]
        return best[1], best[0], info
    body = msg.get_body(preferencelist=("html", "plain"))
    if body is None:
        raise UnsupportedDocument("This email has no attachment and no text")
    content = body.get_content()
    is_html = body.get_content_type() == "text/html"
    info["email_attachment"] = None
    return content.encode("utf-8"), "email-body.html" if is_html else "email-body.txt", info


def _from_zip(data: bytes) -> tuple[bytes, str]:
    z = zipfile.ZipFile(io.BytesIO(data))
    files = [(n, z.read(n)) for n in z.namelist() if not n.endswith("/") and z.getinfo(n).file_size < MAX_UPLOAD_BYTES]
    best = _pick_best(files)
    if not best:
        raise UnsupportedDocument("This ZIP contains no invoice file (PDF, image, Word, Excel...)")
    return best[1], best[0]


# ---------------------------------------------------------------- main entry
def to_pages(data: bytes, filename: str | None = None, _depth: int = 0) -> dict:
    """Returns {"kind", "pages": [jpeg...], "total_pages", "skipped_pages", "via"}; raises UnsupportedDocument."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise UnsupportedDocument(f"File too large ({len(data) // 1_000_000} MB, max {MAX_UPLOAD_BYTES // 1_000_000} MB)")
    kind = kind_of(data, filename)
    if kind in ("eml", "zip") and _depth < 2:            # containers: open the invoice inside
        if kind == "eml":
            inner, inner_name, info = _from_email(data)
        else:
            (inner, inner_name), info = _from_zip(data), {}
        res = to_pages(inner, inner_name, _depth + 1)
        res.update(container=kind, inner_name=inner_name, **info)
        res["kind"] = kind if res.get("kind") in ("txt", "html") and kind == "eml" else res["kind"]
        return res
    if kind == "msg":
        raise UnsupportedDocument("Outlook .msg: save the attachment (or the email as .eml) and send that instead")
    if kind == "unknown":
        raise UnsupportedDocument("Unknown file type: send a PDF, a photo, or a Word / Excel / text document")
    via = None
    if kind == "pdf":
        pdf = data
    elif kind in IMAGE_KINDS:
        pages, total = _images(data, kind)
        return {"kind": kind, "pages": pages, "total_pages": total, "skipped_pages": max(0, total - len(pages)), "via": None}
    else:
        pdf, via = office_to_pdf(data, kind), "LibreOffice"
    try:
        pages, total = _render_pdf(pdf)
    except Exception as e:  # noqa: BLE001
        raise UnsupportedDocument(f"Could not open this PDF ({type(e).__name__}): is it password-protected?") from e
    if not pages:
        raise UnsupportedDocument("This document has no pages")
    return {"kind": kind, "pages": pages, "total_pages": total, "skipped_pages": max(0, total - len(pages)), "via": via}
