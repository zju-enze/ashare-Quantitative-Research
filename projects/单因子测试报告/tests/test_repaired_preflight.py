from pathlib import Path
import sys
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from preflight_repaired import canonical_factor_series, entry_qualification, halted_at_close


class RepairedPreflightTests(unittest.TestCase):
    def test_primary_trade_quote_and_explicit_close_halt_take_priority(self):
        result = entry_qualification(pd.Series([False, False, False, False]),
                                     pd.Series([False, True, False, False]),
                                     pd.Series([True, True, False, False]),
                                     pd.Series(["0", "1", "0", None]))
        self.assertEqual(result.tolist(), ["tradable", "not_tradable_at_close", "not_tradable_at_close", "unknown"])

    def test_observed_halt_ranges_distinguish_closing_auction_resumption(self):
        self.assertTrue(halted_at_close(None))
        self.assertTrue(halted_at_close("13:00-15:00"))
        self.assertFalse(halted_at_close("13:36-13:46,14:53-14:57"))
        self.assertFalse(halted_at_close("10:05:50-10:15:50"))

    def test_alias_factors_keep_one_complete_scale(self):
        aliases = pd.DataFrame({"old_code": ["old"], "new_code": ["new"]})
        frame = pd.DataFrame({"ts_code": ["old", "new", "new"], "trade_date": ["d1", "d1", "d2"],
                              "adj_factor": [4.189, 4.1885, 4.1885]})
        got = canonical_factor_series(frame, aliases)
        self.assertEqual(got.raw_code.tolist(), ["new", "new"])
        self.assertEqual(got.adj_factor.tolist(), [4.1885, 4.1885])
        with self.assertRaises(ValueError):
            canonical_factor_series(frame.drop(index=1), aliases)


if __name__ == "__main__":
    unittest.main()
