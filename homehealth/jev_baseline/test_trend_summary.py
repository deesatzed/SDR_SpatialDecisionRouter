"""v1.10 Jev prompt: computed 7-day trend summary (practice-style synthetic text)."""
import os
import trend_summary as S
def test_rising_hr_rr_falling_steps():
    s = S.summary("Day -6: rest HR 64, RR 15, steps 3000, weight 70.0 kg. Day -3: rest HR 66, RR 16, steps 2600. Day 0: rest HR 73, RR 18, steps 1900, weight 70.2 kg.")
    assert "HR 64 to 73 (+9 bpm, rising" in s and "RR 15 to 18 (+3/min, rising" in s
    assert "steps 3000 to 1900 (-37%, falling" in s and "weight 70.0 to 70.2 (+0.2 kg, flat" in s
def test_no_series_gives_none():
    assert S.summary("Day 0 rest HR 70.") is None
def test_prompt_v110_appends_summary_without_label_leak(monkeypatch):
    monkeypatch.setenv("JEV_PROMPT", "v1.10")
    import importlib, jev_run as J
    J = importlib.reload(J)
    c = {"id": "LIB-X", "lines": ["SYNTHETIC FIXTURE. Age 80-84 F.", "Day -6: rest HR 64. Day 0: rest HR 75."], "key_line": 1}
    base = J.variants(c)["base"][0]
    assert base.splitlines()[-1].startswith("Computed 7-day trend") and not J.LEAK.search(base)
    assert J.variants(c)["key_deleted"][0].splitlines()[1].startswith("Computed")   # key_line index unchanged
