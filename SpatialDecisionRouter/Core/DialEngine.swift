import Foundation

// MARK: - M2 earned-autonomy dials (docs/SYMBIOSIS_PLAN.md §3 layer 1, §8 M2)
// Dials move ONLY from outcome-graded evidence in the unified ledger:
//   evidence  = decisions of this context since its last dial change that have an observed outcome;
//               success = the AGENT's proposal matched the outcome (that is what autonomy is about).
//   posterior = Beta(1 + successes, 1 + failures); 90% interval by normal approximation (labelled as such).
//   raise     : n ≥ minN and interval low ≥ raiseLo  → autonomy +step, deference −step
//   lower     : n ≥ minN and interval high ≤ lowerHi → autonomy −step, deference +step
//   demotion  : ANY critical miss in the window (agent wrong where a hard trigger / escalation applied, or on a card
//               marked severity=critical)  → autonomy −demoteStep, deference +demoteStep, immediately (no minN)
//   split     : split ratings may nudge detail / challenge by ±step, but only together with an outcome-graded window
//               of n ≥ minN (never from self-ratings alone) and only with ≥ splitMin ratings of the same kind.
// Caps (clinical: autonomy ≤ 40, deference ≥ 80) are applied after every move. Every change (and every revert) is a
// signed `dial_change` ledger line with reason, evidence refs and the posterior. Current dials = replay of those lines.
// Thresholds below are DESIGN PLACEHOLDERS, not validated.

struct DialPosterior: Codable, Hashable {
    var successes: Int
    var failures: Int
    var n: Int
    var mean: Double
    var lo: Double
    var hi: Double
    var method: String
}

struct DialPolicy {
    var minN = 5
    var raiseLo = 0.6
    var lowerHi = 0.5
    var step = 5.0
    var demoteStep = 15.0
    var splitMin = 3
    var sharpMin = 3            // spot-checks needed before human sharpness affects dials
    var sharpPoorHi = 0.5       // 90% high ≤ this → AI hands detail back + challenges more
    var sharpGoodLo = 0.5       // 90% low ≥ this → absorption may rise above sharpDetailGate
    var sharpDetailGate = 85.0  // detail ≥ this needs good sharpness evidence to rise further
    var demoteDeferenceStep = 10.0
    var demoteDeferenceMax = 95.0
    static let standard = DialPolicy()
}

struct DialMove: Equatable {
    var before: DialSnapshot
    var after: DialSnapshot
    var reason: String
    var evidence: [String]
    var posterior: DialPosterior?
    var demotion: Bool
}

enum DialEngine {
    static let earnedSource = "earned (ledger-derived; thresholds are design placeholders)"
    static let escalateAnswers: Set<String> = ["Escalate", "escalate", "escalate to security"]

    static func posterior(_ s: Int, _ f: Int) -> DialPosterior {
        let a = Double(1 + s), b = Double(1 + f), m = a / (a + b)
        let sd = (a * b / ((a + b) * (a + b) * (a + b + 1))).squareRoot()
        let r = { (x: Double) in (x * 1000).rounded() / 1000 }
        return DialPosterior(successes: s, failures: f, n: s + f, mean: r(m), lo: r(max(0, m - 1.645 * sd)), hi: r(min(1, m + 1.645 * sd)),
                             method: "Beta(1+s,1+f), 90% interval via normal approximation")
    }

    struct Graded { let id: String; let agentCorrect: Bool; let critical: Bool; let split: String? }
    struct Spot { let id: String; let humanCorrect: Bool }

    static func outcomes(_ recs: [UnifiedDecisionRecord]) -> [String: RecordOutcome] {
        var o: [String: RecordOutcome] = [:]
        for r in recs where r.kind == "outcome" { if let ref = r.ref_id, let x = r.outcome { o[ref] = x } }
        return o
    }
    /// outcome-graded spot-checks of `key` (all, or since index `from`)
    static func spots(key: String, recs: [UnifiedDecisionRecord], from: Int = 0) -> [Spot] {
        let o = outcomes(recs)
        return recs[from...].compactMap { r in
            guard r.kind == "spot_check", r.domain == key, let sc = r.spot_check else { return nil }
            guard let out = sc.outcome ?? r.ref_id.flatMap({ o[$0]?.value }) else { return nil }
            return Spot(id: r.id, humanCorrect: sc.human_call == out)
        }
    }
    /// human sharpness (spot-check calibration) for UI
    static func sharpness(key: String, recs: [UnifiedDecisionRecord]) -> DialPosterior? {
        let sp = spots(key: key, recs: recs); guard !sp.isEmpty else { return nil }
        let k = sp.filter(\.humanCorrect).count; return posterior(k, sp.count - k)
    }
    /// did the human's overrides (changed the agent's pick) hold up against the outcome?
    static func overrides(key: String, recs: [UnifiedDecisionRecord]) -> DialPosterior? {
        let o = outcomes(recs)
        var k = 0, n = 0
        for r in recs where r.kind == "decision" && r.domain == key && r.human_decision?.changed == true {
            guard let out = (o[r.id] ?? r.outcome)?.value, let h = r.human_decision?.answer else { continue }
            n += 1; if h == out { k += 1 }
        }
        return n == 0 ? nil : posterior(k, n - k)
    }

    /// decisions for `key` after its last dial_change, with outcomes / split ratings folded from amendment lines
    static func window(key: String, recs: [UnifiedDecisionRecord]) -> (graded: [Graded], splits: [String: Int]) {
        let start = (recs.lastIndex { $0.kind == "dial_change" && $0.domain == key }).map { $0 + 1 } ?? 0
        var outcome: [String: RecordOutcome] = [:], split: [String: String] = [:]
        for r in recs {
            guard let ref = r.ref_id else { continue }
            if r.kind == "outcome", let o = r.outcome { outcome[ref] = o }
            if r.kind == "split_rating", let s = r.split_rating { split[ref] = s }
        }
        var g: [Graded] = [], splits: [String: Int] = [:]
        for r in recs[start...] where r.kind == "decision" && r.domain == key {
            let sp = split[r.id] ?? r.split_rating
            if let sp { splits[sp, default: 0] += 1 }
            guard let o = outcome[r.id] ?? r.outcome, let p = r.agent_proposal?.answer else { continue }
            let correct = p == o.value
            let severe = !(r.escalation_flags ?? []).isEmpty || escalateAnswers.contains(o.value) || r.card_payload?["severity"] == "critical"
            g.append(Graded(id: r.id, agentCorrect: correct, critical: severe && !correct, split: sp))
        }
        return (g, splits)
    }

    static func evaluate(key: String, current: SymbiosisContext, recs: [UnifiedDecisionRecord], policy: DialPolicy = .standard) -> DialMove? {
        let (g, splits) = window(key: key, recs: recs)
        let before = current.dials
        var c = current
        func finish(_ reason: String, _ ev: [String], _ post: DialPosterior?, demotion: Bool) -> DialMove? {
            c.dials.source = earnedSource
            let e = c.enforced()
            var capNote = ""
            if e.dials.autonomy_horizon != c.dials.autonomy_horizon { capNote += " · autonomy held at cap \(Int(c.caps.autonomyMax))" }
            if e.dials.deference != c.dials.deference {
                capNote += c.dials.deference < c.caps.deferenceMin ? " · deference held at floor \(Int(c.caps.deferenceMin))" : " · deference at max" }
            let a = e.dials
            guard a.deference != before.deference || a.autonomy_horizon != before.autonomy_horizon ||
                  a.detail_absorption != before.detail_absorption || a.challenge != before.challenge else { return nil }
            return DialMove(before: before, after: a, reason: reason + capNote, evidence: ev, posterior: post, demotion: demotion)
        }
        if let miss = g.first(where: \.critical) {
            c.dials.autonomy_horizon -= policy.demoteStep
            // softened: deference rises by at most demoteDeferenceStep and never above demoteDeferenceMax (floor still applies)
            c.dials.deference = max(c.dials.deference, min(c.dials.deference + policy.demoteDeferenceStep, policy.demoteDeferenceMax))
            return finish("DEMOTION: critical miss — the agent's pick was wrong on a high-severity card", [miss.id], posterior(g.filter(\.agentCorrect).count, g.filter { !$0.agentCorrect }.count), demotion: true)
        }
        let start = (recs.lastIndex { $0.kind == "dial_change" && $0.domain == key }).map { $0 + 1 } ?? 0
        let sp = spots(key: key, recs: recs, from: start)
        let sk = sp.filter(\.humanCorrect).count, sharp = sp.count >= policy.sharpMin ? posterior(sk, sp.count - sk) : nil
        let sharpPoor = sharp.map { $0.hi <= policy.sharpPoorHi } ?? false
        let sharpGood = sharp.map { $0.lo >= policy.sharpGoodLo } ?? false
        var why: [String] = [], sharpNote: [String] = []
        var ev: [String] = []
        if sharpPoor, let sh = sharp {
            c.dials.detail_absorption -= policy.step; c.dials.challenge += policy.step
            sharpNote.append("sharpness: you matched the outcome on \(sk)/\(sp.count) spot-checks (90% high \(sh.hi) ≤ \(policy.sharpPoorHi)) → AI hands detail back, challenges more")
            ev += sp.map(\.id)
        }
        guard g.count >= policy.minN else {
            return sharpNote.isEmpty ? nil : finish(sharpNote.joined(separator: " · "), ev, sharp, demotion: false)
        }
        let s = g.filter(\.agentCorrect).count, post = posterior(s, g.count - s)
        ev += g.map(\.id)
        if post.lo >= policy.raiseLo {
            c.dials.autonomy_horizon += policy.step; c.dials.deference -= policy.step
            why.append("earned: agent matched the outcome \(s)/\(g.count) (90% low \(post.lo) ≥ \(policy.raiseLo))")
        } else if post.hi <= policy.lowerHi {
            c.dials.autonomy_horizon -= policy.step; c.dials.deference += policy.step
            why.append("lowered: agent matched the outcome \(s)/\(g.count) (90% high \(post.hi) ≤ \(policy.lowerHi))")
        }
        // split nudges: only alongside the outcome-graded window above
        if let (k, n) = splits.max(by: { $0.value < $1.value }), n >= policy.splitMin {
            switch k {
            case "buried_me":
                if sharpPoor { why.append("split: 'buried me' ×\(n) ignored — sharpness too low to absorb more") }
                else if c.dials.detail_absorption >= policy.sharpDetailGate && !sharpGood {
                    if c.dials.detail_absorption == before.detail_absorption { why.append("split: 'buried me' ×\(n) held — detail ≥ \(Int(policy.sharpDetailGate)) needs good spot-check evidence") }
                } else { c.dials.detail_absorption += policy.step; why.append("split: 'buried me in detail' ×\(n) → AI absorbs more detail") }
            case "too_abstract": c.dials.detail_absorption -= policy.step; why.append("split: 'too abstract' ×\(n) → AI hands back detail")
            case "overstepped_me": c.dials.challenge -= policy.step; why.append("split: 'overstepped me' ×\(n) → AI challenges less")
            default: break
            }
        }
        why += sharpNote
        guard !why.isEmpty else { return nil }
        return finish(why.joined(separator: " · "), ev, post, demotion: false)
    }

    /// seed profile for a unified-domain key
    static func seed(for key: String) -> SymbiosisContext? {
        switch key {
        case "symbiosis:ed_triage", "ed_triage": SymbiosisSeeds.clinical
        case "symbiosis:personal_finance": SymbiosisSeeds.finance
        case "ai_tele_doc": SymbiosisSeeds.teleDoc
        case "weriam_principal": SymbiosisSeeds.weriam
        default: nil
        }
    }
    /// current dials per key = seed, then every dial_change line in ledger order
    static func replay(_ recs: [UnifiedDecisionRecord]) -> [String: SymbiosisContext] {
        var out: [String: SymbiosisContext] = [:]
        for r in recs where r.kind == "dial_change" {
            guard var c = out[r.domain] ?? seed(for: r.domain), let a = r.dial_after else { continue }
            c.dials = a; c.generation = r.generation; out[r.domain] = c.enforced()
        }
        return out
    }

    static func record(key: String, contextId: String, move: DialMove, generation: Int) -> UnifiedDecisionRecord {
        var r = UnifiedDecisionRecord(kind: "dial_change", id: UUID().uuidString, ref_id: nil, timestamp: DecisionLedger.iso(), domain: key,
                                      context_id: contextId, dial_snapshot: move.after, generation: generation,
                                      signer_key_id: "", signer_pub: "", ledger_prev: "")
        r.dial_before = move.before; r.dial_after = move.after; r.reason = move.reason; r.evidence_refs = move.evidence; r.posterior = move.posterior
        r.escalation_flags = move.demotion ? ["demotion"] : []
        return r
    }
}
