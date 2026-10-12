#!/usr/bin/env python3
"""Domain-agnostic: convert crossroads RoutingDecision logs (JSONL/JSON) into chat-style fine-tune examples.

user      = item display line + history + structured context + capacity snapshot + upstream answers + handoff
assistant = {"route": routedAnswer, "changed": bool, "trial": bool}
Overrides are upweighted. Trial-category routes are kept (flagged) so a model can learn proposed new categories,
but they are excluded from ground-truth accuracy. Domain/site/registry version are kept in metadata.

Usage: python3 tools/to_training.py routing.jsonl -o out_dir [--system "..."]
"""
import argparse, collections, json, os

DEFAULT_SYSTEM = ("You are the crossroads router between narrow decision agents. For each handoff, pass the source agent's "
                  "proposed answer through, flip it (binary), or select another category (categorical), weighing the item's "
                  "history and the current capacity snapshot. You may propose a new category only when none fits. "
                  "Reply with JSON {\"route\": <answer>, \"changed\": <bool>, \"trial\": <bool>}.")

def load(p):
    t = open(p).read().strip()
    return json.loads(t) if t.startswith("[") else [json.loads(l) for l in t.splitlines() if l.strip()]

def kv(d): return ", ".join(f"{k}={v}" for k, v in sorted((d or {}).items())) or "none"

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("log"); ap.add_argument("-o", "--out", default="training_out")
    ap.add_argument("--system", default=DEFAULT_SYSTEM)
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
    recs = load(a.log); out = []; st = collections.Counter()
    for r in recs:
        user = (f"[{r['domain']} · site {r['siteId']} · registry v{r['registryVersion']}] {r['itemId']}: {r['displayLine']}\n"
                f"History: {r.get('history') or 'none'}\n"
                f"Context: {kv(r.get('context'))}\n"
                f"Capacity: {kv(r.get('capacity'))}\n"
                f"Upstream: {kv(r.get('upstream'))}\n"
                f"Handoff: {r['sourceAgent']} -> {r['destAgent']} | {r['question']} ({r['answerType']})\n"
                f"Options: {', '.join(r['options'])}" + (f" | trial: {', '.join(r['trialOptions'])}" if r.get('trialOptions') else "") + "\n"
                f"Proposed: {r['proposedAnswer']} (confidence {r['proposedConfidence']:.2f})")
        asst = json.dumps({"route": r["routedAnswer"], "changed": r["changed"], "trial": r.get("routedIsTrial", False)})
        kind = "trial_category" if r.get("routedIsTrial") else ("override" if r["changed"] else "pass_through")
        st[kind] += 1
        if r.get("agreesWithGroundTruth") is False: st["human_disagrees_gt"] += 1
        out.append({"messages": [{"role": "system", "content": a.system}, {"role": "user", "content": user},
                                 {"role": "assistant", "content": asst}],
                    "weight": 2.0 if r["changed"] else 1.0,
                    "metadata": {k: r.get(k) for k in ["domain", "siteId", "registryVersion", "linkId", "gesture", "latency", "priority",
                                                        "groundTruth", "effectiveAnswer", "downstreamOutcome", "distanceFromHead", "neighbors"]}})
    with open(os.path.join(a.out, "crossroads_chat.jsonl"), "w") as f:
        for o in out: f.write(json.dumps(o, ensure_ascii=False) + "\n")
    s = {"records": len(recs), "examples": len(out), "by_kind": dict(st),
         "by_link": dict(collections.Counter(r["linkId"] for r in recs)),
         "outcomes": dict(collections.Counter(r.get("downstreamOutcome") for r in recs))}
    json.dump(s, open(os.path.join(a.out, "summary.json"), "w"), indent=2); print(json.dumps(s, indent=2))

if __name__ == "__main__":
    main()
