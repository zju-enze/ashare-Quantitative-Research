# Quantitative Research

A repository for reproducible quantitative finance research. Each study has a defined research question, documented inputs and statistical assumptions, and an explicit record of what has been implemented and executed.

## Research projects

| Project | Research question | Current status | Start here |
|---|---|---|---|
| **A-share value-signal robustness** | How robust is value-signal evidence after correcting measurement and changing the inferential framework? | Executed notebook, aggregate results, figures, and a local execution record are available. | [Study overview](VALUE_SIGNAL_RESEARCH.md) |
| **A-share industry cointegration** | Which predefined within-industry stock pairs show cointegration evidence under a fixed testing and multiple-correction protocol? | Final V1/V2 reports integrate the completed 20,000-path / 80,000-test supplement. Historical nominal market findings remain 110 (V1) and 0 (V2), with calibration limits retained. Old public results are archived; V3 remains paused. | [Project overview](projects/ashare-cointegration/README.md) |

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

The new project has three research stages:

1. **Cointegration evidence identification:** identify statistical discoveries among predefined within-industry pairs.
2. **Long–short construction and out-of-sample exploration:** investigate applications and subsequent behavior of identified relationships.
3. **Execution and cost validation:** examine implementability and trading outcomes.

**Final V1/V2 delivery (2026-10-22).** The [combined results](projects/ashare-cointegration/results_final/README.md), [V1 report](projects/ashare-cointegration/results_final/V1_FINAL_REPORT.md), and [V2 report](projects/ashare-cointegration/results_final/V2_FINAL_REPORT.md) integrate the historical market and calibration evidence with the completed common-DGP supplement.

The original adjusted-price-level market analysis remains unchanged: V1 has 110 L2-Holm nominal discoveries (7 under GLOBAL-Holm), while V2 has 0 under either domain. V1's historical calibration failures remain disclosed. V2's formal calibration remains inconclusive: C3-N0's one-sided 95% upper bound is 11.50%, above the prespecified 10% tolerance. Zero discoveries do not establish absence of cointegration.

The supplement used the same log-price pair paths for four specifications, with no stock-level ADF entry gate. Across four scenarios it completed 20,000 paths and 80,000 tests. Under the main DGP, fixed-one-lag EG/DH type-I error rates were 5.54%/5.06%, and slow-reversion power was 16.28%/8.56%. Under the specific-innovation nu=3.5 comparison, EG's type-I error rose to 6.78% and DH's was 4.62%. These are conditional pairwise results; they do not validate full-market family error control.

A [dated archive](projects/ashare-cointegration/archive/v1_v2_before_final_20261022/README.md) preserves all 159 historical public-output and context files. Original result paths remain available for reproduction; old reports link to the new final reports. [Machine-readable final results](projects/ashare-cointegration/results_final/FINAL_RESULTS.json) retain source references and uncertainty.

The [Student-t diagnostic](projects/ashare-cointegration/results_review/student_t_2021_2025/REPORT.md), [estimated pair DGP](projects/ashare-cointegration/results_review/dgp_fixed_nu_2021_2025/REPORT.md), and [supplementary report](projects/ashare-cointegration/results_revision/pair_comparison/REPORT.md) provide the supporting evidence. Current design and execution records are the [joint revision plan](projects/ashare-cointegration/EXPERIMENT_REVISION_PLAN_V1_V2.md) and [engineering arrangements](projects/ashare-cointegration/ENGINEERING_CHANGES.md).

V3 remains paused by the user. Revised full-family calibration, log-price market reruns, real-2026 evaluation, and trading stages have not been performed. This delivery synchronizes the GitHub branch only; it does not synchronize or restart the compute server.

## Repository organization

New studies live in self-contained directories under `projects/`, with their own configuration, data contract, dependencies, execution commands, and outputs. The original value-signal study retains its existing root-level layout.

Project-specific code becomes shared infrastructure only after its assumptions and interfaces have been shown to fit more than one study. Adding a study should preserve the reproducibility of existing work.

## Data and reproducibility

Raw vendor data and security-level intermediate panels remain local. Publish code, permitted research outputs, and provenance that distinguishes a planned analysis, a completed computation, and an independently verified result.

Dependencies and execution records are maintained at the study level. The repository reorganization itself does not constitute a new empirical execution of either study.
