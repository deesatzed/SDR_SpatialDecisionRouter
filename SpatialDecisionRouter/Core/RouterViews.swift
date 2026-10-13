import SwiftUI
import RealityKit

struct CrossroadsView: View {
    @Environment(RouterEngine.self) private var engine
    @State private var root = Entity()
    @State private var builtVersion = -1
    @State private var pulsed: [String: Date] = [:]

    var body: some View {
        RealityView { content, att in
            content.add(root); buildStatic(att)
        } update: { _, att in
            if builtVersion != engine.packVersion { buildStatic(att) }
            sync(att)
        } attachments: {
            ForEach(engine.config.agents, id: \.id) { a in
                Attachment(id: "agent-\(a.id)") { AgentCard(agent: a, received: engine.inbox[a.id] ?? 0, queued: engine.queueCount(a.id)) }
            }
            Attachment(id: "now") { NowCard() }
            Attachment(id: "upnext") { UpNextStrip() }
            Attachment(id: "side") { SidePanel() }
            Attachment(id: "ring") { OptionRing() }
            Attachment(id: "board") { BoardView() }
        }
        .task { while !Task.isCancelled { try? await Task.sleep(for: .milliseconds(50)); engine.tick(0.05) } }
        .task {
            let a = ProcessInfo.processInfo.arguments
            if let i = a.firstIndex(of: "-autoResolve"), i + 1 < a.count, let n = Int(a[i + 1]) {
                try? await Task.sleep(for: .seconds(2)); await engine.autoResolve(n)
                if a.contains("-autoExport") { engine.export() }
            }
        }
    }

    private func line(_ a: SIMD3<Float>, _ b: SIMD3<Float>) -> Entity {
        let e = ModelEntity(mesh: .generateCylinder(height: simd_distance(a, b), radius: 0.003), materials: [UnlitMaterial(color: UIColor(white: 1, alpha: 0.22))])
        e.position = (a + b) / 2; e.orientation = simd_quatf(from: [0, 1, 0], to: simd_normalize(b - a)); return e
    }

    private func place(_ att: RealityViewAttachments, _ id: String, _ p: SIMD3<Float>, _ sc: Float) {
        guard let e = att.entity(for: id) else { return }
        e.name = "att-\(id)"; e.position = p; e.scale = [sc, sc, sc]; e.components.set(BillboardComponent()); root.addChild(e)
    }

    private func buildStatic(_ att: RealityViewAttachments) {
        let cfg = engine.config
        guard cfg.agents.allSatisfy({ att.entity(for: "agent-\($0.id)") != nil }) else { return }
        for c in Array(root.children) { c.removeFromParent() }
        let env = ProceduralEnvironment.make(cfg.theme); env.isEnabled = engine.fullImmersion; root.addChild(env)
        let hub = ModelEntity(mesh: .generateSphere(radius: 0.02), materials: [UnlitMaterial(color: UIColor(white: 1, alpha: 0.6))])
        hub.position = RouterEngine.hub; root.addChild(hub)
        for (i, a) in cfg.agents.enumerated() {
            let p = engine.agentPosition(a.id)
            // context nodes: quieter (smaller, translucent)
            let node = ModelEntity(mesh: .generateSphere(radius: a.tier == 0 ? 0.08 : 0.1),
                                   materials: [SimpleMaterial(color: UIColor(hue: CGFloat(i) / CGFloat(cfg.agents.count + 1), saturation: 0.5, brightness: 0.9, alpha: 0.55), isMetallic: false)])
            node.position = p; node.name = "agent-\(a.id)"; root.addChild(node)
            root.addChild(line(p, RouterEngine.hub))
            if let card = att.entity(for: "agent-\(a.id)") {
                card.position = p + [0, a.tier == 0 ? -0.2 : 0.24, 0]; card.scale = [1.4, 1.4, 1.4]
                card.components.set(BillboardComponent()); root.addChild(card)
            }
        }
        place(att, "board", [0, 2.45, -2.05], 1.3)
        place(att, "now", RouterEngine.nowCard, 1.5)
        place(att, "upnext", RouterEngine.upNextPos, 1.15)
        place(att, "side", RouterEngine.sidePos, 1.15)
        if let r = att.entity(for: "ring") { r.name = "ringAttachment"; r.isEnabled = false; r.position = [0, 1.45, -1.0]; r.components.set(BillboardComponent()); root.addChild(r) }
        let v = engine.packVersion
        Task { @MainActor in builtVersion = v; pulsed = [:] }
    }

    private func sync(_ att: RealityViewAttachments) {
        let cfg = engine.config
        for h in engine.handoffs {
            if engine.phase[h.id] == .delivered { root.findEntity(named: h.id)?.removeFromParent(); continue }
            var e = root.findEntity(named: h.id)
            if e == nil {
                let hue = CGFloat(engine.agentIndex(h.link.source)) / CGFloat(cfg.agents.count + 1)
                let m = ModelEntity(mesh: h.link.answerType == .binary ? .generateBox(size: 0.06, cornerRadius: 0.015) : .generateSphere(radius: 0.04),
                                    materials: [SimpleMaterial(color: UIColor(hue: hue, saturation: 0.25 + 0.7 * CGFloat(h.confidence), brightness: 1, alpha: 0.9), isMetallic: false)])
                m.name = h.id; root.addChild(m); e = m
            }
            e?.position = engine.position(h)
            let s: Float = h.id == engine.nowId ? 1.6 : 1
            e?.scale = [s, s, s]
        }
        for (agent, t) in engine.lastDelivered where pulsed[agent] != t {
            if let n = root.findEntity(named: "agent-\(agent)") {
                var big = n.transform; big.scale = [1.8, 1.8, 1.8]; n.move(to: big, relativeTo: root, duration: 0.18)
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) { var s = n.transform; s.scale = [1, 1, 1]; n.move(to: s, relativeTo: root, duration: 0.35) }
            }
            Task { @MainActor in pulsed[agent] = t }
        }
        root.findEntity(named: "environment")?.isEnabled = engine.fullImmersion
        root.findEntity(named: "att-side")?.isEnabled = engine.detailOpen || engine.spotCheckOpen
        root.findEntity(named: "ringAttachment")?.isEnabled = engine.ringFor != nil
    }
}

/// Glossary-backed hover: highlight + tooltip.
struct Gloss: ViewModifier {
    @Environment(RouterEngine.self) private var engine
    let key: String
    func body(content: Content) -> some View {
        content.contentShape(.hoverEffect, RoundedRectangle(cornerRadius: 8)).hoverEffect(.highlight)
            .help(engine.config.glossary[key] ?? engine.config.glossary[key.lowercased()] ?? key)
    }
}
extension View { func gloss(_ k: String) -> some View { modifier(Gloss(key: k)) } }

struct Chip: View {
    let r: ReasonChip
    var body: some View {
        let c: Color = r.severity == .high ? .red : r.severity == .warn ? .orange : .teal
        Text(r.text).font(.callout.bold()).lineLimit(1).padding(.horizontal, 9).padding(.vertical, 3)
            .background(c.opacity(0.5), in: Capsule()).gloss(r.key)
    }
}

struct AgentCard: View {
    let agent: AgentSpec; let received: Int; let queued: Int
    var body: some View {
        HStack(spacing: 8) {
            VStack(spacing: 1) {
                Text(agent.name).font(.headline)
                if let r = agent.role { Text(r).font(.caption).foregroundStyle(.secondary) }
                if agent.tier == 1 { Text("received \(received)").font(.caption.monospacedDigit()) }
            }
            if agent.tier == 0 {
                Text("\(queued)").font(.title3.bold().monospacedDigit()).frame(minWidth: 30).padding(4)
                    .background(queued > 0 ? Color.orange.opacity(0.8) : Color.white.opacity(0.15), in: Circle()).help("items from this agent waiting in the review queue")
            }
        }.padding(8).glassBackgroundEffect().opacity(0.85)
    }
}

/// The single large decision card (top of the review queue).
struct NowCard: View {
    @Environment(RouterEngine.self) private var engine
    var body: some View {
        TimelineView(.periodic(from: .now, by: 1)) { _ in
            if let h = engine.nowHandoff { content(h) }
            else {
                Text("Queue clear · \(engine.autoPassed) auto-passed").font(.title).padding(30).frame(width: 880).glassBackgroundEffect()
            }
        }
    }
    @ViewBuilder func content(_ h: Handoff) -> some View {
        let item = engine.items[h.itemId], t = engine.config.terminology
        let src = engine.agent(h.link.source)?.name ?? h.link.source, dst = engine.agent(h.link.dest)?.name ?? h.link.dest
        let reasons = engine.reasons(h)
        let rel = engine.reliability(h)
        VStack(alignment: .leading, spacing: 10) {
            if let t = h.trigger {
                HStack {
                    Text("⚠ HARD ESCALATION — \(t)").font(.title2.bold()).foregroundStyle(.white)
                    Spacer()
                    Text("fired \(h.firedAt.map { Int(Date().timeIntervalSince($0)) } ?? 0)s ago · reliability analysis bypassed").font(.headline)
                }.padding(10).background(.red, in: RoundedRectangle(cornerRadius: 10)).gloss("hard trigger")
            }
            HStack {
                Text("NOW").font(.headline.bold()).padding(.horizontal, 8).background(.blue, in: Capsule())
                Text("\(src) → \(dst) · \(h.itemId)").font(.title3).foregroundStyle(.secondary)
                Spacer()
                Text(String(format: "priority %.2f", engine.livePriority(h))).font(.headline.monospacedDigit()).gloss("priority")
                if engine.livePriority(h) >= 1.0 { Text("⚑").font(.title2).foregroundStyle(.red).gloss("priority") }
            }
            Text(item?.displayLine ?? "").font(.title2).lineLimit(2).gloss("ESI")
            Text("\(t.historyLabel): \(item?.historyLine ?? "none")").font(.title3).foregroundStyle(.yellow).lineLimit(1).gloss("PMH")
            Text("\(t.capacityLabel): \(h.capacityLine)").font(.headline).foregroundStyle(.cyan).lineLimit(1).gloss("census")
            if !reasons.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("WHY QUEUED").font(.caption.bold()).foregroundStyle(.secondary)
                    ForEach(Array(stride(from: 0, to: reasons.count, by: 3)), id: \.self) { i in
                        HStack(spacing: 6) { ForEach(reasons[i..<min(i + 3, reasons.count)], id: \.self) { Chip(r: $0) } }
                    }
                }
            }
            if !rel.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("RELIABILITY (key fields)").font(.caption.bold()).foregroundStyle(.secondary).gloss("reliability score")
                    HStack(spacing: 6) {
                        ForEach(rel.filter(\.key).prefix(6)) { r in RelChip(r: r) }
                    }
                    if let w = rel.compactMap({ f in f.ifWrong.map { (f, $0) } }).max(by: { $0.1.riskHi < $1.1.riskHi }) {
                        Text("IF WRONG · \(w.0.field): “\(w.0.stated)” → \(w.1.alternative): risk +\(Int(w.1.riskLo * 100))–\(Int(w.1.riskHi * 100))% · worst: \(w.1.worstMiss) · plan: \(w.1.planChange)")
                            .font(.headline).foregroundStyle(.pink).lineLimit(2).gloss("if wrong")
                    }
                    if let a = engine.lastAnswer[h.itemId] { Text("last answer · \(a)").font(.headline).foregroundStyle(.mint) }
                }
            }
            HStack(alignment: .firstTextBaseline) {
                Text(h.link.question).font(.title)
                Text(h.proposal).font(.extraLargeTitle2.bold())
                Text("\(Int(h.confidence * 100))%").font(.title2.monospacedDigit()).foregroundStyle(h.confidence < 0.7 ? .orange : .secondary).gloss("confidence")
                Spacer()
            }
            VStack(alignment: .leading, spacing: 3) {
                Text("WHAT HAPPENS NEXT").font(.caption.bold()).foregroundStyle(.secondary).gloss("what happens next")
                Text("Pass → \(h.preview)").font(.title3).foregroundStyle(.green)
                if let alt = h.altPreview { Text("Flip → \(alt)").font(.title3).foregroundStyle(.orange) }
                else if h.link.answerType == .category { Text("Change… → pick another \(h.link.shortLabel ?? "option") (preview on hover)").font(.headline).foregroundStyle(.blue) }
            }
            HStack(spacing: 14) {
                Button(h.trigger != nil ? "Acknowledge ✓" : (h.link.id == engine.config.review.escalationLink ? "Sign off ✓" : "Pass ✓")) { engine.pass(h.id) }.tint(.green)
                if h.link.answerType == .binary { Button("Flip") { engine.flip(h.id) }.tint(.orange) }
                else if h.trigger == nil { Button("Modify…") { engine.openRing(h.id) }.tint(.blue) }
                if h.trigger == nil && h.link.id == engine.config.review.escalationLink {
                    Button("Escalate") { engine.escalate(h.id) }.tint(.red)
                }
                Spacer()
                if !rel.isEmpty {
                    Button("Reliability") { engine.sideTab = "reliability"; if !engine.detailOpen { engine.toggleDetail() } }.tint(.purple)
                    Button("Ask next") { engine.sideTab = "ask"; if !engine.detailOpen { engine.toggleDetail() } }.tint(.teal)
                }
                Button(engine.detailOpen ? "ⓘ Hide" : "ⓘ Details") { engine.sideTab = "details"; engine.toggleDetail() }.tint(.gray)
            }.font(.title2.bold())
        }
        .frame(width: 880).padding(22).glassBackgroundEffect()
    }
}

func relColor(_ s: ReliabilityState) -> Color {
    switch s { case .reliable: .green; case .notSaid: .gray; case .saidWrong: .orange; case .saidDifferently: .purple }
}
struct RelChip: View {
    let r: FieldReliability
    var body: some View {
        Text("\(r.field) \(r.state.short) \(Int(r.score * 100))%").font(.callout.bold()).padding(.horizontal, 8).padding(.vertical, 3)
            .background(relColor(r.state).opacity(0.55), in: Capsule()).gloss(r.state.rawValue)
    }
}

/// Per-field reliability with 4-state re-rating and if-wrong risk.
struct ReliabilityPanel: View {
    @Environment(RouterEngine.self) private var engine
    let h: Handoff
    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack { Text("Reliability · \(h.itemId)").font(.title2.bold()).gloss("reliability score"); Spacer()
                     Text("R N W D = re-rate").font(.caption).foregroundStyle(.secondary).gloss("re-rate") }
            ForEach(engine.reliability(h)) { r in
                VStack(alignment: .leading, spacing: 2) {
                    HStack {
                        Text(r.field + (r.key ? " ★" : "")).font(.headline).frame(width: 110, alignment: .leading)
                        Text("“\(r.stated)”").font(.callout).lineLimit(1).frame(width: 130, alignment: .leading)
                        Text("\(Int(r.score * 100))%").font(.callout.monospacedDigit()).frame(width: 44)
                        ForEach(ReliabilityState.allCases, id: \.self) { st in
                            Button(st.short) { engine.rerate(h.id, field: r.field, to: st) }
                                .font(.caption.bold()).tint(r.state == st ? relColor(st) : .gray.opacity(0.4)).gloss(st.rawValue)
                        }
                    }
                    Text(r.state.rawValue + " · " + r.why.prefix(3).joined(separator: " · ")).font(.caption).foregroundStyle(relColor(r.state))
                    if !r.notAsked.isEmpty { Text("☐ not asked: " + r.notAsked.joined(separator: "; ")).font(.caption).foregroundStyle(.secondary) }
                    if let w = r.ifWrong {
                        Text("if wrong → \(w.alternative): risk +\(Int(w.riskLo * 100))–\(Int(w.riskHi * 100))% · worst \(w.worstMiss) · \(w.planChange) · ddx \(w.ddxShift)")
                            .font(.caption.bold()).foregroundStyle(.pink).gloss("if wrong")
                    }
                }
            }
        }
    }
}

/// Top-3 value-of-information questions; send one.
struct AskNextPanel: View {
    @Environment(RouterEngine.self) private var engine
    let h: Handoff
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Ask next · \(h.itemId)").font(.title2.bold()).gloss("ask next")
            let qs = engine.askNextList(h)
            if qs.isEmpty { Text("no high-value questions left").foregroundStyle(.secondary) }
            ForEach(qs) { q in
                VStack(alignment: .leading, spacing: 3) {
                    HStack {
                        Text(String(format: "VOI %.2f", q.voi)).font(.headline.monospacedDigit()).foregroundStyle(.teal).gloss("VOI")
                        Text(q.field).font(.headline)
                        Spacer()
                        Button("Send") { engine.ask(h.id, q) }.tint(.teal)
                    }
                    Text(q.text).font(.callout)
                    Text(q.rationale).font(.caption).foregroundStyle(.secondary)
                }
            }
            ForEach(Array((engine.itemAsks[h.itemId] ?? []).enumerated()), id: \.offset) { _, a in
                Text("✉ \(a.field) → \(a.answer)").font(.callout).foregroundStyle(.mint)
            }
            if engine.reasons(h).contains(where: { $0.key == "recommend escalation" }) {
                Text("Critical miss not excluded and info unreliable → recommend Escalate").font(.headline).foregroundStyle(.red).gloss("recommend escalation")
            }
        }
    }
}

struct UpNextStrip: View {
    @Environment(RouterEngine.self) private var engine
    var body: some View {
        TimelineView(.periodic(from: .now, by: 1)) { _ in
            let q = engine.queue
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Text("Up next").font(.title2.bold())
                    Spacer()
                    Text("\(q.count) queued").font(.headline.monospacedDigit()).gloss("priority")
                }
                HStack(spacing: 10) {
                    Text("auto-passed \(engine.autoPassed)").gloss("auto-pass")
                    Button("spot-check \(engine.pendingSpotChecks.count)") { engine.spotCheckOpen.toggle(); if engine.detailOpen { engine.toggleDetail() } }
                        .gloss("spot-check")
                }.font(.callout)
                ForEach(q.prefix(engine.config.review.upNextCount)) { h in
                    Button { engine.makeNow(h.id) } label: {
                        VStack(alignment: .leading, spacing: 3) {
                            HStack {
                                if h.trigger != nil { Text("⚠").foregroundStyle(.red).font(.headline) }
                                Text("\(h.itemId) · \(h.link.shortLabel ?? h.link.id)").font(.headline)
                                Spacer()
                                Text("\(h.proposal) \(Int(h.confidence * 100))%").font(.headline.monospacedDigit())
                                Text(String(format: "%.2f", engine.livePriority(h))).font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                            }
                            if let r = engine.reasons(h).max(by: { $0.severity.rawValue < $1.severity.rawValue }) { Chip(r: r) }
                        }.frame(maxWidth: .infinity, alignment: .leading)
                    }.buttonStyle(.bordered)
                }
                if q.count > engine.config.review.upNextCount { Text("+\(q.count - engine.config.review.upNextCount) more").font(.callout).foregroundStyle(.secondary) }
            }
            .frame(width: 470).padding(16).glassBackgroundEffect()
        }
    }
}

/// Beside the Now card: detail sections, or the spot-check queue.
struct SidePanel: View {
    @Environment(RouterEngine.self) private var engine
    var body: some View {
        TimelineView(.periodic(from: .now, by: 1)) { _ in
            Group {
                if engine.spotCheckOpen { spot }
                else if let h = engine.nowHandoff {
                    if engine.sideTab == "reliability" && !engine.reliability(h).isEmpty { ReliabilityPanel(h: h) }
                    else if engine.sideTab == "ask" && !engine.reliability(h).isEmpty { AskNextPanel(h: h) }
                    else { detail(h) }
                } else { Text("—") }
            }.frame(width: 540).padding(16).glassBackgroundEffect()
        }
    }
    func detail(_ h: Handoff) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Details · \(h.itemId)").font(.title2.bold())
            ForEach(engine.detailSections(h)) { s in
                let open = engine.openSections[s.title] != nil
                Button { engine.toggleSection(s.title) } label: {
                    HStack { Text(open ? "▾" : "▸"); Text(s.title).font(.title3.bold()); Spacer(); Text("\(s.rows.count)").foregroundStyle(.secondary) }
                }.buttonStyle(.plain).gloss(s.title)
                if open {
                    ForEach(Array(s.rows.enumerated()), id: \.offset) { _, r in
                        HStack(alignment: .top) {
                            Text(r.0).font(.callout.bold()).frame(width: 170, alignment: .leading).gloss(r.0)
                            Text(r.1).font(.callout).foregroundStyle(.secondary)
                        }
                    }.padding(.leading, 18)
                }
            }
            Text("sections opened + dwell are logged with the decision").font(.caption2).foregroundStyle(.secondary)
        }
    }
    var spot: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack { Text("Spot-check queue").font(.title2.bold()).gloss("spot-check"); Spacer(); Button("Close") { engine.spotCheckOpen = false } }
            let p = engine.pendingSpotChecks
            if p.isEmpty { Text("nothing sampled yet").foregroundStyle(.secondary) }
            ForEach(p.prefix(6)) { d in
                VStack(alignment: .leading, spacing: 3) {
                    Text("\(d.itemId) · \(d.question) \(d.proposedAnswer) (\(Int(d.proposedConfidence * 100))%) · auto-passed").font(.headline)
                    Text(d.displayLine).font(.caption).lineLimit(1).foregroundStyle(.secondary)
                    Text("→ \(d.downstreamPreview ?? "")").font(.caption).foregroundStyle(.green)
                    HStack { Button("Agree") { engine.reviewSpotCheck(d.id, agree: true) }.tint(.green)
                             Button("Disagree") { engine.reviewSpotCheck(d.id, agree: false) }.tint(.red) }.font(.callout)
                }
            }
            let done = engine.decisions.filter { $0.spotCheckResult != nil }
            Text("reviewed \(done.count) · disagree \(done.filter { $0.spotCheckResult == "disagree" }.count)").font(.callout).foregroundStyle(.secondary)
        }
    }
}

struct OptionRing: View {
    @Environment(RouterEngine.self) private var engine
    @State private var newName = ""
    @State private var adding = false
    var body: some View {
        let h = engine.handoffs.first { $0.id == engine.ringFor }
        let opts = h.map { engine.registry.mainOptions($0.link) } ?? []
        let trials = h.map { engine.registry.trialOptions($0.link) } ?? []
        VStack(spacing: 10) {
            ZStack {
                Circle().stroke(.white.opacity(0.4), lineWidth: 2).frame(width: 280, height: 280)
                Text(h?.link.question ?? "").font(.headline)
                ForEach(Array(opts.enumerated()), id: \.offset) { i, o in
                    let ang = Double(i) / Double(max(opts.count, 1)) * 2 * .pi - .pi / 2
                    Button(o) { if let h { engine.select(h.id, o) } }
                        .help(h.flatMap { hh in engine.items[hh.itemId].map { Review.preview(engine.domain, $0, hh.link, o, trial: false) } } ?? o)
                        .font(.headline).tint(o == h?.proposal ? .gray : .blue)
                        .offset(x: 140 * cos(ang), y: 140 * sin(ang))
                }
            }.frame(width: 440, height: 360)
            if !trials.isEmpty {
                HStack {
                    Text("trial:").font(.callout).foregroundStyle(.purple)
                    ForEach(trials, id: \.self) { t in Button(t) { if let h { engine.select(h.id, t) } }.tint(.purple).font(.callout) }
                }
            }
            if adding {
                HStack {
                    TextField("new category", text: $newName).textFieldStyle(.roundedBorder).frame(width: 220)
                    Button("Add") { if let h, !newName.isEmpty { engine.selectNew(h.id, newName); newName = ""; adding = false } }
                }
                Text("trial categories are logged but never change routing or fire alerts until promoted").font(.caption2).foregroundStyle(.secondary)
            } else {
                Button("New…") { adding = true }.tint(.purple).font(.headline)
            }
        }.padding(12).glassBackgroundEffect()
    }
}

struct BoardView: View {
    @Environment(RouterEngine.self) private var engine
    @Environment(\.openWindow) private var openWindow
    @Environment(\.dismissImmersiveSpace) private var dismissImmersiveSpace
    var body: some View {
        TimelineView(.periodic(from: .now, by: 1)) { _ in
            let cfg = engine.config, s = engine.stats
            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Text(cfg.terminology.boardTitle).font(.title.bold())
                    if cfg.synthetic { Text(cfg.terminology.syntheticBanner).font(.callout.bold()).foregroundStyle(.yellow) }
                    Spacer()
                    Text("site \(engine.siteId) · agent error \(Int(s.agentErrorRate * 100))%").font(.callout).foregroundStyle(.secondary)
                }
                HStack(spacing: 14) {
                    stat(cfg.terminology.completedLabel, "\(s.completed)"); stat("Decisions", "\(s.decisions)")
                    stat("Alerts", "\(s.alertsFired)"); stat("Corrections", "\(s.corrections)")
                    stat("Prevented", "\(s.errorsPrevented)"); stat("Misses", "\(s.misses)")
                    stat("Median dec.", String(format: "%.1fs", s.medianLatency)); stat("Auto-passed", "\(engine.autoPassed)")
                }
                HStack(spacing: 14) { ForEach(engine.domain.boardMetrics(s)) { m in stat(m.label, m.value) } }
                HStack(spacing: 10) {
                    ForEach(engine.domain.breakdown(), id: \.0) { b in
                        Text("\(b.0): \(b.1)").font(.headline).padding(.horizontal, 8).padding(.vertical, 3).background(.white.opacity(0.12), in: Capsule())
                    }
                }
                Divider()
                ForEach(engine.recentRows) { r in
                    HStack(spacing: 6) {
                        Text(r.id).font(.headline.monospaced()).frame(width: 56, alignment: .leading)
                        Text(r.line).font(.callout).lineLimit(1).frame(width: 300, alignment: .leading)
                        HStack(spacing: 3) {
                            ForEach(Array(r.steps.enumerated()), id: \.offset) { _, st in
                                Text(st.0).font(.callout.bold()).padding(.horizontal, 6).padding(.vertical, 1)
                                    .background(st.3 ? Color.purple.opacity(0.6) : (st.1 ? Color.orange : Color.white.opacity(0.15)), in: Capsule())
                                    .foregroundStyle(st.2 ? Color.primary : Color.red)
                            }
                        }.frame(width: 360, alignment: .leading)
                        Text(label(r.status)).font(.callout.bold()).foregroundStyle(color(r.status))
                    }
                }
                CategoriesStrip()
                HStack(spacing: 12) {
                    Text("orange = changed · purple = trial · red = wrong · hover any field for its meaning").font(.caption).foregroundStyle(.secondary)
                    Spacer()
                    if DomainCatalog.all.count > 1 { Button("Next Domain") { engine.nextDomain() } }
                    Button("Export") { engine.export() }
                    @Bindable var e = engine
                    Toggle("Environment", isOn: $e.fullImmersion).frame(width: 170)
                    Button("Close") { Task { openWindow(id: "main"); await dismissImmersiveSpace(); engine.immersiveOpen = false } }
                }.font(.callout)
            }
            .frame(width: 1000).padding(16).glassBackgroundEffect()
        }
    }
    private func stat(_ t: String, _ v: String) -> some View {
        VStack(spacing: 0) { Text(v).font(.title2.bold().monospacedDigit()); Text(t).font(.caption) }
    }
    private func label(_ s: String) -> String {
        switch s { case "correct": "✓ correct"; case "corrected": "✓ corrected"; case "missed": "✗ miss"; default: s }
    }
    private func color(_ s: String) -> Color {
        switch s { case "correct": .green; case "corrected": .orange; case "missed": .red; default: .secondary }
    }
}

/// Categories panel: main / trial / dormant per category link, with scores.
struct CategoriesStrip: View {
    @Environment(RouterEngine.self) private var engine
    var body: some View {
        let reg = engine.registry
        VStack(alignment: .leading, spacing: 3) {
            HStack {
                Text("Categories · site \(reg.siteId) · registry v\(reg.version)").font(.callout.bold())
                if let ev = reg.history.last(where: { $0.op != "seed" }) {
                    Text("last: \(ev.op) “\(ev.category)” \(ev.detail)").font(.caption).foregroundStyle(.purple).lineLimit(1)
                }
            }
            ForEach(engine.config.links.filter { $0.answerType == .category }, id: \.id) { l in
                HStack(spacing: 6) {
                    Text(l.shortLabel ?? l.id).font(.caption.bold()).frame(width: 44, alignment: .leading)
                    ForEach(reg.list(l, .main).filter { !$0.isBase }, id: \.name) { e in chip("★ \(e.name)", .green) }
                    ForEach(reg.list(l, .trial), id: \.name) { e in
                        chip(String(format: "%@ · %du %.0f%% %d✓", e.name, e.uses, e.consistency * 100, e.outcomeSupport), .purple)
                    }
                    ForEach(reg.list(l, .dormant), id: \.name) { e in chip("⌀ \(e.name)", .gray) }
                    if reg.list(l, .trial).isEmpty && reg.list(l, .dormant).isEmpty && reg.list(l, .main).allSatisfy(\.isBase) {
                        Text("base set only").font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
        }
    }
    private func chip(_ t: String, _ c: Color) -> some View {
        Text(t).font(.caption.bold()).padding(.horizontal, 6).padding(.vertical, 1).background(c.opacity(0.45), in: Capsule())
    }
}

struct LauncherView: View {
    @Environment(RouterEngine.self) private var engine
    @Environment(\.openImmersiveSpace) private var openImmersiveSpace
    @Environment(\.dismissWindow) private var dismissWindow
    var body: some View {
        VStack(spacing: 14) {
            Text(engine.config.title).font(.extraLargeTitle2)
            Text(engine.config.agents.filter { $0.tier == 0 }.map(\.name).joined(separator: " · "))
            if engine.config.synthetic { Text(engine.config.terminology.syntheticBanner).foregroundStyle(.yellow) }
            Button("Enter Crossroads") { Task { await open() } }.font(.title2)
        }
        .padding(40)
        .task { if ProcessInfo.processInfo.arguments.contains("-autoOpenImmersive") { await open() } }
    }
    private func open() async {
        if case .opened = await openImmersiveSpace(id: "Router") { engine.immersiveOpen = true; dismissWindow(id: "main") }
    }
}
