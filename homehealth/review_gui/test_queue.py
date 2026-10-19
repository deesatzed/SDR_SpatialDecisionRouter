import json
import tempfile
import unittest
from pathlib import Path

from homehealth.review_gui.queue import load_queue


class QueueTests(unittest.TestCase):
    def fixture(self, cases):
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        path = Path(tempdir.name) / "queue.json"
        path.write_text(json.dumps(cases))
        return path

    def test_loads_explicitly_synthetic_preconfigured_case(self):
        queue = load_queue(self.fixture([{
            "case_id": "GL1-005", "synthetic": True,
            "summary": "Synthetic confirmed low.",
            "clinician_ruling_ref": "GL1-005",
            "input": {"synthetic": True, "case_id": "GL1-005", "reading": {"vital": "glucose", "value": 47, "ts": 9900, "activity_state": "rest", "source": "cgm", "cgm": {"fingerstick": {"value": 44, "minutes_apart": 10}}}},
            "expected": {"tier": "ABSOLUTE", "rule": "HT_VS_DANGER"},
        }]))
        self.assertEqual(queue[0].case_id, "GL1-005")

    def test_rejects_unmarked_or_missing_ruling_reference(self):
        with self.assertRaises(ValueError):
            load_queue(self.fixture([{"case_id": "bad", "synthetic": False}]))
        with self.assertRaises(ValueError):
            load_queue(self.fixture([{"case_id": "bad", "synthetic": True}]))
