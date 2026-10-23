import copy
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from scipy.signal import lfilter
from scipy.stats import binom

import run_scale_calibration_v2 as runner
from src import calibration_scale_dh as scale
from src import simulation
from src.engine import candidates
from src.engine_dh import dh_audit
from src.simulation_dh import panel_metrics


def fixture(stage="C2"):
    stocks, pairs = (120, 1740) if stage == "C2" else (2984, 67678)
    table = pd.DataFrame(dict(candidate_id=[str(i) for i in range(pairs)],
        true_alternative=False, reject_GLOBAL_Holm=False, compute_status="valid",
        ungated_p_for_adjustment=1., ungated_compute_status="valid",
        ungated_p_zero_origin=None, stage=stage))
    gates = {str(i): {"compatible": True} for i in range(stocks)}
    return panel_metrics(table, gates), table, gates


class ScaleCalibrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol = json.loads((runner.ROOT/runner.c1.PROTOCOL).read_text(encoding="utf-8"))

    def test_frozen_stage_tasks_and_distinct_seed_ranges(self):
        all_keys = []
        for stage, count, start, end in (("C2", 2500, 40000, 40499), ("C3", 500, 50000, 50099)):
            scale.validate_protocol(self.protocol, stage)
            keys = scale.task_keys(self.protocol, stage)
            self.assertEqual(len(keys), count)
            self.assertEqual(keys[0], ("N0", start))
            self.assertEqual(keys[-1], ("M1", end))
            all_keys.extend(keys)
            for scenario, r in (("N1", start), ("N0", start-1), ("M1", end+1)):
                with self.assertRaises(ValueError):
                    scale.validate_task(stage, scenario, r)
            changed = copy.deepcopy(self.protocol)
            changed["simulation"]["stages"][stage]["repeats"] += 1
            with self.assertRaisesRegex(ValueError, "F0 specification"):
                scale.validate_protocol(changed, stage)
        self.assertEqual(len(set(all_keys)), 3000)

    def test_membership_generator_is_exact_original_dgp_at_uniform_sizes(self):
        with patch.dict(simulation.STAGES, {"reference": (3, 4, 10, 1, scale.FOCUS)}):
            for scenario in scale.FOCUS:
                u, h, values = simulation.panel("reference", scenario, 90000, nobs=96)
                actual_u, actual_h, actual_values = scale.membership_panel(
                    u, h.drop(columns="true_alternative"), scenario, 90000, nobs=96)
                pd.testing.assert_frame_equal(actual_u, u)
                pd.testing.assert_frame_equal(actual_h, h)
                for code in u.ts_code:
                    np.testing.assert_array_equal(actual_values[code], values[code])

    def test_unequal_groups_singleton_offsets_and_mixed_truth(self):
        sizes = [1, 3, 7, 11]
        u = pd.DataFrame([dict(ts_code=f"U{g}{j:03}", name=f"U{g}{j:03}",
                              L2=f"G{g}", L3=f"G{g}L{j//2}")
                          for g, n in enumerate(sizes) for j in range(n)])
        h = candidates(u)
        _, actual_h, values = scale.membership_panel(u, h, "N0", 90001, nobs=64)
        self.assertEqual(len(actual_h), 79)
        self.assertEqual(len(values), 22)
        self.assertNotIn("U0000", set(h.A) | set(h.B))
        self.assertFalse(actual_h.true_alternative.any())
        rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([20261018, 3, 0, 90001])))
        trends = rng.normal(size=(2064, 27))[2000:].copy().cumsum(axis=0)
        trends -= trends[0]
        errors = lfilter([np.sqrt(.75)], [1, -.5], rng.normal(size=(2064, 22)), axis=0)[2000:]
        for code, g, j, offset, loading in [("U0000", 0, 0, 0, 1.), ("U3005", 3, 5, 11, 1.)]:
            x = 10000+5*(offset+j)+loading*(trends[:, 0]+trends[:, 1+g]+trends[:, 5+offset+j])+.25*errors[:, offset+j]
            np.testing.assert_array_equal(values[code], 100*x/x[0])
        _, mixed, _ = scale.membership_panel(u, h, "M1", 90001, nobs=64)
        truth = mixed.set_index("candidate_id").true_alternative
        self.assertTrue(truth["U3000__U3005"])
        self.assertFalse(truth["U3004__U3009"])
        pd.testing.assert_frame_equal(mixed.drop(columns="true_alternative"), h)

    def test_actual_C2_evaluator_uses_original_panel_and_frozen_kernel(self):
        metric, full, gates = scale.evaluate_panel("C2", "N0", 90002)
        self.assertEqual((metric["stocks"], metric["pairs"], metric["kernel_calls"]), (120, 1740, 1740))
        u, h, values = simulation.panel("S2", "N0", 90002)
        pd.testing.assert_frame_equal(full[h.columns], h)
        self.assertTrue(full.stage.eq("C2").all())
        self.assertTrue(full.ungated_N_effective.eq(1204).all())
        self.assertTrue(full.ungated_lags.eq(7).all())
        for row in full.iloc[:2].itertuples():
            audit = dh_audit(values[row.A], values[row.B])
            self.assertEqual(row.ungated_Q, audit["Q"])
            self.assertEqual(row.ungated_log_p, audit["log_p"])
        self.assertEqual(len(gates), len(u))

    def test_atomic_checkpoint_resume_and_missing_pair_rows(self):
        metric, table, gates = fixture()
        with TemporaryDirectory() as name:
            task = ("C2", "N0", 40000, name)
            with patch.object(scale, "evaluate_panel", return_value=(metric, table, gates)):
                with patch.object(scale, "write_json", side_effect=OSError("interrupted")):
                    with self.assertRaises(OSError):
                        scale.run_repetition(task)
            self.assertIsNone(scale.load_checkpoint(name, *task[:3]))
            with patch.object(scale, "evaluate_panel", return_value=(metric, table, gates)):
                result = scale.run_repetition(task)
            with patch.object(scale, "evaluate_panel", side_effect=AssertionError("must reuse")):
                self.assertEqual(scale.run_repetition(task), result)
            table.iloc[:-1].to_parquet(Path(name)/"N0/40000.pairs.parquet", index=False)
            with self.assertRaisesRegex(ValueError, "Incomplete pair"):
                scale.load_checkpoint(name, *task[:3])

    def test_summary_denominators_cp_and_partial_status(self):
        base, _, _ = fixture()
        records = [dict(base, stage="C2", scenario="N0", repetition=40000+i,
                        false_any=int(i < 25), total_seconds=1., cpu_seconds=.9)
                   for i in range(500)]
        summary = scale.summarize(records, self.protocol, "C2")
        row = summary.set_index("scenario").loc["N0"]
        self.assertEqual(row.B, 500)
        self.assertEqual(row.FWER, .05)
        self.assertAlmostEqual(binom.cdf(25, 500, row.FWER_upper95), .05)
        self.assertEqual(row.unit_acceptance, "tolerated_pass")
        self.assertEqual(scale.stage_acceptance(summary), "incomplete")
        records[0]["stage"] = "C1"
        with self.assertRaisesRegex(ValueError, "another stage"):
            scale.summarize(records, self.protocol, "C2")
        table = pd.DataFrame(dict(scenario=scale.FOCUS, complete=True, unit_acceptance="strict_pass"))
        self.assertEqual(scale.stage_acceptance(table), "strict_pass")
        table.loc[0, "unit_acceptance"] = "tolerated_pass"
        self.assertEqual(scale.stage_acceptance(table), "tolerated_pass")
        table.loc[0, "unit_acceptance"] = "inconclusive"
        self.assertEqual(scale.stage_acceptance(table), "inconclusive")
        table.loc[0, "unit_acceptance"] = "fail"
        self.assertEqual(scale.stage_acceptance(table), "fail")

    def test_previous_stage_must_pass_and_be_independently_checked(self):
        with TemporaryDirectory() as name:
            root = Path(name)
            folder = root/"results_v2/simulation"
            folder.mkdir(parents=True)
            state = dict(status="complete", C1_acceptance="tolerated_pass")
            check = dict(status="passed_engineering_and_summary_reconciliation", statistical_acceptance="tolerated_pass")
            scale.write_json(folder/"C1_status.json", state)
            with self.assertRaises(FileNotFoundError):
                runner.require_previous(root, "C2")
            scale.write_json(folder/"C1_validation.json", check)
            runner.require_previous(root, "C2")
            for result in ("fail", "inconclusive", "incomplete"):
                state["C1_acceptance"] = result
                scale.write_json(folder/"C1_status.json", state)
                with self.assertRaises(RuntimeError):
                    runner.require_previous(root, "C2")

    def test_new_source_snapshot_does_not_modify_F0_or_C1(self):
        with TemporaryDirectory() as name:
            root = Path(name)
            for file in runner.SOURCE_FILES:
                target = root/file
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(runner.ROOT/file, target)
            c1_folder = root/".local/dh_v2/simulation/C1"
            for file in runner.c1.SOURCE_FILES:
                target = c1_folder/"source"/file
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(root/file, target)
            scale.write_json(c1_folder/"environment.json", runner.c1.environment())
            (root/"results_v2").mkdir()
            shutil.copy2(runner.ROOT/"results_v2/F0_FREEZE.json", root/"results_v2/F0_FREEZE.json")
            before = (root/runner.c1.PROTOCOL).read_bytes()
            folder, keys = runner.prepare_run(root, "C2", self.protocol)
            self.assertEqual(len(keys), 2500)
            self.assertEqual((root/runner.c1.PROTOCOL).read_bytes(), before)
            self.assertEqual(runner.prepare_run(root, "C2", self.protocol), (folder, keys))
            (root/"src/calibration_scale_dh.py").write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "source differs"):
                runner.prepare_run(root, "C2", self.protocol)


if __name__ == "__main__":
    unittest.main()
