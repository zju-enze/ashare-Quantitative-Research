"""Check the 23 used-prefix repairs against the existing independent IV reference."""
import os
for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[key] = "1"
import importlib.util
import json
from pathlib import Path
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.simulation_dh import dh_audit_fields, write_json


def main():
    protocol = json.loads((ROOT/"experiment_protocol_v2_frozen.json").read_text(encoding="utf-8"))
    parent = ROOT/".local/dh_v2/production"
    initial = parent/protocol["market"]["run_id"]
    current = parent/(protocol["market"]["run_id"]+"__used-prefix")
    old = pd.read_parquet(initial/"full_results.parquet")
    new = pd.read_parquet(current/"full_results.parquet")
    assert old.candidate_id.tolist() == new.candidate_id.tolist()
    affected = old.compute_status.eq("numerically_ineligible") & old.placeholder_reason.eq("recursive_regression_rank_deficient")
    assert int(affected.sum()) == 23
    pd.testing.assert_frame_equal(old.loc[~affected, list(dh_audit_fields())],
                                  new.loc[~affected, list(dh_audit_fields())],
                                  check_dtype=False, check_exact=True)
    assert not new.loc[~affected, "prefix_guard_corrected"].any()
    assert new.loc[affected, "prefix_guard_corrected"].all()
    assert new.loc[affected, "compute_status"].eq("valid").all()
    universe = pd.read_parquet(current/"U.parquet")
    positions = {code: i for i, code in enumerate(universe.ts_code)}
    values = np.load(current/"prices.npy", mmap_mode="r")
    spec = importlib.util.spec_from_file_location("dh_literal_reference", ROOT/"tests/test_engine_dh.py")
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    rows = []
    for row in new.loc[affected].itertuples():
        a, b = values[:, positions[row.A]], values[:, positions[row.B]]
        shifted = b-b[0]
        centered = shifted-np.cumsum(shifted)/np.arange(1, len(b)+1)
        denominator = np.cumsum(centered*centered)
        assert denominator[2] == 0 and np.all(denominator[7:-1] > 0)
        ref = reference.literal_reference(a, b, 7)
        np.testing.assert_allclose(row.Q, ref["Q"], rtol=1e-8, atol=1e-10)
        np.testing.assert_allclose([row.adjustment_A, row.adjustment_B], ref["adjustment"], rtol=1e-8, atol=1e-10)
        np.testing.assert_allclose(row.p_raw, ref["p"], rtol=1e-7, atol=1e-14)
        rows.append(dict(candidate_id=row.candidate_id, B=row.B,
            first_changed_index=int(np.flatnonzero(b != b[0])[0]), first_used_error_index=7,
            Q=row.Q, reference_Q=ref["Q"], raw_p=row.p_raw, reference_p=ref["p"],
            Q_relative_error=abs(row.Q-ref["Q"])/max(abs(ref["Q"]), 1e-12)))
    result = dict(status="passed", checked_at=datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        corrected_pairs=len(rows), unaffected_pair_audits_unchanged=int((~affected).sum()),
        initial_run_id=initial.name, corrected_run_id=current.name,
        calibration_unchanged_basis="All formal ungated kernel evaluations were valid, so the new fallback is never entered for them",
        scope="Engineering formula and preservation check only; overall calibration remains inconclusive",
        reference="Existing independent prefix-loop plus full IV matrix reference in tests/test_engine_dh.py",
        max_Q_relative_error=max(r["Q_relative_error"] for r in rows), pairs=rows)
    write_json(ROOT/"results_v2/market_prefix_validation.json", result)
    print(json.dumps({k: v for k, v in result.items() if k != "pairs"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
