"""C1 uses D1's validated 40-stock evaluator with independent formal seeds."""
import copy
import json
from pathlib import Path
from time import perf_counter, process_time

import pyarrow.parquet as pq

from . import simulation_dh as development

SCENARIOS = development.D1_SCENARIOS
VERSION = development.VERSION
write_json = development.write_json


def validate_protocol(protocol):
    development.validate_protocol(protocol)
    expected = dict(kind="formal", geometry="S1", geometry_id=1, groups=4,
                    stocks_per_group=10, pairs=180, scenarios=SCENARIOS,
                    repeats=1000, repetition_start=30000)
    if protocol["simulation"]["stages"]["C1"] != expected:
        raise ValueError("C1 task specification differs from the fixed plan")
    if (protocol["status"] != "formally_frozen"
            or not protocol["method_freeze_at"]
            or protocol["execution"]["implemented_stages"] != ["C1"]
            or protocol["execution"]["remote_allowed"]
            or protocol["execution"]["automatic_stage_chaining"]):
        raise ValueError("C1 requires the local-only F0 frozen protocol")


def task_keys(protocol):
    spec = protocol["simulation"]["stages"]["C1"]
    return [(s, r) for r in range(spec["repetition_start"],
                                  spec["repetition_start"] + spec["repeats"])
            for s in spec["scenarios"]]


def validate_task(scenario, repetition):
    if scenario not in SCENARIOS or not 30000 <= repetition < 31000:
        raise ValueError("Task is outside the frozen C1 list")


def load_checkpoint(folder, scenario, repetition):
    validate_task(scenario, repetition)
    base = Path(folder)/scenario/str(repetition)
    marker = base.with_suffix(".json")
    if not marker.exists():
        return None
    metric = json.loads(marker.read_text(encoding="utf-8"))
    for key, value in dict(stage="C1", scenario=scenario, repetition=repetition,
                           method_version=VERSION, stocks=40, pairs=180,
                           kernel_calls=180, complete=True).items():
        if metric.get(key) != value:
            raise ValueError(f"Inconsistent C1 checkpoint: {marker}: {key}")
    if not base.with_suffix(".adf.json").exists():
        raise ValueError(f"Completed C1 checkpoint missing ADF: {marker}")
    if pq.read_metadata(base.with_suffix(".pairs.parquet")).num_rows != 180:
        raise ValueError(f"Incomplete C1 pair table: {marker}")
    return metric


def run_repetition(task):
    scenario, repetition, folder = task
    existing = load_checkpoint(folder, scenario, repetition)
    if existing is not None:
        return existing
    start, cpu_start = perf_counter(), process_time()
    metric, full, gates = development.evaluate_panel(scenario, repetition)
    full["stage"] = "C1"
    base = Path(folder)/scenario/str(repetition)
    base.parent.mkdir(parents=True, exist_ok=True)
    temporary = base.with_suffix(".pairs.tmp")
    full.to_parquet(temporary, index=False)
    temporary.replace(base.with_suffix(".pairs.parquet"))
    write_json(base.with_suffix(".adf.json"), gates)
    metric.update(stage="C1", scenario=scenario, repetition=repetition,
                  method_version=VERSION, complete=True, total_seconds=perf_counter()-start,
                  cpu_seconds=process_time()-cpu_start)
    write_json(base.with_suffix(".json"), metric)
    return metric


def summarize(metrics, protocol):
    for metric in metrics:
        validate_task(metric["scenario"], metric["repetition"])
        if metric["stage"] != "C1":
            raise ValueError("Development observations cannot enter C1")
    # Reuse the identical estimators without editing D1's frozen implementation.
    aggregation = copy.deepcopy(protocol)
    aggregation["simulation"]["stages"]["D1"]["repeats"] = 1000
    table = development.summarize(metrics, aggregation)
    table["stage"] = "C1"
    table = table.rename(columns={"development_diagnostic": "unit_acceptance"})
    table = table.drop(columns="formal_acceptance")
    table["assessment_scope"] = "C1_180_pair_geometry"
    return table


def stage_acceptance(summary, protocol):
    required = summary.set_index("scenario").loc[protocol["acceptance"]["required_C1_scenarios"]]
    if required.unit_acceptance.eq("fail").any():
        return "fail"
    if not summary.complete.all():
        return "incomplete"
    if required.unit_acceptance.eq("strict_pass").all():
        return "strict_pass"
    if required.unit_acceptance.isin(["strict_pass", "tolerated_pass"]).all():
        return "tolerated_pass"
    return "inconclusive"
