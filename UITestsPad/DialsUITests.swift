import XCTest

/// M2: auto-played Symbiosis demo must show an earned dial rise (finance) and a demotion after a critical miss (ED triage).
final class DialsUITests: XCTestCase {
    override func setUp() { continueAfterFailure = false }
    private func shot(_ name: String) {
        let s = XCUIScreen.main.screenshot()
        let a = XCTAttachment(screenshot: s); a.name = name; a.lifetime = .keepAlways; add(a)
        if let dir = ProcessInfo.processInfo.environment["SHOT_DIR"] { try? s.pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent("\(name).png")) }
    }
    private func why(_ app: XCUIApplication, _ text: String, _ t: TimeInterval) -> Bool {
        app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", text)).firstMatch.waitForExistence(timeout: t)
    }
    func testEarnedRiseAndDemotion() {
        let app = XCUIApplication()
        app.launchArguments += ["-demo", "-symbiosisDemo", "-demoAuto", "-speedup", "3", "-freshLedger", "-freshRegistry", "-hideSidebar", "-focus", "-noBridge"]
        app.launch(); XCUIDevice.shared.orientation = .landscapeLeft
        XCTAssertTrue(app.descendants(matching: .any)["humanColumn"].waitForExistence(timeout: 30))
        sleep(2); shot("m2_01_no_moves_yet")
        if !why(app, "Why it moved: earned", 150) { shot("m2_fail_rise"); XCTFail("no earned dial move shown"); return }
        sleep(1); shot("m2_02_earned_rise")
        if !why(app, "DEMOTION", 200) { shot("m2_fail_demotion"); XCTFail("no demotion shown"); return }
        sleep(1); shot("m2_03_demotion")
        let undo = app.buttons["undoDial"].firstMatch
        XCTAssertTrue(undo.exists); undo.tap()
        XCTAssertTrue(why(app, "REVERT", 10), "undo did not write a revert"); shot("m2_04_reverted")
    }
}
