# P1修复证据（2026-10-26，尚非正式因子结果）

原始offline库保持只读；证券级来源和修复明细在`.local/data_repairs/`。本目录保存修复过程汇总；整体P1已通过，正式冻结与当前完整样本以[修复后预检](../preflight_repaired/preflight_findings.md)为准。不得据此宣称BP有效。

- `local_sources_audit.json`、`local_industry_coverage.csv`：复用本地申万历史事件表，保留旧分类；252条明确身份映射；16个月沪深300候选补充。
- `hs300_reconstruction.json`：另外两个月（2023-01/02）依据2022-12-30原始名单和官方公告链重建，共核对86条公告、6份可能相关的调整附件。3月相同名单仅作佐证。
- `endpoint_status_acquisition.json`：已覆盖173个请求日期，含完整样本新增的52个入场状态缺口。来源的非交易标记不自动等于停牌，仍须结合退市日；完整原始成交记录与二次来源冲突时保留原始交易证据。
- `endpoint_reclassification.json`、`endpoint_reclassification_by_month.csv`：原P1的8,422个问题股票—期重分类；不是补全行业/执行资格后的新全体样本。7,434个原缺价键中，7,358个有停牌证据，76个涉及退出上市。入场不合格1,288个股票—期；剩余退出估值仍待落实。
- `suspension_valuation_audit.json`：完整S的7,936个持仓退出停牌端点中，7,761个区间因子恒定、175个变化；不再把入场不合格的点混入持仓退出统计。
- `suspension_quote_acquisition.json`、`suspension_action_reconciliation.json`：175个变化端点的参考行情和事件核对，最后成交价均与原库一致；161个有普通分配记录，另有11个精度变化和3个专项公司行为。
- `suspension_valuations.json`、`delisting_valuations.json`、`merger_valuations.json`：7,936个停牌、58个公告末日退出、17个换股估值均已生成并接回完整预检；这些是估值及事件处理，不是因子绩效。
- `terminal_announcement_acquisition.json`、`terminal_document_acquisition.json`：75家公司限定日期区间内的公告索引与选定正文；普通退市公告须在末日前，合并对价资料不得晚于原计划评价日。公告获取完成本身不等于对价核对通过。

## 已查明的具体边界

2009-12-31沪深300的298只名单有事件依据：两只合并退市股票于2009-12-29退出，替补于2010-01-04生效。保留298只，不提前补入替补。依据是[中证指数签署的补充公告转载](https://fund.sohu.com/20091222/n269111352.shtml)及[上交所定期调整公告](https://big5.sse.com.cn/site/cht/www.sse.com.cn/aboutus/mediacenter/hotandd/c/c_20150912_3988345.shtml)。BaoStock请求12月31日却返回12月28日300只旧名单，已明确拒绝用它覆盖该快照。私有复核记录为`hs300_200912_review.json`。

部分早期BaoStock停牌日参考价在已实施现金/送转分配后仍沿用旧价，不能直接乘退出日复权因子使用。特别派息、配股和股改追送等差异已落实到事件估值；完整规则见RESEARCH_SPEC第15.2节。

退市整理股的事件退出政策和两项未上市换股权利估值延续已由用户确认，见方法v0.5。没有额外排除这类信号、倒推卖出时点或延长原持有期。

## 重现入口

使用已核实的课程Python环境；PDF文本提取使用本机已有`pdftotext`，个别复杂PDF的指定页使用桌面提供的Python/pdfplumber。参数传入已有目录，不下载整库。官方改码表、公告附件、已复核的特别公司行为/换股对价表、选定公告清单和原始库均为本地输入，保留在`.local/`；公共仓库不包含这些证券级资料。

```powershell
python scripts/prepare_local_repairs.py --course-root COURSE_ROOT --industry-source EXISTING_INDUSTRY_SOURCE
python scripts/fetch_endpoint_status.py --course-root COURSE_ROOT --baostock-client EXISTING_CLIENT
python scripts/reconstruct_index_gaps.py --course-root COURSE_ROOT
python scripts/classify_endpoint_repairs.py --course-root COURSE_ROOT
python scripts/preflight_repaired.py --course-root COURSE_ROOT
python scripts/fetch_endpoint_status.py --course-root COURSE_ROOT --baostock-client EXISTING_CLIENT
python scripts/fetch_signal_risk_status.py --baostock-client EXISTING_CLIENT
python scripts/preflight_repaired.py --course-root COURSE_ROOT
python scripts/audit_suspension_values.py --course-root COURSE_ROOT
python scripts/fetch_suspension_quotes.py --baostock-client EXISTING_CLIENT
python scripts/fetch_suspension_actions.py --baostock-client EXISTING_CLIENT
python scripts/reconcile_suspension_actions.py
python scripts/build_suspension_valuations.py
python scripts/fetch_terminal_announcements.py
python scripts/fetch_terminal_documents.py
python scripts/build_delisting_valuations.py
python scripts/build_merger_valuations.py --course-root COURSE_ROOT
python scripts/preflight_repaired.py --course-root COURSE_ROOT
python -m unittest discover -s tests -p test_endpoint_repairs.py -v
```

脚本保存原始响应、候选证据和估值结果；原始端点不足始终保存在`raw_endpoint_issues.csv`，修复后尚未解决的点单独保存，避免下次重现时丢失修复对象。P1已在政策落实后整体重跑；这些数据脚本不是P2的因子检验实现。
