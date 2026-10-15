import XCTest

/// Symbiosis M1 slice: start → Symbiosis → three-column card → show AI depth → rate split → decide → manifesto lenses.
final class SymbiosisUITests: XCTestCase {
    override func setUp() { continueAfterFailure = false }
    private func shot(_ name: String) {
        let s = XCUIScreen.main.screenshot()
        let a = XCTAttachment(screenshot: s); a.name = name; a.lifetime = .keepAlways; add(a)
        if let dir = ProcessInfo.processInfo.environment["SHOT_DIR"] { try? s.pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent("\(name).png")) }
    }
    func testSymbiosisDemoFlow() {
        let app = XCUIApplication(); app.launchArguments += ["-freshRegistry", "-freshLedger", "-hideSidebar", "-focus", "-noBridge"]; app.launch()
        XCUIDevice.shared.orientation = .landscapeLeft
        let b = app.buttons["Symbiosis"]
        XCTAssertTrue(b.waitForExistence(timeout: 20)); b.tap()
        if !app.descendants(matching: .any)["humanColumn"].waitForExistence(timeout: 20) { shot("sym_fail"); XCTFail("three-column card missing"); return }
        XCTAssertTrue(app.descendants(matching: .any)["bridgeColumn"].exists)
        XCTAssertTrue(app.descendants(matching: .any)["aiColumn"].exists)
        sleep(2); shot("sym_01_card_ai_collapsed")
        let depth = app.buttons["aiDepthToggle"]; XCTAssertTrue(depth.exists); depth.tap()
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label == %@", "Edge cases")).firstMatch.waitForExistence(timeout: 5), "AI depth did not expand")
        app.buttons["split_overstepped_me"].tap(); sleep(1)
        shot("sym_02_card_ai_open_split_rated")
        let pass = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Sign off' OR label BEGINSWITH 'Pass'")).firstMatch
        if !pass.waitForExistence(timeout: 5) { shot("sym_fail_pass"); XCTFail("decision button missing"); return }
        pass.tap()
        // next card (order: finance first, then ED triage incl. the hard-trigger card)
        XCTAssertTrue(app.descendants(matching: .any)["humanColumn"].waitForExistence(timeout: 20), "next card missing"); sleep(2); shot("sym_03_next_card")
        let mf = app.buttons["openManifesto"].firstMatch
        XCTAssertTrue(mf.waitForExistence(timeout: 20)); mf.tap()
        XCTAssertTrue(app.buttons["lens_philosophical"].waitForExistence(timeout: 10), "manifesto did not open"); sleep(1)
        shot("sym_04_manifesto_philosophical")
        app.buttons["lens_executive"].tap(); sleep(1); shot("sym_05_manifesto_executive")
        app.buttons["closeManifesto"].tap()
        XCTAssertTrue(app.buttons["openBoard"].waitForExistence(timeout: 10)); app.buttons["openBoard"].tap(); sleep(2)
        shot("sym_06_board")
    }
}
