import Foundation

/// Importer hook for real encounter spreadsheets (one row per encounter).
/// xlsx: export the sheet to CSV (UTF-8) and drop it in the app's Documents as `encounters.csv`, or pass `-importCSV <path>`.
/// Native .xlsx parsing is a TODO (needs a zip/XML reader); the column mapping below is the contract.
/// See docs/AI_DOC_REVIEW.md for the full column table.
enum EncounterImporter {
    static let columns = ["encounter_id", "age", "sex", "chief_complaint", "channel", "companion", "interpreter", "language",
                          "health_literacy", "hr", "sbp", "spo2", "temp", "pmh", "ai_plan", "transcript",
                          "stated_pregnancy", "stated_meds", "stated_substance", "stated_allergies", "stated_symptoms",
                          "stated_safety", "stated_adherence", "stated_sexual",
                          "true_pregnancy", "true_meds", "true_substance", "true_allergies", "true_symptoms",
                          "true_safety", "true_adherence", "true_sexual", "hard_trigger"]

    @MainActor static func loadDefault(now: Double) -> [DREncounter] {
        let a = ProcessInfo.processInfo.arguments
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("encounters.csv")
        let url = a.firstIndex(of: "-importCSV").flatMap { $0 + 1 < a.count ? URL(fileURLWithPath: a[$0 + 1]) : nil } ?? docs
        guard let text = try? String(contentsOf: url, encoding: .utf8) else { return [] }
        return parse(csv: text, now: now)
    }

    static func parse(csv: String, now: Double) -> [DREncounter] {
        var lines = csv.split(whereSeparator: \.isNewline).map(String.init)
        guard !lines.isEmpty else { return [] }
        let header = split(lines.removeFirst()).map { $0.lowercased().trimmingCharacters(in: .whitespaces) }
        return lines.compactMap { line in
            let v = split(line); var r: [String: String] = [:]
            for (i, h) in header.enumerated() where i < v.count { r[h] = v[i].trimmingCharacters(in: .whitespaces) }
            guard let id = r["encounter_id"], !id.isEmpty else { return nil }
            let cc = DRComplaint.allCases.first { $0.rawValue.lowercased() == (r["chief_complaint"] ?? "").lowercased() } ?? .chestPain
            var e = DREncounter(id: "X-" + id, age: Int(r["age"] ?? "") ?? 40, sex: r["sex"] ?? "U", cc: cc, channel: r["channel"] ?? "imported",
                                companion: (r["companion"]).flatMap { $0.isEmpty || $0 == "none" ? nil : $0 }, interpreter: r["interpreter"] == "yes",
                                language: r["language"] ?? "English", literacyLow: r["health_literacy"] == "low",
                                hr: Int(r["hr"] ?? ""), sbp: Int(r["sbp"] ?? ""), spo2: Int(r["spo2"] ?? ""), temp: Double(r["temp"] ?? ""),
                                pmh: (r["pmh"] ?? "").split(separator: ";").map { $0.trimmingCharacters(in: .whitespaces) },
                                aiPlan: r["ai_plan"] ?? "—", aiDdx: DRSpec.ddx[cc]!, arrival: now)
            let benign = ["pregnancy": "not pregnant", "meds": "none", "substance": "none", "allergies": "NKDA", "symptoms": "mild",
                          "safety": "safe", "adherence": "adherent", "sexual": "no new partners"]
            for (k, b) in benign {
                guard let s = r["stated_" + k], !s.isEmpty else { continue }
                let t = r["true_" + k].flatMap { $0.isEmpty ? nil : $0 } ?? s   // no truth column → treat stated as truth (unknown)
                let st: ReliabilityState = s == "—" ? .notSaid : (t == s ? .reliable : .saidWrong)
                e.fields[k] = DRField(name: k, benign: b, truth: t, stated: s, trueState: st, asked: s != "—", clue: nil,
                                      sensitive: DRSpec.sensitive.contains(k))
            }
            if let t = r["hard_trigger"], !t.isEmpty { e.trigger = t }
            return e
        }
    }
    /// minimal CSV split with quoted fields
    static func split(_ line: String) -> [String] {
        var out: [String] = [], cur = "", q = false
        for ch in line {
            if ch == "\"" { q.toggle() } else if ch == "," && !q { out.append(cur); cur = "" } else { cur.append(ch) }
        }
        out.append(cur); return out
    }
}
