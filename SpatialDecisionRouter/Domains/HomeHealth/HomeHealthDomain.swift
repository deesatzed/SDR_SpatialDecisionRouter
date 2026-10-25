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
            self.queue = self.vignettes.enumerated().map { index, vignette in
                self.item(vignette, arrival: Double(index))
            }
            self.ready = true
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
        let meaning = [
            "silent_log": "Silent log keeps a record and opens no human task",
            "nurse_task": "Nurse queue: contact within about 24 h (same-shift hospice nurse when goals say so)",
            "provider_task": "Provider queue: same-business-day review, not a page",
            "urgent_page": "Urgent page: page someone now",
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
            MetricValue(label: "Reviewed", value: "\(reviewed)/\(vignettes.count)"),
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

/// Near-field decision: case, route, one reason, Pass / Modify. Rule text stays in Details.
struct HomeHealthNowFace: View {
    @Environment(RouterEngine.self) private var engine
    let handoff: Handoff
    let item: DomainItem
    var body: some View {
        let route = handoff.proposal
        let ticket = item.fields["ticket_type"] ?? "none"
        let plain = item.fields["plain_reason"] ?? ""
        let note = item.fields["note"] ?? ""
        let why = !plain.isEmpty ? plain : (note.isEmpty ? item.historyLine : note)
        let badge = engine.domain.riskBadge(item: item) ?? ""
        VStack(alignment: .leading, spacing: 18) {
            HStack(alignment: .center, spacing: 12) {
                Text("NOW").font(.title3.bold()).padding(.horizontal, 12).padding(.vertical, 5)
                    .background(.blue, in: Capsule())
                Text(item.id).font(.sdrHuge.bold()).lineLimit(1).minimumScaleFactor(0.5)
                HomeHealthRouteChip(route: route)
                Spacer(minLength: 8)
                if !badge.isEmpty {
                    Text(shortBadge(badge)).font(.headline.bold()).lineLimit(1)
                        .padding(.horizontal, 10).padding(.vertical, 4)
                        .background(NowCard.badgeFill(badge), in: Capsule())
                        .help(badge)
                        .gloss(NowCard.badgeKey(badge))
                }
            }
            Text(why).font(.title).lineLimit(2).gloss("plain reason")
            if !ticket.isEmpty, ticket != "none" {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Device ticket").font(.title3.bold()).foregroundStyle(.black)
                        .padding(.horizontal, 12).padding(.vertical, 5)
                        .background(.orange, in: Capsule()).gloss("device ticket")
                    if let detail = item.fields["ticket_detail"], !detail.isEmpty {
                        Text(detail).font(.title3).foregroundStyle(.orange).lineLimit(2).gloss("device ticket")
                    }
                }
            }
            Text(HomeHealthRoute.action(route, ticket: ticket))
                .font(.title2.bold()).foregroundStyle(.green).lineLimit(2)
                .gloss("what happens next")
            ActionRow {
                Button(handoff.trigger != nil ? "Acknowledge ✓" : (handoff.link.id == engine.config.review.escalationLink ? "Sign off ✓" : "Pass ✓")) { engine.pass(handoff.id) }.tint(.green)
                if handoff.link.answerType == .binary { Button("Flip") { engine.flip(handoff.id) }.tint(.orange) }
                else if handoff.trigger == nil { Button("Modify…") { engine.openRing(handoff.id) }.tint(.blue) }
                if handoff.trigger == nil, handoff.link.id == engine.config.review.escalationLink {
                    Button("Escalate") { engine.escalate(handoff.id) }.tint(.red)
                }
                #if os(visionOS)
                Spacer()
                #endif
                Button(engine.detailOpen ? "ⓘ Hide" : "ⓘ Details") { engine.sideTab = "details"; engine.toggleDetail() }.tint(.gray)
            }
            .font(.title.bold())
            Text("\(Int(handoff.confidence * 100))% · Details has the note, rule, and library label")
                .font(.title3).foregroundStyle(.secondary).lineLimit(1)
        }
        .sdrWidth(860).padding(28).sdrPanel()
    }
    private func shortBadge(_ b: String) -> String {
        if b.hasPrefix("L1 live") { return "L1 live" }
        if b.hasPrefix("L1 bundled") { return "Bundled" }
        return b
    }
}
