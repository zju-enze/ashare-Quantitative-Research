"""Run/resume the fixed D1 development list. No automatic next stage."""
import os
for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[key] = "1"
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
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

from src.simulation_dh import (load_checkpoint, run_repetition, summarize, task_keys,
                               validate_protocol, write_json)

ROOT = Path(__file__).resolve().parent
SOURCE_FILES = ("experiment_protocol_v2.json", "run_simulation_v2.py",
                "src/simulation_dh.py", "src/simulation.py",
                "src/engine_dh.py", "src/engine.py")


def now():
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()


def prepare_run(root, folder, protocol):
    folder.mkdir(parents=True, exist_ok=True)
    for name in SOURCE_FILES:
        source, saved = root/name, folder/"source"/name
        if saved.exists():
            if source.read_bytes() != saved.read_bytes():
                raise RuntimeError(f"Saved D1 source differs: {name}; preserve this run and document a revision")
        else:
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, saved)
    environment = dict(python=platform.python_version(), numpy=np.__version__,
                       pandas=pd.__version__, scipy=scipy.__version__,
                       statsmodels=statsmodels.__version__, blas_threads=1)
    saved = folder/"environment.json"
    if saved.exists() and json.loads(saved.read_text(encoding="utf-8")) != environment:
        raise RuntimeError("Saved D1 runtime differs; do not mix checkpoints")
    if not saved.exists():
        write_json(saved, environment)
    manifest = dict(stage="D1", planned=1500, tasks=[
        dict(scenario=s, repetition=r) for s, r in task_keys(protocol)])
    saved = folder/"tasks.json"
    if saved.exists() and json.loads(saved.read_text(encoding="utf-8")) != manifest:
        raise RuntimeError("Saved D1 task list differs")
    if not saved.exists():
        write_json(saved, manifest)
    return environment


def collect_checkpoints(folder, keys):
    records = {}
    for scenario, repetition in keys:
        metric = load_checkpoint(folder, scenario, repetition)
        if metric is not None:
            records[(scenario, repetition)] = metric
    return records


def save_outputs(output, status, records, keys, protocol):
    ordered = [records[key] for key in keys if key in records]
    status.update(completed=len(ordered), updated_at=now(),
                  kernel_calls=sum(x["kernel_calls"] for x in ordered))
    for name, frame in (("D1_panels.csv", pd.DataFrame(ordered)),
                        ("D1_summary.csv", summarize(ordered, protocol))):
        temporary = output/(name + ".tmp")
        frame.to_csv(temporary, index=False)
        temporary.replace(output/name)
    write_json(output/"D1_status.json", status)


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--stage", choices=["D1"], required=True)
    result.add_argument("--workers", type=int, default=4)
    result.add_argument("--max-new", type=int,
                        help="Bound one engineering pilot; keep the full 1500-panel denominator")
    result.add_argument("--summarize-only", action="store_true")
    return result


def main():
    args = parser().parse_args()
    if args.workers < 1 or (args.max_new is not None and args.max_new < 1):
        raise ValueError("workers and max-new must be positive")
    folder = ROOT/".local/dh_v2/simulation/D1"
    output = ROOT/"results_v2/simulation"
    protocol_path = (folder/"source/experiment_protocol_v2.json"
                     if args.summarize_only else ROOT/"experiment_protocol_v2.json")
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    validate_protocol(protocol)
    keys = task_keys(protocol)
    environment = (json.loads((folder/"environment.json").read_text(encoding="utf-8"))
                   if args.summarize_only else prepare_run(ROOT, folder, protocol))
    output.mkdir(parents=True, exist_ok=True)
    records = collect_checkpoints(folder, keys)
    state_path = output/"D1_status.json"
    status = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    invocation = dict(started_at=now(), workers=args.workers, pid=os.getpid(),
                      reused_panels=len(records), max_new=args.max_new,
                      summarize_only=args.summarize_only)
    status.setdefault("invocations", []).append(invocation)
    status.setdefault("execution_snapshot_at", now())
    status.update(stage="D1", kind="development_only", method_version=protocol["version"],
                  status="running", planned=len(keys), repeats_per_scenario=100,
                  workers=args.workers, blas_threads=1, environment=environment,
                  method_freeze_at=None, formal_acceptance="not_assessed_development_only",
                  formal_calibration="not_run", full_market_test="not_run", remote_used=False,
                  local_checkpoints=str(folder.relative_to(ROOT)),
                  protocol="source/experiment_protocol_v2.json")
    save_outputs(output, status, records, keys, protocol)
    remaining = [key for key in keys if key not in records]
    selected = [] if args.summarize_only else remaining[:args.max_new]
    print(f"D1: reused={len(records)}/{len(keys)}, new={len(selected)}, workers={args.workers}", flush=True)
    start = perf_counter()
    pool = None
    futures = {}
    try:
        if selected:
            pool = ProcessPoolExecutor(max_workers=args.workers)
            futures = {pool.submit(run_repetition, (s, r, str(folder))): (s, r)
                       for s, r in selected}
            for future in as_completed(futures):
                key = futures[future]
                try:
                    records[key] = future.result()
                except BaseException:
                    invocation["failed_task"] = dict(scenario=key[0], repetition=key[1])
                    raise
                if len(records) % 15 == 0 or len(records) == len(keys):
                    invocation["elapsed_seconds"] = perf_counter()-start
                    save_outputs(output, status, records, keys, protocol)
                    print(f"D1: {len(records)}/{len(keys)}; this invocation {perf_counter()-start:.1f}s",
                          flush=True)
            pool.shutdown(wait=True)
            pool = None
        status["status"] = "complete" if len(records) == len(keys) else "partial"
        invocation.update(status=status["status"], newly_completed=len(records)-invocation["reused_panels"],
                          elapsed_seconds=perf_counter()-start, completed_at=now())
        status["execution_wall_seconds"] = sum(x.get("elapsed_seconds", 0.)
                                               for x in status["invocations"]
                                               if not x["summarize_only"])
        if status["status"] == "complete":
            status["completed_at"] = now()
        save_outputs(output, status, records, keys, protocol)
        print(json.dumps({k: status[k] for k in ("status", "completed", "planned", "kernel_calls",
                                                "execution_wall_seconds")}), flush=True)
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
