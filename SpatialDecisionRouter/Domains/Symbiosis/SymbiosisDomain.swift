import Foundation

/// Symbiosis (M1 demoable slice): seeded three-column cards for two areas — ED triage (clinical, capped) and
/// personal finance. No LLM; OfflineStubGenerator is the optional hook. All content SYNTHETIC; not clinical or financial advice.
@MainActor final class SymbiosisDomain: DomainModule {
    static let options = ["Accept plan", "Alternative plan", "Hold — gather info", "Escalate"]
    let config: DomainConfig
    private(set) var now: Double = 0
    var minutesPerSecond: Double { 1 }
    private var queue: [DomainItem] = []
    private var order: [String] = []
    private var completedIds: Set<String> = []
    private(set) var cards: [String: SymbiosisCard] = [:]
    var contexts: [String: SymbiosisContext] = ["ed_triage": SymbiosisSeeds.clinical, "personal_finance": SymbiosisSeeds.finance]
    var counts: [String: Int] = [:]
    let generator: SymbiosisCardGenerator = OfflineStubGenerator()

    init() {
        var link = LinkSpec(id: "plan", source: "ai_depth", dest: "plan_of_record", question: "Plan:", answerType: .category,
                            options: Self.options)
        link.costWeight = 0.8; link.shortLabel = "plan"
        link.previews = ["Accept plan": "{dest}: the bridge's proposed plan goes ahead", "Alternative plan": "{dest}: the alternative goes ahead",
                         "Hold — gather info": "{dest}: nothing yet — the human gathers one more fact first", "Escalate": "{dest}: handed to a senior human",
                         "*": "{dest}: {answer}"]
        var c = DomainConfig(id: "symbiosis", title: "Symbiosis — Human judgment × AI depth",
                             agents: [AgentSpec(id: "ai_depth", name: "AI depth", role: "carries the detail", tier: 0),
                                      AgentSpec(id: "plan_of_record", name: "Plan of record", role: "what actually happens", tier: 1)],
                             links: [link])
        c.defaultSite = "symbiosis-seed"
        c.terminology = Terminology(itemNoun: "card", itemNounPlural: "cards", boardTitle: "Symbiosis Board",
                                    syntheticBanner: "SYNTHETIC seeded scenarios — not clinical or financial advice",
                                    completedLabel: "Decided", historyLabel: "Area", capacityLabel: "Dials")
        c.review.autoPassConfidence = 1.01; c.review.autoPassMaxCost = 0; c.review.spotCheckRate = 0
        c.review.escalationLink = "plan"; c.review.escalateAnswer = "Escalate"
        c.detailSections = ["Dials", "Functional knowledge"]
        c.rulesTable = ["Human holds judgment; AI holds depth; the bridge names the checkpoint.",
                        "Every decision + split rating is a signed, hash-chained unified record.",
                        "Dials are seeded placeholders in M1; clinical caps (autonomy ≤ 40, deference ≥ 80) always apply."]
        c.glossary = ["split rating": "Second label: did the human/AI split feel right? It never changes dials on its own.",
                      "dials": "Deference · Detail absorption · Challenge · Autonomy horizon (0–100). Seeded placeholders until M2."]
        config = c
    }

    func reset(seed: UInt64) {
        now = 0; completedIds = []; counts = [:]; cards = [:]; issued = 0; decidedN = 0
        // finance first (earned rise shows mid-demo), then ED triage (critical miss → demotion shows on the last ED card)
        let all = (Self.imported() ?? []) + Self.seed.filter { $0.area == "personal_finance" } + Self.seed.filter { $0.area != "personal_finance" }
        for k in all { cards[k.id] = k }
        order = all.map(\.id)
        queue = all.enumerated().map { i, k in item(k, arrival: Double(i)) }
    }
    private func item(_ k: SymbiosisCard, arrival: Double) -> DomainItem {
        let ctx = contexts[k.area]!
        var f: [String: String] = ["symbiosis": "1", "area": k.area, "title": k.title, "situation": k.situation,
                                   "human_judgment": k.humanJudgment, "human_question": k.humanQuestion,
                                   "bridge_architecture": k.bridgeArchitecture, "bridge_checkpoint": k.bridgeCheckpoint, "bridge_workflow": k.bridgeWorkflow,
                                   "ai_distilled": k.aiDistilled, "ai_detail": k.aiDetail.joined(separator: "\n"), "ai_edge": k.aiEdgeCases.joined(separator: "\n"),
                                   "plan": k.planText, "alternative": k.alternativeText, "demo_split": k.demoSplit.rawValue, "showCapacity": "yes",
                                   "severity": k.severity ?? "normal", "origin": k.origin]
        if let call = Self.demoSpots[k.id] { f["demo_spot"] = "1"; f["demo_human_call"] = call }
        return DomainItem(id: k.id, fields: f, displayLine: "\(ctx.title) · \(k.title)", shortLine: "\(ctx.title): \(k.title)",
                          historyLine: k.situation, arrivalTime: arrival)
    }

    func advance(minutes: Double) { now += minutes }
    private var issued = 0
    /// one card at a time: the next card is issued only once the previous one is decided
    func nextItem() -> DomainItem? {
        guard !queue.isEmpty, issued == decidedN else { return nil }
        issued += 1; return queue.removeFirst()
    }
    private var decidedN = 0
    func propose(item: DomainItem, link: LinkSpec, routed: [String: String]) -> Proposal {
        let k = cards[item.id]!
        // M4: the human-promoted champion policy may change the AI's pick (never on hard-trigger cards or clinical escalations)
        let a = k.hardTrigger != nil ? k.proposal : PromotionEngine.answer(ChampionPolicy.rules, area: k.area, conf: k.proposalConfidence, severity: k.severity ?? "normal", base: k.proposal)
        return Proposal(answer: a, confidence: k.proposalConfidence)
    }
    func groundTruth(item: DomainItem, link: LinkSpec, routed: [String: String]) -> String? { cards[item.id]?.scriptedOutcome }
    func demoAnswer(item: DomainItem, link: LinkSpec) -> String? { cards[item.id]?.scriptedOutcome }
    func complete(item: DomainItem, effective: [String: String]) { completedIds.insert(item.id) }
    func alertFired(item: DomainItem, link: LinkSpec) {}
    func decided(item: DomainItem, link: LinkSpec, answer: String, latency: TimeInterval, by: String) { counts[answer, default: 0] += 1; decidedN += 1 }
    func hardTrigger(item: DomainItem) -> String? { cards[item.id]?.hardTrigger }
    var isDemoDone: Bool { DemoState.on && queue.isEmpty && Set(order).isSubset(of: completedIds) }
    func demoCaption(item: DomainItem) -> String? {
        guard let i = order.firstIndex(of: item.id) else { return nil }
        return "\(i + 1)/\(order.count) · read your column, peek at the AI's, rate the split, then decide"
    }
    func area(_ item: DomainItem) -> SymbiosisContext? { item.fields["area"].flatMap { contexts[$0] } }
    func capacitySnapshot() -> [String: String] { ["areas": contexts.keys.sorted().joined(separator: ",")] }
    func capacityLine() -> String { "dials start seeded; they move only on outcome-graded ledger evidence (thresholds are placeholders) · clinical caps enforced" }
    func boardMetrics(_ s: EngineStats) -> [MetricValue] {
        [MetricValue(label: "Cards decided", value: "\(s.decisions)"),
         MetricValue(label: "Changed the AI's pick", value: "\(s.corrections)"),
         MetricValue(label: "Matched scripted outcome", value: "\(s.decisions - s.misses)/\(s.decisions)"),
         MetricValue(label: "Escalated", value: "\(counts["Escalate"] ?? 0)")]
    }
    func breakdown() -> [(String, Int)] { Self.options.map { ($0, counts[$0] ?? 0) } }
    func reasons(item: DomainItem, link: LinkSpec, proposal: String, upstream: [String: String]) -> [ReasonChip] {
        guard let a = area(item) else { return [] }
        var r = [ReasonChip(text: a.clinical ? "clinical area · caps on" : "personal area", key: "dials", severity: a.clinical ? .high : .info),
                 ReasonChip(text: "split rating wanted", key: "split rating", severity: .info)]
        if (cards[item.id]?.proposalConfidence ?? 1) < 0.7 { r.append(ReasonChip(text: "AI unsure (seeded confidence)", key: "", severity: .warn)) }
        return r
    }
    func decisionContext(item: DomainItem) -> DecisionContext {
        let a = area(item)
        return DecisionContext(domain: "symbiosis:\(item.fields["area"] ?? "unknown")", contextId: item.fields["area"] ?? "unknown",
                               dials: a?.dials, generation: a?.generation ?? 0,
                               reliability: RecordReliability(score: nil, n: 0, label: "placeholder — no graded labels yet"),
                               outcomeSource: item.fields["origin"] == "imported" ? "imported_outcome (synthetic template)" : "seeded_scenario (synthetic)")
    }
    func detail(item: DomainItem, section: String) -> [(String, String)]? {
        guard let a = area(item) else { return nil }
        switch section {
        case "Dials": return [("deference", "\(Int(a.dials.deference))"), ("detail absorption", "\(Int(a.dials.detail_absorption))"),
                              ("challenge", "\(Int(a.dials.challenge))"), ("autonomy horizon", "\(Int(a.dials.autonomy_horizon))"),
                              ("source", a.dials.source), ("caps", a.clinical ? "autonomy ≤ \(Int(a.caps.autonomyMax)) · deference ≥ \(Int(a.caps.deferenceMin))" : "none")]
        case "Functional knowledge": return a.humanFocus.map { ("you keep", $0) } + a.aiFocus.map { ("AI carries", $0) }
        default: return nil
        }
    }
}

extension SymbiosisDomain {
    /// M3 demo: forced "Your call first" spot-checks, with the (scripted) human call. The demo human misses all three,
    /// so the sharpness rule hands detail back alongside the earned rise at FIN-6.
    static let demoSpots: [String: String] = ["SYM-FIN-4": "Alternative plan", "SYM-FIN-5": "Alternative plan", "SYM-FIN-6": "Alternative plan"]
    /// compact seeded finance card where the AI's pick is right (gives the earned-autonomy demo graded evidence)
    static func fin(_ id: String, _ title: String, _ sit: String, _ q: String, _ ai: String, _ plan: String, _ alt: String,
                    outcome: String, split: SplitRating) -> SymbiosisCard {
        SymbiosisCard(id: id, area: "personal_finance", title: title, situation: sit + " Sample scenario.",
                      humanJudgment: "Does this fit what the money is for?", humanQuestion: q,
                      bridgeArchitecture: "AI checks the mechanics; you check the fit with your life.",
                      bridgeCheckpoint: "No emergency fund → hold.", bridgeWorkflow: "AI: rules + arithmetic. You: goals.",
                      aiDistilled: ai, aiDetail: ["Check fees and terms first"], aiEdgeCases: ["Irregular income"],
                      planText: plan, alternativeText: alt, proposal: "Accept plan", proposalConfidence: 0.8,
                      scriptedOutcome: outcome, hardTrigger: nil, demoSplit: split)
    }

    /// `-importItems <dir>`: personal-finance items from tools/import_cases.py (`<dir>/items/personal_finance.json`, outcomes from
    /// `<dir>/decisions_imported.jsonl`). Imported options map to Symbiosis options by closest fit (shown on the card).
    static let importMap = ["proceed": "Accept plan", "proceed with changes": "Alternative plan", "pause and review": "Hold — gather info", "decline": "Escalate"]
    static func imported() -> [SymbiosisCard]? {
        let a = ProcessInfo.processInfo.arguments
        guard let i = a.firstIndex(of: "-importItems"), i + 1 < a.count else { return nil }
        let dir = URL(fileURLWithPath: a[i + 1])
        guard let d = try? Data(contentsOf: dir.appendingPathComponent("items/personal_finance.json")),
              let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any], let items = j["items"] as? [[String: Any]] else { return nil }
        var outcome: [String: String] = [:]
        if let t = try? String(contentsOf: dir.appendingPathComponent("decisions_imported.jsonl"), encoding: .utf8) {
            for l in t.split(separator: "\n") {
                guard let r = try? JSONSerialization.jsonObject(with: Data(l.utf8)) as? [String: Any], let iid = r["item_id"] as? String,
                      let o = (r["outcome"] as? [String: Any])?["value"] as? String else { continue }
                outcome[iid] = o
            }
        }
        return items.compactMap { it in
            guard let id = it["id"] as? String else { return nil }
            let ap = it["agent_proposal"] as? [String: Any]
            let prop = importMap[(ap?["answer"] as? String) ?? ""] ?? "Hold — gather info"
            let pres = (it["presentation"] as? String) ?? ""
            return SymbiosisCard(id: id, area: "personal_finance", title: pres, situation: "Imported synthetic case (\(it["context_id"] as? String ?? "")).",
                                 humanJudgment: "Does this fit what the money is for?", humanQuestion: "What would you regret?",
                                 bridgeArchitecture: "Imported options: proceed = Accept plan · proceed with changes = Alternative · pause and review = Hold · decline = Escalate (closest fit).",
                                 bridgeCheckpoint: (it["hard_trigger"] as? String).map { "Fixed trigger: \($0)" } ?? "none",
                                 bridgeWorkflow: "AI: mechanics. You: fit.", aiDistilled: "Imported case — no AI depth text in the template.",
                                 aiDetail: [], aiEdgeCases: [], planText: "proceed", alternativeText: "proceed with changes",
                                 proposal: prop, proposalConfidence: (ap?["confidence"] as? Double) ?? 0.5,
                                 scriptedOutcome: outcome[id].flatMap { importMap[$0] }, hardTrigger: it["hard_trigger"] as? String,
                                 demoSplit: .about_right, origin: "imported")
        }
    }

    static let seed: [SymbiosisCard] = [
        SymbiosisCard(id: "SYM-ED-1", area: "ed_triage", title: "Abdominal pain, 'looks fine'",
                      situation: "34F, lower abdominal pain 6 h, vitals normal, smiling in triage. Sample scenario.",
                      humanJudgment: "Does she look sick to you, or only sound fine?",
                      humanQuestion: "Is there anything about this story you would not want to send home?",
                      bridgeArchitecture: "AI lists must-not-miss causes; you decide if any is plausible enough to change the level.",
                      bridgeCheckpoint: "Positive pregnancy test or syncope → hard escalation (fixed trigger).",
                      bridgeWorkflow: "AI: differential + pending labs. You: gestalt + one targeted question.",
                      aiDistilled: "Normal vitals do not rule out ectopic pregnancy or torsion in the first hours.",
                      aiDetail: ["Ask LMP and contraception; obtain urine hCG first", "Pain migration and guarding raise appendicitis likelihood"],
                      aiEdgeCases: ["Early ectopic with normal vitals", "Intermittent torsion pain-free between episodes"],
                      planText: "Level 3, urine hCG + labs in the waiting room", alternativeText: "Level 2, bed now",
                      proposal: "Accept plan", proposalConfidence: 0.74, scriptedOutcome: "Hold — gather info", hardTrigger: nil, demoSplit: .about_right),
        SymbiosisCard(id: "SYM-ED-2", area: "ed_triage", title: "Chest pressure, diaphoretic",
                      situation: "61M, chest pressure 40 min, sweaty, ECG pending. Sample scenario.",
                      humanJudgment: "Fixed trigger fired — confirm you saw it and route to the resuscitation team.",
                      humanQuestion: "Who owns this patient in the next 5 minutes?",
                      bridgeArchitecture: "Hard trigger: reliability analysis bypassed; the human acknowledges and escalates.",
                      bridgeCheckpoint: "Possible MI → hard escalation (fixed trigger, never learned away).",
                      bridgeWorkflow: "AI: ECG within 10 min checklist. You: acknowledge + hand-off.",
                      aiDistilled: "Diaphoresis with chest pressure is a high-risk presentation regardless of age.",
                      aiDetail: ["ECG within 10 minutes of arrival", "Atypical presentations are common in diabetics and older women"],
                      aiEdgeCases: ["Aortic dissection mimics", "Normal first ECG does not exclude MI"],
                      planText: "Escalate to resus now", alternativeText: "—",
                      proposal: "Escalate", proposalConfidence: 0.95, scriptedOutcome: "Escalate", hardTrigger: "possible MI (chest pressure + diaphoresis)", demoSplit: .about_right),
        SymbiosisCard(id: "SYM-ED-3", area: "ed_triage", title: "Elderly fall, 'just a bruise'",
                      situation: "82M on anticoagulant, fell at home, small forehead bruise, alert. Sample scenario.",
                      humanJudgment: "The AI says routine; your experience says anticoagulated head strikes bleed late. Which wins?",
                      humanQuestion: "What would make you regret sending him to the waiting room?",
                      bridgeArchitecture: "AI applies the rule; you decide whether the rule fits this patient.",
                      bridgeCheckpoint: "Anticoagulant + head strike → imaging pathway (your override is logged and later graded).",
                      bridgeWorkflow: "AI: guideline criteria. You: frailty + home situation.",
                      aiDistilled: "Anticoagulated older adults with head strike warrant imaging even when alert.",
                      aiDetail: ["Many decision rules exclude anticoagulated patients", "Delayed bleeds can present hours later"],
                      aiEdgeCases: ["Subtle confusion attributed to baseline dementia"],
                      planText: "Level 4, waiting room", alternativeText: "Level 3 + head CT pathway",
                      proposal: "Accept plan", proposalConfidence: 0.62, scriptedOutcome: "Alternative plan", hardTrigger: nil, demoSplit: .overstepped_me,
                      severity: "critical"),
        SymbiosisCard(id: "SYM-ED-4", area: "ed_triage", title: "Sprained ankle, can walk",
                      situation: "25M twisted ankle playing football, bearing weight, no bony tenderness. Sample scenario.",
                      humanJudgment: "After the last miss, the AI defers more — do you agree this one is routine?",
                      humanQuestion: "Anything in the story that doesn't fit an ankle sprain?",
                      bridgeArchitecture: "AI applies the ankle rule; you confirm the story fits.",
                      bridgeCheckpoint: "Unable to bear weight or bony tenderness → imaging.",
                      bridgeWorkflow: "AI: decision rule. You: story fit.",
                      aiDistilled: "Weight-bearing with no bony tenderness usually means no fracture imaging is needed.",
                      aiDetail: ["Check both malleoli and the base of the fifth metatarsal"], aiEdgeCases: ["High ankle sprain"],
                      planText: "Level 5, fast track", alternativeText: "Level 4 + X-ray",
                      proposal: "Accept plan", proposalConfidence: 0.8, scriptedOutcome: "Accept plan", hardTrigger: nil, demoSplit: .about_right),
        SymbiosisCard(id: "SYM-FIN-1", area: "personal_finance", title: "Pay off car loan or invest?",
                      situation: "Windfall equal to the car loan balance. Sample scenario; numbers omitted on purpose.",
                      humanJudgment: "What is this money for, and how would you feel in a down year?",
                      humanQuestion: "Is there a near-term need (job change, family) the spreadsheet can't see?",
                      bridgeArchitecture: "AI compares after-tax rates and liquidity; you decide what security is worth to you.",
                      bridgeCheckpoint: "No emergency fund → hold (AI will not recommend illiquid moves).",
                      bridgeWorkflow: "AI: rate math + scenarios. You: goals + risk tolerance.",
                      aiDistilled: "Paying a loan is a guaranteed return equal to its rate; investing is uncertain but usually higher over long periods.",
                      aiDetail: ["Check for prepayment penalties", "Compare against the after-tax expected return"],
                      aiEdgeCases: ["Low-rate loan + no emergency fund", "Employer match left unclaimed"],
                      planText: "Invest, keep paying the loan", alternativeText: "Pay off the loan",
                      proposal: "Accept plan", proposalConfidence: 0.68, scriptedOutcome: "Accept plan", hardTrigger: nil, demoSplit: .buried_me),
        fin("SYM-FIN-3", "Raise the 401(k) contribution to the match?", "Employer matches up to a percentage; you contribute below it.",
            "Is there any reason you need this cash in the next year?", "Match is free money; liquidity is the trade-off.",
            "Raise to the match", "Keep as is", outcome: "Accept plan", split: .buried_me),
        fin("SYM-FIN-4", "Turn on automatic savings transfer?", "Paycheck lands; savings depend on remembering.",
            "Will an automatic transfer ever leave you short on rent?", "Automation beats willpower for most people.",
            "Automate a fixed transfer", "Keep manual", outcome: "Accept plan", split: .buried_me),
        fin("SYM-FIN-5", "Refinance a high-rate card balance?", "Balance on a high-APR card; a 0% transfer offer arrived.",
            "Will you stop using the card once the balance moves?", "Transfer fees and the promo end date matter more than the headline rate.",
            "Transfer and set a payoff plan", "Keep paying as is", outcome: "Accept plan", split: .buried_me),
        fin("SYM-FIN-6", "Cancel unused subscriptions?", "Several monthly charges you rarely use.",
            "Which of these would you actually miss?", "Small recurring charges add up; cancellation terms vary.",
            "Cancel the unused ones", "Keep all", outcome: "Accept plan", split: .about_right),
        SymbiosisCard(id: "SYM-FIN-2", area: "personal_finance", title: "Co-sign a sibling's lease?",
                      situation: "Sibling asks you to co-sign. Sample scenario.",
                      humanJudgment: "This is about the relationship as much as the money — what can you afford to lose, in both?",
                      humanQuestion: "Has this person kept similar commitments before?",
                      bridgeArchitecture: "AI explains the legal exposure; the decision is yours (values, family history).",
                      bridgeCheckpoint: "AI may not decide family obligations; it only describes the downside.",
                      bridgeWorkflow: "AI: liability + credit impact. You: trust + relationship.",
                      aiDistilled: "A co-signer is fully liable for the debt and it appears on your credit file.",
                      aiDetail: ["Ask for a release clause after N on-time payments", "Missed payments affect your credit too"],
                      aiEdgeCases: ["Lease renewal extends your liability"],
                      planText: "Decline politely, offer other help", alternativeText: "Co-sign with a release clause",
                      proposal: "Accept plan", proposalConfidence: 0.55, scriptedOutcome: "Hold — gather info", hardTrigger: nil, demoSplit: .too_abstract),
    ]
}
