"""v1.11.2 stable-angina nurse_task rule (PLACEHOLDER). Practice-style synthetic vignettes only."""
import layer1_adapter as L
from test_layer1_v110 import ev
PMH = ["stable angina", "hypertension"]
MEDS = [{"name": "GTN spray", "dose": "400 mcg PRN"}, {"name": "amlodipine", "dose": "5 mg OD"}]
def _d(t, n): return ev(pmh=PMH, meds=MEDS, trend_last_7d=t, caregiver_or_nurse_note=n)

def test_unchanged_exertional_angina_is_nurse_task():
    d = _d("Day -6 to 0 rest HR 66-72, SBP 128-136. Day -3 and Day 0 brief chest tightness walking up the hill to the shop, eased within 3 min of resting. Day 0 rest HR 70, SBP 132.",
           "He says it is the same as usual, about twice a week on the hill, always settles with a rest and he has not needed the spray more than usual.")
    assert d.get("stable_angina") is True
    for pick in (None, "provider_task", "urgent_page", "silent_log"):
        assert L.route(d, pick) == ("nurse_task", "layer1_stable_angina")

def _not_nurse(d):
    assert not d.get("stable_angina")
    assert L.route(d, "provider_task")[0] in ("provider_task", "urgent_page")

def test_crescendo_more_frequent_not_nurse():
    _not_nurse(_d("Day -6 to 0 rest HR 66-74. Day -4, -2, -1 and Day 0 chest tightness on the stairs, eased within 4 min of rest. Day 0 rest HR 72.",
                  "Wife: it is happening more often this week, now on the stairs as well as the hill; settles with rest."))
def test_rest_onset_not_nurse():
    _not_nurse(_d("Day -6 to 0 rest HR 66-72. Day 0 06:10 chest tightness while sitting in bed reading, eased after 6 min with the GTN spray. Day 0 rest HR 74.",
                  "He says this one came on at rest, which has not happened before."))
def test_sweating_nausea_not_nurse():
    _not_nurse(_d("Day -6 to 0 rest HR 66-72. Day 0 chest tightness carrying shopping up the path, eased within 5 min of resting. Day 0 rest HR 76.",
                  "Daughter: he was sweaty and felt sick with it this time, otherwise like his usual angina."))
def test_longer_episode_not_nurse():
    _not_nurse(_d("Day -6 to 0 rest HR 66-72. Day 0 chest tightness walking to the bus stop, lasted about 20 min and needed two puffs of GTN. Day 0 rest HR 74.",
                  "He says it lasted longer than his usual angina."))
