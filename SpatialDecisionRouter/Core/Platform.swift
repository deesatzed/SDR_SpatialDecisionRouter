import SwiftUI

/// Cross-platform shims so the shared panels render on visionOS (glass, fixed spatial widths)
/// and on iPad / Mac-Designed-for-iPad (material cards, adaptive widths).
extension Font {
    static var sdrHuge: Font {
        #if os(visionOS)
        .extraLargeTitle2
        #else
        .system(size: 38, weight: .bold)
        #endif
    }
}

extension View {
    @ViewBuilder func sdrPanel() -> some View {
        #if os(visionOS)
        self.glassBackgroundEffect()
        #else
        self.background(.regularMaterial, in: RoundedRectangle(cornerRadius: 22, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 22, style: .continuous).stroke(.white.opacity(0.08)))
        #endif
    }
    /// fixed width in space; fill the column on iPad
    @ViewBuilder func sdrWidth(_ w: CGFloat) -> some View {
        #if os(visionOS)
        self.frame(width: w)
        #else
        self.frame(maxWidth: .infinity, alignment: .leading)
        #endif
    }
    @ViewBuilder func sdrMaxHeight(_ h: CGFloat) -> some View {
        #if os(visionOS)
        self.frame(maxHeight: h).fixedSize(horizontal: false, vertical: true)
        #else
        self
        #endif
    }
}

/// Wrapping row: chips/buttons flow onto the next line when the column is narrow (iPad portrait).
struct FlowRow: Layout {
    var spacing: CGFloat = 6
    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let maxW = proposal.width ?? .infinity
        var x: CGFloat = 0, y: CGFloat = 0, rowH: CGFloat = 0, widest: CGFloat = 0
        for v in subviews {
            let s = v.sizeThatFits(.unspecified)
            if x > 0 && x + s.width > maxW { y += rowH + spacing; x = 0; rowH = 0 }
            x += s.width + spacing; rowH = max(rowH, s.height); widest = max(widest, x - spacing)
        }
        return CGSize(width: min(widest, maxW), height: y + rowH)
    }
    func placeSubviews(in b: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x = b.minX, y = b.minY, rowH: CGFloat = 0
        for v in subviews {
            let s = v.sizeThatFits(.unspecified)
            if x > b.minX && x + s.width > b.maxX { y += rowH + spacing; x = b.minX; rowH = 0 }
            v.place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(s)); x += s.width + spacing; rowH = max(rowH, s.height)
        }
    }
}
