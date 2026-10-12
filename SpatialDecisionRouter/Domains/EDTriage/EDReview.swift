import Foundation

/// ED review hooks (SYNTHETIC): reason rules, urgency, downstream previews, detail sections.
extension EDTriageDomain {
    private func hxDrivers(_ p: EDPatient, _ link: String) -> [String] {
        var r: [String] = []
        switch link {
        case "acuity":
            if p.anticoag && p.complaint == .fallHead { r.append("anticoag + head strike") }
            if p.immuno && p.temp >= 38.0 { r.append("immunosuppressed + fever") }
            if p.bounceback72h { r.append("72h bounceback") }
            if p.pregnant && p.complaint == .abdPain { r.append("pregnant + abd pain") }
            if p.baselineAMS && p.gcs < 15 { r.append("baseline AMS explains GCS") }
        case "sepsis": if p.immuno && p.temp >= 38.0 { r.append("immunosuppressed + fever") }
        case "isolation": if p.mdro { r.append("MDRO history") }
        default: break
        }
        return r
    }

    func reasons(item: DomainItem, link: LinkSpec, proposal: String, upstream: [String: String]) -> [ReasonChip] {
        guard let p = patients[item.id] else { return [] }
        var r: [ReasonChip] = []
        let hx = hxDrivers(p, link.id)
        if !hx.isEmpty {
            // the agents are history-blind: flag when a history rule would change their answer
            let yn: (Bool) -> String = { $0 ? "yes" : "no" }
            let withHx: String? = link.id == "acuity" ? "\(EDRules.esi(p))" : link.id == "sepsis" ? yn(EDRules.sepsis(p))
                : link.id == "isolation" ? yn(EDRules.isolation(p)) : nil
            let conflict = withHx.map { $0 != proposal } ?? false
            r.append(ReasonChip(text: (conflict ? "history conflicts with proposal: " : "history relevant: ") + hx.joined(separator: ", "),
                                key: conflict ? "history conflicts" : "history relevant", severity: conflict ? .high : .info))
        }
        if p.sbp < 90 || p.spo2 < 92 || p.hr > 120 || p.rr > 24 || p.gcs < 13 {
            var v: [String] = []
            if p.sbp < 90 { v.append("SBP \(p.sbp)") }; if p.spo2 < 92 { v.append("SpO2 \(p.spo2)%") }
            if p.hr > 120 { v.append("HR \(p.hr)") }; if p.rr > 24 { v.append("RR \(p.rr)") }; if p.gcs < 13 { v.append("GCS \(p.gcs)") }
            r.append(ReasonChip(text: "abnormal vitals: " + v.joined(separator: ", "), key: "abnormal vitals", severity: .high))
        }
        if link.id == "placement" {
            let a = EDCapacity.physical(proposal)
            if a != "waiting room" && !capacity.free(a) {
                r.append(ReasonChip(text: "capacity full: \(a) \(capacity.used(a))/\(capacity.rooms[a] ?? 0)", key: "capacity full", severity: .high))
            }
            if capacity.boardingNow >= 3 { r.append(ReasonChip(text: "boarding \(capacity.boardingNow)", key: "boarding", severity: .info)) }
        }
        return r
    }

    func urgency(item: DomainItem, link: LinkSpec, proposal: String) -> Double {
        guard let p = patients[item.id] else { return 0 }
        var u = 0.0
        if link.firesAlert && !link.alertNegative.contains(proposal) { u += 0.6 }      // positive alert waiting to fire
        if p.sbp < 90 || p.spo2 < 90 || p.gcs < 13 { u += 0.5 }
        if link.id == "acuity" && (Int(proposal) ?? 3) <= 2 { u += 0.3 }
        return u
    }

    func downstreamPreview(item: DomainItem, link: LinkSpec, answer: String) -> String? {
        switch link.id {
        case "acuity": return "Charge Nurse: logs ESI \(answer) → Placement uses it"
        case "sepsis": return answer == "yes" ? "Alert Team paged: sepsis bundle (lactate, cultures, abx)" : "Alert Team: no sepsis page"
        case "alert": return answer == "none" ? "Alert Team: no code" : "Alert Team paged: \(answer) code activated"
        case "isolation":
            let free = (capacity.rooms["isolation"] ?? 0) - capacity.used("isolation")
            return answer == "yes" ? "Isolation Desk: holds iso room (\(free) free) + PPE sign" : "Isolation Desk: standard precautions"
        case "placement":
            let a = EDCapacity.physical(answer)
            if a == "waiting room" { return "Bed Board: waiting room (#\(capacity.waitingCount + 1) in line)" }
            if capacity.free(a) { return "Bed Board: assigns \(answer) room \(capacity.used(a) + 1)" }
            return "Bed Board: \(answer) full → queued (+\(capacity.waiting(a) + 1))"
        default: return nil
        }
    }

    /// Deterministic per-patient synthetic chart (does not disturb the generator stream).
    func detail(item: DomainItem, section: String) -> [(String, String)]? {
        guard let p = patients[item.id] else { return nil }
        var r = SplitMix64(s: 7919 &* UInt64(Int(p.id.dropFirst()) ?? 1))
        switch section {
        case "PMH":
            let f = p.historyFlags
            return f.isEmpty ? [("PMH", "none reported")] : f.map { ($0, Self.pmhNote[$0] ?? "") }
        case "Meds":
            var m: [(String, String)] = []
            if p.anticoag { m.append(("apixaban 5 mg BID", "anticoagulant")) }
            if p.immuno { m.append((r.pick(["prednisone 20 mg", "tacrolimus 2 mg BID", "methotrexate weekly"]), "immunosuppressant")) }
            if p.chf { m.append(("furosemide 40 mg", "diuretic")) }
            if p.ckd { m.append(("calcitriol", "CKD")) }
            if p.priorStrokeMI { m.append(("aspirin 81 mg + atorvastatin", "secondary prevention")) }
            if p.pregnant { m.append(("prenatal vitamin", "")) }
            return m.isEmpty ? [("meds", "none reported")] : m
        case "Allergies":
            return [("allergies", r.pick(["NKDA", "NKDA", "NKDA", "penicillin (rash)", "sulfa", "contrast (hives)"]))]
        case "Prior visits":
            var v: [(String, String)] = []
            if p.bounceback72h { v.append(("2 days ago", "ED · \(p.complaint.rawValue) · discharged")) }
            let n = Int(r.range(0, 3))
            for i in 0..<n { v.append(("\(Int(r.range(1, 11)) + i * 2) mo ago", r.pick(["ED · fall", "ED · URI", "clinic · BP check", "ED · abd pain", "admit · pneumonia"]))) }
            return v.isEmpty ? [("prior visits", "none in 12 mo")] : v
        case "Prior ESI":
            return p.bounceback72h ? [("last visit", "ESI \(min(5, EDRules.esi(p, hx: false) + 1))")] : [("last visit", "none on file")]
        case "Vitals trend":
            let t0 = Int(p.arrival) % 60
            return [("arrival +0m", p.vitals),
                    ("+\(10 + t0 % 5)m", "HR \(p.hr + Int(r.range(-6, 9))) SpO2 \(min(100, p.spo2 + Int(r.range(-2, 2))))% T \(String(format: "%.1f", p.temp + r.range(-0.2, 0.4)))"),
                    ("+\(25 + t0 % 7)m", "HR \(p.hr + Int(r.range(-8, 12))) SBP \(p.sbp + Int(r.range(-10, 6)))")]
        default: return nil
        }
    }
    static let pmhNote: [String: String] = [
        "anticoag": "bleeding risk ↑ with head strike", "immunosuppressed": "fever = possible sepsis", "CHF": "volume status",
        "CKD": "renal dosing / contrast", "prior stroke/MI": "vascular risk", "MDRO": "contact isolation",
        "72h bounceback": "return within 72 h", "recent surgery": "post-op complication risk", "baseline AMS": "GCS < 15 at baseline",
        "pregnant": "OB considerations"]
}
