"""Normalize casegen outputs (A: other prompt, B: our prompt) into
 1) runner JSON for run_decisions.py (id, kind, expected, lines, key_line; days=None -> fly gate needs its own mapping)
 2) SDR import CSVs matching data/templates/Cases_Medical.csv and Outcomes.csv headers.
artifact_flags are EXCLUDED from model-visible lines by default (several name the answer, e.g. 'optical_pigmentation_overestimation').
A's router_input is not used (it restates labels/diagnoses and adds facts absent from structured fields).
Smart triggers (SMART_TRIGGERS.md; v1.5 adds escalation_target, route_basis, secondary_triggers to the runner JSON and notes; a pending secondary CONFIRM_FIRST makes severity at least major): if a case has trigger_tier, runner JSON carries the trigger fields; Outcomes severity_if_wrong = critical
for ABSOLUTE/CONFIRM_FIRST cases (a miss is a critical miss); Cases_Medical notes carry the tier and v2.3 baseline_layer; drift_not_absorbed -> severity major. Old behaviour: convert_casegen_v2.1.py."""
import json, csv, sys
WITH_FLAGS = "--with-flags" in sys.argv
CM = "case_id,source,domain,context_id,subject_key,day_offset,age_band,sex,chief_complaint,channel,hr,sbp,spo2,temp_c,pmh,presentation,question,options,agent_proposal,agent_confidence,hard_trigger,ambiguity,notes".split(",")
OC = "outcome_id,source,case_id,outcome_value,outcome_source,observed_offset_days,severity_if_wrong".split(",")
def meds(c):
    out=[]
    for m in c["meds"]:
        s=f'{m["name"]} {m["dose"]}'
        if m.get("started_day") is not None: s+=f' (since Day {m["started_day"]})'
        out.append(s)
    for m in c["recent_med_changes"]: out.append(f'{m["name"]}: {m["change"]} (Day {m["day"]})')
    return "; ".join(out) or "none"
def lines(c):
    b=c["baseline_30d"]; q=c["data_quality"]
    hdr=f'SYNTHETIC FIXTURE. Age {c["age_band"]} {c["sex"]}, lives {c["living"]}. Skin tone: {c.get("skin_tone_note") or "unknown"}. PMH: {", ".join(c["pmh"])}. Meds: {meds(c)}. Devices: {", ".join(c["devices"])}.'
    if c.get("patient_goals"): hdr+=f' Goals: {c["patient_goals"]}.'
    base="30-day baseline: "+", ".join(f"{k}={v}" for k,v in b.items() if v is not None and k!="baseline_window_days")+"."
    dqs=f'Wear time 7d: {q["wear_time_pct_7d"] if q["wear_time_pct_7d"] is not None else "n/a"}%, missing hours last 48: {q["missing_hours_last_48"] if q["missing_hours_last_48"] is not None else "n/a"}.'
    if WITH_FLAGS and q["artifact_flags"]: dqs+=" Device flags: "+"; ".join(q["artifact_flags"])+"."
    note="Caregiver/nurse note: "+(c["caregiver_or_nurse_note"] or "none received.")
    return [hdr, base, "Last 7 days: "+c["trend_last_7d"], dqs, note]
runner=[]; cm=[]; oc=[]
SOURCES_DEFAULT=[("A","A_otherprompt.json","llm1","other"),("B","B_ourprompt.json","llm1","ours"),("C","llm2/C_otherprompt.json","llm2","other"),("D","llm2/D_ourprompt.json","llm2","ours"),("E","llm3/E_otherprompt.json","llm3","other"),("F","llm3/F_ourprompt.json","llm3","ours")]
# optional CLI: --source TAG=path:llm:prompt (repeatable) and --out-prefix PREFIX (default "casegen_")
_src=[a.split("=",1)[1] for a in sys.argv if a.startswith("--source=")]
SOURCES=[(x.split("=",1)[0],)+tuple(x.split("=",1)[1].split(":")) for x in _src] or SOURCES_DEFAULT
OUTP=next((a.split("=",1)[1] for a in sys.argv if a.startswith("--out-prefix=")), "casegen_")
REQ=["case_id","age_band","sex","living","pmh","meds","recent_med_changes","devices","baseline_30d","trend_last_7d","caregiver_or_nurse_note","data_quality","expected_route","acceptable_alternates","hard_trigger","difficulty","category","rationale","decisive_feature"]
ROUTES={"silent_log","nurse_task","wake_specialist","escalate_human"}
rejected=[]
for tag,fn,llm,prompt in SOURCES:
    _d = json.load(open(fn))
    for c in (_d["cases"] if isinstance(_d, dict) else _d):
        bad=[k for k in REQ if k not in c] + ([] if c.get("expected_route") in ROUTES else ["expected_route"])
        if bad: rejected.append((tag,c.get("case_id"),bad)); continue
        cid=f'{tag}-{c["case_id"]}'; L=lines(c)
        runner.append(dict(id=cid, src=tag, llm=llm, prompt=prompt, kind=c["category"][0], expected=c["expected_route"], acceptable=c["acceptable_alternates"],
            hard_trigger=c["hard_trigger"], hard_trigger_rule=c.get("hard_trigger_rule"), trigger_tier=c.get("trigger_tier"), confirm_step=c.get("confirm_step"),
            confirm_timeout_min=c.get("confirm_timeout_min"), suppression_reason=c.get("suppression_reason"), baseline_layer=c.get("baseline_layer"), baseline_status=c.get("baseline_status"), escalation_target=c.get("escalation_target"), route_basis=c.get("route_basis"), secondary_triggers=c.get("secondary_triggers"), difficulty=c["difficulty"], pair_id=c["pair_id"] and f'{tag}-{c["pair_id"]}', lines=L, key_line=2, days=None))
        b=c["baseline_30d"]
        cm.append(dict(case_id=cid, source="synthetic", domain="home_wearable", context_id="eldercare_home", subject_key=cid, day_offset=0,
            age_band=c["age_band"], sex=c["sex"], chief_complaint=c["category"][0], channel="remote_monitoring", hr=b.get("rest_hr"), sbp=b.get("sbp",""),
            spo2=b.get("spo2_night_min"), temp_c="", pmh=";".join(c["pmh"]), presentation=" ".join(L[2:]), question="Route?",
            options="silent_log;nurse_task;wake_specialist;escalate_human", agent_proposal="", agent_confidence="",
            hard_trigger=c["decisive_feature"] if c["hard_trigger"] else "", ambiguity=c["difficulty"], notes=f'casegen {tag} {llm} {prompt}-prompt' + (f' | trigger {c.get("hard_trigger_rule")} {c["trigger_tier"]}' + (f' confirm={c.get("confirm_step")}/{c.get("confirm_timeout_min")}min' if c["trigger_tier"]=="CONFIRM_FIRST" else '') + (f' suppressed={c.get("suppression_reason")}' if c["trigger_tier"]=="SUPPRESSED" else '') if c.get("trigger_tier") else '') + (f' | layer {c["baseline_layer"]}' if c.get("baseline_layer") else '') + (f' | target {c["escalation_target"]}' if c.get("escalation_target") else '') + (f' | basis {c["route_basis"]}' if c.get("route_basis") else '') + ''.join(f' | secondary {t.get("hard_trigger_rule")} {t.get("trigger_tier")}' + (f' confirm={t.get("confirm_step")}/{t.get("confirm_timeout_min")}min' if t.get("trigger_tier")=="CONFIRM_FIRST" else '') + (f' suppressed={t.get("suppression_reason")}' if t.get("trigger_tier")=="SUPPRESSED" else '') for t in (c.get("secondary_triggers") or []))))
        oc.append(dict(outcome_id=f"O-{cid}", source="synthetic", case_id=cid, outcome_value=c["expected_route"], outcome_source="author_label",
            observed_offset_days=0, severity_if_wrong="critical" if c.get("trigger_tier") in ("ABSOLUTE","CONFIRM_FIRST") else ("major" if c["expected_route"]=="escalate_human" or c.get("baseline_layer")=="drift_not_absorbed" or any(t.get("trigger_tier") in ("ABSOLUTE","CONFIRM_FIRST") for t in (c.get("secondary_triggers") or [])) else "minor")))
json.dump(runner, open(OUTP+"runner.json","w"), indent=1)
for name,hdr,rows in ((OUTP+"Cases_Medical.csv",CM,cm),(OUTP+"Outcomes.csv",OC,oc)):
    with open(name,"w",newline="") as f: w=csv.DictWriter(f,hdr); w.writeheader(); w.writerows(rows)
import collections
print("rejected:", rejected or "none")
print("by src:", dict(collections.Counter(r["src"] for r in runner)), "| by llm:", dict(collections.Counter(r["llm"] for r in runner)), "| by prompt:", dict(collections.Counter(r["prompt"] for r in runner)))
print("routes:", dict(collections.Counter(r["expected"] for r in runner)), "| hard_trigger:", sum(r["hard_trigger"] for r in runner), "| tiers:", dict(collections.Counter(r["trigger_tier"] for r in runner if r["trigger_tier"])))
print("runner cases:", len(runner), "| Cases_Medical rows:", len(cm), "| Outcomes rows:", len(oc))
