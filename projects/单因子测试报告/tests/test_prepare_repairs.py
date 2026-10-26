from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from prepare_local_repairs import canonical_codes, collapse_equal_alias_rows, industry_asof
from fetch_endpoint_status import read_status_snapshot


class RepairInputsTests(unittest.TestCase):
    def test_explicit_aliases_do_not_guess_by_suffix(self):
        aliases = pd.DataFrame({"old_code": ["837023.BJ"], "new_code": ["920123.BJ"]})
        got = canonical_codes(pd.Series(["837023.BJ", "920123.BJ", "830123.BJ"]), aliases)
        self.assertEqual(got.tolist(), ["920123.BJ", "920123.BJ", "830123.BJ"])

    def test_industry_event_does_not_leak_into_earlier_close(self):
        history = pd.DataFrame({"ts_code": ["x", "x"],
                                "effective_from": pd.to_datetime(["2020-01-01", "2021-07-30 16:00"], format="mixed"),
                                "l1_code": ["old", "new"]})
        self.assertEqual(industry_asof(history, ["x"], "2021-07-30 15:00").loc["x", "l1_code"], "old")
        self.assertEqual(industry_asof(history, ["x"], "2021-08-02 15:00").loc["x", "l1_code"], "new")

    def test_only_equivalent_alias_observations_collapse(self):
        same = pd.DataFrame({"code": ["x", "x"], "date": ["d", "d"], "pb": [2.0, 2.0]})
        self.assertEqual(len(collapse_equal_alias_rows(same, ["code", "date"], ["pb"])), 1)
        same.loc[1, "pb"] = 3.0
        with self.assertRaises(ValueError):
            collapse_equal_alias_rows(same, ["code", "date"], ["pb"])

    def test_expired_session_is_renewed_once_without_partial_output(self):
        class Response:
            fields = ["code", "tradeStatus"]
            error_msg = "expired"
            def __init__(self, error):
                self.error_code, self.i = error, 0
            def next(self):
                self.i += 1
                return self.i == 1
            def get_row_data(self):
                return ["sz.000001", "0"]
        responses = iter([Response("10001001"), Response("0")])
        logins = []
        bs = SimpleNamespace(query_all_stock=lambda **kw: next(responses),
                             login=lambda: logins.append(True) or SimpleNamespace(error_code="0"))
        got = read_status_snapshot(bs, "2007-02-01")
        self.assertEqual(got.to_dict("records"), [{"code": "sz.000001", "tradeStatus": "0"}])
        self.assertEqual(len(logins), 1)


if __name__ == "__main__":
    unittest.main()
