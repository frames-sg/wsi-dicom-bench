import json
import os
import unittest
from pathlib import Path

from wsi_dicom_bench.negative_bench import http_statement_cases
from wsi_dicom_bench.negative_bench.http_statement_runner import observe_case


class HttpStatementCaseTests(unittest.TestCase):
    def test_cases_name_checked_http_statements_once(self):
        requirements_path = (
            Path(__file__).parents[1]
            / "src/wsi_dicom_bench/rules/wsi-dicom-requirements-v1.json"
        )
        requirements = {
            entry["id"]: entry
            for entry in json.loads(requirements_path.read_text(encoding="utf-8"))["requirements"]
            if entry.get("id")
        }
        cases = http_statement_cases.CASES
        self.assertEqual(len({case["case_id"] for case in cases}), len(cases))
        named = [identifier for case in cases for identifier in case["requirement_ids"]]
        self.assertEqual(len(named), len(set(named)))
        for case in cases:
            for identifier in case["requirement_ids"]:
                self.assertEqual(
                    requirements[identifier]["disposition"],
                    {"kind": "checked", "detail": case["expected_check"]},
                )

    @unittest.skipUnless(os.environ.get("WSI_DICOM_CANDIDATE"), "needs candidate CLI")
    def test_positive_and_broken_origins_run_through_candidate_cli(self):
        candidate = Path(os.environ["WSI_DICOM_CANDIDATE"])
        for case in http_statement_cases.CASES:
            with self.subTest(case=case["case_id"]):
                observation = observe_case(candidate, case)
                self.assertEqual(observation["baseline_status"], "passed")
                self.assertEqual(observation["baseline_failed_checks"], [])
                if case.get("expected_evidence") == "advisory":
                    self.assertEqual(observation["observed_status"], "passed")
                    self.assertTrue(observation["observed_advisories"])
                else:
                    self.assertEqual(observation["observed_status"], "failed")
                    self.assertIn(case["expected_check"], observation["failed_checks"])


if __name__ == "__main__":
    unittest.main()
