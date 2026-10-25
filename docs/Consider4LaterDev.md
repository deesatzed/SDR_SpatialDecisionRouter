# Consider for later development

Scan date: 25 October 2026. These are external Vision Pro repositories worth another look. None of them are dependencies of the Spatial Decision Router, and none should be bolted into the Overseer.

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
