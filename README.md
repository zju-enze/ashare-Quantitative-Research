# Quantitative Research

A repository for reproducible quantitative finance research. Each study has a defined research question, documented inputs and statistical assumptions, and an explicit record of what has been implemented and executed.

## Research projects

| Project | Research question | Current status | Start here |
|---|---|---|---|
| **A-share value-signal robustness** | How robust is value-signal evidence after correcting measurement and changing the inferential framework? | Executed notebook, aggregate results, figures, and a local execution record are available. | [Study overview](VALUE_SIGNAL_RESEARCH.md) |
| **A-share industry cointegration** | Which predefined within-industry stock pairs show cointegration evidence under a fixed testing and multiple-correction protocol? | Stage 1 plan reviewed; implementation and empirical execution pending in this repository. | [Project overview](projects/ashare-cointegration/README.md) |

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

**Stage 1 is the current scope.** Its output will be a complete record of which pairs show cointegration evidence, the supporting tests and corrections, and the limits of those statements.

Read the [project overview](projects/ashare-cointegration/README.md), [experiment plan](projects/ashare-cointegration/EXPERIMENT_PLAN.md), and [independent review](projects/ashare-cointegration/REVIEW_AND_IMPLEMENTATION.md). The [Codex Stage 1 prompt](projects/ashare-cointegration/CODEX_STAGE1_PROMPT.md) defines the implementation handoff.

## Repository organization

New studies live in self-contained directories under `projects/`, with their own configuration, data contract, dependencies, execution commands, and outputs. The original value-signal study retains its existing root-level layout.

Project-specific code becomes shared infrastructure only after its assumptions and interfaces have been shown to fit more than one study. Adding a study should preserve the reproducibility of existing work.

## Data and reproducibility

Raw vendor data and security-level intermediate panels remain local. Publish code, permitted research outputs, and provenance that distinguishes a planned analysis, a completed computation, and an independently verified result.

Dependencies and execution records are maintained at the study level. The repository reorganization itself does not constitute a new empirical execution of either study.
