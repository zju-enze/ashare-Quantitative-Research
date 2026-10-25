# BP 单因子测试报告

版本：1.1（2026-10-25，本地P0/P1预检）

本项目研究BP，优先复用已有程序，以教材附录优秀标准为目标。P0环境与源码接入已通过；P1已生成日期表、候选样本流转及历史资料缺口记录，正式股票池和可靠窗口尚未通过。当前没有回测核心修改、因子实证结果或完整报告。

当前入口：[项目状态](docs/PROJECT_STATUS.md)、[P0/P1预检发现](outputs/preflight/preflight_findings.md)。

课程材料和源码位于`F:\quant_lab\量化投资课程资料包`，原始数据位于其`data/offline`。证券级核验明细只保存在本项目被Git忽略的`.local/preflight/`。

从本项目目录重现数据预检（不运行因子测试）：

```powershell
& 'F:\quant_lab\.venv\Scripts\python.exe' -X utf8 -m unittest discover -s tests -v
& 'F:\quant_lab\.venv\Scripts\python.exe' -X utf8 scripts/preflight.py --course-root 'F:\quant_lab\量化投资课程资料包'
```

## 放到哪里

将本包内容放入用户已指定的项目目录：

F:\Robustness of Value Signals and Asset-Pricing Models in China A-Shares\projects\单因子测试报告

压缩包中的 AGENTS.md、README.md、docs/ 应直接位于该项目根目录。若本地已有同名文件，先读取并合并，不覆盖既有研究记录。课程和原始数据继续留在 F:\quant_lab。

原文档包编制时没有连接本地Windows目录。2026-10-25已完成本地接入与本轮可执行预检，核实内容及限制以PROJECT_STATUS为准；以下首次启动提示词保留为建立文档包时的记录。

## 九份文档如何分工

| 文档 | 用途 | 维护规则 |
|---|---|---|
| [AGENTS.md](AGENTS.md) | Codex的常驻行为约束、范围与读取顺序 | 保持精简；不放全部统计细节 |
| [README.md](README.md) | 人类入口、文件导航和启动提示词 | 项目入口变化时更新 |
| [RESEARCH_SPEC.md](docs/RESEARCH_SPEC.md) | 因子、股票池、时点、处理、指标与分域口径 | 统计方法的唯一维护位置 |
| [EXECUTION_PLAN.md](docs/EXECUTION_PLAN.md) | P0–P7阶段、产物、验证与继续条件 | 路径变化时同步；不填实证结论 |
| [DATA_CONTRACT.md](docs/DATA_CONTRACT.md) | 所需源文件、字段语义、时点和样本流转 | 记录核实事实，不猜字段 |
| [IMPLEMENTATION_REVIEW.md](docs/IMPLEMENTATION_REVIEW.md) | 上传实现的重点问题与最小修正顺序 | 本地版本比对后更新状态 |
| [ACCEPTANCE_CHECKLIST.md](docs/ACCEPTANCE_CHECKLIST.md) | 附录A–E、C1–C4、D1–D10及质量检查 | 完成后附证据再勾选 |
| [WRITING_AND_SKILLS.md](docs/WRITING_AND_SKILLS.md) | 中文写作、证据对应、nature等技能路由 | 技能版本与实际可用性须记录 |
| [PROJECT_STATUS.md](docs/PROJECT_STATUS.md) | 当前阶段、决策、问题、运行记录、下一步 | 每轮结束更新；唯一动态入口 |

## 第一次交给Codex的提示词

将下面内容完整交给位于本项目目录中的Codex。此启动范围仅到接入和数据预检；后续阶段由你继续指定。

> 请先读取当前路径上适用的AGENTS.md，以及本项目README、docs/PROJECT_STATUS.md、docs/RESEARCH_SPEC.md和docs/EXECUTION_PLAN.md。目标是检验BP因子，优先复用F:\quant_lab中的已有程序，并按教材附录优秀标准完成报告。
>
> 本轮执行P0和P1：核实项目与环境路径，先比较本地single_test.py的SHA-256与IMPLEMENTATION_REVIEW所列摘要；一致则确认同版，不一致则按审阅事项重新核查本地行为。原始上传快照未随本包附带，只有实际取得快照才做逐行差异比较。随后定位main_student.pdf附录，读取数据字段与覆盖摘要，核查历史成分/行业/股票状态以及实际可用skills。优先使用已有检查入口；必要读取与摘要保持原始文件只读。
>
> 先完成所有当前能完成的核实，不要因为一项数据暂缺就停掉其余工作。不要运行完整单因子测试，不编写回测核心实现，不生成结果性报告，不改动原始数据或共享课程库，也不要安装第三方skills。
>
> 更新PROJECT_STATUS中的路径、版本、缺口、研究默认设定的冻结情况和下一阶段建议。用中文向我说明：哪些已经核验，哪些只是字段/文件存在，哪些仍未验证，P2最小修改涉及哪些函数。遇到实质改变研究问题的决策再集中提问，不要逐个文件请求确认。

## 以后如何继续

- “执行P2”表示完成最小实现修正及针对性核验，尚不自动授权全样本实证。
- “执行P3–P5”表示在前置条件通过后完成诊断、基础和优秀线计算；普通可逆修复可在范围内完成。
- “执行P6–P7”表示基于锁定结果写报告、做证据审阅和最终验收。
- 若希望一次推进更多阶段，可以明确给出阶段范围；阶段之间仍需满足证据条件，并持续汇报。

每次继续都先读PROJECT_STATUS；不要重新从零规划，也不要把未完成项直接改为完成。

## 项目默认设定的性质

主因子BP、优先复用、优秀线是用户确认事项。正且有限PB的倒数、月末估值截面、2007年目标起点、三池共同可靠窗口、全A主图、D3算术累积、分域方法等在RESEARCH_SPEC逐项注明依据。它们作为可执行默认建议，P1核验后冻结；不表示已经检查过本地数据。

若数据确实止于2026-02-13，按下一交易日收盘到下一次换仓收盘的规则，2026-01信号尚无完整持有期；具体可用末期须用真实日历和各数据源共同覆盖确认。

## 资料依据

1. 用户上传main_student.pdf，附录书内197–200页／PDF211–214页；正文用于补充成本、回报与方法解释。
2. 用户上传single_test.py及课程工作区README.md，均只是静态快照；摘要值见IMPLEMENTATION_REVIEW。
3. [OpenAI官方AGENTS.md指南](https://developers.openai.com/codex/guides/agents-md/)：项目指令按目录发现；从本项目目录开启会话，并让Codex说明实际读取到的规则。不要修改全局配置来掩盖项目文件未加载的问题。
4. 外部学术技能来源及适用边界见WRITING_AND_SKILLS。文档包没有安装这些技能，也不宣称它们属于期刊官方规范。

