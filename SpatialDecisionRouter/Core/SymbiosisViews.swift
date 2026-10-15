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
        VStack(alignment: .leading, spacing: 12) {
            if let a = area { DialGauge(key: "symbiosis:\(a.id)", fallback: a) }
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
            SplitRatingRow(itemId: item.id)
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
