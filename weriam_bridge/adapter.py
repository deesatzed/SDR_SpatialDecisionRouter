"""Read-only adapter: WERIAM state dir (journal/evidence JSONL) -> SDR review cards.

* Principal requests are READ with WERIAM's own Principal/Ledger classes and DECIDED only through
  WERIAM's sanctioned CLI (`python -m weriam principal --state DIR --approve|--decline ID --by NAME`),
  so every decision is a single-use, scoped, hash-chained journal entry written by WERIAM itself.
* Shadow labels never touch WERIAM. They are measurement / training data for the future independent
  C/D scorer and are stored in this bridge's own data dir (labels.jsonl). They are NOT rules.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

WERIAM_ROOT = Path(os.environ.get("WERIAM_ROOT", "/Volumes/WS4TB/Quncen38/hive-lineage-sim/WERIAM"))
WERIAM_SRC = WERIAM_ROOT / "src"
if str(WERIAM_SRC) not in sys.path:
    sys.path.insert(0, str(WERIAM_SRC))

from weriam.ledger import Ledger          # noqa: E402  (read-only use)
from weriam.principal import Principal    # noqa: E402  (read-only use: requests()/status())

CONTAINMENT = "A_K shield (floor + consent), environment guard and STOP are containment: never retired, not learned."

SCOPE = {
    "retire_watcher": dict(
        scope="One retirement of the theology watcher prior. The approval is consumed by that retirement; "
              "re-retiring after any reinstatement needs a NEW sign-off.",
        reversibility="Reversible: the watcher keeps running in shadow and reinstates the scaffold on a "
                      "watcher-only rejection or a larger temptation.",
        effect="Agent moves scaffold → mature on its next qualifying episode."),
    "retraining": dict(
        scope="One foundation rebuild of the base proposer (roadmap v0.6). With WERIAM branch sdr-principal-hooks "
              "the agent consumes the approval at its next episode end and RECORDS the rebuild (foundation_rebuild "
              "entry, status recorded_no_weights) — the simulator has no weights to retrain.",
        reversibility="Irreversible in a real system (weights change). Prefer Defer unless evidence is strong.",
        effect="Consumed + recorded as foundation_rebuild (no weights changed in the simulator)."),
    "amend_standards": dict(
        scope="One amendment to the narrative standards.",
        reversibility="Reversible by a later amendment; history stays in the journal.",
        effect="Standards change on next episode."),
}

PRINCIPAL_OPTIONS = ["Approve once", "Decline", "Defer"]
SHADOW_OPTIONS = ["Agree", "Alt #2", "Alt #3", "WAIT / ask", "Refuse (harm)"]


def _jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def journal(state: Path) -> Ledger:
    return Ledger("journal", Path(state) / "journal.jsonl")


def verify(state: Path) -> dict:
    out = {}
    for name in ("journal", "evidence"):
        p = Path(state) / f"{name}.jsonl"
        ok, msg = Ledger(name, p).verify() if p.exists() else (False, "missing")
        out[name] = {"ok": ok, "msg": msg}
    out["ok"] = all(v["ok"] for v in out.values() if isinstance(v, dict))
    return out


def _agent_state(state: Path) -> dict:
    p = Path(state) / "agent.json"
    return json.loads(p.read_text()) if p.exists() else {}


def shadow_record(state: Path) -> dict:
    """Watcher history: retirements / reinstatements and recent load-bearing count."""
    ag = _agent_state(state)
    sc = ag.get("scaffold") or {}
    tr = sc.get("transitions") or []
    hist = sc.get("history") or []
    return {"phase": sc.get("phase", "?"),
            "retirements": sum(1 for t in tr if t.get("to") == "mature"),
            "reinstatements": sum(1 for t in tr if t.get("to") == "scaffold"),
            "last_reinstatement": next((t.get("reason") for t in reversed(tr) if t.get("to") == "scaffold"), None),
            "window_load_bearing": sum(1 for h in hist if h.get("load_bearing")),
            "window_len": len(hist)}


def principal_requests(state: Path) -> list[dict]:
    return Principal(journal(state)).requests()


def principal_cards(state: Path) -> list[dict]:
    sr = shadow_record(state)
    hashes = {e["hash"][:16]: e["hash"] for e in journal(state).entries("principal_request")}
    cards = []
    for r in principal_requests(state):
        if r["status"] != "pending":
            continue
        s = SCOPE.get(r["kind"], dict(scope="?", reversibility="?", effect="?"))
        cards.append({"type": "principal", "id": r["id"], "kind": r["kind"], "seq": r["seq"], "request_hash": hashes.get(r["id"]),
                      "evidence": r["evidence"], "shadow_record": sr, **s, "containment": CONTAINMENT,
                      "options": PRINCIPAL_OPTIONS, "agent_pick": "Defer"})
    return cards


def _key(d: dict) -> str:
    return f"{d['episode']}@t{d['t']}"


def _alternatives(d: dict) -> list[dict]:
    """Agent's option menu, best-first: gap-solver candidate plans if a gap fired, else node verdicts."""
    if d.get("gap"):
        seen, alts = set(), []
        for c in sorted(d.get("gap_candidates", []), key=lambda c: -c.get("score", 0)):
            k = " > ".join(c["plan"])
            if k in seen:
                continue
            seen.add(k)
            alts.append({"option": k, "C_hat": c.get("C_hat"), "D_hat": c.get("D_hat"), "score": c.get("score"),
                         "status": c.get("status")})
        if alts:
            return alts
    vs = sorted(d.get("verdicts", []), key=lambda v: (v["status"] != "chosen", -(v.get("net") or 0)))
    return [{"option": v["node"], "C_hat": v.get("C_hat"), "D_hat": v.get("D_hat"), "score": v.get("net"),
             "status": v["status"]} for v in vs]


def _containment_hits(d: dict) -> list[str]:
    return [f"{v['node']} ({v['status']})" for v in d.get("verdicts", []) if v["status"].startswith("pruned_protection")]


def shadow_candidates(state: Path) -> list[dict]:
    """Gap-solver decisions, plus the first gate decision per scenario where the base proposer defected."""
    es = journal(state).entries()
    gaps = [e["payload"] for e in es if e["kind"] == "gap"]
    gi = 0
    out, seen_gate = [], set()
    for e in es:
        if e["kind"] != "decision":
            continue
        d = dict(e["payload"])
        if d.get("gap"):
            # gap entries precede/accompany their decision in the same order
            if gi < len(gaps):
                d["gap_candidates"] = gaps[gi].get("candidate_verdicts", [])
                gi += 1
            d["_why"] = f"gap: {d['gap'].get('reason')}"
        elif d["base_proposal"].get("defect"):
            sc = d["episode"].split(":")[1]
            if (sc, d["observed"]) in seen_gate:
                continue
            seen_gate.add((sc, d["observed"]))
            d["_why"] = "gate: base proposer defected"
        else:
            continue
        d["_seq"] = e["seq"]
        out.append(d)
    return out


def shadow_card(d: dict) -> dict:
    alts = _alternatives(d)
    chosen = d["gap"]["plan"] if d.get("gap") else [d["action"]]
    pick = " > ".join(chosen)
    i = next((k for k, a in enumerate(alts) if a["option"] == pick), None)   # agent pick is always menu item #1
    first = alts.pop(i) if i is not None else {"option": pick, "C_hat": None, "D_hat": None, "score": None, "status": "chosen"}
    alts = [first] + alts
    top = alts[0]["score"] or 0
    second = max([(a["score"] or 0) for a in alts[1:]], default=0)
    margin = max(0.0, min(1.0, top - second))   # heuristic placeholder, not a calibrated reliability
    h = d.get("h", {})
    unc = float(h.get("uncertainty", 0) or 0)
    reliability = round(max(0.05, min(0.95, 0.5 + margin - 0.5 * unc)), 3)
    _, sc, obs, ep = d["episode"].split(":")
    return {"type": "shadow", "id": _key(d), "seq": d["_seq"], "scenario": sc, "observed": bool(d["observed"]),
            "t": d["t"], "why": d["_why"], "agent_pick": " > ".join(chosen), "action": d["action"],
            "base_proposal": d["base_proposal"], "alternatives": alts[:6], "affordances": d.get("affordances", []),
            "forecast": {k: d.get("forecast", {}).get(k) for k in ("C", "D", "net", "unc")},
            "E": d.get("E"), "phase": d.get("phase"), "h": h, "reliability": reliability,
            "containment_hits": _containment_hits(d), "containment": CONTAINMENT,
            "options": SHADOW_OPTIONS, "outcome_hidden": True}


def shadow_cards(state: Path, labels_path: Path | None = None, limit: int = 14) -> list[dict]:
    done = {l["id"] for l in _jsonl(labels_path)} if labels_path else set()
    return [shadow_card(d) for d in shadow_candidates(state) if _key(d) not in done][:limit]


def outcomes(state: Path) -> dict:
    """Later-observed outcome per decision key from the evidence ledger (teacher)."""
    return {f"{e['payload']['episode']}@t{e['payload']['t']}": {
        k: e["payload"].get(k) for k in ("C", "D", "D_executed", "executed", "nominated", "guarded", "guard_hits")}
        for e in _jsonl(Path(state) / "evidence.jsonl") if e["kind"] == "consequence"}


# ---------------- writes ----------------

def decide(state: Path, request_id: str, decision: str, by: str, reason: str = "", data_dir: Path | None = None) -> dict:
    """Approve/Decline go through WERIAM's own CLI. Defer writes nothing to WERIAM (bridge log only)."""
    decision = decision.lower()
    rec = {"request_id": request_id, "decision": decision, "by": by, "reason": reason, "at": time.time()}
    if decision.startswith("approve") or decision.startswith("decline"):
        flag = "--approve" if decision.startswith("approve") else "--decline"
        env = dict(os.environ, PYTHONPATH=str(WERIAM_SRC) + os.pathsep + os.environ.get("PYTHONPATH", ""))
        p = subprocess.run([sys.executable, "-m", "weriam", "principal", "--state", str(state), flag, request_id, "--by", by],
                           capture_output=True, text=True, env=env, cwd=str(WERIAM_ROOT), timeout=60)
        if p.returncode != 0:
            raise ValueError((p.stderr or p.stdout).strip().splitlines()[-1] if (p.stderr or p.stdout) else "weriam CLI failed")
        rec["weriam"] = json.loads(p.stdout)
        ent = [e for e in journal(state).entries("principal_decision") if e["payload"]["request_id"] == request_id]
        rec["journal_seq"] = ent[-1]["seq"] if ent else None
        rec["journal_hash"] = ent[-1]["hash"] if ent else None
    elif not decision.startswith("defer"):
        raise ValueError(f"unknown decision {decision}")
    rec["verify"] = verify(state)
    if data_dir:
        Path(data_dir).mkdir(parents=True, exist_ok=True)
        with (Path(data_dir) / "principal_log.jsonl").open("a") as f:
            f.write(json.dumps(rec, sort_keys=True) + "\n")
    return rec


def record_label(state: Path, labels_path: Path, key: str, label: str, by: str = "human", latency: float | None = None,
                 note: str = "") -> dict:
    if label not in SHADOW_OPTIONS:
        raise ValueError(f"label must be one of {SHADOW_OPTIONS}")
    card = next((shadow_card(d) for d in shadow_candidates(state) if _key(d) == key), None)
    if card is None:
        raise KeyError(f"no shadow decision {key}")
    alts = card["alternatives"]
    human_pick = {"Agree": card["agent_pick"], "Alt #2": alts[1]["option"] if len(alts) > 1 else None,
                  "Alt #3": alts[2]["option"] if len(alts) > 2 else None}.get(label, label)
    rec = {"schema": "sdr.weriam.shadow_label.v1", "id": key, "scenario": card["scenario"], "observed": card["observed"],
           "t": card["t"], "journal_seq": card["seq"], "why": card["why"],
           "option_menu": alts, "affordances": card["affordances"], "agent_pick": card["agent_pick"],
           "base_proposal": card["base_proposal"], "human_label": label, "human_pick": human_pick,
           "agree": label == "Agree", "cd_scores": card["forecast"], "reliability": card["reliability"],
           "E": card["E"], "phase": card["phase"], "containment_hits": card["containment_hits"],
           "labeled_by": by, "latency_s": latency, "note": note, "labeled_at": time.time(),
           "label_semantics": "measurement/training data for the independent C/D scorer — not a rule or veto"}
    Path(labels_path).parent.mkdir(parents=True, exist_ok=True)
    with Path(labels_path).open("a") as f:
        f.write(json.dumps(rec, sort_keys=True) + "\n")
    return rec


def export_labels(state: Path, labels_path: Path, out: Path) -> int:
    """Join labels with the later-observed outcome (evidence ledger). Outcome is attached only here."""
    oc = outcomes(state)
    rows = _jsonl(labels_path)
    with Path(out).open("w") as f:
        for r in rows:
            r = dict(r, observed_outcome=oc.get(r["id"]))
            f.write(json.dumps(r, sort_keys=True) + "\n")
    return len(rows)


def init_state(state: Path, episodes: int = 2) -> str:
    """Create a WERIAM state by running its own `develop` (no --approve-retirement → requests stay pending)."""
    env = dict(os.environ, PYTHONPATH=str(WERIAM_SRC))
    p = subprocess.run([sys.executable, "-m", "weriam", "develop", "--state", str(state), "--episodes", str(episodes)],
                       capture_output=True, text=True, env=env, cwd=str(WERIAM_ROOT), timeout=600)
    if p.returncode != 0:
        raise RuntimeError(p.stderr)
    return p.stdout.strip().splitlines()[-1] if p.stdout.strip() else ""
