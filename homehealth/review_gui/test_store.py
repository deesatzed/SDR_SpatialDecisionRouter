import tempfile
import unittest
from pathlib import Path

from homehealth.review_gui.store import ReviewStore


class ReviewStoreTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.store = ReviewStore(Path(self.tempdir.name) / "review.sqlite")

    def test_queue_record_and_status_update_are_local_state(self):
        self.store.ensure_case("SYN-001", "ready")
        self.store.set_status("SYN-001", "approved")
        self.assertEqual(self.store.status_for("SYN-001"), "approved")

    def test_audit_events_are_append_only(self):
        self.store.ensure_case("SYN-001", "ready")
        self.store.audit("SYN-001", "reviewer", "agree", {"checks": 5})
        self.store.audit("SYN-001", "reviewer", "edit", {"field": "value"})
        self.assertEqual([event["action"] for event in self.store.audit_for("SYN-001")], ["agree", "edit"])

    def test_invalid_status_is_rejected(self):
        self.store.ensure_case("SYN-001", "ready")
        with self.assertRaises(ValueError):
            self.store.set_status("SYN-001", "mutate_source")

    def test_draft_is_local_and_separate_from_audit(self):
        self.store.ensure_case("SYN-001", "ready")
        self.store.set_draft("SYN-001", {"reading_value": 45})
        self.assertEqual(self.store.draft_for("SYN-001"), {"reading_value": 45})
        self.assertEqual(self.store.audit_for("SYN-001"), [])
