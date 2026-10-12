import RealityKit
import UIKit

/// Procedural, asset-free "clinical command center": soft blue-gray gradient dome, floor grid,
/// and a few low wall panels / a console ring suggesting a triage station.
enum ClinicalEnvironment {
    @MainActor static func make() -> Entity {
        let env = Entity(); env.name = "clinicalEnvironment"

        // gradient dome (inverted sphere)
        if let tex = gradientTexture() {
            var m = UnlitMaterial()
            m.color = .init(texture: .init(tex))
            let dome = ModelEntity(mesh: .generateSphere(radius: 40), materials: [m])
            dome.scale = [-1, 1, 1]          // render inside faces
            env.addChild(dome)
        }

        // floor + grid
        let floor = ModelEntity(mesh: .generatePlane(width: 30, depth: 30),
                                materials: [UnlitMaterial(color: UIColor(red: 0.20, green: 0.24, blue: 0.29, alpha: 1))])
        floor.position = [0, -0.001, 0]
        env.addChild(floor)
        let lineMat = UnlitMaterial(color: UIColor(red: 0.42, green: 0.52, blue: 0.60, alpha: 1))
        for i in -10...10 {
            let f = Float(i)
            let a = ModelEntity(mesh: .generateBox(width: 20, height: 0.002, depth: 0.012), materials: [lineMat])
            a.position = [0, 0.001, f]; env.addChild(a)
            let b = ModelEntity(mesh: .generateBox(width: 0.012, height: 0.002, depth: 20), materials: [lineMat])
            b.position = [f, 0.001, 0]; env.addChild(b)
        }

        // curved wall of dark display panels behind the agent arc (command-center feel)
        let panelMat = UnlitMaterial(color: UIColor(red: 0.16, green: 0.20, blue: 0.25, alpha: 1))
        let trimMat = UnlitMaterial(color: UIColor(red: 0.35, green: 0.70, blue: 0.80, alpha: 1))
        for k in -4...4 {
            let ang = Float(k) * 0.24
            let r: Float = 4.2
            let p = ModelEntity(mesh: .generateBox(width: 1.0, height: 1.6, depth: 0.04), materials: [panelMat])
            p.position = [r * sin(ang), 1.7, -r * cos(ang)]
            p.orientation = simd_quatf(angle: -ang, axis: [0, 1, 0])
            env.addChild(p)
            let trim = ModelEntity(mesh: .generateBox(width: 1.0, height: 0.02, depth: 0.05), materials: [trimMat])
            trim.position = [0, -0.82, 0]; p.addChild(trim)
        }

        // low console ring at waist height around the user (triage station)
        let consoleMat = SimpleMaterial(color: UIColor(red: 0.85, green: 0.88, blue: 0.91, alpha: 1), roughness: 0.6, isMetallic: false)
        for k in 0..<10 {
            let ang = -0.9 + Float(k) * 0.2
            let seg = ModelEntity(mesh: .generateBox(width: 0.17, height: 0.05, depth: 0.32, cornerRadius: 0.01), materials: [consoleMat])
            seg.position = [0.75 * sin(ang), 0.85, -0.75 * cos(ang)]
            seg.orientation = simd_quatf(angle: -ang, axis: [0, 1, 0])
            env.addChild(seg)
        }
        let edge = ModelEntity(mesh: .generateBox(width: 1.4, height: 0.006, depth: 0.01), materials: [trimMat])
        edge.position = [0, 0.878, -0.6]; env.addChild(edge)

        // soft overhead light for the lit (non-unlit) items
        let light = Entity()
        light.components.set(DirectionalLightComponent(color: .white, intensity: 2500))
        light.orientation = simd_quatf(angle: -.pi / 3, axis: [1, 0, 0])
        env.addChild(light)
        return env
    }

    /// Vertical gradient: pale blue-gray zenith -> calm mid blue-gray horizon -> darker below.
    private static func gradientTexture() -> TextureResource? {
        let w = 8, h = 256
        let r = UIGraphicsImageRenderer(size: CGSize(width: w, height: h))
        let img = r.image { ctx in
            let colors = [UIColor(red: 0.80, green: 0.85, blue: 0.90, alpha: 1).cgColor,
                          UIColor(red: 0.55, green: 0.63, blue: 0.71, alpha: 1).cgColor,
                          UIColor(red: 0.30, green: 0.36, blue: 0.43, alpha: 1).cgColor]
            let g = CGGradient(colorsSpace: CGColorSpaceCreateDeviceRGB(), colors: colors as CFArray, locations: [0, 0.5, 1])!
            ctx.cgContext.drawLinearGradient(g, start: .zero, end: CGPoint(x: 0, y: h), options: [])
        }
        guard let cg = img.cgImage else { return nil }
        return try? TextureResource(image: cg, options: .init(semantic: .color))
    }
}
