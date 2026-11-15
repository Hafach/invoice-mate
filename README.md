# Invoice Mate: AlphaHack 2026

> **Current deployment:** everything (camera, local vision model, web app) runs **on the Jetson Orin Nano**. After boot: `bash ~/alphahack/jetson/start_all.sh`, then open `http://<jetson-ip>:8400` and enter the PIN (`APP_PIN` in `.env`). The laptop setup below still works for development.

**Job:** a shop owner or accountant in Lebanon types paper supplier invoices into an Excel ledger by hand, every week.
**Agent:** an invoice goes under the camera, and the agent reads it **on the Jetson** (local vision model, no cloud, no API key), checks it, and prepares the ledger entry and a WhatsApp draft. The owner clicks **Approve**, and only then is anything written to `ledger.xlsx`.

```
[Jetson: camera :8090 + Ollama vision model :11434]
        |  photo                 ^ "read this invoice" (JSON schema only, no tools)
        v                        |
[laptop: server.py] -- code checks: math, VAT, duplicate, new supplier, price jump
        |
web UI http://127.0.0.1:8400 : human edits / approves / rejects
        |  approve only (enforced in code: ledger.commit_invoice)
        v
data/ledger.xlsx   (Invoices, Lines, Suppliers sheets)
```

## Run it

**Jetson** (login `elevai`; the laptop's SSH key is installed):
- First time, on a FAST internet connection (~5 GB, resumes if interrupted):
  `ssh elevai@<jetson-ip> "bash ~/setup_local_ai.sh"`
- After every Jetson boot, run `start_jetson.cmd` on the laptop. It starts the camera and the local AI.

**Laptop:**
```
pip install -r requirements.txt
python server.py              # open http://127.0.0.1:8400
```
`.env` lists the Jetson addresses to try (Wi-Fi, USB cable `192.168.55.1`, Tailscale) and the model (`OLLAMA_MODEL`, default `qwen2.5vl:3b`).

**Tests:**
- `python tests/test_flow.py` runs the whole app with a stand-in AI (21 checks, temp data).
- `python eval/run_eval.py` runs the real model on your saved cases. It prints the pass rate, how many needed a human, silent errors and cost, and adds a line to `eval/results/curve.csv`.

**Building the 20 real cases:** in the UI, read each real invoice, correct the fields to match the paper, then click **Save as test case**.

## Scoring map
| Criterion | Where |
|---|---|
| Whole job, real tool | Writes the shop's Excel ledger (`agent/ledger.py`) and drafts the WhatsApp message to the supplier |
| Works every time | `eval/run_eval.py` on 20 real cases. Flags uncertain reads, so mistakes don't pass silently |
| Human lock | `ledger.commit_invoice` refuses to write without a human approval record. Only the UI's Approve button creates one (typed name + second click to confirm). The AI has no tools |
| Security | The photo never leaves the shop (model runs on the Jetson). Text aimed at the AI on the invoice is reported and ignored. The UI listens on 127.0.0.1 only |
| Cost per run | Electricity only: 25 W × seconds × $/kWh (`agent/config.py`). Shown next to the human cost |
| Count humans | UI header "needed a human edit" and the eval "NEEDED A HUMAN" |

## Known limits (be honest in the pitch)
- A 3B local model is less accurate than big cloud models on Arabic handwriting and crumpled paper. Those invoices get flagged for review.
- About 20–60 s per invoice on the Jetson Orin Nano.
- The Brio 300 has fixed focus. Hold the invoice 30–40 cm away in good light and wait for the sharpness ✓.
