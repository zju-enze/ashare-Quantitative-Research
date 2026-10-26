# P1修复证据（2026-10-26，尚非正式因子结果）

原始offline库保持只读；证券级来源和修复明细在`.local/data_repairs/`。本目录只保存汇总。当前仍不满足P1全部门槛，不得据此宣称BP有效或开始解释组合绩效。

- `local_sources_audit.json`、`local_industry_coverage.csv`：复用本地申万历史事件表，保留旧分类；251条明确身份映射；16个月沪深300候选补充。
- `hs300_reconstruction.json`：另外两个月（2023-01/02）依据2022-12-30原始名单和官方公告链重建，共核对86条公告、6份可能相关的调整附件。3月相同名单仅作佐证。
- `endpoint_status_acquisition.json`：145个日期、5,238个精确待查键的市场状态查询完成。来源的非交易标记不自动等于停牌，仍须结合退市日。
- `endpoint_reclassification.json`、`endpoint_reclassification_by_month.csv`：原P1的8,422个问题股票—期重分类；不是补全行业/执行资格后的新全体样本。7,434个原缺价键中，7,358个有停牌证据，76个涉及退出上市。入场不合格1,288个股票—期；剩余退出估值仍待落实。
- `suspension_valuation_audit.json`：7,358个停牌端点都有最后成交价及同一原始证券代码的复权序列；7,192个区间因子恒定，166个存在变化。恒定因子只是供应商未记录调整事件的支持证据，不等于独立公告审计。
- `suspension_quote_acquisition.json`、`suspension_action_acquisition.json`、`suspension_action_reconciliation.json`：166个例外端点已取得参考行情及分红/复权事件资料，最后成交价全部与原库一致；153个端点有区间内已公告的分配事件，13个没有匹配分配记录。尚未据此插入估值或计算收益。

## 已查明的具体边界

2009-12-31沪深300的298只名单有事件依据：两只合并退市股票于2009-12-29退出，替补于2010-01-04生效。保留298只，不提前补入替补。依据是[中证指数签署的补充公告转载](https://fund.sohu.com/20091222/n269111352.shtml)及[上交所定期调整公告](https://big5.sse.com.cn/site/cht/www.sse.com.cn/aboutus/mediacenter/hotandd/c/c_20150912_3988345.shtml)。BaoStock请求12月31日却返回12月28日300只旧名单，已明确拒绝用它覆盖该快照。私有复核记录为`hs300_200912_review.json`。

部分早期BaoStock停牌日参考价在已实施现金/送转分配后仍沿用旧价，不能直接乘退出日复权因子使用。事件对照已识别特别派息、配股和股改追送等差异；精确处理尚未完成。普通分红理论参考价比较仅作诊断，不将小误差自动判成失败，也不把大差异自动补零。

退市整理股的事件退出政策仍待用户确认；当前没有额外排除这类信号、倒推卖出时点或假定终值。

## 重现入口

使用已核实的课程Python环境。按顺序运行，参数传入本地已有目录；不下载整库。前三步所需官方改码表、公告附件和人工阅读记录也是输入，保留在`.local/data_repairs/`，不包含在公共仓库中。

```powershell
python scripts/prepare_local_repairs.py --course-root COURSE_ROOT --industry-source EXISTING_INDUSTRY_SOURCE
python scripts/fetch_endpoint_status.py --course-root COURSE_ROOT --baostock-client EXISTING_CLIENT
python scripts/reconstruct_index_gaps.py --course-root COURSE_ROOT
python scripts/classify_endpoint_repairs.py --course-root COURSE_ROOT
python scripts/audit_suspension_values.py --course-root COURSE_ROOT
python scripts/fetch_suspension_quotes.py --baostock-client EXISTING_CLIENT
python scripts/fetch_suspension_actions.py --baostock-client EXISTING_CLIENT
python scripts/reconcile_suspension_actions.py
python -m unittest discover -s tests -p test_endpoint_repairs.py -v
```

脚本分别保存原始响应、候选证据和诊断结果；这些不是P2的回测适配实现。全部历史样本仍须在修复政策落实后统一重跑P1。
