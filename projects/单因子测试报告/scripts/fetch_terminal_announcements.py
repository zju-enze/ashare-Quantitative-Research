"""Fetch bounded official announcement metadata for actual held terminal-event cases."""

import json
import math
from pathlib import Path

import pandas as pd
import requests


def main():
    root = Path(__file__).resolve().parents[1]
    private = root / ".local/data_repairs"
    source = private / "terminal_sources"
    cache = source / "queries"
    cache.mkdir(exist_ok=True)
    directory = pd.DataFrame(json.loads((source / "stock_directory.json").read_text(encoding="utf-8"))["stockList"])
    directory = directory.set_index("code")
    queue = pd.read_csv(private / "terminal_event_candidates.csv", dtype=str)
    assert queue.ts_code.is_unique
    session = requests.Session()
    receipts, records = [], []
    for number, key in enumerate(queue.itertuples(index=False), 1):
        code = key.ts_code[:6]
        last_trade = pd.Timestamp(key.last_trade_date)
        end = last_trade if "退" in key.signal_names else pd.Timestamp(key.exit_date)
        start = last_trade - pd.Timedelta(days=45)
        payload = dict(pageNum=1, pageSize=30, column="szse", tabName="fulltext", plate="",
                       stock=code + "," + directory.loc[code, "orgId"], searchkey="", secid="", category="",
                       trade="", seDate=f"{start:%Y-%m-%d}~{end:%Y-%m-%d}", sortName="", sortType="", isHLtitle="false")
        page, total, rows = 1, None, []
        paths = []
        while total is None or page <= math.ceil(total / 30):
            path = cache / f"{key.ts_code}_{start:%Y%m%d}_{end:%Y%m%d}_{page}.json"
            if path.exists():
                result = json.loads(path.read_text(encoding="utf-8"))
            else:
                payload["pageNum"] = page
                response = session.post("https://www.cninfo.com.cn/new/hisAnnouncement/query", data=payload, timeout=25)
                response.raise_for_status()
                result = response.json()
                assert "totalAnnouncement" in result
                path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            total = int(result["totalAnnouncement"])
            rows.extend(result.get("announcements") or [])
            paths.append(str(path.relative_to(private)))
            page += 1
        assert len(rows) == total, f"Incomplete announcement pagination for {key.ts_code}: {len(rows)}/{total}"
        for item in rows:
            publication = pd.Timestamp(item["announcementTime"], unit="ms", tz="UTC").tz_convert("Asia/Shanghai")
            records.append(dict(ts_code=key.ts_code, last_trade_date=key.last_trade_date,
                                announcement_id=item["announcementId"], title=item["announcementTitle"],
                                published_at=publication.isoformat(), publication_date=publication.strftime("%Y%m%d"),
                                source_code=item["secCode"], adjunct_url=item.get("adjunctUrl"),
                                pdf_url="https://static.cninfo.com.cn/" + item["adjunctUrl"] if item.get("adjunctUrl") else ""))
        receipts.append(dict(ts_code=key.ts_code, start_date=start.strftime("%Y%m%d"), end_date=end.strftime("%Y%m%d"),
                             reported_total=total, retrieved_rows=len(rows), source_files=paths))
        (private / "terminal_announcement_queries.json").write_text(json.dumps(receipts, ensure_ascii=False, indent=2), encoding="utf-8")
        if number == 1 or number % 10 == 0 or number == len(queue):
            print(f"Terminal announcement metadata {number}/{len(queue)}: {key.ts_code}, {total} records", flush=True)
    frame = pd.DataFrame(records)
    frame.to_csv(private / "terminal_announcement_index.csv", index=False, encoding="utf-8-sig")
    summary = dict(completed=True, terminal_securities=len(queue), announcements=len(frame),
                   securities_with_no_announcements=sum(r["reported_total"] == 0 for r in receipts),
                   source="CNINFO official hisAnnouncement/query, public stock directory IDs",
                   scope="From 45 days before last trade: ordinary delistings through last trade, mergers through planned valuation date; metadata only")
    (root / "outputs/repairs/terminal_announcement_acquisition.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
