# Home health on visionOS

The **Home health** domain reviews Layer 1 smart-trigger routes on synthetic library cases. ED triage is a separate domain and is unchanged.

Layer 1 (homehealth v1.14.4, params `0.14.4-placeholder`) proposes one of:

| Route | Meaning |
|---|---|
| `silent_log` | Log only. No human task. |
| `nurse_task` | Nurse contact within about 24 h (same-shift hospice nurse when goals say so). |
| `provider_task` | Same-business-day review. Not a page. |
| `urgent_page` | Page someone now. |

A `device_maintenance` ticket is shown when Layer 1 files one. Clinical routes do not keep a ticket. The headset does not call OpenRouter or any other cloud model. Jev is not called.

The six cases are copied from the synthetic library (fact text only):

| Case | Layer 1 route | Device ticket |
|---|---|---|
| ST1-002 | `silent_log` | none |
| LX12-007 | `silent_log` | `device_maintenance` (poor-contact resting SpO2 cleared by a fingertip reading) |
| LX12-008 | `urgent_page` | none (same family as LX12-007; the fingertip reading stays low) |
| NV6-001 | `nurse_task` | none |
| LX4-009 | `provider_task` | none |
| HK6-007 | `urgent_page` | none |

**Record log** / **Pass to …** accepts the route and sends it to the named on-call person. **Change route…** opens the other routes. This decision is a category, so Flip is not offered. Passing `urgent_page` sends the handoff to the On-call HH MD sphere. The Overseer is not that person.

## Overseer role contract

Home health in this app is one role: **Overseer**. The Overseer is always a physician. Bedside and Nurse HITM are visible on the card as **Later** and do nothing yet. One role is active at a time. A switcher can come later. It is not built here.

The Overseer does not receive the clinical work. Pass records the physician's decision and routes it to the on-call for that setting:

| Route | Recipient on the card | Sphere a Pass flies to |
|---|---|---|
| `silent_log` | Log only | On-call desk (no person tasked) |
| `nurse_task` | Night nurse | On-call desk |
| `nurse_task` when goals say hospice or comfort-focused | On-call hospice nurse | On-call desk |
| `provider_task` | On-call HH MD | On-call desk |
| `urgent_page` | On-call HH MD | On-call HH MD |

Those names are synthetic labels. They are not staff at a named health system. Layer 1 still chooses the route. The labels only say who the route is for.

Every Pass and route change is written to the existing decision ledger (`downstreamPreview` names the recipient, and the case context includes `review_role: overseer`). That log is for later training phases. Nothing in this build trains a model.

### Cascade

The case opens collapsed on awareness.

| Level | What is open |
|---|---|
| L0 Awareness | Case id, route chip, recipient chip, compressed patient chip (age band, key conditions, key meds, living and night SpO₂ when the library has them), one clinical line, and the route controls. |
| L1 Story | The next few sentences, ordered for this situation, then chart sections as summaries. |
| L2 Rules | The rule that fired or was held, who receives it, and the oxygen, drug, goals, or device lines that apply to this patient. |
| L3 More | The note, the trend, and the library label next to Layer 1. Chart sections stay. |

Chart sections, summary first, one open at a time: PMH, meds, active problems, recent hospitalizations, baselines / bands, goals of care. Order follows this situation. Show opens a section. Hide, or Show on another section, collapses it. The side panel has a fixed height so More can scroll.

Active problems are problem-list lines that match this situation (atrial fibrillation on a blood thinner, prior stroke on a new deficit, coronary disease on a GTN case, COPD or GOLD when oxygen is the lead). If none match, the summary says none are tied to this situation. Hospitalizations use the library discharge field. In this pack that field is none.

## Layout in the simulator (focus tunnel + cascade)

The open case starts as **awareness**: what needs you, how serious the route chip is, and where a Pass would send it. Story, rules, and the chart stay collapsed until you cascade.

| Layer | What you should see |
|---|---|
| Near, center | `HomeHealthNowFace` (L0). Overseer framing, case id, colored route chip, recipient chip, patient chip, one clinical line for **this** situation (a fall on a blood thinner leads with the fall and the drug; a low oxygen reading leads with that reading). **Record log** or **Pass to …** and **Change route…** stay on this face. |
| Beside, when cascaded | `HomeHealthDossier` inside a fixed-height scroller. **Story**, then **Rules**, then the chart. **More** adds the note and the trend. |
| Mid-left | `BoardView.homeStatus`: **Overseer**, then large **Reviewed**, **Alerts**, **Corrections**. **Show** opens the log. The strip moves up while a dossier is open. It grows and pulses only when Alerts or Corrections are above zero. |
| Mid-right | `UpNextStrip.homeQueue`: fat chips (case id + route). **Show** adds the clinical line and who it would go to. No priority float. |
| Far | Three spheres. **Overseer queue** grows with how many cases are waiting and lists them. **On-call desk** and **On-call HH MD** stay smaller until a Pass would send the open case there, then the lit sphere grows with urgency (a page is the largest) and the label names the recipient. Look or **Show list** opens the waiting or sent lines. |

### Gestures

The visionOS simulator often does not deliver a real gaze hover. Use the buttons.

| Action | Result |
|---|---|
| Look at the card for about 0.4 s | Unpinned **Story** opens on the left. About 1.5 s also opens **Rules**. Look away and it returns to the pinned level (usually awareness). |
| **Expand** | Pins the next layer (awareness → story → rules). |
| **Pin** | Shows when a look has opened a layer you have not pinned yet. |
| **More for this case** | Pins More (the note and the trend). Also on the rules panel. Chart sections are already on Story. |
| **Collapse** | Peels one layer. **Awareness** on the row jumps straight back to the face. |
| **Record log** / **Pass to …** / **Change route…** | Stay on the face at every layer. They name the on-call recipient. They do not send the case to the Overseer. |

Ordering is `HomeHealthBrief` in `HomeHealthDomain.swift`. It scores facts from the case fields already on the vignette (note, trend, meds, problems, goals, baseline, rule, reason). It does not use one who / problems / meds template for every card. A fall plus an anticoagulant leads with the fall, the drug, and the bleed lines in the note, then the other problems. An oxygen case leads with the Day 0 reading, then that patient's baseline `spo2_night_min`, then the human note. Home oxygen, GOLD, or a commode desaturation leads when those words are in the case text.

Views to check after a Mac rebuild: `HomeHealthNowFace`, `HomeHealthDossier`, `HomeHealthChart`, `HomeHealthBrief`, `HomeHealthSeat`; `AgentCard.homeNode`; `CrossroadsView.layoutHomeFocus` and `nodeRestScale`; `SidePanel.homeCascade` (the scroller); `RouterEngine.homeCascade` / `homeCollapse` / `homeChartToggle`. Layer 1's route choice and the bridge are unchanged.

`xcodegen generate` is only needed if you regenerate the project. `tools/homehealth_vision.sh` is still the one-shot simulator launch. This VM cannot run the visionOS simulator, so confirm the layout there.

## Where the decision comes from

- **L1 live** (teal) — `homehealth/sdr_bridge` recomputed the case on this Mac.
- **L1 bundled · bridge offline** (orange) — the bridge did not answer. The card still shows the route from `homehealth_vignettes.json`, which the tests check against the same engine.

**More for this case** has the full note, the trend, and the library label next to the Layer 1 route. Layer 1 does not read that label.

## Run on the visionOS Simulator (Mac)

Requirements: macOS, Xcode 27, the visionOS 27 simulator runtime, Python 3. `xcodegen` if you regenerate the project. From the repo root:

```bash
xcodegen generate
python3 -m pytest -q homehealth/sdr_bridge/test_sdr_bridge.py

# optional. Without it the app still shows routes, badged "bridge offline".
homehealth/sdr_bridge/run_bridge.sh
# check: curl -s http://127.0.0.1:8767/health

# one-shot: boot the simulator, build, install, open Home health
tools/homehealth_vision.sh
```

`tools/homehealth_vision.sh` uses the simulator named `SDR-VisionPro` unless `SIM_NAME` or `SIM_UDID` is set. The README quickstart uses that name. If your runtime calls it **Apple Vision Pro**, set `SIM_NAME`.

Manual launch, after a successful `xcodebuild` of scheme `SpatialDecisionRouter`:

```bash
xcodebuild -scheme SpatialDecisionRouter \
  -destination 'platform=visionOS Simulator,name=SDR-VisionPro' \
  -derivedDataPath build build

xcrun simctl boot "SDR-VisionPro"
open -a Simulator
xcrun simctl install booted build/Build/Products/Debug-xrsimulator/SpatialDecisionRouter.app
xcrun simctl launch booted com.wsatz.SpatialDecisionRouter \
  -domain home_health -autoOpenImmersive -freshRegistry
```

Or launch the app and tap **Home health** on the start screen. Do not pass `-demo` together with `-domain home_health`; demo mode selects the demo domain instead.

`-noHomeHealthBridge` skips the bridge and always uses the bundled snapshot. `HOMEHEALTH_URL` overrides the bridge address (default `http://127.0.0.1:8767`).

The visionOS simulator shares the Mac's `127.0.0.1`, so the bridge is reachable. A physical Vision Pro does not see the Mac's localhost. On device you get the bundled snapshot unless you point `HOMEHEALTH_URL` at a bridge you chose to expose. The bridge binds `127.0.0.1` unless `HOMEHEALTH_BIND` is set.

## iPad

The same sources build `SpatialDecisionRouterPad`. The start screen has **Home health**. The iPad simulator also uses `127.0.0.1:8767`.

## Regenerate the snapshot

After a Layer 1 change, from the repo root:

```bash
python3 homehealth/sdr_bridge/export_vignettes.py
python3 -m pytest -q homehealth/sdr_bridge/test_sdr_bridge.py
```

The test fails if the committed snapshot drifts from the engine or from the library fact text. Do not hand-edit clinical numbers in the vignette file.
