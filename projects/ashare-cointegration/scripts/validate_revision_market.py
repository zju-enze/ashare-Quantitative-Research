"""Reconcile the complete revised-market output and predeclared reference cases."""
import os
for key in ("OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "OMP_NUM_THREADS"):
    os.environ[key] = "1"
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import json
import shutil
import warnings

import numpy as np
import pandas as pd
from statsmodels.tsa.adfvalues import mackinnonp
from statsmodels.tsa.stattools import coint
import run_market_revision as market
from tests.test_engine_dh import literal_reference


def reference_holm(values):
    p = np.asarray(values, dtype=float)
    order = np.argsort(p, kind="stable")
    corrected = np.minimum(1., np.maximum.accumulate(p[order] * np.arange(len(p), 0, -1)))
    result = np.empty(len(p))
    result[order] = corrected
    return result


def main():
    np.testing.assert_allclose(reference_holm([.01, .04, .02, 1.]), [.04, .08, .06, 1.])
    run, output = market.RUN, market.OUTPUT
    protocol = json.loads((run / "protocol.json").read_text(encoding="utf-8"))
    registry = pd.read_parquet(run / "H.parquet")
    universe = pd.read_parquet(run / "U.parquet")
    full = pd.read_parquet(run / "full_results.parquet")
    prices = np.load(run / "prices.npy", mmap_mode="r")
    values = np.load(run / "log_prices.npy", mmap_mode="r")
    np.testing.assert_array_equal(values, np.log(prices))
    assert values.shape == (1212, 2984)
    assert len(full) == 270712 and len(registry) == 67678
    assert full.method.value_counts().to_dict() == {m:67678 for m in market.METHODS}
    assert not full.duplicated(["candidate_id", "method"]).any()
    for name in market.INPUT_FILES:
        assert (market.INPUT / name).read_bytes() == (run / name).read_bytes(), name
    for name in market.SOURCE_FILES:
        assert (market.ROOT / name).read_bytes() == (run / "source" / name).read_bytes(), name
    diagnostics = json.loads((run / "stock_ADF_diagnostics.json").read_text(encoding="utf-8"))
    assert set(diagnostics) == set(universe.ts_code)
    for result in diagnostics.values():
        if result["level"] is not None:
            expected = result["level"]["p"] >= .05 and result["difference"]["p"] < .05
            assert result["compatible"] == expected
    saved_summary = pd.read_csv(output / "summary.csv").set_index("method")
    checked_groups = 0
    discovery_diagnostics = []
    for method in market.METHODS:
        part = full.loc[full.method.eq(method)].reset_index(drop=True)
        pd.testing.assert_frame_equal(part[registry.columns], registry.reset_index(drop=True),
                                      check_dtype=False, check_exact=True)
        valid = part.status.isin(market.VALID)
        assert part.loc[~valid, "p"].eq(1.).all()
        assert part.p.between(0, 1).all()
        assert not part.status.eq("precheck_placeholder").any()
        expected_compatible = (part.A.map(lambda code: diagnostics[code]["compatible"])
                               & part.B.map(lambda code: diagnostics[code]["compatible"]))
        np.testing.assert_array_equal(part.both_I1_compatible_diagnostic, expected_compatible)
        if method.startswith("EG"):
            p = [mackinnonp(stat, regression="c", N=2)
                 for stat in part.loc[valid, "statistic"]]
            np.testing.assert_allclose(part.loc[valid, "p"], p, rtol=1e-10, atol=1e-15)
            if method == "EG-fixed-1":
                assert part.loc[valid, "used_lag"].eq(1).all()
        else:
            lag = 1 if method == "DH-fixed-1" else 7
            assert part.loc[valid, "used_lag"].eq(lag).all()
            np.testing.assert_allclose(part.loc[valid, "log_p"], -part.loc[valid, "statistic"]/2,
                                       rtol=1e-12, atol=1e-12)
            np.testing.assert_allclose(part.loc[valid, "p"], np.exp(part.loc[valid, "log_p"]),
                                       rtol=1e-12, atol=1e-15)
        assert np.all(part.loc[valid, "n_effective"] == 1212-part.loc[valid, "used_lag"]-1)
        for domain in ("GLOBAL", "L2"):
            groups = [part.index] if domain == "GLOBAL" else part.groupby("L2").groups.values()
            for indices in groups:
                expected = reference_holm(part.loc[indices, "p"])
                np.testing.assert_allclose(part.loc[indices, f"p_{domain}_Holm"], expected,
                                           rtol=1e-12, atol=1e-15)
                np.testing.assert_array_equal(part.loc[indices, f"reject_{domain}_Holm"], expected <= .05)
                checked_groups += 1
            expected_rows = part.loc[part[f"reject_{domain}_Holm"]].sort_values("candidate_id")
            published = pd.read_csv(output / f"{method}_{domain}_Holm.csv",
                                    dtype={"candidate_id":str, "A":str, "B":str, "L2":str})
            assert published.candidate_id.tolist() == expected_rows.candidate_id.tolist()
            for col in ("p", "p_raw", "p_L2_Holm", "p_GLOBAL_Holm", "log_ols_beta"):
                np.testing.assert_allclose(published[col].to_numpy(dtype=float),
                                           expected_rows[col].to_numpy(dtype=float),
                                           rtol=1e-10, atol=1e-15)
            np.testing.assert_array_equal(published.both_I1_compatible_diagnostic,
                                          expected_rows.both_I1_compatible_diagnostic)
            assert saved_summary.loc[method, domain+"_Holm"] == len(expected_rows)
            discovery_diagnostics.append(dict(
                method=method, domain=domain, discoveries=len(expected_rows),
                both_I1_compatible=int(expected_rows.both_I1_compatible_diagnostic.sum()),
                applicability_warning=int((~expected_rows.both_I1_compatible_diagnostic).sum()),
                nonpositive_OLS_beta=int(expected_rows.log_ols_beta.le(0).sum()),
                zero_p=int(expected_rows.p.eq(0).sum())))
        assert saved_summary.loc[method, "effective"] == valid.sum()
        assert saved_summary.loc[method, "numerical_unavailable"] == (~valid).sum()
        assert saved_summary.loc[method, "raw_p_below_005"] == part.p.lt(.05).sum()
    families = pd.read_csv(output / "families.csv")
    for method in market.METHODS:
        for domain in ("L2", "GLOBAL"):
            fam = families.loc[families.method.eq(method) & families.domain.eq(domain)]
            assert fam.candidates.sum() == 67678
            assert fam.discoveries.sum() == saved_summary.loc[method, domain+"_Holm"]
    codes = {code:i for i,code in enumerate(universe.ts_code)}
    reference_cases = []
    for index in protocol["independent_reference_candidate_positions"]:
        candidate = registry.iloc[index]
        a, b = values[:, codes[candidate.A]], values[:, codes[candidate.B]]
        for method in market.METHODS:
            saved = full.loc[full.candidate_id.eq(candidate.candidate_id) & full.method.eq(method)].iloc[0]
            if saved.status not in market.VALID:
                reference_cases.append(dict(position=index, candidate_id=candidate.candidate_id,
                                            method=method, status="unavailable", reason=saved.placeholder_reason))
                continue
            if method.startswith("EG"):
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    expected, p, _ = coint(a, b, trend="c",
                                          maxlag=1 if method=="EG-fixed-1" else None,
                                          autolag=None if method=="EG-fixed-1" else "aic")
            else:
                check = literal_reference(a, b, 1 if method=="DH-fixed-1" else 7)
                expected, p = check["Q"], float(np.exp(-check["Q"]/2))
            np.testing.assert_allclose(saved.statistic, expected, rtol=1e-6, atol=1e-9)
            np.testing.assert_allclose(saved.p, p, rtol=1e-6, atol=1e-12)
            reference_cases.append(dict(position=index, candidate_id=candidate.candidate_id,
                                        method=method, status="matched",
                                        statistic_absolute_error=float(abs(saved.statistic-expected))))
    overlap = pd.read_csv(output / "overlap.csv").set_index("domain")
    for domain in ("L2", "GLOBAL"):
        flag = "reject_"+domain+"_Holm"
        a = set(full.loc[full.method.eq("EG-fixed-1") & full[flag], "candidate_id"])
        b = set(full.loc[full.method.eq("DH-fixed-1") & full[flag], "candidate_id"])
        assert overlap.loc[domain, "intersection"] == len(a & b)
        assert overlap.loc[domain, "EG_only"] == len(a-b)
        assert overlap.loc[domain, "DH_only"] == len(b-a)
    record = dict(status="passed", checked_at=market.now(), test_rows=len(full), candidates=len(registry),
                  stock_diagnostics=len(diagnostics), method_domain_families_checked=checked_groups,
                  independent_reference_cases=reference_cases,
                  independent_numeric_reference_calls=sum(r["status"]=="matched" for r in reference_cases),
                  full_retest=False, frozen_inputs_and_statistical_sources_unchanged=True,
                  diagnostic_gate_applied=False, calibration_validation=False)
    market.write_json(output / "validation.json", record)
    pd.DataFrame(discovery_diagnostics).to_csv(output / "discovery_diagnostics.csv", index=False)
    completion = json.loads((output / "COMPLETION.json").read_text(encoding="utf-8"))
    completion.update(status="complete_verified_nominal_market", independent_validation="passed",
                      verified_at=record["checked_at"])
    market.write_json(output / "COMPLETION.json", completion)
    validation_source = run / "validation_source"
    validation_source.mkdir(exist_ok=True)
    shutil.copy2(__file__, validation_source / Path(__file__).name)
    shutil.copy2(market.ROOT / "tests/test_engine_dh.py", validation_source / "test_engine_dh.py")
    print(json.dumps({k:v for k,v in record.items() if k != "independent_reference_cases"},
                     ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
