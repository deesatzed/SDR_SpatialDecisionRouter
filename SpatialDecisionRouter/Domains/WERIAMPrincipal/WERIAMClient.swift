import CryptoKit
import Foundation
import Security

/// Client for the localhost WERIAM bridge (weriam_bridge/, 127.0.0.1:8766). nil/0 on any failure → seeded fallback cards.
/// Every call except /health carries X-SDR-Token (env WERIAM_TOKEN, else the bridge's token file on the host Mac).
enum WERIAMClient {
    static var baseURL = URL(string: ProcessInfo.processInfo.environment["WERIAM_URL"] ?? "http://127.0.0.1:8766")!
    static let session: URLSession = {
        let c = URLSessionConfiguration.ephemeral
        c.timeoutIntervalForRequest = 3; c.timeoutIntervalForResource = 20
        return URLSession(configuration: c)
    }()
    static var disabled: Bool { ProcessInfo.processInfo.arguments.contains("-noBridge") }
    static var token: String? = {
        let env = ProcessInfo.processInfo.environment
        if let t = env["WERIAM_TOKEN"], !t.isEmpty { return t }
        // simulator: the host Mac's home is visible as SIMULATOR_HOST_HOME
        for home in [env["SIMULATOR_HOST_HOME"], NSHomeDirectory()].compactMap({ $0 }) {
            if let t = try? String(contentsOfFile: home + "/.sdr/weriam_bridge/token", encoding: .utf8) {
                return t.trimmingCharacters(in: .whitespacesAndNewlines) }
        }
        return nil
    }()

    private static func request(_ path: String) -> URLRequest {
        var rq = URLRequest(url: baseURL.appendingPathComponent(path))
        if let t = token { rq.setValue(t, forHTTPHeaderField: "X-SDR-Token") }
        return rq
    }
    static func get(_ path: String) async -> [String: Any]? {
        guard !disabled, let (d, r) = try? await session.data(for: request(path)),
              (r as? HTTPURLResponse)?.statusCode == 200 else { return nil }
        return (try? JSONSerialization.jsonObject(with: d)) as? [String: Any]
    }
    /// returns (status code, json); code 0 = unreachable
    static func post(_ path: String, _ body: [String: Any]) async -> (Int, [String: Any]) {
        guard !disabled, let data = try? JSONSerialization.data(withJSONObject: body) else { return (0, [:]) }
        var rq = request(path)
        rq.httpMethod = "POST"; rq.httpBody = data; rq.setValue("application/json", forHTTPHeaderField: "Content-Type")
        guard let (d, r) = try? await session.data(for: rq) else { return (0, [:]) }
        return ((r as? HTTPURLResponse)?.statusCode ?? 0, ((try? JSONSerialization.jsonObject(with: d)) as? [String: Any]) ?? [:])
    }
}

/// The approver's Ed25519 key: generated on this device, private key stays in the Keychain (file fallback if the
/// simulator Keychain is unavailable). The bridge pins the public key on first use and verifies every signature.
enum ApproverSigner {
    static let name = "W. Allen Satz"
    static let service = "com.wsatz.sdr.approver.ed25519"
    private(set) static var storage = "?"
    private(set) static var keyId: String?

    static let key: Curve25519.Signing.PrivateKey = {
        if let raw = keychainRead(), let k = try? Curve25519.Signing.PrivateKey(rawRepresentation: raw) { storage = "Keychain"; return k }
        if let raw = try? Data(contentsOf: fileURL), let k = try? Curve25519.Signing.PrivateKey(rawRepresentation: raw) { storage = "file (Keychain unavailable)"; return k }
        let k = Curve25519.Signing.PrivateKey()
        if keychainWrite(k.rawRepresentation) { storage = "Keychain" }
        else { try? k.rawRepresentation.write(to: fileURL, options: [.atomic, .completeFileProtection]); storage = "file (Keychain unavailable)" }
        return k
    }()
    static var publicB64: String { key.publicKey.rawRepresentation.base64EncodedString() }
    static var fileURL: URL {
        let d = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        try? FileManager.default.createDirectory(at: d, withIntermediateDirectories: true)
        return d.appendingPathComponent("approver.ed25519")
    }
    private static var q: [String: Any] { [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: name] }
    private static func keychainRead() -> Data? {
        var out: CFTypeRef?
        var qq = q; qq[kSecReturnData as String] = true; qq[kSecMatchLimit as String] = kSecMatchLimitOne
        return SecItemCopyMatching(qq as CFDictionary, &out) == errSecSuccess ? out as? Data : nil
    }
    private static func keychainWrite(_ d: Data) -> Bool {
        var qq = q; qq[kSecValueData as String] = d; qq[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        SecItemDelete(q as CFDictionary)
        return SecItemAdd(qq as CFDictionary, nil) == errSecSuccess
    }

    /// register (idempotent) → key id
    static func register() async -> String? {
        if let k = keyId { return k }
        let (code, j) = await WERIAMClient.post("approver/register", ["name": name, "pub": publicB64])
        if code == 200 { keyId = j["key_id"] as? String }
        return keyId
    }
    /// canonical JSON (sorted keys, compact) — byte-identical to the bridge's json.dumps(sort_keys, separators)
    static func signed(requestId: String, decision: String, requestHash: String) -> [String: Any]? {
        let payload: [String: Any] = ["request_id": requestId, "decision": decision, "by": name,
                                      "ts": Int(Date().timeIntervalSince1970), "nonce": UUID().uuidString, "request_hash": requestHash]
        guard let bytes = try? JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys, .withoutEscapingSlashes]),
              let sig = try? key.signature(for: bytes) else { return nil }
        return ["payload": payload, "sig": sig.base64EncodedString()]
    }
}

/// JSON helpers
extension Dictionary where Key == String, Value == Any {
    func s(_ k: String) -> String { if let v = self[k] as? String { return v }; if let v = self[k], !(v is NSNull) { return "\(v)" }; return "—" }
    func d(_ k: String) -> Double? { (self[k] as? NSNumber)?.doubleValue }
    func o(_ k: String) -> [String: Any] { self[k] as? [String: Any] ?? [:] }
    func a(_ k: String) -> [[String: Any]] { self[k] as? [[String: Any]] ?? [] }
}
func fmt(_ x: Double?, _ p: Int = 2) -> String { x.map { String(format: "%.\(p)f", $0) } ?? "—" }
