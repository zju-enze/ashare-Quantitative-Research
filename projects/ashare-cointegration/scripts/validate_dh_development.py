"""Bounded local DH run: tests, 75 smoke panels, nine timings and six timing repeats.

No market prices, formal calibration, remote calls, or v1 writes.
Run with the project's Python; each invocation creates a separate result directory.
"""
import os
for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[key] = "1"
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
import json
from datetime import datetime
from pathlib import Path
from time import perf_counter
import sys
import unittest
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import scipy
import statsmodels

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.engine import applicability
from src.engine_dh import dh_audit, test_pair, global_holm
from src.simulation import panel, SCENARIOS


def inspect_panel(stage, scenario, repetition, purpose):
    start = perf_counter()
    u, h, values = panel(stage, scenario, repetition)
    generated = perf_counter()
    gates = {s: applicability(values[s]) for s in u.ts_code}
    checked = perf_counter()
    rows, raw_p = [], []
    for candidate in h.to_dict("records"):
        a, b = values[candidate["A"]], values[candidate["B"]]
        row = test_pair((candidate, a, b, gates[candidate["A"]], gates[candidate["B"]]))
        # Synthetic inputs have known I(1) truth; inspect the kernel even if the ADF gate excludes a pair.
        raw = dh_audit(a, b) if row["compute_status"] == "precheck_placeholder" else row
        raw_p.append(raw["p_for_adjustment"])
        row.update(raw_DH_Q=raw.get("Q"), raw_DH_p=raw.get("p_raw"),
                   raw_DH_status=raw["compute_status"],
                   raw_DH_reason=raw["placeholder_reason"])
        rows.append(row)
    tested = perf_counter()
    full, main = global_holm(pd.DataFrame(rows), alpha=.05)
    finished = perf_counter()
    truth = full.true_alternative.to_numpy(bool)
    rejected = full.reject_GLOBAL_Holm.to_numpy(bool)
    A, R, V = int(truth.sum()), int(rejected.sum()), int((rejected & ~truth).sum())
    available = full.compute_status.eq("valid").to_numpy()
    survivors = int((truth & available).sum())
    metric = dict(purpose=purpose, geometry=stage, scenario=scenario, repetition=repetition,
                  stocks=len(u), pairs=len(h), kernel_calls=len(h), true_alternatives=A,
                  discoveries=R, false_discoveries=V, false_any=int(V > 0),
                  power=float((rejected & truth).sum()/A) if A else None,
                  conditional_power=float((rejected & truth).sum()/survivors) if survivors else None,
                  raw_null_rejection=float((np.array(raw_p)[~truth] < .05).mean()) if (~truth).any() else None,
                  precheck_placeholders=int(full.compute_status.eq("precheck_placeholder").sum()),
                  numerical_count=int(full.raw_DH_status.ne("valid").sum()),
                  stock_I1_fraction=float(np.mean([g["compatible"] for g in gates.values()])),
                  dgp_seconds=generated-start, precheck_seconds=checked-generated,
                  all_pairs_seconds=tested-checked, holm_seconds=finished-tested,
                  total_seconds=finished-start)
    full["purpose"], full["geometry"] = purpose, stage
    full["scenario"], full["repetition"] = scenario, repetition
    assert len(full) == len(h) and full.candidate_id.is_unique
    assert len(main) == R and full.M_GLOBAL.eq(len(h)).all()
    return metric, full


def make_budget(metrics, repeats):
    timing = metrics[(metrics.purpose == "timing") & (metrics.geometry == "S2")]
    rates = dict(pair_seconds=timing.all_pairs_seconds/timing.pairs,
                 precheck_stock_seconds=timing.precheck_seconds/timing.stocks,
                 dgp_stock_seconds=timing.dgp_seconds/timing.stocks,
                 holm_pair_seconds=timing.holm_seconds/timing.pairs)
    rate_summary = {key: dict(low=float(x.min()), median=float(x.median()), high=float(x.max()))
                    for key, x in rates.items()}
    slowdown = float(repeats.groupby("scenario").total_seconds.apply(
        lambda x: x.max()/x.min()).max())
    market = json.loads((ROOT/"RESEARCH_STATUS.json").read_text(encoding="utf-8"))["stage1_production"]
    plans = [
        ("development_15x100_40stocks", 1500, 40, 180),
        ("formal_S1_15x1000", 15000, 40, 180),
        ("formal_S2_5x500", 2500, 120, 1740),
        ("market_once", 1, market["stocks"], market["candidates"]),
        ("market_geometry_5x100", 500, market["stocks"], market["candidates"]),
        ("market_geometry_5x300", 1500, market["stocks"], market["candidates"]),
    ]
    estimates = []
    for name, panels, stocks, pairs in plans:
        estimates.append(dict(
            plan=name, panels=panels, stocks=stocks, pairs_per_panel=pairs,
            pair_system_tests=panels*pairs,
            **{f"serial_hours_{bound}": panels * (
                stocks*(rate_summary["precheck_stock_seconds"][bound] +
                        rate_summary["dgp_stock_seconds"][bound]) +
                pairs*(rate_summary["pair_seconds"][bound] +
                       rate_summary["holm_pair_seconds"][bound]))/3600
               for bound in ("low", "median", "high")}))
        estimates[-1]["serial_hours_slow_repeat_scenario"] = (
            estimates[-1]["serial_hours_median"] * slowdown)
    return dict(rates=rate_summary, estimates=estimates,
                observed_same_input_wall_slowdown=slowdown,
                basis="Three 120-stock / 1740-pair synthetic panels, one worker, BLAS=1; all pairs evaluated.",
                limitations=[
                    "Ranges reflect three measured mechanisms, not confidence or prediction intervals.",
                    "Slow-repeat column multiplies the median by observed same-input wall-time variation; it is not a guaranteed upper bound.",
                    "Full-market input/output, larger-memory effects and parallel speedup have not been measured.",
                    "Holm sorting is extrapolated linearly; full-scale overhead may differ.",
                    "No market prices or full-scale synthetic panel were evaluated."])


def main():
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    out = ROOT/"results_dh_dev"/now.strftime("%Y%m%dT%H%M%S")
    out.mkdir(parents=True, exist_ok=False)
    state = dict(status="running", kind="engineering_only", started_at=now.isoformat(),
                 method="DH2018-bivariate-development", lags=7, nominal_alpha=.05,
                 maximum_tolerated_FWER=.10, tolerance_used_as_test_alpha=False,
                 formal_calibration="not_run", full_market_test="not_run",
                 remote_used=False, benchmark_workers=1, blas_threads=1,
                 seed_policy="v1 panel formula; repetitions 10000-10004 consumed for development only",
                 source_doi="10.1111/obes.12214",
                 source_pages="accepted manuscript pp7-9, Appendix S1 pp29-37",
                 scope="75 S0 engineering panels, 9 larger timings and 6 same-input timing repeats; not statistical acceptance",
                 python=sys.version, packages=dict(numpy=np.__version__, pandas=pd.__version__,
                     scipy=scipy.__version__, statsmodels=statsmodels.__version__))
    def save():
        (out/"development.json").write_text(
            json.dumps(state, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    save()
    print(f"OUTPUT={out}", flush=True)
    print(f"PID={os.getpid()}", flush=True)
    start = perf_counter()
    try:
        with (out/"tests.txt").open("w", encoding="utf-8") as log:
            suite = unittest.defaultTestLoader.discover(str(ROOT/"tests"))
            result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
        state["unit_tests"] = dict(run=result.testsRun, failures=len(result.failures),
                                  errors=len(result.errors), skipped=len(result.skipped))
        save()
        if not result.wasSuccessful():
            raise RuntimeError("Unit tests failed; see tests.txt. No engineering panels run.")
        scenarios = [s for s in SCENARIOS if s != "N1"]
        specs = [("S0", s, 10000+r, "smoke") for s in scenarios for r in range(5)]
        specs += [("S1", s, 10000+r, "timing") for s in ("N0", "N6", "M1") for r in range(2)]
        specs += [("S2", s, 10000, "timing") for s in ("N0", "N6", "M1")]
        metrics = []
        pair_columns = None
        for stage, scenario, repetition, purpose in specs:
            metric, full = inspect_panel(stage, scenario, repetition, purpose)
            if pair_columns is None:
                pair_columns = list(full.columns)
            assert list(full.columns) == pair_columns, "Inconsistent CSV column order"
            metrics.append(metric)
            full.to_csv(out/"pairs.csv", mode="a", header=len(metrics)==1, index=False)
            pd.DataFrame([metric]).to_csv(out/"panels.csv", mode="a",
                                        header=len(metrics)==1, index=False)
            state["completed_panels"] = len(metrics)
            save()
            if purpose == "timing" or repetition == 10004:
                print(f"{purpose} {stage} {scenario}: {len(metrics)}/{len(specs)} panels; "
                      f"last={metric['total_seconds']:.3f}s", flush=True)
        frame = pd.DataFrame(metrics)
        smoke = frame[frame.purpose == "smoke"]
        assert len(smoke) == 75 and int(smoke.kernel_calls.sum()) == 900
        assert len(frame) == 84 and int(frame.kernel_calls.sum()) == 7200
        summary = smoke.groupby("scenario", sort=False).agg(
            panels=("scenario", "size"), pairs=("pairs", "sum"),
            false_event_panels=("false_any", "sum"),
            discoveries=("discoveries", "sum"), false_discoveries=("false_discoveries", "sum"),
            power=("power", "mean"), conditional_power=("conditional_power", "mean"),
            raw_null_rejection=("raw_null_rejection", "mean"),
            stock_I1_fraction=("stock_I1_fraction", "mean"),
            precheck_placeholders=("precheck_placeholders", "sum"),
            numerical_count=("numerical_count", "sum"))
        summary.to_csv(out/"smoke_summary.csv")
        repeats = []
        for timing_pass in range(2):
            for scenario in ("N0", "A0", "N7"):
                metric, _ = inspect_panel("S1", scenario, 10000, "timing_repeat")
                repeats.append(dict(metric, timing_pass=timing_pass))
        repeats = pd.DataFrame(repeats)
        repeats.to_csv(out/"timing_followup.csv", index=False)
        budget = make_budget(frame, repeats)
        pd.DataFrame(budget["estimates"]).to_csv(out/"budget.csv", index=False)
        state.update(status="complete", unit_tests_passed=True, completed_panels=len(frame),
                     kernel_calls=int(frame.kernel_calls.sum()),
                     timing_repeat_evaluations=len(repeats), timing_repeat_kernel_calls=1080,
                     numerical_count=int(frame.numerical_count.sum()),
                     budget=budget, elapsed_seconds=perf_counter()-start,
                     completed_at=datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
                     statistical_acceptance="not_assessed; five smoke repeats per mechanism are insufficient")
        save()
        print(json.dumps({k:state[k] for k in ("status","completed_panels","kernel_calls",
                                              "numerical_count","elapsed_seconds")}), flush=True)
    except BaseException as error:
        state.update(status="failed", error=f"{type(error).__name__}: {error}",
                     elapsed_seconds=perf_counter()-start)
        save()
        raise


if __name__ == "__main__":
    main()
