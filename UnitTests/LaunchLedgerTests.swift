import XCTest
@testable import SpatialDecisionRouter

/// launch-option ledger routing: -testLedger / -ledgerPath never resolve to the device ledger; no option → device ledger.
final class LaunchLedgerTests: XCTestCase {
    func testDefaultIsDeviceLedger() { XCTAssertNil(RouterEngine.isolatedLedgerURL(["app", "-freshLedger", "-demo"])) }
    func testTestLedgerIsIsolatedTmp() throws {
        let u = try XCTUnwrap(RouterEngine.isolatedLedgerURL(["app", "-testLedger", "-freshLedger"]))
        XCTAssertNotEqual(u, DecisionLedger.defaultURL)
        XCTAssertTrue(u.path.hasPrefix(FileManager.default.temporaryDirectory.path))
    }
    func testLedgerPath() {
        XCTAssertEqual(RouterEngine.isolatedLedgerURL(["app", "-ledgerPath", "/tmp/x"])?.path, "/tmp/x/decision_ledger.jsonl")
        XCTAssertNil(RouterEngine.isolatedLedgerURL(["app", "-ledgerPath"]))
    }
}
