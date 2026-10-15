# Case import: faux / de-identified cases for case-based-learning tests

**All template rows are synthetic.** Nothing here is a real patient, user or repository.

Goal: load cases, prior human-in-the-middle (HITM) responses and later observed outcomes, then measure how decisions
change when prior cases + prior HITM responses are available (**with_history**) vs not (**no_history**) on held-out cases.

## Files

| File | What |
|------|------|
| `data/templates/case_import_template.xlsx` | Workbook: README (field dictionary), Cases_Medical, Cases_NonMedical, Prior_Responses, Outcomes, Field_Reliability |
| `data/templates/<Sheet>.csv` | Same sheets as CSV (the importer accepts either) |
| `tools/case_schema.py` | Single source of truth for columns, required flags, allowed values |
| `tools/make_case_templates.py` | Regenerates the workbook + CSVs (`python3 tools/make_case_templates.py`) |
| `tools/import_cases.py` | Validate + PHI guard + convert + `--split` experiment |
| `tools/case_learning_eval.py` | Nearest-prior-case **baseline** (not a model) |
| `tools/tests/test_import_cases.py` | pytest: round-trip, PHI rejections, schema errors, no-leak split, eval |

## Schema summary (full dictionary is the README sheet)

- **Cases_Medical** (ED triage `M###`, AI tele-doc `T###`): `subject_key` P0001, `day_offset`, `age_band`, `sex`,
  `chief_complaint` (exact app complaint strings, incl. outpatient GLP-1 / HRT / testosterone / PDE5 / antibiotics / refill),
  `channel`, vitals `hr sbp spo2 temp_c` (blank = not measured), `pmh` (`;`-list), `presentation`, `question`, `options`,
  `agent_proposal`, `agent_confidence`, `hard_trigger`, `ambiguity`, `notes`.
  Options: ED `ESI 1..ESI 5`; tele-doc `treat remotely; in-person visit; send to ED; decline request`.
- **Cases_NonMedical** (personal finance `F###`, DevSecOps PR gate `D###`; `N###` reserved): generic columns + `topic` +
  `extra_json` (domain-specific JSON object). Options: finance `proceed; proceed with changes; pause and review; decline`;
  DevSecOps `merge; request changes; block; escalate to security`.
- **Prior_Responses**: `response_id`, `case_id`, `subject_key`, `reviewer_role` (role, never a name), `human_decision`
  (pass/modify/flip/escalate/wait), `human_answer`, `split_rating`, `latency_ms`, `rationale_tag`.
- **Outcomes**: `case_id`, `outcome_value` (the option that was right in hindsight), `outcome_source`, `observed_offset_days`,
  `severity_if_wrong` (none/minor/major/critical).
- **Field_Reliability**: `case_id`, `field`, `reported_value`, `true_value`, `reliability_state`
  (`confirmed` / `not_said` / `said_wrong` / `said_differently` = on purpose), `info_source`. Medical fields use the app's
  names (pregnancy, meds, substance, allergies, symptoms, safety, adherence, sexual) and map to `ReliabilityState`.

Example data covers repeat subjects over time (P0001 atypical chest pain twice, P0010 recurrent UTI that later needs the ED,
U0002 serial balance transfers, R0001 repeat risky migrations), hard triggers, ambiguous cases, a human answer that the
outcome proved wrong (T007), a case where history misleads (M011), a case with no response (M009) and one with no outcome (F006).

## De-identification rules

Use only synthetic data or data de-identified under HIPAA **Safe Harbor** (45 CFR 164.514(b)(2)) or expert determination.
Safe Harbor removes the 18 identifiers of the person and relatives/employers/household:

1. Names 2. Geography smaller than a state (street, city, county, ZIP; first 3 ZIP digits only if area >20,000 people)
3. All date elements except year (and ages >89 → "90+") 4. Phone 5. Fax 6. Email 7. SSN 8. Medical record numbers
9. Health-plan beneficiary numbers 10. Account numbers 11. Certificate/license numbers 12. Vehicle IDs / plates
13. Device IDs / serials 14. URLs 15. IP addresses 16. Biometric IDs 17. Full-face photos 18. Any other unique code.

House rules on top: **no dates at all** (relative `day_offset` only), ages as bands, synthetic keys not derived from real IDs,
amounts as bands or percentages, `source` = `synthetic` or `deidentified` on every row.

**PHI guard** (`import_cases.py`): rejects identifier-like column names (name, mrn, dob, address, zip, phone, email, ...) and
any unknown column, and scans every cell for names (`Mr./Dr. X`, `name: X`), dates (numeric or month-name), DOB/birth,
phone, email, SSN, MRN/account wording, 7+ digit numbers, street addresses, ZIP codes, URLs, IPs and exact ages over 89.
Any hit stops the import with row + column; nothing is written. It is a pattern guard, **not** a guarantee: a human still
reviews free text before import of anything that started as real data.

## Run

```bash
python3 tools/import_cases.py data/templates/case_import_template.xlsx --validate-only
python3 tools/import_cases.py data/templates/case_import_template.xlsx --split --export --out build/case_experiment
python3 tools/case_learning_eval.py build/case_experiment --json build/case_experiment/eval.json
```

Outputs in `--out`: `items/<domain>.json` (app-shaped items), `encounters.csv` (AI tele-doc app format),
`decisions_imported.jsonl` (sdr.decision.v1, `provenance=imported_unsigned`, no signature, never written to the device
ledger), `unified/` (with `--export`: SFT/preference pairs, RL reward rows, frozen replay via `unified_export.export`), and with
`--split`: `train/history.jsonl`, `train/decisions.jsonl`, `test/cases.jsonl` (blinded), `test/answers.jsonl` (held out),
`conditions/no_history.jsonl`, `conditions/with_history.jsonl`, `manifest.json` (counts, sha256 of every file).
Split is temporal: train = `day_offset < --cutoff` (default 30), test = the rest. Responses on test cases are dropped and
listed in the manifest so they cannot leak.

## App hook

- **AI tele-doc**: launch with `-importCSV <out>/encounters.csv`, or copy it to the app's Documents as `encounters.csv`
  (existing `EncounterImporter`). Age bands are sent as band midpoints because the app takes an integer age.
- **ED triage, Symbiosis personal finance, DevSecOps**: `items/<domain>.json` is the hook; the app does not load it yet
  (TODO: a `-importItems <path>` flag in each domain's seed loader). DevSecOps is not an app domain yet.

## Baseline eval (honest)

`case_learning_eval.py` compares, on the same held-out cases: **no_history** = the agent's own proposal and confidence;
**with_history** = the outcome (or human answer) of the most similar prior case in the domain
(0.5 same subject + 0.3 same complaint/topic + 0.2 word overlap, threshold 0.5), else the agent proposal. It reports accuracy,
Brier score and critical misses overall and for repeat-subject, hard-trigger, ambiguous and per-domain slices, and lists cases
where history hurt. It is a baseline, not a learned model. On the template the agent proposals were authored to be wrong on
most test cases, so the gap mostly reflects how the example was written; treat it as a smoke test until real
de-identified data is loaded.
