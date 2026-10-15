import Foundation
import CryptoKit

// M4 — frozen-replay promotion + Principal card (docs/SYMBIOSIS_PLAN.md M4; Python mirror: tools/promotion.py).
// critic PROPOSES → frozen, blinded replay evaluation vs champion → (only if it passes) Principal card →
// only a signed human "Approve once" promotes (champion generation +1) → reversible by a signed rollback.
// There is deliberately no function that applies a candidate from its own evaluation (no self-graded apply path).

struct PolicyWhen: Codable, Hashable { var conf_lt: Double?; var severity: String? }
struct PolicyRule: Codable, Hashable {
    var area: String; var when: PolicyWhen; var answer: String
    var text: String { "\(area): " + (when.conf_lt.map { "agent confidence < \($0)" } ?? "severity = \(when.severity ?? "?")") + " → \(answer)" }
}
struct ChangedCase: Codable, Hashable { var case_id: String; var title: String; var before: String; var after: String; var outcome: String; var critical: Bool }
struct ReplayMetrics: Codable, Hashable {
    var n: Int; var champion_correct: Int; var candidate_correct: Int
    var accuracy_delta: Double; var delta_interval: [Double]
    var wins: Int; var losses: Int; var sign: DialPosterior
    var critical_champion: Int; var critical_candidate: Int; var escalations_removed: Int
    var changed: [ChangedCase]
}
/// payload of every M4 ledger line (policy_proposal | policy_evaluation | principal_decision | promotion | rollback)
struct PromotionInfo: Codable, Hashable {
    var candidate_id: String?
    var area: String?
    var rule: PolicyRule?
    var critic: String?
    var train_gain: Int?
    var verdict: String?            // passed | failed (failed = discarded, logged)
    var reasons: [String]?
    var metrics: ReplayMetrics?
    var replay_name: String?
    var cases_sha256: String?
    var answers_sha256: String?
    var evaluator_version: String?
    var evaluator_sha: String?
    var decision: String?           // approve_once | decline | defer   (Pass = defer)
    var decided_by: String?
    var champion_generation: Int?
    var rules_before: [PolicyRule]?
    var rules_after: [PolicyRule]?
}

struct ReplayFeatures: Codable, Hashable { var agent_confidence: Double?; var severity: String?; var area: String? }
/// the ONLY thing a policy sees: blinded inputs. Answers live in a separate type joined only inside the evaluator.
struct ReplayCase: Codable, Hashable { var case_id: String; var card: String; var agent_proposal: String; var features: ReplayFeatures }
struct ReplayAnswer: Codable, Hashable { var case_id: String; var outcome: String; var source_id: String }
struct ReplayManifest: Codable { var name: String; var cases: Int; var cases_sha256: String; var answers_sha256: String; var blinded: Bool }
struct ReplayPack { var manifest: ReplayManifest; var cases: [ReplayCase]; var answers: [String: ReplayAnswer] }
struct TrainRec: Codable { var id: String; var domain: String; var card_payload: [String: String]?; var agent_proposal: AgentProposal?; var outcome: RecordOutcome? }
struct Candidate: Hashable { var id: String; var rule: PolicyRule; var trainGain: Int; var evidence: [String]; var critic: String }

enum PromotionError: Error, Equatable { case replayTampered(String), leakage(String), evaluatorTampered, missing(String) }

enum PromotionEngine {
    static let evaluatorVersion = "replay-eval-v1"
    /// pre-registered before any candidate is seen (same numbers as tools/promotion.py MARGIN)
    static let deltaMin = 0.05, nMin = 20, signLoMin = 0.5
    static let clinicalAreas: Set<String> = ["ed_triage"], escalate: Set<String> = ["Escalate"]
    static let forbidden = ["outcome", "human_answer", "human_label", "demo_human_call", "source_id", "split_rating"]
    static var spec: String { "\(evaluatorVersion)|delta_min=\(deltaMin)|n_min=\(nMin)|sign_lo_min=\(signLoMin)|clinical=\(clinicalAreas.sorted())|escalate=\(escalate.sorted())|crit:no-rise" }
    /// frozen evaluator lock: changing the margin or rules without bumping the version is refused
    static let evaluatorLock = "bccdf6d17f336fbb7bf272d058a661acac5294b4b0c21b61726c1c36dba9879f"
    static func sha(_ d: Data) -> String { SHA256.hash(data: d).map { String(format: "%02x", $0) }.joined() }
    static var evaluatorSha: String { sha(Data(spec.utf8)) }
    static var evaluatorPinned: String = evaluatorLock

    // MARK: pack
    static func bundled(_ name: String, _ ext: String) -> URL? { Bundle.main.url(forResource: name, withExtension: ext) }
    static func loadPack(cases: URL, answers: URL, manifest: URL) throws -> ReplayPack {
        let m = try JSONDecoder().decode(ReplayManifest.self, from: Data(contentsOf: manifest))
        let cd = try Data(contentsOf: cases), ad = try Data(contentsOf: answers)
        guard sha(cd) == m.cases_sha256 else { throw PromotionError.replayTampered("cases.jsonl") }
        guard sha(ad) == m.answers_sha256 else { throw PromotionError.replayTampered("answers.jsonl") }
        guard m.blinded else { throw PromotionError.leakage("pack not blinded") }
        var cs: [ReplayCase] = []
        for line in cd.split(separator: UInt8(ascii: "\n")) where !line.isEmpty {
            let obj = try JSONSerialization.jsonObject(with: Data(line)) as? [String: Any] ?? [:]
            if let bad = forbidden.first(where: { obj[$0] != nil }) { throw PromotionError.leakage("case exposes \(bad)") }
            cs.append(try JSONDecoder().decode(ReplayCase.self, from: Data(line)))
        }
        var an: [String: ReplayAnswer] = [:]
        for line in ad.split(separator: UInt8(ascii: "\n")) where !line.isEmpty {
            let a = try JSONDecoder().decode(ReplayAnswer.self, from: Data(line)); an[a.case_id] = a
        }
        return ReplayPack(manifest: m, cases: cs, answers: an)
    }
    static func bundledPack() throws -> ReplayPack {
        guard let c = bundled("replay_cases", "jsonl"), let a = bundled("replay_answers", "jsonl"), let m = bundled("replay_manifest", "json")
        else { throw PromotionError.missing("bundled replay pack") }
        return try loadPack(cases: c, answers: a, manifest: m)
    }
    static func bundledTrain() -> [TrainRec] {
        guard let u = bundled("replay_train", "jsonl"), let d = try? Data(contentsOf: u) else { return [] }
        return d.split(separator: UInt8(ascii: "\n")).compactMap { try? JSONDecoder().decode(TrainRec.self, from: Data($0)) }
    }

    // MARK: policy
    static func matches(_ w: PolicyWhen, conf: Double?, severity: String?) -> Bool {
        if let t = w.conf_lt { return (conf ?? 1) < t }
        if let s = w.severity { return severity == s }
        return false
    }
    static func apply(_ rules: [PolicyRule], _ c: ReplayCase) -> String {
        // raw policy (no live guard) so the evaluator sees what the candidate would really do — guards are scored, not hidden
        let area = c.features.area ?? ""
        return rules.first { $0.area == area && matches($0.when, conf: c.features.agent_confidence, severity: c.features.severity) }?.answer ?? c.agent_proposal
    }
    /// live use (Symbiosis proposals). Clinical escalations are never rewritten.
    static func answer(_ rules: [PolicyRule], area: String, conf: Double?, severity: String?, base: String) -> String {
        if clinicalAreas.contains(area) && escalate.contains(base) { return base }
        return rules.first { $0.area == area && matches($0.when, conf: conf, severity: severity) }?.answer ?? base
    }

    // MARK: critic (proposes only)
    static func critic(train: [TrainRec], champion: [PolicyRule], exclude: Set<String>) -> [Candidate] {
        let recs = train.filter { !exclude.contains($0.id) && $0.outcome != nil && $0.agent_proposal != nil }
        let preds = [PolicyWhen(conf_lt: 0.6), PolicyWhen(conf_lt: 0.65), PolicyWhen(conf_lt: 0.7), PolicyWhen(severity: "critical")]
        var out: [Candidate] = []
        for area in Set(recs.map { String($0.domain.split(separator: ":").last ?? "") }).sorted() {
            var best: Candidate?
            for w in preds {
                let m = recs.filter { $0.domain.hasSuffix(area) && matches(w, conf: $0.agent_proposal?.confidence, severity: $0.card_payload?["severity"] ?? "normal") }
                var wrong: [String: Int] = [:]
                for r in m where r.outcome!.value != r.agent_proposal!.answer { wrong[r.outcome!.value, default: 0] += 1 }
                guard let (ans, c) = wrong.sorted(by: { $0.value != $1.value ? $0.value > $1.value : $0.key < $1.key }).first else { continue }
                let gain = c - m.filter { $0.outcome!.value == $0.agent_proposal!.answer }.count
                if c >= 3 && gain > 0 && gain > (best?.trainGain ?? Int.min) {
                    let rule = PolicyRule(area: area, when: w, answer: ans)
                    best = Candidate(id: String(sha(Data(rule.text.utf8)).prefix(12)), rule: rule, trainGain: gain, evidence: m.map(\.id), critic: "deterministic-v1")
                }
            }
            if let b = best, !champion.contains(b.rule) { out.append(b) }
        }
        return out
    }
    /// optional LLM critic — STUB behind a flag; no external calls. Output would still only be a proposal.
    static func llmCritic() -> [Candidate] { [] }

    // MARK: frozen evaluator
    static func score(champion: [PolicyRule], candidate: [PolicyRule], pack: ReplayPack, area: String) -> ReplayMetrics {
        var rows: [ChangedCase] = []
        for c in pack.cases where c.features.area == area {
            guard let out = pack.answers[c.case_id]?.outcome else { continue }
            let title = c.card.components(separatedBy: "title: ").last?.components(separatedBy: "\n").first ?? c.case_id
            rows.append(ChangedCase(case_id: c.case_id, title: title, before: apply(champion, c), after: apply(candidate, c), outcome: out, critical: c.features.severity == "critical"))
        }
        let n = rows.count, ca = rows.filter { $0.before == $0.outcome }.count, cb = rows.filter { $0.after == $0.outcome }.count
        let w = rows.filter { $0.after == $0.outcome && $0.before != $0.outcome }.count, l = rows.filter { $0.before == $0.outcome && $0.after != $0.outcome }.count
        let d = n > 0 ? Double(cb - ca) / Double(n) : 0
        let se = n > 0 ? (max(Double(w + l) / Double(n) - d * d, 0) / Double(n)).squareRoot() : 0
        let r = { (x: Double) in (x * 1000).rounded() / 1000 }
        return ReplayMetrics(n: n, champion_correct: ca, candidate_correct: cb, accuracy_delta: r(d), delta_interval: [r(d - 1.645 * se), r(d + 1.645 * se)],
                             wins: w, losses: l, sign: DialEngine.posterior(w, l),
                             critical_champion: rows.filter { $0.critical && $0.before != $0.outcome }.count,
                             critical_candidate: rows.filter { $0.critical && $0.after != $0.outcome }.count,
                             escalations_removed: rows.filter { escalate.contains($0.before) && !escalate.contains($0.after) }.count,
                             changed: rows.filter { $0.before != $0.after })
    }
    static func rules(_ m: ReplayMetrics, area: String) -> (String, [String]) {
        var why: [String] = []
        if m.n < nMin { why.append("n \(m.n) < \(nMin)") }
        if m.accuracy_delta < deltaMin { why.append("Δaccuracy \(m.accuracy_delta) < margin \(deltaMin)") }
        if m.sign.lo <= signLoMin { why.append("wins/losses \(m.wins)/\(m.losses): 90% low \(m.sign.lo) ≤ \(signLoMin)") }
        if m.critical_candidate > m.critical_champion { why.append("critical misses rise \(m.critical_champion)→\(m.critical_candidate)") }
        if clinicalAreas.contains(area) && m.escalations_removed > 0 { why.append("clinical guard: would remove \(m.escalations_removed) escalation(s)") }
        return (why.isEmpty ? "passed" : "failed", why)
    }
    static func evaluate(_ c: Candidate, champion: [PolicyRule], pack: ReplayPack) throws -> PromotionInfo {
        guard evaluatorSha == evaluatorPinned else { throw PromotionError.evaluatorTampered }
        let held = Set(pack.answers.values.map(\.source_id))
        if let leak = c.evidence.first(where: held.contains) { throw PromotionError.leakage("candidate evidence \(leak) is in the held-out replay") }
        let m = score(champion: champion, candidate: champion + [c.rule], pack: pack, area: c.rule.area)
        let (v, why) = rules(m, area: c.rule.area)
        return PromotionInfo(candidate_id: c.id, area: c.rule.area, rule: c.rule, critic: c.critic, train_gain: c.trainGain, verdict: v, reasons: why, metrics: m,
                             replay_name: pack.manifest.name, cases_sha256: pack.manifest.cases_sha256, answers_sha256: pack.manifest.answers_sha256,
                             evaluator_version: evaluatorVersion, evaluator_sha: evaluatorSha)
    }

    // MARK: ledger
    static func line(_ kind: String, area: String, ref: String?, generation: Int, _ p: PromotionInfo, reason: String, evidence: [String] = []) -> UnifiedDecisionRecord {
        var r = UnifiedDecisionRecord(kind: kind, id: UUID().uuidString, ref_id: ref, timestamp: DecisionLedger.iso(), domain: "symbiosis:\(area)",
                                      context_id: area, dial_snapshot: nil, generation: generation, signer_key_id: "", signer_pub: "", ledger_prev: "")
        r.promo = p; r.reason = reason; r.evidence_refs = evidence
        return r
    }
    /// champion rules + generation replayed from signed promotion / rollback lines
    static func champion(_ recs: [UnifiedDecisionRecord]) -> (rules: [PolicyRule], generation: Int) {
        guard let last = recs.last(where: { ["promotion", "rollback"].contains($0.kind) }), let p = last.promo else { return ([], 0) }
        return (p.rules_after ?? [], p.champion_generation ?? 0)
    }
    /// evaluations that passed and have no approve/decline yet (defer keeps them pending)
    static func pending(_ recs: [UnifiedDecisionRecord]) -> [UnifiedDecisionRecord] {
        let closed = Set(recs.filter { $0.kind == "principal_decision" && $0.promo?.decision != "defer" }.compactMap(\.ref_id))
        return recs.filter { $0.kind == "policy_evaluation" && $0.promo?.verdict == "passed" && !closed.contains($0.id) }
    }
}

/// live champion used by Symbiosis proposals (set by the engine from the ledger)
enum ChampionPolicy { nonisolated(unsafe) static var rules: [PolicyRule] = [] }
