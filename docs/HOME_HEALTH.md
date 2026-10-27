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

Every decision writes `review_role` on the ledger context (`card_payload.review_role`): `overseer`, `bedside`, or `nurse`. Bedside and Nurse also write `review_action` (the verb id below) and set `recipient` to that action's synthetic chip. An ordinary Overseer Pass or Log only does not write `review_action`. The pass or route change is already the Overseer verb. Overseer does write `review_action` for three coordination verbs: `voi_wait`, `revisit_prior`, and `human_after_refusal`. Every decision also writes the retained differential, the goals constraint, and whether the agent refused. The rollup that later phases can read is in [HOME_HEALTH_INTELLIGENCE.md](HOME_HEALTH_INTELLIGENCE.md). Nothing in this build trains a model.

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

The far objects are small beacons. Pass still flies to the desk, or to On-call HH MD for a page. The reading sits on the mid node in that spoke: **This pass ·** the same recipient chip when that beacon is the lit target. Log only does not page anyone.

## Bedside

Bedside is the covering clinician for **this** patient, not the multi-site router. Chrome reads **Bedside · covering clinician** and the badge reads **Clinician**. The line under the chips says you are covering this patient.

There is no **Pass to on-call HH MD** button. The green button is the verb that fits Layer 1's route. The others are always there.

| Button | When it is green | Route recorded | Recipient chip |
|---|---|---|---|
| Acknowledge & continue | `silent_log` | `silent_log` | You continue care |
| Request nurse visit | `nurse_task` | `nurse_task` | Nurse visit · Night nurse, or On-call hospice nurse when goals say hospice or comfort-focused |
| Document plan | `provider_task` | `silent_log` | Plan stays with you |
| Page on-call | `urgent_page` | `urgent_page` | Page · On-call HH MD |

`review_action` is `acknowledge_continue`, `request_nurse_visit`, `document_plan`, or `page_on_call`. **Wait for …** is also on this face (`review_action` `voi_wait`). A page still flies to the On-call HH MD sphere. You are not paged. A visit request flies to the care-tasks sphere (the same node as the Overseer's on-call desk). Acknowledge and Document plan stay with you and do not page. A wait stays on the desk, shows the time left, and does not page. If that window passes with no observation, the case comes back to Now. It does not auto-pass. When goals are comfort-focused or do-not-hospitalize, the green verb for an urgent or provider proposal is **Request nurse visit**, and the page button stays available with the goals line on the face.

Mid-node titles while Bedside is selected: **Covering list**, **Care tasks**, **On-call MD**. The far beacons stay small. Switching back to Overseer restores the Overseer titles.

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

`review_action` is `schedule_visit`, `call_patient`, `device_check`, `escalate_on_call_md`, `escalate_on_call_nurse`, or `log_only`. **Wait for …** is also on this face (`review_action` `voi_wait`). Escalate to on-call MD flies to the On-call MD sphere. You are not that physician. Schedule, call, device check, escalate-to-nurse, log only, and a wait use the visits-and-calls sphere. The wait shows the time left. Past that window, the case comes back to Now and does not auto-pass. When goals are comfort-focused or do-not-hospitalize, the green verb for an urgent or provider proposal is **Escalate to on-call nurse**.

Mid-node titles while Nurse HITM is selected: **Nurse list**, **Visits and calls**, **On-call MD**. The far beacons stay small.

Patient or caregiver is a synthetic role label. It is not a name and not a phone number.

### Cascade

The case opens collapsed on awareness.

| Level | What is open |
|---|---|
| L0 Awareness | Case id, route chip, recipient chip, compressed patient chip (age band, key conditions, key meds, living, and a night SpO₂ labeled **baseline** when a pattern trigger is also on the card), then **Still open** (the retained differential and a confidence line, in lilac, separate from why-now and from the baseline chip). An **Act under uncertainty** line appears when the route is required before that list closes. **Why now** stays the triggering event. **This week** stays the pattern. A falsified prior reads Prior → new evidence → Revise. **Goals of care** is one line on this face. The route controls, **Wait for … · window**, and **Revise prior** (when a prior decision was falsified) stay here. An overdue wait adds an orange **OVERDUE** line above Why now. |
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
| Near, center | `HomeHealthNowFace` (L0). Role chips, then the active framing, case id, colored route chip, recipient chip, patient chip, **Still open**, then one clinical line for **this** situation (a fall on a blood thinner leads with the fall and the drug; a low oxygen reading leads with that reading). A pattern card adds **Why now** (the event) above **This week** (the pattern). Goals sit under that. Overseer keeps **Log only** or **Pass to …**, **Change route…**, and **Wait for … · window** on this face. Bedside and Nurse HITM keep their own verbs, plus the same wait. The on-call desk's mid-spoke reads **Held · Wait for … · 4h left** while the window is open, and the case returns to Now as **OVERDUE** when it expires. **Revise prior** appears when new evidence falsifies the last decision. A red **Agent refused** banner means the human chooses and the card will not auto-pass. |
| Beside, when cascaded | `HomeHealthDossier` inside a fixed-height scroller. **Patient details**, then **Rules**, then the chart. **More** adds the note and the trend. |
| Mid-left | `BoardView.homeStatus`: the active role title (**Overseer**, **Bedside**, or **Nurse HITM**), then large **Reviewed**, **Alerts**, **Corrections**. **Show** opens the log. The strip moves up while a dossier is open. It grows and pulses only when Alerts or Corrections are above zero. |
| Mid-right | `UpNextStrip.homeQueue`: fat chips (case id + route). **Show** adds the clinical line and who it would go to. No priority float. |
| On the spokes | A small glass card on the line between the NOW card and each beacon. Queue side: the next waiting case id and a one-line why-now, plus a second line when that case is a refusal or a falsified prior. Destination side: **This pass ·** the recipient when that node is the lit target, otherwise the last case sent there. A page that fights stated goals adds **Goals constrain this page**. A wait in flight reads **Held ·** and paints the desk teal. A colored pip (red page, orange task, teal log) marks the lit target. Patient chip, Trends, and Rules stay on the face cascade. |
| Far | Three small beacons, not billboards. Color and a glow mark the queue and the lit pass target. A page beacon is the largest of the three and still small. The action still flies to that beacon. On Overseer, you are not the recipient. |

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

Views to check after a Mac rebuild: `HomeHealthNowFace`, `HomeHealthMind`, `HomeHealthDossier`, `HomeHealthChart`, `HomeHealthTrends`, `HomeHealthBrief`, `HomeHealthInk`, `HomeHealthSeat`, `HomeHealthRole`, `HomeHealthVocabulary`; `AgentCard.homeNode`; `CrossroadsView.layoutHomeFocus`, `layoutHomeNodes`, `homeMidPosition`, and `nodeRestScale`; `SidePanel.homeCascade` (the scroller); `RouterEngine.homeSetRole` / `homeCascade` / `homeCollapse` / `homeChartToggle`. Layer 1's route choice and the bridge are unchanged.

`xcodegen generate` is only needed if you regenerate the project. `tools/homehealth_vision.sh` is still the one-shot simulator launch. This VM cannot run the visionOS simulator, so confirm the layout there.

## Where the decision comes from

- **L1 live** (teal) — `homehealth/sdr_bridge` recomputed the case on this Mac.
- **L1 bundled · bridge offline** (orange) — the bridge did not answer. The card still shows the route from `homehealth_vignettes.json`, which the tests check against the same engine.

**More for this case** has the full note, the trend, and the library label next to the Layer 1 route. Layer 1 does not read that label.

## Run on the visionOS Simulator (Mac)

Requirements: macOS, Xcode 27, the visionOS 27 simulator runtime, Python 3. `xcodegen` if you regenerate the project. From the repo root. Pointer, gaze, and scale controls are in [VISIONOS_SIM_CONTROLS.md](VISIONOS_SIM_CONTROLS.md).

```bash
xcodegen generate
python3 -m pytest -q homehealth/sdr_bridge/test_sdr_bridge.py homehealth/sdr_bridge/test_hitm_intelligence.py

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
python3 -m pytest -q homehealth/sdr_bridge/test_sdr_bridge.py homehealth/sdr_bridge/test_hitm_intelligence.py
```

The test fails if the committed snapshot drifts from the engine or from the library fact text. Do not hand-edit clinical numbers in the vignette file. `homehealth_patterns.json` is a display fixture and is not part of that snapshot.

## Role switcher check (simulator)

This VM cannot boot the visionOS simulator. On a Mac, after `tools/homehealth_vision.sh`:

1. Home health opens on Overseer. Chips read Overseer, Bedside, Nurse HITM. None say Later. Only Overseer is filled.
2. Framing is **Overseeing · routes to on-call**. Badge is **Physician**. Buttons are **Log only** or **Pass to …** and **Change route…**. PX-COPD-01 still leads with **Why now**, and **Patient details → Trends** still opens.
3. Far beacons are small. The queue spoke shows the next case id and a one-line why-now, not the patient chip. The lit destination spoke shows **This pass ·** the same recipient as the card, with a colored pip. Pass does not page you.
4. Tap Bedside. The Overseer chip clears and Bedside fills. Framing becomes **Bedside · covering clinician**. Buttons are Acknowledge & continue, Request nurse visit, Document plan, Page on-call. There is no Pass to on-call HH MD.
5. Tap Nurse HITM. Buttons are Schedule visit, Call patient, Device check, Escalate to on-call MD, Escalate to on-call nurse, Log only. Chrome says Nurse HITM.
6. Tap Overseer again. The pass buttons and mid-node titles return. Expand still says **Patient details**. Trends still open only from that cascade.
7. Decide one case in each role. Export. Each line's `card_payload.review_role` is the seat you used. Bedside and Nurse lines also have `review_action`. Overseer lines have `review_action` when you waited, revised, or decided after a refusal.
8. On `PX-COPD-01`, **Still open** is lilac and **Why now** is orange. **Wait for resting SpO2 back in band · 2h** is on the face.
9. On `PX-REVISE-01`, the face and the queue spoke show Prior → new evidence → Revise. **Revise prior** on Overseer opens **Change route…**. The decision logs `revisit` `1`.
10. On `PX-REFUSE-01`, the banner is **Agent refused. You choose.** Pass and the role verbs remain. Export shows `agent_refused` `1`.
11. On `PX-DNH-01`, the goals line says she would refuse hospital. The page button reads **· goals constrain**. Bedside's green button is **Request nurse visit**.
12. On `PX-WAIT-01`, **Wait for temperature and resting SpO2 over 6 hours · 6h** logs `voi_wait`, `voi_wait_minutes` `360`, and a deadline. The page beacon stays dark. The desk reads **Held · … · 6h left**. At the default clock, one sim-minute is about one real second, so that 6h window is about six minutes of simulator time and a 10m spray wait is about ten seconds. When the window passes with no new observation, the case returns to Now with an orange **OVERDUE** line. You still choose. It does not page and it does not auto-pass.

## Medical intelligence on the card

The coordination-layer read is [HOME_HEALTH_INTELLIGENCE.md](HOME_HEALTH_INTELLIGENCE.md) (Liu et al. 2026). In the simulator, after `tools/homehealth_vision.sh`:

| What you should see | Where |
|---|---|
| **Still open** lists more than one explanation. Lilac. It is not the orange **Why now** line and not the cyan baseline on the patient chip. | Every L0 card, including the six library cases. `PX-COPD-01` favors positional desaturation and still lists infection and device artifact. |
| **Act under uncertainty** when a route is required before that list closes. | `HK6-007` (new deficit), `LX4-009` (angina), `NV6-001` (hospice fall), `PX-REVISE-01`, `PX-DNH-01`. A cleared artifact such as `ST1-002` does not show it. |
| **Prior → new evidence → Revise**, and the **Revise prior** button. The next decision logs `revisit` `1`. Overseer `review_action` is `revisit_prior`. Bedside and Nurse keep their verb and set `revisit`. | `PX-REVISE-01`, second card. The queue spoke repeats the same line. |
| **Wait for … · window** names the observation, a timer, and the route that would flip. The decision logs `review_action` `voi_wait`, `voi_observation`, `voi_flip_route`, `voi_flip_if`, `voi_wait_minutes`, and `voi_wait_deadline` (domain-clock minutes) plus `voi_wait_deadline_iso`. The desk shows the time left. Past the window, the case returns to Now, logs `voi_recheck` / `voi_wait_overdue`, and does not page or auto-pass. | Every role, every card. `PX-WAIT-01` is 6h. A chest-pain spray wait is 10m. Text with no number gets a visible default (10m, 30m, 2h, or 4h). |
| Red **Agent refused. You choose.** Log only, Pass, and the role verbs stay. The card does not auto-pass. The log has `agent_refused` `1` and, once you decide, `review_action` `human_after_refusal` on Overseer. | `PX-REFUSE-01`. The queue spoke says **Agent refused · you choose**. |
| Goals line on the face. Comfort or do-not-hospitalize turns a page button orange and adds **· goals constrain**. Bedside's green verb becomes **Request nurse visit**. Nurse HITM's green verb becomes **Escalate to on-call nurse**. The route chip stays what was proposed. The log has `goals_constraint`, `goals_kind`, `goals_blocks_escalation`. | `NV6-001` and `PX-DNH-01`. The lit page spoke adds **Goals constrain this page**. |
| Outcome scores and the Overseer rollup. | `python3 -m pytest -q homehealth/sdr_bridge/test_hitm_intelligence.py`. Rollup: `python3 homehealth/sdr_bridge/learning_export.py <decisions.jsonl> -o rollup.json`. |

`card_payload` keys for later training: `review_role`, `review_action`, `uncertainty_differential`, `uncertainty_confidence`, `act_under_uncertainty`, `agent_refused`, `refusal_reason`, `revisit`, `prior_decision`, `new_evidence`, `voi_observation`, `voi_flip_route`, `voi_flip_if`, `voi_wait_minutes`, `voi_wait_deadline`, `voi_wait_deadline_iso`, `voi_wait_overdue`, `voi_recheck`, `goals_constraint`, `goals_blocks_escalation`, `goals_kind`.

## Later, not this build

Repos worth another look, and what not to integrate, are in [Consider4LaterDev.md](Consider4LaterDev.md) (scan date 25 October 2026). None of them are wired into the Overseer. The medical-intelligence slices above are in this build. They are not in that later list.
