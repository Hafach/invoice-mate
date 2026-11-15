# 20 real invoices for testing the demo

Real scanned invoices from public research datasets. Each has `inv-XX.jpg` (the photo) and `inv-XX.expected.json` (the correct answer).

**These are not the 20 real cases for judging.** Those must come from the Lebanese shop owner. Use these to test and demo the agent before then.

| File | Supplier | Date | Total | Source |
|---|---|---|---|---|
| inv-01 | MR D.I.Y. (JOHOR) SDN BHD | 2019-01-12 | MYR 33.90 | SROIE X00016469620 |
| inv-02 | YONGFATT ENTERPRISE | 2018-12-25 | MYR 80.90 | SROIE X00016469622 |
| inv-03 | SAM SAM TRADING CO | 2017-12-29 | MYR 14.10 | SROIE X51005255805 |
| inv-04 | AIK HUAT HARDWARE ENTERPRISE (SETIA ALAM) SDN BHD | 2017-06-15 | MYR 15.00 | SROIE X51005268200 |
| inv-05 | ASIA MART | 2017-12-22 | MYR 32.70 | SROIE X51005268472 |
| inv-06 | LIGHTROOM GALLERY SDN BHD | 2017-12-20 | MYR 73.00 | SROIE X51005301661 |
| inv-07 | TEO HENG STATIONERY & BOOKS | 2018-01-18 | MYR 4.90 | SROIE X51005361883 |
| inv-08 | FUYI MINI MARKET | 2018-01-25 | MYR 9.00 | SROIE X51005361895 |
| inv-09 | C W KHOO HARDWARE SDN BHD | 2018-03-01 | MYR 21.20 | SROIE X51005365179 |
| inv-10 | BENS INDEPENDENT GROCER SDN. BHD | 2018-03-12 | MYR 77.20 | SROIE X51005444033 |
| inv-11 | PASARAYA BORONG PINTAR SDN BHD | 2018-03-14 | MYR 8.20 | SROIE X51005447840 |
| inv-12 | LIAN HING STATIONERY SDN BHD | 2018-03-27 | MYR 79.50 | SROIE X51005453729 |
| inv-13 | MR.D.I.Y(M)SDN BHD | 2017-09-19 | MYR 15.90 | SROIE X51005568880 |
| inv-14 | HON HWA HARDWARE TRADING | 2017-09-21 | MYR 10.40 | SROIE X51005568881 |
| inv-15 | MR. D.I.Y. SDN BHD | 2017-11-24 | MYR 3.90 | SROIE X51005568884 |
| inv-16 | VIVOPAC MARKETING SDN BHD | 2017-05-30 | MYR 18.80 | SROIE X51005568898 |
| inv-17 | MR. D.I.Y. (KUCHAI) SDN BHD | 2017-03-08 | MYR 37.80 | SROIE X51005568911 |
| inv-18 | FY EAGLE ENTERPRISE | 2017-12-04 | MYR 7.00 | SROIE X51005577192 |
| inv-19 | Healthy Buildings International, Inc. | 1991-08-08 | USD 5910.00 | RVL-CDIP |
| inv-20 | Hazleton Laboratories America, Inc. | 1984-03-19 | USD 1950.00 | RVL-CDIP |

**Sources and licenses**
- inv-01…18: [ICDAR 2019 SROIE](https://rrc.cvc.uab.es/?ch=13) via Hugging Face `jsdnrs/ICDAR2019-SROIE`. Real Malaysian tax invoices from hardware, stationery, wholesale and grocery suppliers (2017–2018, MYR, GST 6%). The answer files have only supplier, date and total, because that is all SROIE labels. For research and testing use.
- inv-19…20: [RVL-CDIP](https://adamharley.com/rvl-cdip/) invoice class via `jordyvl/rvl_cdip_100_examples_per_class`. Real US supplier invoices (1984, 1991), from the public Legacy Tobacco Documents archive. Answers read by hand.

Run the eval on them:
```
set CASES_DIR=invoices
python eval/run_eval.py
```
