import XCTest

/// iPad 2D crossroads: start screen → Demo → decide → board.
final class PadUITests: XCTestCase {
    override func setUp() { continueAfterFailure = false }
    func testDemoFlowOnPad() {
        // isolate from state left by other tests (registry, game mode, sidebar overlay)
        let app = XCUIApplication(); app.launchArguments += ["-freshRegistry", "-hideSidebar", "-focus", "-noBridge"]; app.launch(); XCUIDevice.shared.orientation = .landscapeLeft
        let demo = app.buttons["Demo"]
        XCTAssertTrue(demo.waitForExistence(timeout: 20)); demo.tap()
        let pass = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Pass' OR label BEGINSWITH 'Sign off' OR label BEGINSWITH 'Acknowledge'")).firstMatch
        XCTAssertTrue(pass.waitForExistence(timeout: 30), "Now card did not appear")
        XCTAssertTrue(app.buttons["openBoard"].exists, "results strip missing")
        pass.tap()
        let rate = app.buttons["Rate trust"].firstMatch
        if rate.waitForExistence(timeout: 20), rate.isHittable { rate.tap(); XCTAssertTrue(app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS 'Reliability'")).firstMatch.waitForExistence(timeout: 15), "reliability panel missing") }
        app.buttons["openBoard"].firstMatch.tap()
        XCTAssertTrue(app.buttons["Reset demo"].waitForExistence(timeout: 10), "board did not open")
    }

    private func shot(_ name: String) {
        let png = XCUIScreen.main.screenshot().pngRepresentation
        let a = XCTAttachment(screenshot: XCUIScreen.main.screenshot()); a.name = name; a.lifetime = .keepAlways; add(a)
        if let dir = ProcessInfo.processInfo.environment["SHOT_DIR"] { try? png.write(to: URL(fileURLWithPath: dir).appendingPathComponent("\(name).png")) }
    }
    /// screenshot walk-through: portrait + landscape card, detail, ring sheet, board
    func testScreens() {
        let app = XCUIApplication(); app.launch()
        XCUIDevice.shared.orientation = .portrait
        XCTAssertTrue(app.buttons["Demo"].waitForExistence(timeout: 20)); app.buttons["Demo"].tap()
        XCTAssertTrue(app.buttons["Rate trust"].firstMatch.waitForExistence(timeout: 30)); sleep(4)
        shot("ipad_02_portrait_card")
        XCUIDevice.shared.orientation = .landscapeLeft; sleep(3)
        shot("ipad_03_landscape_card")
        app.buttons["Rate trust"].firstMatch.tap(); sleep(2); shot("ipad_04_landscape_reliability")
        app.buttons["Ask next"].firstMatch.tap(); sleep(2); shot("ipad_05_landscape_asknext")
        let mod = app.buttons["Modify…"].firstMatch
        if mod.waitForExistence(timeout: 5) { mod.tap(); sleep(2); shot("ipad_06_change_sheet")
            if app.buttons["decline"].waitForExistence(timeout: 3) { app.buttons["decline"].tap() } else { app.swipeDown() }
            sleep(3); shot("ipad_07_after_decision") }
        for _ in 0..<3 {
            let p = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Pass' OR label BEGINSWITH 'Sign off' OR label BEGINSWITH 'Acknowledge'")).firstMatch
            if p.waitForExistence(timeout: 15) { p.tap(); sleep(2) }
        }
        shot("ipad_08_escalation_or_next")
        app.buttons["openBoard"].firstMatch.tap(); sleep(2); shot("ipad_09_board_landscape")
        XCUIDevice.shared.orientation = .portrait; sleep(3); shot("ipad_10_board_portrait")
    }

    /// WERIAM Principal (bridge forced offline → seeded cards, nothing sent): start → card → Modify → Approve once → board
    func testWERIAMPrincipalOffline() {
        let app = XCUIApplication(); app.launchArguments = ["-noBridge", "-freshRegistry", "-hideSidebar"]; app.launch()
        XCUIDevice.shared.orientation = .landscapeLeft
        let w = app.buttons["WERIAM Principal"]
        XCTAssertTrue(w.waitForExistence(timeout: 20)); w.tap()
        let card = app.staticTexts.matching(NSPredicate(format: "label CONTAINS 'Retire the watcher' OR label CONTAINS 'Foundation rebuild'")).firstMatch
        if !card.waitForExistence(timeout: 20) { shot("weriam_fail_card"); XCTFail("principal card missing"); return }
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS 'bridge offline'")).firstMatch.exists, "offline chip missing")
        sleep(2)
        let mod = app.buttons["Modify…"].firstMatch
        XCTAssertTrue(mod.waitForExistence(timeout: 10)); mod.tap()
        let ap = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Approve once'")).firstMatch
        if !ap.waitForExistence(timeout: 8) { shot("weriam_fail_ring"); XCTFail("Approve once option missing"); return }
        ap.tap()
        sleep(3)
        app.buttons["openBoard"].firstMatch.tap()
        XCTAssertTrue(app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS 'Approved once'")).firstMatch.waitForExistence(timeout: 10), "board did not open")
    }
}
