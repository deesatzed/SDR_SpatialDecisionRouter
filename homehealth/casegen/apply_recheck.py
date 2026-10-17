"""Apply agreed re-check label additions (trigger metadata only, never a route change) to library_v2_smart_accepted.json; append review rows; refresh CSVs and summary.
Run by build_outputs.py after apply_chest_pain.py. Idempotent (the library is rebuilt from base on every build)."""
import json, csv, subprocess, os
if not os.path.exists("recheck/decisions.json"): raise SystemExit("no recheck decisions")
D = json.load(open("recheck/decisions.json")); dec = {r["case_id"]: r for r in D["decisions"]}
FIELDS = ["hard_trigger_rule", "trigger_tier", "suppression_reason", "confirm_step", "confirm_timeout_min", "baseline_layer"]
lib = json.load(open("library_v2_smart_accepted.json")); n = 0
for c in lib["cases"]:
    r = dec.get(c["case_id"])
    if not r or not r["apply"] or c.get("hard_trigger"): continue
    p = r["proposal"]
    c["prev_labels"] = {"hard_trigger": c.get("hard_trigger"), **{f: c.get(f) for f in FIELDS}}
    c["hard_trigger"] = True; c.update({f: p.get(f) for f in FIELDS})
    c["recheck"] = {"policy": "SMART_TRIGGERS v1.3", "date": "2026-10-17", "approved_scope": "Wayne: re-check non-trigger cases; apply only label additions both agree on, no route change",
                    "proposer": "anthropic/claude-haiku-5.5", "grader": "google/gemini-4-argon GRADER_LLM3_v1.3 rev c (blind, compact)", "evaluator": "trigger_eval det screen",
                    "evaluator_scoreable": r["det_scoreable"], "evidence": p.get("evidence"), "grader_score": (r["grade"] or {}).get("score")}
    n += 1
lib.setdefault("provenance", {})["recheck"] = f"recheck/decisions.json: {n} non-trigger cases gained agreed trigger metadata (no route changes)"
json.dump(lib, open("library_v2_smart_accepted.json", "w"), indent=1)
q = [r for r in csv.DictReader(open("review_queue.csv")) if r.get("pass") != "recheck"] + D["review_rows"]
keys = []
for r in q: keys += [k for k in r if k not in keys]
with open("review_queue.csv", "w", newline="") as f: w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(q)
print(subprocess.run(["python3", "../../casegen/convert_casegen.py", "--source=LIB=library_v2_smart_accepted.json:library_v2_smart:v2.2-v2.3", "--out-prefix=library_v2_smart_"], capture_output=True, text=True).stdout)
S = json.load(open("summary.json")); S["recheck"] = {**D["summary"], "applied_in_library": n}; S["library_v2_smart_n"] = len(lib["cases"])
S["library_hard_trigger_n"] = sum(bool(c.get("hard_trigger")) for c in lib["cases"])
json.dump(S, open("summary.json", "w"), indent=1)
print("recheck applied:", n, "| review rows:", len(D["review_rows"]))
