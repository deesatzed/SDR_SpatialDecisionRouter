import XCTest

/// M4: critic proposal → frozen-replay evaluation → Principal approve → champion generation bump → rollback.
final class PromotionUITests: XCTestCase {
    override func setUp() { continueAfterFailure = false }
    private func shot(_ name: String) {
        let s = XCUIScreen.main.screenshot()
        let a = XCTAttachment(screenshot: s); a.name = name; a.lifetime = .keepAlways; add(a)
        if let dir = ProcessInfo.processInfo.environment["SHOT_DIR"] { try? s.pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent("\(name).png")) }
    }
    private func has(_ app: XCUIApplication, _ text: String, _ t: TimeInterval = 10) -> Bool {
        app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", text)).firstMatch.waitForExistence(timeout: t)
    }
    func testProposalEvalPrincipalApproveRollback() {
        let app = XCUIApplication()
        app.launchArguments += ["-demo", "-symbiosisDemo", "-testLedger", "-freshRegistry", "-hideSidebar", "-focus", "-noBridge"]
        app.launch(); XCUIDevice.shared.orientation = .landscapeLeft
        let open = app.buttons["openPromotions"].firstMatch
        XCTAssertTrue(open.waitForExistence(timeout: 30)); open.tap()
        let run = app.buttons["runCritic"].firstMatch
        XCTAssertTrue(run.waitForExistence(timeout: 10)); XCTAssertTrue(has(app, "CHAMPION gen 0"))
        run.tap()
        XCTAssertTrue(has(app, "DISCARDED"), "losing clinical candidate must be discarded and shown")
        XCTAssertTrue(has(app, "clinical guard"))
        let approve = app.buttons["principal_approve"].firstMatch
        XCTAssertTrue(approve.waitForExistence(timeout: 10), "Principal card missing for the winning candidate")
        XCTAssertTrue(has(app, "PRINCIPAL CARD")); XCTAssertTrue(app.buttons["principal_defer"].exists && app.buttons["principal_decline"].exists)
        sleep(1); shot("m4_01_principal_card")
        approve.tap()
        XCTAssertTrue(has(app, "CHAMPION gen 1"), "generation did not bump")
        XCTAssertTrue(has(app, "Principal: approve_once"))
        sleep(1); shot("m4_02_promoted_gen1")
        let rb = app.buttons["rollback"].firstMatch; XCTAssertTrue(rb.exists); rb.tap()
        XCTAssertTrue(has(app, "CHAMPION gen 2")); XCTAssertTrue(has(app, "seed policy"))
        sleep(1); shot("m4_03_rolled_back_gen2")
    }
}
