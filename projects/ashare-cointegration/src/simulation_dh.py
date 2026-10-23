"""D1 whole-panel development trials; V1 DGP and DH kernel remain unchanged."""
import json
from pathlib import Path
from time import perf_counter, process_time

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy.stats import beta

from .engine import applicability
from .engine_dh import dh_audit, test_pair, global_holm
from .simulation import panel, SCENARIOS

VERSION = "2.1-DH"
D1_SCENARIOS = [s for s in SCENARIOS if s != "N1"]


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                    allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def validate_protocol(protocol):
    """Reject a configuration the fixed implementation would silently ignore."""
    expected = {
        "method": dict(test="DH2018_joint_bivariate", lags=7, df=2,
                       deterministic="constant_mean_no_linear_drift",
                       direction="lexicographic_A_on_B",
                       differences="original_price_differences",
                       recursive_error_initial_zeros=2, covariance_divisor="original_T",
                       p_value="exp(-Q/2)", log_p="-Q/2", regularization=False),
        "precheck": dict(test="ADF", regression="c", autolag="AIC", maxlag=None,
                         alpha=.05, placeholder=1, retain_full_family=True),
        "correction": dict(domain="GLOBAL", method="holm", alpha=.05,
                           unavailable_p=1, filter_after_rejection=False),
        "simulation": dict(nobs=1212, burnin=2000, generator="PCG64", seed_base=20261018,
                           raw_kernel_on_all_synthetic_pairs=True,
                           scenario_ids={s: i for i, s in enumerate(SCENARIOS)}),
        "acceptance": dict(nominal_alpha=.05, maximum_tolerated_FWER=.10,
                           interval="one_sided_95_percent_Clopper_Pearson",
                           tail_probability=.05, development_in_formal_acceptance=False),
    }
    if protocol["version"] != VERSION:
        raise ValueError("Unsupported V2 version")
    for section, fields in expected.items():
        for key, value in fields.items():
            if protocol[section][key] != value:
                raise ValueError(f"Protocol/implementation mismatch: {section}.{key}")
    expected_d1 = dict(kind="development", geometry="S1", geometry_id=1, groups=4,
                       stocks_per_group=10, pairs=180, scenarios=D1_SCENARIOS,
                       repeats=100, repetition_start=20000)
    if protocol["simulation"]["stages"]["D1"] != expected_d1:
        raise ValueError("D1 task specification differs from V2.1-DH")


def task_keys(protocol):
    spec = protocol["simulation"]["stages"]["D1"]
    return [(s, r) for r in range(spec["repetition_start"],
                                  spec["repetition_start"] + spec["repeats"])
            for s in spec["scenarios"]]


def panel_metrics(full, gates):
    truth = full.true_alternative.to_numpy(bool)
    reject = full.reject_GLOBAL_Holm.to_numpy(bool)
    valid = full.compute_status.eq("valid").to_numpy()
    R, V, A = int(reject.sum()), int((reject & ~truth).sum()), int(truth.sum())
    true_discoveries = int((reject & truth).sum())
    survivors = int((truth & valid).sum())
    return dict(
        stocks=len(gates), pairs=len(full), kernel_calls=len(full), R=R, V=V, A=A,
        true_nulls=int((~truth).sum()), true_discoveries=true_discoveries,
        valid_alternatives=survivors, false_any=int(V > 0), FDP=V/max(R, 1),
        power=true_discoveries/A if A else None,
        conditional_power=true_discoveries/survivors if survivors else None,
        raw_null_rejection=float((full.ungated_p_for_adjustment.to_numpy()[~truth]
                                  < .05).mean()) if (~truth).any() else None,
        stock_I1_fraction=float(np.mean([g["compatible"] for g in gates.values()])),
        precheck_placeholders=int(full.compute_status.eq("precheck_placeholder").sum()),
        valid_pairs=int(valid.sum()),
        numerical_count=int(full.ungated_compute_status.ne("valid").sum()),
        gated_numerical_count=int(full.compute_status.eq("numerically_ineligible").sum()),
        underflow_count=int(full.ungated_p_zero_origin.eq("exp_underflow").sum()))


def evaluate_panel(scenario, repetition):
    start = perf_counter()
    u, h, values = panel("S1", scenario, repetition, nobs=1212)
    if len(u) != 40 or len(h) != 180:
        raise RuntimeError("D1 geometry mismatch")
    generated = perf_counter()
    gates = {s: applicability(values[s]) for s in u.ts_code}
    checked = perf_counter()
    rows = []
    for candidate in h.to_dict("records"):
        a, b = values[candidate["A"]], values[candidate["B"]]
        row = test_pair((candidate, a, b, gates[candidate["A"]], gates[candidate["B"]]))
        raw = dh_audit(a, b) if row["compute_status"] == "precheck_placeholder" else row
        # Retain the ungated audit even when ADF makes the main p-value one.
        row.update({f"ungated_{key}": raw[key] for key in dh_audit_fields()})
        rows.append(row)
    tested = perf_counter()
    full, _ = global_holm(pd.DataFrame(rows), alpha=.05)
    full["stage"], full["scenario"], full["repetition"] = "D1", scenario, repetition
    full["input_version"] = f"synthetic-PCG64-20261018-1-{SCENARIOS.index(scenario)}-{repetition}"
    full["method_version"] = VERSION
    metric = panel_metrics(full, gates)
    metric.update(dgp_seconds=generated-start, precheck_seconds=checked-generated,
                  all_pairs_seconds=tested-checked, holm_seconds=perf_counter()-tested)
    return metric, full, gates


def dh_audit_fields():
    return ("N_input", "N_effective", "lags", "covariance_denominator", "DH_executed",
            "Q", "df", "p_raw", "log_p", "p_for_adjustment", "compute_status",
            "placeholder_reason", "p_zero_origin", "adjustment_A", "adjustment_B",
            "t_A", "t_B", "residual_correlation", "control_rank", "control_condition",
            "covariance_condition", "instrument_denominator", "instrument_residual_ss")


def load_checkpoint(folder, scenario, repetition):
    base = Path(folder)/scenario/str(repetition)
    marker = base.with_suffix(".json")
    if not marker.exists():
        return None
    metric = json.loads(marker.read_text(encoding="utf-8"))
    for key, value in dict(stage="D1", scenario=scenario, repetition=repetition,
                           method_version=VERSION, stocks=40, pairs=180,
                           kernel_calls=180, complete=True).items():
        if metric.get(key) != value:
            raise ValueError(f"Inconsistent completed checkpoint: {marker}: {key}")
    if not base.with_suffix(".adf.json").exists():
        raise ValueError(f"Completed checkpoint missing ADF audit: {marker}")
    if pq.read_metadata(base.with_suffix(".pairs.parquet")).num_rows != 180:
        raise ValueError(f"Incomplete pair table: {marker}")
    return metric


def run_repetition(task):
    scenario, repetition, folder = task
    existing = load_checkpoint(folder, scenario, repetition)
    if existing is not None:
        return existing
    start, cpu_start = perf_counter(), process_time()
    metric, full, gates = evaluate_panel(scenario, repetition)
    base = Path(folder)/scenario/str(repetition)
    base.parent.mkdir(parents=True, exist_ok=True)
    temporary = base.with_suffix(".pairs.tmp")
    full.to_parquet(temporary, index=False)
    temporary.replace(base.with_suffix(".pairs.parquet"))
    write_json(base.with_suffix(".adf.json"), gates)
    metric.update(stage="D1", scenario=scenario, repetition=repetition,
                  method_version=VERSION, complete=True, total_seconds=perf_counter()-start,
                  cpu_seconds=process_time()-cpu_start)
    write_json(base.with_suffix(".json"), metric)
    return metric


def confidence_bounds(k, B):
    if B == 0:
        return None, None
    return (0. if k == 0 else float(beta.ppf(.05, k, B-k+1)),
            1. if k == B else float(beta.ppf(.95, k+1, B-k)))


def diagnostic_classification(low, high):
    if high <= .05:
        return "strict_pass"
    if high <= .10:
        return "tolerated_pass"
    return "fail" if low > .10 else "inconclusive"


def summarize(metrics, protocol):
    frame = pd.DataFrame(metrics)
    if len(frame) and frame.duplicated(["scenario", "repetition"]).any():
        raise ValueError("Repeated panel would change the Monte Carlo denominator")
    rows = []
    for scenario in D1_SCENARIOS:
        g = frame.loc[frame.scenario.eq(scenario)] if len(frame) else frame
        B = len(g)
        required = protocol["simulation"]["stages"]["D1"]["repeats"]
        has_nulls = not scenario.startswith("A")
        k = int(g.false_any.sum()) if B and has_nulls else None
        low, high = confidence_bounds(k, B) if has_nulls else (None, None)
        status = ("not_run" if not B else "partial" if B < required else
                  "not_applicable_all_alternative" if not has_nulls else
                  diagnostic_classification(low, high))
        row = dict(stage="D1", scenario=scenario, B=B, planned_B=required,
                   complete=B == required, false_event_panels=k,
                   FWER=k/B if B and has_nulls else None, FWER_lower95=low,
                   FWER_upper95=high, development_diagnostic=status,
                   formal_acceptance="not_assessed_development_only")
        row["FWER_MCSE"] = (float(np.sqrt(row["FWER"]*(1-row["FWER"])/B))
                            if B and has_nulls else None)
        for field in ("power", "conditional_power", "FDP", "raw_null_rejection",
                      "stock_I1_fraction", "total_seconds", "cpu_seconds"):
            x = g[field].dropna() if B else pd.Series(dtype=float)
            row[field] = float(x.mean()) if len(x) else None
            row[field+"_B"] = len(x)
            row[field+"_MCSE"] = float(x.std(ddof=1)/np.sqrt(len(x))) if len(x) > 1 else None
        for field in ("R", "V", "A", "true_nulls", "true_discoveries", "valid_alternatives",
                      "precheck_placeholders", "valid_pairs", "numerical_count",
                      "gated_numerical_count", "underflow_count", "kernel_calls"):
            row[field+"_total"] = int(g[field].sum()) if B else 0
        rows.append(row)
    return pd.DataFrame(rows)
