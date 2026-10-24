"""Layer 1 alone on the library expansions (SYNTHETIC): ticket hits/false tickets and route errors. Usage: python3 score_library.py <out.json>. No API calls."""
import json, os, sys
HO = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HO, "..", "jev_baseline"))
import layer1_adapter as L  # noqa: E402
SETS = {"v1": "library_expansion_v1/library_expansion_v1_accepted.json", "v2": "library_expansion_v2/library_expansion_v2_accepted.json"}
rows = []
for s, f in SETS.items():
    for c in json.load(open(os.path.join(HO, "..", f)))["cases"]:
        d = L.evaluate_case(c); rt, own = L.route(d, None)
        t = L.V141.final_ticket(d, rt or c["expected_route"]) or {}   # POLICY 1: no picks here, so a Jev-routed conditional ticket is gated on the labelled route
        rows.append({"set": s, "case_id": c["case_id"], "expected": c["expected_route"], "alts": c.get("acceptable_alternates") or [], "l1_route": rt, "owner": own,
                     "rule": d.get("rule"), "exp_ticket": c.get("expected_device_ticket"), "ticket": t.get("type"), "detail": t.get("detail")})
def summ(rs):
    e = [r for r in rs if r["exp_ticket"]]; hit = [r for r in e if r["ticket"] == r["exp_ticket"]]
    return {"n": len(rs), "tickets_expected": len(e), "tickets_hit": len(hit), "false_tickets": [r["case_id"] for r in rs if r["ticket"] and not r["exp_ticket"]],
            "missed_tickets": [r["case_id"] for r in e if r not in hit], "l1_decided": sum(1 for r in rs if r["l1_route"]),
            "l1_route_errors": [r["case_id"] for r in rs if r["l1_route"] and r["l1_route"] != r["expected"] and r["l1_route"] not in r["alts"]]}
out = {"params": L.PARAMS.get("version"), "summary": {**{s: summ([r for r in rows if r["set"] == s]) for s in SETS}, "all": summ(rows)}, "rows": rows}
json.dump(out, open(sys.argv[1], "w"), indent=1); print(json.dumps(out["summary"], indent=1))
