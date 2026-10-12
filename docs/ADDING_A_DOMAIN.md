# Adding a domain

The crossroads engine (`SpatialDecisionRouter/Core/`) knows nothing about any specific field. A domain is a
plug-in made of **one JSON config + one Swift module** under `SpatialDecisionRouter/Domains/<Name>/`.
ED triage (`Domains/EDTriage/`) is the reference implementation. Example of a future domain name:
`DevSecOpsTickets` (incoming security/ops tickets) — not implemented, used below only as a naming example.

## What the core provides (do not modify for a new domain)
- Spatial router: source/destination node tiers, handoff volumes, priority-ordered slots, hub travel, receive pulse.
- Gestures/buttons: tap = pass, hold/“Change…” = option ring (with “New…” and trial picks), drag/“Flip” = binary flip.
- Dependency graph: links with `dependsOn` are emitted only after their dependencies are routed and delivered.
- Category registry per `siteId` (base set from config → trial → main → dormant; merge/split; versioned history).
- Guardrail: trial categories never fire alerts or change routing (effective answer = agent proposal).
- Logging: `RoutingDecision` JSONL with generic `context`, `history`, `capacity`, `upstream`, registry version, site.
- Export (`Documents/exports/`), board shell, procedural environment themed from config, `tools/to_training.py`.

## Checklist
1. **Config** `Domains/<Name>/<id>.domain.json` (see `DomainConfig` in `Core/DomainKit.swift`):
   - [ ] `id`, `title`, `synthetic`, `defaultSite`
   - [ ] `terminology` (itemNoun, boardTitle, completedLabel, historyLabel, capacityLabel, syntheticBanner)
   - [ ] `agents`: decision agents `tier: 0`, destinations `tier: 1` (keep ≤ 6 + ≤ 4 so all fit in view)
   - [ ] `links`: one per narrow decision — `answerType` binary|category, base `options` (registry seed),
         `dependsOn`, `firesAlert` + `alertNegative`, `costWeight` (priority surfacing), `shortLabel`
   - [ ] `rulesTable`: human-readable ground-truth rules (documentation; exported with logs)
   - [ ] `capacity`: numeric parameters for your queue model
   - [ ] `theme`: sky/floor/grid/panel/trim colors
   - [ ] `testNewCategories` (optional): names the test driver uses for “New…”
2. **Module** `Domains/<Name>/<Name>Domain.swift` — a class conforming to `DomainModule`:
   - [ ] `reset(seed:)`, `advance(minutes:)` — seeded generator + your world/capacity simulation
   - [ ] `nextItem()` → `DomainItem` (fields dict, displayLine, shortLine, historyLine, arrivalTime)
   - [ ] `propose(item:link:routed:)` — narrow, deliberately imperfect agent heuristics
   - [ ] `groundTruth(item:link:routed:)` — rule hooks implementing `rulesTable` (may read capacity)
   - [ ] `complete(item:effective:)`, `alertFired(item:link:)` — world effects of routed answers
   - [ ] `capacitySnapshot()`, `capacityLine()`, `boardMetrics(_:)`, `breakdown()`
3. **Register** the module in `DomainCatalog.all` (`Core/DomainKit.swift`). The board shows “Next Domain”.
4. **Run** `xcodegen generate`, build, launch with `-autoOpenImmersive -autoResolve 60 -speedup 2`.
5. **Verify** logs (`Documents/routing_log.jsonl`) and `python3 tools/to_training.py <log> -o out`.

## Skeleton
```swift
@MainActor final class DevSecOpsTicketsDomain: DomainModule {      // example name only
    let config = (try? DomainLoader.config(named: "devsecops.domain"))!
    private(set) var now: Double = 0
    var minutesPerSecond: Double { config.capacity["minutesPerSecond"] ?? 1 }
    private var rng = SplitMix64(s: 1); private var queue: [DomainItem] = []
    func reset(seed: UInt64) { rng = SplitMix64(s: seed); now = 0; queue = [] }
    func advance(minutes: Double) { now += minutes /* arrivals + capacity model */ }
    func nextItem() -> DomainItem? { queue.isEmpty ? nil : queue.removeFirst() }
    func propose(item: DomainItem, link: LinkSpec, routed: [String: String]) -> Proposal { Proposal(answer: link.options[0], confidence: 0.7) }
    func groundTruth(item: DomainItem, link: LinkSpec, routed: [String: String]) -> String? { nil }
    func complete(item: DomainItem, effective: [String: String]) {}
    func alertFired(item: DomainItem, link: LinkSpec) {}
    func capacitySnapshot() -> [String: String] { [:] }
    func capacityLine() -> String { "" }
    func boardMetrics(_ s: EngineStats) -> [MetricValue] { [] }
    func breakdown() -> [(String, Int)] { [] }
}
```
```json
{ "id": "devsecops", "title": "Ticket Crossroads", "terminology": {"itemNoun": "ticket", "boardTitle": "Ticket Throughput"},
  "agents": [{"id": "severity", "name": "Severity Agent", "tier": 0}, {"id": "oncall", "name": "On-call", "tier": 1}],
  "links": [{"id": "severity", "source": "severity", "dest": "oncall", "question": "Severity?", "answerType": "category",
             "options": ["P1","P2","P3","P4"], "costWeight": 0.5}] }
```

## Review queue, detail panel, glossary (all generic)

The engine shows ONE large **Now** card (top of the queue), an **Up next** strip (next `review.upNextCount`),
a per-source-agent queue badge, and a side panel for **details** or the **spot-check** queue. A domain supplies:

### Config (`<domain>.domain.json`)
```json
"review": { "autoPassConfidence": 0.88, "autoPassMaxCost": 0.5, "spotCheckRate": 0.35, "waitWeight": 0.02, "upNextCount": 4 },
"detailSections": ["History", "Attachments", "Capacity snapshot"],
"glossary": { "confidence": "…", "trial category": "…", "History": "…", "my reason key": "…" },
"links": [ { "id": "triage", "...": "...", "previews": { "*": "{dest}: receives {answer}", "urgent": "{dest}: pages on-call" } } ]
```
- **Priority** = `(1 − confidence)·(1 + costWeight) + waitWeight·waitMinutes + urgency(...)`. The Now card is sticky until decided; the human can pull any Up-next item forward.
- **Auto-pass**: confidence ≥ `autoPassConfidence`, `costWeight ≤ autoPassMaxCost`, and no `.high` reason chip. A `spotCheckRate` sample is put in the spot-check queue. Logged `decidedBy: auto|human`, `spotCheckSampled`, `spotCheckResult`.
- **Glossary**: every field, chip, section title and row label is looked up by key for its hover tooltip (`.gloss(key)`).
- `"Capacity snapshot"` is a built-in section (it renders the capacity dict from emission time).

### Hooks (optional `DomainModule` requirements; defaults in `Core/ReviewKit.swift`)
```swift
func reasons(item:link:proposal:upstream:) -> [ReasonChip]   // WHY queued (text, glossary key, severity info|warn|high)
func urgency(item:link:proposal:) -> Double                  // extra priority from domain rules
func downstreamPreview(item:link:answer:) -> String?         // WHAT HAPPENS NEXT; nil → link.previews template
func detail(item:section:) -> [(String, String)]?            // rows for a detailSections title; nil → omitted
```
The engine always adds generic chips: `low confidence` (< 70%), `high error cost` (costWeight ≥ 0.7), and `waiting Nm` (or `alert waiting Nm`, which is high once ≥ 10 min).

### Logged per decision
`decidedBy`, `reasons`, `downstreamPreview`, `detailOpened`, `sectionsOpened`, `sectionDwell{section: s}`, `detailDwell`, `spotCheckSampled`, `spotCheckResult`.

### Checklist additions
- [ ] glossary covers each reason key, section title, and domain term shown on cards
- [ ] reasons() flags rule conflicts as `.high` so they are never auto-passed
- [ ] downstreamPreview() or `previews` gives a concrete effect for every option
- [ ] auto-pass threshold tuned so the human sees the uncertain/costly items (check `decidedBy` mix in the log)
