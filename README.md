# Quantitative Research

A repository for reproducible quantitative finance research. Each study has a defined research question, documented inputs and statistical assumptions, and an explicit record of what has been implemented and executed.

## Research projects

| Project | Research question | Current status | Start here |
|---|---|---|---|
| **A-share value-signal robustness** | How robust is value-signal evidence after correcting measurement and changing the inferential framework? | Executed notebook, aggregate results, figures, and a local execution record are available. | [Study overview](VALUE_SIGNAL_RESEARCH.md) |
| **A-share industry cointegration** | Which predefined within-industry A-share pairs have cointegration evidence, under which tests and multiple-testing corrections? | The common-DGP method-validation experiment is complete. Reports now connect false positives and missed relationships to the stock-pair identification objective; a market evidence list under the revised design has not yet been produced. Earlier experiments are archived; V3 remains paused. | [Project overview](projects/ashare-cointegration/README.md) |

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

The research question is which predefined within-industry stock pairs have cointegration evidence, how that evidence is obtained and corrected for multiple testing, and where it applies. The intended output is a traceable stock-pair evidence list. Portfolio construction, out-of-sample trading and costs belong to later stages.

The present V1/EG and V2/DH experiments validate tools for that identification task. A common two-stock log-price DGP supplies known cointegration truth, so false-positive rates and detection power can be measured. Both primary specifications use one fixed lag; EG-AIC and DH-7 are lag-sensitivity checks.

The completed experiment has 20,000 shared paths and 80,000 tests. Under the main DGP, EG/DH false-positive rates are 5.54%/5.06% and slow-reversion detection rates are 16.28%/8.56%. The heavy-tail comparison exposes additional false-positive risk for EG. These findings inform how a future stock-pair list should be constructed and interpreted; they do not themselves identify actual market pairs.

The [research report](projects/ashare-cointegration/results_final/README.md), [V1 report](projects/ashare-cointegration/results_final/V1_FINAL_REPORT.md) and [V2 report](projects/ashare-cointegration/results_final/V2_FINAL_REPORT.md) now lead with the identification question, explain terminology at first use, and interpret results in terms of false discoveries and missed relationships. The [methods and glossary appendix](projects/ashare-cointegration/results_final/METHODS_AND_GLOSSARY.md) preserves formulas, parameters and complete sensitivity evidence.

The revised design still needs a coherent overlapping-stock family calibration, a specified correction domain and real-market testing before a new evidence list can be produced. [Machine-readable status](projects/ashare-cointegration/results_final/FINAL_RESULTS.json) makes this distinction explicit. Earlier designs remain in the [historical archive](projects/ashare-cointegration/archive/README.md); V3 remains paused.

## Repository organization

New studies live in self-contained directories under `projects/`, with their own configuration, data contract, dependencies, execution commands, and outputs. The original value-signal study retains its existing root-level layout.

Project-specific code becomes shared infrastructure only after its assumptions and interfaces have been shown to fit more than one study. Adding a study should preserve the reproducibility of existing work.

## Data and reproducibility

Raw vendor data and security-level intermediate panels remain local. Publish code, permitted research outputs, and provenance that distinguishes a planned analysis, a completed computation, and an independently verified result.

Dependencies and execution records are maintained at the study level. The repository reorganization itself does not constitute a new empirical execution of either study.
