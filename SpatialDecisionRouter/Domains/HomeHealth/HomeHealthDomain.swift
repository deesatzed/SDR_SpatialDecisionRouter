import Foundation
import SwiftUI

/// Home-health HITM review. Layer 1 proposes silent_log / nurse_task / provider_task / urgent_page
/// and, when it files one, a device_maintenance ticket. Cases are the bundled synthetic library pack.
/// A localhost bridge (127.0.0.1:8767) recomputes the same pack; if it is down the bundled snapshot is shown.
@MainActor final class HomeHealthDomain: DomainModule {
    let config: DomainConfig
    private(set) var now: Double = 0
    var minutesPerSecond: Double { config.capacity["minutesPerSecond"] ?? 1 }

    private var vignettes: [HHVignette] = []
    private var patternCases: [HHVignette] = []
    private var patterns: [String: HHPattern] = [:]
    private var queue: [DomainItem] = []
    private var ready = false
    private var live: Bool?
    private var packMissing = false
    private var gen = 0
    private var engineVersion = "v1.14.4"
    private var paramsVersion = "0.14.4-placeholder"
    private var counts: [String: Int] = [:]
    private var reviewed = 0
    private var urgentConfirmed = 0

    init() {
        config = (try? DomainLoader.config(named: "homehealth.domain"))
            ?? DomainConfig(id: "home_health", title: "Home health (config missing)", agents: [], links: [])
    }

    static func loadPack() -> HHPack? {
        guard let url = Bundle.main.url(forResource: "homehealth_vignettes", withExtension: "json"),
              let data = try? Data(contentsOf: url) else { return nil }
        return try? JSONDecoder().decode(HHPack.self, from: data)
    }

    func reset(seed: UInt64) {
        gen += 1
        let generation = gen
        now = 0
        ready = false
        live = nil
        counts = [:]
        reviewed = 0
        urgentConfirmed = 0
        queue = []
        loadPatterns()
        if let pack = Self.loadPack() {
            vignettes = pack.cases
            engineVersion = pack.engine_version
            paramsVersion = pack.params_version
            packMissing = false
        } else {
            vignettes = []
            packMissing = true
        }
        Task { @MainActor in
            guard generation == self.gen else { return }
            if let livePack = await HomeHealthClient.fetchCases() {
                guard generation == self.gen else { return }
                self.apply(livePack)
                self.live = true
            } else {
                self.live = false
            }
            self.rebuildQueue()
            self.ready = true
        }
    }

    func pattern(for caseId: String) -> HHPattern? { patterns[caseId] }

    private func loadPatterns() {
        patternCases = []
        patterns = [:]
        guard let url = Bundle.main.url(forResource: "homehealth_patterns", withExtension: "json"),
              let data = try? Data(contentsOf: url),
              let pack = try? JSONDecoder().decode(HHPatternPack.self, from: data) else { return }
        patternCases = pack.cases.map(\.vignette)
        patterns = Dictionary(uniqueKeysWithValues: pack.cases.map { ($0.pattern.case_id, $0.pattern) })
    }

    private func rebuildQueue() {
        let all = patternCases + vignettes
        queue = all.enumerated().map { index, vignette in
            item(vignette, arrival: Double(index))
        }
    }

    private func apply(_ livePack: HomeHealthClient.Live) {
        engineVersion = livePack.engine_version
        paramsVersion = livePack.params_version
        let byId = Dictionary(uniqueKeysWithValues: livePack.cases.map { ($0.case_id, $0.layer1) })
        for i in vignettes.indices {
            if let layer = byId[vignettes[i].case_id] { vignettes[i].layer1 = layer }
        }
    }

    func advance(minutes: Double) { now += minutes }

    func nextItem() -> DomainItem? {
        guard ready, !queue.isEmpty else { return nil }
        return queue.removeFirst()
    }

    func propose(item: DomainItem, link: LinkSpec, routed: [String: String]) -> Proposal {
        let route = item.fields["route"] ?? ""
        if link.options.contains(route) { return Proposal(answer: route, confidence: 0.93) }
        return Proposal(answer: link.options.first ?? "silent_log", confidence: 0.45)
    }

    /// The human is the reviewer. Layer 1's route is the proposal, not a second ground truth.
    func groundTruth(item: DomainItem, link: LinkSpec, routed: [String: String]) -> String? { nil }

    func complete(item: DomainItem, effective: [String: String]) {
        reviewed += 1
        counts[effective["route"] ?? "?", default: 0] += 1
    }

    func alertFired(item: DomainItem, link: LinkSpec) { urgentConfirmed += 1 }

    func reasons(item: DomainItem, link: LinkSpec, proposal: String, upstream: [String: String]) -> [ReasonChip] {
        var chips = [ReasonChip(text: "home-health review", key: "home health", severity: .info)]
        if item.fields["route"] == "urgent_page" || proposal == "urgent_page" {
            chips.append(ReasonChip(text: "urgent page", key: "urgent page", severity: .high))
        }
        if (item.fields["ticket_type"] ?? "none") != "none" {
            chips.append(ReasonChip(text: "device ticket", key: "device ticket", severity: .warn))
        }
        if (item.fields["route"] ?? "").isEmpty {
            chips.append(ReasonChip(text: "Layer 1 deferred", key: "Layer 1", severity: .warn))
        }
        if live == false {
            chips.append(ReasonChip(text: "bridge offline", key: "bridge offline", severity: .warn))
        }
        return chips
    }

    func urgency(item: DomainItem, link: LinkSpec, proposal: String) -> Double {
        switch item.fields["route"] {
        case "urgent_page": return 1.4
        case "provider_task": return 0.7
        case "nurse_task": return 0.45
        case "silent_log": return (item.fields["ticket_type"] ?? "none") == "none" ? 0.1 : 0.25
        default: return 0.2
        }
    }

    func downstreamPreview(item: DomainItem, link: LinkSpec, answer: String) -> String? {
        guard link.id == "route" else { return nil }
        let who = HomeHealthSeat.recipient(route: answer, fields: item.fields)
        let meaning = [
            "silent_log": "Log only. No page and no handoff. Nobody is tasked. The Overseer is not the recipient.",
            "nurse_task": "Pass a nurse task to \(who ?? "Night nurse"). Not to the Overseer.",
            "provider_task": "Pass a provider task to \(who ?? "On-call HH MD"). Not a page, and not to the Overseer.",
            "urgent_page": "Pass an urgent page to \(who ?? "On-call HH MD"). The Overseer is not paged.",
        ]
        var text = meaning[answer] ?? answer
        let ticket = item.fields["ticket_type"] ?? "none"
        if answer == "silent_log", ticket != "none", item.fields["route"] == "silent_log" {
            let detail = item.fields["ticket_detail"] ?? ""
            text += ". Device ticket: \(ticket)" + (detail.isEmpty ? "" : " — \(detail)")
        } else if answer != "silent_log" {
            text += ". No device ticket on a clinical route"
        } else {
            text += ". No device ticket"
        }
        return text
    }

    func detail(item: DomainItem, section: String) -> [(String, String)]? {
        switch section {
        case "Vignette":
            return [
                ("Case", dash(item.fields["case_id"])),
                ("Who", "\(item.fields["age_band"] ?? "") \(item.fields["sex"] ?? "") · \(dash(item.fields["living"]))"),
                ("Problems", dash(item.fields["pmh"])),
                ("Medicines", dash(item.fields["meds"])),
                ("Devices", dash(item.fields["devices"])),
                ("Goals", dash(item.fields["goals"])),
                ("Function", dash(item.fields["function"])),
                ("Baseline", dash(item.fields["baseline"])),
                ("Baseline status", dash(item.fields["baseline_status"])),
                ("Discharge", dash(item.fields["discharge"])),
                ("Device flags", dash(item.fields["artifact_flags"])),
                ("Trend", dash(item.fields["trend"])),
                ("Note", dash(item.fields["note"])),
                ("Library file", dash(item.fields["source_file"])),
            ]
        case "Layer 1":
            let route = item.fields["route"] ?? ""
            let ticket = item.fields["ticket_type"] ?? "none"
            let source = item.fields["decision_source"] == "live" ? "live bridge (recomputed)" : "bundled snapshot (bridge offline)"
            return [
                ("Route", route.isEmpty ? "none (Layer 1 deferred)" : route),
                ("Means", dash(item.fields["route_definition"])),
                ("Owner", dash(item.fields["owner"])),
                ("Tier", dash(item.fields["tier"])),
                ("Rule", dash(item.fields["rule"])),
                ("Reason", dash(item.fields["reason"])),
                ("Plain reason", dash(item.fields["plain_reason"])),
                ("Escalation target", dash(item.fields["escalation_target"])),
                ("Device ticket", ticket == "none" ? "none" : ticket),
                ("Ticket detail", dash(item.fields["ticket_detail"])),
                ("Ticket note", dash(item.fields["ticket_note"])),
                ("Decision source", source),
                ("Engine", dash(item.fields["engine_version"])),
                ("Params", dash(item.fields["params_version"])),
                ("Library label", dash(item.fields["library_label"])),
            ]
        default:
            return nil
        }
    }

    func riskBadge(item: DomainItem) -> String? {
        if packMissing { return "L1 bundled · pack missing" }
        if live == true { return "L1 live · \(engineVersion)" }
        return "L1 bundled · bridge offline"
    }

    func capacitySnapshot() -> [String: String] {
        let bridge: String
        if packMissing { bridge = "pack missing" }
        else if live == true { bridge = "live" }
        else if live == false { bridge = "offline" }
        else { bridge = "checking" }
        return [
            "bridge": bridge,
            "engine": engineVersion,
            "params": paramsVersion,
            "queued": "\(queue.count)",
            "reviewed": "\(reviewed)",
            "urgent_signed": "\(urgentConfirmed)",
        ]
    }

    func capacityLine() -> String {
        if packMissing { return "vignette pack missing from the app bundle" }
        if live == true { return "bridge live · Layer 1 \(engineVersion) · params \(paramsVersion)" }
        if live == nil { return "checking Layer 1 bridge…" }
        return "bridge offline · bundled Layer 1 \(engineVersion) · params \(paramsVersion)"
    }

    func boardMetrics(_ s: EngineStats) -> [MetricValue] {
        [
            MetricValue(label: "Reviewed", value: "\(reviewed)/\(vignettes.count + patternCases.count)"),
            MetricValue(label: "Urgent signed", value: "\(urgentConfirmed)"),
            MetricValue(label: "Bridge", value: live == true ? "live" : "bundled"),
        ]
    }

    func breakdown() -> [(String, Int)] {
        ["silent_log", "nurse_task", "provider_task", "urgent_page"].compactMap { id in
            guard let n = counts[id] else { return nil }
            return (id, n)
        }
    }

    private func item(_ v: HHVignette, arrival: Double) -> DomainItem {
        let route = v.layer1.route ?? ""
        let ticket = v.layer1.ticket?.type ?? "none"
        let fields: [String: String] = [
            "home_health": "1",
            "case_id": v.case_id,
            "source_file": v.source,
            "library_label": v.library_label ?? "",
            "age_band": v.age_band,
            "sex": v.sex,
            "living": v.living,
            "pmh": v.pmh,
            "meds": v.meds,
            "devices": v.devices,
            "goals": v.goals,
            "function": v.function,
            "baseline": v.baseline,
            "baseline_status": v.baseline_status,
            "discharge": v.discharge,
            "trend": v.trend,
            "note": v.note,
            "artifact_flags": v.artifact_flags,
            "route": route,
            "route_definition": v.layer1.route_definition ?? "",
            "owner": v.layer1.owner ?? "",
            "tier": v.layer1.tier ?? "",
            "rule": v.layer1.rule ?? "",
            "reason": v.layer1.reason ?? "",
            "plain_reason": v.layer1.plain_reason ?? "",
            "escalation_target": v.layer1.escalation_target ?? "",
            "ticket_type": ticket,
            "ticket_detail": v.layer1.ticket?.detail ?? "",
            "ticket_rule": v.layer1.ticket?.rule ?? "",
            "ticket_note": v.layer1.ticket_note ?? "",
            "decision_source": live == true ? "live" : "bundled",
            "engine_version": engineVersion,
            "params_version": paramsVersion,
            "review_role": "overseer",
            "recipient": HomeHealthSeat.recipient(route: route, fields: [
                "goals": v.goals, "route": route,
            ]) ?? "log only",
            "pattern_trigger": patterns[v.case_id]?.trigger ?? "",
            "pattern_headline": patterns[v.case_id]?.headline ?? "",
            "pattern_fixture": patterns[v.case_id]?.fixture == true ? "1" : "",
        ]
        let shown = route.isEmpty ? "no Layer 1 route" : route
        let ticketBit = ticket == "none" ? "no device ticket" : "ticket \(ticket)"
        let history = v.note.isEmpty ? v.trend : v.note
        return DomainItem(
            id: v.case_id,
            fields: fields,
            displayLine: "[SYNTHETIC] \(v.case_id) · \(v.age_band) \(v.sex) · \(shown) · \(ticketBit)",
            shortLine: "\(v.case_id) \(shown)",
            historyLine: history,
            arrivalTime: arrival)
    }

    private func dash(_ s: String?) -> String {
        let t = s ?? ""
        return t.isEmpty ? "—" : t
    }
}

enum HomeHealthRoute {
    static func color(_ id: String) -> Color {
        switch id {
        case "urgent_page": .red
        case "provider_task": .orange
        case "nurse_task": .yellow
        case "silent_log": .teal
        default: .gray
        }
    }
    static func title(_ id: String) -> String {
        switch id {
        case "silent_log": "Silent log"
        case "nurse_task": "Nurse task"
        case "provider_task": "Provider task"
        case "urgent_page": "Urgent page"
        default: id.replacingOccurrences(of: "_", with: " ")
        }
    }
    /// One line for the decision face. Same meaning as the route previews; not a second router.
    static func action(_ id: String, ticket: String) -> String {
        let base: String
        switch id {
        case "silent_log": base = "Log only. No human task."
        case "nurse_task": base = "Send a nurse task."
        case "provider_task": base = "Send a provider task. Not a page."
        case "urgent_page": base = "Page someone now."
        default: base = "Pass accepts \(title(id))."
        }
        if id == "silent_log", !ticket.isEmpty, ticket != "none" { return base + " File a device ticket." }
        return base
    }
}

/// Display names for who receives a route. The Overseer is the physician reviewing it.
/// These labels do not change Layer 1's route or where the engine flies a Pass.
enum HomeHealthSeat {
    static let framing = "Overseeing · routes to on-call"

    static func recipient(route: String, fields: [String: String]) -> String? {
        switch route {
        case "nurse_task":
            let goals = (fields["goals"] ?? "").lowercased()
            if goals.contains("hospice") || goals.contains("comfort-focused") { return "On-call hospice nurse" }
            return "Night nurse"
        case "provider_task", "urgent_page":
            return "On-call HH MD"
        default:
            return nil
        }
    }

    static func recipientChip(route: String, fields: [String: String]) -> String {
        recipient(route: route, fields: fields) ?? "Log only"
    }

    /// Button title. Names the other person so Pass does not read as sending the case to the Overseer.
    static func passTitle(route: String, fields: [String: String]) -> String {
        switch route {
        case "urgent_page": return "Pass page to On-call MD"
        case "provider_task": return "Pass to On-call MD"
        case "nurse_task":
            let goals = (fields["goals"] ?? "").lowercased()
            if goals.contains("hospice") || goals.contains("comfort-focused") { return "Pass to hospice nurse" }
            return "Pass to Night nurse"
        default:
            return "Log only"
        }
    }

    /// Same split the engine already uses: urgent_page flies to the page node, other routes to the desk.
    static func deskId(for route: String) -> String {
        route == "urgent_page" ? "urgent" : "routes"
    }
}

struct HomeHealthRouteChip: View {
    let route: String
    var prominent = true
    var body: some View {
        Text(HomeHealthRoute.title(route))
            .font(prominent ? .title.bold() : .title3.bold())
            .lineLimit(1)
            .padding(.horizontal, prominent ? 14 : 12)
            .padding(.vertical, prominent ? 8 : 6)
            .foregroundStyle(.black)
            .background(HomeHealthRoute.color(route), in: Capsule())
            .gloss("route")
    }
}

/// Awareness first. Story, rules, and the chart cascade in the order this situation makes the call hard.
enum HomeHealthBrief {
    struct Signals {
        var fall = false
        var bleed = false
        var oxygen = false
        var homeGas = false
        var exert = false
        var neuro = false
        var chest = false
        var device = false
        var goalsHold = false
        var alone = false
        var anticoag: [String] = []
        var directedMeds: [String] = []
    }

    static func hook(_ f: [String: String]) -> String {
        let s = signals(f)
        if s.fall {
            let event = first(f["note"], matching: ["floor", "fell", "fall", "impact"]) ?? firstSentence(f["note"] ?? "")
            if let drug = s.anticoag.first, !event.isEmpty { return "\(stripPeriod(event)). On \(drug)." }
            if !event.isEmpty { return event }
        }
        if s.neuro && !s.fall {
            if let line = first(f["note"], matching: ["weak", "slur", "speech", "droop"]) { return line }
        }
        if s.chest && !s.fall {
            let plain = f["plain_reason"] ?? ""
            if !plain.isEmpty && !isSlogan(plain, reason: f["reason"] ?? "") { return plain }
        }
        if s.oxygen && !s.fall && !s.neuro && !s.chest {
            if let trigger = f["pattern_trigger"], !trigger.isEmpty { return trigger }
            let today = spo2Today(f["trend"] ?? "")
            if !today.isEmpty { return today.prefix(2).joined(separator: " ") }
            let plain = f["plain_reason"] ?? ""
            if !plain.isEmpty { return plain }
        }
        let plain = f["plain_reason"] ?? ""
        if !plain.isEmpty && !isSlogan(plain, reason: f["reason"] ?? "") { return plain }
        let note = firstSentence(f["note"] ?? "")
        return note.isEmpty ? plain : note
    }

    /// Next 2–4 sentences. Highest scores are the facts that make this decision hard, not a fixed chart order.
    static func story(_ f: [String: String]) -> [String] {
        let s = signals(f)
        let lead = hook(f)
        let oxygenLead = s.oxygen && !s.fall && !s.neuro && !s.chest
        var bits: [(Int, Int, String)] = []
        var order = 0
        func add(_ score: Int, _ text: String) {
            let t = tidy(text)
            guard t.count > 2 else { return }
            if t == "none" || t == "not recorded" || t == "—" { return }
            if lead.localizedCaseInsensitiveContains(t) || t.localizedCaseInsensitiveContains(lead) { return }
            if bits.contains(where: { $0.2.localizedCaseInsensitiveCompare(t) == .orderedSame }) { return }
            bits.append((score, order, t))
            order += 1
        }
        if s.bleed && (s.fall || s.neuro) {
            for line in s.anticoag { add(96, "On \(line).") }
        }
        if s.chest {
            for line in s.directedMeds { add(94, line) }
        }
        if s.fall {
            let bleed = sentences(f["note"] ?? "").filter { contains($0, ["bleed", "consciousness", "scalp"]) }
            if !bleed.isEmpty { add(90, bleed.joined(separator: " ")) }
        }
        if s.homeGas, let q = quote(f, ["gold", "cannula", "commode", "litre", "liter"]) { add(93, q) }
        if oxygenLead, let usual = usualOxygen(f) { add(88, usual) }
        if s.exert {
            for line in sentences(f["trend"] ?? "") where contains(line, ["commode", "stair", "exert", "ambulat", "bus shelter"]) { add(84, line) }
        }
        if s.neuro && !s.fall {
            let rest = sentences(f["note"] ?? "").filter { !lead.localizedCaseInsensitiveContains($0) }
            if !rest.isEmpty { add(80, rest.joined(separator: " ")) }
        }
        if s.chest {
            for line in sentences(f["note"] ?? "") { add(92, line) }
        }
        if let problems = problemsLine(f) {
            let score = (s.oxygen && contains(problems, ["copd", "gold", "emphysema"])) ? 78 : ((s.bleed || s.neuro || s.chest) ? 74 : (s.oxygen ? 46 : 52))
            add(score, problems)
        }
        if s.goalsHold, let g = goalsLine(f) { add(s.fall ? 68 : 64, g) }
        if let who = whoLine(f) { add(s.alone && (s.fall || s.neuro || s.oxygen) ? 70 : 26, who) }
        if oxygenLead {
            for line in sentences(f["note"] ?? "") { add(62, line) }
        } else if !s.fall && !s.neuro && !s.chest {
            for line in sentences(f["note"] ?? "") { add(55, line) }
        }
        for line in sentences(f["trend"] ?? "") where line.lowercased().contains("day 0") { add(oxygenLead ? 58 : 48, line) }
        if s.device, let flag = deviceFlag(f) { add((s.oxygen || s.fall) ? 60 : 36, flag) }
        bits.sort { $0.0 == $1.0 ? $0.1 < $1.1 : $0.0 > $1.0 }
        return Array(bits.prefix(4).map(\.2))
    }

    static func rules(_ f: [String: String]) -> [(String, String)] {
        let s = signals(f)
        let oxygenLead = s.oxygen && !s.fall && !s.neuro && !s.chest
        var bits: [(Int, Int, String, String)] = []
        var order = 0
        func add(_ score: Int, _ title: String, _ body: String) {
            let b = tidy(body)
            guard b.count > 2, b != "none", b != "not recorded" else { return }
            bits.append((score, order, title, b))
            order += 1
        }
        let rule = f["rule"] ?? ""
        let tier = f["tier"] ?? ""
        let reason = f["reason"] ?? ""
        let plain = f["plain_reason"] ?? ""
        let head = [rule, tier, reason].filter { !$0.isEmpty }.joined(separator: " · ")
        let body = plain.isEmpty ? head : (head.isEmpty ? plain : "\(head). \(plain)")
        let matched = (s.fall && rule.localizedCaseInsensitiveContains("fall"))
            || (s.oxygen && rule.localizedCaseInsensitiveContains("spo2"))
            || (s.neuro && rule.localizedCaseInsensitiveContains("focal"))
            || (s.chest && (rule.localizedCaseInsensitiveContains("chest") || reason.localizedCaseInsensitiveContains("angina")))
        if !body.isEmpty { add(matched ? 100 : 78, "Rule on this case", body) }
        let routeId = f["route"] ?? ""
        if let who = HomeHealthSeat.recipient(route: routeId, fields: f) {
            add(97, "Who receives it", "\(who). The Overseer reviews the route and does not receive it.")
        } else {
            add(97, "Who receives it", "Log only. No on-call person is tasked.")
        }
        if s.homeGas, let q = quote(f, ["gold", "cannula", "commode", "litre", "liter"]) { add(96, "Oxygen setup", q) }
        if oxygenLead, let usual = usualOxygen(f) { add(92, "Their usual oxygen", usual) }
        let ticket = f["ticket_type"] ?? ""
        if !ticket.isEmpty, ticket != "none" {
            let detail = f["ticket_detail"] ?? ""
            add(94, "Device policy", detail.isEmpty ? ticket : "\(ticket). \(detail)")
        } else if s.device, let raw = f["artifact_flags"], !raw.isEmpty, raw != "none" {
            add((s.oxygen || s.fall) ? 86 : 48, "Device flag", raw)
        }
        if s.goalsHold, let g = goalsLine(f) { add(90, "Why the route changed", g) }
        if s.bleed && (s.fall || s.neuro) {
            for line in s.anticoag { add(88, "Anticoagulation", line) }
        }
        if s.chest {
            for line in s.directedMeds { add(88, "Medicine in question", line) }
        }
        if s.oxygen, let pmh = f["pmh"], contains(pmh, ["copd", "gold", "emphysema"]) { add(76, "Lung disease", pmh) }
        if let target = f["escalation_target"], !target.isEmpty { add(70, "Who would be paged", target) }
        if let means = f["route_definition"], !means.isEmpty { add(40, "Where this route goes", means) }
        bits.sort { $0.0 == $1.0 ? $0.1 < $1.1 : $0.0 > $1.0 }
        return bits.map { ($0.2, $0.3) }
    }

    static func deep(_ f: [String: String]) -> [(String, String)] {
        let s = signals(f)
        var bits: [(Int, Int, String, String)] = []
        var order = 0
        func add(_ score: Int, _ title: String, _ body: String?) {
            let b = tidy(body ?? "")
            guard b.count > 2, b != "none", b != "not recorded" else { return }
            bits.append((score, order, title, b))
            order += 1
        }
        add((s.fall || s.neuro || s.chest) ? 100 : 72, "Note", f["note"])
        add((s.oxygen || s.exert) ? 100 : 58, "Trend", f["trend"])
        add((s.bleed || s.chest) ? 96 : 54, "Medicines", f["meds"])
        let base = [f["baseline"], f["baseline_status"]].compactMap { $0 }.filter { !$0.isEmpty && $0 != "not recorded" && $0 != "none" }.joined(separator: ". ")
        add(s.oxygen ? 94 : 38, "Baseline", base)
        add(s.goalsHold ? 90 : 34, "Goals", f["goals"])
        add((s.oxygen && contains(f["pmh"] ?? "", ["copd", "gold"])) ? 88 : 50, "Problems", f["pmh"])
        let lib = f["library_label"] ?? ""
        let route = f["route"] ?? ""
        if !lib.isEmpty || !route.isEmpty {
            let gap = lib == route ? "Library and Layer 1 both say \(route)." : "Library label \(lib.isEmpty ? "none" : lib). Layer 1 routed \(route.isEmpty ? "none" : route)."
            add(82, "Library vs Layer 1", gap)
        }
        let ticket = f["ticket_type"] ?? ""
        if !ticket.isEmpty, ticket != "none" {
            let detail = f["ticket_detail"] ?? ""
            add(92, "Device ticket", detail.isEmpty ? ticket : "\(ticket). \(detail)")
        } else if let note = f["ticket_note"], !note.isEmpty {
            add(70, "Device ticket", note)
        }
        add(s.device ? 74 : 22, "Device flags", f["artifact_flags"])
        add(32, "Function", f["function"])
        add(s.alone ? 44 : 24, "Who", whoLine(f))
        add(26, "Devices", f["devices"])
        add(18, "Discharge", f["discharge"])
        bits.sort { $0.0 == $1.0 ? $0.1 < $1.1 : $0.0 > $1.0 }
        return bits.map { ($0.2, $0.3) }
    }

    static func signals(_ f: [String: String]) -> Signals {
        var s = Signals()
        let note = (f["note"] ?? "").lowercased()
        let trend = (f["trend"] ?? "").lowercased()
        let blob = [f["note"], f["trend"], f["pmh"], f["meds"], f["goals"], f["plain_reason"], f["rule"], f["reason"], f["artifact_flags"], f["baseline"], f["devices"]]
            .compactMap { $0 }.joined(separator: "\n").lowercased()
        s.fall = contains(note + "\n" + trend, ["floor", "fell", " fall", "bed-sensor impact"])
        s.anticoag = medLines(f["meds"] ?? "").filter { line in contains(line, ["apixaban", "rivaroxaban", "edoxaban", "dabigatran", "warfarin", "enoxaparin", "heparin", "doac"]) }
        s.bleed = !s.anticoag.isEmpty
        s.oxygen = contains(blob, ["spo2", "oxygen", "desat", "copd", "gold", "cannula"])
        s.homeGas = contains(blob, ["cannula", "gold", "home oxygen", "nasal"]) || (s.oxygen && blob.range(of: #"\d+(\.\d+)?\s*l"#, options: .regularExpression) != nil)
        s.exert = contains(blob, ["commode", "exert", "stair", "ambulat", "bus shelter"])
        s.neuro = contains(blob, ["weak", "slur", "droop", "stroke", "speech", "focal"])
        s.chest = contains(blob, ["angina", "gtn", "trinitrate"]) || contains((f["rule"] ?? "") + (f["reason"] ?? ""), ["CHEST", "ANGINA"])
        let ticket = f["ticket_type"] ?? ""
        let artifact = (f["artifact_flags"] ?? "").lowercased()
        let reason = (f["reason"] ?? "").lowercased()
        s.device = (!ticket.isEmpty && ticket != "none") || (!artifact.isEmpty && artifact != "none") || reason.contains("cleared") || artifact.contains("contact") || artifact.contains("motion")
        let goals = (f["goals"] ?? "").lowercased()
        s.goalsHold = f["reason"] == "goals_of_care" || goals.contains("hospice") || goals.contains("comfort")
        s.alone = (f["living"] ?? "").lowercased() == "alone"
        s.directedMeds = medLines(f["meds"] ?? "").filter { contains($0, ["trinitrate", "gtn", "spray", "nitro"]) }
        return s
    }

    private static func isSlogan(_ plain: String, reason: String) -> Bool {
        let p = plain.lowercased()
        return reason == "goals_of_care" || p.contains("rather than") || p.hasPrefix("comfort-focused")
    }
    private static func tidy(_ text: String) -> String {
        text.trimmingCharacters(in: .whitespacesAndNewlines)
    }
    private static func stripPeriod(_ text: String) -> String {
        var t = tidy(text)
        if t.hasSuffix(".") { t.removeLast() }
        return t
    }
    private static func contains(_ text: String, _ needles: [String]) -> Bool {
        let l = text.lowercased()
        return needles.contains { l.contains($0) }
    }
    private static func sentences(_ text: String) -> [String] {
        let t = tidy(text)
        if t.isEmpty || t == "none" || t == "not recorded" { return [] }
        return t.components(separatedBy: ". ").map { part in
            let s = part.trimmingCharacters(in: .whitespacesAndNewlines)
            if s.isEmpty { return "" }
            return s.hasSuffix(".") ? s : s + "."
        }.filter { $0.count > 2 }
    }
    private static func firstSentence(_ text: String) -> String { sentences(text).first ?? "" }
    private static func first(_ text: String?, matching needles: [String]) -> String? {
        guard let text else { return nil }
        return sentences(text).first { contains($0, needles) }
    }
    private static func medLines(_ meds: String) -> [String] {
        meds.split(separator: ";").map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty }
    }
    private static func spo2Today(_ trend: String) -> [String] {
        sentences(trend).filter { line in
            let l = line.lowercased()
            return l.contains("day 0") && (l.contains("spo2") || l.contains("oximeter") || l.contains("oxygen"))
        }
    }
    private static func usualOxygen(_ f: [String: String]) -> String? {
        let base = f["baseline"] ?? ""
        guard let r = base.range(of: "spo2_night_min ") else { return nil }
        let num = base[r.upperBound...].prefix { $0.isNumber || $0 == "." }
        guard !num.isEmpty else { return nil }
        var line = "Baseline lists spo2_night_min \(num)."
        let status = f["baseline_status"] ?? ""
        if !status.isEmpty && status != "not recorded" { line += " \(status)." }
        return line
    }
    private static func deviceFlag(_ f: [String: String]) -> String? {
        let a = f["artifact_flags"] ?? ""
        if a.isEmpty || a == "none" { return nil }
        return "Device flag: \(a)."
    }
    private static func goalsLine(_ f: [String: String]) -> String? {
        let g = f["goals"] ?? ""
        if g.isEmpty || g == "not recorded" { return nil }
        return "Goals: \(g)."
    }
    private static func problemsLine(_ f: [String: String]) -> String? {
        let p = f["pmh"] ?? ""
        if p.isEmpty || p == "not recorded" { return nil }
        return "Problems: \(p)."
    }
    private static func whoLine(_ f: [String: String]) -> String? {
        let age = f["age_band"] ?? ""
        let sex = f["sex"] ?? ""
        let living = f["living"] ?? ""
        var line = [age, sex].filter { !$0.isEmpty }.joined(separator: " ")
        if living == "alone" { line += line.isEmpty ? "Lives alone" : ", lives alone" }
        else if !living.isEmpty && living != "not recorded" { line += line.isEmpty ? "Lives \(living)" : ", lives \(living)" }
        if line.isEmpty { return nil }
        return line.hasSuffix(".") ? line : line + "."
    }
    private static func quote(_ f: [String: String], _ needles: [String]) -> String? {
        for key in ["note", "trend", "pmh", "goals", "baseline"] {
            if let hit = first(f[key], matching: needles) { return hit }
        }
        return nil
    }

    /// Compressed identity for the awareness face. Facts already on the vignette.
    static func patientChip(_ f: [String: String]) -> String {
        var parts: [String] = []
        let age = [f["age_band"] ?? "", f["sex"] ?? ""].filter { !$0.isEmpty }.joined(separator: " ")
        if !age.isEmpty { parts.append(age) }
        let problems = problemItems(f["pmh"] ?? "")
        if !problems.isEmpty { parts.append(problems.prefix(2).joined(separator: ", ")) }
        let meds = keyMedNames(f)
        if !meds.isEmpty { parts.append(meds.prefix(2).joined(separator: ", ")) }
        var tail = livingShort(f)
        if let o2 = oxygenShort(f) {
            let bit = (f["pattern_trigger"] ?? "").isEmpty ? o2 : "baseline \(o2)"
            tail = tail.isEmpty ? bit : "\(tail), \(bit)"
        }
        if !tail.isEmpty { parts.append(tail) }
        return parts.joined(separator: " · ")
    }

    struct ChartBlock: Identifiable {
        let id: String
        let title: String
        let summary: String
        let body: String
        let score: Int
    }

    /// Chart sections, highest score first for this situation. Summaries stay visible; one section opens at a time.
    static func chart(_ f: [String: String]) -> [ChartBlock] {
        let s = signals(f)
        let oxygenLead = s.oxygen && !s.fall && !s.neuro && !s.chest
        var blocks: [ChartBlock] = []
        let problems = problemItems(f["pmh"] ?? "")
        let pmh = tidy(f["pmh"] ?? "")
        if !pmh.isEmpty && pmh != "not recorded" {
            let summary = problems.prefix(2).joined(separator: ", ")
            blocks.append(ChartBlock(id: "pmh", title: "PMH", summary: summary.isEmpty ? pmh : summary, body: pmh, score: (s.bleed || s.neuro || s.chest) ? 70 : 44))
        }
        let meds = tidy(f["meds"] ?? "")
        if !meds.isEmpty && meds != "none" {
            let names = keyMedNames(f)
            let summary = names.isEmpty ? meds : names.joined(separator: ", ")
            let body = meds.replacingOccurrences(of: "; ", with: "\n")
            blocks.append(ChartBlock(id: "meds", title: "Meds", summary: summary, body: body, score: (s.bleed || s.chest) ? 86 : 48))
        }
        let active = activeProblems(f, s, oxygenLead: oxygenLead)
        if active.isEmpty {
            blocks.append(ChartBlock(id: "active", title: "Active problems", summary: "None tied to this situation", body: problems.isEmpty ? "No problem list on this case." : "Nothing in the problem list is the reason for this route. The list is under PMH.", score: 24))
        } else {
            blocks.append(ChartBlock(id: "active", title: "Active problems", summary: active.joined(separator: ", "), body: active.joined(separator: "\n"), score: 94))
        }
        let discharge = tidy(f["discharge"] ?? "")
        if discharge.isEmpty || discharge == "none" || discharge == "not recorded" {
            blocks.append(ChartBlock(id: "hosp", title: "Recent hospitalizations", summary: "None recorded", body: "The library discharge field is none.", score: 18))
        } else {
            blocks.append(ChartBlock(id: "hosp", title: "Recent hospitalizations", summary: discharge, body: discharge, score: 72))
        }
        let base = tidy(f["baseline"] ?? "")
        let status = tidy(f["baseline_status"] ?? "")
        if !base.isEmpty && base != "not recorded" {
            var summary = oxygenShort(f) ?? String(base.prefix(72))
            if !status.isEmpty && status != "not recorded" && status != "none" { summary += " · \(status)" }
            var body = base
            if !status.isEmpty && status != "not recorded" && status != "none" { body += "\n\(status)" }
            blocks.append(ChartBlock(id: "baseline", title: "Baselines / bands", summary: summary, body: body, score: oxygenLead ? 90 : (s.oxygen ? 55 : 36)))
        }
        let goals = tidy(f["goals"] ?? "")
        if !goals.isEmpty && goals != "not recorded" {
            let summary = goals.count > 90 ? String(goals.prefix(87)) + "…" : goals
            blocks.append(ChartBlock(id: "goals", title: "Goals of care", summary: summary, body: goals, score: s.goalsHold ? 88 : 32))
        }
        return blocks.sorted { $0.score == $1.score ? $0.title < $1.title : $0.score > $1.score }
    }

    private static func problemItems(_ pmh: String) -> [String] {
        pmh.split(separator: ",").map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty && $0 != "not recorded" }
    }
    private static func medName(_ line: String) -> String {
        var name: [String] = []
        for part in line.split(separator: " ") {
            if part.first?.isNumber == true { break }
            name.append(String(part))
        }
        return name.joined(separator: " ")
    }
    private static func keyMedNames(_ f: [String: String]) -> [String] {
        let s = signals(f)
        if !s.anticoag.isEmpty { return s.anticoag.map(medName) }
        if !s.directedMeds.isEmpty { return s.directedMeds.map(medName) }
        return medLines(f["meds"] ?? "").prefix(2).map(medName)
    }
    private static func livingShort(_ f: [String: String]) -> String {
        let living = (f["living"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if living.isEmpty || living == "not recorded" { return "" }
        if living == "alone" { return "lives alone" }
        return living
    }
    private static func oxygenShort(_ f: [String: String]) -> String? {
        let base = f["baseline"] ?? ""
        guard let r = base.range(of: "spo2_night_min ") else { return nil }
        let num = base[r.upperBound...].prefix { $0.isNumber || $0 == "." }
        guard !num.isEmpty else { return nil }
        return "night SpO₂ \(num)"
    }
    private static func activeProblems(_ f: [String: String], _ s: Signals, oxygenLead: Bool) -> [String] {
        problemItems(f["pmh"] ?? "").filter { item in
            let l = item.lowercased()
            if (s.fall || s.bleed) && (l.contains("afib") || l.contains("fibril")) { return true }
            if s.neuro && (l.contains("stroke") || l.contains("tia")) { return true }
            if s.chest && (l.contains("angina") || l.contains("cad") || l.contains("stent") || l.contains("coronary")) { return true }
            if oxygenLead && (l.contains("copd") || l.contains("gold") || l.contains("emphysema")) { return true }
            return false
        }
    }
}

/// L0 awareness. Pass and Modify stay here while story, rules, and the chart cascade beside the card.
struct HomeHealthNowFace: View {
    @Environment(RouterEngine.self) private var engine
    let handoff: Handoff
    let item: DomainItem
    private let levels = ["Awareness", "Patient details", "Rules", "More"]
    var body: some View {
        let route = handoff.proposal
        let ticket = item.fields["ticket_type"] ?? "none"
        let hook = HomeHealthBrief.hook(item.fields)
        let badge = engine.domain.riskBadge(item: item) ?? ""
        let shown = engine.homeShownLevel
        let pinned = engine.homePinnedLevel
        VStack(alignment: .leading, spacing: 16) {
            HStack(alignment: .center, spacing: 10) {
                Text(HomeHealthSeat.framing).font(.title3.bold()).lineLimit(1)
                Spacer(minLength: 8)
                Text("Physician").font(.headline.bold()).foregroundStyle(.black)
                    .padding(.horizontal, 10).padding(.vertical, 4)
                    .background(.white.opacity(0.85), in: Capsule())
            }
            HStack(spacing: 8) {
                roleSlot("Overseer", selected: true, later: false)
                roleSlot("Bedside", selected: false, later: true)
                roleSlot("Nurse HITM", selected: false, later: true)
            }
            HStack(alignment: .center, spacing: 12) {
                Text("NOW").font(.title3.bold()).padding(.horizontal, 12).padding(.vertical, 5)
                    .background(.blue, in: Capsule())
                Text(item.id).font(.sdrHuge.bold()).lineLimit(1).minimumScaleFactor(0.5)
                HomeHealthRouteChip(route: route)
                Spacer(minLength: 8)
                if item.fields["pattern_fixture"] == "1" {
                    Text("Pattern fixture").font(.headline.bold()).lineLimit(1)
                        .padding(.horizontal, 10).padding(.vertical, 4)
                        .background(.yellow, in: Capsule())
                        .help("Synthetic pattern card for the Trends section. Layer 1 did not compute this case.")
                } else if !badge.isEmpty {
                    Text(shortBadge(badge)).font(.headline.bold()).lineLimit(1)
                        .padding(.horizontal, 10).padding(.vertical, 4)
                        .background(NowCard.badgeFill(badge), in: Capsule())
                        .help(badge)
                        .gloss(NowCard.badgeKey(badge))
                }
            }
            Text(HomeHealthSeat.recipientChip(route: route, fields: item.fields))
                .font(.title2.bold()).lineLimit(1)
                .foregroundStyle(.black)
                .padding(.horizontal, 14).padding(.vertical, 6)
                .background(route == "silent_log" ? Color.gray.opacity(0.55) : Color.white.opacity(0.9), in: Capsule())
                .gloss("recipient")
            let chip = HomeHealthBrief.patientChip(item.fields)
            if !chip.isEmpty {
                Text(chip).font(.title3).foregroundStyle(.secondary).lineLimit(2).fixedSize(horizontal: false, vertical: true)
            }
            let trigger = item.fields["pattern_trigger"] ?? ""
            let week = item.fields["pattern_headline"] ?? ""
            if !trigger.isEmpty {
                Text("Why now").font(.title3.bold()).foregroundStyle(.orange)
                Text(trigger).font(.title).lineLimit(4)
                if !week.isEmpty {
                    Text("This week").font(.title3.bold()).foregroundStyle(.secondary)
                    Text(week).font(.title3).foregroundStyle(.secondary).lineLimit(3)
                }
            } else {
                Text(hook).font(.title).lineLimit(4)
            }
            if !ticket.isEmpty, ticket != "none" {
                Text("Device ticket").font(.title3.bold()).foregroundStyle(.black)
                    .padding(.horizontal, 12).padding(.vertical, 5)
                    .background(.orange, in: Capsule()).gloss("device ticket")
            }
            FlowRow(spacing: 12) {
                Button(handoff.trigger != nil ? "Acknowledge ✓" : (handoff.link.id == engine.config.review.escalationLink ? "Sign off ✓" : HomeHealthSeat.passTitle(route: route, fields: item.fields))) { engine.pass(handoff.id) }
                    .tint(.green)
                    .help(route == "silent_log" ? "No page and no handoff. Acknowledge and log the decision. Nobody is tasked." : "Sends the route to the on-call recipient. You are not the recipient.")
                if handoff.link.answerType == .binary { Button("Flip") { engine.flip(handoff.id) }.tint(.orange) }
                else if handoff.trigger == nil { Button("Change route…") { engine.openRing(handoff.id) }.tint(.blue) }
                if handoff.trigger == nil, handoff.link.id == engine.config.review.escalationLink {
                    Button("Escalate") { engine.escalate(handoff.id) }.tint(.red)
                }
                if shown > pinned {
                    Button("Pin") { engine.homeCascade() }.tint(.teal)
                } else if pinned >= 2 && pinned < 3 {
                    Button("More for this case") { engine.homeMore() }.tint(.teal)
                } else if pinned < 2 {
                    Button("Expand") { engine.homeCascade() }.tint(.teal)
                }
                if shown > 0 { Button("Collapse") { engine.homeCollapse() }.tint(.gray) }
            }
            .font(.title2.bold())
            FlowRow(spacing: 8) {
                ForEach(0..<levels.count, id: \.self) { i in
                    Button { engine.homeJump(i) } label: {
                        Text(levels[i]).font(.title3.bold())
                            .padding(.horizontal, 12).padding(.vertical, 6)
                            .background(i == shown ? Color.white.opacity(0.22) : Color.clear, in: Capsule())
                            .overlay(Capsule().stroke(i <= shown ? Color.white.opacity(0.75) : Color.white.opacity(0.28), lineWidth: 1.5))
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(i < shown ? "Collapse to \(levels[i])" : (i == shown ? levels[i] : "Cascade to \(levels[i])"))
                }
            }
            Text(shown == 0 ? "Look to cascade. Expand pins the next layer. Logged for later training." : "Collapse peels one layer. The route controls stay here. You are not the recipient.")
                .font(.title3).foregroundStyle(.secondary).lineLimit(2)
        }
        .sdrWidth(860).padding(28).sdrPanel()
        .contentShape(RoundedRectangle(cornerRadius: 22))
        #if os(visionOS)
        .onContinuousHover { phase in
            switch phase {
            case .ended: engine.homeHoverEnded()
            default: engine.homeHoverBegan()
            }
        }
        .hoverEffect(.lift)
        #else
        .onHover { inside in
            if inside { engine.homeHoverBegan() } else { engine.homeHoverEnded() }
        }
        #endif
    }
    private func roleSlot(_ title: String, selected: Bool, later: Bool) -> some View {
        Button {} label: {
            Text(later ? "\(title) · Later" : title)
                .font(.headline.bold())
                .padding(.horizontal, 12).padding(.vertical, 6)
                .foregroundStyle(selected ? Color.black : Color.secondary)
                .background(selected ? Color.white.opacity(0.9) : Color.white.opacity(0.08), in: Capsule())
                .overlay(Capsule().stroke(Color.white.opacity(selected ? 0 : 0.25), lineWidth: 1))
        }
        .buttonStyle(.plain)
        .disabled(later)
        .accessibilityLabel(later ? "\(title), later" : title)
    }
    private func shortBadge(_ b: String) -> String {
        if b.hasPrefix("L1 live") { return "L1 live" }
        if b.hasPrefix("L1 bundled") { return "Bundled" }
        return b
    }
}

/// Cascaded layers beside the awareness card. Each step adds the next situation-ordered block.
struct HomeHealthDossier: View {
    @Environment(RouterEngine.self) private var engine
    let item: DomainItem
    let level: Int
    var body: some View {
        let hook = HomeHealthBrief.hook(item.fields)
        VStack(alignment: .leading, spacing: 16) {
                HStack {
                    Text(level >= 3 ? "More" : (level == 2 ? "Rules" : "Patient details")).font(.title.bold())
                    Spacer()
                    Button("Collapse") { engine.homeCollapse() }.font(.title2.bold())
                }
                Text(hook).font(.title3).foregroundStyle(.secondary).lineLimit(3)
                if level >= 1 {
                    ForEach(Array(HomeHealthBrief.story(item.fields).enumerated()), id: \.offset) { _, line in
                        Text(line).font(.title2).fixedSize(horizontal: false, vertical: true)
                    }
                    if let pattern = (engine.domain as? HomeHealthDomain)?.pattern(for: item.id) {
                        HomeHealthTrends(pattern: pattern)
                    }
                }
                if level >= 2 {
                    Divider()
                    Text("Rules for this situation").font(.title2.bold())
                    ForEach(Array(HomeHealthBrief.rules(item.fields).enumerated()), id: \.offset) { _, row in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(row.0).font(.title3.bold()).foregroundStyle(.secondary)
                            Text(row.1).font(.title2).fixedSize(horizontal: false, vertical: true)
                        }
                    }
                    if level < 3 {
                        Button("More for this case") { engine.homeMore() }.font(.title2.bold()).tint(.teal)
                    }
                }
                if level >= 1 {
                    Divider()
                    HomeHealthChart(item: item)
                }
                if level >= 3 {
                    Divider()
                    let covered: Set<String> = ["Medicines", "Problems", "Goals", "Baseline", "Who"]
                    let extra = HomeHealthBrief.deep(item.fields).filter { !covered.contains($0.0) }
                    ForEach(Array(extra.enumerated()), id: \.offset) { _, row in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(row.0).font(.title3.bold()).foregroundStyle(.secondary)
                            Text(row.1).font(.title3).fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// Summary-first chart. One section open at a time, ordered for this situation.
struct HomeHealthChart: View {
    @Environment(RouterEngine.self) private var engine
    let item: DomainItem
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Chart").font(.title2.bold())
            ForEach(HomeHealthBrief.chart(item.fields)) { section in
                let open = engine.homeChartOpen == section.id
                Button { engine.homeChartToggle(section.id) } label: {
                    VStack(alignment: .leading, spacing: 6) {
                        HStack {
                            Text(section.title).font(.title3.bold())
                            Spacer()
                            Text(open ? "Hide" : "Show").font(.title3).foregroundStyle(.secondary)
                        }
                        Text(section.summary).font(.title3).foregroundStyle(.secondary).lineLimit(open ? 4 : 2)
                        if open {
                            Text(section.body).font(.title3).fixedSize(horizontal: false, vertical: true)
                        }
                    }
                    .padding(12)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(open ? Color.white.opacity(0.08) : Color.clear, in: RoundedRectangle(cornerRadius: 12))
                }
                .buttonStyle(.plain)
                .accessibilityLabel(open ? "Collapse \(section.title)" : "Expand \(section.title)")
            }
        }
    }
}

/// Recent pattern. Collapsed to one line until Show. Same one-open-section control as the chart.
struct HomeHealthTrends: View {
    @Environment(RouterEngine.self) private var engine
    let pattern: HHPattern
    private var open: Bool { engine.homeChartOpen == "trends" }
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Button { engine.homeChartToggle("trends") } label: {
                VStack(alignment: .leading, spacing: 6) {
                    HStack {
                        Text("Trends").font(.title2.bold())
                        Spacer()
                        Text(open ? "Hide" : "Show").font(.title3).foregroundStyle(.secondary)
                    }
                    Text(pattern.headline).font(.title3).foregroundStyle(.secondary).lineLimit(open ? 4 : 2)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .buttonStyle(.plain)
            .accessibilityLabel(open ? "Collapse trends" : "Expand trends")
            if open {
                Text(pattern.summary).font(.title3).fixedSize(horizontal: false, vertical: true)
                Text(pattern.rule_note).font(.title3).fixedSize(horizontal: false, vertical: true)
                Text("Recent alerts and actions").font(.title3.bold())
                ForEach(pattern.alerts) { event in
                    VStack(alignment: .leading, spacing: 2) {
                        Text("\(event.when) · \(event.what)").font(.title3.bold())
                        Text(event.action).font(.title3).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                    }
                }
                Text("Vitals against this patient's band").font(.title3.bold())
                ForEach(pattern.vitals) { vital in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(vital.name).font(.title3.bold())
                        Text(vital.band).font(.title3).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                        HomeHealthSpark(points: vital.points, low: vital.low, high: vital.high)
                        Text(vital.outside_note).font(.title3).foregroundStyle(.orange).fixedSize(horizontal: false, vertical: true)
                    }
                }
                Text(pattern.horizon).font(.title3).fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(12)
        .background(open ? Color.white.opacity(0.08) : Color.clear, in: RoundedRectangle(cornerRadius: 12))
    }
}

/// Compact bars. Orange is outside the band set for this patient. Teal is inside it.
struct HomeHealthSpark: View {
    let points: [Int]
    let low: Int
    let high: Int
    var body: some View {
        let lo = min(low, points.min() ?? low)
        let hi = max(high, points.max() ?? high)
        let span = max(hi - lo, 1)
        HStack(alignment: .bottom, spacing: 5) {
            ForEach(Array(points.enumerated()), id: \.offset) { _, value in
                let outside = value < low || value > high
                RoundedRectangle(cornerRadius: 2)
                    .fill(outside ? Color.orange : Color.teal)
                    .frame(width: 14, height: 8 + CGFloat(value - lo) / CGFloat(span) * 28)
                    .accessibilityLabel(outside ? "\(value) outside band" : "\(value) in band")
            }
        }
        .frame(height: 40, alignment: .bottom)
        .accessibilityElement(children: .contain)
    }
}
