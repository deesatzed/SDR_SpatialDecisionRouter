"""Score the CURRENT Layer 1 (layer1_adapter params) + stored Jev picks against a ruled key (SYNTHETIC). No API calls.
Usage: python3 score_ruled.py <key.json> <out.json> <picks_dir> [picks_dir ...]
Systems: default L1 + dual(d1-ultra, pplx) cautious_max_hitm; challenger L1 + dual(d1-ultra, drex-max); single L1 + d1-ultra, L1 + pplx, L1 + drex-max; Layer 1 alone (decided cases).
Device tickets come from Layer 1 (type match vs expected_device_ticket; any_device_ticket_ok cases accept any ticket type)."""
import json, os, sys
HO = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HO, "..", "jev_baseline"))
import score_v110 as V, dual_jev as D, score_l1jev as SL, layer1_adapter as L  # noqa: E402
KEY, OUT, DIRS = sys.argv[1], sys.argv[2], sys.argv[3:]
if os.environ.get("V1120_OFF"): L.T.v110(L.PARAMS).setdefault("v1120", {})["enabled"] = False   # score the v1.11.2 baseline
M3 = ["liquid/d1-ultra", "perplexity/pplx-decider-v1.2", "nace-ai/drex-max"]
cases = json.load(open(KEY))["cases"]
P = {m: {} for m in M3}
for d in DIRS:
    for m in M3:
        f = os.path.join(d, SL.S_slug(m) + ".jsonl")
        if os.path.exists(f): P[m].update(D.load_picks(f))
def pick(res, s): m = dict(res[s]); m["n_errors"] = len(m["errors"]); m["errors_caught_by_hitm"] = sum(1 for x in m["errors"] if x["hitm"]); return m
base = V.run(cases, {"liquid/d1-ultra": P[M3[0]], "perplexity/pplx-decider-v1.2": P[M3[1]]})
chal = V.run(cases, {"liquid/d1-ultra": P[M3[0]], "perplexity/pplx-decider-v1.2": P[M3[2]]})
sysm = {"L1 + dual(d1-ultra, pplx) [default]": pick(base, V.SYS[0]), "L1 + dual(d1-ultra, drex-max) [challenger]": pick(chal, V.SYS[0]),
        "L1 + d1-ultra": pick(base, V.SYS[1]), "L1 + pplx": pick(base, V.SYS[2]), "L1 + drex-max": pick(chal, V.SYS[2]), "Layer 1 alone": pick(base, V.SYS[3])}
l1 = {c["case_id"]: L.evaluate_case(c) for c in cases}
tk = [c for c in cases if c.get("expected_device_ticket")]
def hit(c):
    t = (l1[c["case_id"]].get("device_ticket") or {}).get("type")
    return bool(t) and (t == c["expected_device_ticket"] or c.get("any_device_ticket_ok"))
tk_ids = {c["case_id"] for c in tk}
out = {"params": L.PARAMS.get("version"), "key": os.path.basename(KEY), "n": len(cases), "picks_dirs": [os.path.relpath(d, HO) for d in DIRS],
       "missing_picks": {m: [c["case_id"] for c in cases if "LIB-" + c["case_id"] not in P[m]] for m in M3}, "systems": sysm,
       "device_tickets": {"expected": len(tk), "hit": sum(hit(c) for c in tk), "any_ticket": sum(1 for c in tk if l1[c["case_id"]].get("device_ticket")),
                          "missed_ids": [c["case_id"] for c in tk if not hit(c)], "unexpected_ids": [i for i, d in l1.items() if d.get("device_ticket") and i not in tk_ids]},
       "layer1_decided_ids": [i for i, d in l1.items() if L.route(d, None)[0] is not None], "tier_agreement": {k: v for k, v in base["tier_agreement"].items()}}
os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True); json.dump(out, open(OUT, "w"), indent=1)
for s, m in sysm.items():
    print(f'{s:44s} acc={m["accuracy"]} ({m["decided"]}/{m["n"]}) crit={m["critical_misses"]} {m["critical_ids"]} fp/100={m["false_pages_per_100"]} {m["false_page_ids"]} hitm/100={m["hitm_per_100"]} err={m["n_errors"]}')
print("tickets", {k: v for k, v in out["device_tickets"].items()}, "missing", {k: len(v) for k, v in out["missing_picks"].items()})
