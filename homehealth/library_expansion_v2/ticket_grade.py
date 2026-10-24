"""Blind device-ticket grading pass (SYNTHETIC). The v1.3 grader output has no ticket field, so the same grader model (gemini-4-argon)
gives a blind ticket opinion from the case facts only (no answer fields) under the v1.13 device-ticket addendum. Never prints the key."""
import json, os, glob, threading
import run_lx2 as R
rl = R.rl; from orcall import parse_json
SYS = ("You are the case grader for a home-health monitoring library. For each case decide, BLIND, whether a device ticket should be filed and which type, "
       "using ONLY the rules below. Reply with JSON only: {\"tickets\": [{\"case_id\": ..., \"expected_device_ticket\": \"device_maintenance\"|\"supply_reference_oximeter_and_baseline\"|\"ecg_strip_request\"|null, \"reason\": \"<one sentence>\"}]}\n\n"
       + open("ADDENDUM_v113.md").read() + "\nAlso from the v1.11.2 addendum: two devices on the same vital disagreeing with no acute signs -> ticket (device_maintenance | supply_reference_oximeter_and_baseline | ecg_strip_request).")
FIELDS = ["case_id", "age_band", "sex", "living", "pmh", "meds", "recent_med_changes", "devices", "baseline_30d", "trend_last_7d", "caregiver_or_nurse_note", "data_quality"]
def run(b):
    out = f"grade/{b}.tickets.json"
    if os.path.exists(out): return
    cs = [{k: c.get(k) for k in FIELDS} for c in json.load(open(f"gen/{b}.batch.json"))["cases"]]
    for a in range(3):
        r = rl.call(f"ticketgrade {b} try{a+1}", rl.GRADER, SYS, json.dumps({"cases": cs}), 12000, 0.2)
        obj, how = parse_json(r["content"])
        if isinstance(obj, dict) and len(obj.get("tickets", [])) >= len(cs):
            json.dump(obj, open(out, "w"), indent=1); rl.log(f"TICKETGRADE {b}: ok"); return
        rl.log(f"TICKETGRADE {b} bad parse={how} err={r['error']}")
if __name__ == "__main__":
    ts = [threading.Thread(target=run, args=(b,)) for b in ("LX9", "LX10", "LX11", "LX12")]; [t.start() for t in ts]; [t.join() for t in ts]
    rl.log(f"TICKETGRADE END spend=${rl.STATE['spend']:.3f}")
