import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA = Path(os.environ.get("DATA_DIR", ROOT / "data"))
PENDING = DATA / "pending"
IMAGES = DATA / "images"
LEDGER_XLSX = Path(os.environ.get("LEDGER_XLSX", DATA / "ledger.xlsx"))
RUNS_LOG = DATA / "runs.jsonl"
CASES = Path(os.environ.get("CASES_DIR", ROOT / "eval" / "cases"))
for d in (DATA, PENDING, IMAGES, CASES):
    d.mkdir(parents=True, exist_ok=True)

# Tried in order; the first one that answers is used (USB cable, Wi-Fi, Tailscale).
JETSON_URLS = [u.strip().rstrip("/") for u in os.environ.get(
    "JETSON_URL", "http://192.168.55.1:8090,http://elevai.local:8090,http://100.80.250.116:8090").split(",") if u.strip()]
JETSON_URL = JETSON_URLS[0]
# Local vision model served by Ollama on the Jetson (no cloud, no key)
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5vl:3b")
OLLAMA_URLS = [u.replace(":8090", ":11434") for u in JETSON_URLS]
NUM_PREDICT = int(os.environ.get("NUM_PREDICT", "1100"))  # rich invoices with many lines/fields need ~700-900
MAX_IMAGE_SIDE = int(os.environ.get("MAX_IMAGE_SIDE", "1024"))  # 1280 ran out of GPU memory on the Orin Nano
MAX_IMAGE_PIXELS = int(os.environ.get("MAX_IMAGE_PIXELS", "720000"))  # 940k crashed, 800k worked: keep a margin

# Cost of one run = electricity only: Jetson power x seconds x price per kWh
JETSON_WATTS = float(os.environ.get("JETSON_WATTS", "25"))
KWH_USD = float(os.environ.get("KWH_USD", "0.40"))  # generator subscription rate in Lebanon, edit if needed

# What the same job costs a human (edit to match the real interview)
HUMAN_MINUTES_PER_INVOICE = float(os.environ.get("HUMAN_MINUTES_PER_INVOICE", "6"))
HUMAN_HOURLY_USD = float(os.environ.get("HUMAN_HOURLY_USD", "4"))

VAT_RATE = float(os.environ.get("VAT_RATE", "0.11"))  # Lebanon standard VAT

# Lebanese pound: market/official dollar rate since 2023 (edit if it changes) and plausibility limits
USD_LBP_RATE = float(os.environ.get("USD_LBP_RATE", "89500"))
RATE_TOLERANCE = float(os.environ.get("RATE_TOLERANCE", "0.10"))   # +-10% around USD_LBP_RATE
LBP_GUESS_MIN = float(os.environ.get("LBP_GUESS_MIN", "50000"))    # no currency printed & total >= this -> LBP
USD_MAX_PLAUSIBLE = float(os.environ.get("USD_MAX_PLAUSIBLE", "100000"))  # a shop's USD invoice above this is odd
LBP_MIN_PLAUSIBLE = float(os.environ.get("LBP_MIN_PLAUSIBLE", "1000"))    # an LBP total below this is odd
PRICE_JUMP_PCT = float(os.environ.get("PRICE_JUMP_PCT", "15"))
