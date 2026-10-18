"""Independent release acceptance from frozen tables (no statsmodels correction call)."""
from pathlib import Path
from datetime import datetime,timezone
import argparse
import json
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]


def adjustment(p,method):
    p=np.asarray(p,float);m=len(p)
    if not m:return p
    order=np.argsort(p,kind="stable");rank=np.arange(1,m+1)
    if method=="BF":return np.minimum(1,m*p)
    values=(m-rank+1)*p[order] if method=="Holm" else m*p[order]/rank
    values=np.maximum.accumulate(values) if method=="Holm" else np.minimum.accumulate(values[::-1])[::-1]
    output=np.empty(m);output[order]=np.minimum(1,values)
    return output


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--run-id",default="formation-2021-2025-v2")
    args=parser.parse_args();run=ROOT/".local/production"/args.run_id
    assert not (run/"invalidation.json").exists(),"Superseded input must not be accepted"
    np.testing.assert_allclose(adjustment([.01,.04,.03],"BF"),[.03,.12,.09])
    np.testing.assert_allclose(adjustment([.01,.04,.03],"Holm"),[.03,.06,.06])
    np.testing.assert_allclose(adjustment([.01,.04,.03],"BH"),[.03,.04,.04])
    u=pd.read_parquet(run/"U.parquet");h=pd.read_parquet(run/"H.parquet")
    full=pd.read_parquet(run/"full_results.parquet")
    main=pd.read_csv(ROOT/"results/main_evidence.csv",float_precision="round_trip",dtype={"L2":str,"L3_A":str,"L3_B":str})
    sizes=u.groupby("L2").size();sizes3=u.groupby("L3").size()
    assert len(h)==int((sizes*(sizes-1)//2).sum())
    assert int((h.layer=="T").sum())==int((sizes3*(sizes3-1)//2).sum())
    assert not h.candidate_id.duplicated().any() and (h.A<h.B).all()
    assert h.candidate_id.tolist()==full.candidate_id.tolist()
    assert not u.ts_code.str.startswith("689").any()
    valid=full.compute_status.isin(["valid","tail_unresolved"])
    pre=full.compute_status.eq("precheck_placeholder")
    numerical=full.compute_status.eq("numerically_ineligible")
    assert (valid.astype(int)+pre.astype(int)+numerical.astype(int)).eq(1).all()
    assert full.loc[~valid,"p_for_adjustment"].eq(1).all()
    assert full.loc[~valid,"p_raw"].isna().all()
    assert full.loc[valid,"p_raw"].eq(full.loc[valid,"p_for_adjustment"]).all()
    expected_main=set()
    for domain,key in [("L3","L3_family"),("L2","L2"),("GLOBAL",None)]:
        groups=[("GLOBAL",full)] if key is None else full.groupby(key)
        for family,g in groups:
            assert g[f"M_{domain}"].eq(len(g)).all()
            for method in ("BF","Holm","BH"):
                independent=adjustment(g.p_for_adjustment,method)
                np.testing.assert_allclose(independent,g[f"p_{domain}_{method}"],atol=2e-15,rtol=1e-13)
                np.testing.assert_array_equal(independent<=.05,g[f"reject_{domain}_{method}"].to_numpy(bool))
                if domain=="L2" and method=="Holm":
                    expected_main.update(g.loc[(independent<=.05)&valid.loc[g.index],"candidate_id"])
    assert set(main.candidate_id)==expected_main and not main.candidate_id.duplicated().any()
    matching=full.set_index("candidate_id").loc[main.candidate_id]
    for column in ["alpha","beta","EG_stat","p_raw","p_L2_Holm","M_L2","N_input","N_effective"]:
        np.testing.assert_allclose(main[column],matching[column],atol=1e-15,rtol=1e-13)
    for column in ["A","B","L2","L3_A","L3_B","layer","compute_status","input_version","code_version"]:
        assert main[column].tolist()==matching[column].tolist(),column
    for method in ("BF","Holm","BH"):
        assert full.loc[full.layer=="C",f"p_L3_{method}"].isna().all()
        assert full.loc[full.layer=="C",f"reject_L3_{method}"].isna().all()
    result=dict(status="passed",run_id=args.run_id,checked_at=datetime.now(timezone.utc).isoformat(),
                stocks=len(u),candidates=len(h),main_discoveries=len(main),
                all_family_sizes_and_terminal_states=True,independent_three_domain_three_method_formulas=True,
                main_exactly_independent_L2_Holm=True,CSV_rows_match_full_table=True,CDR_excluded=True)
    (ROOT/"results/independent_acceptance.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
