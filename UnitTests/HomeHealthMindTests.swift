import XCTest
@testable import SpatialDecisionRouter

final class HomeHealthMindTests: XCTestCase {
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

    private func item(_ fields: [String: String]) -> DomainItem {
        DomainItem(id: fields["case_id"] ?? "T", fields: fields, displayLine: "t", shortLine: "t", historyLine: "", arrivalTime: 0)
    }
}
