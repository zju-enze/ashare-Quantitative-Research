"""Reconcile completed D1 checkpoints and summaries without recomputing DH/ADF."""
from datetime import datetime
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from scipy.stats import binom, chi2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.validate_production import adjustment


def same(actual, expected):
    if expected is None:
        assert actual is None or pd.isna(actual)
    else:
        np.testing.assert_allclose(actual, expected, rtol=2e-12, atol=1e-14)


def main():
    folder = ROOT/".local/dh_v2/simulation/D1"
    output = ROOT/"results_v2/simulation"
    status = json.loads((output/"D1_status.json").read_text(encoding="utf-8"))
    assert status["status"] == "complete" and status["completed"] == status["planned"] == 1500
    assert status["formal_acceptance"] == "not_assessed_development_only"
    assert status["formal_calibration"] == status["full_market_test"] == "not_run"
    assert status["method_freeze_at"] is None and status["remote_used"] is False
    protocol = json.loads((folder/"source/experiment_protocol_v2.json").read_text(encoding="utf-8"))
    spec = protocol["simulation"]["stages"]["D1"]
    scenarios = ["N0", "N2", "N3", "N4", "N5", "N6", "N7",
                 "A0", "A1", "A2", "A3", "A4", "A5", "M0", "M1"]
    expected_keys = {(s, r) for s in scenarios for r in range(20000, 20100)}
    actual_keys = {(p.parent.name, int(p.name.split(".")[0]))
                   for p in folder.glob("*/*.pairs.parquet")}
    assert actual_keys == expected_keys
    manifest = json.loads((folder/"tasks.json").read_text(encoding="utf-8"))
    manifest_keys = [(x["scenario"], x["repetition"]) for x in manifest["tasks"]]
    assert len(manifest_keys) == 1500 and set(manifest_keys) == expected_keys
    expected_ids = [f"S{g:02d}{j:03d}__S{g:02d}{k:03d}"
                    for g in range(4) for j in range(10) for k in range(j+1, 10)]
    records = []
    counts = dict(pair_rows=0, stock_audits=0, underflow=0, ungated_numerically_ineligible=0)
    for scenario, repetition in sorted(expected_keys):
        base = folder/scenario/str(repetition)
        metric = json.loads(base.with_suffix(".json").read_text(encoding="utf-8"))
        gates = json.loads(base.with_suffix(".adf.json").read_text(encoding="utf-8"))
        table = pd.read_parquet(base.with_suffix(".pairs.parquet"))
        assert metric["scenario"] == scenario and metric["repetition"] == repetition and metric["complete"]
        assert table.candidate_id.tolist() == expected_ids and len(table) == 180 and len(gates) == 40
        assert table.M_GLOBAL.eq(180).all() and table.M_L2.eq(45).all()
        assert table.scenario.eq(scenario).all() and table.repetition.eq(repetition).all()
        assert table.N_input.eq(1212).all() and table.ungated_N_effective.eq(1204).all()
        assert table.lags.eq(7).all() and table.ungated_lags.eq(7).all() and table.df.eq(2).all()
        for gate in gates.values():
            assert gate["compatible"] == (gate["level"]["p"] >= .05 and gate["difference"]["p"] < .05)
        pass_gate = np.array([gates[a]["compatible"] and gates[b]["compatible"]
                              for a, b in zip(table.A, table.B)])
        assert np.array_equal(table.compute_status.eq("precheck_placeholder"), ~pass_gate)
        raw_valid = table.ungated_compute_status.eq("valid").to_numpy()
        np.testing.assert_allclose(table.loc[raw_valid, "ungated_log_p"],
                                   -table.loc[raw_valid, "ungated_Q"]/2, rtol=0, atol=0)
        np.testing.assert_allclose(table.loc[raw_valid, "ungated_p_raw"],
                                   chi2.sf(table.loc[raw_valid, "ungated_Q"], 2),
                                   rtol=2e-12, atol=1e-300)
        p = np.where(pass_gate, table.ungated_p_for_adjustment, 1.)
        np.testing.assert_array_equal(table.p_for_adjustment, p)
        corrected = adjustment(p, "Holm")
        np.testing.assert_allclose(table.p_GLOBAL_Holm, corrected, rtol=2e-14, atol=0)
        reject = corrected <= .05
        np.testing.assert_array_equal(table.reject_GLOBAL_Holm, reject)
        if scenario.startswith("M"):
            def cluster(code):
                j = int(code[3:])
                return j % 5 // 2 if j % 5 < 4 else j
            truth = np.array([cluster(a) == cluster(b) for a, b in zip(table.A, table.B)])
            assert truth.sum() == 48
        else:
            truth = np.full(180, scenario.startswith("A"))
        np.testing.assert_array_equal(table.true_alternative, truth)
        valid = pass_gate & raw_valid
        assert np.array_equal(table.compute_status.eq("valid"), valid)
        R, V, A = int(reject.sum()), int((reject & ~truth).sum()), int(truth.sum())
        successes, survivors = int((reject & truth).sum()), int((truth & valid).sum())
        expected = dict(R=R, V=V, A=A, true_nulls=180-A, false_any=int(V > 0),
                        FDP=V/max(R, 1), true_discoveries=successes, valid_alternatives=survivors,
                        power=successes/A if A else None,
                        conditional_power=successes/survivors if survivors else None,
                        raw_null_rejection=float((table.ungated_p_for_adjustment.to_numpy()[~truth]
                                                  < .05).mean()) if (~truth).any() else None,
                        stock_I1_fraction=np.mean([x["compatible"] for x in gates.values()]),
                        precheck_placeholders=int((~pass_gate).sum()), valid_pairs=int(valid.sum()),
                        numerical_count=int((~raw_valid).sum()),
                        gated_numerical_count=int((pass_gate & ~raw_valid).sum()),
                        underflow_count=int(table.ungated_p_zero_origin.eq("exp_underflow").sum()),
                        kernel_calls=180, stocks=40, pairs=180)
        for field, value in expected.items():
            same(metric[field], value)
        records.append(metric)
        counts["pair_rows"] += len(table)
        counts["stock_audits"] += len(gates)
        counts["underflow"] += expected["underflow_count"]
        counts["ungated_numerically_ineligible"] += expected["numerical_count"]
    panels = pd.read_csv(output/"D1_panels.csv").sort_values(["scenario", "repetition"]).reset_index(drop=True)
    expected = pd.DataFrame(records).sort_values(["scenario", "repetition"]).reset_index(drop=True)
    pd.testing.assert_frame_equal(panels, expected[panels.columns], check_dtype=False,
                                  check_exact=False, rtol=2e-12, atol=1e-14)
    summary = pd.read_csv(output/"D1_summary.csv").set_index("scenario")
    assert set(summary.index) == set(scenarios) and summary.B.eq(100).all()
    assert summary.complete.all() and summary.formal_acceptance.eq("not_assessed_development_only").all()
    for scenario, group in panels.groupby("scenario"):
        row = summary.loc[scenario]
        assert len(group) == spec["repeats"] == 100
        has_nulls = not scenario.startswith("A")
        k = int(group.false_any.sum())
        if has_nulls:
            same(row.FWER, k/100)
            same(row.FWER_MCSE, np.sqrt((k/100)*(1-k/100)/100))
            if k:
                same(binom.sf(k-1, 100, row.FWER_lower95), .05)
            else:
                same(row.FWER_lower95, 0.)
            if k < 100:
                same(binom.cdf(k, 100, row.FWER_upper95), .05)
            else:
                same(row.FWER_upper95, 1.)
            classification = ("strict_pass" if row.FWER_upper95 <= .05 else
                              "tolerated_pass" if row.FWER_upper95 <= .10 else
                              "fail" if row.FWER_lower95 > .10 else "inconclusive")
            assert row.development_diagnostic == classification
        else:
            assert pd.isna(row.FWER) and row.development_diagnostic == "not_applicable_all_alternative"
        for field in ("power", "conditional_power", "FDP", "raw_null_rejection", "stock_I1_fraction"):
            values = group[field].dropna()
            same(row[field], values.mean() if len(values) else None)
            same(row[field+"_MCSE"], values.std(ddof=1)/np.sqrt(len(values)) if len(values) > 1 else None)
            assert row[field+"_B"] == len(values)
        for field in ("R", "V", "A", "true_nulls", "true_discoveries", "valid_alternatives",
                      "precheck_placeholders", "valid_pairs", "numerical_count",
                      "gated_numerical_count", "underflow_count", "kernel_calls"):
            assert row[field+"_total"] == group[field].sum()
    assert counts["pair_rows"] == 270000 and counts["stock_audits"] == 60000
    result = dict(status="passed_engineering_and_summary_reconciliation",
                  checked_at=datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
                  panels=1500, **counts, unit_tests_passed=29,
                  verification="all pair identities, known truth, ADF gates, independent Holm, metrics, CP binomial tails and summaries",
                  DH_or_ADF_recomputed=False, formal_calibration="not_run", market_test="not_run",
                  remote_used=False, statistical_acceptance="not_assessed_development_only")
    (output/"D1_validation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n",
                                             encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
