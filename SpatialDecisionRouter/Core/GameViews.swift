import SwiftUI
#if os(iOS)
import AudioToolbox
import UIKit
#endif

/// Game-mode strip above the Now card: score · streak · combo · goals · live countdown + mode toggle.
struct GameHUDStrip: View {
    @Environment(RouterEngine.self) private var engine
    var body: some View {
        TimelineView(.periodic(from: .now, by: 1)) { _ in
            HStack(spacing: 14) {
                Toggle(isOn: Binding(get: { engine.gameMode }, set: { engine.gameMode = $0 })) {
                    Text(engine.gameMode ? "Game" : "Focus").font(.headline)
                }.toggleStyle(.switch).fixedSize().accessibilityIdentifier("gameToggle")
                if engine.gameMode, let h = engine.domain.gameHUD() {
                    stat("\(h.score)", "score")
                    stat("\(h.streak)🔥", "streak")
                    stat("×\(h.combo)", "combo")
                    stat("\(h.hits)/\(h.graded)", "graded hits")
                    ForEach(h.goals) { g in
                        Text("\(g.done ? "✓" : "○") \(g.title) \(min(g.progress, g.target))/\(g.target)")
                            .font(.caption.bold()).padding(.horizontal, 8).padding(.vertical, 3)
                            .background((g.done ? Color.green : Color.gray).opacity(0.35), in: Capsule())
                    }
                    Spacer(minLength: 0)
                    if let c = h.countdown { Text("⏱ \(c)").font(.headline.monospacedDigit()).foregroundStyle(.orange) }
                } else { Spacer(minLength: 0) }
            }
            .padding(.horizontal, 16).padding(.vertical, 8).sdrWidth(880).sdrPanel()
        }
    }
    private func stat(_ v: String, _ l: String) -> some View {
        VStack(spacing: 0) { Text(v).font(.title3.bold().monospacedDigit()); Text(l).font(.caption2).foregroundStyle(.secondary) }
    }
}

/// "Predict then reveal": the real outcome (WERIAM teacher) after your label.
struct RevealBanner: View {
    @Environment(RouterEngine.self) private var engine
    @State private var shown: Reveal?
    var body: some View {
        Group {
            if engine.gameMode, let r = shown {
                HStack(spacing: 14) {
                    Text(r.hit == true ? "✓" : r.hit == false ? "✗" : "⏱").font(.system(size: 44, weight: .heavy))
                    VStack(alignment: .leading, spacing: 4) {
                        Text(r.title).font(.title2.bold())
                        Text(r.detail).font(.headline).foregroundStyle(.white.opacity(0.85)).lineLimit(2)
                    }
                    Spacer(minLength: 0)
                }
                .padding(16).sdrWidth(880)
                .background((r.hit == true ? Color.green : r.hit == false ? Color.red : Color.gray).opacity(0.75), in: RoundedRectangle(cornerRadius: 18))
                .transition(.scale(scale: 0.6).combined(with: .opacity))
                .accessibilityIdentifier("revealBanner")
            }
        }
        .animation(.spring(response: 0.35, dampingFraction: 0.6), value: shown)
        .onChange(of: engine.reveal) { _, r in
            guard let r else { return }
            shown = r; feedback(r.hit)
            Task { try? await Task.sleep(for: .seconds(4)); if shown?.id == r.id { shown = nil } }
        }
    }
    private func feedback(_ hit: Bool?) {
        guard engine.gameMode else { return }
        #if os(iOS)
        UINotificationFeedbackGenerator().notificationOccurred(hit == true ? .success : hit == false ? .error : .warning)
        AudioServicesPlaySystemSound(hit == true ? 1057 : 1053)
        #endif
    }
}

/// Goals, earned-autonomy bars, personal calibration curve, end-of-session recap.
struct GameInsights: View {
    @Environment(RouterEngine.self) private var engine
    var body: some View {
        TimelineView(.periodic(from: .now, by: 1)) { _ in
            if engine.gameMode, let h = engine.domain.gameHUD() {
                VStack(alignment: .leading, spacing: 12) {
                    if let rc = h.recap {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Session recap").font(.title2.bold())
                            ForEach(rc, id: \.self) { Text("• \($0)").font(.headline) }
                        }.padding(14).frame(maxWidth: .infinity, alignment: .leading)
                            .background(Color.purple.opacity(0.35), in: RoundedRectangle(cornerRadius: 14)).accessibilityIdentifier("recapCard")
                    }
                    HStack(alignment: .top, spacing: 16) {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Agent earned-autonomy (per world)").font(.headline)
                            if h.levels.isEmpty { Text("Fills in as your labels are graded").font(.caption).foregroundStyle(.secondary) }
                            ForEach(h.levels) { l in
                                HStack {
                                    Text(l.scope).font(.caption).lineLimit(1).frame(width: 210, alignment: .leading)
                                    ProgressView(value: (Double(l.level) + l.progress) / 4).frame(width: 140).tint(l.level >= 2 ? .green : .teal)
                                    Text("L\(l.level) \(l.note)").font(.caption.bold())
                                }
                            }
                            Text(h.levelCaption).font(.caption2).foregroundStyle(.secondary)
                        }.frame(maxWidth: .infinity, alignment: .leading)
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Your calibration curve").font(.headline)
                            CalibrationChart(bins: h.calibration).frame(width: 220, height: 120)
                            Text(h.calibrationNote).font(.caption2).foregroundStyle(.secondary)
                            Text(h.flipLine).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    if !h.actions.isEmpty {
                        HStack { ForEach(h.actions, id: \.id) { a in Button(a.title) { engine.domain.gameAction(a.id) }.font(.callout) } }
                    }
                }.padding(16).sdrWidth(880).sdrPanel()
            }
        }
    }
}

/// predicted (x) vs observed (y) harm-free rate per bin; dot size ∝ n; diagonal = perfect calibration
struct CalibrationChart: View {
    let bins: [CalibrationBin]
    var body: some View {
        GeometryReader { g in
            ZStack {
                Path { p in p.move(to: CGPoint(x: 0, y: g.size.height)); p.addLine(to: CGPoint(x: g.size.width, y: 0)) }
                    .stroke(.gray.opacity(0.6), style: StrokeStyle(lineWidth: 1, dash: [4, 4]))
                ForEach(bins) { b in
                    if let o = b.observed {
                        Circle().fill(.mint).frame(width: CGFloat(8 + min(b.n, 10) * 2), height: CGFloat(8 + min(b.n, 10) * 2))
                            .position(x: b.predicted * g.size.width, y: (1 - o) * g.size.height)
                        Text("n=\(b.n)").font(.system(size: 9)).position(x: b.predicted * g.size.width, y: max(8, (1 - o) * g.size.height - 14))
                    }
                }
            }
            .overlay(RoundedRectangle(cornerRadius: 6).stroke(.gray.opacity(0.5)))
        }
    }
}
