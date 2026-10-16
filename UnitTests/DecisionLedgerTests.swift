import XCTest
import CryptoKit
@testable import SpatialDecisionRouter

final class DecisionLedgerTests: XCTestCase {
    override func tearDown() { TestTemp.cleanup(); super.tearDown() }
    private func tmpLedger() -> DecisionLedger {
        let u = TestTemp.url("ledger")
        return DecisionLedger(url: u, signer: LedgerSigner(key: Curve25519.Signing.PrivateKey()))
    }
    private func decision(_ domain: String, gesture: String = "pass", answer: String = "A", proposal: String = "A", truth: String? = "A") -> RoutingDecision {
        var d = RoutingDecision(domain: domain, siteId: "s", registryVersion: 1, itemId: "I1", linkId: "L", sourceAgent: "a", destAgent: "b",
                                question: "Q?", displayLine: "line / with slash · ü", context: ["k": "v"], history: "none", capacity: [:], upstream: [:],
                                proposedAnswer: proposal, proposedConfidence: 0.7345, answerType: .category, options: ["A", "B"], trialOptions: [],
                                routedAnswer: answer, effectiveAnswer: answer, routedIsTrial: false, newCategoryCreated: false, changed: answer != proposal,
                                gesture: gesture, priority: 0.1, latency: 1.2345, shownAt: Date(), decidedAt: Date(), position: Vec3(x: 0, y: 0, z: 0),
                                distanceFromHead: 1, neighbors: [], queueDepth: 0, groundTruth: truth, agreesWithGroundTruth: truth.map { $0 == answer })
        d.decidedBy = "human"
        return d
    }
    private func ctx(_ d: String, dials: DialSnapshot? = SymbiosisSeeds.clinical.dials) -> DecisionContext {
        DecisionContext(domain: d, contextId: "c", dials: dials, generation: 0, reliability: RecordReliability(score: nil, n: 0, label: "placeholder"), outcomeSource: "test")
    }

    func testChainAndSignaturesVerify() {
        let l = tmpLedger()
        let a = l.append(.from(decision("ed_triage"), ctx: ctx("ed_triage"), split: nil))!
        let b = l.append(.from(decision("symbiosis", gesture: "select", answer: "B"), ctx: ctx("symbiosis:ed_triage"), split: .overstepped_me))!
        l.append(.amendment(kind: "outcome", ref: a, outcome: RecordOutcome(value: "A", source: "test", observed_at: DecisionLedger.iso())))
        l.append(.amendment(kind: "split_rating", ref: b, split: .buried_me))
        let recs = l.read()
        XCTAssertEqual(recs.count, 4)
        XCTAssertEqual(recs[0].ledger_prev, DecisionLedger.genesis)
        XCTAssertEqual(recs[1].ledger_prev, recs[0].ledger_hash)
        XCTAssertEqual(recs[1].human_decision?.label, "modify")
        XCTAssertEqual(recs[1].split_rating, "overstepped_me")
        XCTAssertEqual(recs[2].ref_id, a.id)
        XCTAssertTrue(DecisionLedger.verify(recs).ok)
        // reopen continues the chain
        let l2 = DecisionLedger(url: l.url, signer: l.signer)
        XCTAssertEqual(l2.head, recs[3].ledger_hash)
    }

    func testTamperIsDetected() throws {
        let l = tmpLedger()
        l.append(.from(decision("ed_triage"), ctx: ctx("ed_triage"), split: nil))
        l.append(.from(decision("ed_triage", gesture: "flip", answer: "B"), ctx: ctx("ed_triage"), split: nil))
        var recs = l.read()
        recs[0].human_decision?.answer = "B"
        XCTAssertFalse(DecisionLedger.verify(recs).ok)
        recs = l.read(); recs.remove(at: 0)
        XCTAssertFalse(DecisionLedger.verify(recs).ok, "dropping a line must break the chain")
    }

    func testLabelsAndOutcomeMapping() {
        XCTAssertEqual(UnifiedDecisionRecord.decisionLabel(gesture: "pass", changed: false, isNew: false), "pass")
        XCTAssertEqual(UnifiedDecisionRecord.decisionLabel(gesture: "flip", changed: true, isNew: false), "flip")
        XCTAssertEqual(UnifiedDecisionRecord.decisionLabel(gesture: "select", changed: true, isNew: false), "modify")
        XCTAssertEqual(UnifiedDecisionRecord.decisionLabel(gesture: "escalate", changed: true, isNew: false), "escalate")
        let r = UnifiedDecisionRecord.from(decision("weriam_principal", truth: nil), ctx: ctx("weriam_principal"), split: nil)
        XCTAssertNil(r.outcome, "outcome stays null until observed")
        XCTAssertEqual(UnifiedDomainId.of("ai_doc_review"), "ai_tele_doc")
    }

    func testClinicalCapsEnforced() {
        let c = SymbiosisSeeds.clinical
        XCTAssertLessThanOrEqual(c.dials.autonomy_horizon, 40)
        XCTAssertGreaterThanOrEqual(c.dials.deference, 80)
        var bad = c; bad.dials.autonomy_horizon = 99; bad.dials.deference = 10
        let e = bad.enforced()
        XCTAssertEqual(e.dials.autonomy_horizon, 40); XCTAssertEqual(e.dials.deference, 80)
        XCTAssertTrue(c.dials.source.contains("placeholder"))
        XCTAssertLessThanOrEqual(SymbiosisSeeds.teleDoc.dials.autonomy_horizon, 40)
    }

    @MainActor func testSymbiosisDomainSeedsBothAreas() {
        let d = SymbiosisDomain(); d.reset(seed: 1)
        let areas = Set(SymbiosisDomain.seed.map(\.area))
        XCTAssertEqual(areas, ["ed_triage", "personal_finance"])
        for k in SymbiosisDomain.seed { XCTAssertTrue(SymbiosisDomain.options.contains(k.proposal)); XCTAssertTrue(SymbiosisDomain.options.contains(k.scriptedOutcome ?? "")) }
        guard let it = d.nextItem() else { return XCTFail("no item") }
        XCTAssertEqual(d.decisionContext(item: it).domain, "symbiosis:personal_finance")
        XCTAssertEqual(d.decisionContext(item: it).dials, SymbiosisSeeds.finance.dials)
    }

    /// Golden fixture for the Python exporter: tools/tests read this file and must verify the same hashes/signatures.
    func testWriteGoldenFixture() throws {
        guard let out = ProcessInfo.processInfo.environment["LEDGER_GOLDEN_OUT"] else { throw XCTSkip("set LEDGER_GOLDEN_OUT to write fixture") }
        let u = URL(fileURLWithPath: out); try? FileManager.default.removeItem(at: u)
        let l = DecisionLedger(url: u, signer: LedgerSigner(key: Curve25519.Signing.PrivateKey()))
        let a = l.append(.from(decision("ed_triage"), ctx: ctx("ed_triage"), split: nil))!
        l.append(.from(decision("symbiosis", gesture: "select", answer: "B", proposal: "A", truth: "B"), ctx: ctx("symbiosis:personal_finance"), split: .about_right))
        l.append(.amendment(kind: "outcome", ref: a, outcome: RecordOutcome(value: "A", source: "test", observed_at: DecisionLedger.iso())))
        var after = SymbiosisSeeds.finance.dials; after.autonomy_horizon += 5; after.source = DialEngine.earnedSource
        let mv = DialMove(before: SymbiosisSeeds.finance.dials, after: after, reason: "earned: test", evidence: [a.id], posterior: DialEngine.posterior(5, 0), demotion: false)
        l.append(DialEngine.record(key: "symbiosis:personal_finance", contextId: "personal_finance", move: mv, generation: 1))
        var sc = UnifiedDecisionRecord.amendment(kind: "spot_check", ref: a)
        sc.spot_check = SpotCheckInfo(human_call: "B", agent_pick: "A", outcome: nil, human_correct: nil, agent_correct: nil, hidden: ["ai_column", "proposal"], trigger: "test")
        l.append(sc)
        let rule = PolicyRule(area: "personal_finance", when: PolicyWhen(conf_lt: 0.65), answer: "Hold — gather info")
        l.append(PromotionEngine.line("promotion", area: "personal_finance", ref: a.id, generation: 1,
                                      PromotionInfo(rule: rule, verdict: "passed", decision: "approve_once", champion_generation: 1, rules_before: [], rules_after: [rule]),
                                      reason: "PROMOTED by human signature (fixture)"))
        XCTAssertTrue(DecisionLedger.verify(l.read()).ok)
    }
}
