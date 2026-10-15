import XCTest
import CryptoKit
@testable import SpatialDecisionRouter

final class DialEngineTests: XCTestCase {
    private func ledger() -> DecisionLedger {
        DecisionLedger(url: FileManager.default.temporaryDirectory.appendingPathComponent("dial-\(UUID().uuidString).jsonl"),
                       signer: LedgerSigner(key: Curve25519.Signing.PrivateKey()))
    }
    /// one graded decision; agentRight decides whether the agent's proposal matched the outcome
    @discardableResult
    private func dec(_ l: DecisionLedger, key: String, agentRight: Bool, critical: Bool = false, split: SplitRating? = nil, outcome: Bool = true) -> UnifiedDecisionRecord {
        let truth = "A"
        var r = UnifiedDecisionRecord(kind: "decision", id: UUID().uuidString, ref_id: nil, timestamp: DecisionLedger.iso(), domain: key,
                                      context_id: "c", dial_snapshot: nil, generation: 0, signer_key_id: "", signer_pub: "", ledger_prev: "")
        r.card_payload = critical ? ["severity": "critical"] : [:]
        r.agent_proposal = AgentProposal(answer: agentRight ? truth : "B", confidence: 0.7)
        r.human_decision = HumanDecision(label: "pass", answer: truth, gesture: "pass", changed: false, decided_by: "human")
        r.outcome = outcome ? RecordOutcome(value: truth, source: "test", observed_at: DecisionLedger.iso()) : nil
        r.split_rating = split?.rawValue
        r.escalation_flags = []
        return l.append(r)!
    }
    private func step(_ l: DecisionLedger, _ key: String, _ cur: inout SymbiosisContext) -> DialMove? {
        guard let m = DialEngine.evaluate(key: key, current: cur, recs: l.read()) else { return nil }
        l.append(DialEngine.record(key: key, contextId: "c", move: m, generation: cur.generation + 1))
        cur.dials = m.after; cur.generation += 1
        return m
    }

    func testNoMoveBelowMinN() {
        let l = ledger(); var c = SymbiosisSeeds.finance
        for _ in 0..<4 { dec(l, key: "k", agentRight: true) }
        XCTAssertNil(step(l, "k", &c), "4 < minN must not move")
    }
    func testSelfRatingsAloneNeverMove() {
        let l = ledger(); var c = SymbiosisSeeds.finance
        for _ in 0..<8 { dec(l, key: "k", agentRight: true, split: .buried_me, outcome: false) }
        XCTAssertNil(step(l, "k", &c), "split ratings without outcomes must not move dials")
    }
    func testRiseAfterNCorrectGraded() {
        let l = ledger(); var c = SymbiosisSeeds.finance
        for _ in 0..<5 { dec(l, key: "k", agentRight: true) }
        let m = step(l, "k", &c)
        XCTAssertEqual(m?.after.autonomy_horizon, SymbiosisSeeds.finance.dials.autonomy_horizon + 5)
        XCTAssertEqual(m?.after.deference, SymbiosisSeeds.finance.dials.deference - 5)
        XCTAssertEqual(m?.posterior?.n, 5); XCTAssertEqual(m?.evidence.count, 5)
        XCTAssertNil(step(l, "k", &c), "window resets after a move")
        XCTAssertTrue(DecisionLedger.verify(l.read()).ok)
    }
    func testMixedEvidenceHolds() {
        let l = ledger(); var c = SymbiosisSeeds.finance
        for i in 0..<6 { dec(l, key: "k", agentRight: i % 2 == 0) }
        XCTAssertNil(step(l, "k", &c), "3/6 is inconclusive: no move")
    }
    func testLowerOnPoorRecord() {
        let l = ledger(); var c = SymbiosisSeeds.finance
        for _ in 0..<6 { dec(l, key: "k", agentRight: false) }
        XCTAssertEqual(step(l, "k", &c)?.after.autonomy_horizon, SymbiosisSeeds.finance.dials.autonomy_horizon - 5)
    }
    func testCriticalMissDemotesImmediately() {
        let l = ledger(); var c = SymbiosisSeeds.finance
        dec(l, key: "k", agentRight: true)
        let miss = dec(l, key: "k", agentRight: false, critical: true)
        let m = step(l, "k", &c)
        XCTAssertEqual(m?.demotion, true); XCTAssertEqual(m?.evidence, [miss.id])
        XCTAssertEqual(m?.after.autonomy_horizon, SymbiosisSeeds.finance.dials.autonomy_horizon - 15)
        let rec = l.read().last!
        XCTAssertEqual(rec.kind, "dial_change"); XCTAssertEqual(rec.escalation_flags, ["demotion"]); XCTAssertNotNil(rec.signature)
    }
    func testClinicalCapsNeverExceeded() {
        let l = ledger(); var c = SymbiosisSeeds.clinical
        for _ in 0..<4 { for _ in 0..<5 { dec(l, key: "e", agentRight: true) }; _ = step(l, "e", &c) }
        XCTAssertLessThanOrEqual(c.dials.autonomy_horizon, 40); XCTAssertGreaterThanOrEqual(c.dials.deference, 80)
        XCTAssertEqual(c.dials.autonomy_horizon, 40); XCTAssertEqual(c.dials.deference, 80)
        // deference can earn its way down to the floor (90→85→80); after that every rise is a no-op and writes nothing
        XCTAssertEqual(l.read().filter { $0.kind == "dial_change" }.count, 2)
    }
    func testSplitNudgesOnlyWithGradedWindow() {
        let l = ledger(); var c = SymbiosisSeeds.finance
        for _ in 0..<5 { dec(l, key: "k", agentRight: true, split: .buried_me) }
        let m = step(l, "k", &c)
        XCTAssertEqual(m?.after.detail_absorption, SymbiosisSeeds.finance.dials.detail_absorption + 5)
    }
    func testReplayAndRevert() {
        let l = ledger(); var c = SymbiosisSeeds.finance
        for _ in 0..<5 { dec(l, key: "symbiosis:personal_finance", agentRight: true) }
        let m = step(l, "symbiosis:personal_finance", &c)!
        XCTAssertEqual(DialEngine.replay(l.read())["symbiosis:personal_finance"]?.dials, m.after)
        // revert = new signed dial_change restoring the previous dials
        let back = DialMove(before: m.after, after: m.before, reason: "REVERT", evidence: [], posterior: nil, demotion: false)
        l.append(DialEngine.record(key: "symbiosis:personal_finance", contextId: "c", move: back, generation: 2))
        XCTAssertEqual(DialEngine.replay(l.read())["symbiosis:personal_finance"]?.dials.autonomy_horizon, SymbiosisSeeds.finance.dials.autonomy_horizon)
        XCTAssertTrue(DecisionLedger.verify(l.read()).ok)
    }
    func testPosterior() {
        let p = DialEngine.posterior(5, 0)
        XCTAssertEqual(p.mean, 0.857, accuracy: 0.001); XCTAssertGreaterThan(p.lo, 0.6); XCTAssertLessThanOrEqual(p.hi, 1)
    }
}
