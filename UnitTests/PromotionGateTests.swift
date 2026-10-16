import XCTest
import CryptoKit
@testable import SpatialDecisionRouter

/// M6 acceptance: the promotion gate cannot be bypassed. Only `principal(_, "approve_once")` on a fresh,
/// passing, untampered evaluation promotes; everything else writes the human decision but leaves the champion alone.
@MainActor final class PromotionGateTests: XCTestCase {
    private func passingEval(_ e: RouterEngine) throws -> UnifiedDecisionRecord {
        let pack = try PromotionEngine.bundledPack()
        let held = Set(pack.answers.values.map(\.source_id))
        let c = try XCTUnwrap(PromotionEngine.critic(train: PromotionEngine.bundledTrain(), champion: e.champion, exclude: held)
            .first { $0.rule.area == "personal_finance" }, "no personal_finance candidate (champion may already hold it)")
        var ev = try PromotionEngine.evaluate(c, champion: e.champion, pack: pack); ev.champion_generation = e.championGeneration
        XCTAssertEqual(ev.verdict, "passed")
        return PromotionEngine.line("policy_evaluation", area: "personal_finance", ref: nil, generation: e.championGeneration, ev, reason: "t")
    }
    private var dir: URL!
    override func setUp() {
        dir = FileManager.default.temporaryDirectory.appendingPathComponent("gate-\(UUID().uuidString)", isDirectory: true)
    }
    override func tearDown() { try? FileManager.default.removeItem(at: dir); dir = nil }
    /// fresh engine on an isolated temp ledger (never the app's device ledger)
    private func engine() -> RouterEngine {
        let l = DecisionLedger(url: dir.appendingPathComponent("decision_ledger.jsonl"), signer: LedgerSigner(key: Curve25519.Signing.PrivateKey()))
        let e = RouterEngine(ledger: l); e.loadPromotion()
        XCTAssertNotEqual(e.ledger.url, DecisionLedger.defaultURL)
        XCTAssertEqual(e.championGeneration, 0); XCTAssertTrue(e.champion.isEmpty)
        return e
    }
    private func assertNoPromotion(_ e: RouterEngine, _ rec: UnifiedDecisionRecord, _ decision: String, file: StaticString = #filePath, line: UInt = #line) {
        let gen = e.championGeneration, rules = e.champion, n = e.ledgerCount
        e.principal(rec, decision)
        XCTAssertEqual(e.championGeneration, gen, file: file, line: line)
        XCTAssertEqual(e.champion, rules, file: file, line: line)
        XCTAssertFalse(e.ledger.read().suffix(e.ledgerCount - n).contains { $0.kind == "promotion" }, file: file, line: line)
    }

    func testDeclineAndDeferNeverPromoteButAreLogged() throws {
        let e = engine(); let ev = try passingEval(e)
        for d in ["decline", "defer"] {
            let n = e.ledgerCount
            assertNoPromotion(e, ev, d)
            XCTAssertEqual(e.ledger.read().last?.kind, "principal_decision"); XCTAssertEqual(e.ledgerCount, n + 1)
        }
    }
    func testNonEvaluationRecordIsIgnoredEntirely() throws {
        let e = engine(); var ev = try passingEval(e); ev.kind = "policy_proposal"
        let n = e.ledgerCount
        assertNoPromotion(e, ev, "approve_once"); XCTAssertEqual(e.ledgerCount, n)
    }
    func testStaleGenerationRefused() throws {
        let e = engine(); var ev = try passingEval(e); ev.promo?.champion_generation = e.championGeneration - 1
        assertNoPromotion(e, ev, "approve_once"); XCTAssertNotNil(e.promoError)
    }
    func testTamperedEvaluatorShaRefused() throws {
        let e = engine(); var ev = try passingEval(e); ev.promo?.evaluator_sha = String(repeating: "0", count: 64)
        assertNoPromotion(e, ev, "approve_once"); XCTAssertNotNil(e.promoError)
    }
    func testTamperedReplayHashRefused() throws {
        let e = engine(); var ev = try passingEval(e); ev.promo?.cases_sha256 = String(repeating: "f", count: 64)
        assertNoPromotion(e, ev, "approve_once"); XCTAssertNotNil(e.promoError)
    }
    func testForgedVerdictWithoutRuleRefused() throws {
        let e = engine(); var ev = try passingEval(e); ev.promo?.rule = nil
        assertNoPromotion(e, ev, "approve_once")
    }
    func testOnlyApproveOnPassingFreshEvaluationPromotesThenRollbackRestores() throws {
        let e = engine(); let ev = try passingEval(e)
        let gen = e.championGeneration, before = e.champion
        e.principal(ev, "approve_once")
        XCTAssertEqual(e.championGeneration, gen + 1); XCTAssertEqual(e.champion.count, before.count + 1)
        let p = try XCTUnwrap(e.ledger.read().last); XCTAssertEqual(p.kind, "promotion"); XCTAssertNotNil(p.signature)
        // the same approval cannot be replayed: it is now stale
        assertNoPromotion(e, ev, "approve_once")
        e.rollbackChampion()
        XCTAssertEqual(e.championGeneration, gen + 2); XCTAssertEqual(e.champion, before)
        XCTAssertTrue(DecisionLedger.verify(e.ledger.read()).ok)
    }
}
