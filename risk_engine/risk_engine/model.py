"""Per-complaint discrete Bayesian networks (pyAgrum, exact LazyPropagation) + reliability, if-wrong, VOI, escalation."""
from itertools import product
import numpy as np
import pyagrum as gum

from .params import v, source_summary

YN = ["no", "yes"]


class EvidenceError(ValueError):
    pass


def noisy_or(base, incs):
    q = 1.0 - base
    for i in incs:
        q *= 1.0 - i
    return 1.0 - q


class RiskModel:
    """One BN per complaint. Node naming: <truth>, <truth>__rep, <truth>__<signal>, <truth>__ask, ctx_<c>, <plan_flag>, dx_<d>, critical."""

    def __init__(self, params, complaint):
        if complaint not in params["complaints"]:
            raise EvidenceError(f"unknown complaint {complaint!r}; known: {sorted(params['complaints'])}")
        self.p, self.name = params, complaint
        self.c = params["complaints"][complaint]
        self.truths = list(self.c["truths"])
        self.ctx = list(self.c.get("context", []))
        self.flags = list(self.c.get("plan_flags", []))
        self.crit_sev = v(params["thresholds"]["critical_severity"])
        self.states, self.cpt, self.order = {}, {}, []
        self._build()
        self.bn = gum.BayesNet(complaint)
        for n in self.order:
            self.bn.add(gum.LabelizedVariable(n, n, self.states[n]))
        for n in self.order:
            for par in self.cpt[n]["parents"]:
                self.bn.addArc(par, n)
        for n in self.order:
            pars, tab = self.cpt[n]["parents"], self.cpt[n]["table"]
            if not pars:
                self.bn.cpt(n).fillWith(tab[()])
            else:
                for key, probs in tab.items():
                    self.bn.cpt(n)[dict(zip(pars, key))] = probs

    # ---- construction ----
    def _node(self, name, states, parents, fn):
        self.states[name] = states
        par_states = [self.states[x] for x in parents]
        tab = {}
        for key in product(*par_states) if parents else [()]:
            probs = fn(dict(zip(parents, key)))
            s = sum(probs)
            if abs(s - 1.0) > 1e-9 or min(probs) < -1e-12:
                raise ValueError(f"bad CPT row for {name} {key}: {probs}")
            tab[key] = [max(0.0, x) for x in probs]
        self.cpt[name] = {"parents": list(parents), "table": tab}
        self.order.append(name)

    def risky(self, t, s):
        return s != self.p["truths"][t]["states"][0]

    def _build(self):
        P = self.p
        for c in self.ctx:
            pr = v(P["context_priors"][c]); self._node("ctx_" + c, YN, [], lambda _, pr=pr: [1 - pr, pr])
        for f in self.flags:
            pr = v(P["context_priors"][f]); self._node(f, YN, [], lambda _, pr=pr: [1 - pr, pr])
        for t in self.truths:
            T = P["truths"][t]; st = T["states"]; pr = T["prior"][self.name]
            if len(st) == 2:
                dist = [1 - v(pr), v(pr)]
            else:
                risky = [v(pr[s]) for s in st[1:]]; dist = [1 - sum(risky)] + risky
            self._node(t, st, [], lambda _, d=dist: d)
            rep = T["report"]
            cc = [c for c in rep.get("conceal_context", {}) if c in self.ctx]
            rc = [c for c in rep.get("recall_context", {}) if c in self.ctx]
            ctx_par = sorted(set(cc) | set(rc))

            def rep_fn(a, t=t, rep=rep, cc=cc, rc=rc):
                if not self.risky(t, a[t]):
                    fp = v(rep["false_positive"]); return [1 - fp, fp]
                conceal = noisy_or(v(rep["conceal_base"]), [v(rep["conceal_context"][c]) for c in cc if a["ctx_" + c] == "yes"])
                recall = noisy_or(v(rep["recall_miss"]), [v(rep["recall_context"][c]) for c in rc if a["ctx_" + c] == "yes"])
                pneg = noisy_or(conceal, [recall]); return [pneg, 1 - pneg]
            self._node(t + "__rep", ["neg", "pos"], [t] + ["ctx_" + c for c in ctx_par], rep_fn)
            for sig, sp in T.get("signals", {}).items():
                self._node(f"{t}__{sig}", YN, [t], lambda a, t=t, sp=sp: (
                    [1 - v(sp["p_if_true"]), v(sp["p_if_true"])] if self.risky(t, a[t]) else [1 - v(sp["p_if_false"]), v(sp["p_if_false"])]))
            ask = T["ask"]
            self._node(t + "__ask", ["neg", "pos"], [t], lambda a, t=t, ask=ask: (
                [1 - v(ask["reveal"]), v(ask["reveal"])] if self.risky(t, a[t]) else [1 - v(ask["false_positive"]), v(ask["false_positive"])]))
        self.dx = {}
        for dname, d in self.c["dx"].items():
            rows = {tuple(r["when"][x] for x in d["parents"]): v(r["p"]) for r in d["cpt"]}
            self._node("dx_" + dname, YN, list(d["parents"]), lambda a, d=d, rows=rows: (
                lambda pp: [1 - pp, pp])(rows[tuple(a[x] for x in d["parents"])]))
            self.dx[dname] = d
        crit = ["dx_" + k for k, d in self.dx.items() if d["severity"] >= self.crit_sev]
        self._node("critical", YN, crit, lambda a: [0.0, 1.0] if any(a[x] == "yes" for x in crit) else [1.0, 0.0])
        # critical misses that a plan change cannot mitigate (only escalation does) -> drives the escalation recommendation
        crit_esc = [x for x in crit if "modify" not in self.dx[x[3:]].get("mitigated_by", [])]
        self._node("critical_esc", YN, crit_esc, lambda a, ce=crit_esc: [0.0, 1.0] if any(a[x] == "yes" for x in ce) else [1.0, 0.0])

    # ---- evidence ----
    def evidence(self, req):
        allowed = {"complaint", "context", "plan_flags", "reports", "signals", "answers", "known", "seed", "encounter_id"}
        bad = set(req) - allowed
        if bad:
            raise EvidenceError(f"unknown request keys {sorted(bad)}")
        ev = {}
        for c, val in (req.get("context") or {}).items():
            if c not in self.ctx:
                raise EvidenceError(f"unknown context {c!r} for {self.name}; allowed {self.ctx}")
            if not isinstance(val, bool):
                raise EvidenceError(f"context {c} must be boolean")
            ev["ctx_" + c] = "yes" if val else "no"
        for f, val in (req.get("plan_flags") or {}).items():
            if f not in self.flags:
                raise EvidenceError(f"unknown plan flag {f!r} for {self.name}; allowed {self.flags}")
            if not isinstance(val, bool):
                raise EvidenceError(f"plan flag {f} must be boolean")
            ev[f] = "yes" if val else "no"
        for t, val in (req.get("reports") or {}).items():
            self._truth(t)
            if val is None:
                continue
            st = self.states[t]
            if val == "neg":
                ev[t + "__rep"] = "neg"
            elif val == "pos":
                ev[t + "__rep"] = "pos"
            elif val in st[1:]:
                ev[t + "__rep"] = "pos"; ev[t] = val     # specific risky state disclosed
            else:
                raise EvidenceError(f"report for {t} must be null, 'neg', 'pos' or one of {st[1:]}")
        for t, sigs in (req.get("signals") or {}).items():
            self._truth(t)
            for s, val in sigs.items():
                n = f"{t}__{s}"
                if n not in self.states:
                    raise EvidenceError(f"unknown signal {s!r} for {t}")
                if not isinstance(val, bool):
                    raise EvidenceError(f"signal {t}.{s} must be boolean")
                ev[n] = "yes" if val else "no"
        for t, val in (req.get("known") or {}).items():   # truth known from demographics (e.g. male -> not pregnant)
            self._truth(t)
            if val not in self.states[t]:
                raise EvidenceError(f"known value for {t} must be one of {self.states[t]}")
            ev[t] = val
        for t, val in (req.get("answers") or {}).items():
            self._truth(t)
            if val not in ("neg", "pos"):
                raise EvidenceError(f"answer for {t} must be 'neg' or 'pos'")
            ev[t + "__ask"] = val
        return ev

    def _truth(self, t):
        if t not in self.truths:
            raise EvidenceError(f"unknown truth {t!r} for {self.name}; allowed {self.truths}")

    # ---- inference ----
    def post(self, ev, nodes):
        ie = gum.LazyPropagation(self.bn)
        ie.setEvidence(ev)
        ie.makeInference()
        return {n: ie.posterior(n).tolist() for n in nodes if n not in ev} | {
            n: [1.0 if s == ev[n] else 0.0 for s in self.states[n]] for n in nodes if n in ev}

    def p_risky(self, ev, t):
        return 1.0 - self.post(ev, [t])[t][0]

    def p_dx(self, ev):
        names = ["dx_" + d for d in self.dx] + ["critical", "critical_esc"]
        r = self.post(ev, names)
        return {k: r[k][1] for k in names}

    def expected_losses(self, pdx):
        L = self.p["loss"]; miss = {int(k): v(e) for k, e in L["miss_cost_by_severity"].items()}
        res = v(L["residual_after_mitigation"])
        out = {}
        for a in ("sign_off", "modify", "escalate"):
            mc = v(self.c["modify_cost"]) if "modify_cost" in self.c else v(L["modify_cost"])   # per-complaint override
            tot = mc if a == "modify" else v(L["escalate_cost"]) if a == "escalate" else 0.0
            for d, spec in self.dx.items():
                cost = pdx["dx_" + d] * miss[int(spec["severity"])]
                tot += cost * (res if a in spec.get("mitigated_by", []) else 1.0)
            out[a] = tot
        return out

    def label(self, p):
        for b in self.p["labels"]:
            if p <= b["max"] + 1e-12:
                return b["label"]
        return self.p["labels"][-1]["label"]

    def sample(self, n, seed):
        """Seeded forward (ancestral) sampling of synthetic encounters from the BN."""
        rng = np.random.default_rng(seed)
        out = []
        for _ in range(n):
            s = {}
            for node in self.order:
                c = self.cpt[node]
                probs = c["table"][tuple(s[x] for x in c["parents"])]
                s[node] = self.states[node][int(rng.choice(len(probs), p=probs))]
            out.append(s)
        return out


def assess(params, req):
    """Full assessment: posteriors, 4-state reliability, if-wrong ranges, VOI, escalation."""
    if not isinstance(req, dict) or "complaint" not in req:
        raise EvidenceError("request must be an object with 'complaint'")
    m = RiskModel(params, req["complaint"])
    ev = m.evidence(req)
    th = params["thresholds"]
    doubt, crit_thr, min_ro = v(th["doubt_posterior"]), v(th["critical_escalate"]), v(th["min_ruleout"])
    doubt_crit = v(th["doubt_posterior_critical"]) if "doubt_posterior_critical" in th else doubt
    pdx = m.p_dx(ev)
    el = m.expected_losses(pdx)
    best = min(el, key=el.get)
    truths = []
    for t in m.truths:
        T = params["truths"][t]; pr = m.p_risky(ev, t)
        rep = ev.get(t + "__rep"); ans = ev.get(t + "__ask")
        if ans == "pos" or rep == "pos":
            state, why = "Reliable", "disclosed"
        elif rep is None and ans is None:
            state, why = "Not said", "no report (never asked)"
        elif pr < (doubt_crit if any(t in d["parents"] and d["severity"] >= m.crit_sev for d in m.dx.values()) else doubt):
            state, why = "Reliable", "negative report consistent with context"
        else:
            # which path explains a false negative here: deliberate concealment vs recall/understanding error
            r = T["report"]; ctxon = [c for c in m.ctx if ev.get("ctx_" + c) == "yes"]
            conceal = noisy_or(v(r["conceal_base"]), [v(r["conceal_context"][c]) for c in r.get("conceal_context", {}) if c in ctxon])
            recall = noisy_or(v(r["recall_miss"]), [v(r["recall_context"][c]) for c in r.get("recall_context", {}) if c in ctxon])
            if T.get("sensitive") and conceal >= recall:
                state, why = "Said differently on purpose", f"concealment path dominates ({conceal:.2f} vs recall {recall:.2f})"
            else:
                state, why = "Said wrong", f"recall/understanding path dominates ({recall:.2f} vs concealment {conceal:.2f})"
        # if-wrong: worst-case dx range across plausible truth states
        iw = None
        kids = [d for d, spec in m.dx.items() if t in spec["parents"]]
        if kids:
            cands = []
            benign = T["states"][0]
            for d in kids:
                if t in ev:   # truth fixed by disclosure
                    lo = hi = pdx["dx_" + d]
                else:
                    lo = m.p_dx(ev | {t: benign})["dx_" + d]
                    hi = max(m.p_dx(ev | {t: s})["dx_" + d] for s in T["states"][1:])
                cands.append((m.dx[d]["severity"] * hi, d, lo, hi))
            _, d, lo, hi = max(cands)
            spec = m.dx[d]
            iw = {"dx": d, "current": pdx["dx_" + d], "low": lo, "high": hi, "severity": int(spec["severity"]),
                  "worst_miss": spec["worst_miss"], "plan_change": spec["plan_change"],
                  "label_current": m.label(pdx["dx_" + d]), "label_high": m.label(hi)}
        truths.append({"truth": t, "posterior": pr, "label": m.label(pr), "state": state, "why": why,
                       "report": rep, "answer": ans, "sensitive": bool(T.get("sensitive")), "if_wrong": iw})
    voi = voi_list(m, params, ev, el, crit_thr)
    p_crit, p_esc = pdx["critical"], pdx["critical_esc"]
    best_ro = max([q["p_ruleout"] for q in voi], default=0.0)
    recommend = p_esc > crit_thr and best_ro < min_ro
    return {"complaint": m.name, "engine": "bn", "inference": "exact (pyAgrum LazyPropagation)",
            "param_source": source_summary(params), "param_version": params.get("meta", {}).get("version"),
            "truths": truths,
            "dx": {k[3:]: {"p": pdx[k], "label": m.label(pdx[k]), "severity": int(m.dx[k[3:]]["severity"])} for k in pdx if k.startswith("dx_")},
            "p_critical": p_crit, "p_critical_label": m.label(p_crit),
            "p_critical_needs_escalation": p_esc, "p_critical_needs_escalation_label": m.label(p_esc),
            "expected_loss": el, "best_action": best, "voi": voi,
            "escalation": {"recommend": recommend, "p_critical": p_esc, "threshold": crit_thr, "best_question_ruleout": best_ro,
                           "reason": (f"P(critical miss a plan change cannot fix) {m.label(p_esc)} ({p_esc:.2f}) > {crit_thr} and no question rules it out with P >= {min_ro}"
                                      if recommend else "")}}


def voi_list(m, params, ev, el_now, crit_thr):
    """True VOI = EL(best action now) − E_answer[EL(best action | answer)], per candidate question (truth not yet answered)."""
    best_now = min(el_now.values())
    out = []
    for t in m.truths:
        n = t + "__ask"
        if n in ev or t in ev:
            continue
        pa = m.post(ev, [n])[n]
        exp_best, ro = 0.0, 0.0
        for a, pa_ in zip(m.states[n], pa):
            if pa_ <= 0:
                continue
            pdx = m.p_dx(ev | {n: a})
            exp_best += pa_ * min(m.expected_losses(pdx).values())
            if pdx["critical_esc"] < crit_thr:
                ro += pa_
        out.append({"truth": t, "question": params["truths"][t]["question"], "voi": max(0.0, best_now - exp_best),
                    "p_answer_pos": pa[1], "p_ruleout": ro})
    return sorted(out, key=lambda q: -q["voi"])
