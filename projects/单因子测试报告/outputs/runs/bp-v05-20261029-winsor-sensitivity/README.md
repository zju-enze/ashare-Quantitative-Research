# BP去极值方法敏感性实验

运行标识：`bp-v05-20261029-winsor-sensitivity`。状态：计算与核验完成。方法为原0.5加本次单一去极值变化，不替换默认MAD5。

项目已于2026-10-30结项，当前报告为[最终17页PDF](../../../latex-report/main.pdf)。下文的独立补充PDF、390字草稿与备份描述是2026-10-29的运行记录；最终稿以当前LaTeX源文件为准。仅重编译最终稿时运行`latex-report/build.ps1`，不要重跑会覆盖手工修订的补充文字生成器。表S1中的差值按未舍入结果计算。

全部A股，2007-01至2025-12信号共228期，持有期归属2007-02至2026-01；实际起止收盘日2007-02-01至2026-02-02。相同686,280个S股票期及原有收益映射。2026-01-30仅属原截面诊断，未加入绩效。

## 核心结果

|方案|Rank IC均值|ICIR|回归因子收益（%/月）|多空CAGR（%）|Q5算术年化超额（百分点）|
|---|---:|---:|---:|---:|---:|
|MAD5|0.0566|0.550|0.40|13.00|5.31|
|MAD3|0.0565|0.522|0.40|12.34|4.80|
|1%/99%分位数缩尾|0.0563|0.563|0.38|13.32|5.55|

ICIR未年化；多空为双腿各扣教材成本后的CAGR。Q5超额相对原内部等权毛收益基准，使用12倍月度超额均值。五层CAGR在三方案均严格递增。收益幅度变化真实存在，未实施方案差异统计检验，不按结果更改默认参数。

## 入口与文件

- `run_manifest.json`：原运行、时间、环境、输入大小/mtime、方法和方案。`implementation.patch`记录本轮计算/生成代码与第5节引用的实际差异，不用哈希。
- `calendar.csv`：直接采用原运行保存的228期。当前预检日历的mtime不同，但内容逐项一致，未改原文件。
- `summary.csv`、`difference_vs_mad5.csv`：全部未舍入汇总及相对MAD5的差值。
- 每个`mad-k5/`、`mad-k3/`、`quantile-p01-p99-linear/`目录分别保存`config.json`、`winsor_diagnostics.csv`、`monthly.csv`、`layers_gross.csv`、`layers_net.csv`、`turnover.csv`、`costs.csv`、`counts.csv`、`known_weight.csv`、`layer_stats.csv`、`summary.csv`、异常记录及月度差值。
- `winsor_diagnostics.csv`的上下界从各月原始BP计算。`n_changed`为原值实际改变的只数，恰等于边界者不计；`changed_fraction`分母为当期固定S人数。
- `monthly.csv`额外含毛多空、双腿成本及Q5超额；`ls_*_arithmetic_ann`为可加总的12倍月均值，不能将其当作CAGR差分解。
- 证券级`formations.parquet`（原PB、控制变量、BP、缩尾、Z值、OLS残差与确定性排名）、`holdings.parquet`（层号、等权）保存在`.local/runs/<本运行>/<方案>/`。统一`responses.parquet`保存三日期、原端点估值与收益，只在冻结持仓后连接。
- `mad5_baseline_check.json`：14类完整基线核对，读取后的最大绝对差均为0；浮点容差rtol=1e-7、atol=1e-13，日期/键/计数/持仓精确比较。MAD5通过后才执行其他方案。
- `numerical_audit.json`：全部3方案逐期缩尾、排名、分层收益、换手、成本及IC核对；2007-01、2020-01、2025-12分别用statsmodels独立核对OLS/WLS。无异常或删月。
- `holding_change_vs_mad5.csv`：每期层号变化；MAD3共57,326个股票期，分位数方案共22,434个股票期改变层号。
- `report_values.json`与`supplement_paragraph.txt`：表S1显示值、390字解读及数字来源。新版PDF为`latex-report/bp_single_factor_report_winsor_sensitivity_20261029.pdf`。
- `delivery_audit.json`：正文/原图表/原主结果直接字节核对及编译、版面验收。本轮前备份为`latex-report/backup/pre-winsor-20261029/`。

## 重现

在项目根目录，用现有课程Python环境执行；新run-id不得覆盖已有运行。

```powershell
python -m unittest discover -s tests -p test_bp_core.py -v
python scripts/run_winsor_sensitivity.py --run-id <新的运行标识>
python scripts/validate_winsor_sensitivity.py --run-id <同一运行标识>
python latex-report/scripts/build_winsor_supplement.py --run-id <同一运行标识>
./latex-report/build-winsor-sensitivity.ps1
```

MAD仍使用未乘1.4826的绝对离差中位数；分位数方案直接从原始BP做1%/99%线性分位点缩尾，不先经过MAD5。三个方案均在全A每期S上全局处理；各自重新估计标准化和中性化，WLS/IC/分层评价复用原引擎与成本函数。负残差保留。

本次只完成该敏感性问题，没有IC衰减、中性化方案对照、样本外或其他股票池实验；不扩展严格PIT或实盘可交易性的原有主张。

## 本次文件范围

相对本轮开始时的工作区，仅修改以下既有文件：

- `src/bp_core.py`：缩尾方案参数与使用对应缩尾BP的OLS代数。
- `tests/test_bp_core.py`：追加三种方案及独立OLS的一个针对性检查。
- `latex-report/sections/05_annual.tex`：末尾追加一处带标记的input引用。
- `docs/PROJECT_STATUS.md`、`docs/ACCEPTANCE_CHECKLIST.md`、`latex-report/README.md`：只追加本轮记录。

新增入口为`scripts/run_winsor_sensitivity.py`、`scripts/validate_winsor_sensitivity.py`、`latex-report/scripts/build_winsor_supplement.py`、`latex-report/build-winsor-sensitivity.ps1`。

新增报告产物为`latex-report/tables/S1.tex`、`latex-report/sections/05_winsor_sensitivity.tex`、`latex-report/source-data/winsor_sensitivity_summary.csv`、`latex-report/reviews/winsor-sensitivity-20261029.md`以及带独立名称的新版PDF。本目录与对应`.local/runs/`保存本次实验输出；`latex-report/backup/pre-winsor-20261029/`和`.local/winsor-baseline-20261029/`保存本轮前的可核对基线。编译日志和渲染页在`latex-report/build/winsor-sensitivity-20261029/`。

原研究规范、执行计划、数据契约、实现审阅和写作规范均逐字节未变。父仓库及旧报告此前已有的其他未提交改动不属于本次变更，也未被本任务覆盖。
