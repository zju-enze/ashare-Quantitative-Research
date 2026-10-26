"""Synthetic arithmetic checks; these data never enter empirical outputs."""
from pathlib import Path
import json
import sys
import unittest
import numpy as np
import pandas as pd
import statsmodels.api as sm

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, json.loads((ROOT / '.local/paths.json').read_text(encoding='utf-8-sig'))['course_root'])
sys.path.insert(0, str(ROOT / 'src'))
import bp_core as bp


class CoreTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(42)
        self.calendar = pd.DataFrame({'signal_month': ['2020-01', '2020-02'], 'holding_month': ['2020-02', '2020-03']})
        g = pd.DataFrame({'ts_code': [f'{i:06}' for i in range(80)], 'pb': rng.lognormal(1, .6, 80),
                          'total_mv': rng.lognormal(12, 1, 80), 'circ_mv': rng.lognormal(10, .8, 80),
                          'industry_code': np.repeat(['A', 'B'], 40)})
        self.panel = pd.concat([g.assign(signal_month=m) for m in self.calendar.signal_month], ignore_index=True)
        self.formed, self.status = bp.form_pool(self.panel, self.calendar)
        self.responses = self.panel[['signal_month', 'ts_code']].assign(ret_fwd=rng.normal(.005, .07, 160))

    def test_missing_response_keeps_transforms_holdings_and_turnover(self):
        full = bp.evaluate_layers(self.formed, self.status, self.responses, self.calendar)
        missing = self.responses.drop(index=0)
        got = bp.evaluate_layers(self.formed, self.status, missing, self.calendar)
        pd.testing.assert_frame_equal(full['holdings'], got['holdings'])
        pd.testing.assert_frame_equal(full['turnover'], got['turnover'])
        with_future = self.panel.merge(missing, on=['signal_month', 'ts_code'], how='left')
        again, _ = bp.form_pool(with_future, self.calendar)
        for month in self.formed:
            pd.testing.assert_frame_equal(self.formed[month], again[month])
        q = full['holdings'].iloc[0].layer
        self.assertTrue(np.isnan(got['layers_net'].iloc[0][q]))
        self.assertTrue(np.isnan(got['benchmark'].iloc[0]))
        self.assertEqual(got['n_response'].iloc[0], 79)
        self.assertEqual(got['layers_net'].iloc[0].isna().sum(), 1)

    def test_frozen_wls_matches_statsmodels_and_course_complete_case(self):
        g = self.formed['2020-01'].merge(self.responses.query('signal_month == "2020-01"'), on='ts_code')
        a, t, reason = bp.frozen_wls(g)
        expected = bp.course.wls_factor_ret_t(g, 'bp')
        np.testing.assert_allclose([a, t], expected, rtol=1e-10)
        g = g.iloc[1:]
        x = bp.course._design(g, ['bp_z', 'ln_mv'])
        model = sm.WLS(g.ret_fwd.to_numpy(), x, weights=g.w_wls.to_numpy()).fit()
        a, t, reason = bp.frozen_wls(g)
        np.testing.assert_allclose([a, t], [model.params[1], model.tvalues[1]], rtol=1e-10)
        self.assertEqual(reason, 'ok')

    def test_costs_first_period_and_both_legs(self):
        res = bp.evaluate_layers(self.formed, self.status, self.responses, self.calendar)
        np.testing.assert_allclose(res['turnover'].iloc[0], 1)
        np.testing.assert_allclose(res['turnover'].iloc[1], 0)
        expected = res['layers_gross'][5] - res['layers_gross'][1] - .004 * (res['turnover'][5] + res['turnover'][1])
        np.testing.assert_allclose(res['long_short'], expected)
        self.assertAlmostEqual((res['layers_gross'][5] - res['layers_gross'][1] - res['long_short']).iloc[0], .008)

    def test_initial_loss_and_missing_month_not_hidden(self):
        s = pd.Series([-.1, .05], index=pd.period_range('2020-01', periods=2, freq='M'))
        self.assertAlmostEqual(bp.performance(s)['max_dd'], -.1)
        self.assertEqual(bp.nav(s)[0], 1)
        idx = pd.period_range('2020-01', periods=13, freq='M').delete(5)
        r = pd.Series(.01, index=idx)
        self.assertTrue(np.isnan(bp.performance(r)['ann']))
        roll = bp.rolling_excess({'layers_net': pd.DataFrame({1:r}), 'benchmark': r*0})
        self.assertEqual(len(roll), 13)
        self.assertTrue(roll.isna().all().all())
        self.assertTrue(np.isnan(bp.nav(r)[-1]))

    def test_tie_breaks_and_degenerate_formation_are_explicit(self):
        g = self.formed['2020-01'].copy()
        g['f_neu'] = np.repeat(np.arange(20), 4)
        a, _ = bp.assign_layers(g, 5, 50, 20)
        b, _ = bp.assign_layers(g.sample(frac=1, random_state=1), 5, 50, 20)
        pd.testing.assert_frame_equal(a, b)
        _, reason = bp.form_cross_section(self.panel.assign(pb=1).iloc[:80])
        self.assertEqual(reason, 'insufficient_sample_or_distinct_bp')


if __name__ == '__main__':
    unittest.main()
