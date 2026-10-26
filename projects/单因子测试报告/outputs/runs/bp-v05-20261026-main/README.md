# 正式运行结果索引

运行`bp-v05-20261026-main`，方法0.5，三池各228期；研究源码提交与输入记录见[运行清单](run_manifest.json)。读者入口为[中文报告](../../../report/bp_single_factor_report.md)。

| 内容 | 文件 |
| --- | --- |
| 三池回归与Rank IC | [C1.csv](C1.csv) |
| 三池五层与多空绩效 | [C2.csv](C2.csv) |
| 全A年度表现 | [C3.csv](C3.csv) |
| 行业内五层及不足记录 | [C4.csv](C4.csv) |
| 统一信号/入场/退出日期 | [calendar.csv](calendar.csv) |
| U/F/S/Y与覆盖、排除 | [D1_sample_flow.csv](D1_sample_flow.csv) |
| 行业中位数与规模诊断 | [行业截面](industry_median_20260130.csv)、[规模相关](size_correlation.csv) |
| 全A五层月度、毛/净收益、换手 | [月度结果](ALL_A_monthly.csv)、[毛收益](ALL_A_layers_gross.csv)、[净收益](ALL_A_layers_net.csv)、[换手](ALL_A_turnover.csv) |
| 指数端点 | [index_returns.csv](index_returns.csv) |
| 滚动与分段解释 | [D6_rolling_excess.csv](D6_rolling_excess.csv)、[interpretation_segments.csv](interpretation_segments.csv) |
| 十层与市值三域 | [D9层指标](D9_layer_stats.csv)、[低](D10_size1_layer_stats.csv)、[中](D10_size2_layer_stats.csv)、[高](D10_size3_layer_stats.csv)、[域边界](D10_size_domains.csv) |
| 全部图形 | [figures](figures/)，每图PNG/PDF/SVG，另有[来源表](figures/figure_sources.csv) |
| 结果验收 | [acceptance_results.json](acceptance_results.json) |

HS300、ZZ500与全A有相同的月度、分层、换手、只数及已知权重文件。`C4_<行业代码>_*`保存各行业对应结果；`*_issues.csv`保留不可计算原因。综合行业的缺期与NA是预先声明的样本不足，不是被忽略的计算失败。所有证券名单与形成暴露只保留在本地被忽略目录。

收益字段用小数，`ann`为复利年化净收益，`ann_exc`为相对内部毛基准的算术年化超额；`max_dd`与`excess_max_dd`均为非正值。`holding_month`按建仓月份归属，实际退出日期见日历。C4窗为54期，其余主绩效为228期；2026-01-30仅诊断。
