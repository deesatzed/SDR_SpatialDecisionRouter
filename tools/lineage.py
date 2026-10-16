#!/usr/bin/env python3
"""M5 lineage markdown from the signed ledger (mirror of SpatialDecisionRouter/Core/Lineage.swift).

Per area: champion generations, promotions / rollbacks / discarded candidates (reasons + replay results), dial changes (why +
evidence), spot-check calibration, override-held-up rate, critical misses / demotions, and per-line signature + chain status.
Called by tools/unified_export.py (lineage/<area>.md); standalone: python3 tools/lineage.py decision_ledger.jsonl [-o dir]
"""
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unified_export as ux

ESCALATE = {"Escalate", "escalate", "escalate to security"}


def post(s, f):
    a, b = 1 + s, 1 + f; m = a / (a + b); sd = (a * b / ((a + b) ** 2 * (a + b + 1))) ** 0.5
    return {"successes": s, "n": s + f, "mean": round(m, 3), "lo": round(max(0, m - 1.645 * sd), 3), "hi": round(min(1, m + 1.645 * sd), 3)}


def line_status(recs):
    """verified | chain break here | bad signature | after chain break (line N) — per line, one verify pass"""
    _, probs = ux.verify(recs)
    first = {}
    for p in probs:
        if p.startswith("line "):
            n = int(p.split()[1].rstrip(":")); first.setdefault(n, p)
    if not first:
        return ["verified"] * len(recs)
    b = min(first)
    return ["verified" if i < b else ("bad signature" if "signature" in first[b] else "chain break here") if i == b else f"after chain break (line {b})"
            for i in range(1, len(recs) + 1)]


def build(area, recs):
    st = line_status(recs)
    outs = {r.get("ref_id"): (r.get("outcome") or {}).get("value") for r in recs if r.get("kind") == "outcome"}
    ev, champ, champ_gen, dial_gen = [], [], 0, 0
    c = {"decisions": 0, "graded": 0, "critical": 0, "demotions": 0}
    sk = sn = ok = on = 0
    for i, r in enumerate(recs):
        if r.get("domain") != area: continue
        k = r.get("kind")
        add = lambda kind, title, detail, evid: ev.append({"line": i + 1, "id": r["id"], "time": r.get("timestamp"), "kind": kind, "title": title,
                                                           "detail": detail, "evidence": evid or [], "status": st[i], "hash": r.get("ledger_hash", ""),
                                                           "champion_generation": champ_gen, "dial_generation": dial_gen})
        if k == "decision":
            c["decisions"] += 1
            o = outs.get(r["id"]) or (r.get("outcome") or {}).get("value")
            if o is not None:
                c["graded"] += 1
                ap, h = r.get("agent_proposal") or {}, r.get("human_decision") or {}
                severe = bool(r.get("escalation_flags")) or o in ESCALATE or (r.get("card_payload") or {}).get("severity") == "critical"
                if ap.get("answer") is not None and ap["answer"] != o and severe:
                    c["critical"] += 1; add("critical_miss", "Critical miss", f"agent {ap.get('answer')} · outcome {o} · human {h.get('answer')}", [r["id"]])
                if h.get("changed"):
                    on += 1; ok += h.get("answer") == o
        elif k == "dial_change":
            dial_gen = r.get("generation", dial_gen)
            demo = "demotion" in (r.get("escalation_flags") or []); rev = (r.get("reason") or "").startswith("REVERT")
            c["demotions"] += demo
            add("demotion" if demo else "revert" if rev else "dial_change", "Dial move", r.get("reason") or "", r.get("evidence_refs"))
        elif k == "spot_check":
            sc = r.get("spot_check") or {}; o = sc.get("outcome") or outs.get(r.get("ref_id"))
            if o is not None: sn += 1; sk += o == sc.get("human_call")
            add("spot_check", f"Spot-check · you {sc.get('human_call')} · AI {sc.get('agent_pick')} · outcome {o or 'pending'}", sc.get("trigger", ""), [r.get("ref_id")])
        elif k == "policy_proposal":
            add(k, "Critic proposes", json.dumps((r.get("promo") or {}).get("rule"), ensure_ascii=False), r.get("evidence_refs"))
        elif k == "policy_evaluation":
            p = r.get("promo") or {}; m = p.get("metrics") or {}
            add("evaluation_passed" if p.get("verdict") == "passed" else "discarded", "Beats champion" if p.get("verdict") == "passed" else "Discarded",
                f"replay n={m.get('n')} {m.get('champion_correct')}→{m.get('candidate_correct')} Δ {m.get('accuracy_delta')} · " + "; ".join(p.get("reasons") or []), [r.get("ref_id")])
        elif k == "principal_decision":
            add(k, f"Principal · {(r.get('promo') or {}).get('decision')}", "", [r.get("ref_id")])
        elif k in ("promotion", "rollback"):
            p = r.get("promo") or {}; champ_gen = p.get("champion_generation", champ_gen); champ = p.get("rules_after") or []
            add(k, f"{'PROMOTED' if k == 'promotion' else 'ROLLBACK'} → champion gen {champ_gen}", r.get("reason") or "", r.get("evidence_refs"))
    return {"area": area, "lines": len(recs), "chain_ok": all(s == "verified" for s in st), "events": ev, "counts": c,
            "sharpness": post(sk, sn - sk) if sn else None, "overrides": post(ok, on - ok) if on else None,
            "champion": champ, "champion_generation": champ_gen, "dial_generation": dial_gen}


def markdown(L):
    p = lambda x: f"{x['successes']}/{x['n']} · mean {x['mean']} [{x['lo']}–{x['hi']}]" if x else "none yet"
    c = L["counts"]
    s = f"# Lineage · {L['area']}\n\nReconstructed from the signed ledger · {L['lines']} lines · chain {'✓ verified' if L['chain_ok'] else '✗ broken'}\n\n"
    s += "## Summary\n\n"
    s += f"- Champion generation: {L['champion_generation']} · rules: {len(L['champion'])}\n- Dial generation: {L['dial_generation']}\n"
    s += f"- Decisions: {c['decisions']} (outcome-graded {c['graded']}) · critical misses: {c['critical']} · demotions: {c['demotions']}\n"
    s += f"- Sharpness (spot-checks): {p(L['sharpness'])}\n- Overrides held up: {p(L['overrides'])}\n\n"
    s += "## Timeline\n\n| line | time | event | detail | evidence | signature |\n|---:|---|---|---|---|---|\n"
    esc = lambda x: str(x).replace("|", "\\|").replace("\n", " ")
    for e in L["events"]:
        s += f"| {e['line']} | {e['time']} | {esc(e['title'])} | {esc(e['detail'])} | {' '.join(str(x)[:8] for x in e['evidence'] if x)} | {'✓' if e['status'] == 'verified' else '✗ ' + e['status']} {e['hash'][:10]} |\n"
    return s


def areas(recs):
    return sorted({r["domain"] for r in recs if str(r.get("domain", "")).startswith("symbiosis:")})


def write_all(recs, out):
    os.makedirs(out, exist_ok=True); res = {}
    for a in areas(recs):
        L = build(a, recs)
        open(os.path.join(out, a.replace(":", "_") + ".md"), "w", encoding="utf-8").write(markdown(L)); res[a] = len(L["events"])
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("ledger"); ap.add_argument("-o", default="lineage"); a = ap.parse_args()
    print(json.dumps(write_all(ux.load_jsonl(a.ledger), a.o), indent=1))
