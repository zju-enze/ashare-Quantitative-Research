import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
import run_stage1


class PipelineTests(unittest.TestCase):
    def test_frozen_pipeline_resume_and_main_identity(self):
        real_root=run_stage1.ROOT
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            (root/"results").mkdir();(root/"src").mkdir()
            for p in [real_root/"run_stage1.py",real_root/"experiment_protocol.json"]:
                shutil.copy2(p,root/p.name)
            for p in (real_root/"src").glob("*.py"):
                shutil.copy2(p,root/"src"/p.name)
            (root/"results"/"acquisition_status.json").write_text('{"status":"complete","errors":[]}')
            rng=np.random.default_rng(20261018)
            common=rng.normal(size=1212).cumsum()
            dates=pd.bdate_range("2021-01-04",periods=1212).strftime("%Y-%m-%d").tolist()
            rows=[]
            for i in range(4):
                code=f"sz.00000{i}";ts_code=f"00000{i}.SZ"
                folder=root/".local"/"market"/code;folder.mkdir(parents=True)
                (folder/"status.json").write_text(json.dumps(dict(status="complete",exclusion_tags=[])))
                values=100+(1 if i<2 else -1)*common+rng.normal(size=1212)
                pd.DataFrame(dict(date=dates,adjusted_close=values)).to_parquet(folder/"adjusted.parquet")
                rows.append(dict(code=code,ts_code=ts_code,name=ts_code,L2="G",L3=f"L{i//2}",
                                 exclusion_tags=[],primary_exclusion=None))
            u=pd.DataFrame(rows)
            cat=pd.DataFrame(dict(industry_code=["G","L0","L1","EMPTY"],level=["L2","L3","L3","L2"]))
            with patch.object(run_stage1,"ROOT",root),patch.object(run_stage1,"initial_universe",return_value=(u,cat,dates)),patch.object(
                run_stage1.subprocess,"check_output",return_value="synthetic-fixture"),patch(
                "sys.argv",["run_stage1.py","--workers","2","--run-id","synthetic"]):
                run_stage1.main()
                run=root/".local"/"production"/"synthetic"
                full=pd.read_parquet(run/"full_results.parquet")
                self.assertEqual(len(full),6)
                main=pd.read_csv(root/"results"/"main_evidence.csv")
                self.assertEqual(set(main.candidate_id),set(full.loc[full.reject_L2_Holm,"candidate_id"]))
                self.assertTrue((main.beta<0).any())
                run_stage1.main()
                pd.testing.assert_frame_equal(full,pd.read_parquet(run/"full_results.parquet"))
                modified=json.loads((root/"experiment_protocol.json").read_text(encoding="utf8"))
                modified["changed"]=True
                (root/"experiment_protocol.json").write_text(json.dumps(modified),encoding="utf8")
                with self.assertRaisesRegex(RuntimeError,"Frozen code"):
                    run_stage1.main()
