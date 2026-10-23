"""SMART_TRIGGERS v1.10.3 HT_FOCAL_NEURO lay wording (Wayne 2026-10-23). Hand-written SYNTHETIC practice cases (not holdout text). No API calls."""
import os, sys, pytest
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import layer1_adapter as L  # noqa: E402
from test_layer1_v110 import ev  # noqa: E402
FIRE = ["Wife: at lunch his grin went lopsided and he sounded drunk.",
        "Son: the left side of her mouth is drooping since she woke from the nap.",
        "Carer: one side of his face has dropped in the last half hour.",
        "Daughter: she couldn't grip the spoon with her right hand at dinner, it just fell.",
        "Husband: she keeps dropping things from her left hand this afternoon.",
        "Neighbour: his right arm has gone floppy and he cannot lift it.",
        "Aide: her words keep coming out muddled, like the wrong ones.",
        "Wife: he can't get the words out, he knows what he wants to say.",
        "Partner: he started slurring halfway through his story about the bus."]
QUIET = ["Wife: his hands shake when he holds a cup, same as for years with the tremor.",
         "Daughter: her arthritis makes it hard to grip jars in the morning.",
         "Carer: he was tired and mumbling sleepily after the late night, then fine after breakfast.",
         "Son: no lopsided smile, speech clear, both hands strong."]
@pytest.mark.parametrize("note", FIRE)
def test_lay_focal_wording_fires(note):
    d = ev(caregiver_or_nurse_note=note); assert d["rule"] == "HT_FOCAL_NEURO" and d["tier"] == "ABSOLUTE" and L.route(d, None)[0] == "urgent_page"
@pytest.mark.parametrize("note", QUIET)
def test_non_focal_wording_quiet(note):
    assert ev(caregiver_or_nurse_note=note).get("rule") != "HT_FOCAL_NEURO"
def test_lay_focal_hospice_goes_to_goals_of_care():
    d = ev(patient_goals="hospice, comfort only, no hospital transfers", caregiver_or_nurse_note="Wife: his smile went crooked an hour ago.")
    assert d["rule"] == "HT_FOCAL_NEURO" and d["reason"] == "goals_of_care" and L.route(d, None)[0] == "nurse_task"
