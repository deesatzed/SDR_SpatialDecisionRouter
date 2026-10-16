import XCTest
import CryptoKit
@testable import SpatialDecisionRouter

/// Isolated temp files for tests. Every ledger/pack a test writes lives under a per-test temp path and is
/// removed in tearDown; no test touches DecisionLedger.defaultURL (the app's device ledger).
enum TestTemp {
    nonisolated(unsafe) private static var made: [URL] = []
    static func url(_ prefix: String, _ ext: String? = "jsonl") -> URL {
        let u = FileManager.default.temporaryDirectory.appendingPathComponent("\(prefix)-\(UUID().uuidString)" + (ext.map { ".\($0)" } ?? ""))
        precondition(u != DecisionLedger.defaultURL); made.append(u); return u
    }
    static func ledger(_ prefix: String) -> DecisionLedger {
        DecisionLedger(url: url(prefix), signer: LedgerSigner(key: Curve25519.Signing.PrivateKey()))
    }
    static func cleanup() { for u in made { try? FileManager.default.removeItem(at: u) }; made.removeAll() }
}
