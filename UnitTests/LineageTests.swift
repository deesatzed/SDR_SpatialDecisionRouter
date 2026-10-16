import XCTest
import CryptoKit
@testable import SpatialDecisionRouter

final class LineageTests: XCTestCase {
    override func tearDown() { TestTemp.cleanup(); super.tearDown() }
    private func ledger() -> (DecisionLedger, URL) {
        let u = TestTemp.url("lin")
        return (DecisionLedger(url: u, signer: LedgerSigner(key: Curve25519.Signing.PrivateKey())), u)
    }
    private let K = "symbiosis:personal_finance"
    private func dec(_ l: DecisionLedger, agent: String = "A", human: String = "A", outcome: String = "A", severity: String = "normal", key: String? = nil) -> UnifiedDecisionRecord {
        var r = UnifiedDecisionRecord(kind: "decision", id: UUID().uuidString, ref_id: nil, timestamp: DecisionLedger.iso(), domain: key ?? K,
                                      context_id: "c", dial_snapshot: nil, generation: 0, signer_key_id: "", signer_pub: "", ledger_prev: "")
        r.card_payload = ["severity": severity, "title": "t"]
        r.agent_proposal = AgentProposal(answer: agent, confidence: 0.7)
        r.human_decision = HumanDecision(label: "pass", answer: human, gesture: "pass", changed: human != agent, decided_by: "human")
        r.outcome = RecordOutcome(value: outcome, source: "test", observed_at: DecisionLedger.iso())
        r.escalation_flags = []
        return l.append(r)!
    }
    /// a small demo-like session: decisions, override, spot-check, dial move, discarded + promoted candidate, rollback
    private func session() throws -> DecisionLedger {
        let (l, _) = ledger()
        for _ in 0..<4 { _ = dec(l) }
        let ov = dec(l, agent: "A", human: "B", outcome: "B")
        var s = UnifiedDecisionRecord.amendment(kind: "spot_check", ref: ov)
        s.spot_check = SpotCheckInfo(human_call: "B", agent_pick: "A", outcome: "B", human_correct: true, agent_correct: false, hidden: ["ai_column"], trigger: "test")
        l.append(s)
        var c = SymbiosisSeeds.finance
        if let m = DialEngine.evaluate(key: K, current: c, recs: l.read()) { l.append(DialEngine.record(key: K, contextId: "c", move: m, generation: 1)); c.dials = m.after }
        _ = dec(l, agent: "Escalate", human: "Escalate", outcome: "Alternative plan", severity: "critical", key: "symbiosis:ed_triage")
        let pack = try PromotionEngine.bundledPack()
        let cands = PromotionEngine.critic(train: PromotionEngine.bundledTrain(), champion: [], exclude: Set(pack.answers.values.map(\.source_id)))
        for cd in cands {
            let p = l.append(PromotionEngine.line("policy_proposal", area: cd.rule.area, ref: nil, generation: 0, PromotionInfo(rule: cd.rule, critic: cd.critic), reason: "p", evidence: Array(cd.evidence.prefix(3))))!
            let ev = l.append(PromotionEngine.line("policy_evaluation", area: cd.rule.area, ref: p.id, generation: 0, try PromotionEngine.evaluate(cd, champion: [], pack: pack), reason: "e"))!
            if ev.promo?.verdict == "passed" {
                let d = l.append(PromotionEngine.line("principal_decision", area: cd.rule.area, ref: ev.id, generation: 0, PromotionInfo(rule: cd.rule, decision: "approve_once"), reason: "a"))!
                l.append(PromotionEngine.line("promotion", area: cd.rule.area, ref: d.id, generation: 1, PromotionInfo(rule: cd.rule, champion_generation: 1, rules_before: [], rules_after: [cd.rule]), reason: "PROMOTED"))
                l.append(PromotionEngine.line("rollback", area: cd.rule.area, ref: nil, generation: 2, PromotionInfo(champion_generation: 2, rules_before: [cd.rule], rules_after: []), reason: "ROLLBACK"))
            }
        }
        return l
    }

    func testReconstructionMatchesLedger() throws {
        let recs = try session().read()
        let fin = LineageBuilder.build(area: K, recs: recs)
        let want = recs.filter { $0.domain == K && LineageBuilder.eventKinds.contains($0.kind) }.map(\.id)
        XCTAssertEqual(fin.events.filter { $0.kind != "critical_miss" }.map(\.id), want, "every signed event, in ledger order")
        XCTAssertTrue(fin.chainOK); XCTAssertTrue(fin.events.allSatisfy(\.ok))
        XCTAssertEqual(fin.decisions, 5); XCTAssertEqual(fin.overrideSeries.last?.successes, 1); XCTAssertEqual(fin.sharpSeries.last?.n, 1)
        XCTAssertEqual(fin.championGeneration, 2); XCTAssertTrue(fin.champion.isEmpty)
        XCTAssertEqual(Set(fin.events.map(\.kind)), ["spot_check", "policy_proposal", "evaluation_passed", "principal_decision", "promotion", "rollback"])
        XCTAssertEqual(fin.events.first { $0.kind == "promotion" }?.championGeneration, 1)
        let ed = LineageBuilder.build(area: "symbiosis:ed_triage", recs: recs)
        XCTAssertEqual(ed.criticalMisses, 1)
        XCTAssertTrue(ed.events.contains { $0.kind == "discarded" && $0.detail.contains("clinical guard") })
    }
    func testChainStatusDisplay() throws {
        let l = try session(); var recs = l.read()
        XCTAssertTrue(LineageBuilder.lineStatus(recs).status.allSatisfy { $0 == "verified" })
        recs[3].timestamp = "1999-01-01T00:00:00Z"   // tamper one line
        let st = LineageBuilder.lineStatus(recs)
        XCTAssertFalse(st.ok)
        XCTAssertEqual(Array(st.status.prefix(3)), ["verified", "verified", "verified"])
        XCTAssertEqual(st.status[3], "bad signature")
        XCTAssertTrue(st.status[4].hasPrefix("after chain break"))
        let lin = LineageBuilder.build(area: K, recs: recs)
        XCTAssertFalse(lin.chainOK); XCTAssertTrue(lin.events.contains { !$0.ok })
        XCTAssertTrue(LineageBuilder.markdown(lin).contains("✗"))
    }
    func testMarkdownExportMatchesLedger() throws {
        let recs = try session().read()
        let lin = LineageBuilder.build(area: K, recs: recs), md = LineageBuilder.markdown(lin)
        XCTAssertTrue(md.hasPrefix("# Lineage · \(K)"))
        XCTAssertTrue(md.contains("chain ✓ verified")); XCTAssertTrue(md.contains("Champion generation: 2"))
        for e in lin.events { XCTAssertTrue(md.contains(String(e.hash.prefix(10))), "event \(e.kind) missing from markdown") }
        let rows = md.split(separator: "\n").filter { $0.hasPrefix("| ") && !$0.hasPrefix("| line") }
        XCTAssertEqual(rows.count, lin.events.count)
    }
    func testHardTriggerNeverSpotChecked() {
        // forced, demo, eligible, every-1, roll: still nil on a hard-trigger card
        XCTAssertNil(RouterEngine.sharpDecision(hardTrigger: true, demo: true, forced: true, detail: 99, detailMin: 85, every: 1, eligibleCount: 1, roll: true, rate: 1))
        XCTAssertNil(RouterEngine.sharpDecision(hardTrigger: true, demo: false, forced: false, detail: 99, detailMin: 85, every: nil, eligibleCount: 1, roll: true, rate: 1))
        XCTAssertNotNil(RouterEngine.sharpDecision(hardTrigger: false, demo: true, forced: true, detail: 85, detailMin: 85, every: nil, eligibleCount: 0, roll: false, rate: 0.3))
        XCTAssertNotNil(RouterEngine.sharpDecision(hardTrigger: false, demo: false, forced: false, detail: 90, detailMin: 85, every: 2, eligibleCount: 4, roll: false, rate: 0.3))
        XCTAssertNil(RouterEngine.sharpDecision(hardTrigger: false, demo: false, forced: false, detail: 80, detailMin: 85, every: 1, eligibleCount: 1, roll: true, rate: 1))
    }
}
