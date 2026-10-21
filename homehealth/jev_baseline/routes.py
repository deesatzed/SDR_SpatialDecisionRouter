"""Route ids, display labels and definitions (SMART_TRIGGERS v1.9 section 0; Wayne 2026-10-21). SYNTHETIC pipeline, stdlib only.

v1.9 renamed two routes. New writes use the canonical ids; readers map legacy ids on read so stored model outputs,
library/holdout labels and old scores still parse:  wake_specialist -> provider_task, escalate_human -> urgent_page.
"""
ROUTES = ["silent_log", "nurse_task", "provider_task", "urgent_page"]   # lowest -> highest
RANK = {r: i for i, r in enumerate(ROUTES)}
LABELS = {"silent_log": "silent", "nurse_task": "nurse task", "provider_task": "provider task", "urgent_page": "urgent page"}
DEFINITIONS = {
    "silent_log": "Log only; no human action needed",
    "nurse_task": "Nurse contact within about 24 h (or a same-shift hospice nurse contact under hospice/comfort goals)",
    "provider_task": "Review by the clinician responsible for that condition or medication on the same business day; not a page",
    "urgent_page": "Page someone now (a clinician; for an urgent comfort problem under hospice goals, the hospice nurse)",
}
LEGACY_ALIAS = {"wake_specialist": "provider_task", "escalate_human": "urgent_page"}
LEGACY_IDS = {v: k for k, v in LEGACY_ALIAS.items()}   # canonical -> v1.8 id (for reproducing the v1.8 prompt only)

def canon(r):
    """Map a legacy route id to its v1.9 id; anything else (including None and alternate tokens) passes through."""
    return LEGACY_ALIAS.get(r, r) if isinstance(r, str) else r

def label(r):
    r = canon(r); return LABELS.get(r, r)

def canon_probs(p):
    """Probability dict keyed by route -> keyed by v1.9 ids (legacy and new keys for one route are summed)."""
    if not isinstance(p, dict): return p
    out = {}
    for k, v in p.items():
        k2 = canon(k)
        out[k2] = (out[k2] + (v or 0)) if k2 in out else v
    return out

def canon_row(row):
    """A stored Jev checkpoint row (pick, probs) with v1.9 route ids. Returns a new dict."""
    r = dict(row)
    if "pick" in r: r["pick"] = canon(r["pick"])
    if "probs" in r: r["probs"] = canon_probs(r["probs"])
    return r
