# Spatial Decision Router — AI Doc Review (visionOS)

> **Research prototype. All encounters are synthetic. Every risk-engine parameter is `source: placeholder` and the numbers are only illustrative. Not for clinical use.**

AI "doctors" now take histories and draft plans at scale. In this setting the main failure mode is usually bad *information*, not bad medicine. Patients leave things out, get things wrong, or sometimes tell a different story on purpose. **Spatial Decision Router** puts a physician, the *human-in-the-middle* (HITM), at the crossroads between narrow decision agents. Each AI decision arrives as a card, and the physician can **Pass**, **Flip** (for binary decisions) or **Change** (to pick another category) with no typing. Each decision is logged as it happens, so the fine-tune data comes from live supervision rather than biased retrospective labeling.

Landing page: https://deesatzed.github.io/SDR_SpatialDecisionRouter/

| | |
|---|---|
| ![Crossroads](screens/30_crossroads_live.small.jpg) *The immersive crossroads: agents, handoffs and the live board.* | ![Card](screens/36_card.small.jpg) *Encounter card: the proposal, confidence, why it was queued, and trust chips.* |
| ![Reliability](screens/32_reliability_ifwrong.small.jpg) *Per-field reliability states and the if-wrong risk range.* | ![Ask next](screens/32_ask_next.small.jpg) *Value-of-information: the next question worth asking.* |
| ![Hard trigger](screens/32_hard_trigger.small.jpg) *Hard escalation trigger (MI, stroke, unstable vitals or AMS).* | ![Board](screens/36_board_enlarged.small.jpg) *Enlargeable Encounter Review board: progress and results.* |

## What it does
- **Review queue.** One physician supervises many AI encounters. Confident, clean items auto-pass, and a sample of those goes to spot-check. Everything else is queued with *why-queued* reason chips. Cards expand to show detail and prior history.
- **Field reliability, in 4 states:** *Reliable*, *Not said* (omission), *Said wrong*, and *Said differently on purpose* (`Core/ReliabilityKit.swift`). Context such as a companion present, an interpreter, an adolescent, low literacy or an elderly patient living alone changes how far the app trusts each field. That uncertainty is carried into the differential and the disposition.
- **If-wrong risk ranges.** Each field shows the worst case if it turns out to be false. Examples: an undisclosed pregnancy with a teratogen, methadone plus a QT-prolonging drug, or a nitrate taken with a PDE5 inhibitor.
- **Value of information (VOI).** The app suggests the next question for the AI to ask, ranked by expected loss reduction.
- **Hard escalation triggers.** Only unambiguous MI/STEMI, stroke, unstable vitals or AMS force immediate escalation.
- **Presentations:**
  - ED: chest pain, abdominal pain, head injury, and infection/antibiotics.
  - Outpatient AI-doc requests: URI/antibiotics, medication refills (including *labs first* when monitoring is overdue), GLP-1 weight loss, menopausal HRT, testosterone, and erectile dysfunction (PDE5).
- **Queue simulation.** An in-app discrete-event model of ED crowding, rooms and inpatient beds (`Domains/EDTriage/EDCapacity.swift`). Each decision captures a snapshot of the current capacity.
- **Evolving categories.** The HITM can propose a new category. Categories go through trial, promotion and relegation, and each site keeps its own set (`Core/CategoryRegistry.swift`).

## Architecture
```
SpatialDecisionRouter/            visionOS 27 app (SwiftUI + RealityKit, ImmersiveSpace)
  Core/        DomainKit · RouterEngine · CategoryRegistry · RoutingDecision · ReliabilityKit · ReviewKit · RouterViews · ProceduralEnvironment
  Domains/     EDTriage/ (EDTriageDomain, EDCapacity, EDReview)   AIDocReview/ (AIDocReviewDomain, OutpatientSpec, RiskClient, EncounterImporter)
UITests/                          XCUITest (real button taps, demo polish)
risk_engine/                      pyAgrum Bayesian-network sidecar + params.yaml + pytest
tools/  demo.sh · to_training.py
docs/   ADDING_A_DOMAIN.md · AI_DOC_REVIEW.md · RISK_ENGINE.md · DEMO_SCRIPT.md · index.html (landing page)
screens/                          screenshots, sample routing logs, demo.mp4
```
- **The domain framework is pluggable.** A domain supplies items, agents, categories and views through `DomainKit`. `RouterEngine` runs the handoffs, and every Pass/Flip/Change is recorded as a `RoutingDecision`. To add a new domain, such as DevSecOps, follow [docs/ADDING_A_DOMAIN.md](docs/ADDING_A_DOMAIN.md).
- **Bayesian risk sidecar** ([docs/RISK_ENGINE.md](docs/RISK_ENGINE.md)):
  - There is one discrete BN per complaint, solved with exact pyAgrum LazyPropagation.
  - Hidden truths are linked to reported, hedge, record and ask signals through noisy-OR concealment and recall.
  - Context nodes and `dx_*` nodes feed `critical` and `critical_esc`.
  - It serves `127.0.0.1:8765` with `GET /health` and `/params`, plus `POST /assess`, `/voi` and `/sample`.
  - The app calls `/assess` with a 0.8 s timeout. If the sidecar can't be reached, the app falls back to Swift heuristics, and the card badge reads `fallback`.
- **Training export.** `tools/to_training.py` converts routing logs (JSONL/JSON) into chat-style fine-tune examples. Overrides are upweighted. Trial-category routes are flagged and excluded from ground-truth accuracy.

## Quickstart
Requirements: macOS with Xcode 27, the visionOS 27 simulator runtime, xcodegen, and Python 3.
```bash
xcodegen generate
xcodebuild -scheme SpatialDecisionRouter -destination 'platform=visionOS Simulator,name=SDR-VisionPro' -derivedDataPath build build
risk_engine/run_sidecar.sh          # optional; creates .venv, serves 127.0.0.1:8765
tools/demo.sh                       # sidecar + simulator + app in demo mode
tools/demo.sh --auto                # auto-plays the 6 scripted steps
tools/demo.sh --auto --record 185   # also records screens/demo.mp4
```
A 3–5 minute talk track is in [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md). The app also accepts the launch flags `-demo`, `-noSidecar` and `-forceTrigger`.

Export the training data:
```bash
python3 tools/to_training.py screens/32_routing_log.jsonl -o out/
```

## Tests
```bash
cd risk_engine && .venv/bin/python -m pytest -q       # BN engine
xcodebuild test -scheme SpatialDecisionRouter -destination 'platform=visionOS Simulator,name=SDR-VisionPro'   # UI tests
```

## Disclaimer
This is a research and demo prototype. Every patient and encounter is synthetic. The Bayesian parameters are placeholders that have not been reviewed by experts or clinically validated. The UI shows categorical labels, and the digits are illustrative. Do not use it for clinical decisions.
