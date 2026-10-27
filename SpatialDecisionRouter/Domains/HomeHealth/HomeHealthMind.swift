import Foundation

/// Synthetic medical-intelligence read for one home-health card.
/// Uncertainty stays a list. A route can be required before that list closes.
/// Overrides live on the pattern fixture (`mi_*` fields). Library cases derive from text already on the vignette.
struct HomeHealthMind: Equatable {
    var differential: [String]
    var confidence: String
    var actBeforeClosure: Bool
    var actBanner: String
    var priorDecision: String
    var newEvidence: String
    var falsifiesPrior: Bool
    var waitFor: String
    var flipRoute: String
    var flipIf: String
    /// Window for this wait, in minutes. Always set. Explicit fixture, then text, then a situation default.
    var waitMinutes: Int
    var waitOverdue: Bool
    var overdueLine: String
    var agentRefused: Bool
    var refusalReason: String
    var goalsLine: String
    var goalsKind: String
    var blocksEscalation: Bool

    var differentialLine: String { differential.joined(separator: " · ") }

    var revisitLine: String {
        guard falsifiesPrior else { return "" }
        let prior = priorDecision.isEmpty ? "prior decision" : priorDecision
        let evidence = newEvidence.isEmpty ? "new evidence" : newEvidence
        return "Prior \(prior) → \(evidence) → Revise"
    }

    var waitClockLabel: String {
        waitOverdue ? "OVERDUE" : HomeHealthWaitClock.faceLabel(minutes: waitMinutes)
    }

    var waitTitle: String { "Wait for \(waitFor) · \(waitClockLabel)" }

    static func of(_ f: [String: String]) -> HomeHealthMind {
        let signals = HomeHealthBrief.signals(f)
        let goals = deriveGoals(f)
        let diff = overrideList(f["mi_differential"]) ?? derivedDifferential(f, signals)
        let act = overrideBool(f["mi_act"]) ?? derivedAct(f, signals)
        let refused = overrideBool(f["mi_refused"]) ?? (f["route"] ?? "").isEmpty
        let prior = nonempty(f["mi_prior"]) ?? ""
        let evidence = nonempty(f["mi_evidence"]) ?? ""
        let falsifies = overrideBool(f["mi_falsifies"]) ?? (!prior.isEmpty && !evidence.isEmpty)
        let wait = derivedWait(f, signals, goals)
        let waitFor = nonempty(f["mi_wait_for"]) ?? wait.0
        let flipIf = nonempty(f["mi_flip_if"]) ?? wait.2
        let minutes = resolvedWaitMinutes(f, waitFor: waitFor, flipIf: flipIf, signals: signals, goals: goals)
        let overdue = f["voi_wait_overdue"] == "1" || f["voi_recheck"] == "1"
        let blocks = overrideBool(f["mi_blocks"]) ?? goals.blocks
        let kind = nonempty(f["mi_goals_kind"]) ?? goals.kind
        let line = nonempty(f["mi_goals_line"]) ?? goals.line
        return HomeHealthMind(
            differential: diff,
            confidence: nonempty(f["mi_confidence"]) ?? derivedConfidence(f),
            actBeforeClosure: act,
            actBanner: nonempty(f["mi_act_banner"]) ?? (act ? "Act under uncertainty. Choose the route before this differential closes." : ""),
            priorDecision: prior,
            newEvidence: evidence,
            falsifiesPrior: falsifies,
            waitFor: waitFor,
            flipRoute: nonempty(f["mi_flip_route"]) ?? wait.1,
            flipIf: flipIf,
            waitMinutes: minutes,
            waitOverdue: overdue,
            overdueLine: nonempty(f["wait_overdue_line"]) ?? (overdue ? HomeHealthWaitClock.overdueLine(waitFor) : ""),
            agentRefused: refused,
            refusalReason: nonempty(f["mi_refusal"]) ?? (refused ? defaultRefusal(f) : ""),
            goalsLine: line,
            goalsKind: kind,
            blocksEscalation: blocks)
    }

    /// Keys copied onto every decision's `card_payload`.
    static func logFields(_ f: [String: String]) -> [String: String] {
        let m = of(f)
        var out: [String: String] = [
            "uncertainty_differential": m.differentialLine,
            "uncertainty_confidence": m.confidence,
            "act_under_uncertainty": m.actBeforeClosure ? "1" : "0",
            "goals_constraint": m.goalsLine,
            "goals_blocks_escalation": m.blocksEscalation ? "1" : "0",
            "goals_kind": m.goalsKind,
            "agent_refused": m.agentRefused ? "1" : "0",
        ]
        if m.agentRefused { out["refusal_reason"] = m.refusalReason }
        if m.falsifiesPrior {
            out["prior_decision"] = m.priorDecision
            out["new_evidence"] = m.newEvidence
        }
        return out
    }

    static func apply(_ note: HHMindNote?, onto fields: inout [String: String]) {
        guard let note else { return }
        if let d = note.differential, !d.isEmpty {
            fields["mi_differential"] = d.joined(separator: " | ")
        }
        if let v = note.confidence { fields["mi_confidence"] = v }
        if let v = note.act_under_uncertainty { fields["mi_act"] = v ? "1" : "0" }
        if let v = note.act_banner { fields["mi_act_banner"] = v }
        if let v = note.prior_decision { fields["mi_prior"] = v }
        if let v = note.new_evidence { fields["mi_evidence"] = v }
        if let v = note.falsifies_prior { fields["mi_falsifies"] = v ? "1" : "0" }
        if let v = note.wait_for { fields["mi_wait_for"] = v }
        if let v = note.wait_minutes, v > 0 { fields["mi_wait_minutes"] = String(v) }
        if let v = note.flip_route { fields["mi_flip_route"] = v }
        if let v = note.flip_if { fields["mi_flip_if"] = v }
        if let v = note.agent_refused { fields["mi_refused"] = v ? "1" : "0" }
        if let v = note.refusal_reason { fields["mi_refusal"] = v }
        if let v = note.goals_line { fields["mi_goals_line"] = v }
        if let v = note.goals_kind { fields["mi_goals_kind"] = v }
        if let v = note.blocks_escalation { fields["mi_blocks"] = v ? "1" : "0" }
    }

    private static func derivedDifferential(_ f: [String: String], _ s: HomeHealthBrief.Signals) -> [String] {
        let cleared = (f["reason"] ?? "") == "cleared_by_repeat"
        let oxygenLead = s.oxygen && !s.fall && !s.neuro && !s.chest
        let positional = !(f["pattern_trigger"] ?? "").isEmpty || s.exert
            || (f["note"] ?? "").lowercased().contains("position")
        if s.neuro { return ["ischemic stroke", "intracranial hemorrhage", "stroke mimic"] }
        if s.chest { return ["unstable angina or acute coronary syndrome", "stable angina with a weak spray", "non-cardiac tightness"] }
        if s.fall && s.bleed { return ["intracranial bleed", "mechanical fall", "syncope or arrhythmia"] }
        if s.fall { return ["mechanical fall", "syncope", "new neurologic event"] }
        if oxygenLead && cleared { return ["motion or contact artifact", "true hypoxemia"] }
        if oxygenLead && positional { return ["positional desaturation", "infection or exacerbation", "device artifact"] }
        if oxygenLead { return ["true hypoxemia", "infection or exacerbation", "device artifact"] }
        if s.device { return ["device fault", "true clinical change"] }
        let plain = tidy(f["plain_reason"] ?? "")
        if plain.isEmpty { return ["working explanation open", "another cause not excluded"] }
        return [plain, "another explanation not excluded"]
    }

    private static func derivedConfidence(_ f: [String: String]) -> String {
        switch f["reason"] ?? "" {
        case "cleared_by_repeat": return "Repeat favors artifact. Hypoxemia stays on the list."
        case "goals_of_care": return "Route follows goals. The diagnosis is not closed."
        default: break
        }
        switch f["tier"] ?? "" {
        case "ABSOLUTE": return "High concern. The diagnosis is not closed."
        case "CONFIRM_FIRST": return "Needs a human. The diagnosis is not closed."
        default: break
        }
        if f["pattern_fixture"] == "1" { return "Pattern favored. Not a closed diagnosis." }
        return "Open. More than one explanation still fits."
    }

    private static func derivedAct(_ f: [String: String], _ s: HomeHealthBrief.Signals) -> Bool {
        let route = f["route"] ?? ""
        if (f["reason"] ?? "") == "cleared_by_repeat" && route == "silent_log" { return false }
        if f["pattern_fixture"] == "1" && route == "silent_log" && (s.exert || !(f["pattern_trigger"] ?? "").isEmpty) {
            return false
        }
        if s.neuro || s.chest || (s.fall && s.bleed) { return true }
        return route == "urgent_page" || route == "provider_task" || route == "nurse_task"
    }

    private static func derivedWait(_ f: [String: String], _ s: HomeHealthBrief.Signals, _ goals: (kind: String, line: String, blocks: Bool)) -> (String, String, String) {
        if goals.blocks {
            return ("a hospice symptom check", "nurse_task", "distress they would want treated at home")
        }
        if s.neuro {
            return ("repeat strength and speech", "provider_task", "the deficit has fully cleared")
        }
        if s.chest {
            return ("whether one spray eases it", "urgent_page", "pain is still there after 10 minutes")
        }
        if s.fall && s.bleed {
            return ("a witnessed neuro check", "urgent_page", "headache, vomiting, or new weakness appears")
        }
        let cleared = (f["reason"] ?? "") == "cleared_by_repeat"
        if s.oxygen && cleared {
            return ("the next resting waveform", "urgent_page", "the repeat stays under 88% at rest")
        }
        let positional = !(f["pattern_trigger"] ?? "").isEmpty || s.exert
        if s.oxygen && positional {
            return ("resting SpO2 back in band", "urgent_page", "resting SpO2 stays below the band")
        }
        if s.oxygen {
            return ("a second resting reading", "silent_log", "the repeat is back in band on a good waveform")
        }
        return ("the next scheduled vital", "provider_task", "a new red-flag reading appears")
    }

    /// Explicit `mi_wait_minutes`, else the first duration in the wait or flip text, else a situation default.
    private static func resolvedWaitMinutes(_ f: [String: String], waitFor: String, flipIf: String, signals: HomeHealthBrief.Signals, goals: (kind: String, line: String, blocks: Bool)) -> Int {
        if let raw = nonempty(f["mi_wait_minutes"]), let n = Int(raw), n > 0 { return n }
        if let n = HomeHealthWaitClock.parseMinutes(waitFor) { return n }
        if let n = HomeHealthWaitClock.parseMinutes(flipIf) { return n }
        return defaultWaitMinutes(f, signals, goals)
    }

    /// Used when the wait text names no clock. Visible on the face as 10m, 30m, 2h, or 4h.
    private static func defaultWaitMinutes(_ f: [String: String], _ s: HomeHealthBrief.Signals, _ goals: (kind: String, line: String, blocks: Bool)) -> Int {
        if goals.blocks { return 240 }
        if s.neuro { return 10 }
        if s.chest { return 10 }
        if s.fall && s.bleed { return 30 }
        let cleared = (f["reason"] ?? "") == "cleared_by_repeat"
        if s.oxygen && cleared { return 30 }
        let positional = !(f["pattern_trigger"] ?? "").isEmpty || s.exert
        if s.oxygen && positional { return 120 }
        if s.oxygen { return 30 }
        return 240
    }

    private static func deriveGoals(_ f: [String: String]) -> (kind: String, line: String, blocks: Bool) {
        let raw = tidy(f["goals"] ?? "")
        let g = raw.lowercased()
        if g.contains("do-not-hospital") || g.contains("do not hospital") || g.contains("dnh") {
            return ("dnh", "Would refuse hospital. Do-not-hospitalize.", true)
        }
        if g.contains("hospice") || g.contains("comfort") {
            return ("comfort", "Would refuse hospital transfer. Comfort-focused.", true)
        }
        if g.contains("hospital if") || g.contains("hospital care if") {
            return ("hospital_if_needed", "Hospital is acceptable if home treatment does not recover.", false)
        }
        if raw.isEmpty || g == "not recorded" {
            return ("unstated", "Goals of care are not recorded.", false)
        }
        return ("stated", raw, false)
    }

    private static func defaultRefusal(_ f: [String: String]) -> String {
        if (f["route"] ?? "").isEmpty {
            return "Layer 1 did not own a route. You choose. This card does not auto-pass."
        }
        return "The proposing agent refused this decision. You choose Log only, Pass, or a role action. This card does not auto-pass."
    }

    private static func overrideList(_ raw: String?) -> [String]? {
        guard let raw = nonempty(raw) else { return nil }
        let parts = raw.components(separatedBy: " | ").map(tidy).filter { !$0.isEmpty }
        return parts.isEmpty ? nil : parts
    }

    private static func overrideBool(_ raw: String?) -> Bool? {
        switch raw {
        case "1": return true
        case "0": return false
        default: return nil
        }
    }

    private static func nonempty(_ raw: String?) -> String? {
        let t = tidy(raw ?? "")
        return t.isEmpty ? nil : t
    }

    private static func tidy(_ text: String) -> String {
        text.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

/// Clock for a Wait. Pure so tests can check the window without the simulator.
enum HomeHealthWaitClock {
    /// First number with an hour or minute unit. "few minutes" is 10. A bare clinical number (38.5 C, 88%) is not a duration.
    static func parseMinutes(_ text: String) -> Int? {
        let pattern = #"(\d+(?:\.\d+)?)\s*(hours?|hrs?|minutes?|mins?)\b"#
        if let regex = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]) {
            let range = NSRange(text.startIndex..., in: text)
            if let match = regex.firstMatch(in: text, options: [], range: range),
               let numberRange = Range(match.range(at: 1), in: text),
               let unitRange = Range(match.range(at: 2), in: text),
               let value = Double(text[numberRange]) {
                let unit = text[unitRange].lowercased()
                let minutes = unit.hasPrefix("h") ? value * 60 : value
                return max(1, Int(minutes.rounded()))
            }
        }
        if text.range(of: #"\bfew\s+minutes?\b"#, options: [.regularExpression, .caseInsensitive]) != nil {
            return 10
        }
        return nil
    }

    static func faceLabel(minutes: Int) -> String {
        let minutes = max(1, minutes)
        if minutes < 60 { return "\(minutes)m" }
        let hours = minutes / 60
        let rest = minutes % 60
        if rest == 0 { return "\(hours)h" }
        return "\(hours)h \(rest)m"
    }

    /// Sim-clock deadline. Whole minutes stay whole so the ledger string round-trips through `Double`.
    static func deadlineString(now: Double, minutes: Int) -> String {
        let value = now + Double(max(1, minutes))
        if abs(value - value.rounded()) < 0.001 { return String(Int(value.rounded())) }
        return String(format: "%.3f", value)
    }

    static func wallDeadlineISO(minutes: Int, from now: Date = Date()) -> String {
        DecisionLedger.iso(now.addingTimeInterval(TimeInterval(max(1, minutes)) * 60))
    }

    static func parseISO(_ text: String) -> Date? {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter.date(from: text)
    }

    static func remaining(now: Double, deadline: Double) -> String {
        let left = deadline - now
        if left <= 0 { return "OVERDUE" }
        let mins = Int(ceil(left - 1e-9))
        if mins <= 0 { return "OVERDUE" }
        return "\(faceLabel(minutes: mins)) left"
    }

    /// True when either the domain clock or the wall clock has passed the window.
    static func isOverdue(domainNow: Double, deadlineMinutes: Double, wallNow: Date, deadlineWall: Date) -> Bool {
        domainNow >= deadlineMinutes || wallNow >= deadlineWall
    }

    static func overdueLine(_ observation: String) -> String {
        let name = observation.trimmingCharacters(in: .whitespacesAndNewlines)
        let who = name.isEmpty ? "the named observation" : name
        return "OVERDUE. Waited for \(who). The observation did not arrive."
    }

    /// Payload for the automatic recheck. The route is unchanged. Nothing is paged.
    static func recheckContext(_ context: [String: String], observation: String) -> [String: String] {
        var next = context
        let name = observation.isEmpty ? (context["voi_observation"] ?? "") : observation
        next["review_action"] = "voi_recheck"
        next["voi_observation"] = name
        next["voi_wait_overdue"] = "1"
        next["voi_recheck"] = "1"
        next["wait_overdue_line"] = overdueLine(name)
        return next
    }
}
