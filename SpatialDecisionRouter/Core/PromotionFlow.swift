import Foundation

/// M4 engine flow. Every step is a signed ledger line. Only `principal(_:_:)` with a human decision can promote.
extension RouterEngine {
    static let promoKinds: Set<String> = ["policy_proposal", "policy_evaluation", "principal_decision", "promotion", "rollback"]
    func loadPromotion() {
        let recs = ledger.read()
        promoLog = recs.filter { Self.promoKinds.contains($0.kind) }
        let c = PromotionEngine.champion(recs); champion = c.rules; championGeneration = c.generation
    }
    var pendingPrincipal: [UnifiedDecisionRecord] { PromotionEngine.pending(promoLog) }
    var lastEvaluations: [UnifiedDecisionRecord] { promoLog.filter { $0.kind == "policy_evaluation" }.suffix(6).reversed() }
    func packStatus() -> String {
        do { let p = try PromotionEngine.bundledPack()
            return "replay \(p.manifest.name) · \(p.manifest.cases) blinded cases · sha \(p.manifest.cases_sha256.prefix(10))… ✓ verified · evaluator \(PromotionEngine.evaluatorVersion) \(PromotionEngine.evaluatorSha.prefix(10))…"
        } catch { return "replay pack refused: \(error)" }
    }
    private func put(_ r: UnifiedDecisionRecord) -> UnifiedDecisionRecord? {
        guard let s = ledger.append(r) else { return nil }
        promoLog.append(s); return s
    }
    /// critic proposes; each proposal is evaluated on the frozen replay; losers are discarded (logged), winners await a Principal
    func runCritic() {
        promoError = nil
        do {
            let pack = try PromotionEngine.bundledPack()
            let held = Set(pack.answers.values.map(\.source_id))
            // held-in evidence: bundled synthetic history + this device's own graded Symbiosis decisions
            let live: [TrainRec] = ledger.read().filter { $0.kind == "decision" && $0.domain.hasPrefix("symbiosis:") }.map {
                TrainRec(id: $0.id, domain: $0.domain, card_payload: $0.card_payload, agent_proposal: $0.agent_proposal, outcome: $0.outcome) }
            let cands = PromotionEngine.critic(train: PromotionEngine.bundledTrain() + live, champion: champion, exclude: held) + PromotionEngine.llmCritic()
            if cands.isEmpty { promoError = "critic: no candidate with enough held-in evidence" }
            for c in cands {
                let prop = PromotionInfo(candidate_id: c.id, area: c.rule.area, rule: c.rule, critic: c.critic, train_gain: c.trainGain, champion_generation: championGeneration)
                guard let p = put(PromotionEngine.line("policy_proposal", area: c.rule.area, ref: nil, generation: championGeneration, prop,
                                                       reason: "critic proposes (never grades itself): \(c.rule.text)", evidence: c.evidence)) else { continue }
                var ev = try PromotionEngine.evaluate(c, champion: champion, pack: pack); ev.champion_generation = championGeneration
                _ = put(PromotionEngine.line("policy_evaluation", area: c.rule.area, ref: p.id, generation: championGeneration, ev,
                                             reason: ev.verdict == "passed" ? "beats champion on frozen replay → Principal card" : "DISCARDED: " + (ev.reasons ?? []).joined(separator: "; ")))
            }
        } catch { promoError = "refused: \(error)" }
    }
    /// Principal card. decision ∈ approve_once | decline | defer (Pass = defer). Approve promotes only a fresh, passing evaluation.
    func principal(_ eval: UnifiedDecisionRecord, _ decision: String) {
        guard eval.kind == "policy_evaluation", var p = eval.promo, let area = p.area else { return }
        p.decision = decision; p.decided_by = "human (Principal card)"
        guard let d = put(PromotionEngine.line("principal_decision", area: area, ref: eval.id, generation: championGeneration, p,
                                               reason: "Principal: \(decision)")) else { return }
        guard decision == "approve_once" else { return }
        // stale or failing evaluations cannot promote, even with a signature
        guard p.verdict == "passed", p.champion_generation == championGeneration, let rule = p.rule,
              let pack = try? PromotionEngine.bundledPack(), pack.manifest.cases_sha256 == p.cases_sha256,
              p.evaluator_sha == PromotionEngine.evaluatorSha else { promoError = "approval refused: evaluation stale or not passing — re-run the critic"; return }
        var q = PromotionInfo(candidate_id: p.candidate_id, area: area, rule: rule, verdict: p.verdict, metrics: p.metrics,
                              replay_name: p.replay_name, cases_sha256: p.cases_sha256, answers_sha256: p.answers_sha256,
                              evaluator_version: p.evaluator_version, evaluator_sha: p.evaluator_sha, decision: decision, decided_by: p.decided_by)
        q.champion_generation = championGeneration + 1; q.rules_before = champion; q.rules_after = champion + [rule]
        if put(PromotionEngine.line("promotion", area: area, ref: d.id, generation: championGeneration + 1, q,
                                    reason: "PROMOTED by human signature: \(rule.text)", evidence: [eval.id, d.id])) != nil {
            champion = q.rules_after!; championGeneration += 1; lastAction = "champion gen \(championGeneration)"
        }
    }
    /// reversible: restore the previous champion (signed rollback line, generation still increments)
    func rollbackChampion() {
        guard let last = promoLog.last(where: { $0.kind == "promotion" || $0.kind == "rollback" }), let p = last.promo, let before = p.rules_before else { return }
        var q = PromotionInfo(champion_generation: championGeneration + 1, rules_before: champion, rules_after: before)
        q.decided_by = "human"
        let area = p.area ?? before.last?.area ?? "unknown"
        if put(PromotionEngine.line("rollback", area: area, ref: last.id, generation: championGeneration + 1, q,
                                    reason: "ROLLBACK of \(last.kind) \(last.id.prefix(8)) (human)", evidence: [last.id])) != nil {
            champion = before; championGeneration += 1
        }
    }
}
