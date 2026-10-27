# Consider for later development

Scan date: 25 October 2026. These are external Vision Pro repositories worth another look. None of them are dependencies of **Spatial HITM**, and none should be bolted into the Overseer. The repo folder may still be `SpatialDecisionRouter`, and the GitHub repository may still be `SDR_SpatialDecisionRouter`, until a later rename.

## Shipped on the home-health HITM

Liu et al. 2026 (BMJ Digital Health & AI, e000395) frames six dimensions of medical intelligence. The home-health seat uses that framing as a coordination layer, not as a vignette exam. The slices below are in the app. They are not later work. The note is [HOME_HEALTH_INTELLIGENCE.md](HOME_HEALTH_INTELLIGENCE.md).

- Retained differential on L0 (**Still open**), separate from why-now and from baseline, including when the route is required before the list closes.
- **Revise prior** when new evidence falsifies a Pass or Log only, logged on the decision.
- **Wait for …** with the observation, a timer, and the route that would flip, logged as `voi_wait`. An expired window returns the case for review (`voi_recheck`) and does not page or auto-pass.
- Agent refusal that forces Overseer, Bedside, or Nurse HITM and does not auto-pass.
- Synthetic outcome scoring (route, timing, downstream utility) beside expert-consensus agreement.
- Goals of care on the Pass and page controls, logged with the decision.
- A local rollup of those logs for a later shared update (`homehealth/sdr_bridge/learning_export.py`).

## Worth attention

### [DcmVision](https://github.com/iOmega8561/DcmVision)

DICOM to 2D and 3D on visionOS (DCMTK / VTK). R&D only.

**Steal later:** how a volume or a series opens beside a decision, if imaging ever expands under More. Treat it as a pattern or an optional sidecar.

**Do not:** import it into SDR now, or send library cases through a DICOM stack.

### [c3d-sdk-visionOS](https://github.com/CognitiveVR/c3d-sdk-visionOS/)

Headset pose, a gaze proxy (forward vector), dynamic objects, and custom events.

**Steal later:** event names for look-to-cascade, dwell on a dossier section, Pass / Log only / Change route, and which sphere was looked at. Those belong in the HITM training log. Reimplementing the events in-house is enough.

**Do not:** send a real patient path through this vendor SaaS until privacy and PHI are reviewed. The synthetic pack is not that review.

## Adjacent / robotics

Different product line. Park until a teleop track exists. Not Overseer UI.

### [VisionProTeleop](https://github.com/Improbable-AI/VisionProTeleop)

Hand and head stream to Python, WebRTC, egocentric recording.

**Later, if at all:** gesture datasets, pinch-as-Pass instrumentation, a Python desk bridge. Not the review card.

### [xr_tele_locomotion](https://github.com/OmenDevs/xr_tele_locomotion)

Hand gestures and WebRTC robot locomotion. Same family as the teleop repo. Skip unless that track starts.

## Out of scope

- [awesome-testflight-link](https://github.com/pluwen/awesome-testflight-link) — TestFlight browsing only.
- [xnuimagetools](https://github.com/xsscx/xnuimagetools) — UTI and image fuzzing. No product direction.
