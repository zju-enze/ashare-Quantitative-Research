import os
for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[key] = "1"
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import unittest
from concurrent.futures import ProcessPoolExecutor
from unittest.mock import patch
import numpy as np
import pandas as pd
from scipy.stats import chi2
from src.engine import candidates
from src.engine_dh import recursive_errors, dh_audit, test_pair, global_holm
from src.simulation import panel


def literal_reference(a, b, lags):
    """Independent prefix loops + full Z'W IV matrices, not the FWL kernel."""
    y = np.column_stack((a, b))
    T = len(y)
    centered = np.array([y[s] - y[:s+1].mean(axis=0) for s in range(T)])
    errors = np.zeros(T)
    for s in range(2, T):
        beta = np.linalg.lstsq(centered[:s+1, 1:2], centered[:s+1, 0],
                              rcond=None)[0][0]
        errors[s] = centered[s, 0] - beta*centered[s, 1]
    dy = np.diff(y, axis=0)
    indices = range(lags+1, T)
    x = np.array([[value for j in range(1, lags+1)
                   for value in dy[t-j-1]] for t in indices]).reshape(T-lags-1, 2*lags)
    dependent = np.array([y[t]-y[t-1] for t in indices])
    error = np.array([errors[t-1] for t in indices])
    W = np.column_stack((error, x))
    Z = np.column_stack((np.sign(error), x))
    zw = Z.T @ W
    coefficients = np.linalg.solve(zw, Z.T @ dependent)
    residuals = dependent - W @ coefficients
    omega = residuals.T @ residuals / T
    inverse = np.linalg.inv(zw)
    coefficient_factor = (inverse @ (Z.T @ Z) @ inverse.T)[0, 0]
    covariance = omega * coefficient_factor
    adjustment = coefficients[0]
    t = adjustment / np.sqrt(np.diag(covariance))
    Q = float(adjustment @ np.linalg.solve(covariance, adjustment))
    return dict(errors=errors, adjustment=adjustment, t=t, Q=Q, p=chi2.sf(Q, 2))


class DHTests(unittest.TestCase):
    def test_budget_counts_stock_and_pair_work_and_timing_variation(self):
        from scripts.validate_dh_development import make_budget
        metrics = pd.DataFrame([dict(purpose="timing", geometry="S2", stocks=120, pairs=1740,
                                    all_pairs_seconds=3480., precheck_seconds=120.,
                                    dgp_seconds=0., holm_seconds=0.)])
        repeats = pd.DataFrame(dict(scenario=["N0", "N0"], total_seconds=[1., 3.]))
        budget = make_budget(metrics, repeats)
        plan = next(x for x in budget["estimates"] if x["plan"] == "formal_S1_15x1000")
        self.assertEqual(plan["pair_system_tests"], 2700000)
        self.assertAlmostEqual(plan["serial_hours_median"], 15000*(40+2*180)/3600)
        self.assertAlmostEqual(plan["serial_hours_slow_repeat_scenario"],
                               3*plan["serial_hours_median"])

    def test_recursive_prefix_and_no_future_information(self):
        a = np.array([10., 12., 11., 16., 14., 19.])
        b = np.array([5., 6., 8., 7., 9., 8.])
        actual = recursive_errors(a, b)
        expected = literal_reference(a, b, 0)["errors"]
        np.testing.assert_allclose(actual, expected, atol=1e-12)
        np.testing.assert_array_equal(actual[:2], [0, 0])
        longer = recursive_errors(np.r_[a, 1e6, -1e6], np.r_[b, -2e6, 3e6])
        np.testing.assert_array_equal(actual, longer[:len(a)])

    def test_literal_iv_matrix_reference_and_joint_covariance(self):
        for scenario in ("N0", "N6", "A0", "M1"):
            u, _, values = panel("S0", scenario, 0, nobs=300)
            a, b = [values[s] for s in u.ts_code.iloc[:2]]
            for lags in (0, 7):
                with self.subTest(scenario=scenario, lags=lags):
                    ref = literal_reference(a, b, lags)
                    got = dh_audit(a, b, lags)
                    self.assertEqual(got["compute_status"], "valid")
                    np.testing.assert_allclose(
                        [got["adjustment_A"], got["adjustment_B"]], ref["adjustment"], rtol=1e-8)
                    np.testing.assert_allclose([got["t_A"], got["t_B"]], ref["t"], rtol=1e-8)
                    np.testing.assert_allclose(got["Q"], ref["Q"], rtol=1e-8)
                    np.testing.assert_allclose(got["p_raw"], ref["p"], rtol=1e-7)
                    self.assertEqual(got["N_effective"], len(a)-lags-1)
                    self.assertEqual(got["covariance_denominator"], len(a))
                    self.assertAlmostEqual(got["log_p"], -got["Q"]/2)
                    if scenario == "N0":
                        self.assertGreater(abs(got["residual_correlation"]), .1)
                        self.assertGreater(abs(got["Q"] - got["t_A"]**2 - got["t_B"]**2), .01)

    def test_location_and_positive_scale_invariance(self):
        rng = np.random.default_rng(64)
        b = rng.normal(size=400).cumsum()
        a = .6*b + rng.normal(size=400).cumsum()
        original = dh_audit(a, b)
        transformed = dh_audit(100 + 7*a, -37 + .2*b)
        np.testing.assert_allclose(original["Q"], transformed["Q"], rtol=1e-10)

    def test_unavailable_inputs_and_no_regularization(self):
        b = np.random.default_rng(15).normal(size=100).cumsum()
        cases = [(b, np.ones(100)), (2*b, b), (np.r_[np.nan, b[1:]], b), (b[:20], b[:20])]
        for a, other in cases:
            with self.subTest():
                row = dh_audit(a, other)
                self.assertEqual(row["compute_status"], "numerically_ineligible")
                self.assertEqual(row["p_for_adjustment"], 1)
                self.assertTrue(row["placeholder_reason"])
        with self.assertRaises(ValueError):
            dh_audit(b, b[:-1])
        with self.assertRaises(ValueError):
            dh_audit(b, b, lags=-1)

    def test_gate_and_complete_global_family(self):
        u, _, values = panel("S0", "N0", 0)
        h = candidates(u)
        good = dict(compatible=True, status="compatible")
        bad = dict(compatible=False, status="incompatible")
        first = h.iloc[0].to_dict()
        with patch("src.engine_dh.dh_audit") as kernel:
            row = test_pair((first, values[first["A"]], values[first["B"]], good, bad))
        kernel.assert_not_called()
        self.assertEqual(row["p_for_adjustment"], 1)
        executed = test_pair((first, values[first["A"]], values[first["B"]], good, good))
        self.assertEqual(list(row), list(executed))
        h["p_for_adjustment"] = [1e-4, .004, .01] + [1.] * (len(h)-3)
        h["compute_status"] = ["valid"]*3 + ["precheck_placeholder"]*(len(h)-3)
        full, main = global_holm(h)
        expected = np.array([.0012, .044, .1] + [1.] * (len(h)-3))
        np.testing.assert_allclose(full.p_GLOBAL_Holm, expected)
        self.assertEqual(len(main), 2)
        with self.assertRaises(ValueError):
            global_holm(h.iloc[:-1])
        h.loc[3, "p_for_adjustment"] = 0.
        with self.assertRaises(ValueError):
            global_holm(h)

    def test_single_two_worker_identity(self):
        u, h, values = panel("S0", "N6", 1, nobs=300)
        gate = dict(compatible=True, status="compatible")
        tasks = [(r, values[r["A"]], values[r["B"]], gate, gate)
                 for r in h.head(4).to_dict("records")]
        serial = [test_pair(t) for t in tasks]
        with ProcessPoolExecutor(max_workers=2) as pool:
            parallel = list(pool.map(test_pair, tasks))
        # Cross-L3 candidate metadata contains NaN; statistics must still match exactly.
        pd.testing.assert_frame_equal(pd.DataFrame(serial), pd.DataFrame(parallel), check_exact=True)


if __name__ == "__main__":
    unittest.main()
