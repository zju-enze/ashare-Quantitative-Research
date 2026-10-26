"""Small artificial checks for date truncation and BP missing-value accounting."""

from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from preflight import bp_reason, industry_at, make_calendar


class PreflightTests(unittest.TestCase):
    def test_holiday_entry_and_truncated_last_month(self):
        days = ["20251230", "20251231", "20260105", "20260130", "20260202", "20260213",
                "20260227", "20260302", "20260331", "20260401"]
        result = make_calendar(days, "20260213", "2025-12").set_index("signal_month")
        december = result.loc["2025-12"]
        self.assertEqual((december.signal_date, december.entry_date, december.exit_date),
                         ("20251231", "20260105", "20260202"))
        self.assertTrue(december.holding_complete)
        self.assertTrue(result.loc["2026-01", "signal_complete"])
        self.assertFalse(result.loc["2026-01", "holding_complete"])
        self.assertEqual(result.loc["2026-02", "signal_date"], "20260227")
        self.assertFalse(result.loc["2026-02", "signal_complete"])

    def test_last_observed_date_is_not_automatically_month_end(self):
        result = make_calendar(["20260130", "20260202", "20260213"], "20260213", "2026-01")
        self.assertEqual(result.iloc[-1].signal_date, "")
        self.assertFalse(result.holding_complete.any())

    def test_pb_reasons_are_disjoint(self):
        got = bp_reason([np.nan, np.nan, np.inf, -np.inf, 0, -2, 2],
                        [False, True, True, True, True, True, True]).tolist()
        self.assertEqual(got, ["valuation_row_missing", "pb_missing", "pb_nonfinite", "pb_nonfinite",
                               "pb_zero", "pb_negative", "valid"])

    def test_interval_versions_agree_before_change_and_conflict_after(self):
        frame = pd.DataFrame([
            ["stock", "20200101", "99991231", "old"],
            ["stock", "20200101", "20260630", "old"],
            ["stock", "20260701", "99991231", "new"],
        ], columns=["ts_code", "in_date", "end", "l1_name"])
        labels, conflicts = industry_at(frame, "20251231")
        self.assertEqual(labels["stock"], "old")
        self.assertFalse(conflicts)
        labels, conflicts = industry_at(frame, "20260701")
        self.assertTrue(labels.empty)
        self.assertEqual(conflicts, {"stock"})

    def test_old_industry_covers_its_last_trading_day(self):
        frame = pd.DataFrame([
            ["stock", "20000101", "20070629", "old"],
            ["stock", "20070702", "99991231", "new"],
        ], columns=["ts_code", "in_date", "end", "l1_name"])
        self.assertEqual(industry_at(frame, "20070629")[0]["stock"], "old")
        self.assertEqual(industry_at(frame, "20070702")[0]["stock"], "new")


if __name__ == "__main__":
    unittest.main()
