# Codex 第一阶段 v2 稳健重做执行提示词

请在当前连接的 zju-enze 量化研究仓库 `projects/ashare-cointegration/` 中，实现并执行 A 股同业协整研究第一阶段的**稳健重做 v2.0**。

v1.2 已完成，产出 110 对名义发现，但预定校准暴露了主方法在若干真实压力机制下的名义错误控制失效（N1 高共同趋势占比的伪协整、N5/N6/N7 非平稳波动与组合压力；S2 固定 L2-Holm FWER 达 52%–58%）。v2 的唯一目的是：在**同一冻结数据**上，用**事前固定的、对非平稳波动与伪协整稳健的方法**，在**全市场 FWER=5%** 下给出一个经校准验收的可靠发现清单。

## 0. 先读、后动

以下三份为共同依据，动手前通读：

- [EXPERIMENT_PLAN_V2.md](EXPERIMENT_PLAN_V2.md)：v2 预注册设计与声明范围。
- [REVIEW_AND_IMPLEMENTATION_V2.md](REVIEW_AND_IMPLEMENTATION_V2.md)：算法、数值口径、确定性、算力预算与修订机制、测试与验收。
- [AGENTS.md](../../AGENTS.md)：工程维护与暂停/恢复纪律。

同时核对 v1 现状：[README.md](../v1_handoffs_20261019/README_STAGE1_V1.md)、[RESEARCH_STATUS.json](../../RESEARCH_STATUS.json)、[results/CALIBRATION_REPORT.md](../../results/CALIBRATION_REPORT.md)、[src/engine.py](../../src/engine.py)、[src/simulation.py](../../src/simulation.py)。遇常规工程问题自主修复并继续；只在确实缺少关键输入、算力授权或存在无法自行解决的统计定义冲突时，报告具体阻塞。

## 1. 不可逾越的纪律（最重要）

1. **复用 v1 冻结数据，不重新取数。** 复用 U、H、方向、家族规模、SW2021 归属、研究价格 `P*`。开始时记录来源路径与哈希写入 `experiment_protocol_v2.json`；哈希与 v1 完成记录不符则停止并报告。
2. **v1 只增不改。** 不改 v1 任何文件、代码行为、检查点与结果。v2 以新增模块与独立输出路径实现（`src/engine_v2.py`、`src/simulation_v2.py`、`run_stage1_v2.py`、`run_simulation_v2.py`、`results_v2/`、`.local/production_v2/`、`*_v2.json`、`*_V2.md`）。v1 全部测试必须继续通过。
3. **方法在运行前全部冻结，冻结后不得为改变发现数调方法。** 因子定义、剥离规格、双向 EG、bootstrap 构造与参数、Romano–Wolf 程序、校准机制/家族/种子/重复数、验收门槛——全部先写入 `experiment_protocol_v2.json` 并冻结，再运行。
4. **不得自动恢复远端、不得自动启动长批。** 先用 S0 实测给出算力预算，向用户报告并取得授权后方可使用远端（qzwx2026）或长时本机批处理。
5. **不读取 2026 价格/表现，不按其回填 2025 资格。** 与 v1 相同。

## 2. 要实现的方法（详见 PLAN_V2 §4–§6 与 REVIEW_V2 §1–§4）

1. **因子剥离**：对每股做留一市场因子 \(M^{(-i)}\) 与留一 L2 行业因子 \(S^{(-i)}\) 的一阶 OLS，取残差 \(r_i\) 为特异性价格分量。小行业（\(|L2|<K_{\min}=5\)）回退为仅市场因子。沿用 v1 数值口径与审计字段。
2. **双向 EG 统计量**：在 \((r_a,r_b)\) 上按 v1 `eg_audit` 同一路径算两方向 \(\tau_{AB},\tau_{BA}\)，配对统计量 \(\tau_{\text{pair}}=\max(\tau_{AB},\tau_{BA})\)（要求两方向都给证据）。v2 不以渐近 MacKinnon p 值判定。
3. **公共面板 sieve wild bootstrap**：直接对已剥离残差做（条件于一阶载荷）；逐股对差分 AR(AIC, ≤8) 白化，公共时点 Rademacher 乘子 \(w_t\) 跨股共用相乘，重上色、累加，得独立随机趋势的自助面板（施加全市场无协整零假设），重算全部配对 \(\tau^*\)。
4. **Romano–Wolf 步降**：在全部有效候选上，用自助极值（最小）统计量分布做左侧 5% 分位步降，强控制全市场 FWER=5%。市场 B=999。

对照视角（逐对 bootstrap p ＋三域 Holm/BY）与可靠性诊断（分半 β 稳定性、半衰期）只报告，不作门槛。预检在剥离残差上执行、家族预检前冻结、不缩小家族——与 v1 一致。

## 3. 执行顺序

1. 建立 v2 独立环境说明与 `experiment_protocol_v2.json`（含全部冻结参数、种子规则、输入哈希、\(K_{\min}\)、\(p_{\max}\)、\(B\) 初值），冻结时间以实际 commit 为准，不伪装更早预注册。
2. 实现 v2 模块并通过 [REVIEW_AND_IMPLEMENTATION_V2.md](REVIEW_AND_IMPLEMENTATION_V2.md) §6 的全部测试 ＋ v1 全部测试。
3. **先跑 S0 冒烟**（全 16 机制各 5 次），核对流水线正确并**实测嵌套 bootstrap 吞吐**；据此估算 S1/S2/S3 真实耗时与资源。若冻结 \(B\) 初值不可行，在运行主校准之前、按**算力（非结果）**修订一次 \((B_{\text{inner}},B_{\text{outer}})\)，记入 ENGINEERING_CHANGES.md 与协议并重算 MCSE。向用户报告预算、请求远端/长批授权。
4. 经授权后运行 S1（必跑全机制）→ S2 → S3（规模压力，含 N7）。按机制/阶段给出全市场 FWER、Wilson 区间、门槛判定、功效与 MCSE。断点可恢复；时间不足则记录未完成阶段，**不改 \(B\)/重复数凑完整**。
5. 跑 v2 市场运行（单次 B=999 自助 ＋ Romano–Wolf）→ v2 主发现清单、完整逐对证据、对照视角、与 v1 110 对的交集/差集/Jaccard、可靠性诊断。
6. 生成 v2 统计报告与校准报告（`results_v2/STAGE1_REPORT_V2.md`、`results_v2/simulation/acceptance_v2.json`）。

市场主表与完整校准互不阻塞：校准未完时，主清单标"v2 名义稳健发现，预定 v2 校准尚未完成"，保留检查点，不记为通过。

## 4. 交付与验收

交付至少包括：v2 有效协议/环境/哈希；逐股剥离审计（因子成员计数、载荷、R²、数值终态、`defactor_mode`）；完整逐对 v2 结果（双向统计量、bootstrap p、Romano–Wolf 轮次/临界值、预检/数值/尾部状态）；v2 主发现清单（代码、行业、剥离载荷、统计量、调整结果、家族、证据状态）；对照视角与 v1 对照表；可靠性诊断；S0/S1/S2/S3 实际状态与门槛判定；校准图；统计报告。

验收门槛（PLAN_V2 §9.4）：全部全零机制 N0–N7、全部已运行阶段，v2 主程序全市场 FWER 的 95% Wilson 下限 ≤ 0.05 即通过。任一机制下限 > 0.05 即失败：如实披露、保留诊断与全部发现、**不换主方法**，进一步稳健化作为 v2.1 重新预注册。通过不等于无条件真实市场误差控制；**发现数远少于 110 是预期代价，不得据此回调方法**。

## 5. 收尾

- 维护 [ENGINEERING_CHANGES.md](../../ENGINEERING_CHANGES.md)（新编号追加 v2 决策、动作、验证、恢复条件）、[RESEARCH_STATUS.json](../../RESEARCH_STATUS.json)（新增 v2 区块，不改 v1 区块）、[README.md](../v1_handoffs_20261019/README_STAGE1_V1.md)（新增 v2 指引行）。保持第二、三阶段 `planned_deferred`。
- 原始授权数据、大规模逐证券/逐自助中间表、缓存留本地受忽略路径；仓库只发布代码、文档与授权范围内的汇总结果。用独立工作分支提交，保留清晰变更记录，不强推或自动合并。
- 最终回复说明：实际实现与执行了什么、哪些完整/部分/未执行、v2 候选与发现数量（只有实际计算后填写）、门槛判定、与 v1 的对照、验证证据、文件位置/工作分支、具体未解问题与继续所需最小输入（尤其远端/算力授权）。
