import XCTest

/// M3: sharpness spot-checks — "Your call first" hides the AI, human calls, reveal + calibration, and a dial effect.
final class SharpnessUITests: XCTestCase {
    override func setUp() { continueAfterFailure = false }
    private func shot(_ name: String) {
        let s = XCUIScreen.main.screenshot()
        let a = XCTAttachment(screenshot: s); a.name = name; a.lifetime = .keepAlways; add(a)
        if let dir = ProcessInfo.processInfo.environment["SHOT_DIR"] { try? s.pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent("\(name).png")) }
    }
    private func has(_ app: XCUIApplication, _ text: String, _ t: TimeInterval) -> Bool {
        app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", text)).firstMatch.waitForExistence(timeout: t)
    }
    private func launch(_ extra: [String]) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments += ["-demo", "-symbiosisDemo", "-freshLedger", "-freshRegistry", "-hideSidebar", "-focus", "-noBridge"] + extra
        app.launch(); XCUIDevice.shared.orientation = .landscapeLeft
        return app
    }
    /// manual: pass the first two finance cards, then the forced spot-check hides the AI; your call → reveal
    func testYourCallFirstHidesAIThenReveals() {
        let app = launch([])
        let any = app.descendants(matching: .any)
        let decide = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Sign off' OR label BEGINSWITH 'Pass'"))
        for _ in 0..<2 {
            XCTAssertTrue(any["humanColumn"].waitForExistence(timeout: 30))
            let pass = decide.firstMatch; XCTAssertTrue(pass.waitForExistence(timeout: 10)); pass.tap(); sleep(2)
        }
        XCTAssertTrue(any["yourCallFirst"].waitForExistence(timeout: 20), "forced spot-check missing")
        XCTAssertTrue(any["aiHidden"].exists); XCTAssertFalse(any["aiColumn"].exists, "AI column must be hidden")
        XCTAssertFalse(decide.firstMatch.exists, "accept-the-AI shortcut must be hidden")
        shot("m3_01_your_call_first")
        app.buttons["call_Accept plan"].firstMatch.tap()
        XCTAssertTrue(any["spotReveal"].waitForExistence(timeout: 10), "reveal missing")
        XCTAssertTrue(has(app, "you held up", 5))
        XCTAssertTrue(any["calibrationCard"].exists)
        sleep(1); shot("m3_02_reveal_calibration")
    }
    /// auto demo: three missed spot-checks → sharpness rule hands detail back alongside the earned rise
    func testMissedChecksHandDetailBack() {
        let app = launch(["-demoAuto", "-speedup", "3"])
        XCTAssertTrue(app.descendants(matching: .any)["yourCallFirst"].waitForExistence(timeout: 90))
        if !has(app, "missed", 120) { shot("m3_fail_reveal"); XCTFail("no missed reveal"); return }
        if !has(app, "AI hands detail back", 150) { shot("m3_fail_effect"); XCTFail("no sharpness dial effect"); return }
        sleep(1); shot("m3_03_detail_handed_back")
        XCTAssertTrue(has(app, "0/3", 5), "calibration should show 0/3")
    }
}
