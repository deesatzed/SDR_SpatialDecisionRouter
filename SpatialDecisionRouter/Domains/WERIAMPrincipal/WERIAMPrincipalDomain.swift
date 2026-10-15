import Foundation

/// WERIAM Principal: the human is WERIAM's real principal (approve once / decline / defer its requests) and a
/// shadow-mode labeler of its gap-solver / gate decisions. Cards come from the localhost bridge (weriam_bridge/);
/// Approve/Decline are written by WERIAM's own principal CLI (single-use, scoped, hash-chained). Shadow labels are
/// measurement data for the future independent C/D scorer — not rules. Offline → seeded sample cards, nothing sent.
@MainActor final class WERIAMPrincipalDomain: DomainModule {
    let config: DomainConfig
    private(set) var now: Double = 0
    var minutesPerSecond: Double { config.capacity["minutesPerSecond"] ?? 1 }
    private var cards: [String: [String: Any]] = [:]
    private var queue: [DomainItem] = []
    private var order: [String] = []
    private(set) var online: Bool? = nil
    private var loaded = false
    private var completed: Set<String> = []
    private var results: [String: String] = [:]
    private var verify: [String: Any] = [:]
    private var shadowRecord: [String: Any] = [:]
    var counts: [String: Int] = [:]
    var sent = 0, failed = 0

    init() {
        config = (try? DomainLoader.config(named: "weriam_principal.domain"))
            ?? DomainConfig(id: "weriam_principal", title: "WERIAM Principal (config missing)", agents: [], links: [])
    }

    func reset(seed: UInt64) {
        now = 0; cards = [:]; queue = []; order = []; completed = []; results = [:]; counts = [:]; sent = 0; failed = 0
        loaded = false; online = nil
        Task { @MainActor in
            if let live = await WERIAMClient.get("cards") { self.online = true; self.load(live) }
            else { self.online = false; self.load(Self.seed()) }
        }
    }
    static func seed() -> [String: Any] {
        guard let u = Bundle.main.url(forResource: "weriam_seed", withExtension: "json"), let d = try? Data(contentsOf: u),
              let j = (try? JSONSerialization.jsonObject(with: d)) as? [String: Any] else { return [:] }
        return j
    }
    private func load(_ j: [String: Any]) {
        verify = j.o("verify"); shadowRecord = j.o("shadow_record")
        var p = j.a("principal"), s = j.a("shadow")
        if DemoState.on { s = Array(s.prefix(3)) }
        p.sort { ($0.s("kind") == "retire_watcher" ? 0 : 1) < ($1.s("kind") == "retire_watcher" ? 0 : 1) }
        for c in p { add("P-" + String(c.s("id").prefix(6)), c) }
        for (i, c) in s.enumerated() { add("S-\(i + 1)", c) }
        loaded = true
    }
    private func add(_ id: String, _ c: [String: Any]) {
        cards[id] = c; order.append(id)
        if let it = item(id) { queue.append(it) }
    }
    private func isP(_ id: String) -> Bool { id.hasPrefix("P-") }

    private func item(_ id: String) -> DomainItem? {
        guard let c = cards[id] else { return nil }
        let off = online == false
        var f: [String: String] = ["kind": c.s("type"), "bridge": off ? "offline-seeded" : "live"]
        if isP(id) {
            let e = c.o("evidence"), k = c.s("kind")
            f["request_id"] = c.s("id"); f["request_kind"] = k
            for (kk, v) in e { f["ev.\(kk)"] = "\(v)" }
            let line: String
            switch k {
            case "retire_watcher":
                line = "Retire the watcher · E \(fmt(e.d("E"))) vs E_crit \(fmt(e.d("E_crit"))) · \(e.s("temptations_in_window")) temptations · \(e.s("load_bearing")) load-bearing / \(e.s("decisions_in_window")) · procedures \(e.s("operators_ok") == "1" || e.s("operators_ok") == "true" ? "ok" : "not ok")"
            case "retraining":
                line = "Foundation rebuild · base proposer defect rate \(Int(((e.d("base_defect_rate") ?? 0) * 100).rounded()))% over \(e.s("decisions")) decisions"
            default: line = "\(k) · " + e.keys.sorted().prefix(3).map { "\($0) \(e.s($0))" }.joined(separator: " · ")
            }
            return DomainItem(id: id, fields: f, displayLine: line, shortLine: "\(k) · \(c.s("id").prefix(8))",
                              historyLine: c.s("scope"), arrivalTime: now)
        } else {
            let bp = c.o("base_proposal"), fc = c.o("forecast")
            f["scenario"] = c.s("scenario"); f["agent_pick"] = c.s("agent_pick"); f["why"] = c.s("why")
            f["reliability"] = fmt(c.d("reliability")); f["C_hat"] = fmt(fc.d("C")); f["D_hat"] = fmt(fc.d("D"))
            let watched = (c["observed"] as? Bool) == true ? "watched" : "unwatched"
            let line = "\(c.s("scenario")) · \(watched) · t=\(c.s("t")) · \(c.s("why"))\nagent picks: \(c.s("agent_pick"))  (Ĉ \(fmt(fc.d("C"))) · D̂ \(fmt(fc.d("D"))))"
            let base = (bp["defect"] as? Bool) == true ? "base proposer nominated \(bp.s("action")) (defect, D̂ \(fmt(bp.d("D_hat"), 1)))" : "base proposer: \(bp.s("action"))"
            return DomainItem(id: id, fields: f, displayLine: line, shortLine: "\(c.s("scenario")) t\(c.s("t")) · \(c.s("why"))",
                              historyLine: "\(base) · E \(fmt(c.d("E"), 3)) · phase \(c.s("phase"))", arrivalTime: now)
        }
    }

    func advance(minutes: Double) { now += minutes }
    func nextItem() -> DomainItem? { queue.isEmpty ? nil : queue.removeFirst() }
    func applicableLinks(item: DomainItem) -> [String]? { [isP(item.id) ? "principal" : "shadow"] }

    func propose(item: DomainItem, link: LinkSpec, routed: [String: String]) -> Proposal {
        // principal: the safe default is Defer (Pass signs nothing); shadow: the agent's own pick (#1 on the menu)
        if isP(item.id) { return Proposal(answer: "Defer", confidence: 0.7) }
        return Proposal(answer: "Agree", confidence: cards[item.id]?.d("reliability") ?? 0.5)
    }
    func groundTruth(item: DomainItem, link: LinkSpec, routed: [String: String]) -> String? {
        guard DemoState.on, let c = cards[item.id] else { return nil }   // demo script only; no ground truth exists
        if isP(item.id) { return c.s("kind") == "retire_watcher" ? "Approve once" : "Defer" }
        return item.id == "S-2" ? "WAIT / ask" : "Agree"
    }

    func complete(item: DomainItem, effective: [String: String]) {
        completed.insert(item.id)
        guard let c = cards[item.id], let ans = effective[isP(item.id) ? "principal" : "shadow"] else { return }
        counts[ans, default: 0] += 1
        if online != true { results[item.id] = "not sent (bridge offline · seeded card)"; return }
        let id = item.id
        Task { @MainActor in
            let (code, j): (Int, [String: Any])
            if self.isP(id) {
                let dec = ans.hasPrefix("Approve") ? "approve" : ans == "Decline" ? "decline" : ans.hasPrefix("Defer") ? "defer" : "defer"
                (code, j) = await WERIAMClient.post("principal/decide", ["request_id": c.s("id"), "decision": dec,
                                                                          "by": "W. Allen Satz (SDR app)", "reason": ans])
                if code == 200 { self.verify = j.o("verify")
                    self.results[id] = dec == "defer" ? "deferred · nothing written to WERIAM"
                        : "WERIAM journal seq \(j.s("journal_seq")) · \(j.o("weriam").s("status")) · chain \(self.verify["ok"] as? Bool == true ? "ok" : "BROKEN")" }
            } else {
                (code, j) = await WERIAMClient.post("shadow/label", ["id": c.s("id"), "label": ans, "by": "W. Allen Satz (SDR app)"])
                if code == 200 { self.results[id] = "label stored (\(j.s("human_label")))" }
            }
            if code == 200 { self.sent += 1 } else { self.failed += 1; self.results[id] = "bridge error \(code): \(j.s("error"))" }
        }
    }
    func alertFired(item: DomainItem, link: LinkSpec) {}

    func reasons(item: DomainItem, link: LinkSpec, proposal: String, upstream: [String: String]) -> [ReasonChip] {
        guard let c = cards[item.id] else { return [] }
        var r: [ReasonChip] = []
        if online == false { r.append(ReasonChip(text: "bridge offline · seeded card · not sent", key: "bridge offline", severity: .high)) }
        if isP(item.id) {
            r.append(ReasonChip(text: "principal sign-off required", key: "principal sign-off", severity: .high))
            r.append(ReasonChip(text: "single-use · scoped", key: "single-use", severity: .info))
            if c.s("kind") == "retraining" { r.append(ReasonChip(text: "irreversible in a real system", key: "Scope & reversibility", severity: .high)) }
            if c.s("kind") == "retire_watcher" { r.append(ReasonChip(text: "reversible · shadow watcher stays on", key: "Shadow record", severity: .info)) }
        } else {
            r.append(ReasonChip(text: "shadow · outcome hidden", key: "shadow label", severity: .warn))
            r.append(ReasonChip(text: c.s("why"), key: "shadow label", severity: c.s("why").contains("irreversible") ? .high : .warn))
            let hits = (c["containment_hits"] as? [String])?.count ?? 0
            if hits > 0 { r.append(ReasonChip(text: "containment pruned \(hits)", key: "containment", severity: .info)) }
            r.append(ReasonChip(text: "label = measurement, not a rule", key: "measurement", severity: .info))
        }
        return r
    }
    func urgency(item: DomainItem, link: LinkSpec, proposal: String) -> Double { isP(item.id) ? 1.0 : 0 }
    func downstreamPreview(item: DomainItem, link: LinkSpec, answer: String) -> String? {
        guard let c = cards[item.id] else { return nil }
        let off = online == false ? " [offline: logged in app only]" : ""
        if isP(item.id) {
            switch answer {
            case "Approve once": return "WERIAM principal CLI: approve \(c.s("id").prefix(8)) — \(c.s("effect"))\(off)"
            case "Decline": return "WERIAM principal CLI: decline — request closed; re-file needs new evidence\(off)"
            default: return "Nothing signed — request stays pending in WERIAM\(off)"
            }
        }
        let alts = c.a("alternatives")
        func opt(_ i: Int) -> String { i < alts.count ? alts[i].s("option") : "(none)" }
        switch answer {
        case "Agree": return "Scorer set: agree with \(opt(0)) · counterfactual only\(off)"
        case "Alt #2": return "Scorer set: prefer \(opt(1)) · counterfactual only\(off)"
        case "Alt #3": return "Scorer set: prefer \(opt(2)) · counterfactual only\(off)"
        default: return "Scorer set: label '\(answer)' · counterfactual only\(off)"
        }
    }
    func detail(item: DomainItem, section: String) -> [(String, String)]? {
        guard let c = cards[item.id] else { return nil }
        switch section {
        case "Evidence":
            if isP(item.id) { let e = c.o("evidence"); return e.keys.sorted().map { ($0, e.s($0)) } }
            let h = c.o("h"); return [("why queued", c.s("why")), ("E", fmt(c.d("E"), 3)), ("phase", c.s("phase")),
                                      ("reliability (heuristic)", fmt(c.d("reliability")))] + h.keys.sorted().map { ("h.\($0)", fmt(h.d($0))) }
        case "Scope & reversibility":
            if isP(item.id) { return [("scope", c.s("scope")), ("reversibility", c.s("reversibility")), ("effect", c.s("effect"))] }
            return [("scope", "Counterfactual label only — nothing executes on your pick"),
                    ("use", "Training/measurement data for the independent C/D scorer (export joins the later-observed outcome)")]
        case "Shadow record":
            let s = isP(item.id) ? c.o("shadow_record") : shadowRecord
            return s.keys.sorted().map { ($0, s.s($0)) }
        case "Option menu":
            if isP(item.id) { return [("Approve once", "single-use, consumed by the action"), ("Decline", "closed"), ("Defer", "stays pending (default)")] }
            return c.a("alternatives").enumerated().map { (i, a) in ("#\(i + 1)\(i == 0 ? " agent" : "")",
                "\(a.s("option")) · Ĉ \(fmt(a.d("C_hat"))) · D̂ \(fmt(a.d("D_hat"))) · \(a.s("status"))") }
        case "Containment":
            let hits = (c["containment_hits"] as? [String]) ?? []
            return [("policy", c.s("containment"))] + hits.map { ("A_K pruned", $0) }
        case "Ledger":
            var rows = [("bridge", online == true ? "live 127.0.0.1:8766" : online == false ? "offline — seeded cards" : "checking…")]
            for k in ["journal", "evidence"] { let v = verify.o(k); if !v.isEmpty { rows.append((k, "\(v["ok"] as? Bool == true ? "✓" : "✗") \(v.s("msg"))")) } }
            if let r = results[item.id] { rows.append(("result", r)) }
            return rows
        default: return nil
        }
    }
    func riskBadge(item: DomainItem) -> String? { online == true ? "WERIAM live" : online == false ? "fallback · bridge offline" : "fallback · bridge pending" }
    func demoCaption(item: DomainItem) -> String? {
        guard let c = cards[item.id] else { return nil }
        if isP(item.id) { return c.s("kind") == "retire_watcher" ? "1 · Agent asks to retire its watcher — approve ONCE via WERIAM's own CLI"
                                                                   : "2 · Foundation rebuild — irreversible in a real system → Defer" }
        return item.id == "S-2" ? "4 · Shadow: you'd rather WAIT/ask — prospective label, outcome still hidden"
                                : "3 · Shadow mode: label the agent's pick before seeing the outcome"
    }
    var isDemoDone: Bool { DemoState.on && loaded && queue.isEmpty && Set(order).isSubset(of: completed) }

    func capacitySnapshot() -> [String: String] {
        ["bridge": online == true ? "live" : "offline", "journal": verify.o("journal").s("msg"), "pending": "\(order.count - completed.count)"]
    }
    func capacityLine() -> String {
        let j = verify.o("journal")
        return online == false ? "bridge offline · seeded sample · nothing sent to WERIAM"
            : "bridge live · journal \(j["ok"] as? Bool == true ? "chain ✓" : "?") \(j.s("msg")) · watcher \(shadowRecord.s("phase"))"
    }
    func boardMetrics(_ s: EngineStats) -> [MetricValue] {
        let agree = counts["Agree"] ?? 0, labels = ["Agree", "Alt #2", "Alt #3", "WAIT / ask", "Refuse (harm)"].reduce(0) { $0 + (counts[$1] ?? 0) }
        return [MetricValue(label: "Approved once", value: "\(counts["Approve once"] ?? 0)"),
                MetricValue(label: "Declined", value: "\(counts["Decline"] ?? 0)"),
                MetricValue(label: "Deferred", value: "\(counts["Defer"] ?? 0)"),
                MetricValue(label: "Shadow labels", value: "\(labels)"),
                MetricValue(label: "Agree rate", value: labels == 0 ? "—" : "\(Int(Double(agree) / Double(labels) * 100))%"),
                MetricValue(label: "Sent to WERIAM", value: online == true ? "\(sent)\(failed > 0 ? " · \(failed) failed" : "")" : "offline"),
                MetricValue(label: "Hash chain", value: verify["ok"] as? Bool == true ? "verified ✓" : verify.isEmpty ? "—" : "check ✗")]
    }
    func breakdown() -> [(String, Int)] {
        ["Approve once", "Decline", "Defer", "Agree", "Alt #2", "Alt #3", "WAIT / ask", "Refuse (harm)"].map { ($0, counts[$0] ?? 0) }
    }
}
