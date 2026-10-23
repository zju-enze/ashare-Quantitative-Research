import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

import run_market_v2 as market
from src.engine import candidates
from src.engine_dh import dh_audit
from src.engine_dh_market import test_pair as market_test_pair
from test_engine_dh import literal_reference


def registry():
    return candidates(pd.DataFrame([dict(ts_code=f"S{g}{j}", name=f"S{g}{j}", L2=f"G{g}", L3=f"G{g}")
                                    for g in range(2) for j in range(3)]))


class MarketDHTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol = json.loads((market.ROOT/market.c1.PROTOCOL).read_text(encoding="utf-8"))

    def test_market_pool_requires_all_three_checked_passing_stages(self):
        with TemporaryDirectory() as name:
            root = Path(name); folder = root/"results_v2/simulation"; folder.mkdir(parents=True)
            market.write_json(root/market.c1.PROTOCOL, self.protocol)
            for stage, planned in (("C1", 15000), ("C2", 2500), ("C3", 500)):
                market.write_json(folder/f"{stage}_status.json", dict(status="complete", completed=planned,
                    **{f"{stage}_acceptance": "tolerated_pass"}))
                market.write_json(folder/f"{stage}_validation.json", dict(
                    status="passed_engineering_and_summary_reconciliation",
                    statistical_acceptance="tolerated_pass", checked_at="test"))
            self.assertEqual(set(market.require_calibration(root)), {"C1", "C2", "C3"})
            for acceptance in ("inconclusive", "fail"):
                market.write_json(folder/"C3_status.json", dict(status="complete", completed=500,
                                                              C3_acceptance=acceptance))
                market.write_json(folder/"C3_validation.json", dict(
                    status="passed_engineering_and_summary_reconciliation",
                    statistical_acceptance=acceptance, checked_at="test"))
                with patch.object(market, "ROOT", root), patch("sys.argv", ["market"]):
                    with patch.object(market, "ProcessPoolExecutor") as pool, patch.object(market, "prepare_run") as prepare:
                        with self.assertRaises(RuntimeError):
                            market.main()
                        pool.assert_not_called(); prepare.assert_not_called()
                if acceptance == "inconclusive":
                    result = market.require_calibration(root, nominal_if_inconclusive=True)
                    self.assertEqual(result["C3"]["acceptance"], "inconclusive")
                else:
                    with self.assertRaises(RuntimeError):
                        market.require_calibration(root, nominal_if_inconclusive=True)

    def test_global_primary_auxiliary_four_cells_and_zero_discoveries(self):
        raw = registry().assign(compute_status="valid", p_for_adjustment=[.001, .03, 1., .012, .09, 1.])
        raw.loc[[2, 5], "compute_status"] = "precheck_placeholder"
        previous = raw.assign(reject_L2_Holm=[True, True, False, True, False, False],
                              reject_GLOBAL_Holm=[True, False, False, False, False, False])
        full, main, compare, counts, overlap = market.finalize(raw, previous)
        self.assertEqual(main.candidate_id.tolist(), [raw.iloc[0].candidate_id])
        self.assertEqual(int(full.reject_L2_Holm.sum()), 2)
        self.assertEqual(counts, dict(V1_EG_L2_Holm=3, V1_EG_GLOBAL_Holm=1,
                                      V2_DH_L2_Holm=2, V2_DH_GLOBAL_Holm=1))
        self.assertEqual(overlap, dict(intersection=1, V1_only=2, DH_only=0, union=3, Jaccard=1/3))
        self.assertFalse(full.loc[[2, 5], "reject_GLOBAL_Holm"].any())
        identity = ["candidate_id", "A", "B", "L2", "layer"]
        pd.testing.assert_frame_equal(compare[identity], raw[identity])
        with self.assertRaisesRegex(ValueError, "different frozen"):
            market.finalize(raw, previous.iloc[::-1])
        _, empty, _, counts, _ = market.finalize(raw.assign(p_for_adjustment=1.), previous)
        self.assertTrue(empty.empty)
        self.assertEqual(counts["V2_DH_GLOBAL_Holm"], 0)

    def test_existing_batch_must_match_candidate_rows(self):
        h = registry().iloc[3:]
        with TemporaryDirectory() as name:
            path = Path(name)/"batch.parquet"
            self.assertIsNone(market.load_batch(path, h))
            h.assign(Q=1.).to_parquet(path, index=False)
            loaded = market.load_batch(path, h)
            self.assertEqual(len(loaded), 3)
            h.iloc[::-1].to_parquet(path, index=False)
            with self.assertRaises(AssertionError):
                market.load_batch(path, h)

    def test_unused_flat_prefix_matches_independent_IV_reference(self):
        rng = np.random.default_rng(782)
        b = 100+rng.normal(size=160).cumsum()
        a = 90+.7*b+rng.normal(size=160).cumsum()
        b[:4] = b[0]
        gate = dict(compatible=True, status="compatible")
        task = (dict(candidate_id="A__B", A="A", B="B"), a, b, gate, gate)
        self.assertEqual(dh_audit(a, b)["placeholder_reason"], "recursive_regression_rank_deficient")
        got = market_test_pair(task)
        ref = literal_reference(a, b, 7)
        self.assertEqual(got["compute_status"], "valid")
        self.assertTrue(got["prefix_guard_corrected"])
        self.assertEqual(got["N_effective"], 152)
        np.testing.assert_allclose(got["Q"], ref["Q"], rtol=1e-8)
        np.testing.assert_allclose([got["adjustment_A"], got["adjustment_B"]], ref["adjustment"], rtol=1e-8)
        b[:8] = b[0]
        unusable = market_test_pair(task)
        self.assertEqual(unusable["compute_status"], "numerically_ineligible")
        self.assertEqual(unusable["p_for_adjustment"], 1.)

    def test_regular_path_is_unchanged_and_does_not_use_prefix_correction(self):
        rng = np.random.default_rng(97)
        a, b = rng.normal(size=(2, 200)).cumsum(axis=1)
        gate = dict(compatible=True, status="compatible")
        task = (dict(candidate_id="A__B", A="A", B="B"), a, b, gate, gate)
        expected = dh_audit(a, b)
        with patch("src.engine_dh_market._audit_used_prefix", side_effect=AssertionError("original valid path must stay")):
            got = market_test_pair(task)
        self.assertFalse(got["prefix_guard_corrected"])
        for key,value in expected.items():
            self.assertEqual(got[key], value)

    def test_worker_uses_mapped_prices_and_DH_not_legacy_EG(self):
        rng = np.random.default_rng(612)
        prices = 100+rng.normal(size=(160, 3)).cumsum(axis=0)
        u = pd.DataFrame(dict(ts_code=["B", "A", "C"]))
        with TemporaryDirectory() as name:
            root = Path(name)
            np.save(root/"prices.npy", prices)
            u.to_parquet(root/"U.parquet", index=False)
            market.write_json(root/"ADF.json", {s:dict(compatible=True, status="compatible") for s in u.ts_code})
            market.v1.initialize(name)
            result = market.diagnose_pair(dict(candidate_id="A__B", A="A", B="B"))
            expected = dh_audit(prices[:, 1], prices[:, 0])
            self.assertEqual(result["Q"], expected["Q"])
            self.assertEqual(result["df"], 2)
            market.v1.VALUES = None

    def test_market_snapshot_keeps_input_bytes_and_reuses_precheck(self):
        with TemporaryDirectory() as name:
            root = Path(name)
            for file in market.SOURCE_FILES:
                target = root/file; target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(market.ROOT/file, target)
            source = root/".local/production"/self.protocol["market"]["input_run_id"]
            (source/"source").mkdir(parents=True)
            shutil.copy2(root/"src/engine.py", source/"source/engine.py")
            pd.DataFrame(dict(ts_code=["A", "B"])).to_parquet(source/"U.parquet", index=False)
            pd.DataFrame(dict(candidate_id=["A__B"])).to_parquet(source/"H.parquet", index=False)
            np.save(source/"prices.npy", np.ones((3, 2)))
            market.write_json(source/"freeze.json", {"calendar": ["a", "b", "c"]})
            market.write_json(source/"ADF.json", {s:dict(input_version=source.name,
                statsmodels_version=market.c1.environment()["statsmodels"]) for s in ["A", "B"]})
            original = (root/market.c1.PROTOCOL).read_bytes()
            with patch.object(market.c1, "verify_snapshot"), patch.object(market.c1, "market_input_evidence"):
                run, _ = market.prepare_run(root, self.protocol, {})
                self.assertEqual((run/"ADF.json").read_bytes(), (source/"ADF.json").read_bytes())
                self.assertEqual((root/market.c1.PROTOCOL).read_bytes(), original)
                self.assertEqual(market.prepare_run(root, self.protocol, {})[0], run)
                np.save(source/"prices.npy", np.zeros((3, 2)))
                with self.assertRaisesRegex(RuntimeError, "input differs"):
                    market.prepare_run(root, self.protocol, {})


if __name__ == "__main__":
    unittest.main()
