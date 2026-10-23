import os
for key in ("OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "OMP_NUM_THREADS"):
    os.environ[key] = "1"
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
import run_market_revision as market


def registry():
    return pd.DataFrame([
        dict(candidate_id="a__b", A="a", B="b", L2="x", M_L2=2, M_GLOBAL=4),
        dict(candidate_id="a__c", A="a", B="c", L2="x", M_L2=2, M_GLOBAL=4),
        dict(candidate_id="d__e", A="d", B="e", L2="y", M_L2=2, M_GLOBAL=4),
        dict(candidate_id="d__f", A="d", B="f", L2="y", M_L2=2, M_GLOBAL=4)])


class MarketRevisionTests(unittest.TestCase):
    def test_holm_keeps_complete_domains_and_unavailable_positions(self):
        candidates = registry()
        rows = []
        for method in market.METHODS:
            for candidate, p in zip(candidates.to_dict("records"), (.01, .04, .02, 1.)):
                rows.append(dict(candidate, method=method, p=p,
                                 status="valid" if p != 1 else "numerically_ineligible"))
        result = market.correct_methods(pd.DataFrame(rows), candidates)
        for method in market.METHODS:
            part = result.loc[result.method.eq(method)]
            np.testing.assert_allclose(part.p_GLOBAL_Holm, [.04, .08, .06, 1.])
            np.testing.assert_allclose(part.p_L2_Holm, [.02, .04, .04, 1.])
            self.assertEqual(int(part.reject_GLOBAL_Holm.sum()), 1)
            self.assertEqual(int(part.reject_L2_Holm.sum()), 3)
        with self.assertRaises(ValueError):
            market.correct_methods(pd.DataFrame(rows[:-1]), candidates)

    def test_market_path_uses_saved_log_values_and_reuses_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            values = np.column_stack((np.linspace(-2., -.5, 12), np.linspace(-1., .6, 12)))
            np.save(path/"log_prices.npy", values)
            pd.DataFrame({"ts_code":["a","b"]}).to_parquet(path/"U.parquet", index=False)
            candidate = dict(candidate_id="a__b", A="a", B="b", L2="x", M_L2=1, M_GLOBAL=1)
            received = []
            def audited(value):
                received.append(value.copy())
                return [dict(method=m, p=.4, status="valid") for m in market.METHODS]
            market.initialize(path)
            with market.VALUES._mmap:
                with patch("run_market_revision.run_methods", side_effect=audited), \
                     patch("run_market_revision.applicability", side_effect=AssertionError("gate applied")):
                    result = market.work_batch((0, [candidate]))
                self.assertFalse(result["reused"])
                np.testing.assert_array_equal(received[0], values)
                before = market.batch_path(path, 0).stat().st_mtime_ns
                with patch("run_market_revision.run_methods", side_effect=AssertionError("recomputed")):
                    result = market.work_batch((0, [candidate]))
                self.assertTrue(result["reused"])
                self.assertEqual(before, market.batch_path(path, 0).stat().st_mtime_ns)

    def test_checkpoint_rejects_wrong_pair_metadata(self):
        candidate = dict(candidate_id="a__b", A="a", B="b", L2="x", M_L2=1, M_GLOBAL=1)
        frame = pd.DataFrame([dict(candidate, method=m, p=.2) for m in market.METHODS])
        market.check_batch(frame, [candidate])
        frame.loc[0, "B"] = "wrong"
        with self.assertRaises(ValueError):
            market.check_batch(frame, [candidate])


if __name__ == "__main__":
    unittest.main()
