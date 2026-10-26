# BP 单因子测试报告

方法版本0.5；2026-10-26完成P0–P7。按课程附录优秀标准交付C1–C4、D1–D10、行业中位数和市值相关诊断。三池共同228个完整持有期，行业比较采用事先冻结的54期。

- [中文完整报告](report/bp_single_factor_report.md)
- [正式运行结果索引](outputs/runs/bp-v05-20261026-main/README.md)
- [最终证据审阅](outputs/validation/final_review.md)
- [验收清单](docs/ACCEPTANCE_CHECKLIST.md)
- [项目状态与决策记录](docs/PROJECT_STATUS.md)

结论为保留BP作为后续研究候选，观察时变性与适用域。全A平均Rank IC为0.0566，五层年化净收益递增，多空年化13.00%；两指数池较弱，年度和行业存在反例。C4中30个行业有完整共同窗口，综合行业不足，未拼接年化。结果不构成严格PIT、实盘可交易性或未来收益保证。

## 复现

使用既有课程Python环境及课程材料目录。原始数据只读，证券级修复、形成与持仓明细保留在被忽略的`.local/`。公开仓库包含代码、汇总、表图和文档，不包含整套课程原始库。

本机课程Python为`F:/quant_lab/.venv/Scripts/python.exe`；课程材料为`F:/quant_lab/量化投资课程资料包`。路径集中在本地`.local/paths.json`的`course_root`字段。P1修复面板须先准备好，入口及来源见[修复后预检](outputs/preflight_repaired/preflight_findings.md)、[修复说明](outputs/repairs/README.md)与`scripts/preflight_repaired.py`。

在项目目录、课程环境中运行：

```powershell
python -m unittest discover -s tests -p test_bp_core.py -v
python scripts/run_research.py --run-id <新的运行标识> --course-root <课程材料目录>
python scripts/plot_results.py --run-id <同一运行标识>
python scripts/build_report.py --run-id <同一运行标识>
python scripts/validate_results.py --run-id <同一运行标识>
```

正式运行不覆盖已有run_id。`build_report.py`的文字针对当前冻结研究，若更改数据或方法，需要重新审阅叙述。没有替换原课程Notebook或共享qfbook，正确的MAD、中性化、设计矩阵和双腿扣费均复用课程函数。实现差异及5项新增检查见[实现说明](outputs/validation/implementation_notes.md)；此前15项P1检查已通过。

## 方法与过程文档

统计方法唯一维护位置为[RESEARCH_SPEC](docs/RESEARCH_SPEC.md)；[EXECUTION_PLAN](docs/EXECUTION_PLAN.md)保存阶段与门槛；[DATA_CONTRACT](docs/DATA_CONTRACT.md)记录源字段和样本要求；[IMPLEMENTATION_REVIEW](docs/IMPLEMENTATION_REVIEW.md)保存课程实现差异；[WRITING_AND_SKILLS](docs/WRITING_AND_SKILLS.md)规定中文写作与技能边界；[AGENTS.md](AGENTS.md)规定项目范围。

原始P0/P1预检保留在`outputs/preflight/`，修复后P1为`outputs/preflight_repaired/`。完整历史过程、授权和方法变更继续保留在PROJECT_STATUS，不将后来的完成状态倒写为早期已经完成。
