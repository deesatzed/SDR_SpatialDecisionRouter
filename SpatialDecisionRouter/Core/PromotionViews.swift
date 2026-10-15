import SwiftUI

/// M4 UI: critic → frozen replay evaluation → Principal card (Approve once / Decline / Defer) → champion generation → rollback.
struct PromotionView: View {
    @Environment(RouterEngine.self) private var engine
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                HStack {
                    Text("Promotion").font(.largeTitle.bold())
                    Spacer()
                    Button("Close") { engine.showPromotion = false; dismiss() }.accessibilityIdentifier("closePromotion")
                }
                HStack(spacing: 12) {
                    Text("CHAMPION gen \(engine.championGeneration)").font(.headline.bold()).padding(.horizontal, 10).padding(.vertical, 3)
                        .background(.indigo, in: Capsule()).accessibilityIdentifier("championGen")
                    Text(engine.champion.isEmpty ? "seed policy: follow the agent's pick" : engine.champion.map(\.text).joined(separator: " · "))
                        .font(.headline)
                    Spacer()
                    if engine.championGeneration > 0 {
                        Button("Roll back") { engine.rollbackChampion() }.tint(.red).accessibilityIdentifier("rollback")
                    }
                }
                Text(engine.packStatus()).font(.caption.monospaced()).foregroundStyle(.secondary)
                Text("The critic only proposes. A candidate must beat the champion on the frozen, blinded replay by the pre-registered margin (Δaccuracy ≥ \(String(format: "%.2f", PromotionEngine.deltaMin)), n ≥ \(PromotionEngine.nMin), wins/losses 90% low > \(String(format: "%.2f", PromotionEngine.signLoMin))), with no rise in critical misses and no removed clinical escalations. Only your signature promotes. History is SYNTHETIC; thresholds are design placeholders.")
                    .font(.callout).foregroundStyle(.secondary)
                Button("Run critic + replay") { engine.runCritic() }.tint(.teal).font(.title3.bold()).accessibilityIdentifier("runCritic")
                if let e = engine.promoError { Text(e).foregroundStyle(.pink).font(.headline) }
                ForEach(engine.lastEvaluations, id: \.id) { ev in EvaluationCard(ev: ev) }
            }.padding(24)
        }
        .buttonStyle(.bordered).controlSize(.large)
        .accessibilityIdentifier("promotionView")
    }
}

struct EvaluationCard: View {
    @Environment(RouterEngine.self) private var engine
    let ev: UnifiedDecisionRecord
    var body: some View {
        let p = ev.promo ?? PromotionInfo(), m = p.metrics
        let pending = engine.pendingPrincipal.contains { $0.id == ev.id }
        let decided = engine.promoLog.last { $0.kind == "principal_decision" && $0.ref_id == ev.id }?.promo?.decision
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(p.verdict == "passed" ? "BEATS CHAMPION" : "DISCARDED").font(.headline.bold()).padding(.horizontal, 8).padding(.vertical, 2)
                    .background(p.verdict == "passed" ? Color.green.opacity(0.7) : Color.gray.opacity(0.6), in: Capsule())
                Text(p.rule?.text ?? "").font(.title3.bold())
                Spacer()
                Text("vs gen \(p.champion_generation ?? 0)").font(.caption).foregroundStyle(.secondary)
            }
            if let m {
                Text("replay n=\(m.n) · champion \(m.champion_correct)/\(m.n) → candidate \(m.candidate_correct)/\(m.n) · Δ \(fmt(m.accuracy_delta)) [\(fmt(m.delta_interval.first ?? 0)), \(fmt(m.delta_interval.last ?? 0))] · wins/losses \(m.wins)/\(m.losses) · critical misses \(m.critical_champion)→\(m.critical_candidate)")
                    .font(.headline.monospacedDigit())
            }
            if let r = p.reasons, !r.isEmpty { Text(r.joined(separator: " · ")).font(.callout).foregroundStyle(.pink) }
            if p.verdict == "passed", let m {
                PrincipalCard(ev: ev, m: m, pending: pending, decided: decided)
            }
        }
        .padding(14).background(.white.opacity(0.06), in: RoundedRectangle(cornerRadius: 14))
        .accessibilityElement(children: .contain).accessibilityIdentifier("eval_\(p.area ?? "")")
    }
    private func fmt(_ x: Double) -> String { String(format: "%+.2f", x) }
}

/// the Principal card: real before/after replay diff, then Approve once / Decline / Defer (Pass = Defer)
struct PrincipalCard: View {
    @Environment(RouterEngine.self) private var engine
    let ev: UnifiedDecisionRecord
    let m: ReplayMetrics
    let pending: Bool
    let decided: String?
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("PRINCIPAL CARD · \(m.changed.count) replay cases change behaviour (worse first)").font(.caption.bold()).foregroundStyle(.orange)
            Grid(alignment: .leading, horizontalSpacing: 14, verticalSpacing: 3) {
                GridRow { Text("case").bold(); Text("before (champion)").bold(); Text("after (candidate)").bold(); Text("outcome").bold(); Text("") }
                ForEach(m.changed.sorted { ($0.after != $0.outcome ? 0 : 1) < ($1.after != $1.outcome ? 0 : 1) }.prefix(8), id: \.case_id) { c in
                    GridRow {
                        Text(c.title.replacingOccurrences(of: "synthetic ", with: "").replacingOccurrences(of: "personal_finance ", with: "").replacingOccurrences(of: "ed_triage ", with: "")).lineLimit(1)
                        Text(c.before).foregroundStyle(c.before == c.outcome ? .green : .secondary)
                        Text(c.after).foregroundStyle(c.after == c.outcome ? .green : .pink)
                        Text(c.outcome)
                        Text(c.after == c.outcome ? "✓ better" : (c.before == c.outcome ? "✗ worse" : "– both wrong"))
                    }
                }
            }.font(.callout)
            if m.changed.count > 8 { Text("… \(m.changed.count - 8) more in the exported promotion record").font(.caption).foregroundStyle(.secondary) }
            if pending {
                HStack(spacing: 12) {
                    Button("Approve once ✍︎") { engine.principal(ev, "approve_once") }.tint(.green).accessibilityIdentifier("principal_approve")
                    Button("Decline") { engine.principal(ev, "decline") }.tint(.red).accessibilityIdentifier("principal_decline")
                    Button("Defer (Pass)") { engine.principal(ev, "defer") }.tint(.gray).accessibilityIdentifier("principal_defer")
                }.font(.title3.bold())
            } else if let d = decided {
                Text("Principal: \(d)").font(.headline).foregroundStyle(d == "approve_once" ? .green : .secondary)
            }
        }
        .padding(10).overlay(RoundedRectangle(cornerRadius: 10).stroke(.orange.opacity(0.6), lineWidth: 1.5))
        .accessibilityElement(children: .contain).accessibilityIdentifier("principalCard")
    }
}

struct PromotionButton: View {
    @Environment(RouterEngine.self) private var engine
    #if os(visionOS)
    @Environment(\.openWindow) private var openWindow
    #endif
    var body: some View {
        Button("Promotion · gen \(engine.championGeneration)") {
            #if os(visionOS)
            openWindow(id: "promotion")
            #else
            engine.showPromotion = true
            #endif
        }.tint(.indigo).accessibilityIdentifier("openPromotions")
    }
}
