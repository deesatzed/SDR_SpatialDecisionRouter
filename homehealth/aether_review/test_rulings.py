import csv
import tempfile
import unittest
from pathlib import Path

from homehealth.aether_review.rulings import current_references, load_rulings


class RulingRetrievalTests(unittest.TestCase):
    def write_csv(self, rows):
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        path = Path(tempdir.name) / "rulings.csv"
        with path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["case_id", "ruling", "note"])
            writer.writeheader()
            writer.writerows(rows)
        return path

    def test_loads_case_rulings_and_drops_policy_or_malformed_rows(self):
        path = self.write_csv([
            {"case_id": "SYN-001", "ruling": "nurse_task", "note": "clinician reference"},
            {"case_id": "POLICY-v1", "ruling": "policy", "note": "not a case"},
            {"case_id": "", "ruling": "nurse_task", "note": "missing ID"},
        ])
        references = load_rulings(path)
        self.assertEqual([reference.case_id for reference in references], ["SYN-001"])
        self.assertEqual(references[0].evidence_id, "clinician_ruling:SYN-001")

    def test_returns_exact_case_reference_before_other_current_references(self):
        path = self.write_csv([
            {"case_id": "SYN-002", "ruling": "silent_log", "note": "other"},
            {"case_id": "SYN-001", "ruling": "nurse_task", "note": "exact"},
        ])
        references = current_references(path, "SYN-001")
        self.assertEqual([reference.case_id for reference in references], ["SYN-001"])

    def test_caps_references_at_five(self):
        path = self.write_csv([
            {"case_id": f"SYN-{number}", "ruling": "nurse_task", "note": "reference"}
            for number in range(8)
        ])
        self.assertEqual(len(current_references(path, "unknown", include_fallback=True)), 5)


if __name__ == "__main__":
    unittest.main()
