# Quantitative Research

A repository for reproducible quantitative finance research. Each study has a defined research question, documented inputs and statistical assumptions, and an explicit record of what has been implemented and executed.

## Research projects

| Project | Research question | Current status | Start here |
|---|---|---|---|
| **A-share value-signal robustness** | How robust is value-signal evidence after correcting measurement and changing the inferential framework? | Executed notebook, aggregate results, figures, and a local execution record are available. | [Study overview](VALUE_SIGNAL_RESEARCH.md) |
| **A-share industry cointegration** | Which predefined within-industry A-share pairs have cointegration evidence, under which tests and multiple-testing corrections? | Stage 1 research and reporting completed: 67,678 candidates, nominal pair evidence, and six proposed pairs for subsequent exploration. Full-family calibration remains incomplete; stages 2 and 3 have not started. | [Stage 1 final report](projects/ashare-cointegration/results_final/STAGE1_FINAL_REPORT.md) |
| **单因子测试报告** | How does a selected factor relate to subsequent returns, and how stable is that evidence across samples and test specifications? | Initialized; factor definition, sample, and test specifications are pending. No tests have been executed. | [Project overview](projects/单因子测试报告/README.md) |

## A-share value-signal robustness

The existing study examines 2005–2024 A-share data. EP is the focal example, with five other characteristics forming a fixed comparison set. It distinguishes rank association, conditional Fama–MacBeth slopes, gross portfolio spreads, and the pricing of size–value portfolios by CAPM and adapted FF3/FF5 models.

Its complete findings, qualifications, and reproduction instructions are preserved in the [original research overview](VALUE_SIGNAL_RESEARCH.md).

- [Complete research notebook](notebooks/ashare_value_signal_robustness.ipynb)
- [Methodology and correction record](docs/methodology.md)
- [Research findings](docs/findings.md)
- [Required local input schemas](docs/data.md)
- [Recorded local execution status](results/execution.json)

The chronological holdout is retrospective. Published long–short results are gross academic spreads; the study documents the execution conditions that were not modeled.

### Reproduce the existing study

Run from the repository root. Python 3.11 was used for the recorded execution.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe run_research.py --data-dir 'PATH_TO_LICENSED_PARQUET_DIRECTORY'
```

The root-level `requirements.txt`, `run_research.py`, `src/`, `tests/`, `notebooks/`, `docs/`, `results/`, and `figures/` serve this existing study. Its execution paths are retained. GitHub Actions runs its small regression tests without vendor data; full empirical reproduction requires the documented local inputs.

## A-share industry cointegration

The research asks which predefined within-industry stock pairs have cointegration evidence, how the evidence is tested and corrected, and where it applies. Portfolio construction and trading remain later stages.

On 2026-10-23 the revised log-price market experiment completed all 67,678 candidates under four specifications, totaling 270,712 tests. Both primary methods use one fixed lag without a stock-level ADF entry gate. Within-L2 and GLOBAL Holm views were specified before seeing the market p-values, with a nominal 5% level and identical domains across methods.

Primary EG discoveries number 284 within L2 and 21 globally; primary DH discoveries number 11 and 0. EG-AIC yields 162/10 and DH-7 yields 7/0. The within-L2 primary intersection has three pairs, reported descriptively rather than treated as a newly calibrated selection rule.

These are nominal evidence lists. Stock-level applicability warnings affect 148 of the 284 within-L2 EG discoveries and four of the 11 DH discoveries. DH-1 has 43 early-prefix numerical placeholders, retained at p=1 in the full families. Complete shared-stock family calibration remains unfinished.

The [market report and evidence lists](projects/ashare-cointegration/results_revision/market_20261023/REPORT.md), [research overview](projects/ashare-cointegration/results_final/README.md), [V1 report](projects/ashare-cointegration/results_final/V1_FINAL_REPORT.md), [V2 report](projects/ashare-cointegration/results_final/V2_FINAL_REPORT.md), and [methods/glossary](projects/ashare-cointegration/results_final/METHODS_AND_GLOSSARY.md) present the findings and limits. All output rows and Holm views were reconciled, with 32 predeclared independent reference evaluations.

The prior 20,000-path common-DGP study remains the method-validation evidence and was not rerun. Earlier designs remain [archived](projects/ashare-cointegration/archive/README.md). V3 remains paused, and real-2026 evaluation and trading work have not been started.

## Repository organization

New studies live in self-contained directories under `projects/`, with their own configuration, data contract, dependencies, execution commands, and outputs. The original value-signal study retains its existing root-level layout.

Project-specific code becomes shared infrastructure only after its assumptions and interfaces have been shown to fit more than one study. Adding a study should preserve the reproducibility of existing work.

## Data and reproducibility

Raw vendor data and security-level intermediate panels remain local. Publish code, permitted research outputs, and provenance that distinguishes a planned analysis, a completed computation, and an independently verified result.

Dependencies and execution records are maintained at the study level. The repository reorganization itself does not constitute a new empirical execution of either study.
