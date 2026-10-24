import unittest

from wsi_dicom_bench.negative_bench.freeze_v7 import assess_readiness


class V7FreezeGateTests(unittest.TestCase):
    def test_checked_corpus_can_freeze_with_explicit_policy_failure(self):
        result = assess_readiness()

        self.assertEqual(result["status"], "ready_with_known_policy_failure")
        self.assertEqual(result["blockers"], [])
        self.assertEqual(
            result["policy_gaps"], [{
                "field": "unchecked_statement_scope_pairs",
                "count": 16,
                "ids": [
                    "Ps5_8_2_5_5c5c79", "Ps5_8_2_5_6cde8d",
                    "Ps5_8_2_6_405812", "Ps5_8_2_6_4d8fa8",
                    "Ps5_8_2_6_571188", "Ps5_A_11_ce7500", "Ps5_A_6_e0a5fd",
                ],
                "families": ["jpip-dataset-encoding", "mpeg2-stream"],
            }],
        )


if __name__ == "__main__":
    unittest.main()
