"""Laptop web app: live camera from the Jetson, the agent's result, and the Approve button.

Run:  python server.py        then open http://127.0.0.1:8400
"""
import os

import httpx
import uvicorn
import ipaddress
import secrets
import time

from fastapi import FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from agent import documents, extract, ledger, pipeline
from agent.config import (HUMAN_HOURLY_USD, HUMAN_MINUTES_PER_INVOICE, IMAGES, JETSON_URL, JETSON_URLS, LEDGER_XLSX,
                          OLLAMA_MODEL, ROOT)

app = FastAPI(title="Invoice agent")


@app.on_event("startup")
def _warm_up_converters():
    """LibreOffice takes ~60 s on its very first start: do it now in the background, not on the first upload."""
    import threading
    threading.Thread(target=documents.warmup, daemon=True, name="libreoffice-warmup").start()
    if os.environ.get("AI_WARMUP", "on") != "off":   # load the local AI now, not on the first invoice
        from agent.extract import warmup as ai_warmup
        threading.Thread(target=ai_warmup, daemon=True, name="ai-warmup").start()

# --- Access control: when the app is reachable on a network (it runs on the Jetson), every /api call needs a
# session obtained with the shop's PIN (APP_PIN in .env). The PIN is checked in code, not by the AI.
APP_PIN = os.environ.get("APP_PIN", "")
_SESSIONS: set[str] = set()
OPEN_PATHS = {"/", "/api/login", "/api/session"}


# --- Network lock: only devices on the Jetson's own Wi-Fi (DEMO mode), the owner's Tailscale devices, the USB
# cable and the Jetson itself may use the app. Anything else - including the internet via Tailscale Funnel -
# gets 403. Enforced here in code, so a leaked link is useless from outside.
ALLOWED_NETS = [ipaddress.ip_network(n.strip()) for n in os.environ.get(
    "ALLOWED_NETS", "127.0.0.0/8,::1/128,10.42.0.0/24,192.168.55.0/24,100.64.0.0/10,fd7a:115c:a1e0::/48").split(",") if n.strip()]


def client_allowed(request: Request) -> bool:
    if request.headers.get("Tailscale-Funnel-Request"):   # came from the public internet through Funnel
        return False
    try:
        ip = ipaddress.ip_address((request.client.host if request.client else "") or "0.0.0.0")
    except ValueError:
        return False
    return any(ip in net for net in ALLOWED_NETS if ip.version == net.version)


NETWORK_LOCK = os.environ.get("NETWORK_LOCK", "on").lower() not in ("off", "0", "false", "no")


@app.middleware("http")
async def network_lock(request: Request, call_next):
    # NETWORK_LOCK=off in .env: public mode (e.g. reachable by anyone through the Tailscale Funnel link)
    if NETWORK_LOCK and not client_allowed(request):
        return HTMLResponse("<h1>Access denied</h1><p>This invoice agent only works on the shop's own Wi-Fi "
                            "(InvoiceAgent).</p>", status_code=403)
    return await call_next(request)


@app.middleware("http")
async def require_pin(request: Request, call_next):
    if APP_PIN and request.url.path.startswith("/api/") and request.url.path not in OPEN_PATHS:
        if request.cookies.get("session") not in _SESSIONS:
            return JSONResponse({"detail": "PIN required"}, status_code=401)
    return await call_next(request)


class Login(BaseModel):
    pin: str


@app.post("/api/login")
def login(body: Login, response: Response):
    if not APP_PIN:
        return {"ok": True}
    if not secrets.compare_digest(body.pin.strip(), APP_PIN):
        time.sleep(1)  # slow down guessing
        raise HTTPException(401, "Wrong PIN")
    token = secrets.token_urlsafe(24)
    _SESSIONS.add(token)
    response.set_cookie("session", token, httponly=True, samesite="strict", max_age=12 * 3600)
    return {"ok": True}


@app.get("/api/session")
def session(request: Request):
    return {"pin_required": bool(APP_PIN), "logged_in": (not APP_PIN) or request.cookies.get("session") in _SESSIONS}


@app.get("/", response_class=HTMLResponse)
def index():
    return (ROOT / "web" / "index.html").read_text(encoding="utf-8")


@app.get("/api/config")
def config():
    return {"jetson_url": JETSON_URL, "model": OLLAMA_MODEL,
            "human_cost_usd": round(HUMAN_MINUTES_PER_INVOICE / 60 * HUMAN_HOURLY_USD, 3),
            "human_minutes": HUMAN_MINUTES_PER_INVOICE}


HOTSPOT_SSID = os.environ.get("HOTSPOT_SSID", "InvoiceAgent")
HOTSPOT_PASS = os.environ.get("HOTSPOT_PASS", "")
HOTSPOT_URL = "http://10.42.0.1:8400"


def _net_mode():
    """DEMO = the Jetson's own Wi-Fi is on; ONLINE = connected to a normal Wi-Fi (read-only check, no root needed)."""
    import subprocess
    try:
        out = subprocess.run(["nmcli", "-t", "-f", "NAME,DEVICE", "con", "show", "--active"], capture_output=True,
                             text=True, timeout=5).stdout
    except Exception:  # noqa: BLE001 - not on the Jetson (e.g. tests on Windows)
        return {"mode": "unknown", "wifi": None}
    wifi = next((ln.split(":")[0] for ln in out.splitlines() if ln.endswith(":wlP1p1s0")), None)
    return {"mode": "demo" if wifi == "InvoiceAgent-AP" else ("online" if wifi else "offline"), "wifi": wifi}


@app.get("/api/network")
def network(request: Request):
    info = _net_mode()
    host = request.client.host if request.client else ""
    on_hotspot = host.startswith("10.42.0.")
    return info | {"ssid": HOTSPOT_SSID, "app_url": HOTSPOT_URL,
                   # the Wi-Fi password is only shown to devices already allowed in (hotspot, Tailscale, USB, local)
                   "password": HOTSPOT_PASS, "you_are_on": "hotspot" if on_hotspot else "other"}


@app.get("/api/network/qr")
def network_qr(what: str = "wifi"):
    """QR codes for the demo: 'wifi' joins the InvoiceAgent Wi-Fi, 'url' opens the app."""
    import io

    import qrcode
    text = HOTSPOT_URL if what == "url" else f"WIFI:T:WPA;S:{HOTSPOT_SSID};P:{HOTSPOT_PASS};;"
    img = qrcode.make(text, box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return Response(buf.getvalue(), media_type="image/png", headers={"Cache-Control": "no-store"})


@app.get("/api/fields")
def fields_spec():
    """The invoice data model (agent/fields.py): the page draws its form from this."""
    from agent.fields import ui_spec
    return ui_spec()


@app.get("/api/ai/health")
def ai_health():
    try:
        return extract.status()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


_jetson = {"url": None}


def jetson_url():
    """First Jetson address that answers (cached until it stops answering)."""
    cands = ([_jetson["url"]] if _jetson["url"] else []) + [u for u in JETSON_URLS if u != _jetson["url"]]
    for u in cands:
        try:
            if httpx.get(f"{u}/health", timeout=1.5).status_code == 200:
                _jetson["url"] = u
                return u
        except Exception:  # noqa: BLE001
            continue
    _jetson["url"] = None
    return None


@app.get("/api/camera/health")
def camera_health():
    u = jetson_url()
    if not u:
        return {"ok": False, "error": "Jetson camera not reachable (tried " + ", ".join(JETSON_URLS) + ")"}
    try:
        return httpx.get(f"{u}/health", timeout=3).json() | {"url": u}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"Jetson camera error at {u} ({type(e).__name__})"}


@app.get("/api/camera/stream")
async def camera_stream():
    u = _jetson["url"] or jetson_url()
    if not u:
        raise HTTPException(502, "camera offline")

    async def gen():
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(None, connect=3)) as c:
                async with c.stream("GET", f"{u}/stream") as r:
                    async for chunk in r.aiter_bytes():
                        yield chunk
        except httpx.HTTPError:
            _jetson["url"] = None  # link dropped; the page reconnects via the next health check
    return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.post("/api/capture")
def capture(force: bool = False, wait: bool = False, mode: str = "full"):
    u = jetson_url()
    if not u:
        raise HTTPException(502, "Jetson camera not reachable")
    try:
        r = httpx.get(f"{u}/snapshot", timeout=10)
        r.raise_for_status()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Could not get a photo from the Jetson camera: {e}")
    meta = {"sharpness": r.headers.get("X-Sharpness"), "blurry": r.headers.get("X-Blurry") == "1"}
    if meta["blurry"] and not force:
        # don't spend ~20-60 s of AI on a photo it can't read
        raise HTTPException(422, f"Photo too blurry (sharpness {meta['sharpness']}). Hold the invoice flat, "
                                 f"30-40 cm from the camera, the WHOLE page in the frame, in good light, "
                                 f"and wait for the sharpness check to turn ✓.")
    if wait:
        return pipeline.process(r.content, "image/jpeg", "jetson-camera", meta, _mode(mode))
    return pipeline.submit(r.content, "image/jpeg", "jetson-camera", meta, _mode(mode))  # camera free again immediately


def _mode(m):
    return m if m in ("full", "fast") else "full"


@app.post("/api/upload")
async def upload(file: UploadFile = File(...), wait: bool = False, mode: str = "full", source: str = "upload"):
    """Any invoice file (photo, PDF, Word, Excel, email, text, ZIP...) or a phone-camera photo."""
    source = source if source in ("upload", "phone-camera") else "upload"
    data = await file.read()
    # PDF / TIFF / BMP / GIF / JPG / PNG / WEBP -> page images (type detected from the content, not the name)
    from starlette.concurrency import run_in_threadpool
    try:
        doc = await run_in_threadpool(documents.to_pages, data, file.filename)
    except documents.UnsupportedDocument as e:
        raise HTTPException(400, str(e))
    doc["original"] = data
    data, mt = doc["pages"][0], "image/jpeg"
    meta = {"filename": file.filename, "kind": doc["kind"], "pages": doc["total_pages"],
            **{k: doc[k] for k in ("email_subject", "email_from", "email_attachment") if doc.get(k)}}
    if len(data) > 4_500_000:
        data, mt = _shrink(data), "image/jpeg"
    if wait:
        return await run_in_threadpool(pipeline.process, data, mt, source, meta, _mode(mode), doc)
    return pipeline.submit(data, mt, source, meta, _mode(mode), doc)


def _shrink(data: bytes) -> bytes:
    import io

    from PIL import Image
    im = Image.open(io.BytesIO(data)).convert("RGB")
    im.thumbnail((2400, 2400))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88)
    return buf.getvalue()


@app.get("/api/runs")
def runs():
    return pipeline.recent()


def _load(run_id):
    try:
        return pipeline.load(run_id)
    except KeyError:
        raise HTTPException(404, "run not found")


@app.get("/api/run/{run_id}")
def run(run_id: str):
    return _load(run_id)


@app.get("/api/image/{name}")
def image(name: str):
    p = (IMAGES / name).resolve()
    if p.parent != IMAGES.resolve() or not p.exists():
        raise HTTPException(404)
    return FileResponse(p)


class Edited(BaseModel):
    invoice: dict
    approved_by: str = ""
    reason: str = ""
    case_name: str = ""


@app.post("/api/run/{run_id}/recheck")
def recheck(run_id: str, body: Edited):
    _load(run_id)
    return pipeline.recheck(run_id, body.invoice)


@app.post("/api/run/{run_id}/approve")
def approve(run_id: str, body: Edited):
    _load(run_id)
    if not body.approved_by.strip():
        raise HTTPException(400, "Type your name to approve")
    try:
        return pipeline.approve(run_id, body.invoice, body.approved_by)
    except ledger.LedgerLocked as e:
        raise HTTPException(409, str(e))
    except ledger.SaveNotVerified as e:
        raise HTTPException(500, f"Saving to Excel could not be verified: {e}")
    except (ValueError, PermissionError) as e:
        raise HTTPException(400, str(e))


@app.post("/api/run/{run_id}/reject")
def reject(run_id: str, body: Edited):
    _load(run_id)
    try:
        return pipeline.reject(run_id, body.approved_by or "owner", body.reason)
    except ValueError as e:
        raise HTTPException(400, str(e))


class Confirm(BaseModel):
    confirm: str = ""


@app.post("/api/run/{run_id}/delete")
def delete_run(run_id: str, body: Confirm):
    """Delete one invoice test (and its ledger rows). The click in the page must send confirm="DELETE"."""
    _load(run_id)
    if body.confirm != "DELETE":
        raise HTTPException(400, "Deleting needs a confirmation")
    try:
        return pipeline.delete_run(run_id)
    except ledger.LedgerLocked as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.post("/api/reset")
def reset_all(body: Confirm):
    """Delete ALL invoice tests and empty the ledger. The user must type DELETE in the page."""
    if body.confirm != "DELETE":
        raise HTTPException(400, "Type DELETE to confirm")
    try:
        return pipeline.clear_all()
    except ledger.LedgerLocked as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.post("/api/run/{run_id}/save_case")
def save_case(run_id: str, body: Edited):
    _load(run_id)
    return {"case": pipeline.save_as_case(run_id, body.invoice, body.case_name or run_id)}


@app.get("/api/ledger")
def ledger_rows():
    return ledger.read_all()


@app.get("/api/ledger/download")
def ledger_download():
    ledger.read_all()  # creates the file if needed
    return FileResponse(LEDGER_XLSX, filename="ledger.xlsx")


@app.get("/api/stats")
def stats():
    return pipeline.stats()


if __name__ == "__main__":
    uvicorn.run(app, host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "8400")))
