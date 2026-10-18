import unittest
import numpy as np
import pandas as pd
from src.data import audit_quotes,ORDINARY_CODE_PATTERN


class DataTests(unittest.TestCase):
    def test_depositary_receipt_is_not_ordinary_share(self):
        codes=pd.Series(["sh.689009","sh.688981","sh.600036","sz.000001","sz.300750","sh.900901","sz.159915"])
        self.assertEqual(codes.str.match(ORDINARY_CODE_PATTERN).tolist(),
                         [False,True,True,True,True,False,False])

    def test_coordinate_seed_and_decimal_identity(self):
        dates=["2021-01-04","2021-01-05","2021-01-06"]
        raw=pd.DataFrame(dict(date=dates,close=["10.0000","5.0000","6.0000"],
                              volume=["100"]*3,tradestatus=["1"]*3,isST=["0"]*3))
        hfq=pd.DataFrame(dict(date=dates,close=["20.0000000000","20.0000000000","24.0000000000"]))
        factors=pd.DataFrame(dict(dividOperateDate=["2020-01-01","2021-01-05"],
                                  backAdjustFactor=["2.000000","4.000000"]))
        info,reasons,price=audit_quotes(raw,hfq,factors,dates)
        self.assertEqual(reasons,[])
        np.testing.assert_array_equal(price,[10,10,12])
        self.assertEqual(info["seed_factor"],"2.000000")
        bad=hfq.copy();bad.loc[1,"close"]="20.0000000001"
        self.assertIn("adjustment",audit_quotes(raw,bad,factors,dates)[1])
        self.assertEqual(audit_quotes(raw,hfq,factors.iloc[1:],dates)[0]["adjustment_status"],
                         "missing_historical_seed")
        gap=raw.iloc[1:].copy()
        self.assertIn("raw_data_and_continuity",audit_quotes(gap,None,None,dates)[1])
        same_day=factors.copy();same_day.loc[0,"dividOperateDate"]=dates[0]
        self.assertEqual(audit_quotes(raw,hfq,same_day,dates)[0]["seed_effective_date"],dates[0])
