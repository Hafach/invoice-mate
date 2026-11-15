"""Run the agent on every test case and score it (Twists 02/03/05/07).

A case = eval/cases/<name>.jpg|png  +  eval/cases/<name>.expected.json (the truth).
Build cases from the web UI: read an invoice, correct the fields, "Save as test case".

  python eval/run_eval.py            # all cases
  python eval/run_eval.py shop-01    # one case

The ledger is NOT touched (checks run against the current ledger read-only).
A case PASSES when supplier, invoice no., date, currency, total and every line total match.
"Needed a human" = case did not pass untouched OR the agent itself flagged it for review.
"""
import json
import sys
import time
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from agent.checks import run_checks  # noqa: E402
from agent.config import CASES, HUMAN_HOURLY_USD, HUMAN_MINUTES_PER_INVOICE  # noqa: E402
from agent.extract import extract_invoice  # noqa: E402
from agent.ledger import norm  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"
MT = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def num_eq(a, b):
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= max(0.011, 0.001 * abs(float(b)))


CURRENCY_ALIASES = {"rm": "myr", "": "usd", "ll": "lbp", "lbp": "lbp", "usd": "usd", "myr": "myr"}


def cur(v):
    n = norm(v)
    return CURRENCY_ALIASES.get(n, n) if v != "$" else "usd"


def compare(got, exp):
    """Score only the fields the truth file contains (some datasets label only supplier/date/total)."""
    errs = []
    if exp.get("is_invoice") is False:
        return [] if got.get("is_invoice") is False else ["should be rejected as not-an-invoice"]
    if not got.get("is_invoice", True):
        errs.append("wrongly rejected as not-an-invoice")
    if "supplier_name" in exp and SequenceMatcher(
            None, norm(got.get("supplier_name")), norm(exp.get("supplier_name"))).ratio() < 0.8:
        errs.append(f"supplier {got.get('supplier_name')!r} != {exp.get('supplier_name')!r}")
    for k in ("invoice_number", "invoice_date"):
        if k in exp and norm(got.get(k)) != norm(exp.get(k)):
            errs.append(f"{k} {got.get(k)!r} != {exp.get(k)!r}")
    if "currency" in exp and cur(got.get("currency")) != cur(exp.get("currency")):
        errs.append(f"currency {got.get('currency')!r} != {exp.get('currency')!r}")
    if "total" in exp and not num_eq(got.get("total"), exp.get("total")):
        errs.append(f"total {got.get('total')} != {exp.get('total')}")
    if "lines" not in exp:
        return errs
    gl, el = got.get("lines") or [], exp.get("lines") or []
    if len(gl) != len(el):
        errs.append(f"{len(gl)} lines != {len(el)}")
    else:
        bad = [i + 1 for i, (g, e) in enumerate(zip(gl, el)) if not num_eq(g.get("line_total"), e.get("line_total"))]
        if bad:
            errs.append(f"line totals wrong on lines {bad}")
    return errs


def main(only=None):
    cases = sorted(p for p in CASES.iterdir() if p.suffix.lower() in MT and (only is None or p.stem in only))
    if not cases:
        print(f"No cases in {CASES}. Save some from the web UI first.")
        return
    rows, cost, secs = [], 0.0, 0.0
    for img in cases:
        exp_path = CASES / f"{img.stem}.expected.json"
        if not exp_path.exists():
            print(f"skip {img.name}: no expected.json")
            continue
        exp = json.loads(exp_path.read_text(encoding="utf-8"))
        t0 = time.time()
        try:
            out = extract_invoice(img.read_bytes(), MT[img.suffix.lower()])
            got, usage = out["invoice"], out["usage"]
            errs = compare(got, exp)
            status = run_checks(got)["status"]
        except Exception as e:  # noqa: BLE001
            got, usage, errs, status = {}, {"cost_usd": 0, "seconds": round(time.time() - t0, 1)}, [f"ERROR {e}"], "failed"
        ok = not errs
        flagged = status != "ready"
        # Safe = correct, OR wrong but the agent flagged it for a human (no silent error).
        safe = ok or flagged
        rows.append({"case": img.stem, "pass": ok, "agent_status": status, "human_needed": (not ok) or flagged,
                     "silent_error": (not ok) and not flagged, "errors": errs, "cost_usd": usage["cost_usd"],
                     "seconds": usage["seconds"], "got": got})
        cost += usage["cost_usd"]
        secs += usage["seconds"]
        mark = "PASS" if ok else "FAIL"
        print(f"{mark}  {img.stem:<22} agent:{status:<13} ${usage['cost_usd']:.4f} {usage['seconds']:>5}s  "
              + ("" if ok else "; ".join(errs)) + ("" if safe else "   <-- SILENT ERROR"))
    n = len(rows)
    passed = sum(r["pass"] for r in rows)
    human = sum(r["human_needed"] for r in rows)
    silent = sum(r["silent_error"] for r in rows)
    human_cost = HUMAN_MINUTES_PER_INVOICE / 60 * HUMAN_HOURLY_USD
    summary = {"when": datetime.now().isoformat(timespec="seconds"), "cases": n, "passed": passed,
               "pass_rate": round(passed / n, 3), "needed_human": human, "silent_errors": silent,
               "avg_cost_usd": round(cost / n, 4), "avg_seconds": round(secs / n, 1),
               "human_cost_usd": round(human_cost, 3)}
    print("\n" + "=" * 60)
    print(f"PASS RATE      {passed}/{n}  ({100 * passed / n:.0f}%)")
    print(f"NEEDED A HUMAN {human}/{n}   silent errors (wrong AND not flagged): {silent}")
    print(f"COST PER RUN   AI ${cost / n:.4f}  vs  human ${human_cost:.2f} ({HUMAN_MINUTES_PER_INVOICE:g} min)")
    print(f"TIME PER RUN   {secs / n:.1f}s")
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"eval-{datetime.now():%Y%m%d-%H%M%S}.json"
    out.write_text(json.dumps({"summary": summary, "cases": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    with (RESULTS / "curve.csv").open("a", encoding="utf-8") as fh:  # Twist 05: the pass-rate curve
        fh.write(f"{summary['when']},{n},{passed},{human},{silent},{summary['avg_cost_usd']}\n")
    print(f"saved {out.relative_to(RESULTS.parent.parent)}")


if __name__ == "__main__":
    main(set(sys.argv[1:]) or None)
