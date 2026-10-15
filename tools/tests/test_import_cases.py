"""Case-import tests: template round-trip, PHI guard rejections, schema errors, split/no-leak, baseline eval."""
import csv, json, os, shutil, sys
import pytest
HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.dirname(HERE))
import import_cases as ic  # noqa: E402
import case_learning_eval as ev  # noqa: E402
import make_case_templates as mk  # noqa: E402

TPL = os.path.join(HERE, "..", "..", "data", "templates")


@pytest.fixture
def tpl(tmp_path):
    d = tmp_path / "tpl"; mk.write(str(d)); return d


def edit(d, sheet, row, col, val):
    p = d / f"{sheet}.csv"
    rows = list(csv.DictReader(open(p, encoding="utf-8")))
    hdr = list(rows[0].keys())
    if col not in hdr: hdr.append(col)
    rows[row][col] = val
    os.remove(d / "case_import_template.xlsx") if (d / "case_import_template.xlsx").exists() else None
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=hdr); w.writeheader(); w.writerows(rows)


def test_committed_templates_match_generator(tpl):
    for s in ic.SHEETS:
        assert open(tpl / f"{s}.csv").read() == open(os.path.join(TPL, f"{s}.csv")).read(), s


def test_xlsx_and_csv_give_same_items(tpl, tmp_path):
    a = ic.run([str(tpl / "case_import_template.xlsx")], str(tmp_path / "a"))
    os.remove(tpl / "case_import_template.xlsx")
    b = ic.run([str(tpl)], str(tmp_path / "b"))
    assert a["cases"] == b["cases"] == 42 and a["decisions"] == b["decisions"] == 27
    ja = json.load(open(tmp_path / "a" / "items" / "ed_triage.json")); jb = json.load(open(tmp_path / "b" / "items" / "ed_triage.json"))
    assert ja == jb


def test_every_row_synthetic_and_keys_synthetic(tpl):
    d = ic.read_input([str(tpl / "case_import_template.xlsx")])
    for s in ic.SHEETS:
        assert d[s] and all(r["source"] == "synthetic" for r in d[s])
    subs = {r["subject_key"] for r in d["Cases_Medical"]}
    assert len(subs) < len(d["Cases_Medical"])  # repeat patients exist


@pytest.mark.parametrize("text,label", [
    ("pt is John Smith, Mr. Smith says", "name"), ("seen 03/14/2026 for pain", "date"), ("onset March 3rd", "date"),
    ("call 617-555-0142", "phone"), ("email jdoe@example.com", "email"), ("MRN 448812", "mrn"), ("id 12345678", "long id"),
    ("SSN 123-45-6789", "ssn"), ("lives at 42 Elm Street", "street address"), ("DOB unknown", "dob"), ("92 year old", "exact age"),
    ("see https://x.org", "url"), ("from 10.0.0.12", "ip address"), ("zip 02139", "zip"),
])
def test_phi_guard_rejects(tpl, tmp_path, text, label):
    edit(tpl, "Cases_Medical", 0, "presentation", text)
    with pytest.raises(ic.ImportError_) as e:
        ic.run([str(tpl)], str(tmp_path / "o"))
    assert "possible PHI" in str(e.value) and label.split()[0] in str(e.value).lower()
    assert not (tmp_path / "o").exists()  # nothing written


def test_identifier_column_rejected(tpl, tmp_path):
    edit(tpl, "Cases_Medical", 0, "patient_name", "x")
    with pytest.raises(ic.ImportError_, match="direct identifier"):
        ic.run([str(tpl)], str(tmp_path / "o"))


@pytest.mark.parametrize("sheet,col,val,msg", [
    ("Cases_Medical", "age_band", "47", "not allowed"), ("Cases_Medical", "subject_key", "MRN0001", "must match"),
    ("Cases_Medical", "agent_proposal", "ESI 9", "not one of the options"), ("Cases_Medical", "day_offset", "-3", "non-negative"),
    ("Cases_Medical", "agent_confidence", "1.4", "between 0 and 1"), ("Cases_Medical", "source", "real", "not allowed"),
    ("Prior_Responses", "case_id", "M999", "not found"), ("Outcomes", "outcome_value", "ESI 2", "not an option"),
    ("Field_Reliability", "reliability_state", "maybe", "not allowed"), ("Cases_NonMedical", "extra_json", "[1]", "JSON object"),
])
def test_schema_errors(tpl, tmp_path, sheet, col, val, msg):
    row = 30 if (sheet, col) == ("Outcomes", "outcome_value") else 0  # row 30 is a finance/devsecops outcome
    edit(tpl, sheet, row, col, val)
    with pytest.raises(ic.ImportError_, match=msg):
        ic.run([str(tpl)], str(tmp_path / "o"))


def test_split_no_leak_and_manifest(tpl, tmp_path):
    out = tmp_path / "x"
    r = ic.run([str(tpl / "case_import_template.xlsx")], str(out), do_split=True, export=True)
    m = json.load(open(out / "manifest.json"))
    assert m["counts"]["train_cases"] + m["counts"]["test_cases"] == 42 and m["counts"]["test_with_subject_history"] > 0
    for rel, h in m["sha256"].items():
        import hashlib
        assert hashlib.sha256(open(out / rel, "rb").read()).hexdigest() == h
    test_ids = {json.loads(l)["case"]["case_id"] for l in open(out / "test" / "cases.jsonl")}
    blob = open(out / "conditions" / "with_history.jsonl").read() + open(out / "test" / "cases.jsonl").read()
    assert "outcome_value" not in open(out / "test" / "cases.jsonl").read()
    for l in open(out / "conditions" / "with_history.jsonl"):
        row = json.loads(l)
        assert all(h["case"]["case_id"] not in test_ids for h in row["subject_history"])
    assert all(json.loads(l)["card_payload"]["case_id"] not in test_ids for l in open(out / "train" / "decisions.jsonl"))
    recs = [json.loads(l) for l in open(out / "decisions_imported.jsonl")]
    assert all(x["provenance"] == "imported_unsigned" and x["signature"] is None and x["schema"] == "sdr.decision.v1" for x in recs)
    assert r["export"]["rl_rows"] == 27 and blob


def test_encounters_csv_loads_in_app_format(tpl, tmp_path):
    ic.run([str(tpl)], str(tmp_path / "o"))
    rows = list(csv.DictReader(open(tmp_path / "o" / "encounters.csv")))
    t3 = next(r for r in rows if r["encounter_id"] == "T003")
    assert t3["stated_meds"] == "none" and t3["true_meds"] == "nitrate" and t3["hard_trigger"]
    t10 = next(r for r in rows if r["encounter_id"] == "T010")
    assert t10["stated_meds"] == "—"  # not said -> app's not-said marker


def test_baseline_eval_runs_and_is_labeled(tpl, tmp_path):
    out = tmp_path / "x"; ic.run([str(tpl)], str(out), do_split=True)
    r = ev.evaluate(str(out))
    assert r["kind"].startswith("BASELINE") and r["overall"]["no_history"]["n"] == r["overall"]["with_history"]["n"] > 0
    assert set(r["difference"]) == {"accuracy", "brier"}
