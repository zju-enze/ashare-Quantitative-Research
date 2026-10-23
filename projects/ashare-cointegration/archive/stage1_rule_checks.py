"""Small artificial bookkeeping examples. No market inputs or EG scan."""
from itertools import combinations
from pathlib import Path
import json
import math
import numpy as np
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.proportion import proportion_confint

ROOT = Path(__file__).resolve().parents[1]


def test_record(gate=True, case="ordinary", p=.2, beta=1.0):
    row = {"I1_gate": gate, "EG_executed": bool(gate), "beta": beta,
           "case": case, "p_library": p if gate else None}
    if not gate:
        row.update(p_raw=None, p_for_adjustment=1., compute_status="i1_inapplicable",
                   placeholder_reason="I1_gate_failed", p_zero_origin=None)
    elif case in {"collinear", "nonfinite", "unresolved_error"}:
        row.update(p_raw=None, p_for_adjustment=1.,
                   compute_status="compute_error_unresolved" if case == "unresolved_error" else "numerically_ineligible",
                   placeholder_reason=case, p_zero_origin="library_collinearity_branch" if case == "collinear" else None)
    else:
        assert p is not None and math.isfinite(p) and 0 <= p <= 1
        row.update(p_raw=p, p_for_adjustment=p, compute_status="tested_valid_nominal",
                   placeholder_reason=None, p_zero_origin="approximation_boundary" if case == "finite_tail_zero" else None)
    return row


def corrections(rows):
    output = {}
    for domain in ["L3", "L2", "GLOBAL"]:
        families = {}
        for row in rows:
            if domain == "L3" and row["layer"] == "C":
                for method in ["BF", "Holm", "BH"]:
                    output[(row["candidate_id"], domain, method)] = {
                        "m": None, "p_adj": None, "reject": None, "applicable": False}
                continue
            family = row["L3"] if domain == "L3" else row["L2"] if domain == "L2" else "GLOBAL"
            families.setdefault(family, []).append(row)
        for group in families.values():
            p = np.array([row["p_for_adjustment"] for row in group])
            for label, method in [("BF","bonferroni"),("Holm","holm"),("BH","fdr_bh")]:
                rejected, adjusted, *_ = multipletests(p, alpha=.05, method=method)
                for row, reject, adj in zip(group, rejected, adjusted):
                    output[(row["candidate_id"], domain, label)] = {
                        "m": len(group), "p_adj": float(adj), "reject": bool(reject), "applicable": True}
    return output


def main():
    p = json.loads((ROOT / "experiment_protocol.json").read_text(encoding="utf-8"))
    assert p["version"] == "1.2" and p["current_stage"] == 1
    checks = {}
    fixture = [("A","X","X1"),("B","X","X1"),("C","X","X1"),
               ("D","X","X2"),("E","X","X2"),("F","Y","Y1"),("G","Y","Y1")]
    rows = []
    for a,b in combinations(fixture,2):
        if a[1] != b[1]:
            continue
        key = a[0]+b[0]
        row = test_record()
        row.update(candidate_id=key, A=a[0], B=b[0], L2=a[1],
                   L3=a[2] if a[2]==b[2] else None, layer="T" if a[2]==b[2] else "C")
        rows.append(row)
    by_id = {x["candidate_id"]: x for x in rows}
    specs = {"AB": test_record(p=.0001,beta=-.7), "AC": test_record(p=.002,beta=0),
             "AD": test_record(gate=False), "AE": test_record(case="collinear",p=0),
             "BC": test_record(case="finite_tail_zero",p=0),
             "BD": test_record(p=.3), "BE": test_record(case="unresolved_error",p=None),
             "CD": test_record(p=.02), "CE": test_record(p=.006),
             "DE": test_record(p=.4), "FG": test_record(p=.7)}
    for key, spec in specs.items():
        by_id[key].update(spec)
    assert len(rows)==11 and sum(x["layer"]=="T" for x in rows)==5
    assert sum(x["layer"]=="C" for x in rows)==6
    checks["candidate_enumeration_T_C"] = True
    out = corrections(rows)
    assert all(out[(x["candidate_id"],"GLOBAL","Holm")]["m"]==11 for x in rows)
    assert all(out[(x["candidate_id"],"L2","Holm")]["m"]==10 for x in rows if x["L2"]=="X")
    assert by_id["AD"]["p_raw"] is None and by_id["AD"]["p_for_adjustment"]==1
    assert by_id["AD"]["EG_executed"] is False
    checks["gate_placeholder_preserves_family"] = True
    for row in rows:
        if row["layer"]=="C":
            for m in ["BF","Holm","BH"]:
                assert out[(row["candidate_id"],"L3",m)] == {
                    "m":None,"p_adj":None,"reject":None,"applicable":False}
    checks["cross_L3_is_NA_not_one_or_rejected"] = True
    for row in rows:
        for d in ["L3","L2","GLOBAL"]:
            vals = [out[(row["candidate_id"],d,m)] for m in ["BF","Holm","BH"]]
            if vals[0]["applicable"]:
                assert not vals[0]["reject"] or vals[1]["reject"]
                assert not vals[1]["reject"] or vals[2]["reject"]
    checks["same_family_method_nesting"] = True
    assert by_id["AE"]["p_library"]==0 and by_id["AE"]["p_raw"] is None
    assert by_id["AE"]["p_for_adjustment"]==1
    assert by_id["BC"]["p_raw"]==0 and by_id["BC"]["p_for_adjustment"]==0
    assert by_id["BC"]["p_zero_origin"]=="approximation_boundary"
    assert by_id["BD"]["p_raw"]==.3 and by_id["BD"]["p_zero_origin"] is None
    checks["zero_p_and_numerical_status_distinguished"] = True
    extra = test_record(case="nonfinite",p=None)
    assert extra["compute_status"]=="numerically_ineligible" and extra["p_for_adjustment"]==1
    checks["nonfinite_has_explicit_placeholder"] = True
    discovered = [row for row in rows if out[(row["candidate_id"],"L2","Holm")]["reject"]]
    ids = {row["candidate_id"] for row in discovered}
    assert {"AB","AC"}.issubset(ids)
    assert any(row["beta"]<0 for row in discovered) and any(row["beta"]==0 for row in discovered)
    checks["nonpositive_beta_not_application_filtered"] = True
    assert ids == {row["candidate_id"] for row in rows if out[(row["candidate_id"],"L2","Holm")]["p_adj"]<=.05}
    checks["evidence_list_matches_main_correction_exactly"] = True
    assert not out[("FG","L2","Holm")]["reject"]
    assert any(row["candidate_id"]=="FG" for row in rows)
    checks["zero_discovery_family_and_nonrejections_retained"] = True
    production_complete = all(row["compute_status"]!="compute_error_unresolved" for row in rows)
    assert not production_complete
    checks["unresolved_computation_not_called_complete"] = True
    assert not p["stage1"]["monte_carlo_complete_required_for_list_delivery"]
    assert not p["stage1"]["later_stage_required_for_completion"]
    assert all(not x["required_by_stage1"] and not x["enabled"] for x in p["later_stages"].values())
    checks["production_calibration_application_states_independent"] = True

    # Small deterministic truth map, not a Monte Carlo run.
    def cluster(j):
        return 1 if j%5 in (0,1) else 2 if j%5 in (2,3) else 3+j
    truth = {"T":{"alternative":0,"null":0}, "C":{"alternative":0,"null":0}}
    for a,b in combinations(range(4),2):
        layer = "T" if a//2==b//2 else "C"
        truth[layer]["alternative" if cluster(a)==cluster(b) else "null"] += 1
    assert truth=={"T":{"alternative":2,"null":0},"C":{"alternative":0,"null":4}}
    assert p["simulation"]["S0_mixed_truth_per_L2"]==truth
    checks["S0_mixed_truth_counts"] = True
    scale = np.where(np.arange(1212)<1212//4,3.,1.)
    assert (scale[:303]==3).all() and (scale[303:]==1).all()
    stages = {x["name"]:x for x in p["simulation"]["stages"]}
    assert stages["S2"]["scenarios"]==["N1","N5","N6","M1"]
    assert stages["S1"]["scenarios"]=="all16"
    checks["early_volatility_drop_and_preserved_N7_in_S1"] = True
    X = np.array([[100.,102.,99.],[200.,198.,204.]])
    Y = 100*X/X[:,[0]]
    assert np.allclose(Y[:,0],100) and np.allclose(Y[:,1:]/Y[:,:-1],X[:,1:]/X[:,:-1])
    checks["fixed_simulation_normalization"] = True
    failures = np.array([[0,0],[0,0],[1,0],[0,0],[0,0]],dtype=int)
    wilson = []
    for family in range(2):
        successes = int(failures[:,family].sum())
        lo,hi = proportion_confint(successes,len(failures),alpha=.05,method="wilson")
        wilson.append({"fixed_family":family,"independent_panel_trials":len(failures),
                       "FWER_events":successes,"interval":[float(lo),float(hi)]})
    assert [x["independent_panel_trials"] for x in wilson]==[5,5]
    checks["Wilson_per_fixed_family_not_pooled"] = True

    result = {"all_inputs_synthetic":True, "market_files_read":[], "EG_market_scan_executed":False,
              "Monte_Carlo_executed":False,"real_2026_evaluation_executed":False,
              "checks":checks,"check_count":len(checks),"all_passed":all(checks.values()),
              "synthetic_candidate_count":11,"synthetic_main_discovery_ids":sorted(ids),
              "synthetic_main_discovery_beta":[row["beta"] for row in discovered],
              "synthetic_S0_truth":truth,"synthetic_Wilson_examples":wilson,
              "synthetic_batch_with_unresolved_error_complete":production_complete,
              "scope":"Specification bookkeeping checks, not a production screening implementation"}
    Path(__file__).with_name("synthetic_stage1_checks.json").write_text(
        json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")
    print(f"Passed {len(checks)} stage-1 synthetic checks; no market/OOS/Monte Carlo execution.")


if __name__=="__main__":
    main()
