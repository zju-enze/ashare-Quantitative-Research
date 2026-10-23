"""Execute the predeclared C2/C3 geometries without changing F0/C1 sources."""
import copy
import json
from pathlib import Path
from time import perf_counter, process_time

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy.signal import lfilter

from . import calibration_dh, simulation_dh
from .engine import applicability
from .engine_dh import dh_audit, global_holm, test_pair
from .simulation import SCENARIOS, panel

FOCUS = ["N0", "N5", "N6", "N7", "M1"]
VERSION = simulation_dh.VERSION
write_json = simulation_dh.write_json
_universe = _candidates = None


def validate_protocol(protocol, stage):
    calibration_dh.validate_protocol(protocol)
    if stage not in ("C2", "C3"):
        raise ValueError("Only C2/C3 are supported here")
    spec = protocol["simulation"]["stages"][stage]
    expected = (dict(kind="formal", geometry="S2", geometry_id=2, groups=4,
                     stocks_per_group=30, pairs=1740, scenarios=FOCUS,
                     repeats=500, repetition_start=40000) if stage == "C2" else
                dict(kind="formal", geometry="frozen_market_membership_synthetic_prices",
                     geometry_id=3, stocks=2984, pairs=67678, scenarios=FOCUS,
                     repeats=100, repetition_start=50000, geometry_implementation="pending",
                     groups=131, largest_group=121, loading="0.8+0.4*j/(n_g-1); singleton c=1",
                     intercept="10000+5*(cumulative_previous_group_sizes+j)",
                     clusters="same V1 group-local mod5 rule"))
    if spec != expected:
        raise ValueError(f"{stage} differs from the F0 specification")


def task_keys(protocol, stage):
    spec = protocol["simulation"]["stages"][stage]
    return [(s, r) for r in range(spec["repetition_start"],
                                  spec["repetition_start"] + spec["repeats"])
            for s in spec["scenarios"]]


def validate_task(stage, scenario, repetition):
    start, stop = {"C2": (40000, 40500), "C3": (50000, 50100)}[stage]
    if scenario not in FOCUS or not start <= repetition < stop:
        raise ValueError(f"Task is outside the frozen {stage} list")


def initialize(folder):
    global _universe, _candidates
    folder = Path(folder)
    if (folder/"geometry/U.parquet").exists():
        _universe = pd.read_parquet(folder/"geometry/U.parquet")
        _candidates = pd.read_parquet(folder/"geometry/H.parquet")


def membership_panel(universe, registry, scenario, repetition, nobs=1212):
    """F0 section 7.1: the original DGP with group-local sizes and offsets."""
    if scenario not in FOCUS:
        raise ValueError("Unplanned C3 mechanism")
    groups = list(universe.sort_values("ts_code").groupby("L2", sort=True))
    stocks, count = len(universe), 1 + len(groups) + len(universe)
    rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence(
        [20261018, 3, SCENARIOS.index(scenario), repetition])))
    burn = 2000
    shape = (burn+nobs, count)
    innovations = (rng.standard_t(5, size=shape)*np.sqrt(3/5)
                   if scenario == "N7" else rng.normal(size=shape))
    if scenario == "N7":
        innovations = lfilter([np.sqrt(.75)], [1, -.5], innovations, axis=0)
    innovations = innovations[burn:].copy()
    if scenario in ("N5", "N7", "M1"):
        innovations[nobs//2:] *= 3
    if scenario == "N6":
        innovations[:nobs//4] *= 3
    trends = innovations.cumsum(axis=0)
    trends -= trends[0]
    phi, sigma = (.95, 1.) if scenario == "M1" else (.5, .25)
    errors = lfilter([np.sqrt(1-phi**2)], [1, -phi],
                     rng.normal(size=(burn+nobs, stocks)), axis=0)[burn:]
    values, clusters, offset = {}, {}, 0
    for g, (_, group) in enumerate(groups):
        size = len(group)
        for j, code in enumerate(group.ts_code):
            cluster = (j % 5 // 2 if j % 5 < 4 else j) if scenario == "M1" else j
            loading = .8 + .4*j/(size-1) if size > 1 else 1.
            x = 10000 + 5*(offset+j) + loading*(trends[:, 0] + trends[:, 1+g]
                + trends[:, 1+len(groups)+offset+cluster]) + sigma*errors[:, offset+j]
            if not np.isfinite(x).all() or x[0] == 0:
                raise ArithmeticError("Invalid C3 panel; do not redraw")
            values[code] = 100*x/x[0]
            clusters[code] = cluster
        offset += size
    h = registry.copy()
    h["true_alternative"] = [clusters[a] == clusters[b] for a, b in zip(h.A, h.B)]
    return universe, h, values


def evaluate_panel(stage, scenario, repetition):
    start = perf_counter()
    if stage == "C2":
        u, h, values = panel("S2", scenario, repetition, nobs=1212)
    else:
        if _universe is None or _candidates is None:
            raise RuntimeError("C3 worker has no frozen membership")
        u, h, values = membership_panel(_universe, _candidates, scenario, repetition)
    expected = (120, 1740) if stage == "C2" else (2984, 67678)
    if (len(u), len(h)) != expected:
        raise RuntimeError(f"{stage} geometry mismatch")
    generated = perf_counter()
    gates = {s: applicability(values[s]) for s in u.ts_code}
    checked = perf_counter()
    rows = []
    for candidate in h.to_dict("records"):
        a, b = values[candidate["A"]], values[candidate["B"]]
        row = test_pair((candidate, a, b, gates[candidate["A"]], gates[candidate["B"]]))
        raw = dh_audit(a, b) if row["compute_status"] == "precheck_placeholder" else row
        row.update({f"ungated_{key}": raw[key] for key in simulation_dh.dh_audit_fields()})
        rows.append(row)
    tested = perf_counter()
    full, _ = global_holm(pd.DataFrame(rows), alpha=.05)
    full["stage"], full["scenario"], full["repetition"] = stage, scenario, repetition
    geometry_id = 2 if stage == "C2" else 3
    full["input_version"] = f"synthetic-PCG64-20261018-{geometry_id}-{SCENARIOS.index(scenario)}-{repetition}"
    full["method_version"] = VERSION
    metric = simulation_dh.panel_metrics(full, gates)
    metric.update(dgp_seconds=generated-start, precheck_seconds=checked-generated,
                  all_pairs_seconds=tested-checked, holm_seconds=perf_counter()-tested)
    return metric, full, gates


def load_checkpoint(folder, stage, scenario, repetition):
    validate_task(stage, scenario, repetition)
    base = Path(folder)/scenario/str(repetition)
    marker = base.with_suffix(".json")
    if not marker.exists():
        return None
    metric = json.loads(marker.read_text(encoding="utf-8"))
    stocks, pairs = (120, 1740) if stage == "C2" else (2984, 67678)
    for key, value in dict(stage=stage, scenario=scenario, repetition=repetition,
                           method_version=VERSION, stocks=stocks, pairs=pairs,
                           kernel_calls=pairs, complete=True).items():
        if metric.get(key) != value:
            raise ValueError(f"Inconsistent {stage} checkpoint: {marker}: {key}")
    if not base.with_suffix(".adf.json").exists():
        raise ValueError(f"Completed checkpoint missing ADF audit: {marker}")
    if pq.read_metadata(base.with_suffix(".pairs.parquet")).num_rows != pairs:
        raise ValueError(f"Incomplete pair table: {marker}")
    return metric


def run_repetition(task):
    stage, scenario, repetition, folder = task
    existing = load_checkpoint(folder, stage, scenario, repetition)
    if existing is not None:
        return existing
    start, cpu_start = perf_counter(), process_time()
    metric, full, gates = evaluate_panel(stage, scenario, repetition)
    base = Path(folder)/scenario/str(repetition)
    base.parent.mkdir(parents=True, exist_ok=True)
    temporary = base.with_suffix(".pairs.tmp")
    full.to_parquet(temporary, index=False)
    temporary.replace(base.with_suffix(".pairs.parquet"))
    write_json(base.with_suffix(".adf.json"), gates)
    metric.update(stage=stage, scenario=scenario, repetition=repetition,
                  method_version=VERSION, complete=True, total_seconds=perf_counter()-start,
                  cpu_seconds=process_time()-cpu_start)
    write_json(base.with_suffix(".json"), metric)
    return metric


def summarize(metrics, protocol, stage):
    for metric in metrics:
        validate_task(stage, metric["scenario"], metric["repetition"])
        if metric["stage"] != stage:
            raise ValueError("Observations from another stage cannot enter this calibration")
    aggregation = copy.deepcopy(protocol)
    aggregation["simulation"]["stages"]["D1"]["repeats"] = protocol["simulation"]["stages"][stage]["repeats"]
    table = simulation_dh.summarize(metrics, aggregation)
    table = table.loc[table.scenario.isin(FOCUS)].copy()
    table["stage"] = stage
    table = table.rename(columns={"development_diagnostic": "unit_acceptance"}).drop(columns="formal_acceptance")
    table["assessment_scope"] = stage + ("_1740_pair_geometry" if stage == "C2" else "_67678_pair_frozen_geometry")
    return table


def stage_acceptance(summary):
    if summary.unit_acceptance.eq("fail").any():
        return "fail"
    if not summary.complete.all():
        return "incomplete"
    if summary.unit_acceptance.eq("strict_pass").all():
        return "strict_pass"
    if summary.unit_acceptance.isin(["strict_pass", "tolerated_pass"]).all():
        return "tolerated_pass"
    return "inconclusive"
