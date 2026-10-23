"""Reconcile C2/C3 checkpoints and summaries without recomputing DH/ADF."""
import argparse
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
from src.engine import candidates


def same(actual, expected):
    if expected is None:
        assert actual is None or pd.isna(actual)
    else:
        np.testing.assert_allclose(actual, expected, rtol=2e-12, atol=1e-14)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["C2", "C3"], required=True)
    stage = parser.parse_args().stage
    B, start, stocks, pairs = {"C2": (500, 40000, 120, 1740), "C3": (100, 50000, 2984, 67678)}[stage]
    planned = 5*B
    folder = ROOT/".local/dh_v2/simulation"/stage
    output = ROOT/"results_v2/simulation"
    status = json.loads((output/f"{stage}_status.json").read_text(encoding="utf-8"))
    assert status["status"] == "complete" and status["completed"] == status["planned"] == planned
    assert status[f"{stage}_acceptance"] in ("strict_pass", "tolerated_pass", "inconclusive", "fail")
    assert status["full_market_test"] == "not_run"
    assert status["method_freeze_at"] is not None and status["remote_used"] is False
    frozen = json.loads((ROOT/"results_v2/F0_FREEZE.json").read_text(encoding="utf-8"))
    assert frozen["method_freeze_at"] == status["method_freeze_at"]
    assert all(frozen["method_freeze_at"] < x["started_at"] for x in status["invocations"])
    protocol = json.loads((folder/"source/experiment_protocol_v2_frozen.json").read_text(encoding="utf-8"))
    spec = protocol["simulation"]["stages"][stage]
    scenarios = ["N0", "N5", "N6", "N7", "M1"]
    assert spec["repeats"] == B and spec["repetition_start"] == start and spec["pairs"] == pairs
    expected_keys = {(s, r) for s in scenarios for r in range(start, start+B)}
    actual_keys = {(p.parent.name, int(p.name.split(".")[0]))
                   for p in folder.glob("*/*.pairs.parquet")}
    assert actual_keys == expected_keys
    manifest = json.loads((folder/"tasks.json").read_text(encoding="utf-8"))
    manifest_keys = [(x["scenario"], x["repetition"]) for x in manifest["tasks"]]
    assert len(manifest_keys) == planned and set(manifest_keys) == expected_keys
    if stage == "C2":
        universe = pd.DataFrame([dict(ts_code=f"S{g:02d}{j:03d}", name=f"S{g:02d}{j:03d}",
            L2=f"G{g}", L3=f"G{g}L{j//15}") for g in range(4) for j in range(30)])
        registry = candidates(universe)
    else:
        universe = pd.read_parquet(folder/"geometry/U.parquet")
        registry = pd.read_parquet(folder/"geometry/H.parquet")
        pd.testing.assert_frame_equal(registry, candidates(universe), check_dtype=False, check_exact=True)
        calendar = json.loads((folder/"geometry/freeze.json").read_text(encoding="utf-8"))["calendar"]
        assert len(calendar) == 1212 and calendar == sorted(set(calendar))
    assert len(universe) == stocks and len(registry) == pairs
    pair_codes = list(zip(registry.A.tolist(), registry.B.tolist()))
    stock_codes = universe.ts_code.tolist()
    stock_positions = {code: i for i, code in enumerate(stock_codes)}
    assert len(stock_positions) == stocks
    index_a = np.fromiter((stock_positions[a] for a, _ in pair_codes), dtype=np.intp, count=pairs)
    index_b = np.fromiter((stock_positions[b] for _, b in pair_codes), dtype=np.intp, count=pairs)
    cluster_by_code = {}
    for _, group in universe.sort_values("ts_code").groupby("L2", sort=True):
        for j, code in enumerate(group.ts_code):
            cluster_by_code[code] = j % 5 // 2 if j % 5 < 4 else j
    mixed_truth = np.array([cluster_by_code[a] == cluster_by_code[b] for a, b in pair_codes])
    expected_mixed_A = sum(sum(n*(n-1)//2 for n in pd.Series(
        [j % 5 // 2 if j % 5 < 4 else j for j in range(len(group))]).value_counts())
        for _, group in universe.groupby("L2"))
    assert mixed_truth.sum() == expected_mixed_A
    if stage == "C2":
        assert expected_mixed_A == 528
    records = []
    counts = dict(pair_rows=0, stock_audits=0, underflow=0, ungated_numerically_ineligible=0)
    for scenario, repetition in sorted(expected_keys):
        base = folder/scenario/str(repetition)
        metric = json.loads(base.with_suffix(".json").read_text(encoding="utf-8"))
        gates = json.loads(base.with_suffix(".adf.json").read_text(encoding="utf-8"))
        table = pd.read_parquet(base.with_suffix(".pairs.parquet"))
        assert metric["scenario"] == scenario and metric["repetition"] == repetition and metric["complete"]
        pd.testing.assert_frame_equal(table[registry.columns], registry, check_dtype=False, check_exact=True)
        assert len(table) == pairs and set(gates) == set(universe.ts_code)
        assert metric["stage"] == stage and table.stage.eq(stage).all()
        assert table.scenario.eq(scenario).all() and table.repetition.eq(repetition).all()
        assert table.N_input.eq(1212).all() and table.ungated_N_effective.eq(1204).all()
        assert table.lags.eq(7).all() and table.ungated_lags.eq(7).all() and table.df.eq(2).all()
        for gate in gates.values():
            assert gate["compatible"] == (gate["level"]["p"] >= .05 and gate["difference"]["p"] < .05)
        # Apply stock gates through the exactly matched frozen candidate indices.
        stock_pass = np.fromiter((gates[code]["compatible"] for code in stock_codes), dtype=bool, count=stocks)
        pass_gate = stock_pass[index_a] & stock_pass[index_b]
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
        truth = mixed_truth if scenario == "M1" else np.zeros(pairs, dtype=bool)
        np.testing.assert_array_equal(table.true_alternative, truth)
        valid = pass_gate & raw_valid
        assert np.array_equal(table.compute_status.eq("valid"), valid)
        R, V, A = int(reject.sum()), int((reject & ~truth).sum()), int(truth.sum())
        successes, survivors = int((reject & truth).sum()), int((truth & valid).sum())
        expected = dict(R=R, V=V, A=A, true_nulls=pairs-A, false_any=int(V > 0),
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
                        kernel_calls=pairs, stocks=stocks, pairs=pairs)
        for field, value in expected.items():
            same(metric[field], value)
        records.append(metric)
        if len(records) % (250 if stage == "C2" else 50) == 0:
            print(f"Verified {len(records)}/{planned} {stage} panels", flush=True)
        counts["pair_rows"] += len(table)
        counts["stock_audits"] += len(gates)
        counts["underflow"] += expected["underflow_count"]
        counts["ungated_numerically_ineligible"] += expected["numerical_count"]
    panels = pd.read_csv(output/f"{stage}_panels.csv").sort_values(["scenario", "repetition"]).reset_index(drop=True)
    expected = pd.DataFrame(records).sort_values(["scenario", "repetition"]).reset_index(drop=True)
    pd.testing.assert_frame_equal(panels, expected[panels.columns], check_dtype=False,
                                  check_exact=False, rtol=2e-12, atol=1e-14)
    summary = pd.read_csv(output/f"{stage}_summary.csv").set_index("scenario")
    assert set(summary.index) == set(scenarios) and summary.B.eq(B).all()
    assert summary.complete.all() and summary.assessment_scope.eq(stage+("_1740_pair_geometry" if stage == "C2" else "_67678_pair_frozen_geometry")).all()
    for scenario, group in panels.groupby("scenario"):
        row = summary.loc[scenario]
        assert len(group) == spec["repeats"] == B
        has_nulls = not scenario.startswith("A")
        k = int(group.false_any.sum())
        if has_nulls:
            same(row.FWER, k/B)
            same(row.FWER_MCSE, np.sqrt((k/B)*(1-k/B)/B))
            if k:
                same(binom.sf(k-1, B, row.FWER_lower95), .05)
            else:
                same(row.FWER_lower95, 0.)
            if k < B:
                same(binom.cdf(k, B, row.FWER_upper95), .05)
            else:
                same(row.FWER_upper95, 1.)
            classification = ("strict_pass" if row.FWER_upper95 <= .05 else
                              "tolerated_pass" if row.FWER_upper95 <= .10 else
                              "fail" if row.FWER_lower95 > .10 else "inconclusive")
            assert row.unit_acceptance == classification
        else:
            assert pd.isna(row.FWER) and row.unit_acceptance == "not_applicable_all_alternative"
        for field in ("power", "conditional_power", "FDP", "raw_null_rejection", "stock_I1_fraction"):
            values = group[field].dropna()
            same(row[field], values.mean() if len(values) else None)
            same(row[field+"_MCSE"], values.std(ddof=1)/np.sqrt(len(values)) if len(values) > 1 else None)
            assert row[field+"_B"] == len(values)
        for field in ("R", "V", "A", "true_nulls", "true_discoveries", "valid_alternatives",
                      "precheck_placeholders", "valid_pairs", "numerical_count",
                      "gated_numerical_count", "underflow_count", "kernel_calls"):
            assert row[field+"_total"] == group[field].sum()
    required = summary.loc[protocol["acceptance"]["required_C2_C3_scenarios"], "unit_acceptance"]
    expected_acceptance = ("fail" if required.eq("fail").any() else
                           "strict_pass" if required.eq("strict_pass").all() else
                           "tolerated_pass" if required.isin(["strict_pass", "tolerated_pass"]).all()
                           else "inconclusive")
    assert status[f"{stage}_acceptance"] == expected_acceptance
    previous = ["C1"] if stage == "C2" else ["C1", "C2"]
    all_acceptances = [expected_acceptance] + [json.loads((output/f"{name}_status.json").read_text(
        encoding="utf-8"))[f"{name}_acceptance"] for name in previous]
    expected_overall = ("fail" if "fail" in all_acceptances else
        "incomplete_C3_not_run" if stage == "C2" else
        "inconclusive" if "inconclusive" in all_acceptances else
        "strict_pass" if all(x == "strict_pass" for x in all_acceptances) else "tolerated_pass")
    assert status["overall_protocol_acceptance"] == expected_overall
    pilot = json.loads((output/f"{stage}_pilot_evidence.json").read_text(encoding="utf-8"))
    assert len(pilot["checkpoints"]) == pilot["panels"] == status["invocations"][0]["newly_completed"]
    for entry in pilot["checkpoints"]:
        saved = (ROOT/entry["path"]).stat()
        assert saved.st_mtime_ns == entry["mtime_ns"] and saved.st_size == entry["bytes"]
    assert counts["pair_rows"] == planned*pairs and counts["stock_audits"] == planned*stocks
    result = dict(status="passed_engineering_and_summary_reconciliation",
                  checked_at=datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
                  panels=planned, **counts, unit_tests_passed=44, mixed_alternative_pairs_per_panel=int(expected_mixed_A),
                  verification="all pair identities, known truth, ADF gates, independent Holm, metrics, CP binomial tails and summaries",
                  DH_or_ADF_recomputed=False, formal_calibration="C1_C2_complete_C3_not_run" if stage == "C2" else "C1_C2_C3_complete", market_test="not_run",
                  pilot_checkpoints_unchanged=len(pilot["checkpoints"]),
                  method_freeze_precedes_all_stage_invocations=True,
                  remote_used=False, statistical_acceptance=status[f"{stage}_acceptance"],
                  overall_protocol_acceptance=status["overall_protocol_acceptance"])
    (output/f"{stage}_validation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n",
                                             encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
