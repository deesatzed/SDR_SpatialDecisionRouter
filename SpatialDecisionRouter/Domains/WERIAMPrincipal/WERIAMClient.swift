import Foundation

/// Client for the localhost WERIAM bridge (weriam_bridge/, 127.0.0.1:8766). nil on any failure → seeded fallback cards.
enum WERIAMClient {
    static var baseURL = URL(string: ProcessInfo.processInfo.environment["WERIAM_URL"] ?? "http://127.0.0.1:8766")!
    static let session: URLSession = {
        let c = URLSessionConfiguration.ephemeral
        c.timeoutIntervalForRequest = 3; c.timeoutIntervalForResource = 20
        return URLSession(configuration: c)
    }()
    static var disabled: Bool { ProcessInfo.processInfo.arguments.contains("-noBridge") }

    static func get(_ path: String) async -> [String: Any]? {
        guard !disabled, let (d, r) = try? await session.data(from: baseURL.appendingPathComponent(path)),
              (r as? HTTPURLResponse)?.statusCode == 200 else { return nil }
        return (try? JSONSerialization.jsonObject(with: d)) as? [String: Any]
    }
    /// returns (status code, json); code 0 = unreachable
    static func post(_ path: String, _ body: [String: Any]) async -> (Int, [String: Any]) {
        guard !disabled, let data = try? JSONSerialization.data(withJSONObject: body) else { return (0, [:]) }
        var rq = URLRequest(url: baseURL.appendingPathComponent(path))
        rq.httpMethod = "POST"; rq.httpBody = data; rq.setValue("application/json", forHTTPHeaderField: "Content-Type")
        guard let (d, r) = try? await session.data(for: rq) else { return (0, [:]) }
        return ((r as? HTTPURLResponse)?.statusCode ?? 0, ((try? JSONSerialization.jsonObject(with: d)) as? [String: Any]) ?? [:])
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
