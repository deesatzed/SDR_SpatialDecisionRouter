import XCTest
@testable import SpatialDecisionRouter

final class HomeHealthMindTests: XCTestCase {
    override func tearDown() {
        TestTemp.cleanup()
        super.tearDown()
    }

    func testStrokeStaysADifferentialAndActsBeforeClosure() {
        let mind = HomeHealthMind.of([
            "route": "urgent_page",
            "tier": "ABSOLUTE",
            "reason": "new_focal_deficit",
            "plain_reason": "new one-sided weakness, facial droop or speech change; possible stroke",
            "note": "His right arm has just gone weak and his speech is slurred.",
            "goals": "not recorded",
            "pmh": "ischemic stroke 3 years ago",
            "meds": "apixaban 5 mg BID",
        ])
        XCTAssertGreaterThanOrEqual(mind.differential.count, 2)
        XCTAssertFalse(mind.differential.joined(separator: " ").lowercased() == "stroke")
        XCTAssertTrue(mind.differential.contains("ischemic stroke"))
        XCTAssertTrue(mind.differential.contains("stroke mimic"))
        XCTAssertTrue(mind.actBeforeClosure)
        XCTAssertFalse(mind.agentRefused)
        XCTAssertFalse(mind.blocksEscalation)
        XCTAssertEqual(mind.goalsKind, "unstated")
        XCTAssertEqual(mind.flipRoute, "provider_task")
        XCTAssertFalse(mind.waitFor.isEmpty)
        XCTAssertEqual(mind.waitMinutes, 10)
        XCTAssertTrue(mind.waitTitle.contains("10m"))
    }

    func testClearedArtifactDoesNotForceActionAndKeepsHypoxemiaOnTheList() {
        let mind = HomeHealthMind.of([
            "route": "silent_log",
            "reason": "cleared_by_repeat",
            "tier": "SUPPRESSED",
            "note": "Spouse says he is sitting, breathing normally.",
            "trend": "Day 0 watch SpO2 86% with motion. Fingertip 95%.",
            "artifact_flags": "motion during SpO2 sample",
            "goals": "wants hospital care if needed, prefers to stay at home",
            "baseline": "spo2_night_min 93",
        ])
        XCTAssertFalse(mind.actBeforeClosure)
        XCTAssertTrue(mind.differential.contains("motion or contact artifact"))
        XCTAssertTrue(mind.differential.contains("true hypoxemia"))
        XCTAssertEqual(mind.flipRoute, "urgent_page")
        XCTAssertEqual(mind.waitMinutes, 30)
        XCTAssertEqual(mind.goalsKind, "hospital_if_needed")
        XCTAssertFalse(mind.blocksEscalation)
    }

    func testComfortGoalsConstrainEscalationAndTheWaitFlipsToANurse() {
        let fields = [
            "route": "nurse_task",
            "reason": "goals_of_care",
            "goals": "comfort-focused, enrolled in home hospice, prefers to remain at home",
            "note": "Aide found the patient on the floor. Comfortable. Hospice aide present.",
            "meds": "apixaban 5 mg BID",
            "trend": "bed-sensor impact",
        ]
        let mind = HomeHealthMind.of(fields)
        XCTAssertTrue(mind.blocksEscalation)
        XCTAssertEqual(mind.goalsKind, "comfort")
        XCTAssertEqual(mind.flipRoute, "nurse_task")
        XCTAssertEqual(mind.waitMinutes, 240)
        XCTAssertTrue(mind.waitTitle.contains("4h"))
        XCTAssertTrue(mind.actBeforeClosure)
        XCTAssertGreaterThanOrEqual(mind.differential.count, 2)
        XCTAssertEqual(HomeHealthVocabulary.suggested(role: .bedside, route: "urgent_page", fields: fields.merging(["route": "urgent_page"]) { _, new in new }).id, "request_nurse_visit")
        XCTAssertTrue(HomeHealthSeat.passTitle(route: "urgent_page", fields: fields).contains("goals constrain"))
    }

    func testDoNotHospitalizeBlocksAPage() {
        let fields = [
            "route": "urgent_page",
            "goals": "do-not-hospitalize, comfort-focused, would refuse ambulance and hospital",
            "note": "Fever and new confusion.",
        ]
        let mind = HomeHealthMind.of(fields)
        XCTAssertTrue(mind.blocksEscalation)
        XCTAssertEqual(mind.goalsKind, "dnh")
        XCTAssertEqual(HomeHealthVocabulary.suggested(role: .nurse, route: "urgent_page", fields: fields).id, "escalate_on_call_nurse")
    }

    func testRefusalBlocksAutoPassAndStampsTheLog() {
        let fields = [
            "route": "urgent_page",
            "mi_refused": "1",
            "mi_refusal": "Notes conflict.",
            "note": "One note says unresponsive. Another says talking.",
            "goals": "not recorded",
        ]
        let mind = HomeHealthMind.of(fields)
        XCTAssertTrue(mind.agentRefused)
        XCTAssertEqual(mind.refusalReason, "Notes conflict.")
        let seat = HomeHealthDomain()
        XCTAssertTrue(seat.blocksAutoPass(item: item(fields)))
        seat.reviewRole = .overseer
        let logged = seat.ledgerFields(item: item(fields))
        XCTAssertEqual(logged["agent_refused"], "1")
        XCTAssertEqual(logged["review_action"], "human_after_refusal")
        XCTAssertEqual(logged["review_role"], "overseer")
        XCTAssertFalse((logged["uncertainty_differential"] ?? "").isEmpty)
    }

    func testOrdinaryOverseerPassOmitsReviewAction() {
        let seat = HomeHealthDomain()
        seat.reviewRole = .overseer
        let logged = seat.ledgerFields(item: item([
            "route": "silent_log",
            "reason": "cleared_by_repeat",
            "goals": "not recorded",
            "note": "breathing normally",
            "trend": "SpO2 95%",
        ]))
        XCTAssertNil(logged["review_action"])
        XCTAssertEqual(logged["agent_refused"], "0")
        XCTAssertEqual(logged["review_role"], "overseer")
        XCTAssertNotNil(logged["goals_constraint"])
        XCTAssertNotNil(logged["uncertainty_differential"])
    }

    func testWaitAndRevisitLandOnTheCardPayload() {
        let fields = [
            "route": "silent_log",
            "mi_prior": "Log only for positional desats",
            "mi_evidence": "Resting SpO2 86%",
            "mi_falsifies": "1",
            "mi_wait_for": "temperature and resting SpO2 over 6 hours",
            "mi_flip_route": "nurse_task",
            "mi_flip_if": "temperature reaches 38.5 C",
            "goals": "not recorded",
            "note": "cough",
        ]
        let mind = HomeHealthMind.of(fields)
        XCTAssertTrue(mind.falsifiesPrior)
        XCTAssertEqual(mind.revisitLine.contains("Revise"), true)
        XCTAssertTrue(mind.revisitLine.contains("Log only"))
        let seat = HomeHealthDomain()
        seat.reviewRole = .nurse
        seat.armWait()
        let waited = seat.ledgerFields(item: item(fields))
        XCTAssertEqual(waited["review_action"], "voi_wait")
        XCTAssertEqual(waited["voi_observation"], mind.waitFor)
        XCTAssertEqual(waited["voi_flip_route"], "nurse_task")
        XCTAssertEqual(waited["voi_flip_if"], mind.flipIf)
        XCTAssertEqual(mind.waitMinutes, 360)
        XCTAssertTrue(mind.waitTitle.contains("6h"))
        XCTAssertEqual(waited["voi_wait_minutes"], "360")
        XCTAssertEqual(waited["voi_wait_deadline"], "360")
        XCTAssertNotNil(HomeHealthWaitClock.parseISO(waited["voi_wait_deadline_iso"] ?? ""))
        XCTAssertTrue((waited["recipient"] ?? "").contains("6h"))
        seat.clearArms()
        seat.reviewRole = .overseer
        seat.armRevisit()
        let revised = seat.ledgerFields(item: item(fields))
        XCTAssertEqual(revised["revisit"], "1")
        XCTAssertEqual(revised["review_action"], "revisit_prior")
        XCTAssertEqual(revised["prior_decision"], "Log only for positional desats")
        XCTAssertEqual(revised["new_evidence"], "Resting SpO2 86%")
        seat.decided(item: item(fields), link: LinkSpec(id: "route", source: "layer1", dest: "routes", question: "Route", answerType: .category, options: ["silent_log"]), answer: "nurse_task", latency: 0, by: "human")
        XCTAssertFalse(seat.pendingRevisit)
        XCTAssertNil(seat.pendingReviewAction)
    }

    func testBedsideRevisitKeepsTheVerbAndTheFlag() {
        let fields = [
            "route": "nurse_task",
            "mi_prior": "Log only",
            "mi_evidence": "Resting SpO2 86%",
            "mi_falsifies": "1",
            "goals": "not recorded",
        ]
        let seat = HomeHealthDomain()
        seat.reviewRole = .bedside
        seat.armRevisit()
        seat.pendingReviewAction = "page_on_call"
        let logged = seat.ledgerFields(item: item(fields))
        XCTAssertEqual(logged["revisit"], "1")
        XCTAssertEqual(logged["review_action"], "page_on_call")
        XCTAssertEqual(logged["review_role"], "bedside")
    }

    func testWaitClockParsesTextAndFallsBackToAVisibleDefault() {
        XCTAssertEqual(HomeHealthWaitClock.parseMinutes("temperature and resting SpO2 over 6 hours"), 360)
        XCTAssertEqual(HomeHealthWaitClock.parseMinutes("pain is still there after 10 minutes"), 10)
        XCTAssertEqual(HomeHealthWaitClock.parseMinutes("back in a few minutes"), 10)
        XCTAssertNil(HomeHealthWaitClock.parseMinutes("temperature reaches 38.5 C or SpO2 leaves the band"))
        XCTAssertEqual(HomeHealthWaitClock.faceLabel(minutes: 360), "6h")
        XCTAssertEqual(HomeHealthWaitClock.faceLabel(minutes: 90), "1h 30m")
        XCTAssertEqual(HomeHealthWaitClock.remaining(now: 0, deadline: 360), "6h left")
        XCTAssertEqual(HomeHealthWaitClock.remaining(now: 350, deadline: 360), "10m left")
        XCTAssertEqual(HomeHealthWaitClock.remaining(now: 360, deadline: 360), "OVERDUE")
        let past = Date().addingTimeInterval(-30)
        XCTAssertTrue(HomeHealthWaitClock.isOverdue(domainNow: 0, deadlineMinutes: 360, wallNow: Date(), deadlineWall: past))
        XCTAssertFalse(HomeHealthWaitClock.isOverdue(domainNow: 1, deadlineMinutes: 360, wallNow: Date(), deadlineWall: Date().addingTimeInterval(3600)))

        let chest = HomeHealthMind.of([
            "route": "urgent_page",
            "reason": "ANGINA",
            "meds": "glyceryl trinitrate spray",
            "note": "Chest tightness after one spray.",
            "goals": "not recorded",
        ])
        XCTAssertEqual(chest.waitMinutes, 10)
        XCTAssertTrue(chest.waitTitle.contains("10m"))

        let explicit = HomeHealthMind.of([
            "route": "silent_log",
            "mi_wait_for": "temperature and resting SpO2 over 6 hours",
            "mi_wait_minutes": "15",
            "mi_flip_if": "after 10 minutes",
            "goals": "not recorded",
            "note": "cough",
        ])
        XCTAssertEqual(explicit.waitMinutes, 15)

        let plain = HomeHealthMind.of([
            "route": "provider_task",
            "note": "Routine check. No new complaint.",
            "goals": "not recorded",
        ])
        XCTAssertEqual(plain.waitMinutes, 240)
        XCTAssertTrue(plain.waitTitle.contains("4h"))
        XCTAssertFalse(plain.waitOverdue)
    }

    func testOverdueWaitBlocksAutoPassAndStampsTheRecheckPayload() {
        var fields = [
            "route": "silent_log",
            "mi_wait_for": "temperature and resting SpO2 over 6 hours",
            "mi_flip_route": "nurse_task",
            "mi_flip_if": "temperature reaches 38.5 C",
            "goals": "not recorded",
            "note": "cough",
        ]
        let seat = HomeHealthDomain()
        XCTAssertFalse(seat.blocksAutoPass(item: item(fields)))
        fields["voi_wait_overdue"] = "1"
        fields["voi_recheck"] = "1"
        let mind = HomeHealthMind.of(fields)
        XCTAssertTrue(mind.waitOverdue)
        XCTAssertTrue(mind.waitTitle.contains("OVERDUE"))
        XCTAssertTrue(mind.overdueLine.contains("did not arrive"))
        XCTAssertTrue(seat.blocksAutoPass(item: item(fields)))
        let context = HomeHealthWaitClock.recheckContext([
            "review_action": "voi_wait",
            "voi_observation": mind.waitFor,
            "voi_wait_minutes": "360",
            "voi_wait_deadline": "360",
            "route": "silent_log",
        ], observation: mind.waitFor)
        XCTAssertEqual(context["review_action"], "voi_recheck")
        XCTAssertEqual(context["voi_wait_overdue"], "1")
        XCTAssertEqual(context["voi_recheck"], "1")
        XCTAssertEqual(context["voi_wait_minutes"], "360")
        XCTAssertEqual(context["route"], "silent_log")
    }

    func testOverdueWaitReturnsToNowWithoutPaging() {
        let seat = HomeHealthDomain()
        let engine = RouterEngine(ledger: TestTemp.ledger("wait-recheck"))
        engine.start(seat)
        let fields = [
            "home_health": "1",
            "case_id": "T-WAIT",
            "route": "urgent_page",
            "reason": "ANGINA",
            "meds": "glyceryl trinitrate spray",
            "mi_wait_minutes": "10",
            "mi_wait_for": "whether one spray eases it",
            "mi_flip_route": "urgent_page",
            "mi_flip_if": "pain is still there after 10 minutes",
            "goals": "not recorded",
            "note": "Chest tightness.",
        ]
        let caseItem = item(fields)
        engine.items[caseItem.id] = caseItem
        let link = LinkSpec(
            id: "route", source: "layer1", dest: "routes", question: "Route",
            answerType: .category, options: ["silent_log", "nurse_task", "provider_task", "urgent_page"],
            firesAlert: true, alertNegative: ["silent_log", "nurse_task", "provider_task"],
            costWeight: 1, alertDest: "urgent")
        let handoff = Handoff(
            id: "\(caseItem.id)-route", itemId: caseItem.id, link: link, proposal: "urgent_page",
            confidence: 0.5, groundTruth: nil, upstream: [:], capacity: [:], capacityLine: "",
            priority: 1, createdAt: Date(), emittedAtMin: 0)
        engine.handoffs = [handoff]
        engine.phase[handoff.id] = .waiting
        engine.progress[handoff.id] = 1
        seat.armWait()
        engine.pass(handoff.id)

        let waited = engine.decisions.last
        XCTAssertEqual(waited?.context["review_action"], "voi_wait")
        XCTAssertEqual(waited?.context["voi_wait_minutes"], "10")
        XCTAssertEqual(waited?.context["voi_wait_deadline"], "10")
        XCTAssertEqual(engine.destFor[handoff.id], "routes")
        XCTAssertEqual(engine.alertsFired, 0)
        XCTAssertEqual(engine.homeOpenWaits[caseItem.id]?.minutes, 10)
        XCTAssertEqual(engine.homeWaitFace[caseItem.id], "10m left")

        engine.tick(3)
        XCTAssertEqual(engine.phase[handoff.id], .delivered)
        XCTAssertNil(engine.itemStatus[caseItem.id])
        XCTAssertEqual(engine.alertsFired, 0)
        XCTAssertNotNil(engine.homeOpenWaits[caseItem.id])

        seat.advance(minutes: 20)
        engine.recheckHomeWaits()
        XCTAssertEqual(engine.phase[handoff.id], .waiting)
        XCTAssertEqual(engine.nowId, handoff.id)
        XCTAssertEqual(engine.alertsFired, 0)
        XCTAssertNil(engine.destFor[handoff.id])
        XCTAssertEqual(engine.decisions.last?.gesture, "recheck")
        XCTAssertEqual(engine.decisions.last?.decidedBy, "system")
        XCTAssertEqual(engine.decisions.last?.context["review_action"], "voi_recheck")
        XCTAssertEqual(engine.decisions.last?.context["voi_wait_overdue"], "1")
        XCTAssertEqual(engine.decisions.last?.routedAnswer, "urgent_page")
        XCTAssertEqual(engine.items[caseItem.id]?.fields["voi_recheck"], "1")
        XCTAssertTrue(engine.items[caseItem.id]?.fields["wait_overdue_line"]?.contains("OVERDUE") == true)
        XCTAssertTrue(seat.blocksAutoPass(item: engine.items[caseItem.id]!))
        XCTAssertEqual(engine.homeOpenWaits[caseItem.id]?.surfaced, true)
    }

    func testALaterPassClearsTheWaitBeforeTheWindow() {
        let seat = HomeHealthDomain()
        let engine = RouterEngine(ledger: TestTemp.ledger("wait-resolved"))
        engine.start(seat)
        let fields = [
            "home_health": "1",
            "case_id": "T-WAIT-2",
            "route": "silent_log",
            "mi_wait_minutes": "30",
            "mi_wait_for": "the next resting waveform",
            "goals": "not recorded",
            "note": "breathing normally",
        ]
        let caseItem = item(fields)
        engine.items[caseItem.id] = caseItem
        let link = LinkSpec(
            id: "route", source: "layer1", dest: "routes", question: "Route",
            answerType: .category, options: ["silent_log", "nurse_task", "provider_task", "urgent_page"],
            firesAlert: true, alertNegative: ["silent_log", "nurse_task", "provider_task"],
            costWeight: 1, alertDest: "urgent")
        let handoff = Handoff(
            id: "\(caseItem.id)-route", itemId: caseItem.id, link: link, proposal: "silent_log",
            confidence: 0.5, groundTruth: nil, upstream: [:], capacity: [:], capacityLine: "",
            priority: 1, createdAt: Date(), emittedAtMin: 0)
        engine.handoffs = [handoff]
        engine.phase[handoff.id] = .waiting
        engine.progress[handoff.id] = 1
        seat.armWait()
        engine.pass(handoff.id)
        XCTAssertNotNil(engine.homeOpenWaits[caseItem.id])

        engine.phase[handoff.id] = .waiting
        seat.clearArms()
        engine.pass(handoff.id)
        XCTAssertNil(engine.homeOpenWaits[caseItem.id])
        seat.advance(minutes: 400)
        engine.recheckHomeWaits()
        XCTAssertFalse(engine.decisions.contains { $0.gesture == "recheck" })
        XCTAssertNil(engine.items[caseItem.id]?.fields["voi_wait_overdue"])
    }

    private func item(_ fields: [String: String]) -> DomainItem {
        DomainItem(id: fields["case_id"] ?? "T", fields: fields, displayLine: "t", shortLine: "t", historyLine: "", arrivalTime: 0)
    }
}
