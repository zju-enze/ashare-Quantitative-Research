import os
for key in ('OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','OMP_NUM_THREADS'):
    os.environ[key]='1'
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from statsmodels.tsa.adfvalues import mackinnonp

from src import revision_pair as revision
from src.engine import eg_audit
from src.dgp_calibration import generate_pair
from tests.test_engine_dh import literal_reference

ROOT=Path(__file__).resolve().parents[1]


def fixture():
    spec=json.loads((ROOT/'results_review/dgp_fixed_nu_2021_2025/dgp_spec.json').read_text())
    return generate_pair(spec,240,np.random.SeedSequence([20261021,99,0,0]))


def hand_results():
    values={'EG-fixed-1':[.01,.06,.04,.8],'DH-fixed-1':[.2,.03,.04,.7],
            'EG-AIC':[.01,.06,.04,.8],'DH-fixed-7':[.2,.03,.04,.7]}
    return pd.DataFrame([dict(phase='formal',scenario='PAIR_NULL',repetition=r,
        method=method,p=probability,status='valid',true_alternative=False,
        used_lag=1,n_effective=238,seconds=.1,master_seed=20261021,seed_stream=21)
        for method,probabilities in values.items() for r,probability in enumerate(probabilities)])


class RevisionTests(unittest.TestCase):
    def test_fixed_eg_against_literal_residual_regression(self):
        a,b=fixture().T
        design=np.column_stack((b,np.ones(len(b))))
        residual=a-design@np.linalg.lstsq(design,a,rcond=None)[0]
        difference=np.diff(residual)
        x=np.column_stack((residual[1:-1],difference[:-1]))
        y=difference[1:]
        coefficients=np.linalg.lstsq(x,y,rcond=None)[0]
        errors=y-x@coefficients
        variance=float(errors@errors)/(len(y)-2)
        statistic=coefficients[0]/np.sqrt(variance*np.linalg.inv(x.T@x)[0,0])
        got=revision.eg_fixed_audit(a,b)
        self.assertAlmostEqual(got['EG_stat'],statistic,places=10)
        self.assertAlmostEqual(got['p_raw'],mackinnonp(statistic,regression='c',N=2),places=12)
        self.assertEqual(got['N_effective'],len(y))
        self.assertEqual(got['used_lag'],1)
        forced=revision.eg_fixed_audit(2*b,b)
        self.assertEqual(forced['p_for_adjustment'],1.)
        self.assertEqual(forced['p_zero_origin'],'near_collinearity_forced')

    def test_dh_lags_against_existing_independent_matrix_reference(self):
        a,b=fixture().T
        for lag in (1,7):
            expected=literal_reference(a,b,lag)
            actual=revision.dh_audit(a,b,lags=lag)
            self.assertEqual(actual['compute_status'],'valid')
            np.testing.assert_allclose(actual['Q'],expected['Q'],rtol=1e-9,atol=1e-10)
            self.assertEqual(actual['N_effective'],len(a)-lag-1)

    def test_unmodified_log_path_and_legacy_aic_reuse(self):
        values=fixture()-10.
        saved=values.copy()
        values.setflags(write=False)
        output=revision.run_methods(values)
        np.testing.assert_array_equal(values,saved)
        self.assertEqual(tuple(row['method'] for row in output),revision.METHODS)
        old=eg_audit(values[:,0],values[:,1])
        got=next(row for row in output if row['method']=='EG-AIC')
        self.assertEqual(got['statistic'],old['EG_stat'])
        self.assertEqual(got['p'],old['p_for_adjustment'])

    def test_summary_and_paired_mcse_with_hand_counts(self):
        frame=hand_results()
        summary=revision.summarize(frame)
        main=summary[summary.alpha.eq(.05)]
        self.assertTrue(main.repetitions.eq(4).all())
        self.assertTrue(main.rejections.eq(2).all())
        difference=revision.paired_comparisons(frame)
        row=difference.loc[difference.comparison.eq('primary') & difference.alpha.eq(.05)].iloc[0]
        self.assertEqual([row.EG_only,row.DH_only,row.both,row.neither],[1,1,1,1])
        self.assertAlmostEqual(row.paired_mcse,np.sqrt(1/6))
        self.assertEqual(revision.confidence_interval(0,4)[0],0.)
        self.assertEqual(revision.confidence_interval(4,4)[1],1.)

    def test_completed_checkpoint_is_reused_without_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            task=('PAIR_NULL',0,4)
            path=revision.checkpoint_path(directory,task)
            path.parent.mkdir(parents=True)
            hand_results().to_parquet(path,index=False)
            before=path.stat().st_mtime_ns
            protocol={'master_seed':20261021,'phases':{'formal':{'seed_stream':21}}}
            revision.initialize({},protocol,directory,'formal')
            with patch('src.revision_pair.generate_pair',side_effect=AssertionError('recomputed')):
                result=revision.run_batch(task)
            self.assertTrue(result['reused'])
            self.assertEqual(path.stat().st_mtime_ns,before)


if __name__=='__main__':
    unittest.main()
