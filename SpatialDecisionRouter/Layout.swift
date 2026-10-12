import simd
import UIKit

enum Layout {
    /// Places proposals in a forward-facing amphitheatre around the origin. Rank 0 (highest priority) is nearest.
    static func position(rank: Int, count: Int) -> SIMD3<Float> {
        let perRing = 9
        let ring = rank / perRing
        let idx = rank % perRing
        let radius: Float = 1.6 + Float(ring) * 0.55
        let spread: Float = .pi * 0.5
        let angle = -spread / 2 + spread * Float(idx) / Float(perRing - 1)
        let y: Float = 1.35 + Float(ring) * 0.3 + (idx % 2 == 0 ? 0 : 0.18)
        return [radius * sin(angle), y, -radius * cos(angle)]
    }

    static func color(for p: Proposal) -> UIColor {
        let hue: CGFloat
        switch p.category {
        case "toxicity": hue = 0.0
        case "self-harm": hue = 0.83
        case "spam": hue = 0.12
        case "copyright": hue = 0.58
        case "violence": hue = 0.02
        case "fracture": hue = 0.08
        case "nodule": hue = 0.55
        case "hemorrhage": hue = 0.97
        case "pneumothorax": hue = 0.75
        case "navigation": hue = 0.5
        case "manipulation": hue = 0.15
        case "safety-stop": hue = 0.0
        case "charging": hue = 0.33
        default: hue = CGFloat(abs(p.category.hashValue % 100)) / 100
        }
        // low confidence = paler + more transparent
        let c = CGFloat(p.confidence)
        return UIColor(hue: hue, saturation: 0.35 + 0.6 * c, brightness: 0.95, alpha: 0.45 + 0.45 * c)
    }
}
