from pathlib import Path
import sys
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from classify_endpoint_repairs import classify_keys
from reconcile_suspension_actions import ex_reference


class EndpointEvidenceTests(unittest.TestCase):
    def test_cash_and_share_distribution_adjust_reference_not_wealth(self):
        self.assertAlmostEqual(ex_reference(9.19, 0.10, 0, 0), 9.09)
        price = ex_reference(23.52, 0.20, 0, 0.5)
        self.assertAlmostEqual(price * 1.5 + 0.20, 23.52)

    def test_absence_is_not_suspension_and_conflicts_remain_visible(self):
        frame = pd.DataFrame({
            "status_conflict": [False, False, False, False, True, False, False],
            "price_present": [False, False, False, True, False, True, False],
            "suspended": [False, True, False, False, False, True, True],
            "delisted": [False, False, True, False, False, False, True],
        })
        self.assertEqual(classify_keys(frame).tolist(), [
            "unexplained_missing_quote", "confirmed_suspension", "terminal_event_unresolved",
            "quote_present", "conflicting_evidence", "conflicting_evidence", "terminal_event_unresolved",
        ])


if __name__ == "__main__":
    unittest.main()
