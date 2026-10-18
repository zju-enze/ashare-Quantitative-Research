# A-share Industry Cointegration

**Current scope: Stage 1 — identification of cointegration evidence.**

> Among predefined within-industry A-share stock pairs, which pairs show cointegration evidence under a fixed sample, model specification, and multiple-testing procedure?

本项目当前回答“哪些预先限定的同业股票对具有协整证据、证据是什么、统计声明的范围是什么”。多空组合构建、样本外探索与交易验证属于后续阶段。

## Current status

The v1.2 plan and implementation clarifications now have an independent Python environment, a production statistical kernel, free-source acquisition and audits, frozen-family batch execution, reporting, and resumable S0/S1/S2 simulation.

Market acquisition and S1 are currently running. S0 completed all 80 prescribed panels; its small-repetition diagnostic alarms are retained. Market candidates and empirical findings will be reported only after the full input audit and frozen-family execution finish. See [RESEARCH_STATUS.json](RESEARCH_STATUS.json), [acquisition status](results/acquisition_status.json), and [simulation status](results/simulation/S1_status.json).

Historical v1.2 configuration and rule-check artifacts were located in the local quant_lab workspace and copied to archive/. Their claimed 15 checks were not rerun here. Current production-path tests are separate; they exercise real coint, lag diagnostics, zero-value provenance, complete families, one/eight workers, exact decimal price coordinates, and the frozen pipeline's resume path.

## Reading and implementation order

| Document | Purpose |
|---|---|
| [EXPERIMENT_PLAN.md](EXPERIMENT_PLAN.md) | Supplied v1.2 plan, preserved byte for byte. |
| [REVIEW_AND_IMPLEMENTATION.md](REVIEW_AND_IMPLEMENTATION.md) | Independent review and binding clarifications for implementation. |
| [CODEX_STAGE1_PROMPT.md](CODEX_STAGE1_PROMPT.md) | Handoff for implementing and executing Stage 1. |
| [RESEARCH_STATUS.json](RESEARCH_STATUS.json) | Separate implementation, empirical-production, calibration, and later-stage states. |

Read the plan and review together. Where the review explicitly clarifies the plan, use the clarified definition and record it in the executable protocol before production.

## Stage 1 specification

The identification period is **2021–2025**. Candidate pairs come from the documented eligible stock universe and SW2021 industry membership at the end of 2025.

- Price-level Engle–Granger testing with a constant.
- One fixed regression direction determined by stock-code order.
- Specified I(1) applicability checks and AIC lag selection.
- Complete candidate families fixed before applicability and pair testing.
- **Holm correction within each L2 family at nominal 5%** as the primary discovery rule.
- L3/L2/GLOBAL and BF/Holm/BH results as the specified comparison views.

Beta's sign is an estimated property of the relationship, not a Stage 1 eligibility filter. The merged primary table is a summary of separately corrected L2 families; it does not inherit a single market-wide 5% FWER guarantee.

## Required outputs

1. Stock eligibility audit, industry mapping, and frozen complete candidate registry.
2. Every candidate's test or explained terminal status, with applicability and numerical diagnostics.
3. Complete multiple-testing results under the original family definitions.
4. The full primary cointegration-evidence table, estimated equations, supporting statistics, and family labels.
5. Statistical report, execution provenance, and separately labeled simulation diagnostics.

Nonrejections, inapplicable correction domains, numerical exclusions, empty families, and zero discoveries remain visible in the record. Discoveries produced before the planned calibration finishes must disclose that status.

## Interpretation and later stages

A discovery means rejection of the no-cointegration null under the specified sample, model, and correction rule, subject to the validity of the underlying p-values. It does not establish permanent equilibrium, future convergence, or profitability.

| Stage | Research question | Status |
|---|---|---|
| 1 | Which predefined same-industry pairs have cointegration evidence? | Current implementation scope |
| 2 | How can frozen relationships inform long–short construction and subsequent spread behavior? | Planned / deferred |
| 3 | What remains after execution, borrowing, accounting, and trading costs? | Planned / deferred |

Later-stage work is not required to deliver the Stage 1 statistical report. Stage 1 empirical production and its planned simulation calibration also have separate completion states.

## Implementation and relationship to the existing study

Keep this project's configuration, dependencies, source, tests, runtime entry points, and outputs in this directory. Document local input locations and schemas; keep licensed raw records and caches local.

The [existing value-signal study](../../VALUE_SIGNAL_RESEARCH.md) uses a monthly analysis pipeline and a 2005–2024 sample boundary. Its presence does not establish validated 2021–2025 daily prices, adjustment factors, or historical industry membership for this project. Reuse requires a documented compatibility check.

## Reproduce and resume Stage 1

Run these commands in projects/ashare-cointegration/ using Python 3.11:

~~~powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\fetch_sources.ps1
.\.venv\Scripts\python.exe collect_market.py --workers 8
.\.venv\Scripts\python.exe scripts/verify_action_cases.py
.\.venv\Scripts\python.exe run_stage1.py --workers 8 --run-id formation-2021-2025-v2
~~~

The same acquisition/run commands resume completed security caches and statistical batches. An unresolved request or computation error prevents a complete status. Changing the frozen code/protocol requires a documented correction and a new run-id; do not delete prior evidence. [DATA_CONTRACT.md](DATA_CONTRACT.md) describes source schemas, SW2021 historical reconstruction, source coverage, and the C1 exact-record-coordinate comparison.

~~~powershell
.\.venv\Scripts\python.exe run_simulation.py --stage S0 --workers 8
.\.venv\Scripts\python.exe run_simulation.py --stage S1 --workers 8
.\.venv\Scripts\python.exe run_simulation.py --stage S2 --workers 8
~~~

S0 → S1 → S2 completion dependencies concern engineering completeness, not favourable rejection rates. Each repetition has a local checkpoint; rerunning the same stage reuses completed repetitions. Nominal market discovery production does not wait for complete calibration.

| Output | Location |
|---|---|
| Effective protocol and environment | experiment_protocol.json; results/environment.json |
| Raw responses and per-security audit | .local/sources/; .local/market/ |
| Complete frozen U/H, prices, stock exclusions, ADF and pair results | .local/production/{run-id}/ |
| Full primary evidence table and statistical report | results/main_evidence.csv; results/STAGE1_REPORT.md (created after market execution) |
| Full family accounting and cross-view comparison | results/families.csv; results/view_overlap.csv |
| Simulated panels and per-repetition evidence | .local/simulation/ |
| Calibration completion and family-level diagnostics | results/simulation/ |

No Tushare credential is required by this implementation. Public sources replace the unavailable credentialed route without changing the SW2021 standard or the identification window. Raw price records and large security-level caches remain ignored; publish only research outputs with appropriate scope.

Second and third stages remain planned_deferred. No 2026 price evaluation, trading signal, portfolio, borrowing or cost module is executed. Return to the [repository overview](../../README.md).
