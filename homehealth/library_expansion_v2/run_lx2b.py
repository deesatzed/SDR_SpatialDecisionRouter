"""library_expansion_v2 resume driver (SYNTHETIC). Same prompts/models as run_lx2.py, but: grader calls in chunks of <= 6 cases
(22-case grade calls timed out twice), LX11/LX12 generated with haiku-5.5 (deepseek-v4-pro gen timed out). Skips anything already on disk. Never prints the key."""
import json, os, sys, threading
import run_lx2 as R
rl = R.rl; from orcall import parse_json
def grade_chunk(b, k, cs, dnr, sub, requested):
    tag = f"{b}-p{k}"
    if os.path.exists(f"grade/{tag}.grader.json"): return
    for attempt in range(3):
        if rl.STATE["stopped"]: return
        user = json.dumps({"batch_id": tag, "requested": {**requested, "n": len(cs), "sub_batches": sub}, "do_not_repeat": dnr, "batch": {"cases": cs, "tally": {b: sub[b]["generator_tally"]}}})
        r = rl.call(f"grade {tag} try{attempt+1}", rl.GRADER, rl.GRADER_SYS, user, 40000, 0.2)
        obj, how = parse_json(r["content"])
        json.dump({**r, "parse": how, "case_ids": [c["case_id"] for c in cs]}, open(f"grade/{tag}.try{attempt+1}.response.json", "w"), indent=1)
        if isinstance(obj, dict) and len(obj.get("verdicts", [])) >= len(cs):
            json.dump(obj, open(f"grade/{tag}.grader.json", "w"), indent=1); rl.log(f"GRADE {tag}: ok"); return
        rl.log(f"GRADE {tag} bad output parse={how} finish={r['finish_reason']}")
def grade_batch(b):
    d = json.load(open(f"gen/{b}.batch.json")); cases = d["cases"]
    sub = {b: {"module": d["meta"]["module"], "n": len(cases), "generator_tally": d["tally"]}}
    dnr = rl.STATE["dnr"][:rl.STATE["dnr_marks"][b]]
    h = (len(cases) + 1) // 2
    ts = [threading.Thread(target=grade_chunk, args=(b, k, cs, dnr, sub, R.REQ)) for k, cs in ((1, cases[:h]), (2, cases[h:]))]
    [t.start() for t in ts]; [t.join() for t in ts]
def stream(b):
    S = {x[0]: x for x in R.SP.HK}; _, _, _, n, t = S[b]
    if not os.path.exists(f"gen/{b}.batch.json"):
        if not rl.gen_batch(b, R.MODELS["haiku"], rl.HARD_SYS, n, t + "\n" + R.COMMON, True, 120000, "haiku"): return
    grade_batch(b)
if __name__ == "__main__":
    rl.log(f"LX2b START cap ${rl.BUDGET:.2f} spend ${rl.STATE['spend']:.3f}")
    ts = [threading.Thread(target=stream, args=(b,)) for b in ("LX9", "LX10", "LX11", "LX12")]
    [t.start() for t in ts]; [t.join() for t in ts]
    rl.log(f"LX2b END spend=${rl.STATE['spend']:.3f}")
