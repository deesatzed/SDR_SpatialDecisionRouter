"""Build smart_triggers outputs from raw/ + merge_*/ (counts from files only)."""
import json, csv, glob, collections, subprocess, os
PB = [b for b in ("ST1", "ST2", "ST3", "ST4") if os.path.exists(f"raw/{b}.grader.json")]
args = ["python3", "../../casegen/prompts_v2/grade_merge.py", "--smart", "--out", "merge_pairs", "--src", "library_v2_smart_pairs"]
for b in PB: args += ["--batch", f"raw/{b}.batch.json", "--grader", f"raw/{b}.grader.json"]
subprocess.run(args, capture_output=True)
V = {}
for f in glob.glob("raw/*.grader.json"):
    for v in json.load(open(f))["verdicts"]: V[v["case_id"]] = v
rel = json.load(open("raw/relabel_batch.json"))["cases"]
racc = {c["case_id"] for c in json.load(open("merge_relabel/accepted.json"))["cases"]}
rq = {r["case_id"]: r["queue_reasons"] for r in csv.DictReader(open("merge_relabel/review_queue.csv"))}
rf = {r["case_id"]: r["issues"] for r in csv.DictReader(open("merge_relabel/fix_list.csv"))}
rows = []
for c in rel:
    v = V.get(c["case_id"], {}); b = v.get("blind") or {}; p = c["prev_labels"]
    c["grade_v1_2"] = {"grader": "google/gemini-4-argon GRADER_LLM3_v1.2", "blind_route": b.get("grader_route"), "blind_rule": b.get("grader_hard_trigger_rule"),
                       "blind_tier": b.get("grader_trigger_tier"), "blind_suppression_reason": b.get("grader_suppression_reason"), "action": v.get("action"), "score": v.get("score"),
                       "merge_status": "accepted" if c["case_id"] in racc else ("queue:" + rq[c["case_id"]] if c["case_id"] in rq else "fix")}
    rows.append({"case_id": c["case_id"], "src_library": c.get("src_library"), "old_rule": p["hard_trigger_rule"], "new_rule": c["hard_trigger_rule"], "trigger_tier": c["trigger_tier"],
                 "confirm_step": c["confirm_step"], "confirm_timeout_min": c["confirm_timeout_min"], "suppression_reason": c["suppression_reason"],
                 "old_route": p["expected_route"], "new_route": c["expected_route"], "route_changed": p["expected_route"] != c["expected_route"],
                 "old_alternates": "|".join(p["acceptable_alternates"] or []), "new_alternates": "|".join(c["acceptable_alternates"] or []),
                 "grader_blind_route": b.get("grader_route"), "grader_blind_rule": b.get("grader_hard_trigger_rule"), "grader_blind_tier": b.get("grader_trigger_tier"),
                 "grader_blind_suppression_reason": b.get("grader_suppression_reason"), "grader_action": v.get("action"), "grader_score": v.get("score"),
                 "grader_agrees_route": b.get("grader_route") == c["expected_route"], "grader_agrees_tier": b.get("grader_trigger_tier") == c["trigger_tier"],
                 "merge_status": c["grade_v1_2"]["merge_status"], "checks": json.dumps(c["relabel"]["checks"]), "label_note": c["relabel"]["label_note"]})
json.dump({"cases": rel, "provenance": {"policy": "SMART_TRIGGERS v1", "relabel_model": "anthropic/claude-haiku-5.5", "grader": "google/gemini-4-argon GRADER_LLM3_v1.2", "synthetic": True}},
          open("relabeled_cases.json", "w"), indent=1)
with open("relabeled_cases.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
# new pairs
pacc = json.load(open("merge_pairs/accepted.json"))["cases"]; aid = {c["case_id"] for c in pacc}
allp = [c for b in PB for c in json.load(open(f"raw/{b}.batch.json"))["cases"]]
pid_members = collections.defaultdict(list)
for c in allp: pid_members[c["pair_id"]].append(c["case_id"])
for c in pacc:
    c["pair_complete_in_accepted"] = all(m in aid for m in pid_members[c["pair_id"]])
    c.update({"src_model": "anthropic/claude-haiku-5.5", "src_batch": c["case_id"][:3], "src_module": "smart_trigger_pairs", "src_prompt": ("GEN_LLM2_v2.3 rev b" if c["case_id"].startswith("ST4") else "GEN_LLM2_v2.3" if c["case_id"].startswith("ST3") else "GEN_LLM2_v2.2"), "src_grader": "google/gemini-4-argon GRADER_LLM3_v1.3" if c["case_id"].startswith("ST3") else "google/gemini-4-argon GRADER_LLM3_v1.2", "src_library": "library_v2_smart_pairs"})
json.dump({"cases": pacc, "provenance": {"generated_by": "smart_triggers/smart_run.py pairs", "synthetic": True}}, open("new_pairs.json", "w"), indent=1)
# combined review queue / fix list for this pass
for name in ("review_queue", "fix_list"):
    out = []
    for tag in ("relabel", "pairs"):
        for r in csv.DictReader(open(f"merge_{tag}/{name}.csv")): r["pass"] = tag; out.append(r)
    keys = []
    for r in out: keys += [k for k in r if k not in keys]
    if not keys: keys = ["case_id", "pass"]
    with open(f"{name}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(out)
# library_v2 with smart labels (relabels replace originals; non-trigger cases get null trigger fields; accepted new pairs appended)
A = json.load(open("../accepted_cases.json"))["cases"]; R = {c["case_id"]: c for c in rel if c["case_id"] in racc}
lib = []
for c in A:
    if c["case_id"] in R: lib.append(R[c["case_id"]])
    else:
        n = dict(c)
        for k in ("trigger_tier", "confirm_step", "confirm_timeout_min", "suppression_reason"): n.setdefault(k, None)
        lib.append(n)
lib += pacc
json.dump({"cases": lib, "provenance": {"base": "library_v2/accepted_cases.json", "relabel": "smart_triggers/relabeled_cases.json (accepted only)", "new_pairs": "smart_triggers/new_pairs.json", "synthetic": True}},
          open("library_v2_smart_accepted.json", "w"), indent=1)
print(subprocess.run(["python3", "../../casegen/convert_casegen.py", "--source=LIB=library_v2_smart_accepted.json:library_v2_smart:v2.2-v2.3", "--out-prefix=library_v2_smart_"], capture_output=True, text=True).stdout)
aa = ["python3", "../../casegen/prompts_v2/grade_merge.py", "--smart", "--batch", "raw/relabel_batch.json", "--grader", "raw/RELABEL-1.grader.json", "--grader", "raw/RELABEL-2.grader.json", "--out", "merge_all", "--src", "smart"]
for b in PB: aa += ["--batch", f"raw/{b}.batch.json", "--grader", f"raw/{b}.grader.json"]
subprocess.run(aa, capture_output=True)
# summary numbers
tier = collections.Counter(r["trigger_tier"] for r in rows); rc = [r for r in rows if r["route_changed"]]
ac = [r for r in rows if r["old_alternates"] != r["new_alternates"]]
spend = sum((json.load(open(f)).get("usage") or {}).get("cost_usd") or 0 for f in glob.glob("raw/*.try*.json"))
calls = [(json.load(open(f))["tag"], json.load(open(f))["model"], (json.load(open(f)).get("usage") or {}).get("cost_usd")) for f in sorted(glob.glob("raw/*.try*.json"))]
S = {"relabel_n": len(rows), "tiers": dict(tier), "by_rule_tier": {f"{r['new_rule']}:{r['trigger_tier']}": n for r, n in []}, "route_changes": [(r["case_id"], r["old_route"], r["new_route"], r["suppression_reason"]) for r in rc],
     "alternate_changes": [(r["case_id"], r["old_alternates"], r["new_alternates"]) for r in ac], "rule_renames": dict(collections.Counter(f"{r['old_rule']}->{r['new_rule']}" for r in rows if r["old_rule"] != r["new_rule"])),
     "confirm_steps": dict(collections.Counter(r["confirm_step"] for r in rows if r["trigger_tier"] == "CONFIRM_FIRST")),
     "grader_disagree_route": [r["case_id"] for r in rows if not r["grader_agrees_route"]], "grader_disagree_tier": [r["case_id"] for r in rows if not r["grader_agrees_tier"]],
     "relabel_merge": dict(collections.Counter(r["merge_status"] for r in rows)),
     "pairs_generated": len(allp), "pairs_accepted": len(pacc), "complete_pairs_accepted": len({c["pair_id"] for c in pacc if c["pair_complete_in_accepted"]}),
     "pairs_queue": {r["case_id"]: r["queue_reasons"] for r in csv.DictReader(open("merge_pairs/review_queue.csv"))}, "pairs_fix": [r["case_id"] for r in csv.DictReader(open("merge_pairs/fix_list.csv"))],
     "pairs_by_batch": {b: {"generated": sum(c["case_id"].startswith(b) for c in allp), "accepted": sum(c["case_id"].startswith(b) for c in pacc), "complete_pairs": len({c["pair_id"] for c in pacc if c["case_id"].startswith(b) and c["pair_complete_in_accepted"]})} for b in PB},
     "st3_layers": {c["case_id"]: [c.get("baseline_layer"), c.get("trigger_tier"), c["expected_route"]] for c in allp if c["case_id"].startswith("ST3")},
     "library_v2_smart_n": len(lib), "spend_usd": round(spend, 4), "calls": calls}
bt = collections.Counter((r["new_rule"], r["trigger_tier"]) for r in rows); S["by_rule_tier"] = {f"{a}:{b}": n for (a, b), n in sorted(bt.items())}
json.dump(S, open("summary.json", "w"), indent=1); print(json.dumps({k: v for k, v in S.items() if k != "calls"}, indent=1))

# chest-pain banded rule (SMART_TRIGGERS section 7) applied after every rebuild
import subprocess as _sp; print(_sp.run(["python3", "apply_chest_pain.py"], capture_output=True, text=True).stdout)
import os as _os
if _os.path.exists("recheck/decisions.json"): print(_sp.run(["python3", "apply_recheck.py"], capture_output=True, text=True).stdout)
# Wayne's clinician rulings on the review queue (SMART_TRIGGERS v1.5), applied last
if _os.path.exists("clinician_rulings.csv"): print(_sp.run(["python3", "apply_rulings.py"], capture_output=True, text=True).stdout[-600:])
