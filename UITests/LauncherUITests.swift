import XCTest

/// Real button taps (no launch args): start window → Enter Crossroads / Demo must open the immersive space.
final class LauncherUITests: XCTestCase {
    override func setUp() { continueAfterFailure = false }
    private func shot(_ name: String) {
        let a = XCTAttachment(screenshot: XCUIScreen.main.screenshot()); a.name = name; a.lifetime = .keepAlways; add(a)
        let dir = ProcessInfo.processInfo.environment["SHOT_DIR"] ?? NSTemporaryDirectory()
        try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent("\(name).png"))
    }
    func testEnterCrossroadsButton() {
        let app = XCUIApplication(); app.launch()
        let b = app.buttons["Enter Crossroads"]
        XCTAssertTrue(b.waitForExistence(timeout: 15)); shot("ui_launcher"); b.tap()
        let now = app.buttons["Reliability"].firstMatch
        let ok = now.waitForExistence(timeout: 25) || app.staticTexts["NOW"].waitForExistence(timeout: 5)
        shot("ui_after_enter")
        XCTAssertTrue(ok, "immersive content (Now card) did not appear after tapping Enter Crossroads")
    }
    func testDemoButton() {
        let app = XCUIApplication(); app.launch()
        let b = app.buttons["Demo"]
        XCTAssertTrue(b.waitForExistence(timeout: 15)); b.tap()
        let ok = app.buttons["Reset demo"].waitForExistence(timeout: 25)
        sleep(8); shot("ui_after_demo")
        XCTAssertTrue(ok, "demo board did not appear after tapping Demo")
    }
    func testCloseAndReenter() {
        let app = XCUIApplication(); app.launch()
        XCTAssertTrue(app.buttons["Enter Crossroads"].waitForExistence(timeout: 15)); app.buttons["Enter Crossroads"].tap()
        XCTAssertTrue(app.buttons["Close"].waitForExistence(timeout: 25)); app.buttons["Close"].tap()
        let b = app.buttons["Demo"]
        XCTAssertTrue(b.waitForExistence(timeout: 20), "start window did not come back after Close")
        XCTAssertEqual(app.buttons.matching(identifier: "Demo").count, 1, "duplicate start windows"); b.tap()
        XCTAssertTrue(app.buttons["Reset demo"].waitForExistence(timeout: 25), "re-entering after Close failed")
        sleep(10); shot("ui_reenter_demo")
    }
}
