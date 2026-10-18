"""Jev baseline (Layer 2): OpenRouter decision models over the 270-case library x 4 variants. SYNTHETIC DATA ONLY.
- Endpoint POST https://openrouter.ai/api/v1/systemone; questions: route (choice) + veto (noul).
- Model-visible input = POLICY (SMART_TRIGGERS v1.7 summary, no case facts) + the runner `lines` only. Label fields are never sent;
  a leak check on every outgoing state blocks route/rule/tier tokens.
- PHI pre-send guard (phi_guard.py): a real hit blocks that case; counts are written to results/phi_report.json.
- 600 s per-call timeout; backoff on 429/5xx; per-model checkpoint (results/parsed/<model>.jsonl, resume skips done keys).
- Spend = sum of usage.cost in the checkpoints; hard cap SPEND_CAP (default $0.50) checked before every call -> stop.
- Stored per call: parsed pick/probabilities/confidence/veto, token counts, cost, latency, error code. No raw responses.
Never prints the key. Usage: python3 jev_run.py [model ...]"""
import json, os, re, sys, time, threading, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from phi_guard import phi_hits
_HERE = os.path.dirname(os.path.abspath(__file__))
_BOX = "/workspace/jevfly_smoke/library_v2/smart_triggers"
def find_input(env, name):
    """env var, else the SDR repo layout (homehealth/library next to homehealth/jev_baseline), else the box pipeline folder."""
    for p in (os.environ.get(env), os.path.join(_HERE, "..", "library", name), os.path.join(_BOX, name)):
        if p and os.path.exists(p): return p
    raise SystemExit(f"{name} not found: set {env} (the runner JSON is written by casegen/convert_casegen.py via build_outputs.py)")
OUT = os.path.join(HERE, "results"); PARSED = os.path.join(OUT, "parsed")
DEFAULT_MODELS = ["typesafe/jev-1.14", "liquid/d1-ultra", "openai/gpt-6-luna-decisions", "cloudflare/clef"]
SPEND_CAP = float(os.environ.get("SPEND_CAP", "0.50")); PRIOR_SPEND = float(os.environ.get("PRIOR_SPEND", "0"))
TIMEOUT = 600; WORKERS_PER_MODEL = int(os.environ.get("WORKERS", "4"))
ROUTES = {"silent_log": "Log only; no human action needed",
          "nurse_task": "Nurse contact within about 24 h (or a same-shift hospice nurse contact under hospice/comfort goals)",
          "wake_specialist": "Same-day clinician review",
          "escalate_human": "A clinician (or, for an urgent comfort problem under hospice goals, the hospice nurse) must act now"}
POLICY = ("Elder-care home wearable triage (synthetic case). Judge every reading against the person's own baseline, not population cutoffs. "
 "Hard triggers (syncope; new focal neurological deficit; chest pain with ECG change or abnormal vitals; resting SpO2 below 88%; "
 "a fall on an anticoagulant; a 48 h data gap in a high-risk patient) go to a human now only if they pass four checks: "
 "(1) the reading is reliable (no motion/poor-contact flag; a fingertip check or a visit confirms); "
 "(2) it is a change from the person's own baseline; (3) nothing explains it (a timed contact or charger log inside a gap, a dropped watch); "
 "(4) it fits the goals of care. Hospice or comfort-only goals suppress hospital-directed escalation (same-shift hospice nurse), "
 "but an urgent, home-treatable comfort problem (a symptomatic danger-level low glucose, distressing breathlessness treatable at home) needs the hospice nurse now. "
 "A trigger that fails a check is not paged but still gets the route its clinical picture needs; an acute decompensation needs a human now even without a trigger. "
 "Device values that are physiologically implausible are device problems. An unanswered prompt in someone who lives alone counts as a failed confirmation. "
 "Missing critical data in a high-risk person needs a human.")
LEAK = re.compile(r"escalate_human|wake_specialist|nurse_task|silent_log|\bHT_[A-Z]|CONFIRM_FIRST|ABSOLUTE|SUPPRESSED|LOG_ONLY|goals_of_care|at_patient_baseline|unreliable_reading|below_band|already_confirmed|expected_route|acceptable_alternates")
LOCK = threading.Lock(); STOP = threading.Event()
def slug(m): return re.sub(r"[^A-Za-z0-9._-]+", "_", m)
def log(msg):
    line = time.strftime("%H:%M:%S ") + msg
    with LOCK:
        print(line, flush=True); open(os.path.join(OUT, "run.log"), "a").write(line + "\n")
def load_ck(m):
    p = os.path.join(PARSED, slug(m) + ".jsonl"); rows = {}
    if os.path.exists(p):
        for l in open(p):
            if l.strip(): r = json.loads(l); rows[(r["case"], r["variant"])] = r
    return rows
def spend():
    s = 0.0
    for f in os.listdir(PARSED):
        if f.endswith(".jsonl"):
            for l in open(os.path.join(PARSED, f)):
                if l.strip(): s += json.loads(l).get("cost") or 0
    return s + PRIOR_SPEND
def variants(c):
    L = c["lines"]; fwd = list(ROUTES); rev = fwd[::-1]
    v = {"base": ("\n".join(L), fwd), "reversed": ("\n".join(L), rev),
         "missing_all": (L[0] + "\nNo wearable data, meds or caregiver note available.", fwd)}
    if c.get("key_line") is not None: v["key_deleted"] = ("\n".join(l for i, l in enumerate(L) if i != c["key_line"]), fwd)
    return v
def body(model, state, order):
    return {"model": model, "state": POLICY + "\n\n" + state,
            "questions": {"route": {"type": "choice", "instructions": "Which route should this case take?", "criteria": {k: ROUTES[k] for k in order}},
                          "veto": {"type": "noul", "instructions": "Is there a danger sign or missing critical data that requires a human now?",
                                   "true": "Human must review now", "false": "No human needed now"}}}
def post(b, key):
    req = urllib.request.Request("https://openrouter.ai/api/v1/systemone", json.dumps(b).encode(),
                                 {"Authorization": "Bearer " + key, "Content-Type": "application/json", "X-Title": "jev_baseline"})
    return json.load(urllib.request.urlopen(req, timeout=TIMEOUT))
def call(model, state, order, key):
    if LEAK.search(state): raise RuntimeError("label leak in model-visible state")
    t0 = time.time(); err = None; r = {}
    for attempt in range(1, 7):
        try: r = post(body(model, state, order), key); err = None; break
        except urllib.error.HTTPError as e:
            err = f"HTTP {e.code}"
            if e.code in (429, 500, 502, 503, 504) and attempt < 6: time.sleep(min(60, 2 ** attempt)); continue
            break
        except Exception as e:
            err = type(e).__name__
            if attempt < 6: time.sleep(min(60, 2 ** attempt)); continue
    a = r.get("answers") or {}; u = r.get("usage") or {}; ro = a.get("route") or {}
    return dict(served=r.get("model"), pick=ro.get("choice"), probs=ro.get("probabilities"), conf=ro.get("confidence"),
                veto=(a.get("veto") or {}).get("noul"), input_tokens=u.get("input_tokens"), output_tokens=u.get("output_tokens"),
                cost=u.get("cost") or 0, latency_s=round(time.time() - t0, 3), attempts=attempt, error=err)
def run_model(model, cases, key):
    done = load_ck(model); p = os.path.join(PARSED, slug(model) + ".jsonl")
    todo = [(c, v, s, o) for c in cases for v, (s, o) in variants(c).items() if not (done.get((c["id"], v)) and done[(c["id"], v)].get("pick"))]
    log(f"{model}: {len(done)} in checkpoint, {len(todo)} to run")
    def one(item):
        c, v, s, o = item
        if STOP.is_set(): return
        with LOCK:
            sp = spend()
            if sp >= SPEND_CAP - 0.002: STOP.set(); log(f"SPEND CAP reached before {model} {c['id']} {v}: ${sp:.4f} >= cap ${SPEND_CAP:.2f}"); return
        res = call(model, s, o, key); res.update(model=model, case=c["id"], variant=v, ts=time.strftime("%Y-%m-%dT%H:%M:%S"))
        with LOCK: open(p, "a").write(json.dumps(res) + "\n")
    with ThreadPoolExecutor(WORKERS_PER_MODEL) as ex: list(ex.map(one, todo))
    rows = load_ck(model); errs = sum(1 for r in rows.values() if not r.get("pick"))
    log(f"{model}: done {len(rows)} rows, {errs} without a pick, spend ${spend():.4f}")
def main():
    os.makedirs(PARSED, exist_ok=True)
    cases = json.load(open(find_input("RUNNER_JSON", "library_v2_smart_runner.json"))); models = sys.argv[1:] or DEFAULT_MODELS
    blocked = {}; leak = []
    for c in cases:
        for v, (s, o) in variants(c).items():
            h = phi_hits(POLICY + "\n\n" + s)
            if h: blocked.setdefault(c["id"], []).extend(f"{v}:{lab}" for lab, _ in h)
            if LEAK.search(POLICY + "\n\n" + s): leak.append((c["id"], v))
    json.dump({"cases": len(cases), "variants_checked": sum(len(variants(c)) for c in cases), "phi_blocked_cases": len(blocked), "phi_hits": blocked,
               "label_leak_hits": leak, "allowance": "relative day references (Day -N, Days -N to -M, Day -N hh:mm to Day M) removed before matching; case-sensitive titles"},
              open(os.path.join(OUT, "phi_report.json"), "w"), indent=1)
    log(f"pre-send: {len(cases)} cases, PHI-blocked {len(blocked)}, label-leak hits {len(leak)}")
    if leak: sys.exit("label leak in model-visible text; nothing sent")
    send = [c for c in cases if c["id"] not in blocked]
    if "--check-only" in sys.argv: return
    key = os.environ.get("OPENROUTER_API_KEY") or sys.exit("OPENROUTER_API_KEY not set; nothing was sent.")
    log(f"start: models {models}, cap ${SPEND_CAP:.2f}, spend so far ${spend():.4f}")
    with ThreadPoolExecutor(len(models)) as ex: list(ex.map(lambda m: run_model(m, send, key), models))
    log(f"end: spend ${spend():.4f}" + (" (STOPPED AT CAP)" if STOP.is_set() else ""))
if __name__ == "__main__": main()
