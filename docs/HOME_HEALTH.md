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

**Pass** accepts the route. **Modify…** opens the other three routes. This decision is a category, so Flip is not offered. Passing `urgent_page` sends the handoff to the Urgent page node.

## Layout in the simulator (focus tunnel)

While a case is open, the near field is the decision. Status and the queue sit off to the side until you tap **Show**.

| Layer | What you should see |
|---|---|
| Near, center | `HomeHealthNowFace`: case id, colored route chip, one reason line, the action, then **Pass ✓** / **Modify…**. Priority, the wait chip, and the bridge/params line are not on this face. **Details** still opens the vignette and the Layer 1 rule. |
| Mid-left | `BoardView.homeStatus`: a strip with large **Reviewed**, **Alerts**, and **Corrections**. **Show** brings the log forward. The strip grows and pulses only when Alerts or Corrections are above zero. Opening **Details** parks the strip back so the vignette can sit on the left. |
| Mid-right | `UpNextStrip.homeQueue`: up to four fat chips (case id + route). **Show** adds the one-line reason. No priority float. |
| Far | Input node **Layer 1** is larger and shows the current reason. **Route desk** and **Urgent page** stay smaller and dimmer, and light up when Pass would send the case there (`urgent_page` lights Urgent page). |

Views and placement to check after a Mac rebuild: `HomeHealthNowFace` and `HomeHealthRouteChip` in `HomeHealthDomain.swift`; `CrossroadsView.layoutHomeFocus` / `layoutHomeNodes`, `AgentCard.homeNode`, `BoardView.homeStatus`, `UpNextStrip.homeQueue` in `RouterViews.swift`. `RouterEngine.highlightedDest` is display-only. Pass, Modify, and the bridge are unchanged.

`xcodegen generate` is only needed if you regenerate the project. `tools/homehealth_vision.sh` is still the one-shot simulator launch. This VM cannot run the visionOS simulator, so confirm the layout there.

## Where the decision comes from

- **L1 live** (teal) — `homehealth/sdr_bridge` recomputed the case on this Mac.
- **L1 bundled · bridge offline** (orange) — the bridge did not answer. The card still shows the route from `homehealth_vignettes.json`, which the tests check against the same engine.

Open **Details** for the library trend, the note, the rule, and the library label. Layer 1 does not read that label.

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
