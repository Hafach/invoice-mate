"""Network lock: only the Jetson's own Wi-Fi, the owner's Tailscale, the USB cable and localhost may use the app.

  python tests/test_network_lock.py
"""
import os
import sys
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="invoice-agent-lock-"))
os.environ.update(DATA_DIR=str(TMP / "d"), CASES_DIR=str(TMP / "c"), JETSON_URL="http://127.0.0.1:9", APP_PIN="",
                  NETWORK_LOCK="on")  # test the lock itself, whatever the device .env says
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402

ok = 0


def check(name, cond):
    global ok
    print(("PASS " if cond else "FAIL ") + name)
    assert cond, name
    ok += 1


def get(ip, path="/api/session", headers=None):
    return TestClient(server.app, client=(ip, 40000)).get(path, headers=headers or {}).status_code


check("phone on the Jetson's own Wi-Fi (10.42.0.57) is allowed", get("10.42.0.57") == 200)
check("owner's laptop over Tailscale (100.78.122.100) is allowed", get("100.78.122.100") == 200)
check("USB cable (192.168.55.100) is allowed", get("192.168.55.100") == 200)
check("the Jetson itself (127.0.0.1) is allowed", get("127.0.0.1") == 200)
check("someone else on the venue Wi-Fi (10.31.72.50) is blocked", get("10.31.72.50") == 403)
check("a random internet address (8.8.8.8) is blocked", get("8.8.8.8") == 403)
check("the page itself is blocked too, not only the API", get("10.31.72.50", "/") == 403)
check("ledger download is blocked from outside", get("8.8.8.8", "/api/ledger/download") == 403)
check("internet traffic via Tailscale Funnel is blocked even though it arrives from 127.0.0.1",
      get("127.0.0.1", headers={"Tailscale-Funnel-Request": "?1"}) == 403)
print(f"\n{ok} checks passed.")

# public mode: NETWORK_LOCK=off lets everyone in (used with the public Funnel link)
server.NETWORK_LOCK = False
check("NETWORK_LOCK=off: a random internet address is allowed", get("8.8.8.8") == 200)
check("NETWORK_LOCK=off: Funnel (public link) traffic is allowed", get("127.0.0.1", headers={"Tailscale-Funnel-Request": "?1"}) == 200)
server.NETWORK_LOCK = True
print(f"{ok} checks passed (incl. public mode).")
