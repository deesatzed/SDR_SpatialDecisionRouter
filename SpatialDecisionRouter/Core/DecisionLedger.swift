import Foundation
import CryptoKit

// MARK: - Unified decision record (docs/SYMBIOSIS_PLAN.md §4) — one schema for every domain.
// Append-only JSONL, SHA-256 hash-chained, each line Ed25519-signed with the device approver key (same key as
// WERIAM Principal v2). Later facts (observed outcome, a split rating given after the decision) are NEW lines of kind
// "outcome" / "split_rating" that reference the decision id; nothing is rewritten, so the chain always verifies.
// Hash = sha256(canonical body) where body = the line minus `ledger_hash` and `signature`;
// canonical = JSON, sorted keys, compact, no slash escaping (Python: json.dumps(sort_keys=True, separators=(',',':'), ensure_ascii=False)).

/// The four Symbiosis dials (0–100). `source` says where the numbers come from — "seed" values are placeholders, not learned.
struct DialSnapshot: Codable, Hashable {
    var deference: Double
    var detail_absorption: Double
    var challenge: Double
    var autonomy_horizon: Double
    var source: String
}

struct RecordReliability: Codable, Hashable {
    var score: Double?
    var n: Int                 // sample size behind the score (0 = no data)
    var label: String          // e.g. "placeholder — no graded labels yet"
}

struct RecordOutcome: Codable, Hashable {
    var value: String
    var source: String         // simulator_ground_truth (synthetic) | weriam_teacher | seeded_scenario (synthetic) | observed
    var observed_at: String
}

struct AgentProposal: Codable, Hashable { var answer: String; var confidence: Double }

struct HumanDecision: Codable, Hashable {
    var label: String          // pass | flip | modify | escalate | new_category
    var answer: String
    var gesture: String
    var changed: Bool
    var decided_by: String     // human | auto
}

enum SplitRating: String, Codable, CaseIterable, Hashable {
    case about_right, overstepped_me, buried_me, too_abstract
    var title: String {
        switch self { case .about_right: "About right"; case .overstepped_me: "Overstepped me"; case .buried_me: "Buried me in detail"; case .too_abstract: "Too abstract" }
    }
}

struct UnifiedDecisionRecord: Codable, Hashable {
    var schema = "sdr.decision.v1"
    var kind: String                         // decision | outcome | split_rating
    var id: String
    var ref_id: String?                      // amendments: the decision id they apply to
    var timestamp: String                    // ISO 8601 (UTC, Z); displayed in America/New_York
    var domain: String                       // ed_triage | ai_tele_doc | weriam_principal | symbiosis:<area>
    var context_id: String
    var dial_snapshot: DialSnapshot?
    var generation: Int
    var card_payload: [String: String]?
    var card_hash: String?
    var question: String?
    var options: [String]?
    var agent_proposal: AgentProposal?
    var human_decision: HumanDecision?
    var split_rating: String?
    var latency_ms: Int?
    var reliability: RecordReliability?
    var escalation_flags: [String]?
    var outcome: RecordOutcome?
    var item_id: String?
    var link_id: String?
    var legacy_id: String?                   // RoutingDecision.id in routing_log.jsonl (old log kept as-is)
    var signer_key_id: String
    var signer_pub: String                   // base64 raw Ed25519 public key
    var ledger_prev: String
    // not part of the hashed body:
    var ledger_hash: String?
    var signature: String?
}

/// Minimal signer abstraction so tests can use an ephemeral key.
struct LedgerSigner {
    let key: Curve25519.Signing.PrivateKey
    var pubB64: String { key.publicKey.rawRepresentation.base64EncodedString() }
    var keyId: String { SHA256.hash(data: key.publicKey.rawRepresentation).map { String(format: "%02x", $0) }.joined().prefix(16).description }
    static var device: LedgerSigner { LedgerSigner(key: ApproverSigner.key) }
}

final class DecisionLedger {
    static let genesis = String(repeating: "0", count: 64)
    let url: URL
    let signer: LedgerSigner
    private(set) var head: String

    init(url: URL, signer: LedgerSigner) {
        self.url = url; self.signer = signer
        try? FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        head = Self.lastHash(url) ?? Self.genesis
    }
    @MainActor static let shared = DecisionLedger(url: defaultURL, signer: .device)
    static var defaultURL: URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("decisions", isDirectory: true).appendingPathComponent("decision_ledger.jsonl")
    }

    static func canonical(_ r: UnifiedDecisionRecord) throws -> Data {
        var b = r; b.ledger_hash = nil; b.signature = nil
        let e = JSONEncoder(); e.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        return try e.encode(b)
    }
    static func sha(_ d: Data) -> String { SHA256.hash(data: d).map { String(format: "%02x", $0) }.joined() }
    static func iso(_ d: Date = Date()) -> String { let f = ISO8601DateFormatter(); f.formatOptions = [.withInternetDateTime]; return f.string(from: d) }
    static func hashCard(_ p: [String: String]) -> String {
        let e = JSONEncoder(); e.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        return sha((try? e.encode(p)) ?? Data())
    }

    private static func lastHash(_ url: URL) -> String? {
        guard let t = try? String(contentsOf: url, encoding: .utf8) else { return nil }
        guard let last = t.split(separator: "\n").last(where: { !$0.isEmpty }),
              let r = try? JSONDecoder().decode(UnifiedDecisionRecord.self, from: Data(last.utf8)) else { return nil }
        return r.ledger_hash
    }

    /// Seal (prev, signer, hash, signature) and append one line. Returns the sealed record.
    @discardableResult func append(_ rec: UnifiedDecisionRecord) -> UnifiedDecisionRecord? {
        var r = rec
        r.signer_key_id = signer.keyId; r.signer_pub = signer.pubB64; r.ledger_prev = head
        guard let body = try? Self.canonical(r) else { return nil }
        let h = Self.sha(body)
        guard let sig = try? signer.key.signature(for: Data(h.utf8)) else { return nil }
        r.ledger_hash = h; r.signature = sig.base64EncodedString()
        let e = JSONEncoder(); e.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        guard var line = try? e.encode(r) else { return nil }
        line.append(0x0A)
        if let f = try? FileHandle(forWritingTo: url) { f.seekToEndOfFile(); f.write(line); try? f.close() } else { try? line.write(to: url) }
        head = h
        return r
    }

    func read() -> [UnifiedDecisionRecord] {
        let t = (try? String(contentsOf: url, encoding: .utf8)) ?? ""
        return t.split(separator: "\n").compactMap { try? JSONDecoder().decode(UnifiedDecisionRecord.self, from: Data($0.utf8)) }
    }

    /// Verify chain + every signature. Returns (ok, count, first problem).
    static func verify(_ recs: [UnifiedDecisionRecord]) -> (ok: Bool, n: Int, problem: String?) {
        var prev = genesis
        for (i, r) in recs.enumerated() {
            guard r.ledger_prev == prev else { return (false, i, "line \(i + 1): prev mismatch") }
            guard let body = try? canonical(r), sha(body) == r.ledger_hash else { return (false, i, "line \(i + 1): hash mismatch") }
            guard let pub = Data(base64Encoded: r.signer_pub), let k = try? Curve25519.Signing.PublicKey(rawRepresentation: pub),
                  let s = r.signature.flatMap({ Data(base64Encoded: $0) }), k.isValidSignature(s, for: Data(r.ledger_hash!.utf8))
            else { return (false, i, "line \(i + 1): bad signature") }
            prev = r.ledger_hash!
        }
        return (true, recs.count, nil)
    }
}

// MARK: - mapping from the engine's RoutingDecision

/// Per-decision context a domain contributes to the unified record (defaults below; Symbiosis overrides).
struct DecisionContext {
    var domain: String
    var contextId: String
    var dials: DialSnapshot?
    var generation: Int
    var reliability: RecordReliability?
    var outcomeSource: String
}

extension UnifiedDecisionRecord {
    static func decisionLabel(gesture: String, changed: Bool, isNew: Bool) -> String {
        if isNew { return "new_category" }
        switch gesture {
        case "pass": return changed ? "modify" : "pass"
        case "flip": return "flip"
        case "escalate": return "escalate"
        default: return changed ? "modify" : "pass"
        }
    }
    static func from(_ d: RoutingDecision, ctx: DecisionContext, split: SplitRating?) -> UnifiedDecisionRecord {
        var payload = d.context
        payload["displayLine"] = d.displayLine; payload["history"] = d.history
        let flags = [d.hardTrigger].compactMap { $0 } + (d.gesture == "escalate" ? ["human_escalation"] : [])
        let outcome = d.groundTruth.map { RecordOutcome(value: $0, source: ctx.outcomeSource, observed_at: DecisionLedger.iso(d.decidedAt)) }
        return UnifiedDecisionRecord(
            kind: "decision", id: UUID().uuidString, ref_id: nil, timestamp: DecisionLedger.iso(d.decidedAt),
            domain: ctx.domain, context_id: ctx.contextId, dial_snapshot: ctx.dials, generation: ctx.generation,
            card_payload: payload, card_hash: DecisionLedger.hashCard(payload), question: d.question, options: d.options,
            agent_proposal: AgentProposal(answer: d.proposedAnswer, confidence: (d.proposedConfidence * 1000).rounded() / 1000),
            human_decision: HumanDecision(label: decisionLabel(gesture: d.gesture, changed: d.changed, isNew: d.newCategoryCreated),
                                          answer: d.routedAnswer, gesture: d.gesture, changed: d.changed, decided_by: d.decidedBy ?? "human"),
            split_rating: split?.rawValue, latency_ms: Int((d.latency * 1000).rounded()), reliability: ctx.reliability,
            escalation_flags: flags, outcome: outcome, item_id: d.itemId, link_id: d.linkId, legacy_id: d.id.uuidString,
            signer_key_id: "", signer_pub: "", ledger_prev: "")
    }
    static func amendment(kind: String, ref: UnifiedDecisionRecord, outcome: RecordOutcome? = nil, split: SplitRating? = nil) -> UnifiedDecisionRecord {
        UnifiedDecisionRecord(kind: kind, id: UUID().uuidString, ref_id: ref.id, timestamp: DecisionLedger.iso(), domain: ref.domain,
                              context_id: ref.context_id, dial_snapshot: nil, generation: ref.generation, split_rating: split?.rawValue,
                              outcome: outcome, item_id: ref.item_id, link_id: ref.link_id, legacy_id: ref.legacy_id,
                              signer_key_id: "", signer_pub: "", ledger_prev: "")
    }
}

/// Domain-id mapping used in the unified record (plan names).
enum UnifiedDomainId {
    static func of(_ configId: String) -> String {
        switch configId { case "ai_doc_review": "ai_tele_doc"; default: configId }
    }
}
