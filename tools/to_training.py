#!/usr/bin/env python3
"""Dry-run: convert a Spatial Decision Router export (JSONL or JSON) into a fine-tune dataset.

accept (and label agrees with outcome/GT)      -> positive example for the recommending model
reject/recategorize (human overrode the model) -> hard negative (rejected = model's rec) + corrected label
needsMoreInfo / no label                       -> skipped (logged as uncertain for active learning)

Usage: python3 tools/to_training.py export.jsonl -o out_dir
"""
import argparse, collections, json, os, sys

def load(path):
    with open(path) as f:
        text = f.read().strip()
    return json.loads(text) if text.startswith("[") else [json.loads(l) for l in text.splitlines() if l.strip()]

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("export"); ap.add_argument("-o", "--out", default="training_out")
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
    recs = load(a.export)
    train, uncertain = [], []
    stats = collections.Counter()
    for r in recs:
        p = r["proposal"]
        label = r.get("chosenLabel")
        target = r.get("outcome") or label          # delayed outcome wins when joined
        if not label or not target:
            uncertain.append({"id": p["id"], "model": p["modelID"], "evidence": p["evidence"]}); stats["skipped"] += 1; continue
        prompt = (f"[{p['category']} | {p['type']}] options={p['options']}\n"
                  f"Evidence: {p['evidence']}\nModel confidence: {p['confidence']:.2f}")
        overrode = label != p["recommended"]
        kind = "hard_negative" if overrode else "positive"
        if target != label: kind += "+outcome_corrected"
        stats[kind] += 1
        train.append({
            "model": p["modelID"], "kind": kind, "prompt": prompt, "completion": target,
            "rejected": p["recommended"] if p["recommended"] != target else None,
            "weight": 2.0 if overrode else 1.0,   # overrides are the high-value signal
            "meta": {"proposal": p["id"], "action": r["action"], "latency_s": r.get("decisionLatency"),
                     "inspected": r.get("inspected"), "distance_m": r["position"]["distance"],
                     "neighbors": r.get("neighborProposalIDs"), "stream": r.get("stream")},
        })
    with open(os.path.join(a.out, "train.jsonl"), "w") as f:
        for t in train: f.write(json.dumps(t) + "\n")
    with open(os.path.join(a.out, "uncertain_for_active_learning.jsonl"), "w") as f:
        for u in uncertain: f.write(json.dumps(u) + "\n")
    per_model = collections.Counter(t["model"] for t in train)
    summary = {"records": len(recs), "train_examples": len(train), "by_kind": dict(stats), "by_model": dict(per_model)}
    json.dump(summary, open(os.path.join(a.out, "summary.json"), "w"), indent=2)
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    sys.exit(main())
