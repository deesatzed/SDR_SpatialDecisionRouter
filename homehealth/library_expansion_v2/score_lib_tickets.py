"""Library-only device-ticket + Layer-1 route check (SYNTHETIC, no API calls). Usage: python3 score_lib_tickets.py [out.json]
Env V1140_OFF=1 scores v1.13.0 (new v1.14.0 rules off). Library = library_expansion_v1 + library_expansion_v2 accepted cases."""
import json, os, sys, collections
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(H, "..", "jev_baseline"))
import layer1_adapter as L  # noqa: E402
if os.environ.get("V1140_OFF"): L.T.v110(L.PARAMS).setdefault("v1140", {})["enabled"] = False
SETS = {"v1": os.path.join(H, "..", "library_expansion_v1", "library_expansion_v1_accepted.json"), "v2": os.path.join(H, "library_expansion_v2_accepted.json")}
rows = []
for s, f in SETS.items():
    if not os.path.exists(f): continue
    for c in json.load(open(f))["cases"]:
        d = L.evaluate_case(c); r, own = L.route(d, None)
        rows.append({"set": s, "case_id": c["case_id"], "expected": c["expected_route"], "alts": c.get("acceptable_alternates") or [], "l1_route": r, "owner": own,
                     "exp_ticket": c.get("expected_device_ticket"), "ticket": (d.get("device_ticket") or {}).get("type"), "detail": (d.get("device_ticket") or {}).get("detail")})
S = {}
for s in sorted({r["set"] for r in rows}) + ["all"]:
    R = [r for r in rows if s == "all" or r["set"] == s]; dec = [r for r in R if r["l1_route"]]
    S[s] = {"n": len(R), "tickets_expected": sum(1 for r in R if r["exp_ticket"]), "tickets_hit": sum(1 for r in R if r["exp_ticket"] and r["ticket"]),
            "false_tickets": [r["case_id"] for r in R if r["ticket"] and not r["exp_ticket"]], "missed_tickets": [r["case_id"] for r in R if r["exp_ticket"] and not r["ticket"]],
            "l1_decided": len(dec), "l1_route_errors": [r["case_id"] for r in dec if r["l1_route"] != r["expected"] and r["l1_route"] not in r["alts"]]}
print(json.dumps(S, indent=1))
if len(sys.argv) > 1: json.dump({"summary": S, "rows": rows}, open(sys.argv[1], "w"), indent=1)
