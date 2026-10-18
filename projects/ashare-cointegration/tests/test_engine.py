import os
for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[key] = "1"
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import unittest
import warnings
from concurrent.futures import ProcessPoolExecutor
from unittest.mock import patch
import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import coint, adfuller
from src.engine import eg_audit, candidates, correct, applicability, test_pair


class EngineTests(unittest.TestCase):
    def test_real_coint_and_lag_audit(self):
        rng = np.random.default_rng(20261018)
        b = 100 + rng.normal(size=1212).cumsum()
        for a in (40 + .8*b + rng.normal(size=1212).cumsum(),
                  40 + .8*b + rng.normal(size=1212),
                  40 - .8*b + rng.normal(size=1212)):
            calls = []
            def capture(*args, **kwargs):
                result = adfuller(*args, **kwargs)
                calls.append(result)
                return result
            with patch(coint.__module__ + ".adfuller", side_effect=capture):
                actual = coint(a, b, trend="c", maxlag=None, autolag="aic")
            audited = eg_audit(a, b)
            np.testing.assert_allclose(audited["EG_stat"], actual[0], atol=1e-8, rtol=1e-10)
            np.testing.assert_allclose(audited["p_library"], actual[1], atol=1e-10)
            self.assertEqual(audited["used_lag"], calls[0][2])
            self.assertEqual(audited["N_effective"], calls[0][3])
            self.assertEqual(audited["L_max"], 23)
        tail = eg_audit(40 + .8*b + rng.normal(size=1212), b)
        self.assertEqual(tail["compute_status"], "tail_unresolved")
        self.assertEqual(tail["p_zero_origin"], "mackinnon_boundary")

    def test_collinear_and_nonfinite(self):
        b = np.random.default_rng(14).normal(size=1212).cumsum()
        with warnings.catch_warnings(record=True) as caught:
            actual = coint(3+2*b, b)
        row = eg_audit(3+2*b, b)
        self.assertTrue(caught)
        self.assertEqual(row["EG_stat"], actual[0])
        self.assertEqual(row["p_library"], actual[1])
        self.assertEqual(row["p_for_adjustment"], 1)
        self.assertIsNone(row["p_raw"])
        a = b.copy(); a[8] = np.nan
        self.assertEqual(eg_audit(a,b)["placeholder_reason"], "nonfinite_input")
        with self.assertRaises(Exception):
            coint(b, a)

    def test_complete_families_and_main(self):
        u = pd.DataFrame([dict(ts_code=f"S{i}", name=f"S{i}", L2="G", L3=f"L{i//2}") for i in range(4)])
        h = candidates(u)
        self.assertEqual(len(h), 6)
        self.assertEqual((h.layer=="T").sum(), 2)
        h["p_for_adjustment"] = [0, .002, 1, .03, .7, 1]
        h["compute_status"] = ["tail_unresolved","valid","precheck_placeholder","valid","valid","numerically_ineligible"]
        h["alpha"] = 1.; h["beta"] = -1.
        full, main = correct(h)
        self.assertTrue(full.loc[full.layer=="C","p_L3_Holm"].isna().all())
        for domain in ("L3","L2","GLOBAL"):
            bf, holm, bh = [full[f"reject_{domain}_{m}"].fillna(False) for m in ("BF","Holm","BH")]
            self.assertFalse((bf & ~holm).any()); self.assertFalse((holm & ~bh).any())
        self.assertEqual(set(main.candidate_id), set(full.loc[full.reject_L2_Holm, "candidate_id"]))
        self.assertTrue((main.beta<0).all())
        with self.assertRaises(ValueError):
            correct(h.iloc[:-1])
        h.loc[0,"compute_status"] = "unexplained_error"
        with self.assertRaises(ValueError):
            correct(h)

    def test_single_eight_process_agreement(self):
        rng = np.random.default_rng(47)
        b = rng.normal(size=1212).cumsum()
        a = b + rng.normal(size=1212)
        ga, gb = applicability(a), applicability(b)
        self.assertTrue(ga["compatible"] and gb["compatible"])
        tasks = [(dict(candidate_id=str(i)), a, b, ga, gb) for i in range(8)]
        one = [test_pair(t) for t in tasks]
        with ProcessPoolExecutor(max_workers=8) as pool:
            many = list(pool.map(test_pair,tasks))
        self.assertEqual(one,many)


if __name__ == "__main__":
    unittest.main()
