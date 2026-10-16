import XCTest

/// M5: after a demo session (dial rise, spot-checks, demotion) and a promotion, the Lineage tab reconstructs it from the ledger.
final class LineageUITests: XCTestCase {
    override func setUp() { continueAfterFailure = false }
    private func shot(_ name: String) {
        let s = XCUIScreen.main.screenshot()
        let a = XCTAttachment(screenshot: s); a.name = name; a.lifetime = .keepAlways; add(a)
        if let dir = ProcessInfo.processInfo.environment["SHOT_DIR"] { try? s.pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent("\(name).png")) }
    }
    private func has(_ app: XCUIApplication, _ text: String, _ t: TimeInterval = 10) -> Bool {
        app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", text)).firstMatch.waitForExistence(timeout: t)
    }
    func testLineageReconstructsSession() {
        let app = XCUIApplication()
        app.launchArguments += ["-demo", "-symbiosisDemo", "-demoAuto", "-speedup", "3", "-testLedger", "-freshRegistry", "-hideSidebar", "-focus", "-noBridge"]
        app.launch(); XCUIDevice.shared.orientation = .landscapeLeft
        if !has(app, "DEMOTION", 240) { shot("m5_fail_demo"); XCTFail("demo did not reach the demotion"); return }
        let any = app.descendants(matching: .any)
        // promotion (approve) so lineage has a generation
        let openP = app.buttons["openPromotions"].firstMatch; XCTAssertTrue(openP.waitForExistence(timeout: 20)); openP.tap()
        let rc = app.buttons["runCritic"].firstMatch; XCTAssertTrue(rc.waitForExistence(timeout: 15)); rc.tap()
        let approve = app.buttons["principal_approve"].firstMatch; XCTAssertTrue(approve.waitForExistence(timeout: 10)); approve.tap()
        XCTAssertTrue(has(app, "CHAMPION gen 1")); app.buttons["closePromotion"].firstMatch.tap(); sleep(1)
        let openL = app.buttons["openLineage"].firstMatch; XCTAssertTrue(openL.waitForExistence(timeout: 20)); openL.tap()
        XCTAssertTrue(any["lineageView"].waitForExistence(timeout: 10))
        XCTAssertTrue(has(app, "✓ chain verified"))
        XCTAssertTrue(any["lineageEvent_promotion"].firstMatch.exists, "promotion missing")
        XCTAssertTrue(any["lineageEvent_dial_change"].firstMatch.exists, "dial move missing")
        XCTAssertTrue(any["lineageEvent_spot_check"].firstMatch.exists, "spot-check missing")
        XCTAssertTrue(has(app, "gen 1"))
        sleep(1); shot("m5_01_lineage_finance")
        any["lineageEvent_dial_change"].firstMatch.tap()
        XCTAssertTrue(any["eventSignature"].firstMatch.waitForExistence(timeout: 5))
        XCTAssertTrue(has(app, "Ed25519 valid"))
        sleep(1); shot("m5_02_event_evidence_signature")
        app.buttons["area_symbiosis:ed_triage"].firstMatch.tap(); sleep(1)
        XCTAssertTrue(any["lineageEvent_demotion"].firstMatch.waitForExistence(timeout: 5), "demotion missing")
        XCTAssertTrue(any["lineageEvent_discarded"].firstMatch.exists, "discarded candidate missing")
        XCTAssertTrue(any["lineageEvent_critical_miss"].firstMatch.exists, "critical miss missing")
        shot("m5_03_lineage_ed_demotion")
        app.buttons["exportLineage"].firstMatch.tap()
        XCTAssertTrue(has(app, "exported → Documents/lineage/symbiosis_ed_triage.md"))
        app.buttons["area_symbiosis:personal_finance"].firstMatch.tap(); app.buttons["exportLineage"].firstMatch.tap()
        XCTAssertTrue(has(app, "symbiosis_personal_finance.md"))
    }
}
