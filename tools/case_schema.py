"""Shared schema for the case-import templates (docs/CASE_IMPORT.md). One source of truth for the
template generator (make_case_templates.py), the importer (import_cases.py) and the tests."""

AGE_BANDS = ["0-1", "1-4", "5-12", "13-17", "18-29", "30-39", "40-49", "50-64", "65-79", "80-89", "90+"]
SOURCES = ["synthetic", "deidentified"]
SEX = ["F", "M", "X", "U"]
DECISIONS = ["pass", "modify", "flip", "escalate", "wait"]
SPLIT = ["about_right", "overstepped_me", "buried_me", "too_abstract", ""]
SEVERITY = ["none", "minor", "major", "critical"]
AMBIGUITY = ["clear", "ambiguous"]
RELIABILITY = ["confirmed", "not_said", "said_wrong", "said_differently"]
# maps template reliability state -> app ReliabilityState rawValue (Core/ReliabilityKit.swift)
RELIABILITY_APP = {"confirmed": "Reliable", "not_said": "Not said", "said_wrong": "Said wrong",
                   "said_differently": "Said differently on purpose"}
INFO_SOURCES = ["patient", "companion", "interpreter", "record", "device", "self_report", "bank_feed", "ci_log", "pr_description", "other"]
OUTCOME_SOURCES = ["chart_review", "followup_call", "discharge_summary", "lab_result", "bank_statement",
                   "user_followup", "incident_report", "ci_result", "post_merge_review", "synthetic_rule"]

ED_OPTIONS = ["ESI 1", "ESI 2", "ESI 3", "ESI 4", "ESI 5"]
TELE_OPTIONS = ["treat remotely", "in-person visit", "send to ED", "decline request"]
FIN_OPTIONS = ["proceed", "proceed with changes", "pause and review", "decline"]
DEV_OPTIONS = ["merge", "request changes", "block", "escalate to security"]
DOMAINS_MED = {"ed_triage": ED_OPTIONS, "ai_tele_doc": TELE_OPTIONS}
DOMAINS_NONMED = {"personal_finance": FIN_OPTIONS, "devsecops": DEV_OPTIONS}
# app DRComplaint raw values (Domains/AIDocReview/AIDocReviewDomain.swift)
COMPLAINTS = ["chest pain", "abdominal pain", "fall / head strike", "cough + fever", "urinary symptoms", "headache",
              "palpitations / anxiety", "medication refill", "sore throat / sinus — wants antibiotics",
              "GLP-1 weight-loss request", "menopause — HRT request", "testosterone request",
              "erectile dysfunction — PDE5 request"]
CHANNELS = ["walk-in", "ambulance", "video", "async", "phone", "app", "pr", "other"]
APP_FIELDS = ["pregnancy", "meds", "substance", "allergies", "symptoms", "safety", "adherence", "sexual"]

# column: (required, allowed-values or type, description)
SHEETS = {
 "Cases_Medical": {
  "case_id": (True, r"^M\d{3,}$|^T\d{3,}$", "Synthetic case key, M### (ED) or T### (tele-doc). Unique."),
  "source": (True, SOURCES, "synthetic or deidentified (Safe Harbor / expert-determined)."),
  "domain": (True, list(DOMAINS_MED), "App domain."),
  "context_id": (True, "str", "Sub-context, e.g. ed_adult, tele_outpatient."),
  "subject_key": (True, r"^P\d{4}$", "Synthetic patient key P0001. Same key = same person across visits."),
  "day_offset": (True, "int>=0", "Days since that subject's index (first) event in this dataset. No real dates."),
  "age_band": (True, AGE_BANDS, "Age band. Ages 90+ collapse to 90+ (Safe Harbor)."),
  "sex": (True, SEX, "F/M/X/U."),
  "chief_complaint": (True, COMPLAINTS, "Must match the app's complaint list exactly."),
  "channel": (True, CHANNELS, "How the case arrived."),
  "hr": (False, "int", "Heart rate, bpm. Blank = not measured (omission)."),
  "sbp": (False, "int", "Systolic BP, mmHg."),
  "spo2": (False, "int", "SpO2, %."),
  "temp_c": (False, "float", "Temperature, °C."),
  "pmh": (False, "str", "Past history, ';'-separated, coded words only."),
  "presentation": (True, "str", "Short de-identified summary. No names, dates, places, numbers that identify."),
  "question": (True, "str", "The decision being asked."),
  "options": (True, "str", "';'-separated options; the domain's standard list."),
  "agent_proposal": (True, "option", "What the AI agent recommended (one of options)."),
  "agent_confidence": (True, "prob", "Agent's stated confidence 0-1 (as reported by the agent; not calibrated)."),
  "hard_trigger": (False, "str", "Fixed escalation trigger that fires, blank if none."),
  "ambiguity": (True, AMBIGUITY, "Author's judgement of how ambiguous the case is."),
  "notes": (False, "str", "Free text for authors (still PHI-scanned)."),
 },
 "Cases_NonMedical": {
  "case_id": (True, r"^F\d{3,}$|^D\d{3,}$|^N\d{3,}$", "F### finance, D### devsecops, N### other."),
  "source": (True, SOURCES, ""),
  "domain": (True, list(DOMAINS_NONMED), "personal_finance or devsecops."),
  "context_id": (True, "str", ""),
  "subject_key": (True, r"^U\d{4}$|^R\d{4}$", "U#### user, R#### repository. Repeats across time."),
  "day_offset": (True, "int>=0", ""),
  "topic": (True, "str", "Short topic tag."),
  "presentation": (True, "str", "Summary. Amounts as bands or % of savings, never account numbers."),
  "question": (True, "str", ""),
  "options": (True, "str", "';'-separated."),
  "agent_proposal": (True, "option", ""),
  "agent_confidence": (True, "prob", ""),
  "hard_trigger": (False, "str", ""),
  "ambiguity": (True, AMBIGUITY, ""),
  "extra_json": (False, "json", "Domain-specific fields as a JSON object (e.g. {\"pct_liquid\": 60})."),
 },
 "Prior_Responses": {
  "response_id": (True, r"^R-\d{3,}$", "Unique response key."),
  "source": (True, SOURCES, ""),
  "case_id": (True, "case", "Case this HITM decision was made on."),
  "subject_key": (True, "subject", "Must match the case's subject_key."),
  "reviewer_role": (True, ["clinician", "nurse", "physician", "self", "advisor", "security_reviewer", "engineer"], "Role only, never a name."),
  "human_decision": (True, DECISIONS, "pass = agreed with agent; modify/flip = changed; escalate = trigger path."),
  "human_answer": (True, "option", "The option the human chose."),
  "split_rating": (False, SPLIT, "How well the human/AI split worked (auxiliary label)."),
  "latency_ms": (False, "int", "Time to decide."),
  "rationale_tag": (False, "str", "Short coded reason, e.g. 'atypical_presentation'."),
 },
 "Outcomes": {
  "outcome_id": (True, r"^O-\d{3,}$", ""),
  "source": (True, SOURCES, ""),
  "case_id": (True, "case", ""),
  "outcome_value": (True, "option", "The option that turned out correct in hindsight."),
  "outcome_source": (True, OUTCOME_SOURCES, "Where the truth came from."),
  "observed_offset_days": (True, "int>=0", "Days after the case when the outcome was observed."),
  "severity_if_wrong": (True, SEVERITY, "Harm if the agent's proposal had been followed and was wrong."),
 },
 "Field_Reliability": {
  "case_id": (True, "case", ""),
  "source": (True, SOURCES, ""),
  "field": (True, "str", "Field name; medical fields use the app list (pregnancy, meds, substance, allergies, symptoms, safety, adherence, sexual)."),
  "reported_value": (False, "str", "What was said. Blank when not_said."),
  "true_value": (False, "str", "What turned out true (if known)."),
  "reliability_state": (True, RELIABILITY, "confirmed / not_said / said_wrong / said_differently (on purpose)."),
  "info_source": (True, INFO_SOURCES, "Who/what reported it."),
 },
}
OPTIONS_BY_DOMAIN = {**DOMAINS_MED, **DOMAINS_NONMED}
