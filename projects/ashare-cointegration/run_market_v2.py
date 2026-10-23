"""Frozen-market DH; an explicit nominal mode retains inconclusive C3 evidence."""
import os
for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[key] = "1"
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import argparse
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import shutil
from time import perf_counter

import pandas as pd
from statsmodels.stats.multitest import multipletests

import run_calibration_v2 as c1
import run_stage1 as v1
from src.engine_dh import global_holm
from src.engine_dh_market import test_pair
from src.simulation_dh import write_json

ROOT = Path(__file__).resolve().parent
SOURCE_FILES = (*c1.SOURCE_FILES, "run_market_v2.py", "src/engine_dh_market.py", "run_stage1.py", "src/data.py", "src/reporting.py")
INPUT_FILES = ("U.parquet", "H.parquet", "prices.npy", "ADF.json", "freeze.json")


def require_calibration(root, nominal_if_inconclusive=False):
    folder = root/"results_v2/simulation"
    result = {}
    for stage, planned in (("C1", 15000), ("C2", 2500), ("C3", 500)):
        state = json.loads((folder/f"{stage}_status.json").read_text(encoding="utf-8"))
        check = json.loads((folder/f"{stage}_validation.json").read_text(encoding="utf-8"))
        acceptance = state[f"{stage}_acceptance"]
        allowed = ("strict_pass", "tolerated_pass")
        if nominal_if_inconclusive and stage == "C3":
            allowed += ("inconclusive",)
        if (state["status"] != "complete" or state["completed"] != planned
                or acceptance not in allowed
                or check["status"] != "passed_engineering_and_summary_reconciliation"
                or check["statistical_acceptance"] != acceptance):
            raise RuntimeError(f"{stage} is not complete, verified and eligible for the selected market mode")
        result[stage] = dict(completed=planned, acceptance=acceptance,
                             checked_at=check["checked_at"])
    return result


def prepare_run(root, protocol, calibration):
    c1.validate_protocol(protocol)
    c1.verify_snapshot(root, root/".local/dh_v2/simulation/C1")
    c1.market_input_evidence(root, protocol)
    source = root/".local/production"/protocol["market"]["input_run_id"]
    run = root/".local/dh_v2/production"/(protocol["market"]["run_id"]+"__used-prefix")
    if (root/"src/engine.py").read_bytes() != (source/"source/engine.py").read_bytes():
        raise RuntimeError("The retained ADF implementation differs from the frozen market run")
    universe = pd.read_parquet(source/"U.parquet")
    gates = json.loads((source/"ADF.json").read_text(encoding="utf-8"))
    if set(gates) != set(universe.ts_code):
        raise RuntimeError("Frozen ADF coverage differs from the universe")
    for gate in gates.values():
        if (gate["input_version"] != protocol["market"]["input_run_id"]
                or gate["statsmodels_version"] != c1.environment()["statsmodels"]):
            raise RuntimeError("Frozen ADF input/runtime differs")
    if (run/"execution.json").exists():
        for name in SOURCE_FILES:
            if (root/name).read_bytes() != (run/"source"/name).read_bytes():
                raise RuntimeError(f"Market source differs: {name}; preserve existing results")
        for name in INPUT_FILES:
            if (source/name).read_bytes() != (run/name).read_bytes():
                raise RuntimeError(f"Frozen market input differs: {name}")
        if json.loads((run/"environment.json").read_text(encoding="utf-8")) != c1.environment():
            raise RuntimeError("Market runtime differs")
    else:
        if any((run/"batches").glob("*.parquet")):
            raise RuntimeError("Market batches exist without a completed execution snapshot")
        run.mkdir(parents=True, exist_ok=True)
        for name in INPUT_FILES:
            shutil.copy2(source/name, run/name)
        for name in SOURCE_FILES:
            target = run/"source"/name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root/name, target)
        write_json(run/"environment.json", c1.environment())
        write_json(run/"execution.json", dict(implementation_recorded_at=c1.now(),
            method_freeze_at=protocol["method_freeze_at"], engineering_change="ENG-015",
            input_run_id=protocol["market"]["input_run_id"], run_id=run.name,
            precheck="reuse frozen ADF on identical inputs and implementation",
            calibration=calibration, remote_used=False))
    return run, source


def diagnose_pair(row):
    return test_pair((row, v1.VALUES[:, v1.CODES[row["A"]]], v1.VALUES[:, v1.CODES[row["B"]]],
                      v1.GATES[row["A"]], v1.GATES[row["B"]]))


def load_batch(path, expected):
    if not path.exists():
        return None
    table = pd.read_parquet(path)
    pd.testing.assert_frame_equal(table[expected.columns], expected.reset_index(drop=True), check_dtype=False, check_exact=True)
    return table


def finalize(raw, previous):
    full, _ = global_holm(raw, alpha=.05)
    full["p_L2_Holm"] = 1.
    full["reject_L2_Holm"] = False
    for _, indices in full.groupby("L2").groups.items():
        if not full.loc[indices, "M_L2"].eq(len(indices)).all():
            raise ValueError("Incomplete auxiliary L2 family")
        reject, adjusted, _, _ = multipletests(full.loc[indices, "p_for_adjustment"], .05, method="holm")
        full.loc[indices, "p_L2_Holm"] = adjusted
        full.loc[indices, "reject_L2_Holm"] = reject
    if previous.candidate_id.tolist() != full.candidate_id.tolist():
        raise ValueError("V1/DH comparison has different frozen candidates")
    comparison = full[["candidate_id", "A", "B", "L2", "layer"]].copy()
    for prefix, table in (("V1_EG", previous), ("V2_DH", full)):
        for domain in ("L2", "GLOBAL"):
            values = table[f"reject_{domain}_Holm"]
            if values.isna().any():
                raise ValueError("Unresolved correction in comparison")
            comparison[f"{prefix}_{domain}_Holm"] = values.to_numpy(bool)
    main = full.loc[full.compute_status.eq("valid") & full.reject_GLOBAL_Holm].copy()
    before = comparison.V1_EG_L2_Holm.to_numpy(bool)
    after = comparison.V2_DH_GLOBAL_Holm.to_numpy(bool)
    union = int((before | after).sum())
    overlap = dict(intersection=int((before & after).sum()), V1_only=int((before & ~after).sum()),
                   DH_only=int((~before & after).sum()), union=union,
                   Jaccard=float((before & after).sum()/union) if union else None)
    counts = {key: int(comparison[key].sum()) for key in comparison.columns if key.endswith("_Holm")}
    return full, main, comparison, counts, overlap


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--nominal-if-inconclusive", action="store_true",
        help="Explicit nominal output when complete, verified C3 is inconclusive; never mark calibration passed")
    args = parser.parse_args()
    if args.workers < 1:
        raise ValueError("workers must be positive")
    protocol = json.loads((ROOT/c1.PROTOCOL).read_text(encoding="utf-8"))
    calibration = require_calibration(ROOT, nominal_if_inconclusive=args.nominal_if_inconclusive)
    acceptance = ("inconclusive" if any(x["acceptance"] == "inconclusive" for x in calibration.values()) else
                  "strict_pass" if all(x["acceptance"] == "strict_pass" for x in calibration.values()) else "tolerated_pass")
    evidence_scope = "nominal_calibration_inconclusive" if acceptance == "inconclusive" else "nominal_with_calibration_evidence"
    run, source = prepare_run(ROOT, protocol, calibration)
    registry = pd.read_parquet(run/"H.parquet")
    output = ROOT/"results_v2"
    state_path = output/"market_status.json"
    status = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    if status.get("run_id") != run.name:
        status = {}
    invocation = dict(started_at=c1.now(), pid=os.getpid(), workers=args.workers, reused_pairs=0,
                      nominal_if_inconclusive=args.nominal_if_inconclusive)
    status.setdefault("invocations", []).append(invocation)
    status.update(status="running", run_id=run.name, method_freeze_at=protocol["method_freeze_at"],
                  input_run_id=source.name, planned=len(registry), completed=0, workers=args.workers,
                  blas_threads=1, remote_used=False, precheck_reused=True, calibration=calibration,
                  calibration_acceptance=acceptance, evidence_scope=evidence_scope,
                  engineering_change="ENG-015", implementation_revision="used_recursive_prefix_guard")
    (run/"batches").mkdir(exist_ok=True)
    write_json(state_path, status)
    start_time = perf_counter()
    try:
        with ProcessPoolExecutor(max_workers=args.workers, initializer=v1.initialize, initargs=(str(run),)) as pool:
            for start in range(0, len(registry), 1000):
                chunk = registry.iloc[start:start+1000]
                destination = run/"batches"/f"{start:09d}.parquet"
                table = load_batch(destination, chunk)
                if table is None:
                    rows = list(pool.map(diagnose_pair, chunk.to_dict("records"), chunksize=16))
                    temporary = destination.with_suffix(".tmp")
                    pd.DataFrame(rows).to_parquet(temporary, index=False)
                    temporary.replace(destination)
                else:
                    invocation["reused_pairs"] += len(table)
                status.update(completed=min(start+1000, len(registry)), updated_at=c1.now())
                write_json(state_path, status)
                print(f"DH market {status['completed']}/{len(registry)}", flush=True)
        raw = pd.concat([pd.read_parquet(run/"batches"/f"{start:09d}.parquet")
                         for start in range(0, len(registry), 1000)], ignore_index=True)
        pd.testing.assert_frame_equal(raw[registry.columns], registry, check_dtype=False, check_exact=True)
        raw["input_version"] = source.name
        raw["method_version"] = protocol["version"]
        raw["implementation_revision"] = "used_recursive_prefix_guard"
        raw["direction"] = protocol["method"]["direction"]
        raw["calibration_acceptance"] = acceptance
        raw["evidence_scope"] = evidence_scope
        raw["GLOBAL_family"] = "GLOBAL"
        previous = pd.read_parquet(source/"full_results.parquet")
        full, main_evidence, comparison, counts, overlap = finalize(raw, previous)
        comparison["calibration_acceptance"] = acceptance
        comparison["evidence_scope"] = evidence_scope
        temporary = run/"full_results.tmp"
        full.to_parquet(temporary, index=False)
        temporary.replace(run/"full_results.parquet")
        for name, frame in (("main_evidence.csv", main_evidence), ("v1_dh_comparison.csv", comparison)):
            temporary = output/(name+".tmp")
            frame.to_csv(temporary, index=False, encoding="utf-8-sig")
            temporary.replace(output/name)
        invocation.update(status="complete", completed_at=c1.now(), elapsed_seconds=perf_counter()-start_time)
        status.update(status="complete", completed_at=c1.now(), discoveries=len(main_evidence),
            DH_executed=int(full.DH_executed.sum()),
            valid_DH=int(full.compute_status.eq("valid").sum()),
            precheck_placeholders=int(full.compute_status.eq("precheck_placeholder").sum()),
            numerical_placeholders=int(full.compute_status.eq("numerically_ineligible").sum()),
            prefix_guard_corrected=int(full.prefix_guard_corrected.sum()),
            underflow=int(full.p_zero_origin.eq("exp_underflow").sum()),
            method_counts=counts, primary_overlap=overlap,
            market_validation="pending_independent_reconciliation",
            calibration_acceptance=acceptance,
            execution_wall_seconds=sum(x.get("elapsed_seconds", 0.) for x in status["invocations"]))
        write_json(state_path, status)
        print(json.dumps(dict(status="complete", completed=len(full), discoveries=len(main_evidence),
                              method_counts=counts, elapsed_seconds=invocation["elapsed_seconds"])), flush=True)
    except BaseException as error:
        invocation.update(status="interrupted_or_error", completed_at=c1.now(),
                          elapsed_seconds=perf_counter()-start_time)
        status.update(status="interrupted_or_error", error=f"{type(error).__name__}: {error}", updated_at=c1.now())
        write_json(state_path, status)
        raise


if __name__ == "__main__":
    main()
