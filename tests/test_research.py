"""Regression tests for errors that can change the research conclusion."""
from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"src"))
from ashare_research import (monthly_prices, annual_versions, reports_asof,
                             quintile_returns, grs_test, historical_st, mean_hac,
                             fama_macbeth, block_bootstrap, SIGNALS, standardize)
import statsmodels.api as sm


class ResearchTests(unittest.TestCase):
    def prices(self, dates, closes, factors):
        d = pd.DataFrame({"ts_code": "A", "trade_date": dates, "close": closes,
                          "vol": 1, "amount": 100})
        a = d[["ts_code", "trade_date"]].assign(adj_factor=factors)
        return monthly_prices(d, a)

    def test_split_adjustment_and_forward_target(self):
        m = self.prices(["20200131", "20200228", "20200331"], [100, 50, 60], [1, 2, 2])
        self.assertAlmostEqual(m.loc[0, "ret_next"], 0)
        self.assertAlmostEqual(m.loc[1, "ret_next"], .2)
        self.assertAlmostEqual(m.loc[1, "raw_ret"], -.5)

    def test_calendar_gap_is_not_a_monthly_return(self):
        m = self.prices(["20200131", "20200331"], [100, 120], [1, 1])
        self.assertTrue(m["ret_next"].isna().all())
        self.assertTrue(m["ret"].isna().all())

    def test_momentum_excludes_current_month(self):
        dates = pd.period_range("2020-01", periods=15, freq="M").to_timestamp("M").strftime("%Y%m%d")
        closes = 100*1.01**np.arange(15)
        m = self.prices(dates, closes, np.ones(15))
        altered = closes.copy()
        altered[-1] *= 2
        m2 = self.prices(dates, altered, np.ones(15))
        self.assertAlmostEqual(m.loc[14, "mom"], 1.01**11-1)
        self.assertAlmostEqual(m.loc[14, "mom"], m2.loc[14, "mom"])

    def test_future_revision_not_available_at_formation(self):
        v = pd.DataFrame({"ts_code": ["A", "A"], "fiscal_year": [2019, 2019],
                          "available_date": pd.to_datetime(["2020-04-01", "2020-08-01"]), "value": [10., 99.]})
        m = pd.DataFrame({"ts_code": ["A", "A", "A"],
                          "trade_date": pd.to_datetime(["2020-04-01", "2020-06-30", "2020-09-30"])})
        result = reports_asof(m, v, ["value"])
        self.assertTrue(np.isnan(result.loc[0, "value"]))
        self.assertEqual(result.loc[1, "value"], 10)
        self.assertEqual(result.loc[2, "value"], 99)

    def test_conflicting_reports_do_not_pick_an_arbitrary_value(self):
        d = pd.DataFrame({"ts_code": ["A", "A"], "report_type": "1", "end_date": "20191231",
                          "ann_date": "20200401", "f_ann_date": "20200401", "value": [10, 20]})
        versions, conflicts = annual_versions(d, ["value"])
        self.assertEqual(conflicts, 1)
        self.assertTrue(versions["value"].isna().all())

    def test_sorting_uses_forward_returns(self):
        d = pd.DataFrame({"ym": pd.Period("2020-01", "M"), "factor": np.arange(100),
                          "ret": -np.arange(100)/100, "ret_next": np.arange(100)/100})
        result = quintile_returns(d, "factor")
        self.assertEqual(result.index[0], pd.Period("2020-02", "M"))
        self.assertGreater(result.iloc[0]["spread"], 0)

    def test_historical_st_is_date_specific(self):
        m = pd.DataFrame({"ts_code": ["A", "A"], "trade_date": pd.to_datetime(["2020-06-30", "2021-06-30"])})
        names = pd.DataFrame({"ts_code": ["A"], "name": ["ST Example"], "start_date": ["20210101"],
                              "ann_date": ["20201231"], "end_date": [None]})
        self.assertEqual(historical_st(m, names).tolist(), [False, True])

    def test_future_missingness_does_not_change_sort_breakpoints(self):
        d = pd.DataFrame({"ym": pd.Period("2020-01", "M"), "factor": np.arange(100),
                          "ret_next": np.arange(100)/100})
        d.loc[0, "ret_next"] = np.nan
        result = quintile_returns(d, "factor").iloc[0]
        self.assertAlmostEqual(result['Q1'], np.arange(1, 20).mean()/100)
        self.assertEqual(result['stocks'], 100)

    def test_grs_normalization_against_known_covariances(self):
        t = 60
        factor = np.tile([-1., 1.], t//2)+.2
        x = np.column_stack([np.ones(t), factor])
        rng = np.random.default_rng(12)
        raw = rng.normal(size=(t, 2))
        residual = raw-x@np.linalg.lstsq(x, raw, rcond=None)[0]
        q, _ = np.linalg.qr(residual)
        y = np.array([.01, .02])+factor[:, None]*np.array([.5, 1.])+q*np.sqrt(t-2)
        idx = pd.period_range("2000-01", periods=t, freq="M")
        result, _ = grs_test(pd.DataFrame(y, index=idx, columns=["A", "B"]),
                             pd.DataFrame({"MKT": factor}, index=idx))
        expected = (60/2)*(57/58)*(.01**2+.02**2)/(1+.2**2/(60/59))
        self.assertAlmostEqual(result["grs"], expected, places=12)

    def test_hac_lags_preserve_missing_calendar_months(self):
        s = pd.Series([1., -1.], index=pd.PeriodIndex(['2020-01', '2020-03'], freq='M'))
        self.assertAlmostEqual(mean_hac(s, lags=1)['se_hac'], np.sqrt(2)/2)

    def test_six_signal_fm_matches_ols_and_size_does_not_control_itself(self):
        rng = np.random.default_rng(7)
        panel = pd.DataFrame({"ym": np.repeat(pd.period_range('2017-09', periods=6, freq='M'), 120),
                              "industry": np.tile(np.repeat(['A', 'B', 'C'], 40), 6),
                              "ret_next": rng.normal(0, .1, 720)})
        for column, _ in SIGNALS.values():
            panel[column] = rng.lognormal(size=720)
        for signal, (column, long_top) in SIGNALS.items():
            prepared, coefficients, summary = fama_macbeth(panel, signal)
            first = prepared.loc[prepared['ym'] == pd.Period('2017-09', freq='M')]
            values = np.log(first[column]) if signal == 'Size' else first[column]
            f = standardize(values) * (1 if long_top else -1)
            industry = pd.get_dummies(first['industry'], drop_first=True, dtype=float)
            x = pd.concat([f.rename('signal'), industry], axis=1)
            if signal != 'Size':
                x['size'] = standardize(np.log(first['mktcap']))
            expected = sm.OLS(first['ret_next'], sm.add_constant(x)).fit().params['signal']
            self.assertAlmostEqual(coefficients.iloc[0]['Industry_controlled'], expected, places=12)
            self.assertEqual('Size_controlled' in coefficients, signal != 'Size')
            self.assertEqual(set(summary['signal']), {signal})
            self.assertEqual(set(summary['period']), {'Full', 'Development_2005_2017', 'Holdout_2018_2024'})

    def test_bootstrap_retains_calendar_gaps_and_matches_direct_resampling(self):
        index = pd.period_range('2020-01', periods=15, freq='M')
        values = np.array([.02, -.01, .03, np.nan, np.nan, .01, -.03, .04, .01, .02, -.02, .01, .03, -.01, .02])
        result = block_bootstrap(pd.Series(values, index=index).dropna(), repetitions=100, block_length=3)
        starts = np.random.default_rng(42).integers(0, 13, size=(100, 5))
        simulated = []
        for row in starts:
            sample = np.concatenate([values[start:start+3] for start in row])
            observed = sample[~np.isnan(sample)]
            simulated.append(observed.mean()/observed.std(ddof=1)*np.sqrt(12))
        self.assertEqual(result['calendar_months'], 15)
        self.assertEqual(result['months'], 13)
        self.assertEqual(result['missing_months'], 2)
        np.testing.assert_allclose([result['ci_low'], result['ci_high']], np.quantile(simulated, [.025, .975]))


if __name__ == "__main__":
    unittest.main()
