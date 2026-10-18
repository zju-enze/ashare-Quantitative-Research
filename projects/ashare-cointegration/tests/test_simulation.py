import unittest
import numpy as np
from src.simulation import panel,STAGES,SCENARIOS


class SimulationTests(unittest.TestCase):
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
