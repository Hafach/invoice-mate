"""PIN lock test: with APP_PIN set, nothing under /api works without logging in.

  python tests/test_pin.py
"""
import os
import sys
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="invoice-agent-pin-"))
os.environ.update(DATA_DIR=str(TMP / "data"), CASES_DIR=str(TMP / "cases"), JETSON_URL="http://127.0.0.1:9",
                  APP_PIN="4821")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402

c = TestClient(server.app, client=("127.0.0.1", 50000))
ok = 0


def check(name, cond):
    global ok
    print(("PASS " if cond else "FAIL ") + name)
    assert cond, name
    ok += 1


check("page itself loads (shows the PIN screen)", c.get("/").status_code == 200)
check("session says PIN required", c.get("/api/session").json() == {"pin_required": True, "logged_in": False})
for method, path in (("get", "/api/ledger"), ("get", "/api/ledger/download"), ("get", "/api/runs"),
                     ("post", "/api/capture"), ("post", "/api/run/x/approve")):
    check(f"{method.upper()} {path} refused without PIN", getattr(c, method)(path).status_code == 401)
check("wrong PIN refused", c.post("/api/login", json={"pin": "0000"}).status_code == 401)
check("right PIN accepted", c.post("/api/login", json={"pin": "4821"}).status_code == 200)
check("after login the ledger opens", c.get("/api/ledger").status_code == 200)
other = TestClient(server.app, client=("127.0.0.1", 50001))
check("another browser without the cookie is still locked", other.get("/api/ledger").status_code == 401)
print(f"\n{ok} checks passed.")
