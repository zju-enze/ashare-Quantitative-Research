"""Apply the approved final-trading-day cash exit only where prior issuer notices prove the date."""

import json
from pathlib import Path
import re

import numpy as np
import pandas as pd


def announced_last_dates(text):
    compact = re.sub(r"\s+", "", text)
    pattern = r"(?:预计)?最后(?:一个)?交易日(?:期)?[^0-9]{0,8}([12][0-9]{3})年([0-9]{1,2})月([0-9]{1,2})日"
    return sorted({f"{int(y):04d}{int(m):02d}{int(d):02d}" for y, m, d in re.findall(pattern, compact)})


def main():
    root = Path(__file__).resolve().parents[1]
    private = root / ".local/data_repairs"
    queue = pd.read_csv(private / "terminal_event_candidates.csv", dtype=str)
    queue = queue[queue.signal_names.str.contains("退", na=False)].set_index("ts_code")
    docs = pd.read_csv(private / "terminal_documents.csv", dtype=str).set_index("ts_code")
    rows = []
    for code, key in queue.iterrows():
        doc = docs.loc[code]
        text = (private / doc.text_file).read_text(encoding="utf-8")
        dates = announced_last_dates(text)
        assert dates == [key.last_trade_date], f"Announcement and observed final trading date differ: {code} {dates}"
        assert doc.publication_date < key.last_trade_date, "A same-day date without publication time is not prior evidence"
        assert code[:6] in re.sub(r"\s+", "", text)
        assert key.entry_date <= key.last_trade_date < key.exit_date
        close, factor = float(key.last_close), float(key.last_adj_factor)
        assert np.isfinite(close * factor) and close > 0 and factor > 0
        rows.append(dict(ts_code=code, trade_date=key.exit_date, event_exit_date=key.last_trade_date,
                         exit_close=close, factor_used=factor, adjusted_value=close * factor,
                         valuation_kind="announced_final_day_exit_then_cash", publication_date=doc.publication_date,
                         source_url=doc.url, text_file=doc.text_file, cash_interest_rate=0.0))
    result = pd.DataFrame(rows)
    assert len(result) == len(queue) and not result.duplicated(["ts_code", "trade_date"]).any()
    result.to_parquet(private / "delisting_valuations.parquet", index=False)
    summary = dict(checked_at=pd.Timestamp.now(tz="Asia/Shanghai").isoformat(), resolved_stock_periods=len(result),
                   all_notices_precede_event_exit=True, all_announced_final_dates_match_real_quotes=True,
                   policy="RESEARCH_SPEC v0.4 section15, approved by user; RF0 cash to original planned endpoint",
                   limitations="Academic final-close execution and textbook cost approximation; no real-world fill guarantee. Signal memberships and holding calendar unchanged.")
    (root / "outputs/repairs/delisting_valuations.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
