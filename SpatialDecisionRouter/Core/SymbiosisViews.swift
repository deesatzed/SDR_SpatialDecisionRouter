import SwiftUI

// MARK: - Symbiosis card (layer 2) + dual labels (layer 3) + manifesto. Shared by iPad and visionOS.

let symOrange = Color(red: 0.96, green: 0.55, blue: 0.20)
let symBlue = Color(red: 0.30, green: 0.58, blue: 0.98)

/// Shown inside the Now card when the item carries `symbiosis=1`.
struct SymbiosisPanel: View {
    @Environment(RouterEngine.self) private var engine
    let item: DomainItem
    var body: some View {
        let f = item.fields
        let area = (engine.domain as? SymbiosisDomain)?.area(item)
        let sharp = engine.nowHandoff.map { $0.itemId == item.id && engine.isSharp($0) } ?? false
        VStack(alignment: .leading, spacing: 12) {
            if let r = engine.lastSharp { SpotReveal(rec: r) }
            if let a = area { DialGauge(key: "symbiosis:\(a.id)", fallback: a); CalibrationCard(key: "symbiosis:\(a.id)") }
            HStack(alignment: .top, spacing: 12) {
                column("YOU HOLD", symOrange, id: "humanColumn") {
                    Text(f["human_judgment"] ?? "").font(.title3.bold())
                    Text("Consider: \(f["human_question"] ?? "")").font(.headline).italic()
                }
                column("BRIDGE", .white.opacity(0.85), id: "bridgeColumn") {
                    Text(f["bridge_architecture"] ?? "").font(.headline)
                    Text("Checkpoint · \(f["bridge_checkpoint"] ?? "")").font(.callout.bold()).foregroundStyle(.pink)
                    Text("Accept plan = \(f["plan"] ?? "")").font(.callout)
                    if let alt = f["alternative"], alt != "—" { Text("Alternative = \(alt)").font(.callout) }
                }
                if sharp {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("AI HOLDS").font(.caption.bold()).foregroundStyle(symBlue)
                        Text("Hidden — your call first.").font(.headline).foregroundStyle(.secondary)
                        Text("The AI's pick and the outcome are revealed after you decide.").font(.callout).foregroundStyle(.secondary)
                    }
                    .padding(12).frame(maxWidth: .infinity, alignment: .topLeading)
                    .background(.gray.opacity(0.12), in: RoundedRectangle(cornerRadius: 14))
                    .overlay(RoundedRectangle(cornerRadius: 14).stroke(symBlue.opacity(0.4), style: StrokeStyle(lineWidth: 1.5, dash: [6, 4])))
                    .accessibilityElement(children: .contain).accessibilityIdentifier("aiHidden")
                } else {
                column("AI HOLDS", symBlue, id: "aiColumn") {
                    Text(f["ai_distilled"] ?? "").font(.headline)
                    if engine.aiDepthOpen {
                        ForEach((f["ai_detail"] ?? "").split(separator: "\n").map(String.init), id: \.self) { Text("• \($0)").font(.callout) }
                        Text("Edge cases").font(.caption.bold()).foregroundStyle(.secondary)
                        ForEach((f["ai_edge"] ?? "").split(separator: "\n").map(String.init), id: \.self) { Text("• \($0)").font(.callout) }
                    }
                    Button(engine.aiDepthOpen ? "Hide AI depth" : "Show AI depth") { engine.aiDepthOpen.toggle() }
                        .tint(symBlue).accessibilityIdentifier("aiDepthToggle")
                }
                }
            }
            if !sharp { SplitRatingRow(itemId: item.id) }
        }
    }
    @ViewBuilder private func column<C: View>(_ title: String, _ tint: Color, id: String, @ViewBuilder _ c: () -> C) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title).font(.caption.bold()).foregroundStyle(tint)
            c()
        }
        .padding(12).frame(maxWidth: .infinity, alignment: .topLeading)
        .background(tint.opacity(0.14), in: RoundedRectangle(cornerRadius: 14))
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(tint.opacity(0.6), lineWidth: 1.5))
        .accessibilityElement(children: .contain).accessibilityIdentifier(id)
    }
}

struct DialGauge: View {
    @Environment(RouterEngine.self) private var engine
    let key: String
    let fallback: SymbiosisContext
    var body: some View {
        let ctx = engine.dials(key) ?? fallback
        let hist = engine.dialHistory(key)
        let last = engine.dialLog.last { $0.domain == key }
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 14) {
                Text(ctx.title).font(.headline.bold())
                dial("Defer", ctx.dials.deference, floor: ctx.caps.deferenceMin > 0 ? ctx.caps.deferenceMin : nil, cap: nil)
                dial("Detail", ctx.dials.detail_absorption, floor: nil, cap: nil)
                dial("Challenge", ctx.dials.challenge, floor: nil, cap: nil)
                dial("Autonomy", ctx.dials.autonomy_horizon, floor: nil, cap: ctx.caps.autonomyMax < 100 ? ctx.caps.autonomyMax : nil)
                VStack(alignment: .leading, spacing: 2) {
                    Sparkline(values: hist.map(\.autonomy_horizon), color: .mint).frame(width: 110, height: 26)
                    Sparkline(values: hist.map(\.deference), color: .teal).frame(width: 110, height: 26)
                    Text("autonomy · deference history").font(.caption2).foregroundStyle(.secondary)
                }.accessibilityIdentifier("dialSparkline")
                Text("gen \(ctx.generation)").font(.caption.monospaced())
            }
            if let last, let why = last.reason {
                HStack {
                    Text((last.escalation_flags?.contains("demotion") == true ? "⚠ " : "↗ ") + "Why it moved: " + why
                         + (last.posterior.map { " · n=\($0.n), mean \($0.mean) [\($0.lo)–\($0.hi)]" } ?? ""))
                        .font(.callout.bold()).foregroundStyle(last.escalation_flags?.contains("demotion") == true ? .red : .mint)
                        .lineLimit(3).accessibilityIdentifier("dialWhy")
                    Button("Undo move") { engine.undoLastDialMove(key) }.tint(.gray).accessibilityIdentifier("undoDial")
                }
            } else {
                Text("No dial moves yet · needs \(DialPolicy.standard.minN) outcome-graded calls (thresholds are design placeholders)")
                    .font(.caption).foregroundStyle(.yellow)
            }
        }
    }
    private func dial(_ n: String, _ v: Double, floor: Double?, cap: Double?) -> some View {
        VStack(spacing: 2) {
            Gauge(value: v, in: 0...100) { EmptyView() } currentValueLabel: { Text("\(Int(v))").font(.caption.monospacedDigit()) }
                .gaugeStyle(.accessoryCircularCapacity).tint(n == "Autonomy" ? .mint : .teal).scaleEffect(0.8)
            Text(n + (cap.map { " ≤\(Int($0))" } ?? "") + (floor.map { " ≥\(Int($0))" } ?? "")).font(.caption2)
        }.accessibilityElement(children: .combine).accessibilityLabel("\(n) \(Int(v))").accessibilityIdentifier("dial_\(n)")
    }
}

struct Sparkline: View {
    let values: [Double]
    let color: Color
    var body: some View {
        GeometryReader { g in
            let v = values.isEmpty ? [0] : values
            let lo = (v.min() ?? 0) - 1, hi = (v.max() ?? 100) + 1
            Path { p in
                for (i, x) in v.enumerated() {
                    let pt = CGPoint(x: v.count == 1 ? 0 : g.size.width * CGFloat(i) / CGFloat(v.count - 1),
                                     y: g.size.height * (1 - CGFloat((x - lo) / (hi - lo))))
                    i == 0 ? p.move(to: pt) : p.addLine(to: pt)
                }
            }.stroke(color, lineWidth: 2)
        }
    }
}

struct SplitRatingRow: View {
    @Environment(RouterEngine.self) private var engine
    let itemId: String
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("RATE THE SPLIT (one tap · second label, never moves dials alone)").font(.caption.bold()).foregroundStyle(.secondary).gloss("split rating")
            ActionRow {
                ForEach(SplitRating.allCases, id: \.self) { r in
                    let on = engine.splitGiven[itemId] == r
                    Button(r.title) { engine.rateSplit(itemId: itemId, r) }
                        .tint(on ? symOrange : .gray.opacity(0.5)).accessibilityIdentifier("split_\(r.rawValue)")
                }
            }.font(.headline)
        }
    }
}

// MARK: - Manifesto (our words; structure of four audience lenses adapted from the Symbiont concept)

struct Lens: Identifiable { let id: String; let name: String; let thesis: String; let human: String; let ai: String; let learning: String; let quote: String }

enum Manifesto {
    static let lenses: [Lens] = [
        Lens(id: "philosophical", name: "Philosophical",
             thesis: "Stop being the library; become a better judge. Let the machine be the library and stop pretending to be the judge.",
             human: "Keep the why and the ought: values, stakes, and the lessons experience teaches that no database stores.",
             ai: "Carry the how and the exhaustive what: facts, syntax, edge cases, recall at any scale.",
             learning: "Each override is a piece of unwritten experience made visible — and later checked against what actually happened.",
             quote: "Wisdom is what experience teaches that no knowledge base can hold."),
        Lens(id: "technical", name: "Technical",
             thesis: "A per-context division of labour, expressed as four dials, learned only from outcome-graded decisions.",
             human: "Label each decision (pass / flip / modify / escalate) and the split itself (one tap).",
             ai: "Propose, explain depth on demand, and log every decision into a signed, hash-chained record.",
             learning: "Candidates are promoted only if they beat the champion on a frozen replay with known outcomes and a human signs.",
             quote: "No promotion without a frozen evaluator and a signature."),
        Lens(id: "teaching", name: "Teaching",
             thesis: "Learn the map, not every street: keep enough to steer and to catch the AI when it is wrong.",
             human: "Practise judgment; take occasional sharpness checks where the AI's answer is hidden first.",
             ai: "Hold the details so the learner's attention goes to the decisions that matter.",
             learning: "If the human stops catching errors, the AI hands detail back until they can again.",
             quote: "Functional knowledge is what you need to steer and to check — not to recite."),
        Lens(id: "executive", name: "Executive",
             thesis: "Faster decisions with an audit trail: people own judgment, AI owns depth, and autonomy is earned, never assumed.",
             human: "Own the call in high-stakes areas; clinical contexts keep hard caps.",
             ai: "Do the exhaustive work; step back automatically after a serious miss.",
             learning: "Every decision becomes clean, signed training data with a visible history of how the partnership changed.",
             quote: "Autonomy is a balance you earn, not a setting you flip."),
    ]
}

struct ManifestoView: View {
    @State private var lens = "philosophical"
    @Environment(\.dismiss) private var dismiss
    static let paper = Color(red: 0xFB / 255, green: 0xF9 / 255, blue: 0xF5 / 255)
    static let ink = Color(red: 0x1C / 255, green: 0x19 / 255, blue: 0x17 / 255)
    var body: some View {
        let l = Manifesto.lenses.first { $0.id == lens }!
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                HStack {
                    Text("SYMBIOSIS · MANIFESTO").font(.system(.caption, design: .monospaced).bold()).tracking(2)
                    Spacer()
                    Button("Close") { dismiss() }.accessibilityIdentifier("closeManifesto")
                }
                Text("Human judgment × AI depth").font(.system(size: 44, weight: .semibold, design: .serif))
                HStack(spacing: 8) {
                    ForEach(Manifesto.lenses) { x in
                        Button(x.name) { lens = x.id }
                            .buttonStyle(.bordered).tint(x.id == lens ? Color.orange : ManifestoView.ink)
                            .accessibilityIdentifier("lens_\(x.id)")
                    }
                }
                Text(l.thesis).font(.system(size: 26, design: .serif))
                HStack(alignment: .top, spacing: 16) {
                    block("THE HUMAN", l.human, symOrange)
                    block("THE AI", l.ai, symBlue)
                }
                block("HOW BOTH LEARN", l.learning, ManifestoView.ink)
                Text("“\(l.quote)”").font(.system(size: 24, design: .serif).italic()).padding(.top, 6)
                Text("Copy in our own words; four-lens structure inspired by the Symbiont concept (see docs/SYMBIOSIS.md).")
                    .font(.system(.caption, design: .monospaced)).foregroundStyle(ManifestoView.ink.opacity(0.6))
            }
            .padding(36).frame(maxWidth: 900, alignment: .leading)
        }
        .foregroundStyle(ManifestoView.ink)
        .background(ManifestoView.paper)
        .environment(\.colorScheme, .light)
        .accessibilityIdentifier("manifesto")
    }
    private func block(_ t: String, _ s: String, _ c: Color) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(t).font(.system(.caption, design: .monospaced).bold()).foregroundStyle(c)
            Text(s).font(.system(.title3, design: .default))
        }.padding(14).frame(maxWidth: .infinity, alignment: .leading)
        .overlay(Rectangle().frame(width: 3).foregroundStyle(c), alignment: .leading)
    }
}

struct ManifestoButton: View {
    @Environment(RouterEngine.self) private var engine
    #if os(visionOS)
    @Environment(\.openWindow) private var openWindow
    #endif
    var body: some View {
        Button("Manifesto") {
            #if os(visionOS)
            openWindow(id: "manifesto")
            #else
            engine.showManifesto = true
            #endif
        }.tint(.orange).accessibilityIdentifier("openManifesto")
    }
}

/// M3 · "Your call first": the AI's pick, confidence and reasons are hidden; the human picks, then the reveal shows.
struct YourCallFirst: View {
    @Environment(RouterEngine.self) private var engine
    let h: Handoff
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("YOUR CALL FIRST").font(.headline.bold()).padding(.horizontal, 10).padding(.vertical, 3)
                    .background(symOrange, in: Capsule()).foregroundStyle(.black)
                Text("sharpness spot-check · \(engine.sharpWhy[h.id] ?? "")").font(.callout).foregroundStyle(.secondary)
            }
            Text(h.link.question).font(.title)
            ActionRow {
                ForEach(h.link.options, id: \.self) { o in
                    Button(o) { engine.sharpCall(h.id, o) }.tint(symOrange).accessibilityIdentifier("call_\(o)")
                }
            }.font(.title2.bold())
            Text("Keeps your judgment sharp while the AI absorbs detail. Hard-trigger cards are never spot-checked.")
                .font(.caption).foregroundStyle(.secondary)
        }
        .padding(14).background(symOrange.opacity(0.10), in: RoundedRectangle(cornerRadius: 14))
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(symOrange.opacity(0.7), lineWidth: 2))
        .accessibilityElement(children: .contain).accessibilityIdentifier("yourCallFirst")
    }
}

/// reveal of the last spot-check: your call vs the AI's pick vs the outcome
struct SpotReveal: View {
    let rec: UnifiedDecisionRecord
    var body: some View {
        if let s = rec.spot_check {
            HStack(spacing: 14) {
                Text("REVEAL").font(.caption.bold()).foregroundStyle(.secondary)
                Text("You: \(s.human_call)").font(.headline).foregroundStyle(symOrange)
                Text("AI: \(s.agent_pick)").font(.headline).foregroundStyle(symBlue)
                Text("Outcome: \(s.outcome ?? "pending")").font(.headline)
                if let c = s.human_correct { Text(c ? "✓ you held up" : "✗ missed").font(.headline.bold()).foregroundStyle(c ? .green : .pink) }
                Spacer()
            }
            .padding(10).background(.white.opacity(0.06), in: RoundedRectangle(cornerRadius: 10))
            .accessibilityElement(children: .combine).accessibilityIdentifier("spotReveal")
        }
    }
}

/// per-area calibration: human spot-check accuracy vs outcome, and whether overrides held up
struct CalibrationCard: View {
    @Environment(RouterEngine.self) private var engine
    let key: String
    var body: some View {
        let _ = engine.decisions.count + (engine.lastSharp == nil ? 0 : 1)   // re-render on new decisions/spot-checks
        let sh = engine.sharpness(key), ov = engine.overrideRate(key)
        HStack(spacing: 18) {
            Text("CALIBRATION").font(.caption.bold()).foregroundStyle(.secondary)
            stat("Your sharpness", sh, empty: "no spot-checks yet")
            stat("Overrides held up", ov, empty: "no graded overrides")
            Text("checks: detail ≥ \(Int(engine.sharpDetailMin)) · \(engine.sharpEvery.map { "every \($0)" } ?? "rate \(Int(engine.sharpRate * 100))%")")
                .font(.caption).foregroundStyle(.secondary)
            Spacer()
        }
        .padding(8).background(.white.opacity(0.05), in: RoundedRectangle(cornerRadius: 10))
        .accessibilityElement(children: .combine).accessibilityIdentifier("calibrationCard")
    }
    @ViewBuilder private func stat(_ t: String, _ p: DialPosterior?, empty: String) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(t).font(.caption.bold())
            if let p {
                Text("\(p.successes)/\(p.n) · \(Int(p.mean * 100))% [\(Int(p.lo * 100))–\(Int(p.hi * 100))]").font(.headline.monospacedDigit())
                    .foregroundStyle(p.hi <= 0.5 ? .pink : (p.lo >= 0.5 ? .green : .primary))
            } else { Text(empty).font(.callout).foregroundStyle(.secondary) }
        }
    }
}
