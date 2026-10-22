import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from scipy.stats import binom

from run_simulation_v2 import ROOT, SOURCE_FILES, parser, prepare_run
from src.simulation_dh import (confidence_bounds, diagnostic_classification,
                               load_checkpoint, panel_metrics, run_repetition,
                               summarize, task_keys, validate_protocol)


def example_table(n=4):
    return pd.DataFrame(dict(
        candidate_id=[str(i) for i in range(n)], true_alternative=[True, True]+[False]*(n-2),
        reject_GLOBAL_Holm=[True, False, True]+[False]*(n-3),
        compute_status=["valid", "precheck_placeholder"]+["valid"]*(n-2),
        ungated_p_for_adjustment=[.001, .001, .01]+[1.]*(n-3),
        ungated_compute_status=["valid"]*n, ungated_p_zero_origin=[None]*n))


class DHSimulationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol = json.loads((ROOT/"experiment_protocol_v2.json").read_text(encoding="utf-8"))

    def test_fixed_protocol_tasks_and_independent_seed_ranges(self):
        validate_protocol(self.protocol)
        keys = task_keys(self.protocol)
        self.assertEqual(len(keys), 1500)
        self.assertEqual(len(set(keys)), 1500)
        self.assertEqual(keys[0], ("N0", 20000))
        self.assertEqual(keys[-1], ("M1", 20099))
        samples = []
        for spec in self.protocol["simulation"]["stages"].values():
            current = {(spec["geometry_id"], s, r) for s in spec["scenarios"]
                       for r in range(spec["repetition_start"], spec["repetition_start"]+spec["repeats"])}
            self.assertTrue(all(not current.intersection(old) for old in samples))
            samples.append(current)
            self.assertNotIn("N1", spec["scenarios"])
        altered = copy.deepcopy(self.protocol)
        altered["correction"]["alpha"] = .10
        with self.assertRaisesRegex(ValueError, "correction.alpha"):
            validate_protocol(altered)
        with patch("sys.stderr"), self.assertRaises(SystemExit):
            parser().parse_args(["--stage", "C1"])

    def test_whole_panel_metrics_and_unconditional_denominator(self):
        metric = panel_metrics(example_table(), {str(i): {"compatible": i != 1} for i in range(4)})
        self.assertEqual((metric["R"], metric["V"], metric["A"]), (2, 1, 2))
        self.assertEqual(metric["false_any"], 1)
        self.assertEqual(metric["FDP"], .5)
        self.assertEqual(metric["power"], .5)
        self.assertEqual(metric["conditional_power"], 1.)
        self.assertEqual(metric["raw_null_rejection"], .5)
        self.assertEqual(metric["stock_I1_fraction"], .75)
        self.assertEqual(metric["precheck_placeholders"], 1)

    def test_exact_bounds_against_binomial_tail_and_zero_events(self):
        low, high = confidence_bounds(5, 100)
        self.assertAlmostEqual(binom.sf(4, 100, low), .05)
        self.assertAlmostEqual(binom.cdf(5, 100, high), .05)
        self.assertAlmostEqual(confidence_bounds(0, 100)[1], 1-.05**.01)
        self.assertEqual(confidence_bounds(100, 100)[1], 1)
        self.assertEqual(confidence_bounds(0, 0), (None, None))
        self.assertEqual(diagnostic_classification(0., .049), "strict_pass")
        self.assertEqual(diagnostic_classification(.02, .08), "tolerated_pass")
        self.assertEqual(diagnostic_classification(.11, .2), "fail")
        self.assertEqual(diagnostic_classification(.05, .15), "inconclusive")

    def test_partial_and_all_alternative_are_not_acceptance(self):
        metric = panel_metrics(example_table(), {str(i): {"compatible": True} for i in range(4)})
        metric.update(scenario="N0", repetition=20000, total_seconds=1., cpu_seconds=.8)
        result = summarize([metric], self.protocol).set_index("scenario")
        self.assertEqual(result.loc["N0", "B"], 1)
        self.assertEqual(result.loc["N0", "planned_B"], 100)
        self.assertEqual(result.loc["N0", "development_diagnostic"], "partial")
        self.assertEqual(result.loc["N2", "development_diagnostic"], "not_run")
        metrics = [dict(metric, scenario="A0", repetition=r, false_any=0, V=0,
                        true_nulls=0) for r in range(20000, 20100)]
        result = summarize(metrics, self.protocol).set_index("scenario")
        self.assertTrue(pd.isna(result.loc["A0", "FWER"]))
        self.assertEqual(result.loc["A0", "development_diagnostic"], "not_applicable_all_alternative")
        self.assertTrue(result.formal_acceptance.eq("not_assessed_development_only").all())
        with self.assertRaisesRegex(ValueError, "Repeated panel"):
            summarize([metric, metric], self.protocol)

    def test_checkpoint_commit_order_resume_and_missing_pairs(self):
        full = example_table(180)
        gates = {str(i): {"compatible": True} for i in range(40)}
        metric = panel_metrics(full, gates)
        with TemporaryDirectory() as name:
            task = ("N0", 20000, name)
            with patch("src.simulation_dh.evaluate_panel", return_value=(metric, full, gates)):
                with patch("src.simulation_dh.write_json", side_effect=OSError("interrupted write")):
                    with self.assertRaises(OSError):
                        run_repetition(task)
                self.assertIsNone(load_checkpoint(name, "N0", 20000))
                original = run_repetition(task)
            marker = Path(name)/"N0/20000.json"
            saved = marker.read_bytes()
            with patch("src.simulation_dh.evaluate_panel", side_effect=AssertionError("must reuse")):
                self.assertEqual(run_repetition(task), original)
            self.assertEqual(marker.read_bytes(), saved)
            (Path(name)/"N0/20000.pairs.parquet").unlink()
            with self.assertRaises(FileNotFoundError):
                load_checkpoint(name, "N0", 20000)

    def test_snapshot_rejects_changed_source_without_overwriting(self):
        with TemporaryDirectory() as name:
            root, folder = Path(name)/"project", Path(name)/"run"
            for source in SOURCE_FILES:
                path = root/source
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("original", encoding="utf-8")
            prepare_run(root, folder, self.protocol)
            prepare_run(root, folder, self.protocol)
            (root/"src/engine_dh.py").write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "source differs"):
                prepare_run(root, folder, self.protocol)
            self.assertEqual((folder/"source/src/engine_dh.py").read_text(), "original")


if __name__ == "__main__":
    unittest.main()
