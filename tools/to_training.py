#!/usr/bin/env python3
"""Convert Crossroads routing logs (JSONL or JSON export) into chat-style fine-tune examples.

Each human routing decision becomes:
  system:    crossroads router instructions
  user:      case context + upstream routed answers + handoff (source, dest, question, options, proposal, confidence)
  assistant: the human's routed answer (JSON: {"route": ..., "changed": bool})
Changed decisions (overrides) are upweighted; downstream outcome is kept in metadata.

Usage: python3 tools/to_training.py routing.jsonl -o out_dir
"""
import argparse, collections, json, os

SYSTEM = ("You are the crossroads router between decision agents. For each handoff, decide whether to pass the "
          "source agent's proposed answer through unchanged, flip it (binary), or select a different option "
          "(categorical). Weigh prior history (anticoagulation, immunosuppression, MDRO status, recent ED visits). Reply with JSON {\"route\": <answer>, \"changed\": <bool>}.")

def load(p):
    t = open(p).read().strip()
    return json.loads(t) if t.startswith("[") else [json.loads(l) for l in t.splitlines() if l.strip()]

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("log"); ap.add_argument("-o", "--out", default="training_out")
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
    recs = load(a.log); out = []; st = collections.Counter()
    for r in recs:
        user = (f"Case {r['caseID']}: {r['inputContext']}\n"
                f"History: {r.get('history', 'none')}\n"
                f"Upstream: {'; '.join(r.get('upstreamAnswers') or []) or 'none'}\n"
                f"Handoff: {r['sourceAgent']} -> {r['destAgent']} | {r['question']} ({r['answerType']})\n"
                f"Options: {', '.join(r['options'])}\n"
                f"Proposed: {r['proposedAnswer']} (confidence {r['proposedConfidence']:.2f})\n"
                f"Crossroads queue depth: {r.get('queueDepth', 0)}")
        asst = json.dumps({"route": r["routedAnswer"], "changed": r["changed"]})
        kind = "override" if r["changed"] else "pass_through"
        st[kind] += 1
        if r.get("agreesWithGroundTruth") is False: st["human_disagrees_gt"] += 1
        out.append({"messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user},
                                 {"role": "assistant", "content": asst}],
                    "weight": 2.0 if r["changed"] else 1.0,
                    "metadata": {"gesture": r["gesture"], "latency_s": round(r["latency"], 3), "stage": r["stage"],
                                 "groundTruth": r.get("groundTruth"), "downstreamOutcome": r.get("downstreamOutcome"),
                                 "distance_m": r.get("distanceFromHead"), "neighbors": r.get("neighbors")}})
    with open(os.path.join(a.out, "crossroads_chat.jsonl"), "w") as f:
        for o in out: f.write(json.dumps(o, ensure_ascii=False) + "\n")
    s = {"records": len(recs), "examples": len(out), "by_kind": dict(st),
         "by_link": dict(collections.Counter(f"{r['sourceAgent']}->{r['destAgent']}" for r in recs)),
         "outcomes": dict(collections.Counter(r.get("downstreamOutcome") for r in recs))}
    json.dump(s, open(os.path.join(a.out, "summary.json"), "w"), indent=2); print(json.dumps(s, indent=2))

if __name__ == "__main__":
    main()
