import json
import tempfile
import unittest
from pathlib import Path

from homehealth.review_gui.app import create_app


ROOT = Path(__file__).resolve().parents[2]
PARAMS = ROOT / "homehealth" / "trigger_engine" / "trigger_params.json"


class ReviewAppTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        queue = Path(self.tempdir.name) / "queue.json"
        queue.write_text(json.dumps([{
            "case_id": "GL1-005", "synthetic": True,
            "summary": "Synthetic confirmed low glucose reading.",
            "clinician_ruling_ref": "GL1-005",
            "input": {"synthetic": True, "case_id": "GL1-005", "reading": {"vital": "glucose", "value": 47, "ts": 9900, "activity_state": "rest", "source": "cgm", "cgm": {"fingerstick": {"value": 44, "minutes_apart": 10}}}},
            "expected": {"tier": "ABSOLUTE", "rule": "HT_VS_DANGER"},
        }]))
        self.app = create_app(queue, Path(self.tempdir.name) / "review.sqlite3", PARAMS)
        self.client = self.app.test_client()

    def test_index_redirects_to_focused_case(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/cases/GL1-005"))

    def test_case_page_shows_preconfigured_and_computed_engine_result(self):
        response = self.client.get("/cases/GL1-005")
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn("Synthetic clinician review", page)
        self.assertIn("GL1-005", page)
        self.assertIn("ABSOLUTE", page)
        self.assertIn("HT_VS_DANGER", page)
        self.assertIn("No network or live model calls", page)

    def test_app_binds_only_to_loopback_when_run(self):
        self.assertEqual(self.app.config["REVIEW_HOST"], "127.0.0.1")
