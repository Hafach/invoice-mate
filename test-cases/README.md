# 20 test cases run on the real application

Run on **15 Nov 2026, 13:00–14:50**, through the Invoice Mate web app, **entirely on the Jetson Orin Nano** (local model `qwen2.5vl:3b`, no cloud). Testers uploaded or photographed each invoice, read the agent's result and checks, then pressed **Approve**. The Approve button refuses a blocked case.

## Results

| | |
|---|---|
| Cases | **20**: Arabic, French and English, in USD, LBP and EUR. Real invoices, plus synthetic invoices built purely to test agent functions (planted errors, missing fields, duplicates), and a phone-camera photo |
| Handled as intended | **20 / 20** |
| Planted errors caught | **7 / 7**: wrong line amount ×3, wrong VAT ×2, missing date, missing invoice number |
| Duplicates prevented | **2 / 2**: cases 12 and 15 were **blocked**. The server refused Approve (HTTP 400), so nothing was written to the ledger and no double payment is possible |
| Agent status | 5 `ready`, 13 `needs_review` (a check flagged something, a human looked), 2 `blocked` |
| Silent errors | **0**: no wrong invoice reached the ledger without a warning |
| Human edits | 2 cases had one field corrected by hand (11, 14) |
| Time per invoice | 44 s on average (30–97 s) on the Jetson |
| Cost | $0.0025 of electricity for all 20 (about $0.0001 per invoice), vs about $0.40 of human time per invoice |

Final ledger after the session: [`ledger.xlsx`](ledger.xlsx): 18 invoices, 53 item lines, 12 suppliers. That is the 20 cases minus the 2 blocked duplicates.
Event log of every read and approval: [`runs.jsonl`](runs.jsonl).

## The duplicate test (rejected on purpose)

- **Case 10**: a paper invoice `TEST-LBP-001` photographed with a phone is approved into the ledger.
- **Case 12**: the **same invoice** is sent again as a PDF. The agent finds the same supplier and invoice number already in the ledger and sets the status to **`blocked`**:
  > *Same supplier and invoice number as Demo Supply Company (fictional) #TEST-LBP-001 (2026-11-14, already in the ledger, 2026-11-15 13:46). Possible double payment.*
- **Case 15**: same test with a real invoice. Case 01's Axon PDF comes back as a JPEG photo and is also blocked.

The block is enforced in code (`agent/checks.py`, `agent/pipeline.py`), not left to the AI.

## Every case

Each folder holds the **original file** sent to the app, the **image(s) the AI read**, and `run.json`: the full record of what the model extracted, every check, the final values, the approver and the token count, time and cost.

| # | File sent | What it tests | Agent status | What the agent did | Human decision | Time |
|---|---|---|---|---|---|---|
| [01](01-real-axon-2-pages/) | real invoice repeated on 2 pages same.pdf | Real invoice (English, USD), same page repeated twice in a 2-page PDF | `needs_review` | Flagged for review: no date found, line math does not add up | Approved | 65.9 s |
| [02](02-arabic-usd/) | Arabic USD Invoice.pdf | Arabic invoice, USD | `ready` | Read cleanly, all checks passed | Approved | 35.3 s |
| [03](03-french-usd-wrong-line/) | French USD Invoice Wrong Line Amount.pdf | French invoice with a wrong line amount (planted error) | `needs_review` | Caught: 10 x 3.2 = 32, invoice says 37 | Approved | 34.4 s |
| [04](04-french-usd/) | French invoice usd.pdf | French invoice, USD | `needs_review` | Warned that it looks like the same template as case 03, human checked and approved | Approved | 34.5 s |
| [05](05-arabic-usd-discount/) | Arabic USD Invoice With Discount.pdf | Arabic invoice with a discount | `needs_review` | Flagged: subtotal - discount + VAT does not match the total, human checked | Approved | 37.9 s |
| [06](06-arabic-usd-wrong-line/) | Arabic USD Invoice Wrong Line Amount.pdf | Arabic invoice with a wrong line amount (planted error) | `needs_review` | Caught: lines add up to 108, invoice says 113 | Approved | 95.3 s |
| [07](07-english-wrong-tax/) | Invoice english Wrong Tax Amount.pdf | English invoice with a wrong VAT amount (planted error) | `needs_review` | Caught: VAT 15 is not 10% of 100 | Approved | 31.9 s |
| [08](08-english-wrong-line/) | Invoice english Wrong Line Item Amount.pdf | English invoice with a wrong line amount (planted error) | `needs_review` | Caught: 3 x 10 = 30, invoice says 35 | Approved | 30.8 s |
| [09](09-real-fedex-discount/) | Real FedEx Invoice english With Discount.pdf | Real FedEx invoice with a discount | `needs_review` | Flagged: discount math does not match the total | Approved | 49.7 s |
| [10](10-phone-camera-lbp/) | phone-camera.jpg | Paper invoice photographed with a phone camera, LBP | `ready` | Read cleanly, all checks passed (LBP shown with USD equivalent) | Approved | 35.3 s |
| [11](11-real-french-eur/) | real french invoice eur.pdf | Real French invoice, EUR | `ready` | All checks passed. The human corrected 1 field before approving | Approved (1 edit) | 34.4 s |
| [12](12-DUPLICATE-english-lbp/) | English LBP Invoice.pdf | The same invoice as case 10 sent again as a PDF (duplicate test) | `blocked` | BLOCKED: same supplier and invoice number already in the ledger. Approve was refused (HTTP 400), nothing written | **Blocked: cannot be approved** | 39.1 s |
| [13](13-english-missing-date/) | English Missing Invoice Date.pdf | English invoice with no invoice date | `needs_review` | Caught: date not found | Approved | 30.5 s |
| [14](14-real-terracon-usd/) | real terracon english invoice usd currency.pdf | Real Terracon invoice, USD | `needs_review` | Flagged: lines do not add up to the total. The human corrected 1 field before approving | Approved (1 edit) | 31.1 s |
| [15](15-DUPLICATE-real-axon-photo/) | real invoice english usd currency phoenix.jpeg | Case 01's invoice again, as a JPEG photo (duplicate test) | `blocked` | BLOCKED: same supplier and invoice number already in the ledger. Approve was refused (HTTP 400), nothing written | **Blocked: cannot be approved** | 42.3 s |
| [16](16-real-shi-usd/) | real shi invoice english usd  .pdf | Real SHI invoice, USD | `ready` | Read cleanly, all checks passed | Approved | 43.4 s |
| [17](17-arabic-lbp/) | arabic invoice and lbp currency.pdf | Arabic invoice, LBP (large amounts) | `needs_review` | Flagged: several math checks failed (3B model misread Arabic figures), human checked | Approved | 97.1 s |
| [18](18-english-lbp/) | english invoice and lbp currency.pdf | English invoice, LBP (same layout as case 17) | `ready` | Read cleanly, all checks passed | Approved | 41.2 s |
| [19](19-english-missing-number/) | English_Missing_Invoice_Number.pdf | English invoice with no invoice number | `needs_review` | Caught: invoice number not found | Approved | 30.2 s |
| [20](20-arabic-usd-wrong-tax/) | Arabic USD Invoice Wrong Tax Amount.pdf | Arabic invoice with a wrong VAT amount (planted error) | `needs_review` | Caught: VAT 15 is not 10% of 93, and the total does not add up | Approved | 35.3 s |

`needs_review` means at least one check fired and a person had to look before approving. On the real invoices (01, 09, 14) and the Arabic LBP invoice (17), the math warnings come from the small 3B model misreading some figures. That is the intended behaviour: the agent says it is unsure instead of writing a wrong number silently.
