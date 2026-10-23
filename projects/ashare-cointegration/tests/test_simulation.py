import unittest
import numpy as np
import pandas as pd
from src.simulation import panel,STAGES,SCENARIOS,summarize


class SimulationTests(unittest.TestCase):
    def test_binary_mcse_matches_predeclared_formula(self):
        frame=pd.DataFrame([dict(stage='S1',scenario='N0',domain='L2',family='G0',method='Holm',
            false_any=x,FDP=x,power=np.nan,raw_null_rejection=.1,stock_I1_fraction=.9,
            applicable_pair_fraction=.8,any_local_family_false=x) for x in [0,0,0,1]])
        result=summarize(frame).iloc[0]
        self.assertAlmostEqual(result.FWER_MCSE,np.sqrt(.25*.75/4))
        self.assertAlmostEqual(result.any_local_family_FWER_MCSE,np.sqrt(.25*.75/4))
        self.assertAlmostEqual(result.FDR_MCSE,frame.FDP.std(ddof=1)/2)

    def test_truth_and_deterministic_panels(self):
        for stage in STAGES:
            for scenario in SCENARIOS:
                u,h,values=panel(stage,scenario,0)
                self.assertEqual(len(h),STAGES[stage][1]*STAGES[stage][2]*(STAGES[stage][2]-1)//2)
                self.assertTrue(np.isfinite(np.array(list(values.values()))).all())
                np.testing.assert_allclose([v[0] for v in values.values()],100)
                if scenario.startswith("N"):
                    self.assertFalse(h.true_alternative.any())
                if scenario.startswith("A"):
                    self.assertTrue(h.true_alternative.all())
                if stage=="S0" and scenario.startswith("M"):
                    self.assertEqual(int(h.loc[h.layer=="T","true_alternative"].sum()),4)
                    self.assertEqual(int(h.loc[h.layer=="C","true_alternative"].sum()),0)
        a=panel("S0","N6",1)[2];b=panel("S0","N6",1)[2]
        for code in a:
            np.testing.assert_array_equal(a[code],b[code])
