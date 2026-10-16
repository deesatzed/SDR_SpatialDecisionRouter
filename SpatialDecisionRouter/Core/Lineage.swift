import Foundation

// M5 — Lineage: per-area history reconstructed PURELY from the signed ledger (no engine state).
// Generations, promotions / rollbacks / discarded candidates (reasons + replay results), dial changes (why + evidence),
// spot-check calibration over time, override-held-up rate, critical misses / demotions; per-event signature + chain status;
// markdown export (Python mirror: tools/lineage.py, written by the exporter as lineage/<area>.md).

struct LineageEvent: Identifiable, Hashable {
    let id: String
    let line: Int                 // 1-based ledger line
    let timestamp: String
    let kind: String              // dial_change | demotion | revert | spot_check | critical_miss | policy_proposal | evaluation_passed | discarded | principal_decision | promotion | rollback
    let title: String
    let detail: String
    let evidence: [String]
    let championGeneration: Int
    let dialGeneration: Int
    let hash: String
    let prev: String
    let signer: String
    let status: String            // verified | bad signature | after chain break (line N)
    var ok: Bool { status == "verified" }
}

struct Lineage {
    var area: String
    var ledgerLines: Int
    var chainOK: Bool
    var chainProblem: String?
    var signers: [String]
    var events: [LineageEvent]
    var decisions: Int
    var graded: Int
    var criticalMisses: Int
    var demotions: Int
    var dialSeries: [DialSnapshot]
    var sharpSeries: [DialPosterior]      // cumulative after each graded spot-check
    var overrideSeries: [DialPosterior]   // cumulative after each graded override
    var champion: [PolicyRule]
    var championGeneration: Int
    var dialsNow: DialSnapshot?
    var dialGeneration: Int
}

enum LineageBuilder {
    static let eventKinds = ["dial_change", "spot_check", "policy_proposal", "policy_evaluation", "principal_decision", "promotion", "rollback"]
    /// chain + signature status per line, independent of the event list
    static func lineStatus(_ recs: [UnifiedDecisionRecord]) -> (ok: Bool, problem: String?, status: [String]) {
        let v = DecisionLedger.verify(recs)
        let status = recs.enumerated().map { i, r -> String in
            if !v.ok && i > v.n { return "after chain break (line \(v.n + 1))" }
            return DecisionLedger.verifyOne(r) ? (v.ok || i < v.n ? "verified" : "chain break here") : "bad signature"
        }
        return (v.ok, v.problem, status)
    }

    static func build(area key: String, recs: [UnifiedDecisionRecord]) -> Lineage {
        let st = lineStatus(recs)
        let outcomes = DialEngine.outcomes(recs)
        var ev: [LineageEvent] = []
        var champGen = 0, dialGen = 0, decisions = 0, graded = 0, crit = 0, demos = 0
        var dials: [DialSnapshot] = DialEngine.seed(for: key).map { [$0.dials] } ?? []
        var sk = 0, sn = 0, ok = 0, on = 0
        var sharp: [DialPosterior] = [], over: [DialPosterior] = []
        var champion: [PolicyRule] = []
        let s3 = { (x: String) in String(x.prefix(8)) }
        for (i, r) in recs.enumerated() where r.domain == key {
            func add(_ kind: String, _ title: String, _ detail: String, _ evid: [String]) {
                ev.append(LineageEvent(id: r.id, line: i + 1, timestamp: r.timestamp, kind: kind, title: title, detail: detail, evidence: evid,
                                       championGeneration: champGen, dialGeneration: dialGen, hash: r.ledger_hash ?? "", prev: r.ledger_prev,
                                       signer: r.signer_key_id, status: st.status[i]))
            }
            switch r.kind {
            case "decision":
                decisions += 1
                let out = (outcomes[r.id] ?? r.outcome)?.value
                if let o = out { graded += 1
                    let agentWrong = r.agent_proposal.map { $0.answer != o } ?? false
                    let severe = !(r.escalation_flags ?? []).isEmpty || DialEngine.escalateAnswers.contains(o) || r.card_payload?["severity"] == "critical"
                    if agentWrong && severe { crit += 1
                        add("critical_miss", "Critical miss · \(r.card_payload?["title"] ?? r.item_id ?? "")", "agent \(r.agent_proposal?.answer ?? "?") · outcome \(o) · human \(r.human_decision?.answer ?? "?")", [r.id]) }
                    if r.human_decision?.changed == true, let h = r.human_decision?.answer { on += 1; if h == o { ok += 1 }; over.append(DialEngine.posterior(ok, on - ok)) }
                }
            case "dial_change":
                dialGen = r.generation
                if let a = r.dial_after { dials.append(a) }
                let demo = (r.escalation_flags ?? []).contains("demotion"), rev = (r.reason ?? "").hasPrefix("REVERT")
                if demo { demos += 1 }
                let b = r.dial_before, a = r.dial_after
                let delta = [("defer", b?.deference, a?.deference), ("detail", b?.detail_absorption, a?.detail_absorption), ("challenge", b?.challenge, a?.challenge), ("autonomy", b?.autonomy_horizon, a?.autonomy_horizon)]
                    .compactMap { n, x, y -> String? in guard let x, let y, x != y else { return nil }; return "\(n) \(Int(x))→\(Int(y))" }.joined(separator: ", ")
                add(demo ? "demotion" : (rev ? "revert" : "dial_change"), (demo ? "DEMOTION · " : rev ? "Revert · " : "Dial move · ") + delta,
                    (r.reason ?? "") + (r.posterior.map { " · n=\($0.n) mean \($0.mean) [\($0.lo)–\($0.hi)]" } ?? ""), r.evidence_refs ?? [])
            case "spot_check":
                guard let sc = r.spot_check else { break }
                let out = sc.outcome ?? r.ref_id.flatMap { outcomes[$0]?.value }
                if let o = out { sn += 1; if o == sc.human_call { sk += 1 }; sharp.append(DialEngine.posterior(sk, sn - sk)) }
                add("spot_check", "Spot-check · you \(sc.human_call) · AI \(sc.agent_pick) · outcome \(out ?? "pending")" + (out.map { $0 == sc.human_call ? " ✓" : " ✗" } ?? ""),
                    "trigger: \(sc.trigger) · hidden: \(sc.hidden.joined(separator: ", "))" + (sn > 0 ? " · sharpness \(sk)/\(sn)" : ""), [r.ref_id].compactMap { $0 })
            case "policy_proposal":
                add("policy_proposal", "Critic proposes · \(r.promo?.rule?.text ?? "")", "\(r.promo?.critic ?? "") · in-sample gain \(r.promo?.train_gain ?? 0) · \(r.evidence_refs?.count ?? 0) evidence lines", r.evidence_refs ?? [])
            case "policy_evaluation":
                let p = r.promo, m = p?.metrics
                let res = m.map { "replay \(p?.replay_name ?? "") n=\($0.n): \($0.champion_correct)→\($0.candidate_correct) · Δ \($0.accuracy_delta) [\($0.delta_interval.first ?? 0), \($0.delta_interval.last ?? 0)] · W/L \($0.wins)/\($0.losses) · critical \($0.critical_champion)→\($0.critical_candidate)" } ?? ""
                let passed = p?.verdict == "passed"
                add(passed ? "evaluation_passed" : "discarded", (passed ? "Beats champion · " : "Discarded · ") + (p?.rule?.text ?? ""),
                    res + ((p?.reasons ?? []).isEmpty ? "" : " · " + (p?.reasons ?? []).joined(separator: "; ")) + " · evaluator \(p?.evaluator_version ?? "") \(s3(p?.evaluator_sha ?? "")) · cases \(s3(p?.cases_sha256 ?? ""))",
                    [r.ref_id].compactMap { $0 })
            case "principal_decision":
                add("principal_decision", "Principal · \(r.promo?.decision ?? "")", "\(r.promo?.decided_by ?? "") on \(r.promo?.rule?.text ?? "")", [r.ref_id].compactMap { $0 })
            case "promotion", "rollback":
                champGen = r.promo?.champion_generation ?? champGen; champion = r.promo?.rules_after ?? champion
                let rules = champion.isEmpty ? "seed policy" : champion.map(\.text).joined(separator: "; ")
                add(r.kind, (r.kind == "promotion" ? "PROMOTED → champion gen \(champGen)" : "ROLLBACK → champion gen \(champGen)"), (r.reason ?? "") + " · now: \(rules)", r.evidence_refs ?? [])
            default: break
            }
        }
        let now = DialEngine.replay(recs)[key]?.dials ?? DialEngine.seed(for: key)?.dials
        return Lineage(area: key, ledgerLines: recs.count, chainOK: st.ok, chainProblem: st.problem, signers: Array(Set(recs.map(\.signer_key_id))).sorted(),
                       events: ev, decisions: decisions, graded: graded, criticalMisses: crit, demotions: demos, dialSeries: dials,
                       sharpSeries: sharp, overrideSeries: over, champion: champion, championGeneration: champGen, dialsNow: now, dialGeneration: dialGen)
    }
    static func areas(_ recs: [UnifiedDecisionRecord]) -> [String] {
        let s = Set(recs.map(\.domain).filter { $0.hasPrefix("symbiosis:") }).union(["symbiosis:personal_finance", "symbiosis:ed_triage"])
        return s.sorted()
    }

    static func markdown(_ l: Lineage) -> String {
        func p(_ x: DialPosterior?) -> String { x.map { "\($0.successes)/\($0.n) · mean \($0.mean) [\($0.lo)–\($0.hi)]" } ?? "none yet" }
        var s = "# Lineage · \(l.area)\n\n"
        s += "Reconstructed from the signed ledger · \(l.ledgerLines) lines · chain " + (l.chainOK ? "✓ verified" : "✗ \(l.chainProblem ?? "broken")") + " · signers \(l.signers.joined(separator: ", "))\n\n"
        s += "## Summary\n\n"
        s += "- Champion generation: \(l.championGeneration) · rules: \(l.champion.isEmpty ? "seed policy (follow the agent)" : l.champion.map(\.text).joined(separator: "; "))\n"
        if let d = l.dialsNow { s += "- Dials now (gen \(l.dialGeneration)): deference \(Int(d.deference)), detail \(Int(d.detail_absorption)), challenge \(Int(d.challenge)), autonomy \(Int(d.autonomy_horizon))\n" }
        s += "- Decisions: \(l.decisions) (outcome-graded \(l.graded)) · critical misses: \(l.criticalMisses) · demotions: \(l.demotions)\n"
        s += "- Sharpness (spot-checks): \(p(l.sharpSeries.last))\n"
        s += "- Overrides held up: \(p(l.overrideSeries.last))\n"
        s += "- Autonomy path: \(l.dialSeries.map { String(Int($0.autonomy_horizon)) }.joined(separator: " → "))\n\n"
        s += "## Timeline\n\n| line | time | event | detail | evidence | signature |\n|---:|---|---|---|---|---|\n"
        for e in l.events {
            let esc = { (x: String) in x.replacingOccurrences(of: "|", with: "\\|").replacingOccurrences(of: "\n", with: " ") }
            s += "| \(e.line) | \(e.timestamp) | \(esc(e.title)) | \(esc(e.detail)) | \(e.evidence.map { String($0.prefix(8)) }.joined(separator: " ")) | \(e.ok ? "✓" : "✗ " + e.status) \(e.hash.prefix(10)) |\n"
        }
        s += "\n_All history SYNTHETIC unless outcomes are observed; thresholds are design placeholders._\n"
        return s
    }
}
