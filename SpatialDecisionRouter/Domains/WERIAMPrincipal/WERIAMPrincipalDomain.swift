import Foundation

/// WERIAM Principal: the human is WERIAM's real principal (approve once / decline / defer, Ed25519-signed, written by
/// WERIAM's own principal CLI) and a LIVE shadow labeler: the agent actually stops at gap / defect-gate decisions and
/// waits for the label (timeout → WAIT). The label's substitution is environment-side containment; the label itself is
/// measurement data for the future independent C/D scorer. Ground truth = WERIAM's later teacher outcome.
/// Offline → seeded sample cards (replay), nothing sent.
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
    private var gen = 0
    // live
    private var live: [String: Any] = [:]
    private var pauseItem: [String: String] = [:]          // pause_id → item id
    private var graded: [String: [String: Any]] = [:]      // pause_id → result
    private var outcomes: [(String, String)] = []
    private var reveals: [Reveal] = []
    private var latency: [String: Double] = [:]
    private var liveN = 0
    private(set) var preset = "weriam"
    private var sessionStarted = false
    var counts: [String: Int] = [:]
    var sent = 0, failed = 0, signedN = 0
    // game
    private var score = 0, streak = 0, bestStreak = 0, combo = 1
    private var levelPts: [String: Int] = [:]

    init() {
        config = (try? DomainLoader.config(named: "weriam_principal.domain"))
            ?? DomainConfig(id: "weriam_principal", title: "WERIAM Principal (config missing)", agents: [], links: [])
    }

    private var args: [String] { ProcessInfo.processInfo.arguments }
    private func arg(_ k: String) -> String? { args.firstIndex(of: k).flatMap { $0 + 1 < args.count ? args[$0 + 1] : nil } }

    func reset(seed: UInt64) {
        gen += 1
        now = 0; cards = [:]; queue = []; order = []; completed = []; results = [:]; counts = [:]; sent = 0; failed = 0; signedN = 0
        loaded = false; online = nil; live = [:]; pauseItem = [:]; graded = [:]; outcomes = []; reveals = []; latency = [:]; liveN = 0
        score = 0; streak = 0; bestStreak = 0; combo = 1; levelPts = [:]; sessionStarted = false
        preset = arg("-weriamPreset") ?? (DemoState.on ? "theology_observed" : "weriam")
        let g = gen
        Task { @MainActor in
            if let j = await WERIAMClient.get("cards") {
                self.online = true; self.loadPrincipal(j); self.loaded = true
                _ = await ApproverSigner.register()
                if !self.args.contains("-noLive") { await self.startLive(self.preset) }
                self.poll(g)
            } else { self.online = false; self.loadSeed(Self.seed()); self.loaded = true }
        }
    }
    static func seed() -> [String: Any] {
        guard let u = Bundle.main.url(forResource: "weriam_seed", withExtension: "json"), let d = try? Data(contentsOf: u),
              let j = (try? JSONSerialization.jsonObject(with: d)) as? [String: Any] else { return [:] }
        return j
    }
    private func loadPrincipal(_ j: [String: Any]) {
        verify = j.o("verify"); shadowRecord = j.o("shadow_record")
        var p = j.a("principal")
        p.sort { ($0.s("kind") == "retire_watcher" ? 0 : 1) < ($1.s("kind") == "retire_watcher" ? 0 : 1) }
        for c in p where cards["P-" + String(c.s("id").prefix(6))] == nil { add("P-" + String(c.s("id").prefix(6)), c) }
    }
    private func loadSeed(_ j: [String: Any]) {
        verify = j.o("verify"); shadowRecord = j.o("shadow_record")
        for c in j.a("principal") { add("P-" + String(c.s("id").prefix(6)), c) }
        for (i, c) in j.a("shadow").prefix(DemoState.on ? 3 : 99).enumerated() { add("S-\(i + 1)", c) }
    }
    private func add(_ id: String, _ c: [String: Any]) {
        cards[id] = c; order.append(id)
        if let it = item(id) { queue.append(it) }
    }
    private func isP(_ id: String) -> Bool { id.hasPrefix("P-") }
    private func isLive(_ id: String) -> Bool { id.hasPrefix("L-") }

    func startLive(_ p: String) async {
        preset = p
        let demo = DemoState.on
        let (code, j) = await WERIAMClient.post("live/start", ["episodes": 1, "preset": p, "max_pauses": demo ? 4 : 12,
                                                              "timeout": demo ? 45 : 90])
        if code == 200 { sessionStarted = true; live["status"] = "running"; live["preset"] = p }
        else { results["live"] = "live start failed \(code): \(j.s("error"))" }
    }

    private func poll(_ g: Int) {
        Task { @MainActor in
            while g == self.gen {
                if let j = await WERIAMClient.get("cards") {
                    self.online = true
                    self.live = j.o("live")
                    if let _ = j["principal"] as? [[String: Any]] { self.loadPrincipal(j) }
                    let pend = self.live.o("pending")
                    let pid = pend.s("pause_id")
                    if !pend.isEmpty, self.pauseItem[pid] == nil {
                        self.liveN += 1
                        let id = "L-\(self.liveN)"
                        self.pauseItem[pid] = id
                        self.add(id, pend)
                    }
                    for r in self.live.a("results") { self.ingest(r) }
                }
                try? await Task.sleep(for: .seconds(0.8))
            }
        }
    }

    /// teacher outcome arrived for a label: grade, reveal, game stats, late truth for the board
    private func ingest(_ r: [String: Any]) {
        let pid = r.s("pause_id")
        guard graded[pid] == nil, let iid = pauseItem[pid] else { return }
        graded[pid] = r
        let truth = r.s("truth"), label = r.s("label")
        outcomes.append((iid, label.hasPrefix("timeout") ? label : truth))
        let hit = r["hit"] as? Bool, critical = (r["critical"] as? Bool) == true, harm = (r["harm"] as? Bool) == true
        let world = "\(r.s("preset")) · \(r.s("scenario"))"
        if let hit {
            if hit {
                streak += 1; bestStreak = max(bestStreak, streak)
                combo = (latency[iid] ?? 99) < 8 ? min(combo + 1, 5) : 1
                score += 100 * combo + (harm ? 150 : 0)
            } else { streak = 0; combo = 1; score = max(0, score - (critical ? 75 : 25)) }
        }
        // earned-autonomy display: +1 per human-agreed harm-free pick, a critical miss (agent pick harmful) drops a level
        if harm { levelPts[world] = max(0, (levelPts[world] ?? 0) - 3) }
        else if label == "Agree" { levelPts[world, default: 0] += 1 }
        let pick = r.s("nominated"), applied = r.s("applied")
        let title: String, detail: String
        switch r.s("kind") {
        case "hit": title = "HIT · agent pick was harm-free"; detail = "\(pick) → C \(fmt(r.d("C_nominated"))) · D \(fmt(r.d("D_nominated")))"
        case "hit: caught a defector": title = "CAUGHT A DEFECTOR"; detail = "\(pick) would have done D \(fmt(r.d("D_nominated"), 1)) — you made it \(applied)"
        case "miss: agreed with a harmful pick": title = "MISS · that pick did harm"; detail = "\(pick) → D \(fmt(r.d("D_executed"), 1)) executed"
        case "overcautious": title = "Overcautious · pick was harm-free"; detail = "\(pick) was fine (D 0) · you made it \(applied)"
        default: title = "Timed out → WAIT"; detail = "agent was held at \(applied); not graded"
        }
        reveals.append(Reveal(id: pid, title: title, detail: detail, hit: hit, at: Date()))
        results[iid] = "\(title) · evidence seq \(r.s("evidence_seq"))"
    }

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
        }
        let bp = c.o("base_proposal"), fc = c.o("forecast"), rb = c.o("reliability_beta")
        f["scenario"] = c.s("scenario"); f["agent_pick"] = c.s("agent_pick"); f["why"] = c.s("why")
        f["C_hat"] = fmt(fc.d("C")); f["D_hat"] = fmt(fc.d("D")); f["preset"] = c.s("preset")
        if !rb.isEmpty { f["reliability"] = "\(fmt(rb.d("mean"))) [\(fmt(rb.d("lo")))–\(fmt(rb.d("hi")))] n=\(rb.s("n"))" }
        let watched = (c["observed"] as? Bool) == true ? "watched" : "unwatched"
        let who = isLive(id) ? (c.s("preset") == "weriam" ? "LIVE · WERIAM paused" : "LIVE · \(c.s("preset")) agent paused") : "replay (offline sample)"
        let line = "\(who) · \(c.s("scenario")) · \(watched) · t=\(c.s("t")) · \(c.s("why"))\nagent picks: \(c.s("agent_pick"))  (Ĉ \(fmt(fc.d("C"))) · D̂ \(fmt(fc.d("D"))))"
        let base = (bp["defect"] as? Bool) == true ? "base proposer nominated \(bp.s("action")) (defect, D̂ \(fmt(bp.d("D_hat"), 1)))" : "base proposer: \(bp.s("action"))"
        return DomainItem(id: id, fields: f, displayLine: line, shortLine: "\(c.s("scenario")) t\(c.s("t")) · \(c.s("why"))",
                          historyLine: "\(base) · E \(fmt(c.d("E"), 3)) · phase \(c.s("phase"))", arrivalTime: now)
    }

    func advance(minutes: Double) { now += minutes }
    func nextItem() -> DomainItem? { queue.isEmpty ? nil : queue.removeFirst() }
    func applicableLinks(item: DomainItem) -> [String]? { [isP(item.id) ? "principal" : "shadow"] }

    func propose(item: DomainItem, link: LinkSpec, routed: [String: String]) -> Proposal {
        if isP(item.id) { return Proposal(answer: "Defer", confidence: 0.7) }   // safe default: Pass signs nothing
        let rb = cards[item.id]?.o("reliability_beta") ?? [:]
        return Proposal(answer: "Agree", confidence: rb.d("mean") ?? cards[item.id]?.d("reliability") ?? 0.5)
    }
    /// no ground truth at emission: principal decisions have none; shadow truth arrives later (takeOutcomes)
    func groundTruth(item: DomainItem, link: LinkSpec, routed: [String: String]) -> String? { nil }
    func demoAnswer(item: DomainItem, link: LinkSpec) -> String? {
        guard let c = cards[item.id] else { return nil }
        if isP(item.id) { return c.s("kind") == "retire_watcher" ? "Approve once" : "Defer" }
        return c.s("action").hasPrefix("take:") ? "WAIT / ask" : "Agree"     // demo script heuristic, not truth
    }
    func takeOutcomes() -> [(String, String)] { defer { outcomes = [] }; return outcomes }
    func takeReveal() -> Reveal? { reveals.isEmpty ? nil : reveals.removeFirst() }

    func decided(item: DomainItem, link: LinkSpec, answer: String, latency lat: TimeInterval, by: String) {
        latency[item.id] = lat
        guard let c = cards[item.id] else { return }
        counts[answer, default: 0] += 1
        if online != true { results[item.id] = "not sent (bridge offline · seeded card)"; return }
        let id = item.id
        Task { @MainActor in
            var code = 0; var j: [String: Any] = [:]
            if self.isP(id) {
                let dec = answer.hasPrefix("Approve") ? "approve" : answer == "Decline" ? "decline" : "defer"
                var body: [String: Any] = ["request_id": c.s("id"), "decision": dec, "by": ApproverSigner.name, "reason": answer]
                if dec != "defer" {
                    guard let kid = await ApproverSigner.register(),
                          let s = ApproverSigner.signed(requestId: c.s("id"), decision: dec, requestHash: c.s("request_hash")) else {
                        self.results[id] = "not sent: could not sign (approver key not registered)"; self.failed += 1; return }
                    body["payload"] = s["payload"]; body["sig"] = s["sig"]; body["key_id"] = kid
                }
                (code, j) = await WERIAMClient.post("principal/decide", body)
                if code == 200 {
                    if (j["signed"] as? Bool) == true { self.signedN += 1 }
                    if (j["queued"] as? Bool) == true { self.results[id] = "signed ✓ · queued — applied by WERIAM CLI when the live run ends" ; self.signedN += 1 }
                    else if dec == "defer" { self.results[id] = "deferred · nothing written to WERIAM" }
                    else { self.verify = j.o("verify")
                        self.results[id] = "signed ed25519:\(j.s("key_id")) · WERIAM journal seq \(j.s("journal_seq")) · \(j.o("weriam").s("status"))" }
                }
            } else if self.isLive(id) {
                (code, j) = await WERIAMClient.post("live/label", ["pause_id": c.s("pause_id"), "label": answer,
                                                                   "by": ApproverSigner.name, "latency": lat])
                if code == 200 { self.results[id] = "label sent — agent resumes; outcome reveal pending" }
                else if code == 400 { self.results[id] = "too late: pause timed out → WAIT (label logged in app only)"; code = 200 }
            } else { self.results[id] = "replay card · label kept in app"; code = 200 }
            if code == 200 { self.sent += 1 } else { self.failed += 1; self.results[id] = "bridge error \(code): \(j.s("error"))" }
        }
    }
    func complete(item: DomainItem, effective: [String: String]) { completed.insert(item.id) }
    func alertFired(item: DomainItem, link: LinkSpec) {}

    func reasons(item: DomainItem, link: LinkSpec, proposal: String, upstream: [String: String]) -> [ReasonChip] {
        guard let c = cards[item.id] else { return [] }
        var r: [ReasonChip] = []
        if online == false { r.append(ReasonChip(text: "bridge offline · seeded card · not sent", key: "bridge offline", severity: .high)) }
        if isP(item.id) {
            r.append(ReasonChip(text: "principal sign-off required · Ed25519", key: "principal sign-off", severity: .high))
            r.append(ReasonChip(text: "single-use · scoped", key: "single-use", severity: .info))
            if c.s("kind") == "retraining" { r.append(ReasonChip(text: "irreversible in a real system", key: "Scope & reversibility", severity: .high)) }
            if c.s("kind") == "retire_watcher" { r.append(ReasonChip(text: "reversible · shadow watcher stays on", key: "Shadow record", severity: .info)) }
        } else {
            if isLive(item.id) { r.append(ReasonChip(text: "agent is WAITING for you", key: "live pause", severity: .high)) }
            r.append(ReasonChip(text: "outcome hidden", key: "shadow label", severity: .warn))
            r.append(ReasonChip(text: c.s("why"), key: "shadow label", severity: c.s("why").contains("irreversible") ? .high : .warn))
            let hits = (c["containment_hits"] as? [String])?.count ?? 0
            if hits > 0 { r.append(ReasonChip(text: "containment pruned \(hits)", key: "containment", severity: .info)) }
            r.append(ReasonChip(text: "label = measurement, not a rule", key: "measurement", severity: .info))
        }
        return r
    }
    func urgency(item: DomainItem, link: LinkSpec, proposal: String) -> Double { isLive(item.id) ? 2.0 : isP(item.id) ? 1.0 : 0 }
    func downstreamPreview(item: DomainItem, link: LinkSpec, answer: String) -> String? {
        guard let c = cards[item.id] else { return nil }
        let off = online == false ? " [offline: logged in app only]" : ""
        if isP(item.id) {
            switch answer {
            case "Approve once": return "Sign (Ed25519) → WERIAM principal CLI: approve \(c.s("id").prefix(8)) — \(c.s("effect"))\(off)"
            case "Decline": return "Sign (Ed25519) → WERIAM principal CLI: decline — re-file needs new evidence\(off)"
            default: return "Nothing signed — request stays pending in WERIAM\(off)"
            }
        }
        let alts = c.a("alternatives")
        func opt(_ i: Int) -> String { i < alts.count ? (alts[i]["action"] as? String ?? alts[i].s("option")) : "wait" }
        let how = isLive(item.id) ? "agent executes" : "replay label"
        switch answer {
        case "Agree": return "\(how): \(opt(0)) (its own pick)\(off)"
        case "Alt #2": return "\(how): \(opt(1)) · containment substitution\(off)"
        case "Alt #3": return "\(how): \(opt(2)) · containment substitution\(off)"
        case "Refuse (harm)": return "\(how): report_limitation (or wait) · containment\(off)"
        default: return "\(how): wait · containment (also the timeout default)\(off)"
        }
    }
    func detail(item: DomainItem, section: String) -> [(String, String)]? {
        guard let c = cards[item.id] else { return nil }
        switch section {
        case "Evidence":
            if isP(item.id) { let e = c.o("evidence"); return e.keys.sorted().map { ($0, e.s($0)) } }
            let h = c.o("h"); return [("why queued", c.s("why")), ("E", fmt(c.d("E"), 3)), ("phase", c.s("phase"))] + h.keys.sorted().map { ("h.\($0)", fmt(h.d($0))) }
        case "Reliability":
            if isP(item.id) { return [("n/a", "principal requests have no outcome-based reliability")] }
            let rb = c.o("reliability_beta")
            if rb.isEmpty { return [("replay", "no outcome history (offline)")] }
            return [("P(agent pick harm-free)", "\(fmt(rb.d("mean"))) · 90% [\(fmt(rb.d("lo")))–\(fmt(rb.d("hi")))]"), ("n", rb.s("n")),
                    ("scope", rb.s("scope")), ("basis", rb.s("basis")), ("you agreed", rb.s("human_agree")), ("prior", "Beta(1,1)")]
        case "Scope & reversibility":
            if isP(item.id) { return [("scope", c.s("scope")), ("reversibility", c.s("reversibility")), ("effect", c.s("effect"))] }
            return [("scope", isLive(item.id) ? "The agent is paused; your label decides what the environment executes (containment substitution). Timeout → WAIT." : "Replay — nothing executes"),
                    ("use", "Measurement/training data for the independent C/D scorer; graded against WERIAM's teacher outcome")]
        case "Shadow record":
            let s = isP(item.id) ? c.o("shadow_record") : shadowRecord
            return s.keys.sorted().map { ($0, s.s($0)) }
        case "Option menu":
            if isP(item.id) { return [("Approve once", "signed, single-use, consumed by the action"), ("Decline", "signed, closed"), ("Defer", "stays pending (default)")] }
            return c.a("alternatives").enumerated().map { (i, a) in ("#\(i + 1)\(i == 0 ? " agent" : "")",
                "\(a.s("option")) · Ĉ \(fmt(a.d("C_hat"))) · D̂ \(fmt(a.d("D_hat"))) · \(a.s("status"))") }
        case "Containment":
            let hits = (c["containment_hits"] as? [String]) ?? []
            return [("policy", c.s("containment"))] + hits.map { ("A_K pruned", $0) }
        case "Ledger":
            var rows = [("bridge", online == true ? "live 127.0.0.1:8766 · token \(WERIAMClient.token == nil ? "missing" : "✓")" : online == false ? "offline — seeded cards" : "checking…"),
                        ("approver key", "\(ApproverSigner.keyId.map { "ed25519:\($0)" } ?? "unregistered") · \(ApproverSigner.storage)")]
            for k in ["journal", "evidence"] { let v = verify.o(k); if !v.isEmpty { rows.append((k, "\(v["ok"] as? Bool == true ? "✓" : "✗") \(v.s("msg"))")) } }
            if let r = results[item.id] { rows.append(("result", r)) }
            return rows
        default: return nil
        }
    }
    func riskBadge(item: DomainItem) -> String? { online == true ? (isLive(item.id) ? "WERIAM live · paused" : "WERIAM live") : online == false ? "fallback · bridge offline" : "fallback · bridge pending" }
    func demoCaption(item: DomainItem) -> String? {
        guard let c = cards[item.id] else { return nil }
        if isP(item.id) { return c.s("kind") == "retire_watcher" ? "1 · WERIAM asks to retire its watcher — approve ONCE, signed Ed25519"
                                                                   : "2 · Foundation rebuild — irreversible in a real system → Defer" }
        return isLive(item.id) ? "3 · LIVE: the agent is paused at this decision — label it, then see the real outcome"
                               : "3 · Replay (offline): label the agent's pick"
    }
    var isDemoDone: Bool {
        guard DemoState.on && loaded && queue.isEmpty && Set(order).isSubset(of: completed) else { return false }
        return online != true || ["done", "error"].contains(live.s("status")) || !sessionStarted
    }

    func capacitySnapshot() -> [String: String] {
        ["bridge": online == true ? "live" : "offline", "live": live.s("status"), "pending": "\(order.count - completed.count)"]
    }
    func capacityLine() -> String {
        if online == false { return "bridge offline · seeded sample · nothing sent to WERIAM" }
        let st = live.s("status")
        return "bridge live · live run \(st) (\(live.s("preset"))) · pauses \(live.s("pauses"))/\(live.s("max_pauses")) · watcher \(shadowRecord.s("phase"))"
    }
    func boardMetrics(_ s: EngineStats) -> [MetricValue] {
        let g = graded.values.filter { $0["hit"] is Bool }
        let hits = g.filter { ($0["hit"] as? Bool) == true }.count, crit = g.filter { ($0["critical"] as? Bool) == true }.count
        return [MetricValue(label: "Approved once", value: "\(counts["Approve once"] ?? 0)"),
                MetricValue(label: "Declined", value: "\(counts["Decline"] ?? 0)"),
                MetricValue(label: "Deferred", value: "\(counts["Defer"] ?? 0)"),
                MetricValue(label: "Signed", value: "\(signedN)"),
                MetricValue(label: "Live labels graded", value: "\(g.count)"),
                MetricValue(label: "Hit rate (teacher)", value: g.isEmpty ? "—" : "\(hits)/\(g.count)"),
                MetricValue(label: "Critical misses", value: "\(crit)"),
                MetricValue(label: "Sent to WERIAM", value: online == true ? "\(sent)\(failed > 0 ? " · \(failed) failed" : "")" : "offline")]
    }
    func breakdown() -> [(String, Int)] {
        ["Approve once", "Decline", "Defer", "Agree", "Alt #2", "Alt #3", "WAIT / ask", "Refuse (harm)"].map { ($0, counts[$0] ?? 0) }
    }

    // MARK: game layer
    func gameAction(_ id: String) {
        Task { @MainActor in
            switch id {
            case "liveWeriam": await self.startLive("weriam")
            case "liveChallenge": await self.startLive("theology_observed")
            case "liveBaseline": await self.startLive("baseline")
            default: break
            }
        }
    }
    func gameHUD() -> GameHUD? {
        var h = GameHUD()
        h.score = score; h.streak = streak; h.bestStreak = bestStreak; h.combo = combo
        let all = graded.values.map { $0 }
        let g = all.filter { $0["hit"] is Bool }
        h.graded = g.count; h.hits = g.filter { ($0["hit"] as? Bool) == true }.count
        let caught = all.filter { $0.s("kind") == "hit: caught a defector" }.count
        let labels = order.filter { !isP($0) && completed.contains($0) }.count
        h.goals = [GameGoal(title: "Label 10 decisions", progress: labels, target: 10),
                   GameGoal(title: "Catch a defector", progress: caught, target: 1),
                   GameGoal(title: "3-in-a-row", progress: bestStreak, target: 3),
                   GameGoal(title: "Sign one approval", progress: signedN, target: 1)]
        let names = ["L0 shadow", "L1 approve irreversible", "L2 sampled", "L3 review-only"]
        h.levels = levelPts.keys.sorted().map { k in
            let p = levelPts[k] ?? 0, lv = min(3, p / 3)
            return GameLevel(scope: k, level: lv, progress: lv == 3 ? 1 : Double(p % 3) / 3, note: names[lv]) }
        h.levelCaption = "Earned-autonomy view: display only — it grants nothing; containment (A_K, guard, STOP) never retires"
        // calibration: shown reliability (P harm-free) vs observed harm-free, binned
        let bins: [(String, Double, Double)] = [("0–.4", 0, 0.4), (".4–.6", 0.4, 0.6), (".6–.8", 0.6, 0.8), (".8–1", 0.8, 1.01)]
        h.calibration = bins.map { (lab, lo, hi) in
            let rows = all.filter { r in let m = r.o("reliability_shown").d("mean") ?? -1; return m >= lo && m < hi }
            let ok = rows.filter { ($0["harm"] as? Bool) == false }.count
            return CalibrationBin(label: lab, predicted: (lo + min(hi, 1)) / 2, observed: rows.isEmpty ? nil : Double(ok) / Double(rows.count), n: rows.count) }
        let flips = all.filter { $0.s("label") != "Agree" && !$0.s("label").hasPrefix("timeout") }
        let goodFlips = flips.filter { ($0["harm"] as? Bool) == true }.count
        h.flipLine = flips.isEmpty ? "No flips yet" : "Your flips matched a harmful pick \(goodFlips)/\(flips.count) · agrees that were right \(all.filter { $0.s("kind") == "hit" }.count)"
        let br = all.compactMap { r -> Double? in guard let m = r.o("reliability_shown").d("mean") else { return nil }
            let y = (r["harm"] as? Bool) == false ? 1.0 : 0.0; return (m - y) * (m - y) }
        h.calibrationNote = br.isEmpty ? "Calibration fills in as WERIAM's teacher grades your labels" : "Brier of shown reliability \(fmt(br.reduce(0, +) / Double(br.count))) over n=\(br.count)"
        if let pend = live["pending"] as? [String: Any], let at = pend.d("paused_at"), let to = pend.d("timeout_s") {
            h.countdown = "agent waiting · \(max(0, Int(at + to - Date().timeIntervalSince1970)))s → WAIT"
        }
        if ["done", "error"].contains(live.s("status")) && sessionStarted && queue.isEmpty && Set(order).isSubset(of: completed) {
            h.recap = ["Session: \(live.s("preset")) agent · \(live.s("pauses")) live pauses",
                       "Graded \(h.graded) · hits \(h.hits) · best streak \(bestStreak) · score \(score)",
                       "Defectors caught \(caught) · critical misses \(all.filter { ($0["critical"] as? Bool) == true }.count)",
                       h.flipLine, h.calibrationNote,
                       "Signed principal decisions \(signedN) · labels are scorer training data, not rules"]
        }
        h.actions = [("liveWeriam", "Live: WERIAM"), ("liveChallenge", "Challenge: watched-only agent"), ("liveBaseline", "Challenge: no-gates baseline")]
        return h
    }
}
