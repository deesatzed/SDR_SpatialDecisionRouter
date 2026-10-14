#if os(visionOS)
import RealityKit
import UIKit

/// Asset-free environment themed by the domain's ThemeSpec: gradient dome, floor grid, panel wall, console ring.
enum ProceduralEnvironment {
    static func c(_ v: [Double], _ a: CGFloat = 1) -> UIColor { UIColor(red: v[0], green: v[1], blue: v[2], alpha: a) }

    @MainActor static func make(_ t: ThemeSpec) -> Entity {
        let env = Entity(); env.name = "environment"
        if let tex = gradient(t) {
            var m = UnlitMaterial(); m.color = .init(texture: .init(tex))
            let dome = ModelEntity(mesh: .generateSphere(radius: 40), materials: [m]); dome.scale = [-1, 1, 1]
            env.addChild(dome)
        }
        let floor = ModelEntity(mesh: .generatePlane(width: 30, depth: 30), materials: [UnlitMaterial(color: c(t.floor))])
        floor.position = [0, -0.001, 0]; env.addChild(floor)
        let lineMat = UnlitMaterial(color: c(t.grid))
        for i in -10...10 {
            let f = Float(i)
            let a = ModelEntity(mesh: .generateBox(width: 20, height: 0.002, depth: 0.012), materials: [lineMat]); a.position = [0, 0.001, f]; env.addChild(a)
            let b = ModelEntity(mesh: .generateBox(width: 0.012, height: 0.002, depth: 20), materials: [lineMat]); b.position = [f, 0.001, 0]; env.addChild(b)
        }
        let panelMat = UnlitMaterial(color: c(t.panel)), trimMat = UnlitMaterial(color: c(t.trim))
        for k in -4...4 {
            let ang = Float(k) * 0.24, r: Float = 4.2
            let p = ModelEntity(mesh: .generateBox(width: 1.0, height: 1.6, depth: 0.04), materials: [panelMat])
            p.position = [r * sin(ang), 1.7, -r * cos(ang)]; p.orientation = simd_quatf(angle: -ang, axis: [0, 1, 0])
            let trim = ModelEntity(mesh: .generateBox(width: 1.0, height: 0.02, depth: 0.05), materials: [trimMat]); trim.position = [0, -0.82, 0]
            p.addChild(trim); env.addChild(p)
        }
        let light = Entity()
        light.components.set(DirectionalLightComponent(color: .white, intensity: 2500))
        light.orientation = simd_quatf(angle: -.pi / 3, axis: [1, 0, 0]); env.addChild(light)
        return env
    }

    private static func gradient(_ t: ThemeSpec) -> TextureResource? {
        let w = 8, h = 256
        let img = UIGraphicsImageRenderer(size: CGSize(width: w, height: h)).image { ctx in
            let g = CGGradient(colorsSpace: CGColorSpaceCreateDeviceRGB(),
                               colors: [c(t.skyTop).cgColor, c(t.skyHorizon).cgColor, c(t.skyBottom).cgColor] as CFArray, locations: [0, 0.5, 1])!
            ctx.cgContext.drawLinearGradient(g, start: .zero, end: CGPoint(x: 0, y: h), options: [])
        }
        guard let cg = img.cgImage else { return nil }
        return try? TextureResource(image: cg, options: .init(semantic: .color))
    }
}
#endif
