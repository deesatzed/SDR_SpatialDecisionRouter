import XCTest
import CryptoKit
@testable import SpatialDecisionRouter

final class PromotionTests: XCTestCase {
    private func ledger() -> DecisionLedger {
        DecisionLedger(url: FileManager.default.temporaryDirectory.appendingPathComponent("promo-\(UUID().uuidString).jsonl"),
                       signer: LedgerSigner(key: Curve25519.Signing.PrivateKey()))
    }
    private func cands(_ pack: ReplayPack, champion: [PolicyRule] = []) -> [String: Candidate] {
        let held = Set(pack.answers.values.map(\.source_id))
        return Dictionary(uniqueKeysWithValues: PromotionEngine.critic(train: PromotionEngine.bundledTrain(), champion: champion, exclude: held).map { ($0.rule.area, $0) })
    }
    private func tmpPack() throws -> URL {
        let d = FileManager.default.temporaryDirectory.appendingPathComponent("pack-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: d, withIntermediateDirectories: true)
        for (n, e) in [("replay_cases", "jsonl"), ("replay_answers", "jsonl"), ("replay_manifest", "json")] {
            try FileManager.default.copyItem(at: PromotionEngine.bundled(n, e)!, to: d.appendingPathComponent("\(n).\(e)"))
        }
        return d
    }
    private func load(_ d: URL) throws -> ReplayPack {
        try PromotionEngine.loadPack(cases: d.appendingPathComponent("replay_cases.jsonl"), answers: d.appendingPathComponent("replay_answers.jsonl"),
                                     manifest: d.appendingPathComponent("replay_manifest.json"))
    }

    func testParityWithPythonHarness() throws {
        // same numbers as tools/promotion.py on data/replay_seed (pytest test_critic_proposes_and_real_pattern_wins)
        let pack = try PromotionEngine.bundledPack(); let c = cands(pack)
        XCTAssertEqual(pack.manifest.cases, 100)
        let fin = try PromotionEngine.evaluate(c["personal_finance"]!, champion: [], pack: pack)
        XCTAssertEqual(fin.rule, PolicyRule(area: "personal_finance", when: PolicyWhen(conf_lt: 0.65), answer: "Hold — gather info"))
        XCTAssertEqual(fin.verdict, "passed")
        XCTAssertEqual(fin.metrics?.n, 60); XCTAssertEqual(fin.metrics?.champion_correct, 35); XCTAssertEqual(fin.metrics?.candidate_correct, 53)
        XCTAssertEqual(fin.metrics?.wins, 20); XCTAssertEqual(fin.metrics?.losses, 2); XCTAssertEqual(fin.metrics?.accuracy_delta, 0.3)
        XCTAssertEqual(fin.metrics?.delta_interval, [0.188, 0.412])
        let ed = try PromotionEngine.evaluate(c["ed_triage"]!, champion: [], pack: pack)
        XCTAssertEqual(ed.verdict, "failed")
        XCTAssertEqual(ed.metrics?.critical_champion, 0); XCTAssertEqual(ed.metrics?.critical_candidate, 8); XCTAssertEqual(ed.metrics?.escalations_removed, 8)
        XCTAssertTrue(ed.reasons!.contains { $0.hasPrefix("clinical guard") })
    }
    func testMarginRules() {
        let ok = ReplayMetrics(n: 30, champion_correct: 20, candidate_correct: 23, accuracy_delta: 0.1, delta_interval: [0.02, 0.18], wins: 5, losses: 1,
                               sign: DialEngine.posterior(5, 1), critical_champion: 0, critical_candidate: 0, escalations_removed: 0, changed: [])
        XCTAssertEqual(PromotionEngine.rules(ok, area: "personal_finance").0, "passed")
        var m = ok; m.n = 10; XCTAssertEqual(PromotionEngine.rules(m, area: "personal_finance").0, "failed")
        m = ok; m.accuracy_delta = 0.04; XCTAssertEqual(PromotionEngine.rules(m, area: "personal_finance").0, "failed")
        m = ok; m.sign = DialEngine.posterior(1, 1); XCTAssertEqual(PromotionEngine.rules(m, area: "personal_finance").0, "failed")
        m = ok; m.critical_candidate = 1; XCTAssertEqual(PromotionEngine.rules(m, area: "personal_finance").0, "failed")
        m = ok; m.escalations_removed = 1; XCTAssertEqual(PromotionEngine.rules(m, area: "ed_triage").0, "failed")
    }
    func testReplayTamperRefused() throws {
        let d = try tmpPack(); let a = d.appendingPathComponent("replay_answers.jsonl")
        let s = try String(contentsOf: a, encoding: .utf8).replacingOccurrences(of: "Hold — gather info", with: "Accept plan")
        try s.write(to: a, atomically: true, encoding: .utf8)
        XCTAssertThrowsError(try load(d)) { XCTAssertEqual($0 as? PromotionError, .replayTampered("answers.jsonl")) }
    }
    func testLeakageRefused() throws {
        let d = try tmpPack(); let cu = d.appendingPathComponent("replay_cases.jsonl")
        var lines = try String(contentsOf: cu, encoding: .utf8).split(separator: "\n").map(String.init)
        lines[0] = lines[0].replacingOccurrences(of: "{\"agent_proposal\"", with: "{\"outcome\": \"Accept plan\", \"agent_proposal\"")
        let data = Data((lines.joined(separator: "\n") + "\n").utf8); try data.write(to: cu)
        // re-hash so it is not "tamper" — it must still be refused as a leak
        let mu = d.appendingPathComponent("replay_manifest.json")
        var m = try JSONSerialization.jsonObject(with: Data(contentsOf: mu)) as! [String: Any]; m["cases_sha256"] = PromotionEngine.sha(data)
        try JSONSerialization.data(withJSONObject: m).write(to: mu)
        XCTAssertThrowsError(try load(d)) { XCTAssertEqual($0 as? PromotionError, .leakage("case exposes outcome")) }
        // candidate trained on held-out ids
        let pack = try PromotionEngine.bundledPack(); var c = cands(pack)["personal_finance"]!
        c.evidence.append(pack.answers.values.first!.source_id)
        XCTAssertThrowsError(try PromotionEngine.evaluate(c, champion: [], pack: pack))
    }
    func testEvaluatorTamperRefused() throws {
        let pack = try PromotionEngine.bundledPack(); let c = cands(pack)["personal_finance"]!
        XCTAssertEqual(PromotionEngine.evaluatorSha, PromotionEngine.evaluatorLock, "evaluator spec drifted from its lock")
        PromotionEngine.evaluatorPinned = "tampered"; defer { PromotionEngine.evaluatorPinned = PromotionEngine.evaluatorLock }
        XCTAssertThrowsError(try PromotionEngine.evaluate(c, champion: [], pack: pack)) { XCTAssertEqual($0 as? PromotionError, .evaluatorTampered) }
    }
    func testChampionNeverRewritesClinicalEscalation() {
        let r = [PolicyRule(area: "ed_triage", when: PolicyWhen(severity: "critical"), answer: "Alternative plan")]
        XCTAssertEqual(PromotionEngine.answer(r, area: "ed_triage", conf: 0.9, severity: "critical", base: "Escalate"), "Escalate")
        let f = [PolicyRule(area: "personal_finance", when: PolicyWhen(conf_lt: 0.65), answer: "Hold — gather info")]
        XCTAssertEqual(PromotionEngine.answer(f, area: "personal_finance", conf: 0.55, severity: "normal", base: "Accept plan"), "Hold — gather info")
        XCTAssertEqual(PromotionEngine.answer(f, area: "personal_finance", conf: 0.8, severity: "normal", base: "Accept plan"), "Accept plan")
    }
    func testSignedLinesChampionReplayPendingAndRollback() throws {
        let l = ledger(); let pack = try PromotionEngine.bundledPack(); let c = cands(pack)["personal_finance"]!
        let prop = l.append(PromotionEngine.line("policy_proposal", area: "personal_finance", ref: nil, generation: 0, PromotionInfo(rule: c.rule), reason: "p"))!
        let ev = l.append(PromotionEngine.line("policy_evaluation", area: "personal_finance", ref: prop.id, generation: 0,
                                               try PromotionEngine.evaluate(c, champion: [], pack: pack), reason: "e"))!
        XCTAssertEqual(PromotionEngine.pending(l.read()).map(\.id), [ev.id])
        l.append(PromotionEngine.line("principal_decision", area: "personal_finance", ref: ev.id, generation: 0, PromotionInfo(decision: "defer"), reason: "d"))
        XCTAssertEqual(PromotionEngine.pending(l.read()).count, 1, "defer keeps it pending")
        l.append(PromotionEngine.line("principal_decision", area: "personal_finance", ref: ev.id, generation: 0, PromotionInfo(decision: "approve_once"), reason: "a"))
        XCTAssertTrue(PromotionEngine.pending(l.read()).isEmpty)
        l.append(PromotionEngine.line("promotion", area: "personal_finance", ref: ev.id, generation: 1,
                                      PromotionInfo(champion_generation: 1, rules_before: [], rules_after: [c.rule]), reason: "promo"))
        XCTAssertEqual(PromotionEngine.champion(l.read()).generation, 1); XCTAssertEqual(PromotionEngine.champion(l.read()).rules, [c.rule])
        l.append(PromotionEngine.line("rollback", area: "personal_finance", ref: nil, generation: 2,
                                      PromotionInfo(champion_generation: 2, rules_before: [c.rule], rules_after: []), reason: "rb"))
        XCTAssertEqual(PromotionEngine.champion(l.read()).generation, 2); XCTAssertEqual(PromotionEngine.champion(l.read()).rules, [])
        XCTAssertTrue(DecisionLedger.verify(l.read()).ok)
        XCTAssertTrue(l.read().allSatisfy { $0.signature != nil })
    }
    @MainActor func testLosingCandidateCannotBePromotedEvenWithSignature() throws {
        // engine-level: principal approve on a failed evaluation writes the decision but no promotion
        let e = RouterEngine(); let gen = e.championGeneration
        let pack = try PromotionEngine.bundledPack(); let c = cands(pack)["ed_triage"]!
        var ev = try PromotionEngine.evaluate(c, champion: [], pack: pack); ev.champion_generation = gen
        let rec = PromotionEngine.line("policy_evaluation", area: "ed_triage", ref: nil, generation: gen, ev, reason: "e")
        e.principal(rec, "approve_once")
        XCTAssertEqual(e.championGeneration, gen); XCTAssertNotNil(e.promoError)
    }
}
