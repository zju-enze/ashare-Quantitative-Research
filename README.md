# Quantitative Research

A repository for reproducible quantitative finance research. Each study has a defined research question, documented inputs and statistical assumptions, and an explicit record of what has been implemented and executed.

## Research projects

| Project | Research question | Current status | Start here |
|---|---|---|---|
| **A-share value-signal robustness** | How robust is value-signal evidence after correcting measurement and changing the inferential framework? | Executed notebook, aggregate results, figures, and a local execution record are available. | [Study overview](VALUE_SIGNAL_RESEARCH.md) |
| **A-share industry cointegration** | How do EG and DH compare on size and slow-reversion power under a common market-calibrated log-price DGP? | Formal V1/V2 reports use the completed 20,000-path / 80,000-test common-DGP design only. Earlier designs and experiments are archived; V3 remains paused. | [Project overview](projects/ashare-cointegration/README.md) |

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

The formal V1/V2 study uses a common, empirically calibrated two-stock log-price DGP. V1 is Engle–Granger and V2 is the DH joint bivariate test, both with one fixed lag in the primary comparison. The methods receive the same paths without a stock-level ADF entry gate; EG retains its residual ADF. EG-AIC and DH with seven lags are lag-sensitivity specifications.

Four predeclared scenarios have 5,000 independent paths each, for 20,000 paths and 80,000 tests. Under the main DGP, fixed-one-lag EG/DH type-I error rates are 5.54%/5.06% and slow-reversion power is 16.28%/8.56%. Under the specific-innovation nu=3.5 comparison, their type-I error rates are 6.78%/4.62%. These are conditional pairwise results, with pointwise uncertainty and paired differences reported.

Read the [formal results](projects/ashare-cointegration/results_final/README.md), [V1 report](projects/ashare-cointegration/results_final/V1_FINAL_REPORT.md), [V2 report](projects/ashare-cointegration/results_final/V2_FINAL_REPORT.md), and [machine-readable results](projects/ashare-cointegration/results_final/FINAL_RESULTS.json). Supporting evidence includes the [DGP estimation](projects/ashare-cointegration/results_review/dgp_fixed_nu_2021_2025/REPORT.md), [executed design](projects/ashare-cointegration/EXPERIMENT_REVISION_PLAN_V1_V2.md), and [recorded validation](projects/ashare-cointegration/results_revision/pair_comparison/formal_validation.json).

Earlier designs, market experiments and calibration results are retained in the [historical archive](projects/ashare-cointegration/archive/README.md), outside the formal reports. Their stable paths remain as reproduction working copies. The current design has not been extended to a full overlapping-stock family calibration, real-market pair identification, holdout evaluation or trading work. V3 remains paused.

## Repository organization

New studies live in self-contained directories under `projects/`, with their own configuration, data contract, dependencies, execution commands, and outputs. The original value-signal study retains its existing root-level layout.

Project-specific code becomes shared infrastructure only after its assumptions and interfaces have been shown to fit more than one study. Adding a study should preserve the reproducibility of existing work.

## Data and reproducibility

Raw vendor data and security-level intermediate panels remain local. Publish code, permitted research outputs, and provenance that distinguishes a planned analysis, a completed computation, and an independently verified result.

Dependencies and execution records are maintained at the study level. The repository reorganization itself does not constitute a new empirical execution of either study.
