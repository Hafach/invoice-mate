"""Text normalization for matching in Arabic, French and English.

Used by duplicate detection, supplier matching, price history and the injection check, so that
"شركة أبو خليل" / "شركه ابو خليل", "Établissements Nasr" / "ETABLISSEMENTS NASR",
"Facture N° 00123" / "123" and "رقم ٠٠١٢٣" / "123" compare as equal.
"""
import re
import unicodedata

DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
ARABIC_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")  # harakat + tatweel
ARABIC_LETTERS = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي", "ئ": "ي", "ؤ": "و",
                                "ڤ": "ف", "پ": "ب", "گ": "ك", "ک": "ك", "ی": "ي"})


def fold(s) -> str:
    """Lowercase, remove French accents and Arabic diacritics, unify Arabic letter variants and digits.
    Keeps spaces and punctuation (for word-based matching)."""
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", str(s)).translate(DIGITS)
    s = ARABIC_DIACRITICS.sub("", s).translate(ARABIC_LETTERS)
    # strip Latin accents: é->e, ç->c, à->a ... (Arabic letters have no combining marks left at this point)
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    s = s.replace("œ", "oe").replace("æ", "ae").replace("ß", "ss")
    return s.lower()


def key(s) -> str:
    """fold() and drop everything that is not a letter or digit."""
    return re.sub(r"[\W_]+", "", fold(s))


# Legal forms / generic company words in EN, FR, AR that suppliers print inconsistently
LEGAL_WORDS = {
    "sarl", "sal", "sa", "sas", "sasu", "eurl", "snc", "ltd", "llc", "inc", "co", "corp", "company", "cie",
    "et", "ets", "etablissement", "etablissements", "societe", "ste", "group", "groupe", "holding",
    "sdn", "bhd", "plc", "gmbh",
    "شركه", "شركة", "مؤسسه", "مؤسسة", "مؤسسات", "شمل", "شمم", "ش", "م", "ل", "لتجاره", "للتجاره",
}


def supplier_key(name) -> str:
    """Supplier name without legal forms / punctuation: 'S.A.R.L. Abou Khalil Trading' == 'abou khalil trading sarl'."""
    t = fold(name)
    t = re.sub(r"\b([a-z])\.(?=[a-z]\.)", r"\1", t)          # s.a.r.l -> sarl
    t = re.sub(r"(?<=\b[a-z])\.(?=\s|$)", "", t)
    t = t.replace(".", "")
    words = [w for w in re.split(r"[\W_]+", t) if w and w not in LEGAL_WORDS]
    return "".join(words)


INVOICE_LABELS = re.compile(
    r"^(invoice|inv|bill|receipt|no|nr|num|number|ref|facture|fact|fac|fa|n|numero|recu|"
    r"رقم|فاتوره|فاتورة|ف|ايصال|وصل)+", re.IGNORECASE)


GLUED_LABEL = re.compile(r"^(invoice|inv|facture|fact|no|nr|num|ref)(?=[0-9])")


def invoice_no_key(s) -> str:
    """'Facture N° 00123' / 'INV-00123' / 'رقم ٠٠١٢٣' / '123' -> '123'. Keeps letters inside real numbers (CS02070163)."""
    parts = [p for p in re.split(r"[\W_]+", fold(s)) if p]
    while parts and INVOICE_LABELS.fullmatch(parts[0]):        # leading label words: "Facture", "N", "رقم"
        parts.pop(0)
    if parts:
        parts[0] = GLUED_LABEL.sub("", parts[0])                 # "inv2026" -> "2026" (but "ND7781" stays)

    def strip_zeros(p):  # "0418" -> "418", "CS02070163" -> "cs2070163"
        return "".join(r.lstrip("0") or "0" if r.isdigit() else r for r in re.findall(r"[0-9]+|[^0-9]+", p))

    out = ""
    for p in map(strip_zeros, parts):
        # keep a separator only between two numbers ("2026-418" != "2026-41-8"); "A-1001" == "A1001"
        out += ("-" if out and out[-1].isdigit() and p[0].isdigit() else "") + p
    return out.lstrip("0-") or out  # "000A-1001" -> "a1001"


# Currency as printed -> ISO code. Matched on fold()ed text (Arabic letters unified, accents removed).
CURRENCY_WORDS = [
    ("LBP", ["lbp", "ll", "l.l", "l l", "l.l.", "lp", "l.p", "£l", "ل.ل", "ل ل", "لل", "ل.ل.", "ليره", "ليرات",
             "ليره لبنانيه", "الليره اللبنانيه", "livre", "livres", "livre libanaise", "livres libanaises",
             "lebanese pound", "lebanese pounds", "lira", "leb pound"]),
    ("USD", ["usd", "$", "us$", "$us", "us dollar", "us dollars", "dollar", "dollars", "dollar us", "dollars us",
             "دولار", "دولار امريكي", "الدولار", "د.ا", "fresh usd", "fresh $"]),
    ("EUR", ["eur", "€", "euro", "euros", "يورو"]),
    ("MYR", ["myr", "rm", "ringgit"]),
]
_CURRENCY = {fold(w): code for code, words in CURRENCY_WORDS for w in words}
OTHER_ISO = {"GBP", "SAR", "AED", "QAR", "KWD", "JOD", "EGP", "SYP", "TRY", "CHF", "CAD", "AUD", "CNY", "IQD", "OMR",
             "BHD", "JPY", "INR", "XAF", "XOF"}


def currency_code(s):
    """'ل.ل' / 'L.L.' / 'Livres libanaises' / 'LBP' -> 'LBP';  '$' / 'دولار' -> 'USD';  unknown -> None."""
    if not s:
        return None
    t = fold(s).strip()
    if t in _CURRENCY:
        return _CURRENCY[t]
    compact = re.sub(r"\s+", " ", t.replace("’", "'")).strip(" .:")
    if compact in _CURRENCY:
        return _CURRENCY[compact]
    if compact.upper() in OTHER_ISO:
        return compact.upper()
    for w, code in sorted(_CURRENCY.items(), key=lambda kv: -len(kv[0])):  # "Total en L.L." / "المجموع بالليرة"
        if len(w) >= 3 and w in compact:
            return code
    return None


COUNTRY_CODES =("961", "60", "33", "1")  # Lebanon first; Malaysia/France/US for the test sets


def phone_key(s) -> str:
    """'+961 3 987 654' == '03/987654' == '٠٣ ٩٨٧٦٥٤' == '00961 3987654'  -> '3987654'."""
    d = re.sub(r"\D", "", str(s or "").translate(DIGITS))
    if d.startswith("00"):
        d = d[2:]
    for cc in COUNTRY_CODES:
        if d.startswith(cc) and len(d) - len(cc) >= 7:
            d = d[len(cc):]
            break
    d = d.lstrip("0")
    return d[-7:] if len(d) >= 6 else ""
