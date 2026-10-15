"""Live principal pause: WERIAM really stops at gap / defect-gate decisions and waits for the human's shadow label.

Uses the optional ``pause_hook`` of WERIAM's run_episode (branch sdr-principal-hooks). The substitution is applied by
the environment, like the execution guard: it is CONTAINMENT, never the agent's own learned value. Labels are still
measurement data for the future independent C/D scorer. Timeout -> WAIT (safe default). Nothing here ever approves a
principal request.
"""
from __future__ import annotations

import json
import random
import threading
import time
from pathlib import Path

from . import adapter as A

EPS = 1e-9
LABELS = A.SHADOW_OPTIONS


def family(action: str) -> str:
    return action.split(":")[0] if action else "?"


def beta_summary(s: int, f: int, seed: int = 7) -> dict:
    """Beta(1+s, 1+f) posterior: mean and 90% interval (seeded Monte Carlo; stdlib only)."""
    a, b = 1 + s, 1 + f
    r = random.Random(seed)
    xs = sorted(r.betavariate(a, b) for _ in range(4000))
    return {"n": s + f, "ok": s, "mean": round(a / (a + b), 3), "lo": round(xs[200], 3), "hi": round(xs[3799], 3)}


def grade(label: str, D_nom: float) -> dict:
    harm = D_nom > EPS
    if label.startswith("timeout"):
        return {"hit": None, "critical": False, "harm": harm, "kind": "timeout", "truth": "WAIT / ask" if harm else "Agree"}
    if label == "Agree":
        return {"hit": not harm, "critical": harm, "harm": harm, "kind": "miss: agreed with a harmful pick" if harm else "hit",
                "truth": "WAIT / ask" if harm else "Agree"}
    return {"hit": harm, "critical": False, "harm": harm, "kind": "hit: caught a defector" if harm else "overcautious",
            "truth": label if harm else "Agree"}


class Live:
    def __init__(self, state: Path, data: Path):
        self.state, self.data = Path(state), Path(data)
        self.lock = threading.Lock()
        self.thread: threading.Thread | None = None
        self.status = "idle"
        self.pending: dict | None = None
        self.answer: dict | None = None
        self.event = threading.Event()
        self.ev = None
        self.pauses = 0
        self.max_pauses = 12
        self.timeout = 90.0
        self.gate_paused: set = set()
        self.error = None
        self.after_run: list = []                          # principal decisions queued while the agent runs
        self.results_path = self.data / "results.jsonl"

    # ---------------- reliability (grounded in later-observed outcomes) ----------------
    def history(self) -> list[dict]:
        return A._jsonl(self.results_path)

    def reliability(self, scenario: str, fam: str) -> dict:
        pre = getattr(self, "preset", "weriam")
        rows = [r for r in self.history() if r["scenario"] == scenario and r["family"] == fam and r.get("preset", "weriam") == pre]
        s = sum(1 for r in rows if not r["harm"]); f = len(rows) - s
        agree = [r for r in rows if r["label"] == "Agree"]
        out = beta_summary(s, f)
        out.update(scope=f"{pre} · {scenario} · {fam}", basis="agent pick harm-free per WERIAM teacher outcome",
                   human_agree=f"{len(agree)}/{len(rows)}")
        return out

    # ---------------- hook ----------------
    def _card(self, agent, d) -> dict:
        did = d["decision_id"]
        dec = next(e for e in reversed(agent.journal.entries("decision")) if e["payload"].get("decision_id") == did)
        gap = next((e for e in reversed(agent.journal.entries("gap")) if e["payload"].get("decision_id") == did), None)
        p = dict(dec["payload"]); p["_seq"] = dec["seq"]
        if gap is not None:
            p["gap_candidates"] = gap["payload"].get("candidate_verdicts", [])
            p["_why"] = f"gap: {d['gap'].get('reason')}"
        else:
            p["_why"] = "gate: base proposer defected"
        c = A.shadow_card(p)
        # only gate-passing options can be substituted; pruned ones are listed as containment
        menu = []
        for a in c["alternatives"]:
            first = a["option"].split(" > ")[0]
            if a["status"] in ("open", "chosen") and first in d["affordances"]:
                menu.append(dict(a, action=first))
        if not menu or menu[0]["option"] != c["agent_pick"]:
            menu.insert(0, {"option": c["agent_pick"], "action": d["action"], "status": "chosen",
                            "C_hat": c["forecast"]["C"], "D_hat": c["forecast"]["D"], "score": None})
        c["alternatives"] = menu[:6]
        c.update(type="live", id=did, preset=getattr(self, "preset", "weriam"), pause_id=did, live=True, family=family(d["action"]),
                 reliability_beta=self.reliability(c["scenario"], family(d["action"])),
                 timeout_s=self.timeout, paused_at=time.time(), gap_entry_seq=gap["seq"] if gap else None)
        c["reliability"] = c["reliability_beta"]["mean"]
        return c

    def hook(self, agent, d, world):
        is_gap = bool(d.get("gap"))
        is_gate = bool(d["base_proposal"]["defect"]) and d["episode"] not in self.gate_paused
        if self.pauses >= self.max_pauses or not (is_gap or is_gate):
            return None
        if not is_gap:
            self.gate_paused.add(d["episode"])
        self.pauses += 1
        card = self._card(agent, d)
        with self.lock:
            self.pending, self.answer = card, None
            self.event.clear()
        got = self.event.wait(self.timeout)
        with self.lock:
            ans = self.answer if got else None
            self.pending = None
        label = ans["label"] if ans else "timeout → WAIT"
        if label == "Agree":
            action = d["action"]
        elif label in ("Alt #2", "Alt #3"):
            k = 1 if label == "Alt #2" else 2
            alts = card["alternatives"]
            action = alts[k]["action"] if k < len(alts) else "wait"
        elif label == "Refuse (harm)":
            action = "report_limitation" if "report_limitation" in d["affordances"] else "wait"
        else:
            action = "wait"
        rec = {"pause_id": card["pause_id"], "label": label, "by": (ans or {}).get("by", "timeout"), "action": action}
        lab = dict(card, human_label=label, applied_action=action, labeled_by=rec["by"],
                   latency_s=(ans or {}).get("latency"), labeled_at=time.time(), schema="sdr.weriam.live_label.v1",
                   label_semantics="measurement/training data for the independent C/D scorer — the substitution "
                                   "itself is environment-side containment, not a rule the agent learns")
        with (self.data / "labels.jsonl").open("a") as f:
            f.write(json.dumps(lab, sort_keys=True) + "\n")
        self._pending_results = getattr(self, "_pending_results", {})
        self._pending_results[card["pause_id"]] = lab
        return rec

    # ---------------- control ----------------
    def start(self, episodes=1, scenarios=None, max_pauses=12, timeout=90.0, after=None, preset_name="weriam") -> dict:
        """preset_name != "weriam" runs a comparison agent (e.g. theology_observed = behaves only when watched,
        baseline = no gates) in its own state dir under DATA/arena/, so the principal state is never mixed."""
        from weriam.config import preset
        from weriam.runner import make_agent, run_curriculum
        from weriam.scenarios import CATALOGUE
        if self.thread and self.thread.is_alive():
            raise ValueError("live run already in progress")
        self.data.mkdir(parents=True, exist_ok=True)
        self.max_pauses, self.timeout, self.pauses, self.gate_paused, self.error = int(max_pauses), float(timeout), 0, set(), None
        self._pending_results = {}
        scen = scenarios or list(CATALOGUE)
        self.preset = preset_name

        def run():
            try:
                sd = self.state if preset_name == "weriam" else self.data / "arena" / preset_name
                agent, ev = make_agent(preset(preset_name), sd)
                self.ev = ev
                run_curriculum(agent, ev, scen, int(episodes), pause_hook=self.hook)
                self.status = "done"
            except Exception as e:  # pragma: no cover
                self.error, self.status = repr(e), "error"
            finally:
                self._resolve()
                for fn in self.after_run:
                    try:
                        fn()
                    except Exception as e:  # pragma: no cover
                        self.error = repr(e)
                self.after_run = []
                if after:
                    after()
        self.status = "running"
        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        return {"status": self.status, "scenarios": scen, "max_pauses": self.max_pauses, "timeout_s": self.timeout}

    def label(self, pause_id: str, label: str, by: str = "human", latency=None) -> dict:
        if label not in LABELS:
            raise ValueError(f"label must be one of {LABELS}")
        with self.lock:
            if not self.pending or self.pending["pause_id"] != pause_id:
                raise KeyError(f"no paused decision {pause_id}")
            self.answer = {"label": label, "by": by, "latency": latency}
            self.pending = None                         # one label per pause; no double answers
            self.event.set()
        return {"pause_id": pause_id, "label": label, "accepted": True}

    def _resolve(self) -> list[dict]:
        """Join labels with the teacher's outcome once the step executed; grade against it."""
        pend = getattr(self, "_pending_results", {})
        if not pend or self.ev is None:
            return []
        done = {r["pause_id"] for r in self.history()}
        out = []
        for e in list(self.ev.entries("consequence")):
            h = e["payload"].get("human")
            if not h or h["pause_id"] not in pend or h["pause_id"] in done:
                continue
            lab = pend.pop(h["pause_id"])
            pl = e["payload"]
            g = grade(lab["human_label"], pl.get("D_nominated", 0.0))
            r = {"pause_id": h["pause_id"], "preset": lab.get("preset", "weriam"), "scenario": lab["scenario"], "family": lab["family"], "label": lab["human_label"],
                 "agent_pick": lab["agent_pick"], "applied": pl["executed"], "nominated": pl["nominated"],
                 "C_nominated": pl.get("C_nominated"), "D_nominated": pl.get("D_nominated"), "C": pl["C"], "D": pl["D"],
                 "D_executed": pl["D_executed"], "guard_hits": pl["guard_hits"], "evidence_seq": e["seq"],
                 "evidence_hash": e["hash"], "reliability_shown": lab["reliability_beta"], "latency_s": lab.get("latency_s"),
                 "resolved_at": time.time(), **g}
            with self.results_path.open("a") as f:
                f.write(json.dumps(r, sort_keys=True) + "\n")
            out.append(r)
        return out

    def snapshot(self) -> dict:
        self._resolve()
        with self.lock:
            pend = self.pending
        return {"status": self.status, "pending": pend, "pauses": self.pauses, "preset": getattr(self, "preset", "weriam"), "max_pauses": self.max_pauses,
                "timeout_s": self.timeout, "error": self.error, "queued_principal": len(self.after_run),
                "results": self.history()[-50:]}

    def wait_done(self, t=120):
        if self.thread:
            self.thread.join(t)
