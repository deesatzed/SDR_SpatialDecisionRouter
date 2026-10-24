# v1.14.2 human-cause guard (SYNTHETIC, 2026-10-24)

POLICY 2 tightening per Wayne: no device ticket when a human/external cause explains the cuff or scale reading.
- Cuff: ticket withdrawn when the cuff was re-seated/repositioned/pinched or a seated-rest repeat cleared it, unless a cuff error code was shown.
- Scale: ticket withdrawn when a bag/object/person/pet was on the scale or the note says the patient was not on it; a zero/near-zero (<1 kg) reading keeps its ticket (extra weight cannot read 0 kg; library LX11-001).
- Built from library LX2-006, LX11-002, LX11-001 and synthetic vignettes (jev_baseline/test_layer1_v1142.py). Holdout text not read.

Blind re-score, stored picks, $0:
- Library tickets: 20/24 hit, wrong 2 (LX2-006, LX11-002) -> 20/24 hit, wrong 0. Routes unchanged.
- holdout_v4: tickets 2/7, unexpected HX7-002 (unchanged); routes and scores identical (default 86.8%, crit 0).
- holdout_v3: tickets 3/3, unexpected HW5-009, HW6-010, HW7-001, HW7-006 (unchanged); default 100%, crit 0.
Files: lib_after.json, v4.*, v3.*.
