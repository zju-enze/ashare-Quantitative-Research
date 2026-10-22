"""Freeze F0, then explicitly run/resume C1; no C2/C3/market/remote entry."""
import os
for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[key] = "1"
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import copy
from datetime import datetime
import json
from pathlib import Path
import platform
import shutil
from time import perf_counter
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import scipy
import statsmodels

from src.engine import candidates
from src.calibration_dh import (load_checkpoint, run_repetition, summarize,
                               stage_acceptance, task_keys, validate_protocol, write_json)

ROOT = Path(__file__).resolve().parent
PROTOCOL = "experiment_protocol_v2_frozen.json"
SOURCE_FILES = (PROTOCOL, "run_calibration_v2.py", "src/calibration_dh.py",
                "src/simulation_dh.py", "src/engine_dh.py", "src/simulation.py", "src/engine.py")


def now():
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()


def environment():
    return dict(python=platform.python_version(), numpy=np.__version__,
                pandas=pd.__version__, scipy=scipy.__version__,
                statsmodels=statsmodels.__version__, blas_threads=1)


def frozen_protocol(development, frozen_at):
    protocol = copy.deepcopy(development)
    protocol.update(status="formally_frozen", method_freeze_at=frozen_at,
                    implementation_scope="F0 and local C1 only; C2/C3/market remain unimplemented",
                    source_development_protocol="experiment_protocol_v2.json",
                    accepted_limitation="User accepts current slow-reversion power; keep 7 lags fixed")
    protocol["execution"].update(runner="run_calibration_v2.py", implemented_stages=["C1"],
        formal_calibration="C1_authorized_local_only", C2_C3="not_authorized_this_run",
        full_market_test="not_authorized_this_run", remote_allowed=False,
        automatic_stage_chaining=False, progress_save_every_panels=150)
    protocol["outputs"].update(local=".local/dh_v2/simulation/C1",
        status="results_v2/simulation/C1_status.json", panels="results_v2/simulation/C1_panels.csv",
        summary="results_v2/simulation/C1_summary.csv", report="results_v2/simulation/C1_REPORT.md")
    validate_protocol(protocol)
    return protocol


def market_input_evidence(root, protocol):
    run = root/".local/production"/protocol["market"]["input_run_id"]
    ledger = json.loads((run/"freeze.json").read_text(encoding="utf-8"))
    u, h = pd.read_parquet(run/"U.parquet"), pd.read_parquet(run/"H.parquet")
    calendar = ledger["calendar"]
    assert len(u) == 2984 and len(h) == 67678 and len(calendar) == 1212
    assert u.ts_code.tolist() == sorted(u.ts_code.unique())
    assert calendar == sorted(set(calendar))
    assert ledger["formation"] == ["2021-01-01", "2025-12-31"]
    pd.testing.assert_frame_equal(h, candidates(u), check_dtype=False)
    assert int(h.layer.eq("T").sum()) == 28443 and int(h.layer.eq("C").sum()) == 39235
    prices = np.load(run/"prices.npy", mmap_mode="r")
    assert prices.shape == (1212, 2984) and prices.dtype == np.dtype("float64")
    del prices
    return dict(input_run_id=run.name, stocks=len(u), candidates=len(h), observations=len(calendar),
                first_session=calendar[0], last_session=calendar[-1], T=28443, C=39235,
                registry_matches_original_rule=True, price_header_verified=True,
                price_values_read=False, market_test_run=False)


def verify_snapshot(root, folder):
    for name in SOURCE_FILES:
        if (root/name).read_bytes() != (folder/"source"/name).read_bytes():
            raise RuntimeError(f"Frozen C1 source differs: {name}; do not mix versions")
    saved_environment = json.loads((folder/"environment.json").read_text(encoding="utf-8"))
    if saved_environment != environment():
        raise RuntimeError("Frozen C1 runtime differs")


def freeze(root=ROOT):
    folder, output = root/".local/dh_v2/simulation/C1", root/"results_v2"
    freeze_path = output/"F0_FREEZE.json"
    if freeze_path.exists():
        verify_snapshot(root, folder)
        return json.loads(freeze_path.read_text(encoding="utf-8"))
    if any(folder.glob("*/*.pairs.parquet")):
        raise RuntimeError("C1 results exist before F0; do not backdate a freeze")
    tests = json.loads((output/"F0_TESTS.json").read_text(encoding="utf-8"))
    if tests["status"] != "passed":
        raise RuntimeError("F0 implementation checks have not passed")
    d1 = root/".local/dh_v2/simulation/D1"
    d1_state = json.loads((output/"simulation/D1_status.json").read_text(encoding="utf-8"))
    if d1_state["status"] != "complete" or d1_state["completed"] != 1500:
        raise RuntimeError("D1 is not complete")
    for name in ("experiment_protocol_v2.json", "run_simulation_v2.py", "src/simulation_dh.py",
                 "src/engine_dh.py", "src/simulation.py", "src/engine.py"):
        if (root/name).read_bytes() != (d1/"source"/name).read_bytes():
            raise RuntimeError(f"D1 source changed since its validation: {name}")
    if json.loads((d1/"environment.json").read_text(encoding="utf-8")) != environment():
        raise RuntimeError("Runtime differs from the validated D1 environment")
    base = json.loads((root/"experiment_protocol_v2.json").read_text(encoding="utf-8"))
    inputs = market_input_evidence(root, base)
    frozen_at = now()
    protocol = frozen_protocol(base, frozen_at)
    keys = task_keys(protocol)
    assert len(keys) == len(set(keys)) == 15000
    if (root/PROTOCOL).exists():
        raise RuntimeError("Incomplete earlier F0 protocol exists; inspect it before freezing again")
    write_json(root/PROTOCOL, protocol)
    (folder/"source").mkdir(parents=True, exist_ok=True)
    for name in SOURCE_FILES:
        target = folder/"source"/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root/name, target)
    write_json(folder/"environment.json", environment())
    write_json(folder/"tasks.json", dict(stage="C1", planned=15000,
        tasks=[dict(scenario=s, repetition=r) for s, r in keys]))
    record = dict(status="frozen", method_freeze_at=frozen_at, version=protocol["version"],
        protocol=PROTOCOL, execution_source=str((folder/"source").relative_to(root)),
        unit_tests=tests, frozen_market_input=inputs, C1_panels=15000,
        C1_kernel_calls=2700000, C1_repetition_range=[30000, 30999],
        lags=7, nominal_alpha=.05, maximum_tolerated_FWER=.10,
        slow_reversion_power_limitation_accepted=True, D1_source_unchanged=True,
        D1_results_reused_for_formal_acceptance=False, C1_observations_before_freeze=0,
        C2="not_run", C3="not_run", market="not_run", remote_used=False)
    write_json(freeze_path, record)
    return record


def collect_checkpoints(folder, keys):
    records = {}
    for key in keys:
        metric = load_checkpoint(folder, *key)
        if metric is not None:
            records[key] = metric
    return records


def save_outputs(output, status, records, keys, protocol):
    ordered = [records[key] for key in keys if key in records]
    summary = summarize(ordered, protocol)
    acceptance = stage_acceptance(summary, protocol)
    status.update(completed=len(ordered), updated_at=now(),
                  kernel_calls=sum(x["kernel_calls"] for x in ordered),
                  C1_acceptance=acceptance,
                  overall_protocol_acceptance="fail" if acceptance == "fail" else
                                              "incomplete_C2_C3_not_run")
    for name, frame in (("C1_panels.csv", pd.DataFrame(ordered)), ("C1_summary.csv", summary)):
        temporary = output/(name+".tmp")
        frame.to_csv(temporary, index=False)
        temporary.replace(output/name)
    write_json(output/"C1_status.json", status)


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--stage", choices=["F0", "C1"], required=True)
    result.add_argument("--workers", type=int, default=4)
    result.add_argument("--max-new", type=int, help="Bound one invocation; retain all 15000 planned tasks")
    result.add_argument("--summarize-only", action="store_true")
    return result


def main():
    args = parser().parse_args()
    if args.workers < 1 or (args.max_new is not None and args.max_new < 1):
        raise ValueError("workers and max-new must be positive")
    if args.stage == "F0":
        print(json.dumps(freeze(), ensure_ascii=False), flush=True)
        return
    folder, output = ROOT/".local/dh_v2/simulation/C1", ROOT/"results_v2/simulation"
    frozen = json.loads((ROOT/"results_v2/F0_FREEZE.json").read_text(encoding="utf-8"))
    protocol = json.loads((folder/"source"/PROTOCOL).read_text(encoding="utf-8"))
    validate_protocol(protocol)
    if frozen["method_freeze_at"] != protocol["method_freeze_at"]:
        raise RuntimeError("F0 ledger and protocol differ")
    if not args.summarize_only:
        verify_snapshot(ROOT, folder)
    keys = task_keys(protocol)
    saved_keys = json.loads((folder/"tasks.json").read_text(encoding="utf-8"))["tasks"]
    if saved_keys != [dict(scenario=s, repetition=r) for s, r in keys]:
        raise RuntimeError("C1 task manifest differs")
    records = collect_checkpoints(folder, keys)
    state_path = output/"C1_status.json"
    status = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    invocation = dict(started_at=now(), pid=os.getpid(), workers=args.workers,
                      reused_panels=len(records), max_new=args.max_new,
                      summarize_only=args.summarize_only)
    status.setdefault("invocations", []).append(invocation)
    status.update(stage="C1", kind="formal_calibration", method_version=protocol["version"],
                  method_freeze_at=protocol["method_freeze_at"], status="running", planned=15000,
                  repeats_per_scenario=1000, workers=args.workers, blas_threads=1,
                  environment=environment(), local_checkpoints=str(folder.relative_to(ROOT)),
                  C2="not_run", C3="not_run", full_market_test="not_run", remote_used=False)
    save_outputs(output, status, records, keys, protocol)
    remaining = [key for key in keys if key not in records]
    selected = [] if args.summarize_only else remaining[:args.max_new]
    print(f"C1: reused={len(records)}/15000, new={len(selected)}, workers={args.workers}", flush=True)
    start, pool, futures = perf_counter(), None, {}
    try:
        if selected:
            pool = ProcessPoolExecutor(max_workers=args.workers)
            futures = {pool.submit(run_repetition, (*key, str(folder))): key for key in selected}
            for future in as_completed(futures):
                key = futures[future]
                try:
                    records[key] = future.result()
                except BaseException:
                    invocation["failed_task"] = dict(scenario=key[0], repetition=key[1])
                    raise
                if len(records) % 150 == 0 or len(records) == 15000:
                    invocation["elapsed_seconds"] = perf_counter()-start
                    save_outputs(output, status, records, keys, protocol)
                    print(f"C1: {len(records)}/15000; this invocation {perf_counter()-start:.1f}s", flush=True)
            pool.shutdown(wait=True)
            pool = None
        status["status"] = "complete" if len(records) == 15000 else "partial"
        invocation.update(status=status["status"], newly_completed=len(records)-invocation["reused_panels"],
                          elapsed_seconds=perf_counter()-start, completed_at=now())
        status["execution_wall_seconds"] = sum(x.get("elapsed_seconds", 0.) for x in status["invocations"]
                                               if not x["summarize_only"])
        if status["status"] == "complete":
            status["completed_at"] = now()
        save_outputs(output, status, records, keys, protocol)
        print(json.dumps({k: status[k] for k in ("status", "completed", "kernel_calls",
                                                "C1_acceptance", "execution_wall_seconds")}), flush=True)
    except BaseException as error:
        for future in futures:
            future.cancel()
        if pool is not None:
            pool.shutdown(wait=True, cancel_futures=True)
        records = collect_checkpoints(folder, keys)
        invocation.update(status="interrupted_or_error", error=f"{type(error).__name__}: {error}",
                          elapsed_seconds=perf_counter()-start, completed_at=now())
        status["status"] = "interrupted_or_error"
        save_outputs(output, status, records, keys, protocol)
        raise


if __name__ == "__main__":
    main()
