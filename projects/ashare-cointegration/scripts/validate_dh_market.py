"""Independently reconcile the full frozen DH market output; no DH/ADF rerun."""
from datetime import datetime
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from scipy.stats import chi2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.validate_production import adjustment
from src.engine import candidates
from src.simulation_dh import write_json


def main():
    output = ROOT/"results_v2"
    protocol = json.loads((ROOT/"experiment_protocol_v2_frozen.json").read_text(encoding="utf-8"))
    source = ROOT/".local/production"/protocol["market"]["input_run_id"]
    state = json.loads((output/"market_status.json").read_text(encoding="utf-8"))
    assert state["run_id"] == protocol["market"]["run_id"]+"__used-prefix"
    run = ROOT/".local/dh_v2/production"/state["run_id"]
    assert state["status"] == "complete" and state["completed"] == state["planned"] == 67678
    assert state["method_freeze_at"] == protocol["method_freeze_at"] and not state["remote_used"]
    assert all(state["method_freeze_at"] < x["started_at"] for x in state["invocations"])
    units = []
    for stage, repeats in (("C1", 1000), ("C2", 500), ("C3", 100)):
        table = pd.read_csv(output/f"simulation/{stage}_summary.csv").set_index("scenario")
        required = protocol["acceptance"]["required_C1_scenarios" if stage == "C1" else "required_C2_C3_scenarios"]
        required_table = table.loc[required]
        assert required_table.complete.all() and required_table.B.eq(repeats).all()
        check = json.loads((output/f"simulation/{stage}_validation.json").read_text(encoding="utf-8"))
        assert check["status"] == "passed_engineering_and_summary_reconciliation"
        assert check["statistical_acceptance"] in ("strict_pass", "tolerated_pass", "inconclusive")
        for scenario, row in required_table.iterrows():
            classification = ("strict_pass" if row.FWER_upper95 <= .05 else
                              "tolerated_pass" if row.FWER_upper95 <= .10 else
                              "fail" if row.FWER_lower95 > .10 else "inconclusive")
            assert row.unit_acceptance == classification
            units.append(dict(stage=stage, scenario=scenario, acceptance=classification))
    assert len(units) == 19
    assert not any(x["acceptance"] == "fail" for x in units)
    assert all(x["stage"] == "C3" for x in units if x["acceptance"] == "inconclusive")
    overall = ("inconclusive" if any(x["acceptance"] == "inconclusive" for x in units) else
               "strict_pass" if all(x["acceptance"] == "strict_pass" for x in units) else "tolerated_pass")
    assert state["calibration_acceptance"] == overall
    scope = "nominal_calibration_inconclusive" if overall == "inconclusive" else "nominal_with_calibration_evidence"
    assert state["evidence_scope"] == scope
    if overall == "inconclusive":
        assert all(x["nominal_if_inconclusive"] for x in state["invocations"])
    universe = pd.read_parquet(run/"U.parquet")
    registry = pd.read_parquet(run/"H.parquet")
    full = pd.read_parquet(run/"full_results.parquet")
    pd.testing.assert_frame_equal(registry, candidates(universe), check_dtype=False, check_exact=True)
    pd.testing.assert_frame_equal(full[registry.columns], registry, check_dtype=False, check_exact=True)
    assert len(universe) == 2984 and len(full) == 67678
    assert full.input_version.eq(source.name).all() and full.method_version.eq("2.1-DH").all()
    assert full.direction.eq(protocol["method"]["direction"]).all()
    assert full.implementation_revision.eq("used_recursive_prefix_guard").all()
    assert full.calibration_acceptance.eq(overall).all() and full.evidence_scope.eq(scope).all()
    assert full.N_input.eq(1212).all() and full.lags.eq(7).all() and full.df.eq(2).all()
    gates = json.loads((run/"ADF.json").read_text(encoding="utf-8"))
    assert (run/"ADF.json").read_bytes() == (source/"ADF.json").read_bytes()
    assert set(gates) == set(universe.ts_code) and state["precheck_reused"]
    stock_codes = universe.ts_code.tolist()
    positions = {code: i for i, code in enumerate(stock_codes)}
    stock_pass = np.fromiter((gates[code]["compatible"] for code in stock_codes), dtype=bool, count=len(stock_codes))
    index_a = np.fromiter((positions[code] for code in registry.A.tolist()), dtype=np.intp, count=len(registry))
    index_b = np.fromiter((positions[code] for code in registry.B.tolist()), dtype=np.intp, count=len(registry))
    compatible = stock_pass[index_a] & stock_pass[index_b]
    np.testing.assert_array_equal(full.compute_status.eq("precheck_placeholder"), ~compatible)
    assert full.compute_status.isin(["valid", "precheck_placeholder", "numerically_ineligible"]).all()
    valid = full.compute_status.eq("valid")
    assert full.loc[valid, "N_effective"].eq(1204).all()
    assert full.loc[~valid, "p_for_adjustment"].eq(1.).all()
    np.testing.assert_array_equal(full.loc[valid, "log_p"], -full.loc[valid, "Q"]/2)
    np.testing.assert_allclose(full.loc[valid, "p_raw"], chi2.sf(full.loc[valid, "Q"], 2), rtol=2e-12, atol=1e-300)
    np.testing.assert_array_equal(full.loc[valid, "p_for_adjustment"], full.loc[valid, "p_raw"])
    corrected = adjustment(full.p_for_adjustment.to_numpy(), "Holm")
    np.testing.assert_allclose(full.p_GLOBAL_Holm, corrected, rtol=2e-14, atol=0)
    np.testing.assert_array_equal(full.reject_GLOBAL_Holm, corrected <= .05)
    for _, indices in full.groupby("L2").groups.items():
        expected = adjustment(full.loc[indices, "p_for_adjustment"].to_numpy(), "Holm")
        np.testing.assert_allclose(full.loc[indices, "p_L2_Holm"], expected, rtol=2e-14, atol=0)
        np.testing.assert_array_equal(full.loc[indices, "reject_L2_Holm"], expected <= .05)
    main = full.loc[valid & (corrected <= .05)].reset_index(drop=True)
    saved_main = pd.read_csv(output/"main_evidence.csv", dtype={"L2": str, "L3_A": str, "L3_B": str, "L3_family": str})
    pd.testing.assert_frame_equal(saved_main, main[saved_main.columns], check_dtype=False,
                                  check_exact=False, rtol=2e-12, atol=1e-14)
    previous = pd.read_parquet(source/"full_results.parquet")
    assert previous.candidate_id.tolist() == full.candidate_id.tolist()
    comparison = pd.read_csv(output/"v1_dh_comparison.csv", dtype={"L2": str})
    assert comparison.calibration_acceptance.eq(overall).all() and comparison.evidence_scope.eq(scope).all()
    identity = ["candidate_id", "A", "B", "L2", "layer"]
    pd.testing.assert_frame_equal(comparison[identity], registry[identity], check_dtype=False, check_exact=True)
    counts = {}
    for prefix, table in (("V1_EG", previous), ("V2_DH", full)):
        for domain in ("L2", "GLOBAL"):
            key = f"{prefix}_{domain}_Holm"
            np.testing.assert_array_equal(comparison[key], table[f"reject_{domain}_Holm"])
            counts[key] = int(comparison[key].sum())
    assert state["method_counts"] == counts
    assert counts["V1_EG_L2_Holm"] == 110 and counts["V1_EG_GLOBAL_Holm"] == 7
    before = set(previous.loc[previous.reject_L2_Holm, "candidate_id"])
    after = set(main.candidate_id)
    overlap = dict(intersection=len(before & after), V1_only=len(before-after), DH_only=len(after-before),
                   union=len(before | after), Jaccard=len(before & after)/len(before | after))
    assert state["primary_overlap"] == overlap and state["discoveries"] == len(main)
    assert state["valid_DH"] == int(valid.sum())
    assert state["DH_executed"] == int(full.DH_executed.sum())
    assert state["precheck_placeholders"] == int((~compatible).sum())
    assert state["numerical_placeholders"] == int(full.compute_status.eq("numerically_ineligible").sum())
    assert state["underflow"] == int(full.p_zero_origin.eq("exp_underflow").sum())
    assert state["prefix_guard_corrected"] == int(full.prefix_guard_corrected.sum())
    result = dict(status="passed_engineering_and_summary_reconciliation",
        checked_at=datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        run_id=run.name, stocks=2984, candidates=67678, main_discoveries=len(main),
        main_T=int(main.layer.eq("T").sum()), main_C=int(main.layer.eq("C").sum()),
        valid_DH=int(valid.sum()), precheck_placeholders=int((~compatible).sum()),
        numerical_placeholders=state["numerical_placeholders"], underflow=state["underflow"],
        prefix_guard_corrected=state["prefix_guard_corrected"], implementation_revision="used_recursive_prefix_guard",
        method_counts=counts, primary_overlap=overlap, required_calibration_units=units,
        calibration_acceptance=overall, evidence_scope=scope, DH_or_ADF_recomputed=False, remote_used=False,
        limitation="Calibration is limited to the frozen artificial mechanisms and geometries; no unconditional market or trading guarantee")
    write_json(output/"market_validation.json", result)
    state.update(market_validation="passed", verified_at=result["checked_at"])
    write_json(output/"market_status.json", state)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
