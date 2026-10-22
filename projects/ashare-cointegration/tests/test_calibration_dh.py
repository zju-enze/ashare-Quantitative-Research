import copy
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pandas as pd
from scipy.stats import binom

import run_calibration_v2 as runner
from src import calibration_dh as calibration
from src.simulation_dh import panel_metrics


def fixture():
    table = pd.DataFrame(dict(
        candidate_id=[str(i) for i in range(180)], true_alternative=[False]*180,
        reject_GLOBAL_Holm=[False]*180, compute_status=["valid"]*180,
        ungated_p_for_adjustment=[1.]*180, ungated_compute_status=["valid"]*180,
        ungated_p_zero_origin=[None]*180, stage=["D1"]*180))
    gates = {str(i): {"compatible": True} for i in range(40)}
    return panel_metrics(table, gates), table, gates


class CalibrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.development = json.loads((runner.ROOT/"experiment_protocol_v2.json").read_text(encoding="utf-8"))
        cls.protocol = runner.frozen_protocol(cls.development, "2026-10-20T09:00:00+08:00")

    def test_frozen_spec_seeds_and_allowed_stages(self):
        calibration.validate_protocol(self.protocol)
        self.assertIsNone(self.development["method_freeze_at"])
        self.assertEqual(self.protocol["method"], self.development["method"])
        self.assertEqual(self.protocol["acceptance"], self.development["acceptance"])
        keys = calibration.task_keys(self.protocol)
        self.assertEqual(len(keys), 15000)
        self.assertEqual(len(set(keys)), 15000)
        self.assertEqual(keys[0], ("N0", 30000))
        self.assertEqual(keys[-1], ("M1", 30999))
        self.assertTrue(all(20000 > r or r > 20099 for _, r in keys))
        altered = copy.deepcopy(self.protocol)
        altered["simulation"]["stages"]["C1"]["repeats"] = 999
        with self.assertRaisesRegex(ValueError, "C1 task specification"):
            calibration.validate_protocol(altered)
        with self.assertRaises(ValueError):
            calibration.validate_protocol(self.development)
        for name in ("C2", "C3", "M"):
            with patch("sys.stderr"), self.assertRaises(SystemExit):
                runner.parser().parse_args(["--stage", name])

    def test_checkpoint_relabels_only_stage_and_preserves_D1(self):
        metric, table, gates = fixture()
        with TemporaryDirectory() as name:
            root = Path(name)
            d1 = root/"D1/untouched.json"
            d1.parent.mkdir()
            d1.write_text("D1 retained", encoding="utf-8")
            task = ("N0", 30000, str(root/"C1"))
            with patch.object(calibration.development, "evaluate_panel",
                              return_value=(metric, table.copy(), gates)) as evaluate:
                result = calibration.run_repetition(task)
                evaluate.assert_called_once_with("N0", 30000)
            self.assertEqual(result["stage"], "C1")
            saved = pd.read_parquet(root/"C1/N0/30000.pairs.parquet")
            self.assertTrue(saved.stage.eq("C1").all())
            pd.testing.assert_frame_equal(saved.drop(columns="stage"), table.drop(columns="stage"))
            with patch.object(calibration.development, "evaluate_panel", side_effect=AssertionError("must reuse")):
                self.assertEqual(calibration.run_repetition(task), result)
            self.assertEqual(d1.read_text(), "D1 retained")
            result["stage"] = "D1"
            (root/"C1/N0/30000.json").write_text(json.dumps(result), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "checkpoint"):
                calibration.load_checkpoint(root/"C1", "N0", 30000)

    def test_incomplete_write_is_not_completed_and_no_development_seed(self):
        with TemporaryDirectory() as name:
            with patch.object(calibration.development, "evaluate_panel", return_value=fixture()):
                with patch.object(calibration, "write_json", side_effect=OSError("interrupted")):
                    with self.assertRaises(OSError):
                        calibration.run_repetition(("N0", 30000, name))
            self.assertIsNone(calibration.load_checkpoint(name, "N0", 30000))
            for scenario, repetition in (("N0", 20000), ("N1", 30000), ("N0", 31000)):
                with self.assertRaisesRegex(ValueError, "outside"):
                    calibration.run_repetition((scenario, repetition, name))

    def test_formal_summary_uses_1000_trials_and_excludes_D1(self):
        base, _, _ = fixture()
        records = [dict(base, stage="C1", scenario="N0", repetition=30000+i,
                        false_any=int(i < 50), total_seconds=1., cpu_seconds=.9)
                   for i in range(1000)]
        row = calibration.summarize(records, self.protocol).set_index("scenario").loc["N0"]
        self.assertEqual(row.B, 1000)
        self.assertEqual(row.FWER, .05)
        self.assertAlmostEqual(binom.cdf(50, 1000, row.FWER_upper95), .05)
        self.assertEqual(row.unit_acceptance, "tolerated_pass")
        self.assertEqual(row.stage, "C1")
        partial = calibration.summarize(records[:100], self.protocol).set_index("scenario").loc["N0"]
        self.assertEqual(partial.unit_acceptance, "partial")
        records[0]["stage"] = "D1"
        with self.assertRaisesRegex(ValueError, "Development"):
            calibration.summarize(records, self.protocol)

    def test_aggregate_acceptance_requires_all_units_and_completion(self):
        table = pd.DataFrame(dict(scenario=calibration.SCENARIOS, complete=True,
            unit_acceptance=["not_applicable_all_alternative" if s.startswith("A")
                             else "strict_pass" for s in calibration.SCENARIOS]))
        self.assertEqual(calibration.stage_acceptance(table, self.protocol), "strict_pass")
        table.loc[0, "unit_acceptance"] = "tolerated_pass"
        self.assertEqual(calibration.stage_acceptance(table, self.protocol), "tolerated_pass")
        table.loc[0, "unit_acceptance"] = "inconclusive"
        self.assertEqual(calibration.stage_acceptance(table, self.protocol), "inconclusive")
        table.loc[0, "complete"] = False
        self.assertEqual(calibration.stage_acceptance(table, self.protocol), "incomplete")
        table.loc[1, "unit_acceptance"] = "fail"
        self.assertEqual(calibration.stage_acceptance(table, self.protocol), "fail")

    def test_F0_freezes_once_without_executing_panels(self):
        with TemporaryDirectory() as name:
            root = Path(name)
            old_source = root/".local/dh_v2/simulation/D1/source"
            d1_files = ["experiment_protocol_v2.json", "run_simulation_v2.py", "src/simulation_dh.py",
                        "src/engine_dh.py", "src/simulation.py", "src/engine.py"]
            for file in set(d1_files + list(runner.SOURCE_FILES)) - {runner.PROTOCOL}:
                path = root/file
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(self.development) if file == "experiment_protocol_v2.json"
                                else "unchanged source", encoding="utf-8")
            for file in d1_files:
                destination = old_source/file
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(root/file, destination)
            (root/"results_v2/simulation").mkdir(parents=True)
            calibration.write_json(root/"results_v2/F0_TESTS.json", {"status": "passed"})
            calibration.write_json(root/"results_v2/simulation/D1_status.json",
                                   {"status": "complete", "completed": 1500})
            calibration.write_json(old_source.parent/"environment.json", runner.environment())
            with patch.object(runner, "market_input_evidence", return_value={"fixture": True}) as inputs:
                with patch.object(runner, "run_repetition", side_effect=AssertionError("F0 must not run panels")):
                    first = runner.freeze(root)
                    second = runner.freeze(root)
                inputs.assert_called_once()
            self.assertEqual(first, second)
            self.assertEqual(first["C1_observations_before_freeze"], 0)
            self.assertTrue(first["slow_reversion_power_limitation_accepted"])
            (root/"src/calibration_dh.py").write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "source differs"):
                runner.freeze(root)

    def test_missing_F0_cannot_start_C1_pool(self):
        with TemporaryDirectory() as name:
            with patch.object(runner, "ROOT", Path(name)), patch("sys.argv", ["runner", "--stage", "C1"]):
                with patch.object(runner, "ProcessPoolExecutor") as pool:
                    with self.assertRaises(FileNotFoundError):
                        runner.main()
                    pool.assert_not_called()


if __name__ == "__main__":
    unittest.main()
