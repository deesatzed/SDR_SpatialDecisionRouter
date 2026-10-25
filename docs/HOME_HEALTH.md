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

**Log only** acknowledges a silent log: no page and no handoff. **Pass to …** sends a clinical route to the named on-call person. **Change route…** opens the other routes. This decision is a category, so Flip is not offered. Passing `urgent_page` sends the handoff to the On-call HH MD sphere. The Overseer is not that person. Those three controls are the Overseer vocabulary. Bedside and Nurse HITM do not use them.

## Review roles

One role is active at a time. The card opens as **Overseer**. Chips on the face switch to **Bedside** or **Nurse HITM** and back. The case stays put. Layer 1's route chip does not change when you switch. Leaving Home health and opening it again starts on Overseer.

Every decision writes `review_role` on the ledger context (`card_payload.review_role`): `overseer`, `bedside`, or `nurse`. Bedside and Nurse also write `review_action` (the verb id below) and set `recipient` to that action's synthetic chip. Overseer does not write `review_action`. The pass or route change is already the Overseer verb. Nothing in this build trains a model.

## Overseer role contract

The Overseer is always a physician, the regional router. Chrome reads **Overseeing · routes to on-call** and the badge reads **Physician**. Bedside and Nurse are active chips on the same row.

The Overseer does not receive the clinical work. Pass records the physician's decision and routes it to the on-call for that setting:

| Route | Recipient on the card | Sphere a Pass flies to |
|---|---|---|
| `silent_log` | Log only | On-call desk (no person tasked) |
| `nurse_task` | Night nurse | On-call desk |
| `nurse_task` when goals say hospice or comfort-focused | On-call hospice nurse | On-call desk |
| `provider_task` | On-call HH MD | On-call desk |
| `urgent_page` | On-call HH MD | On-call HH MD |

Those names are synthetic labels. They are not staff at a named health system. Layer 1 still chooses the route. The labels only say who the route is for.

Spheres stay **Overseer queue · N waiting**, **On-call desk · N sent**, and **On-call HH MD · N sent**. Pass still flies to the desk, or to On-call HH MD for a page. **This pass ·** is the same recipient chip. Log only does not page anyone.

## Bedside

Bedside is the covering clinician for **this** patient, not the multi-site router. Chrome reads **Bedside · covering clinician** and the badge reads **Clinician**. The line under the chips says you are covering this patient.

There is no **Pass to on-call HH MD** button. The green button is the verb that fits Layer 1's route. The others are always there.

| Button | When it is green | Route recorded | Recipient chip |
|---|---|---|---|
| Acknowledge & continue | `silent_log` | `silent_log` | You continue care |
| Request nurse visit | `nurse_task` | `nurse_task` | Nurse visit · Night nurse, or On-call hospice nurse when goals say hospice or comfort-focused |
| Document plan | `provider_task` | `silent_log` | Plan stays with you |
| Page on-call | `urgent_page` | `urgent_page` | Page · On-call HH MD |

`review_action` is `acknowledge_continue`, `request_nurse_visit`, `document_plan`, or `page_on_call`. A page still flies to the On-call HH MD sphere. You are not paged. A visit request flies to the care-tasks sphere (the same node as the Overseer's on-call desk). Acknowledge and Document plan stay with you and do not page.

Sphere nameplates while Bedside is selected: **Covering list**, **Care tasks**, **On-call MD**. Switching back to Overseer restores the Overseer names.

## Nurse HITM

Nurse HITM is the nursing seat. Chrome reads **Nurse HITM** and the badge reads **Nurse**. The verbs are not the Overseer pass set.

| Button | When it is green | Route recorded | Recipient chip |
|---|---|---|---|
| Schedule visit | `nurse_task` | `nurse_task` | Visit · you schedule (Hospice visit · you schedule when goals say hospice or comfort-focused) |
| Call patient | `provider_task` | `nurse_task` | Call · patient or caregiver |
| Device check | `silent_log` with a device ticket | `silent_log` | Device check · oximetry |
| Escalate to on-call MD | `urgent_page` | `urgent_page` | Escalate · On-call HH MD |
| Escalate to on-call nurse | not the default | `nurse_task` | Escalate · Night nurse, or On-call hospice nurse when goals say hospice or comfort-focused |
| Log only | `silent_log` without a device ticket | `silent_log` | Log only |

`review_action` is `schedule_visit`, `call_patient`, `device_check`, `escalate_on_call_md`, `escalate_on_call_nurse`, or `log_only`. Escalate to on-call MD flies to the On-call MD sphere. You are not that physician. Schedule, call, device check, escalate-to-nurse, and log only use the visits-and-calls sphere.

Sphere nameplates while Nurse HITM is selected: **Nurse list**, **Visits and calls**, **On-call MD**.

Patient or caregiver is a synthetic role label. It is not a name and not a phone number.

### Cascade

The case opens collapsed on awareness.

| Level | What is open |
|---|---|
| L0 Awareness | Case id, route chip, recipient chip, compressed patient chip (age band, key conditions, key meds, living, and a night SpO₂ labeled **baseline** when a pattern trigger is also on the card), the **Why now** line when this card has a pattern, then the week pattern as context, and the route controls. |
| L1 Patient details | The next few sentences, ordered for this situation, then chart sections as summaries. **Trends**, when this case has a pattern, sits here collapsed to one line. |
| L2 Rules | The rule that fired or was held, who receives it, and the oxygen, drug, goals, or device lines that apply to this patient. |
| L3 More | The note, the trend, and the library label next to Layer 1. Chart sections stay. |

Chart sections, summary first, one open at a time: PMH, meds, active problems, recent hospitalizations, baselines / bands, goals of care. Order follows this situation. Show opens a section. Hide, or Show on another section, collapses it. The side panel has a fixed height so More can scroll.

Active problems are problem-list lines that match this situation (atrial fibrillation on a blood thinner, prior stroke on a new deficit, coronary disease on a GTN case, COPD or GOLD when oxygen is the lead). If none match, the summary says none are tied to this situation. Hospitalizations use the library discharge field. In the six library cases that field is none.

### Trends

`PX-COPD-01` is a synthetic pattern fixture and the first card in the queue. It is not one of the six library cases, and Layer 1 did not compute it. The badge says **Pattern fixture**. **Why now** on the face is today’s SpO2 84% (sit up) / 85% (commode), recovered to band. The patient chip’s night SpO₂ 91 is labeled **baseline**, not the alert. **This week** under that is the pattern: eight similar alerts, mostly on position change, resting SpO2 usually in band. On Overseer the button is **Log only** (no page, no handoff). On Bedside the green button is **Acknowledge & continue**. On Nurse HITM it is **Log only**.

**Patient details** shows **Trends** collapsed to that line. **Show** opens recent alerts and actions, SpO2 and heart-rate bars (teal inside this patient’s band, orange outside it), the note that the positional-desat preference was adjusted to log only, and a longer hint: a similar rise in exertion-related alerts about three months ago came before a pneumonia admission, and today’s alerts are not that pattern. **Hide** collapses it. The same scroller still moves the rest of the dossier.

Expanded text uses one small set of colors, at full strength on the dark glass: warm orange for why-now, alerts, and readings outside the band; cool cyan for baseline and the band itself; sage for an action or a log-only note. Chart sections that are not baseline or the situation’s active problems stay white. Rule and More headings share one quiet label color.

The bars and the alert list live in `homehealth_patterns.json`. They are not Layer 1 inputs.

## Layout in the simulator (focus tunnel + cascade)

The open case starts as **awareness**: what needs you, how serious the route chip is, and where a Pass would send it. Patient details, rules, and the chart stay collapsed until you cascade.

| Layer | What you should see |
|---|---|
| Near, center | `HomeHealthNowFace` (L0). Role chips, then the active framing, case id, colored route chip, recipient chip, patient chip, and one clinical line for **this** situation (a fall on a blood thinner leads with the fall and the drug; a low oxygen reading leads with that reading). A pattern card adds **Why now** (the event) above **This week** (the pattern). Overseer keeps **Log only** or **Pass to …** and **Change route…** on this face. Bedside and Nurse HITM keep their own verbs on this face. |
| Beside, when cascaded | `HomeHealthDossier` inside a fixed-height scroller. **Patient details**, then **Rules**, then the chart. **More** adds the note and the trend. |
| Mid-left | `BoardView.homeStatus`: the active role title (**Overseer**, **Bedside**, or **Nurse HITM**), then large **Reviewed**, **Alerts**, **Corrections**. **Show** opens the log. The strip moves up while a dossier is open. It grows and pulses only when Alerts or Corrections are above zero. |
| Mid-right | `UpNextStrip.homeQueue`: fat chips (case id + route). **Show** adds the clinical line and who it would go to. No priority float. |
| Far | Three solid spheres, not a faint graph. Each nameplate is the site plus a count, large enough to read from the seat. On Overseer: **Overseer queue · N waiting**, **On-call desk · N sent**, **On-call HH MD · N sent**. Bedside and Nurse HITM rename those same three objects (see the role sections). The queue grows with how many cases are waiting and glows while any are waiting. A destination stays smaller until this action would send the open case there, then it grows (a page is the largest), glows, and adds **This pass ·** the synthetic recipient. Look or **Show list** opens who is waiting or who was already sent. The action still flies to that sphere. On Overseer, you are not the recipient. |

### Gestures

The visionOS simulator often does not deliver a real gaze hover. Use the buttons. Day-to-day mouse, gaze, and scale controls are in [VISIONOS_SIM_CONTROLS.md](VISIONOS_SIM_CONTROLS.md).

| Action | Result |
|---|---|
| Look at the card for about 0.4 s | Unpinned **Patient details** opens on the left. About 1.5 s also opens **Rules**. Look away and it returns to the pinned level (usually awareness). |
| **Expand** | Pins the next layer (awareness → patient details → rules). |
| **Pin** | Shows when a look has opened a layer you have not pinned yet. |
| **More for this case** | Pins More (the note and the trend). Also on the rules panel. Chart sections are already on Patient details. |
| **Collapse** | Peels one layer. **Awareness** on the row jumps straight back to the face. |
| **Log only** / **Pass to …** / **Change route…** | Overseer only. Stay on the face at every layer. **Log only** does not page anyone. **Pass to …** names the on-call recipient. Neither sends the case to the Overseer. |
| Bedside / Nurse verbs | Replace the Overseer buttons while that role is selected. Expand, Collapse, and Patient details stay. |

Ordering is `HomeHealthBrief` in `HomeHealthDomain.swift`. It scores facts from the case fields already on the vignette (note, trend, meds, problems, goals, baseline, rule, reason). It does not use one who / problems / meds template for every card. A fall plus an anticoagulant leads with the fall, the drug, and the bleed lines in the note, then the other problems. An oxygen case leads with the Day 0 reading, then that patient's baseline `spo2_night_min`, then the human note. Home oxygen, GOLD, or a commode desaturation leads when those words are in the case text.

Views to check after a Mac rebuild: `HomeHealthNowFace`, `HomeHealthDossier`, `HomeHealthChart`, `HomeHealthTrends`, `HomeHealthBrief`, `HomeHealthInk`, `HomeHealthSeat`, `HomeHealthRole`, `HomeHealthVocabulary`; `AgentCard.homeNode`; `CrossroadsView.layoutHomeFocus`, `layoutHomeNodes`, and `nodeRestScale`; `SidePanel.homeCascade` (the scroller); `RouterEngine.homeSetRole` / `homeCascade` / `homeCollapse` / `homeChartToggle`. Layer 1's route choice and the bridge are unchanged.

`xcodegen generate` is only needed if you regenerate the project. `tools/homehealth_vision.sh` is still the one-shot simulator launch. This VM cannot run the visionOS simulator, so confirm the layout there.

## Where the decision comes from

- **L1 live** (teal) — `homehealth/sdr_bridge` recomputed the case on this Mac.
- **L1 bundled · bridge offline** (orange) — the bridge did not answer. The card still shows the route from `homehealth_vignettes.json`, which the tests check against the same engine.

**More for this case** has the full note, the trend, and the library label next to the Layer 1 route. Layer 1 does not read that label.

## Run on the visionOS Simulator (Mac)

Requirements: macOS, Xcode 27, the visionOS 27 simulator runtime, Python 3. `xcodegen` if you regenerate the project. From the repo root. Pointer, gaze, and scale controls are in [VISIONOS_SIM_CONTROLS.md](VISIONOS_SIM_CONTROLS.md).

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

The test fails if the committed snapshot drifts from the engine or from the library fact text. Do not hand-edit clinical numbers in the vignette file. `homehealth_patterns.json` is a display fixture and is not part of that snapshot.

## Role switcher check (simulator)

This VM cannot boot the visionOS simulator. On a Mac, after `tools/homehealth_vision.sh`:

1. Home health opens on Overseer. Chips read Overseer, Bedside, Nurse HITM. None say Later. Only Overseer is filled.
2. Framing is **Overseeing · routes to on-call**. Badge is **Physician**. Buttons are **Log only** or **Pass to …** and **Change route…**. PX-COPD-01 still leads with **Why now**, and **Patient details → Trends** still opens.
3. Spheres read Overseer queue, On-call desk, On-call HH MD. **This pass ·** matches the recipient chip. Pass does not page you.
4. Tap Bedside. The Overseer chip clears and Bedside fills. Framing becomes **Bedside · covering clinician**. Buttons are Acknowledge & continue, Request nurse visit, Document plan, Page on-call. There is no Pass to on-call HH MD.
5. Tap Nurse HITM. Buttons are Schedule visit, Call patient, Device check, Escalate to on-call MD, Escalate to on-call nurse, Log only. Chrome says Nurse HITM.
6. Tap Overseer again. The pass buttons and sphere names return. Expand still says **Patient details**.
7. Decide one case in each role. Export. Each line's `card_payload.review_role` is the seat you used. Bedside and Nurse lines also have `review_action`.

## Later, not this build

Repos worth another look, and what not to integrate, are in [Consider4LaterDev.md](Consider4LaterDev.md) (scan date 25 October 2026). None of them are wired into the Overseer.
