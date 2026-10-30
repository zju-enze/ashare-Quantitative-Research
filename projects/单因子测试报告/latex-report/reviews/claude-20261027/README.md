# 审阅目录说明（claude-20261027）

本目录是对作者手工修订后的中文课程报告《BP单因子测试报告》所做的独立审阅。审阅框架以 nature-reviewer 为主，辅以 nature-statistics、nature-figure 和 nature-polishing。本目录是新建的，没有覆盖 `reviews/` 下的既有文件，也没有改动手稿、表、图、代码、数据或 PDF。全部内容未提交、未推送。

## 阅读顺序

1. `synthesis.md`：综合结论。包括实际审阅的文件与证据范围、对照课程优秀线的逐项评估、各审阅人意见摘要、审计摘要、按影响排序的最小修改建议，以及未核实事实与残余风险。
2. `reviewer_1.md`、`reviewer_2.md`、`reviewer_3.md`：三份独立审阅的冻结原文。文件已设为只读，冻结后未作任何修改。
3. `audit.md`：报告冻结后，由组织者另行完成的数值与内部一致性审计。
4. `supporting/`：审阅包说明、哈希清单、报告提取与审计脚本及其输出。

## 审阅对象与版本核实

- 当前手稿为 `latex-report/main.tex` 及其插入的 `sections/*.tex`、`tables/*.tex`、`figures/*`、`source-data/*`。
- 当前渲染稿为 `latex-report/main.pdf`（16 页）。在临时目录复制工程，用 XeLaTeX 编译两遍，结果与它文本完全一致、16 页逐像素一致，因此它对应当前源文件。
- `latex-report/bp_single_factor_report.pdf` 是 2026-10-26 的旧导出版本，与当前文本有 141 行差异，不是审阅对象。
- 分发审阅包前，记录了手稿快照的哈希（`supporting/packet_manuscript_SNAPSHOT_SHA256.txt`）。暂停后恢复审阅时重新核对，项目文件与审阅包均未改变。

## 技能加载

以下文件均已实际读取。

- **nature-reviewer（主框架）**
  - `SKILL.md`、`manifest.yaml`。
  - always_load 文件：`references/editorial criteria and processes.md`、`references/source-basis.md`。
  - 按需加载：`reviewer-workflow.md`、`report-structure.md`、`technical-concern-taxonomy.md`、`role-boundaries.md`、`qa-checklist.md`、`review-axes.md`、`forensic-consistency-audit.md`。
  - `domain-specific-review-gates.md` 不覆盖金融实证，未加载。
- **nature-shared（依赖）**
  - `SKILL.md`、`manifest.yaml`。
  - `core/consistency-sweep.md`、`core/terminology-ledger.md`、`core/ethics.md`、`core/reader-workflow.md`、`core/paper-type-taxonomy.md`。
- **nature-statistics**
  - `SKILL.md`、`manifest.yaml`。
  - `references/` 下的 `source-basis.md`、`statistical-reporting.md`、`common-failure-modes.md`、`figure-statistics.md`、`reviewer-checklist.md`。
  - 目标不是 Nature 或 NMI，因此未加载期刊专用要求。
- **nature-figure**
  - `SKILL.md`、`manifest.yaml`。
  - `static/core/contract.md`、`static/core/stance.md`。
  - `references/qa-contract.md`、`references/figure-legend-conventions.md`。
  - 本次为只读审查，不重绘图，因此未选择绘图后端，也未运行绘图审计脚本。
- **nature-polishing**
  - `SKILL.md`、`manifest.yaml`。
  - `static/core/` 下的 `stance.md`、`failure-modes.md`、`output-format.md`。
  - `static/fragments/` 下的 `paper_type/research.md`、`journal/generic.md`，以及 `section/` 下的 `abstract.md`、`results.md`、`conclusion.md`、`methods.md`。
  - 该技能的语言分支只有英文与中译英，没有中文到中文的润色分支。本稿须保持中文，因此只采用其核心立场、失效模式与术语一致性规则。`language/zh-to-en.md` 只作参照，未用于改写。

三位审阅人在各自上下文中，按审阅包第 8 节的清单重新读取了相应技能文件，并在报告第 0 节列出。

## 独立审阅的执行方式

1. 先阅读教材附录渲染页（书 197–200 页，PDF 211–214 页）。附录 A 表根据渲染页人工转录，因为文本抽取漏掉了根号。
2. 建立一份不可变的共同审阅包（`supporting/PACKET_README.md`），三位审阅人收到的内容完全相同。审阅包规定了：
   - 手稿快照、渲染页、教材、可读与禁读文件；
   - 课程标准与统计审查清单；
   - 结论分类与报告骨架。
   
   审阅包不含任何预设问题或共同关注清单。
3. 在任何报告生成之前，先确定三项侧重点：
   - 审阅人 1：课程条目覆盖、统计定义与数值一致性；
   - 审阅人 2：图表、中文表述、术语与渲染版面；
   - 审阅人 3：结论强度、分时段与分域解释、可复现边界。
   
   侧重点不是分工，每人都评估整份报告。
4. 三位审阅人在互相隔离的子代理上下文中工作，彼此不可见。审阅包禁止他们读取：
   - 既有的 `reviews/`、`outputs/validation/`；
   - 验收清单、项目状态文件和旧报告；
   - Git 历史。
5. 中途用户要求暂停，三个子代理被停止。恢复时继续的是同一组子代理，上下文完整保留，恢复指令中没有附带任何其他审阅人的信息或组织者的发现。
6. 运行环境不允许子代理自己写入报告文件。三份报告是组织者用 `supporting/extract_report.py` 从各审阅人的最终回复中逐字提取保存的，没有编辑。哈希与冻结时间见 `supporting/FREEZE_LOG.txt`。
7. 三份报告全部冻结后，组织者才开始数值审计（`audit.md`）和综合（`synthesis.md`）。只有至少两份报告独立提出的问题才称为共识。审计结果不计入共识，也没有回写审阅报告。
8. 组织者同样没有阅读既有的 `reviews/` 文件、`final_review.md` 或此前的“通过”结论。

## 冻结报告哈希（SHA-256）

| 文件 | 哈希 |
|---|---|
| reviewer_1.md | f4ca8e3ac5b958ba8cce2d7bbcc210365aa98ec8fe30ca915e46fceb76600889 |
| reviewer_2.md | 63277cc0cd7b2b7c050f80ab4ae8d478e34a424e25df0f11b9c88679966a9b0f |
| reviewer_3.md | 9a5d5b350c33250bd3c06fa55e1d235adad5545db9de967559f5207f9a530210 |

## 局限

- 三位审阅人基于同一模型，上下文虽然隔离，但推理倾向可能相近。高度一致的意见不等同于三位不同背景的人类审阅人。
- 证券层面的数据不在可读范围内，也没有重跑全市场研究。历史日期匹配、PB 修订与修复端点的逐项估值无法独立核实，详见 `synthesis.md` 第 7 节。
- 三位审阅人都报告，读取文件时运行环境自动显示了项目 `AGENTS.md`（项目工作规则，不含审阅结论），并声明未据其作任何判断。
