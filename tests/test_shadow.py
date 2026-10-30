import unittest
from synbios.shadow import eligible, run_experiment


class ShadowTests(unittest.TestCase):
    def test_positive_negative_and_mixed_reviews(self):
        good = {"reviewer_id": "reviewer", "commit_id": "current", "state": "APPROVED"}
        self.assertTrue(eligible("author", "current", [good]))
        self.assertFalse(eligible("author", "current", []))
        for patch in ({"reviewer_id": "author"}, {"commit_id": "old"}, {"state": "DISMISSED"}):
            self.assertFalse(eligible("author", "current", [{**good, **patch}]))
        self.assertTrue(eligible("author", "current", [{**good, "commit_id": "old"}, good]))

    def test_missing_or_invalid_identity_is_not_approval(self):
        for reviewer in (None, "", 42):
            self.assertFalse(eligible("author", "current", [{"reviewer_id": reviewer, "commit_id": "current", "state": "APPROVED"}]))
        self.assertFalse(eligible("author", "current", [{"commit_id": "current", "state": "APPROVED"}]))

    def test_condition_removal_mutants_are_detected(self):
        report = run_experiment()
        self.assertEqual(report["result"], "passed")
        self.assertEqual(report["mutants_detected"], 3)
        self.assertGreater(report["positive_cases"], 0)
        self.assertGreater(report["negative_cases"], 0)
        self.assertEqual(report["formal_verification"], "unavailable")
