# 历史材料归档

当前结论以[共同DGP正式结果](../results_final/README.md)、[V1最终报告](../results_final/V1_FINAL_REPORT.md)和[V2最终报告](../results_final/V2_FINAL_REPORT.md)为准。现行设计依据是[V1/V2联合修订计划](../EXPERIMENT_REVISION_PLAN_V1_V2.md)，V3继续暂停。归档中的执行提示词不构成新的运行授权。

## 原设计实验：独立归档，不纳入正式报告

正式报告仅采用共同DGP、对数价格、固定1阶主比较的设计。以下材料完整保留历史结论，作为已归档实验的复现工作副本；其原位路径不表示仍属于正式报告。

|历史材料|计划与结果入口|
|---|---|
|原V1价格水平、逐股预检与L2校正设计|[原计划](../EXPERIMENT_PLAN.md)、[原市场报告](../results/STAGE1_REPORT.md)、[原校准报告](../results/CALIBRATION_REPORT.md)、[原完成记录](../results/STAGE1_COMPLETION.json)|
|原V2价格水平、7阶与全局校正设计|[原计划](../EXPERIMENT_PLAN_V2.md)、[原市场报告](../results_v2/STAGE1_REPORT_V2.md)、[原校准报告](../results_v2/CALIBRATION_REPORT_V2.md)、[原完成记录](../results_v2/STAGE1_COMPLETION_V2.json)|
|DH开发实验|[开发记录](../DH_DEVELOPMENT.md)、[开发结果](../results_dh_dev/20261019T200814/DH_DEVELOPMENT_REPORT.md)|
|已被替代的混合版综合报告|[4文件原文ZIP](combined_reports_superseded_20261022.zip)，对应Git提交23aae47中的results_final/|

原设计的完整公开实验输出已在下方159文件日期归档中保存。混合版报告的4文件ZIP在重新改写前创建，逐文件内容比较一致；不再作为当前报告使用。

## 2026-10-22：旧结果与报告完整快照

[日期归档说明](v1_v2_before_final_20261022/README.md) · [159文件ZIP](v1_v2_before_final_20261022/legacy_public_results.zip) · [逐文件目录](v1_v2_before_final_20261022/inventory.json)。

归档覆盖V1全部52份输出、V2全部86份输出、DH开发9份输出及12份整理前背景文档。逐文件内容比较一致；原统计路径保留供复现，旧报告原位加历史版本导航。参数诊断与本次补充证据仍在results_review/、results_revision/。


2026-10-19 文档整理只归档本协整项目的过时材料，不处理仓库其他研究。历史正文和结论保留；因移动产生的文档链接重新定位，正文中的命令和路径仍按原项目根目录理解。

## 已被替代的 V2 defactor / bootstrap / RW 草案

归档原因：方法路线被 DH 两方程联合检验及 GLOBAL-Holm 替代；保留原设计、独立审稿及选择历史，避免其再次被误作当前执行协议。

|原项目根文件名|归档位置|
|---|---|
|EXPERIMENT_PLAN_V2.md|[旧实验计划](v2_defactor_rw_20261019/EXPERIMENT_PLAN_V2.md)|
|REVIEW_AND_IMPLEMENTATION_V2.md|[旧实施澄清](v2_defactor_rw_20261019/REVIEW_AND_IMPLEMENTATION_V2.md)|
|CODEX_STAGE1_V2_PROMPT.md|[旧执行提示词](v2_defactor_rw_20261019/CODEX_STAGE1_V2_PROMPT.md)|
|CODEX_V2_DESIGN_AUDIT_PROMPT.md|[已完成的审稿提示词](v2_defactor_rw_20261019/CODEX_V2_DESIGN_AUDIT_PROMPT.md)|
|V2_DESIGN_AUDIT.md|[对应的独立审稿](v2_defactor_rw_20261019/V2_DESIGN_AUDIT.md)|

## 已完成的 V1 交接与早期日志

|原项目根文件名|归档位置|
|---|---|
|CODEX_STAGE1_PROMPT.md|[V1 原执行交接](v1_handoffs_20261019/CODEX_STAGE1_PROMPT.md)|
|IMPLEMENTATION_LOG.md|[V1 早期实施与纠错日志](v1_handoffs_20261019/IMPLEMENTATION_LOG.md)|
|README.md|[文档整理前的 V1 项目入口快照](v1_handoffs_20261019/README_STAGE1_V1.md)|

其中前两项为移动归档，README 为更新当前入口前保存的快照。V1 [原计划](../EXPERIMENT_PLAN.md)、[实施澄清](../REVIEW_AND_IMPLEMENTATION.md)、[数据契约](../DATA_CONTRACT.md)、[最终统计报告](../results/STAGE1_REPORT.md)、[最终校准报告](../results/CALIBRATION_REPORT.md)原位保留。

V1 的代码、机器协议、原始数据、全部检查点及结果不在本次归档移动范围。旧实施日志中的“v2 数据运行”指存托凭证纠错后的输入版本，不是当前 DH 方法版本。

## 此前已归档的来源材料

- [历史机器协议](experiment_protocol.json)
- stage1_rule_checks.py
- [历史规则检查记录](synthetic_stage1_checks.json)

这些是来源记录，不自动等于当前代码或方法已通过验证。
