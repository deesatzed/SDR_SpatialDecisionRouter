import Foundation
/// Discrete-event ED capacity model (SYNTHETIC). Rooms per area, ESI service times,
/// admissions boarding until inpatient beds release, waiting room + LWBS, door-to-room.
struct EDCapacity {
    struct Occ { var id: String; var esi: Int; var doneAt: Double; var admit: Bool; var boarding = false }
    struct Waiter { var id: String; var esi: Int; var area: String; var arrival: Double; var iso: Bool }
    var rooms: [String: Int]
    var occ: [String: [Occ]] = [:]
    var wr: [Waiter] = []
    var lwbs = 0, boardingMinutes = 0.0, alertWaits: [Double] = [], doorToRoom: [Double] = []
    var placed: [String: Int] = [:]
    var bedRate: Double, lwbsAfter: Double, lwbsPerMin: Double, bedCredit = 0.0
    var rng: SplitMix64
    static let areas = ["resus", "main ED", "fast track", "isolation"]
    init(params p: [String: Double], seed: UInt64) {
        rooms = ["resus": Int(p["resusRooms"] ?? 3), "main ED": Int(p["mainRooms"] ?? 12),
                 "fast track": Int(p["fastRooms"] ?? 5), "isolation": Int(p["isoRooms"] ?? 3)]
        bedRate = p["inpatientBedsPerHour"] ?? 2.5; lwbsAfter = p["lwbsAfterMin"] ?? 120; lwbsPerMin = p["lwbsPerMin"] ?? 0.008
        rng = SplitMix64(s: seed &+ 77)
    }
    var waitingCount: Int { wr.count }
    func used(_ a: String) -> Int { occ[a]?.count ?? 0 }
    func free(_ a: String) -> Bool { used(a) < (rooms[a] ?? 0) }
    func waiting(_ a: String) -> Int { wr.filter { $0.area == a }.count }
    var boardingNow: Int { occ.values.flatMap { $0 }.filter { $0.boarding }.count }
    mutating func rnd() -> Double { Double(rng.next() % 1_000_000) / 1_000_000 }
    mutating func service(_ esi: Int) -> Double { [1: 240.0, 2: 200, 3: 170, 4: 80, 5: 50][esi, default: 150] * (0.6 + 0.8 * rnd()) }
    func admitP(_ esi: Int) -> Double { [1: 0.85, 2: 0.6, 3: 0.3, 4: 0.05, 5: 0.01][esi, default: 0.2] }
    static func physical(_ area: String) -> String { areas.contains(area) || area == "waiting room" ? area : "main ED" }
    mutating func prewarm(now: Double) {
        for (a, n) in [("resus", 2), ("main ED", 10), ("fast track", 3), ("isolation", 1)] {
            for i in 0..<n {
                let esi = a == "resus" ? 1 : a == "fast track" ? 4 : 3
                var o = Occ(id: "pre-\(a)-\(i)", esi: esi, doneAt: now + service(esi) * rnd(), admit: rnd() < admitP(esi))
                if a == "main ED" && i < 3 { o.admit = true; o.boarding = true }
                occ[a, default: []].append(o)
            }
        }
    }
    mutating func step(now: Double, dm: Double) {
        bedCredit += bedRate * dm / 60
        for a in Self.areas {
            var keep: [Occ] = []
            for var o in occ[a] ?? [] {
                if o.boarding { boardingMinutes += dm; if bedCredit >= 1 { bedCredit -= 1; continue }; keep.append(o); continue }
                if now >= o.doneAt { if o.admit { o.boarding = true; keep.append(o) }; continue }
                keep.append(o)
            }
            occ[a] = keep
        }
        bedCredit = min(bedCredit, 3)
        // LWBS (low acuity long waits) and rooming from waiting room by ESI then arrival
        var stay: [Waiter] = []
        for w in wr {
            if w.esi >= 3 && now - w.arrival > lwbsAfter && rnd() < lwbsPerMin * dm { lwbs += 1 } else { stay.append(w) }
        }
        wr = stay
        wr.sort { ($0.esi, $0.arrival) < ($1.esi, $1.arrival) }
        var rest: [Waiter] = []
        for w in wr {
            let target = free(w.area) ? w.area : (w.esi <= 2 && free("resus") ? "resus" : nil)
            if let t = target { room(w.id, w.esi, t, w.arrival, now) } else { rest.append(w) }
        }
        wr = rest
    }
    mutating func room(_ id: String, _ esi: Int, _ a: String, _ arrival: Double, _ now: Double) {
        occ[a, default: []].append(Occ(id: id, esi: esi, doneAt: now + service(esi), admit: rnd() < admitP(esi)))
        doorToRoom.append(now - arrival)
    }
    /// Capacity-aware ground truth for placement.
    func capacityAwareArea(esi: Int, alert: String, base: String) -> String {
        let a = Self.physical(base)
        if a == "waiting room" || free(a) { return base }
        if esi <= 2 && free("resus") { return "resus" }
        if esi <= 1 { return "resus" }
        return "waiting room"
    }
    mutating func place(id: String, esi: Int, area: String, isolation: Bool, arrival: Double, now: Double) {
        placed[area, default: 0] += 1
        var a = Self.physical(area)
        if a == "waiting room" { a = isolation ? "isolation" : (esi <= 3 ? "main ED" : "fast track"); wr.append(Waiter(id: id, esi: esi, area: a, arrival: arrival, iso: isolation)); return }
        if free(a) { room(id, esi, a, arrival, now) } else { wr.append(Waiter(id: id, esi: esi, area: a, arrival: arrival, iso: isolation)) }
    }
    func snapshot(queue: Int) -> [String: String] {
        var d = ["triageQueue": "\(queue)", "waitingRoom": "\(wr.count)", "boarding": "\(boardingNow)", "lwbs": "\(lwbs)"]
        for a in Self.areas { d[a] = "\(used(a))/\(rooms[a] ?? 0)"; d[a + " queue"] = "\(waiting(a))" }
        return d
    }
    func line(queue: Int) -> String {
        func f(_ n: String, _ a: String) -> String { let w = waiting(a); return "\(n) \(used(a))/\(rooms[a] ?? 0)" + (w > 0 ? " (+\(w))" : "") }
        return [f("resus", "resus"), f("main", "main ED"), f("FT", "fast track"), f("iso", "isolation"),
                "boarding \(boardingNow)", "WR \(wr.count)", "triage \(queue)"].joined(separator: " · ")
    }
    var medianDoorToRoom: Double { let s = doorToRoom.sorted(); return s.isEmpty ? 0 : s[s.count / 2] }
    var medianAlertWait: Double { let s = alertWaits.sorted(); return s.isEmpty ? 0 : s[s.count / 2] }
    var placedCounts: [(String, Int)] {
        let base = ["resus", "main ED", "fast track", "waiting room"]
        return base.map { ($0, placed[$0] ?? 0) } + placed.keys.filter { !base.contains($0) }.sorted().map { ($0, placed[$0]!) }
    }
}
