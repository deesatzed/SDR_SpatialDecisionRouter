import SwiftUI

/// M5 Lineage tab — editorial palette (paper / ink, serif display, mono data) consistent with the manifesto.
struct LineageView: View {
    @Environment(RouterEngine.self) private var engine
    @Environment(\.dismiss) private var dismiss
    @State private var area = "symbiosis:personal_finance"
    @State private var selected: String?
    @State private var exported: String?
    private let paper = ManifestoView.paper, ink = ManifestoView.ink
    var body: some View {
        let recs = engine.ledger.read()
        let _ = engine.promoLog.count + engine.dialLog.count + engine.decisions.count   // refresh on new signed lines
        let l = LineageBuilder.build(area: area, recs: recs)
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                HStack {
                    Text("SYMBIOSIS · LINEAGE").font(.system(.caption, design: .monospaced).bold()).tracking(2)
                    Spacer()
                    Button("Export markdown") { exported = export(l) }.accessibilityIdentifier("exportLineage")
                    Button("Close") { engine.showLineage = false; dismiss() }.accessibilityIdentifier("closeLineage")
                }
                Text(area.replacingOccurrences(of: "symbiosis:", with: "").replacingOccurrences(of: "_", with: " ").capitalized)
                    .font(.system(size: 40, weight: .semibold, design: .serif))
                HStack(spacing: 8) {
                    ForEach(LineageBuilder.areas(recs), id: \.self) { a in
                        Button(a.replacingOccurrences(of: "symbiosis:", with: "")) { area = a; selected = nil }
                            .tint(a == area ? .orange : .gray).accessibilityIdentifier("area_\(a)")
                    }
                }
                Text((l.chainOK ? "✓ chain verified" : "✗ \(l.chainProblem ?? "chain broken")") + " · \(l.ledgerLines) signed lines · reconstructed from the ledger only")
                    .font(.system(.callout, design: .monospaced)).foregroundStyle(l.chainOK ? Color.green.opacity(0.8) : .red)
                    .accessibilityIdentifier("chainStatus")
                if let e = exported { Text(e).font(.system(.caption, design: .monospaced)).accessibilityIdentifier("exportedPath")
                    #if !os(visionOS)
                    ShareLink(item: LineageBuilder.markdown(l)) { Text("Share markdown") }
                    #endif
                }
                summary(l)
                Text("Timeline").font(.system(size: 26, weight: .semibold, design: .serif))
                if l.events.isEmpty { Text("No signed events yet for this area.").foregroundStyle(ink.opacity(0.6)) }
                ForEach(l.events.reversed()) { e in row(e) }
            }
            .padding(28)
        }
        .foregroundStyle(ink).background(paper)
        .buttonStyle(.bordered)
        .accessibilityIdentifier("lineageView")
    }

    @ViewBuilder private func summary(_ l: Lineage) -> some View {
        HStack(alignment: .top, spacing: 16) {
            card("Champion") {
                Text("gen \(l.championGeneration)").font(.system(size: 30, weight: .semibold, design: .serif)).accessibilityIdentifier("lineageChampionGen")
                Text(l.champion.isEmpty ? "seed policy" : l.champion.map(\.text).joined(separator: "\n")).font(.caption)
            }
            card("Dials · gen \(l.dialGeneration)") {
                spark("autonomy", l.dialSeries.map(\.autonomy_horizon), .orange)
                spark("deference", l.dialSeries.map(\.deference), .indigo)
                spark("detail", l.dialSeries.map(\.detail_absorption), .teal)
                spark("challenge", l.dialSeries.map(\.challenge), .pink)
            }
            card("Your sharpness") {
                post(l.sharpSeries.last)
                spark("mean", l.sharpSeries.map { $0.mean * 100 }, .orange)
            }
            card("Overrides held up") {
                post(l.overrideSeries.last)
                spark("mean", l.overrideSeries.map { $0.mean * 100 }, .indigo)
            }
            card("Safety") {
                Text("\(l.criticalMisses) critical misses").font(.headline)
                Text("\(l.demotions) demotions").font(.headline)
                Text("\(l.decisions) decisions · \(l.graded) graded").font(.caption)
            }
        }
    }
    @ViewBuilder private func card<C: View>(_ t: String, @ViewBuilder _ c: () -> C) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(t.uppercased()).font(.system(.caption2, design: .monospaced).bold()).tracking(1).foregroundStyle(ink.opacity(0.6))
            c()
        }
        .padding(12).frame(maxWidth: .infinity, alignment: .topLeading)
        .background(Color.white, in: RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(ink.opacity(0.12)))
    }
    @ViewBuilder private func spark(_ n: String, _ v: [Double], _ c: Color) -> some View {
        HStack(spacing: 6) {
            Text(n).font(.system(.caption2, design: .monospaced)).frame(width: 64, alignment: .leading)
            Sparkline(values: v, color: c).frame(height: 16)
            Text(v.last.map { String(Int($0)) } ?? "–").font(.system(.caption2, design: .monospaced))
        }
    }
    @ViewBuilder private func post(_ p: DialPosterior?) -> some View {
        if let p { Text("\(p.successes)/\(p.n)").font(.system(size: 26, weight: .semibold, design: .serif)); Text("mean \(Int(p.mean * 100))% · 90% [\(Int(p.lo * 100))–\(Int(p.hi * 100))]").font(.caption) }
        else { Text("none yet").font(.headline).foregroundStyle(ink.opacity(0.5)) }
    }
    private func tint(_ k: String) -> Color {
        switch k {
        case "demotion", "critical_miss": .red
        case "promotion": .green
        case "rollback", "revert": .purple
        case "discarded": .gray
        case "spot_check": .orange
        case "evaluation_passed", "principal_decision", "policy_proposal": .indigo
        default: .teal
        }
    }
    @ViewBuilder private func row(_ e: LineageEvent) -> some View {
        let open = selected == e.id
        VStack(alignment: .leading, spacing: 6) {
            Button { selected = open ? nil : e.id } label: {
                HStack(alignment: .firstTextBaseline, spacing: 10) {
                    Circle().fill(tint(e.kind)).frame(width: 10, height: 10)
                    Text("L\(e.line)").font(.system(.caption, design: .monospaced)).foregroundStyle(ink.opacity(0.5))
                    Text(e.title).font(.system(.headline, design: .serif)).multilineTextAlignment(.leading)
                    Spacer()
                    Text("champ g\(e.championGeneration) · dial g\(e.dialGeneration)").font(.system(.caption2, design: .monospaced)).foregroundStyle(ink.opacity(0.5))
                    Text(e.ok ? "✓" : "✗").foregroundStyle(e.ok ? .green : .red)
                }.contentShape(Rectangle())
            }.buttonStyle(.plain).accessibilityIdentifier("lineageEvent_\(e.kind)")
            if open {
                VStack(alignment: .leading, spacing: 4) {
                    Text(e.detail).font(.callout)
                    Text("evidence: " + (e.evidence.isEmpty ? "—" : e.evidence.map { String($0.prefix(8)) }.joined(separator: " "))).font(.system(.caption, design: .monospaced))
                    Text("signature: \(e.ok ? "✓ Ed25519 valid, chain position verified" : "✗ " + e.status) · signer \(e.signer)").font(.system(.caption, design: .monospaced))
                        .foregroundStyle(e.ok ? .green : .red).accessibilityIdentifier("eventSignature")
                    Text("hash \(e.hash.prefix(16))… · prev \(e.prev.prefix(16))… · \(e.timestamp)").font(.system(.caption, design: .monospaced)).foregroundStyle(ink.opacity(0.6))
                }
                .padding(10).background(paper.opacity(0.6), in: RoundedRectangle(cornerRadius: 8))
                .accessibilityElement(children: .contain).accessibilityIdentifier("eventDetail")
            }
        }
        .padding(10).background(Color.white, in: RoundedRectangle(cornerRadius: 10))
        .overlay(alignment: .leading) { Rectangle().fill(tint(e.kind)).frame(width: 3) }
    }
    private func export(_ l: Lineage) -> String {
        let dir = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("lineage", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let u = dir.appendingPathComponent(l.area.replacingOccurrences(of: ":", with: "_") + ".md")
        do { try LineageBuilder.markdown(l).write(to: u, atomically: true, encoding: .utf8); return "exported → Documents/lineage/\(u.lastPathComponent) (\(l.events.count) events)" }
        catch { return "export failed: \(error.localizedDescription)" }
    }
}

struct LineageButton: View {
    @Environment(RouterEngine.self) private var engine
    #if os(visionOS)
    @Environment(\.openWindow) private var openWindow
    #endif
    var body: some View {
        Button("Lineage") {
            #if os(visionOS)
            openWindow(id: "lineage")
            #else
            engine.showLineage = true
            #endif
        }.tint(.brown).accessibilityIdentifier("openLineage")
    }
}
