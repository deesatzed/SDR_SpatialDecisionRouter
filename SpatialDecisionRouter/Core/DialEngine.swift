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
                capNote += c.dials.deference < c.caps.deferenceMin ? " · deference held at floor \(Int(c.caps.deferenceMin))" : " · deference at max 100" }
            let a = e.dials
            guard a.deference != before.deference || a.autonomy_horizon != before.autonomy_horizon ||
                  a.detail_absorption != before.detail_absorption || a.challenge != before.challenge else { return nil }
            return DialMove(before: before, after: a, reason: reason + capNote, evidence: ev, posterior: post, demotion: demotion)
        }
        if let miss = g.first(where: \.critical) {
            c.dials.autonomy_horizon -= policy.demoteStep; c.dials.deference += policy.demoteStep
            return finish("DEMOTION: critical miss — the agent's pick was wrong on a high-severity card", [miss.id], posterior(g.filter(\.agentCorrect).count, g.filter { !$0.agentCorrect }.count), demotion: true)
        }
        guard g.count >= policy.minN else { return nil }
        let s = g.filter(\.agentCorrect).count, post = posterior(s, g.count - s)
        var why: [String] = []
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
            case "buried_me": c.dials.detail_absorption += policy.step; why.append("split: 'buried me in detail' ×\(n) → AI absorbs more detail")
            case "too_abstract": c.dials.detail_absorption -= policy.step; why.append("split: 'too abstract' ×\(n) → AI hands back detail")
            case "overstepped_me": c.dials.challenge -= policy.step; why.append("split: 'overstepped me' ×\(n) → AI challenges less")
            default: break
            }
        }
        guard !why.isEmpty else { return nil }
        return finish(why.joined(separator: " · "), g.map(\.id), post, demotion: false)
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
