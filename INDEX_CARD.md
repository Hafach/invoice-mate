# AlphaHack 2026: Index card (due Sat 10:00)

> Fill in the [brackets] once you've found the real person.

**Whose job it is**
[Name], [owner / accountant] of [shop type: mini-market / pharmacy / restaurant] in [town], Lebanon.
Every week they type the paper invoices from their suppliers into an Excel sheet by hand: [N] invoices a week, about [6] minutes each.

**What starts the task**
A supplier's paper invoice arrives with a delivery. The owner puts it under the camera (or sends a photo).

**The steps the agent does**
1. Takes the photo (Jetson + camera) and checks it isn't blurry.
2. Reads the invoice with a vision model running **on the Jetson**: supplier, invoice number, date, currency (USD/LBP), every line, VAT, total. Handles Arabic, English and French. No cloud, no API key.
3. Checks it in code: line math, totals, VAT 11%, duplicate invoice (double payment), new supplier, price increase above 15% vs the last invoice.
4. Prepares the ledger rows and, if prices went up, a WhatsApp message to the supplier.
5. **Waits for the owner.** Only after they type their name and click Approve is the invoice written into `ledger.xlsx` (Invoices, Lines and Suppliers sheets). The agent never sends the WhatsApp message itself.

**What "done" looks like**
The invoice is in the shop's Excel ledger with correct numbers and approved by the owner. Duplicates are blocked, and the owner sees any price increases before paying.

**How we prove it**
20 real invoices from [Name]'s shop, plus the judges' 2 cases run live. We report the pass rate, how many needed a human correction, and the cost per invoice (electricity only, under $0.001) vs about $0.40 of staff time.
