"""Run the GoalJevFly FlyPolicy (EPG top-12 connectome gate) over every case, one step per day, locally (no network).

Usage: GOAL_FLY_SRC=/path/to/GoalJevFly/src python run_fly.py [library_accepted.json] [out.json]
Stores per-day readouts for several leak values; thresholds are applied later by score_fly.py
(the readout does not depend on the threshold).
"""
from __future__ import annotations
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from fly_flags import derive_flags  # noqa: E402

DEFAULT_SRC = "/Volumes/WS4TB/My-Builds/SWE/Developer-Workflow/deesatzed--goaljevfly/GoalJevFly/src"
ASSET = "goal_fly/circuits/assets/epg_top12_male_cns_v1.json"
LEAKS = (0.5, 0.8, 0.95)

def load_fly(src=None):
    src = src or os.environ.get("GOAL_FLY_SRC", DEFAULT_SRC)
    if not os.path.isdir(src):
        raise SystemExit(f"GoalJevFly source not found: {src} (is the external volume mounted? set GOAL_FLY_SRC)")
    asset = os.path.join(src, ASSET)
    if not os.path.isfile(asset): raise SystemExit(f"Fly receipt asset missing: {asset}")
    sys.path.insert(0, src)
    from goal_fly.circuits.provenance import GraphReceipt
    from goal_fly.policies.fly import FlyPolicy
    from goal_fly.supervision.state import ObservedState
    from goal_fly.supervision.actions import ActionKind, ActionProposal
    return GraphReceipt.load(asset), FlyPolicy, ObservedState, ActionKind, ActionProposal

def find_accepted():
    for p in (os.environ.get("ACCEPTED_JSON"), os.path.join(HERE, "..", "library", "library_v2_smart_accepted.json"),
              "/workspace/jevfly_smoke/library_v2/smart_triggers/library_v2_smart_accepted.json"):
        if p and os.path.exists(p): return p
    raise SystemExit("library_v2_smart_accepted.json not found: set ACCEPTED_JSON")

def run_case(policy, flags, ObservedState, cont, chk):
    policy.reset_episode(); out = []
    for d in flags["days"]:
        s = ObservedState(evidence_refs=(), repeated_failure_signatures=("x",) if d["repeated"] else (),
                          has_new_diagnostic_evidence=False, latent_failure_signal=d["latent"],
                          verified_task_failure=d["verified"], missing_fields=())
        policy.choose(s, cont, chk); out.append(round(policy.last_readout, 6))
    return out

def main(argv):
    lib = argv[1] if len(argv) > 1 else find_accepted()
    out = argv[2] if len(argv) > 2 else os.path.join(HERE, "results", "fly_readouts.json")
    receipt, FlyPolicy, ObservedState, AK, AP = load_fly()
    cont = AP(AK.CONTINUE, "continue", "task/", "none", ("x",), "resume")
    chk = AP(AK.CHECK, "check", "task/", "local", ("x",), "verify")
    cases = json.load(open(lib))["cases"]; res = {}
    pols = {lk: FlyPolicy(receipt, leak=lk, threshold=0.5) for lk in LEAKS}
    for c in cases:
        f = derive_flags(c)
        res[c["case_id"]] = {"days": [{k: d[k] for k in ("day", "latent", "repeated", "verified", "why")} for d in f["days"]],
                             "l1": f["l1"], "readouts": {str(lk): run_case(p, f, ObservedState, cont, chk) for lk, p in pols.items()}}
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    json.dump({"leaks": list(LEAKS), "n_cases": len(res), "cases": res}, open(out, "w"), indent=1)
    print(f"wrote {out}: {len(res)} cases x {len(LEAKS)} leaks")

if __name__ == "__main__": main(sys.argv)
