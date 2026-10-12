# Local input data

Raw data are licensed Tushare-format exports stored locally. They are not included in this repository, and no downloader, credentials, or API key are needed by the analysis. Obtain your own authorized exports. The repository publishes aggregate research tables and figures rather than raw vendor records.

Set `ASHARE_DATA_DIR` for interactive notebook work, or pass the directory to `run_research.py --data-dir PATH`. The default study is 2005–2024; files can include later data, which are filtered out of the study.

| Parquet file | Required columns |
|---|---|
| `daily.parquet` | `ts_code`, `trade_date`, `close`, `vol`, `amount` |
| `adj_factor.parquet` | `ts_code`, `trade_date`, `adj_factor` |
| `daily_basic.parquet` | `ts_code`, `trade_date`, `pe_ttm`, `pb`, `total_mv`, `turnover_rate` |
| `stock_basic.parquet` | `ts_code`, `list_date`, `list_status`, `industry` |
| `namechange.parquet` | `ts_code`, `name`, `start_date`, `end_date`, `ann_date` |
| `income.parquet` | `ts_code`, `ann_date`, `f_ann_date`, `end_date`, `report_type`, `revenue`, `oper_cost`, `sell_exp`, `admin_exp` |
| `balancesheet.parquet` | `ts_code`, `ann_date`, `f_ann_date`, `end_date`, `report_type`, `total_assets`, `total_hldr_eqy_exc_min_int` |
| `shibor.parquet` | `date`, `1y` |

Dates use `YYYYMMDD` strings. `total_mv` is in ten-thousand CNY, `amount` is in thousand CNY, SHIBOR is an annual percentage, and stock returns are decimal fractions. Security/date keys in prices, adjustment factors, and monthly characteristics are expected to be unique. Annual reports can contain revisions; availability and conflict rules are documented in [methodology.md](methodology.md).

Execution writes stock-level intermediates under ignored `.local/` and aggregate outputs under `results/`. Raw vendor data and security-level intermediate panels are not published.
