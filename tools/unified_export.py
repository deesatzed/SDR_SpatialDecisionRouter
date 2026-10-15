#!/usr/bin/env python3
"""Unified decision record exporter (docs/SYMBIOSIS_PLAN.md §4, milestone M0).

Reads the app's signed, hash-chained ledger (Documents/decisions/decision_ledger.jsonl), verifies every hash and
Ed25519 signature, folds amendment lines (kind=outcome / split_rating) into their decisions, and writes three outputs:

  finetune/sft.jsonl          chat-style SFT pairs: card context -> the human's decision
  finetune/preference.jsonl   chosen vs rejected where the human changed the agent's pick (outcome-aware)
  sharpness/spot_checks.jsonl every signed M3 spot-check (human call vs AI pick vs outcome)
  dials/dial_changes.jsonl    every signed earned-autonomy move / demotion / revert (M2), with reason + evidence refs
  rl/rewards.jsonl            outcome-graded reward (+1 / -1; null when no outcome is known). split rating is an
                              auxiliary field only and is NEVER added into `reward` (plan non-negotiable 2)
  replay/<name>/cases.jsonl   frozen, blinded replay set (only decisions with a known outcome; no human label, no outcome)
  replay/<name>/answers.jsonl the held-out labels/outcomes, keyed by case id
  replay/<name>/manifest.json sha256 of both files, counts, frozen_at — any edit is detectable
  summary.json

Old logs keep working: --legacy routing_log.jsonl converts pre-M0 RoutingDecision lines into the same shape, marked
provenance=legacy_unsigned (not part of the signed chain).

Usage: python3 tools/unified_export.py decision_ledger.jsonl -o out_dir [--legacy routing_log.jsonl] [--replay-name NAME] [--strict]
"""
from __future__ import annotations

import argparse
import base64
import collections
import datetime as dt
import hashlib
import json
import os
import sys

GENESIS = "0" * 64
SFT_SYSTEM = ("You are the AI half of a human/AI decision partnership. Given a decision card (context, the agent's proposal, "
              "options) reply with the decision the human in the middle would make, as JSON {\"decision\": <label>, \"answer\": <option>}.")


def canonical(rec: dict) -> bytes:
    body = {k: v for k, v in rec.items() if k not in ("ledger_hash", "signature")}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def verify(recs):
    """Return (ok, problems). Checks prev links, sha256 of the canonical body, and the Ed25519 signature over the hash."""
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.exceptions import InvalidSignature
    except Exception:  # pragma: no cover
        Ed25519PublicKey = None
    probs, prev = [], GENESIS
    for i, r in enumerate(recs, 1):
        if r.get("ledger_prev") != prev:
            probs.append(f"line {i}: prev mismatch")
        h = hashlib.sha256(canonical(r)).hexdigest()
        if h != r.get("ledger_hash"):
            probs.append(f"line {i}: hash mismatch")
        if Ed25519PublicKey is None:
            probs.append("cryptography not installed: signatures NOT checked")
        else:
            try:
                Ed25519PublicKey.from_public_bytes(base64.b64decode(r["signer_pub"])).verify(
                    base64.b64decode(r["signature"]), r["ledger_hash"].encode())
            except (InvalidSignature, KeyError, ValueError, TypeError):
                probs.append(f"line {i}: bad signature")
        prev = r.get("ledger_hash")
    return (not probs), probs


def fold(recs):
    """Decisions with their latest outcome / split rating applied from amendment lines."""
    dec = collections.OrderedDict()
    for r in recs:
        if r.get("kind") == "decision":
            d = dict(r); d.setdefault("provenance", "signed_ledger"); dec[r["id"]] = d
    for r in recs:
        k, ref = r.get("kind"), r.get("ref_id")
        if ref not in dec:
            continue
        if k == "outcome" and r.get("outcome"):
            dec[ref]["outcome"] = r["outcome"]
        elif k == "split_rating" and r.get("split_rating"):
            dec[ref]["split_rating"] = r["split_rating"]
    return list(dec.values())


GESTURE_LABEL = {"pass": "pass", "flip": "flip", "escalate": "escalate"}


def from_legacy(d: dict) -> dict:
    """pre-M0 RoutingDecision line -> unified shape (unsigned)."""
    label = "new_category" if d.get("newCategoryCreated") else GESTURE_LABEL.get(d.get("gesture"), "modify" if d.get("changed") else "pass")
    if label == "pass" and d.get("changed"):
        label = "modify"
    gt = d.get("groundTruth")
    dom = {"ai_doc_review": "ai_tele_doc"}.get(d.get("domain"), d.get("domain"))
    payload = dict(d.get("context") or {}); payload["displayLine"] = d.get("displayLine", ""); payload["history"] = d.get("history", "")
    return {"schema": "sdr.decision.v1", "kind": "decision", "id": f"legacy-{d.get('id')}", "timestamp": d.get("decidedAt"),
            "domain": dom, "context_id": f"{d.get('domain')}/{d.get('siteId')}", "dial_snapshot": None, "generation": 0,
            "card_payload": payload, "question": d.get("question"), "options": d.get("options"),
            "agent_proposal": {"answer": d.get("proposedAnswer"), "confidence": d.get("proposedConfidence")},
            "human_decision": {"label": label, "answer": d.get("routedAnswer"), "gesture": d.get("gesture"),
                               "changed": d.get("changed"), "decided_by": d.get("decidedBy") or "human"},
            "split_rating": None, "latency_ms": int(round((d.get("latency") or 0) * 1000)),
            "escalation_flags": [x for x in [d.get("hardTrigger")] if x],
            "outcome": {"value": gt, "source": "legacy_groundTruth (synthetic simulator)", "observed_at": d.get("decidedAt")} if gt else None,
            "item_id": d.get("itemId"), "link_id": d.get("linkId"), "legacy_id": d.get("id"), "provenance": "legacy_unsigned"}


def card_text(r):
    p = r.get("card_payload") or {}
    lines = [f"[{r['domain']} · context {r.get('context_id')} · gen {r.get('generation', 0)}]"]
    if r.get("dial_snapshot"):
        ds = r["dial_snapshot"]
        lines.append("Dials: deference {deference}, detail {detail_absorption}, challenge {challenge}, autonomy {autonomy_horizon} ({source})".format(**ds))
    for k in sorted(p):
        if k not in ("demo_split", "symbiosis", "showCapacity"):
            lines.append(f"{k}: {p[k]}")
    ap = r.get("agent_proposal") or {}
    lines.append(f"Question: {r.get('question')}")
    lines.append(f"Options: {', '.join(r.get('options') or [])}")
    lines.append(f"Agent proposal: {ap.get('answer')} (confidence {ap.get('confidence')})")
    if r.get("escalation_flags"):
        lines.append(f"Escalation flags: {', '.join(r['escalation_flags'])}")
    return "\n".join(lines)


def meta(r):
    return {k: r.get(k) for k in ("id", "domain", "context_id", "generation", "provenance", "split_rating", "card_hash", "ledger_hash")} | {
        "outcome_source": (r.get("outcome") or {}).get("source")}


def reward(r):
    o, h = r.get("outcome"), r.get("human_decision") or {}
    if not o or o.get("value") is None:
        return None
    return 1.0 if o["value"] == h.get("answer") else -1.0


def export(decisions, out, replay_name):
    os.makedirs(os.path.join(out, "finetune"), exist_ok=True)
    os.makedirs(os.path.join(out, "rl"), exist_ok=True)
    rdir = os.path.join(out, "replay", replay_name); os.makedirs(rdir, exist_ok=True)
    sft, pref, rl, cases, answers = [], [], [], [], []
    for r in decisions:
        h, ap = r.get("human_decision") or {}, r.get("agent_proposal") or {}
        user = card_text(r)
        sft.append({"messages": [{"role": "system", "content": SFT_SYSTEM}, {"role": "user", "content": user},
                                 {"role": "assistant", "content": json.dumps({"decision": h.get("label"), "answer": h.get("answer")})}],
                    "weight": 2.0 if h.get("changed") else 1.0, "metadata": meta(r)})
        if h.get("changed") and ap.get("answer") != h.get("answer"):
            o = (r.get("outcome") or {}).get("value")
            if o is not None and o == ap.get("answer"):
                chosen, rejected, src = ap.get("answer"), h.get("answer"), "outcome_says_agent_was_right"
            elif o is not None and o == h.get("answer"):
                chosen, rejected, src = h.get("answer"), ap.get("answer"), "outcome_confirms_human"
            elif o is not None:
                chosen, rejected, src = o, h.get("answer"), "outcome_differs_from_both"
            else:
                chosen, rejected, src = h.get("answer"), ap.get("answer"), "human_override_unverified"
            pref.append({"prompt": user, "chosen": chosen, "rejected": rejected, "label_source": src, "metadata": meta(r)})
        rw = reward(r)
        rl.append({"id": r["id"], "domain": r["domain"], "context_id": r.get("context_id"), "state": user,
                   "action": h.get("answer"), "decision_label": h.get("label"), "agent_proposal": ap.get("answer"),
                   "reward": rw, "reward_source": (r.get("outcome") or {}).get("source") if rw is not None else None,
                   "aux_split_rating": r.get("split_rating"), "aux_note": "auxiliary only; never summed into reward",
                   "dial_snapshot": r.get("dial_snapshot"), "latency_ms": r.get("latency_ms"), "provenance": r.get("provenance")})
        if rw is not None:
            cid = hashlib.sha256(r["id"].encode()).hexdigest()[:16]
            cases.append({"case_id": cid, "domain": r["domain"], "context_id": r.get("context_id"), "card": user,
                          "options": r.get("options"), "agent_proposal": ap.get("answer")})
            answers.append({"case_id": cid, "human_answer": h.get("answer"), "human_label": h.get("label"),
                            "outcome": r["outcome"]["value"], "outcome_source": r["outcome"].get("source"),
                            "split_rating": r.get("split_rating"), "source_id": r["id"]})

    def dump(path, rows):
        with open(path, "w", encoding="utf-8") as f:
            for x in rows:
                f.write(json.dumps(x, ensure_ascii=False, sort_keys=True) + "\n")
        return hashlib.sha256(open(path, "rb").read()).hexdigest()

    dump(os.path.join(out, "finetune", "sft.jsonl"), sft)
    dump(os.path.join(out, "finetune", "preference.jsonl"), pref)
    dump(os.path.join(out, "rl", "rewards.jsonl"), rl)
    hc = dump(os.path.join(rdir, "cases.jsonl"), cases)
    ha = dump(os.path.join(rdir, "answers.jsonl"), answers)
    manifest = {"name": replay_name, "frozen_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "cases": len(cases), "cases_sha256": hc, "answers_sha256": ha, "blinded": True,
                "note": "cases.jsonl carries no human label and no outcome; answers.jsonl is held out for champion-vs-challenger scoring",
                "domains": dict(collections.Counter(c["domain"] for c in cases))}
    json.dump(manifest, open(os.path.join(rdir, "manifest.json"), "w"), indent=2)
    return {"sft": len(sft), "preference": len(pref), "rl_rows": len(rl),
            "rl_rows_with_reward": sum(1 for x in rl if x["reward"] is not None), "replay_cases": len(cases)}


def verify_replay(rdir):
    m = json.load(open(os.path.join(rdir, "manifest.json")))
    ok = all(hashlib.sha256(open(os.path.join(rdir, f), "rb").read()).hexdigest() == m[k]
             for f, k in (("cases.jsonl", "cases_sha256"), ("answers.jsonl", "answers_sha256")))
    return ok


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ledger", nargs="?")
    ap.add_argument("-o", "--out", default="unified_out")
    ap.add_argument("--legacy", action="append", default=[], help="pre-M0 routing_log.jsonl (repeatable)")
    ap.add_argument("--replay-name", default=None)
    ap.add_argument("--strict", action="store_true", help="exit 2 if the chain or any signature fails")
    a = ap.parse_args(argv)
    recs = load_jsonl(a.ledger) if a.ledger else []
    ok, probs = verify(recs) if recs else (True, [])
    decisions = fold(recs)
    seen = {d.get("legacy_id") for d in decisions}
    dup = 0
    for lp in a.legacy:
        for d in load_jsonl(lp):
            if d.get("id") in seen:   # already in the signed ledger (post-M0 decisions are dual-written)
                dup += 1; continue
            decisions.append(from_legacy(d))
    name = a.replay_name or "replay-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    counts = export(decisions, a.out, name)
    dial = [r for r in recs if r.get("kind") == "dial_change"]
    os.makedirs(os.path.join(a.out, "dials"), exist_ok=True)
    with open(os.path.join(a.out, "dials", "dial_changes.jsonl"), "w", encoding="utf-8") as f:
        for r in dial:
            f.write(json.dumps({k: r.get(k) for k in ("id", "timestamp", "domain", "context_id", "generation", "dial_before", "dial_after",
                                                    "reason", "evidence_refs", "posterior", "escalation_flags", "ledger_hash")},
                               ensure_ascii=False, sort_keys=True) + "\n")
    counts["dial_changes"] = len(dial)
    # M3: sharpness spot-checks (AI hidden, human called first); later outcome lines are folded in
    outs = {r.get("ref_id"): r.get("outcome") for r in recs if r.get("kind") == "outcome"}
    spots = []
    for r in recs:
        if r.get("kind") != "spot_check":
            continue
        sc = dict(r.get("spot_check") or {})
        if sc.get("outcome") is None and outs.get(r.get("ref_id")):
            sc["outcome"] = outs[r["ref_id"]].get("value")
            sc["human_correct"] = sc["outcome"] == sc.get("human_call")
            sc["agent_correct"] = sc["outcome"] == sc.get("agent_pick")
        spots.append({"id": r.get("id"), "decision_id": r.get("ref_id"), "timestamp": r.get("timestamp"), "domain": r.get("domain"),
                      "context_id": r.get("context_id"), "generation": r.get("generation"), **sc, "ledger_hash": r.get("ledger_hash")})
    os.makedirs(os.path.join(a.out, "sharpness"), exist_ok=True)
    with open(os.path.join(a.out, "sharpness", "spot_checks.jsonl"), "w", encoding="utf-8") as f:
        for row in spots:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    counts["spot_checks"] = len(spots)
    s = {"legacy_skipped_duplicates": dup, "ledger_lines": len(recs), "chain_ok": ok, "problems": probs[:20], "decisions": len(decisions),
         "by_domain": dict(collections.Counter(d["domain"] for d in decisions)),
         "by_kind": dict(collections.Counter(r.get("kind") for r in recs)),
         "by_provenance": dict(collections.Counter(d.get("provenance") for d in decisions)),
         "with_outcome": sum(1 for d in decisions if d.get("outcome")),
         "outcome_sources": dict(collections.Counter((d.get("outcome") or {}).get("source") for d in decisions if d.get("outcome"))),
         "with_split_rating": sum(1 for d in decisions if d.get("split_rating")), "outputs": counts, "replay": name}
    os.makedirs(a.out, exist_ok=True)
    json.dump(s, open(os.path.join(a.out, "summary.json"), "w"), indent=2)
    print(json.dumps(s, indent=2))
    if a.strict and not ok:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
