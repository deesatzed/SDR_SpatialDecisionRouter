#!/usr/bin/env python3
"""Regenerate data/templates/case_import_template.xlsx + one CSV per sheet. ALL ROWS ARE SYNTHETIC.
Usage: python3 tools/make_case_templates.py [out_dir]"""
import csv, json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from case_schema import SHEETS, ED_OPTIONS, TELE_OPTIONS, FIN_OPTIONS, DEV_OPTIONS, AGE_BANDS  # noqa: E402

S = "synthetic"
EDQ, TQ, FQ, DQ = "ESI level?", "Disposition?", "Recommended action?", "Gate decision?"
# case_id, domain, ctx, subj, day, age, sex, cc, channel, hr, sbp, spo2, temp, pmh, presentation, agent, conf, trigger, ambiguity, notes
MED = [
 ("M001","ed_triage","ed_adult","P0001",0,"50-64","F","chest pain","walk-in",96,150,97,36.9,"diabetes;hypertension","pressure-like discomfort 2 h with nausea, no radiation","ESI 3",0.62,"","ambiguous","atypical ACS pattern"),
 ("M002","ed_triage","ed_adult","P0002",2,"18-29","F","palpitations / anxiety","walk-in",112,118,99,37.0,"anxiety","racing heart after caffeine, known panic episodes","ESI 3",0.70,"","clear",""),
 ("M003","ed_triage","ed_adult","P0003",3,"65-79","M","fall / head strike","ambulance",80,160,99,36.7,"atrial fibrillation;anticoagulant","tripped at home, struck head, no loss of consciousness","ESI 3",0.66,"anticoagulated head strike","clear",""),
 ("M004","ed_triage","ed_adult","P0004",5,"30-39","M","chest pain","walk-in",88,135,98,36.8,"","sharp pain worse on breathing after recent cold","ESI 3",0.72,"","clear",""),
 ("M005","ed_triage","ed_adult","P0005",6,"40-49","F","headache","walk-in",78,128,99,36.9,"migraine","typical migraine, same as prior episodes","ESI 4",0.80,"","clear",""),
 ("M006","ed_triage","ed_adult","P0006",8,"50-64","M","chest pain","ambulance",104,88,94,36.6,"smoker","crushing central pain, diaphoretic","ESI 2",0.85,"STEMI alert criteria","clear",""),
 ("M007","ed_triage","ed_adult","P0002",12,"18-29","F","palpitations / anxiety","walk-in",108,120,99,37.0,"anxiety","recurrent episode, settles with slow breathing","ESI 3",0.70,"","clear","repeat visit"),
 ("M008","ed_triage","ed_adult","P0007",15,"80-89","F","cough + fever","ambulance",118,96,91,38.9,"COPD","3 days productive cough, new confusion","ESI 3",0.58,"sepsis screen positive","clear","companion reports confusion"),
 ("M009","ed_triage","ed_peds","P0008",20,"5-12","M","abdominal pain","walk-in",110,110,99,38.1,"","periumbilical pain migrating to right lower side","ESI 3",0.60,"","ambiguous",""),
 ("M010","ed_triage","ed_adult","P0001",40,"50-64","F","chest pain","walk-in",92,148,97,36.8,"diabetes;hypertension","fatigue and jaw ache, mild nausea","ESI 3",0.60,"","ambiguous","repeat patient; prior atypical ACS"),
 ("M011","ed_triage","ed_adult","P0002",45,"18-29","F","palpitations / anxiety","walk-in",115,116,99,37.1,"anxiety","palpitations at rest, felt faint once","ESI 3",0.65,"","ambiguous","history may mislead: new syncope"),
 ("M012","ed_triage","ed_adult","P0003",50,"65-79","M","fall / head strike","walk-in",76,158,98,36.6,"atrial fibrillation;anticoagulant","slipped, bumped forehead","ESI 3",0.64,"anticoagulated head strike","clear",""),
 ("M013","ed_triage","ed_adult","P0009",55,"30-39","M","headache","walk-in",84,170,99,37.0,"","worst headache of life, sudden onset","ESI 3",0.55,"thunderclap headache","clear","no prior history"),
 ("T001","ai_tele_doc","tele_outpatient","P0010",1,"30-39","F","urinary symptoms","video",None,None,None,None,"recurrent UTI","dysuria 2 days, no fever","treat remotely",0.80,"","clear","no vitals (omission)"),
 ("T002","ai_tele_doc","tele_outpatient","P0011",4,"40-49","F","GLP-1 weight-loss request","async",None,None,None,None,"","requests semaglutide, BMI band 30-35","treat remotely",0.70,"","ambiguous","pregnancy intent said differently"),
 ("T003","ai_tele_doc","tele_outpatient","P0012",7,"50-64","M","erectile dysfunction — PDE5 request","async",None,None,None,None,"angina","requests sildenafil","treat remotely",0.74,"nitrate interaction risk","clear","meds said wrong"),
 ("T004","ai_tele_doc","tele_outpatient","P0013",10,"65-79","M","medication refill","video",72,None,None,None,"hypertension","needs refill of BP medicine, home readings 130s","treat remotely",0.85,"","clear",""),
 ("T005","ai_tele_doc","tele_outpatient","P0014",14,"18-29","M","sore throat / sinus — wants antibiotics","async",None,None,None,None,"","3 days sore throat, no fever, wants antibiotics","treat remotely",0.75,"","clear","supportive care, no antibiotics"),
 ("T006","ai_tele_doc","tele_outpatient","P0010",18,"30-39","F","urinary symptoms","video",None,None,None,None,"recurrent UTI","dysuria again, third episode this year","treat remotely",0.78,"","ambiguous","needs culture"),
 ("T007","ai_tele_doc","tele_outpatient","P0015",22,"40-49","F","menopause — HRT request","video",None,None,None,None,"migraine with aura","hot flashes, poor sleep","treat remotely",0.70,"","ambiguous",""),
 ("T008","ai_tele_doc","tele_outpatient","P0010",35,"30-39","F","urinary symptoms","video",None,None,None,38.6,"recurrent UTI","dysuria, now fever and flank pain","treat remotely",0.70,"fever + flank pain","clear","history may mislead: escalation"),
 ("T009","ai_tele_doc","tele_outpatient","P0011",38,"40-49","F","GLP-1 weight-loss request","async",None,None,None,None,"","asks again, now says not trying to conceive","treat remotely",0.70,"","ambiguous","repeat"),
 ("T010","ai_tele_doc","tele_outpatient","P0012",42,"50-64","M","erectile dysfunction — PDE5 request","async",None,None,None,None,"angina","asks again for PDE5 inhibitor","treat remotely",0.74,"","clear","meds not said this time"),
 ("T011","ai_tele_doc","tele_outpatient","P0016",48,"30-39","M","testosterone request","video",None,None,None,None,"","wants testosterone therapy, no labs on file","treat remotely",0.60,"","ambiguous","no prior history"),
]
# case_id, domain, ctx, subj, day, topic, presentation, agent, conf, trigger, ambiguity, extra
NON = [
 ("F001","personal_finance","pf_investing","U0001",0,"concentration","move whole emergency fund into one growth stock","proceed with changes",0.55,"irreversible move >50% of liquid savings","clear",{"pct_liquid":100}),
 ("F002","personal_finance","pf_saving","U0001",6,"automation","set up automatic 10% savings transfer","proceed",0.90,"","clear",{"pct_income":10}),
 ("F003","personal_finance","pf_debt","U0002",3,"balance transfer","consolidate two cards via 0% intro balance transfer","proceed",0.70,"","ambiguous",{"fee_pct":3}),
 ("F004","personal_finance","pf_liability","U0003",9,"co-sign","co-sign a relative's car loan","proceed with changes",0.50,"third-party liability","clear",{}),
 ("F005","personal_finance","pf_debt","U0002",14,"balance transfer","second balance transfer before intro period ends","proceed",0.70,"","clear",{"fee_pct":3}),
 ("F006","personal_finance","pf_budget","U0004",18,"subscriptions","cancel unused subscriptions flagged by bank feed","proceed",0.85,"","clear",{"count":4}),
 ("F007","personal_finance","pf_investing","U0001",33,"concentration","move retirement account into crypto after a market dip","proceed with changes",0.55,"irreversible move >50% of liquid savings","clear",{"pct_liquid":70}),
 ("F008","personal_finance","pf_debt","U0002",36,"balance transfer","third balance transfer in a year","proceed",0.70,"","ambiguous",{"fee_pct":4}),
 ("F009","personal_finance","pf_liability","U0003",40,"lend","lend a relative a lump sum, no written terms","proceed with changes",0.50,"","ambiguous",{"pct_liquid":30}),
 ("D001","devsecops","ci_gate","R0001",1,"dependency","minor dependency bump, all tests pass","merge",0.90,"","clear",{"lines":12}),
 ("D002","devsecops","ci_gate","R0002",4,"tls","PR disables TLS certificate verification in HTTP client","request changes",0.60,"security control disabled","clear",{"lines":3}),
 ("D003","devsecops","ci_gate","R0001",8,"migration","agent-authored migration drops a column","merge",0.70,"irreversible data change","clear",{"lines":40}),
 ("D004","devsecops","ci_gate","R0003",11,"refactor","1200-line refactor with no test changes","merge",0.65,"","ambiguous",{"lines":1200}),
 ("D005","devsecops","ci_gate","R0001",16,"docs","docs-only change","merge",0.95,"","clear",{"lines":30}),
 ("D006","devsecops","ci_gate","R0002",21,"egress","adds outbound network call to an unknown host","request changes",0.60,"new network egress","clear",{"lines":25}),
 ("D007","devsecops","ci_gate","R0001",31,"migration","agent-authored migration renames a table","merge",0.70,"irreversible data change","clear",{"lines":35}),
 ("D008","devsecops","ci_gate","R0002",37,"cors","PR relaxes CORS to allow any origin","request changes",0.60,"","clear",{"lines":2}),
 ("D009","devsecops","ci_gate","R0003",44,"refactor","large refactor, coverage unchanged","merge",0.65,"","ambiguous",{"lines":900}),
]
# outcomes: case_id -> (value, source, offset, severity)
OUT = {
 "M001":("ESI 2","chart_review",2,"major"),"M002":("ESI 4","chart_review",1,"minor"),"M003":("ESI 2","chart_review",1,"critical"),
 "M004":("ESI 3","chart_review",1,"none"),"M005":("ESI 4","chart_review",1,"none"),"M006":("ESI 1","chart_review",0,"critical"),
 "M007":("ESI 4","chart_review",1,"minor"),"M008":("ESI 2","discharge_summary",3,"critical"),"M009":("ESI 3","chart_review",1,"none"),
 "M010":("ESI 2","chart_review",2,"major"),"M011":("ESI 3","chart_review",2,"major"),"M012":("ESI 2","chart_review",1,"critical"),
 "M013":("ESI 2","chart_review",1,"critical"),
 "T001":("treat remotely","followup_call",3,"none"),"T002":("decline request","followup_call",7,"major"),"T003":("in-person visit","chart_review",2,"critical"),
 "T004":("treat remotely","followup_call",14,"none"),"T005":("treat remotely","followup_call",5,"none"),"T006":("in-person visit","lab_result",4,"minor"),
 "T007":("in-person visit","chart_review",10,"major"),"T008":("send to ED","discharge_summary",1,"critical"),"T009":("in-person visit","followup_call",7,"major"),
 "T010":("in-person visit","chart_review",3,"critical"),"T011":("in-person visit","chart_review",10,"major"),
 "F001":("pause and review","user_followup",30,"major"),"F002":("proceed","bank_statement",30,"none"),"F003":("proceed with changes","bank_statement",30,"minor"),
 "F004":("decline","user_followup",60,"major"),"F005":("proceed with changes","bank_statement",30,"minor"),
 "F007":("pause and review","user_followup",30,"major"),"F008":("proceed with changes","bank_statement",30,"minor"),"F009":("decline","user_followup",60,"major"),
 "D001":("merge","ci_result",1,"none"),"D002":("escalate to security","incident_report",2,"critical"),"D003":("request changes","post_merge_review",1,"major"),
 "D004":("request changes","post_merge_review",3,"minor"),"D005":("merge","ci_result",0,"none"),"D006":("escalate to security","incident_report",2,"critical"),
 "D007":("request changes","post_merge_review",1,"major"),"D008":("escalate to security","incident_report",3,"critical"),"D009":("request changes","post_merge_review",3,"minor"),
}  # F006 intentionally has no outcome yet (omission)
# prior HITM responses on train cases: case_id -> (answer, role, split, latency, tag)  (M009 intentionally none: omission)
RESP = {
 "M001":("ESI 2","nurse","about_right",8400,"atypical_presentation"),"M002":("ESI 4","nurse","buried_me",5200,"known_benign_pattern"),
 "M003":("ESI 2","nurse","about_right",3100,"hard_trigger"),"M004":("ESI 3","nurse","about_right",2900,"agree"),
 "M005":("ESI 4","physician","about_right",2500,"agree"),"M006":("ESI 1","physician","about_right",1800,"hard_trigger"),
 "M007":("ESI 4","nurse","overstepped_me",4100,"known_benign_pattern"),"M008":("ESI 2","nurse","about_right",3600,"hard_trigger"),
 "T001":("treat remotely","clinician","about_right",3000,"agree"),"T002":("decline request","physician","about_right",9100,"said_differently_on_purpose"),
 "T003":("in-person visit","physician","about_right",4200,"hard_trigger"),"T004":("treat remotely","clinician","buried_me",2200,"agree"),
 "T005":("treat remotely","clinician","about_right",2600,"agree"),"T006":("in-person visit","clinician","too_abstract",6100,"recurrence"),
 "T007":("treat remotely","clinician","",5000,"agree"),
 "F001":("pause and review","self","overstepped_me",12000,"hard_trigger"),"F002":("proceed","self","about_right",1500,"agree"),
 "F003":("proceed with changes","advisor","buried_me",7000,"fees"),"F004":("decline","advisor","about_right",9000,"hard_trigger"),
 "F005":("proceed with changes","self","about_right",4000,"fees"),"F006":("proceed","self","about_right",1200,"agree"),
 "D001":("merge","engineer","about_right",900,"agree"),"D002":("escalate to security","security_reviewer","about_right",2100,"hard_trigger"),
 "D003":("request changes","engineer","about_right",3300,"hard_trigger"),"D004":("request changes","engineer","overstepped_me",5400,"no_tests"),
 "D005":("merge","engineer","about_right",600,"agree"),"D006":("escalate to security","security_reviewer","about_right",2500,"hard_trigger"),
}
# T007 human answer is wrong vs outcome on purpose (human errors exist; history must be graded, not trusted)
FIELDS = [
 ("M001","meds","metformin","metformin","confirmed","patient"),("M001","symptoms","mild","nausea and diaphoresis","said_wrong","patient"),
 ("M003","meds","blood thinner","anticoagulant","confirmed","record"),("M008","symptoms","just a cough","confusion","said_wrong","patient"),
 ("M008","symptoms","confused since yesterday","confusion","confirmed","companion"),("M011","substance","","energy drinks daily","not_said","patient"),
 ("M013","substance","none","none","confirmed","patient"),("T001","allergies","NKDA","NKDA","confirmed","patient"),
 ("T002","pregnancy","not planning","trying to conceive","said_differently","patient"),("T003","meds","none","nitrate","said_wrong","patient"),
 ("T006","adherence","finished course","stopped early","said_wrong","patient"),("T007","symptoms","hot flashes","hot flashes","confirmed","patient"),
 ("T008","symptoms","mild","fever and flank pain","said_wrong","patient"),("T009","pregnancy","not trying to conceive","","said_differently","patient"),
 ("T010","meds","","nitrate","not_said","patient"),("T011","substance","none","","confirmed","patient"),
 ("F003","income","stable","stable","confirmed","bank_feed"),("F004","obligations","none","existing car loan","said_wrong","self_report"),
 ("F006","subscriptions","2","4","said_wrong","self_report"),("F009","written_terms","yes","","said_differently","self_report"),
 ("D004","tests_added","yes","no","said_wrong","pr_description"),("D007","reversible","yes","no","said_wrong","pr_description"),
 ("D008","scope","internal only","public endpoint","said_wrong","pr_description"),
]

def rows():
    med = []
    for r in MED:
        cid, dom = r[0], r[1]
        opts = ED_OPTIONS if dom == "ed_triage" else TELE_OPTIONS
        med.append(dict(case_id=cid, source=S, domain=dom, context_id=r[2], subject_key=r[3], day_offset=r[4], age_band=r[5], sex=r[6],
                        chief_complaint=r[7], channel=r[8], hr=r[9], sbp=r[10], spo2=r[11], temp_c=r[12], pmh=r[13], presentation=r[14],
                        question=EDQ if dom == "ed_triage" else TQ, options=";".join(opts), agent_proposal=r[15], agent_confidence=r[16],
                        hard_trigger=r[17], ambiguity=r[18], notes=r[19]))
    non = []
    for r in NON:
        dom = r[1]; opts = FIN_OPTIONS if dom == "personal_finance" else DEV_OPTIONS
        non.append(dict(case_id=r[0], source=S, domain=dom, context_id=r[2], subject_key=r[3], day_offset=r[4], topic=r[5], presentation=r[6],
                        question=FQ if dom == "personal_finance" else DQ, options=";".join(opts), agent_proposal=r[7], agent_confidence=r[8],
                        hard_trigger=r[9], ambiguity=r[10], extra_json=json.dumps(r[11]) if r[11] else ""))
    cases = {c["case_id"]: c for c in med + non}
    resp = []
    for i, (cid, (ans, role, split, lat, tag)) in enumerate(RESP.items(), 1):
        c = cases[cid]
        dec = "escalate" if c["hard_trigger"] and ans != c["agent_proposal"] else ("pass" if ans == c["agent_proposal"] else "modify")
        resp.append(dict(response_id=f"R-{i:03d}", source=S, case_id=cid, subject_key=c["subject_key"], reviewer_role=role,
                         human_decision=dec, human_answer=ans, split_rating=split, latency_ms=lat, rationale_tag=tag))
    out = [dict(outcome_id=f"O-{i:03d}", source=S, case_id=cid, outcome_value=v, outcome_source=s, observed_offset_days=o, severity_if_wrong=sev)
           for i, (cid, (v, s, o, sev)) in enumerate(OUT.items(), 1)]
    fr = [dict(case_id=a, source=S, field=b, reported_value=c, true_value=d, reliability_state=e, info_source=f) for a, b, c, d, e, f in FIELDS]
    return {"Cases_Medical": med, "Cases_NonMedical": non, "Prior_Responses": resp, "Outcomes": out, "Field_Reliability": fr}

README = [
 "SDR case-import template — ALL EXAMPLE ROWS ARE SYNTHETIC. Not real patients, users or repositories.",
 "Purpose: import faux or PHI-cleaned cases + prior HITM responses + observed outcomes to measure case-based learning (with-history vs no-history).",
 "De-identification (HIPAA Safe Harbor, 45 CFR 164.514(b)(2)): remove all 18 identifiers — names; geography smaller than a state (incl. street, city, ZIP); all date elements except year (we use NO dates: day_offset only) and ages >89 (use 90+); phone; fax; email; SSN; MRN; health plan no.; account no.; certificate/license no.; vehicle IDs/plates; device IDs/serials; URLs; IP addresses; biometrics; full-face photos; any other unique code. Keys must be synthetic (P0001, U0001, R0001) and not derived from real IDs.",
 "Time: day_offset = days since that subject's first event in this file; observed_offset_days = days after the case. Never real dates.",
 "Free text (presentation, notes, pmh, values) is scanned by tools/import_cases.py; names, dates, phone, email, MRN/long numbers, SSN, street addresses, URLs, IPs and ZIPs are rejected.",
 "Linking: Prior_Responses, Outcomes and Field_Reliability join to cases by case_id; subject_key links visits of the same person/user/repo over time.",
 "Run: python3 tools/import_cases.py data/templates/case_import_template.xlsx --split --out build/case_experiment ; then python3 tools/case_learning_eval.py build/case_experiment",
]

def write(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    data = rows()
    for sheet, rs in data.items():
        cols = list(SHEETS[sheet])
        with open(os.path.join(out_dir, f"{sheet}.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
            for r in rs:
                w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in cols})
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook(); ws = wb.active; ws.title = "README"
    for line in README:
        ws.append([line])
    ws.append([]); ws.append(["sheet", "column", "required", "allowed / type", "description"])
    for c in ws[ws.max_row]: c.font = Font(bold=True)
    for sheet, cols in SHEETS.items():
        for col, (req, allowed, desc) in cols.items():
            ws.append([sheet, col, "required" if req else "optional", ", ".join(allowed) if isinstance(allowed, list) else allowed, desc])
    ws.append([]); ws.append(["age_band values", ", ".join(AGE_BANDS)])
    ws.column_dimensions["A"].width = 22; ws.column_dimensions["B"].width = 22; ws.column_dimensions["E"].width = 90
    for sheet, rs in data.items():
        s = wb.create_sheet(sheet); cols = list(SHEETS[sheet]); s.append(cols)
        for c in s[1]:
            c.font = Font(bold=True); c.fill = PatternFill("solid", fgColor="FFE8CC" if SHEETS[sheet][c.value][0] else "EEEEEE")
        for r in rs:
            s.append([r.get(k) for k in cols])
        s.freeze_panes = "A2"
    wb.save(os.path.join(out_dir, "case_import_template.xlsx"))
    return {k: len(v) for k, v in data.items()}

if __name__ == "__main__":
    print(write(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "data", "templates")))
