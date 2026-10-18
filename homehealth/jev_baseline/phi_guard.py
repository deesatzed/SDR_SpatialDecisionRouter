"""PHI pre-send guard for Jev inputs (SYNTHETIC data, but the path is kept). Patterns follow SDR tools/import_cases.py PHI,
with the synthetic-timeline allowance: relative day references ('Day -7', 'Day -7 to -1', 'Days -6 to -1', 'Day 0') are removed
before matching, and the date patterns no longer read a day range as a date. A real hit blocks sending that case."""
import re
MONTHS = r"(jan(uary)?|feb(ruary)?|mar(ch)?|apr(il)?|may|jun(e)?|jul(y)?|aug(ust)?|sep(t(ember)?)?|oct(ober)?|nov(ember)?|dec(ember)?)"
PHI = [
 ("email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")),
 ("url", re.compile(r"https?://|www\.", re.I)),
 ("ip address", re.compile(r"\b\d{1,3}(\.\d{1,3}){3}\b")),
 ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
 ("phone", re.compile(r"(\+?1[\s.-]?)?\(?\b\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b")),
 ("date", re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b|\b\d{1,2}-\d{1,2}-\d{4}\b|\b\d{1,2}\.\d{1,2}\.\d{4}\b|\b(19|20)\d{2}[/.-]\d{1,2}[/.-]\d{1,2}\b")),
 ("date", re.compile(rf"\b{MONTHS}\.?\s+\d{{1,2}}(st|nd|rd|th)?\b|\b\d{{1,2}}(st|nd|rd|th)?\s+(of\s+)?{MONTHS}\b", re.I)),
 ("dob / birth", re.compile(r"\b(dob|d\.o\.b|born|birth\s*date|date of birth)\b", re.I)),
 ("mrn / record number", re.compile(r"\b(mrn|medical record|record\s*(no|number|#)|acct|account\s*(no|number|#)|member\s*id|policy\s*(no|#))\b", re.I)),
 ("long id number", re.compile(r"\b\d{7,}\b")),
 ("street address", re.compile(r"\b\d{1,6}\s+([A-Z][a-z]+\s+){1,3}(st|street|ave|avenue|rd|road|blvd|lane|ln|dr|drive|ct|court|way|pl|place|hwy)\b\.?", re.I)),
 ("zip code", re.compile(r"\b\d{5}-\d{4}\b|\b(zip|postal)\s*(code)?\s*:?\s*\d{3,5}\b", re.I)),
 ("name", re.compile(r"\b(Mr|Mrs|Ms|Miss|Prof|Dr)\.?\s+[A-Z][a-z]+")),   # case-sensitive title (upstream used re.I, which read '29 ms. Sleep' as a name)
 ("name", re.compile(r"\b(name|patient|pt)\s*[:=]\s*[A-Z][a-z]+")),
 ("exact age >89", re.compile(r"\b(9\d|1[0-4]\d)\s*(y/?o|yrs?|years?[\s-]old)\b", re.I)),
]
# synthetic relative-day allowance: 'Day -7', 'Days -6 to -1', 'Day -7 to -4', 'Day -2 14:00 to Day 0 16:00', 'Day -1-0', 'Day 0'
DAY_REF = re.compile(r"\bDays?\s+[-+]?\d{1,4}(\s*(to|-|–|and|through)\s*(Day\s+)?[-+]?\d{1,4})*", re.I)
def strip_allowed(text): return DAY_REF.sub(" DAYREF ", text)
def phi_hits(text):
    t = strip_allowed(text)
    return [(label, m.group(0)) for label, rx in PHI for m in [rx.search(t)] if m]
