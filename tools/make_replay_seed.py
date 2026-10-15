#!/usr/bin/env python3
"""Deterministic SYNTHETIC history for the M4 promotion demo (docs/SYMBIOSIS_PLAN.md M4).

Writes data/replay_seed/:
  train.jsonl          held-IN decisions the critic may read (unified-record shape, outcomes known)
  replay/seed/…        held-OUT frozen, blinded replay pack written by tools/unified_export.export (cases / answers / manifest)
Train and replay are disjoint by construction (different ids). All numbers are synthetic placeholders, not measurements.

Planted structure (so the demo is honest about what it shows):
  personal_finance: when the agent is unsure (confidence < 0.65) the outcome is usually "Hold — gather info" → a real pattern.
  ed_triage: the train split contains a SPURIOUS in-sample pattern (critical cards → "Alternative plan"); on the held-out
             replay critical cards resolve to "Escalate", so a candidate built on it must lose (and break the clinical guard).
"""
import json, os, random, shutil, sys
sys.path.insert(0, os.path.dirname(__file__))
import unified_export as ux

OPTS = ["Accept plan", "Alternative plan", "Hold — gather info", "Escalate"]


def rec(i, split, area, conf, sev, prop, outcome):
    return {"schema": "sdr.decision.v1", "kind": "decision", "id": f"seed-{split}-{area}-{i:03d}", "timestamp": "2026-10-01T00:00:00Z",
            "domain": f"symbiosis:{area}", "context_id": area, "generation": 0, "question": "Plan:", "options": OPTS,
            "card_payload": {"area": area, "severity": sev, "title": f"synthetic {area} case {i}"},
            "agent_proposal": {"answer": prop, "confidence": conf},
            "human_decision": {"label": "pass", "answer": outcome, "gesture": "pass", "changed": outcome != prop, "decided_by": "human"},
            "outcome": {"value": outcome, "source": "synthetic_seed", "observed_at": "2026-10-02T00:00:00Z"}, "provenance": "synthetic_seed"}


def gen(split, rnd, n_fin, n_ed):
    out = []
    for i in range(n_fin):
        conf = round(rnd.uniform(0.5, 0.95), 2)
        if conf < 0.65: o = "Hold — gather info" if rnd.random() < 0.8 else "Accept plan"
        else: o = "Accept plan" if rnd.random() < 0.85 else "Alternative plan"
        out.append(rec(i, split, "personal_finance", conf, "normal", "Accept plan", o))
    for i in range(n_ed):
        if i % 5 == 0:   # critical
            spurious = split == "train" and i % 10 == 0 or (split == "train" and i in (5, 15, 25))
            out.append(rec(i, split, "ed_triage", 0.9, "critical", "Escalate", "Alternative plan" if spurious else "Escalate"))
        else:
            conf = round(rnd.uniform(0.6, 0.95), 2)
            o = "Accept plan" if rnd.random() < 0.8 else "Hold — gather info"
            out.append(rec(i, split, "ed_triage", conf, "normal", "Accept plan", o))
    return out


def main(root="data/replay_seed"):
    train = gen("train", random.Random(41), 60, 40)
    held = gen("replay", random.Random(42), 60, 40)
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, "train.jsonl"), "w", encoding="utf-8") as f:
        for r in train: f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    tmp = os.path.join(root, "_export")
    ux.export(held, tmp, "seed")
    dst = os.path.join(root, "replay")
    shutil.rmtree(dst, ignore_errors=True); shutil.move(os.path.join(tmp, "replay"), dst); shutil.rmtree(tmp)
    # freeze: pin frozen_at so the pack is byte-stable across regenerations
    mp = os.path.join(dst, "seed", "manifest.json"); m = json.load(open(mp)); m["frozen_at"] = "2026-10-15T00:00:00+00:00"
    json.dump(m, open(mp, "w"), indent=2, sort_keys=True)
    # app bundle copies (flat names) — pytest checks they stay byte-identical
    app = "SpatialDecisionRouter/Resources/ReplaySeed"; os.makedirs(app, exist_ok=True)
    for s, d in (("train.jsonl", "replay_train.jsonl"), ("replay/seed/cases.jsonl", "replay_cases.jsonl"),
                 ("replay/seed/answers.jsonl", "replay_answers.jsonl"), ("replay/seed/manifest.json", "replay_manifest.json")):
        shutil.copyfile(os.path.join(root, s), os.path.join(app, d))
    print(f"train {len(train)} · replay {len(held)} → {root}")


if __name__ == "__main__":
    main()
