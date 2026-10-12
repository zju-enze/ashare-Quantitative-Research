# Research design and correction record

The project uses one executable notebook, `notebooks/ashare_value_signal_robustness.ipynb`, with a common data pipeline and two connected empirical analyses: signal robustness and asset-pricing model comparison. Licensed vendor data and security-level intermediate panels remain local.

## Corrections that change interpretation

| Original issue | Implemented correction | Evidence |
|---|---|---|
| EP labels used raw close ratios | Close multiplied by the vendor adjustment factor before calculating returns | Split-adjustment regression test; actual affected-observation count in `data_audit.json` |
| Monthly characteristics were sorted against the same month's realized return | Month-end t signals evaluated against t+1 returns | Forward-sort regression test; explicit `return_month` |
| Shifting observations could bridge missing calendar months | Nonadjacent months produce missing monthly/forward returns | Calendar-gap regression test |
| One momentum shift was not grouped by stock; window definition was inconsistent | Eleven monthly returns through t-1, computed within stock, excluding t, with a contiguous-calendar requirement | Momentum-window regression tests |
| Today's ST status was applied across historical years | Effective historical name intervals and announcement dates identify ST at formation | Date-specific ST test |
| Latest annual-report versions could enter earlier formation dates | Income, current balance sheet, and prior-year balance sheet are independently selected as of formation | Future-revision and conflicting-report tests |
| Missing future labels could alter the sort breakpoints | Sort all eligible known signals before computing observed-label returns | Future-missingness regression test |
| Artificial p values were mixed into an empirical factor-screening claim | Apply HAC tests and BH/Holm corrections to a fixed six-signal family of real returns | Executed signal tables |
| FF5 reused FF3's size factor | Average SMB from the value, profitability, and investment sorts | Executed FF3/FF5 construction |
| The GRS prefactor did not match the chosen covariance denominators | Use the unbiased covariance convention and prefactor from CRAN `GRS.test` | Known-covariance regression fixture |
| Hard-coded narrative claimed rejection irrespective of p values | Generate the fixed-5% verdict directly from each computed p value | Executed notebook assertion |
| Clipped realized returns were treated as the primary outcome | Primary returns remain untrimmed | Shared monthly panel and research code |

## Common panel

- Study observations: January 2005–December 2024. Actual usable return months depend on signal availability; the final formation date for forward evaluation is November 2024.
- Universe at formation: historical non-ST status, at least 120 **calendar** days since listing, positive volume on at least 15 days (or all market trading days when the month has fewer than 15), positive market capitalization, and positive-volume trading on the formation date. The short-month rule prevents the 14-trading-day February 2005 from clearing the entire universe.
- The last 20 global market trading dates define the final-snapshot liquidity window. This descriptive snapshot does not impose a historical liquidity threshold on the factor study.
- Adjusted close = close × adjustment factor. Returns are adjacent-calendar-month adjusted close ratios. The vendor adjustment factor is accepted as supplied; this is not an independently reconstructed corporate-actions database.
- EP excludes nonpositive or missing PE. Value uses positive inverse PB. Different signals can have different available samples, reported in the saved quintile tables.
- Missing next-month returns are never used to change formation-time group boundaries. Group return means still use observed labels: unobserved liquidation/delisting proceeds remain a limitation, not an assumed zero-loss exit.

## Statistical inference

All six signals receive Fama–MacBeth (FM) regressions. Characteristics use 1%/99% cross-sectional winsorization and sample-standard-deviation scaling, with the declared direction: Size is negative standardized log market capitalization and LowVol is negative standardized volatility. The five non-Size signals have raw, size-controlled, and size/static-industry-controlled specifications. Size has raw and industry-controlled specifications; adding the same size variable as a control would be collinear. Each signal uses its own available monthly sample, held fixed across its specifications. Industry fixed effects use the supplied static classification, including an explicit unknown category; they cannot be described as fully historical industry exposures.

Monthly cross-sectional coefficients, raw Rank IC, and neutralized Rank IC are separate time series. HAC inference tests their means with six calendar-month lags and Bartlett weights. A missing month has no centered-score contribution rather than collapsing two distant observations into adjacent months; the mean and standard error use the observed-month count. This agrees with the uncorrected statsmodels HAC mean standard error on a complete monthly series. Coefficients are conditional associations; a standardized-characteristic regression slope is not a portfolio return or causal effect.

The six predeclared signal directions are high EP, small size, high B/M, positive momentum, low total volatility, and high operating profitability. Their equal-weighted top/bottom quintile spreads use next-month returns. BH-FDR and Holm corrections are applied separately to the six spread tests within each reported period. FM slopes and raw/neutralized IC also receive corrections within each period and statistic: six tests for raw slopes, industry-controlled slopes and each IC, and five tests for size-controlled slopes. These separate families do not adjust for every specification or earlier research decision. No signal direction is reversed after seeing the results.

The chronological split is development return months before January 2018 versus return months from January 2018. It is **retrospective**: the full history had already been analyzed before this split was defined. No claim of untouched prospective testing is made. All six signal spreads receive 10,000 moving-block resamples for full, development and holdout periods, using a fixed seed and block lengths 3, 6, 7, and 12 calendar months (72 settings). The 95% percentile Sharpe intervals are pointwise, not simultaneous six-signal bands. Internal missing calendar positions remain inside sampled blocks; each sampled Sharpe uses its observed returns. This matters for Profitability, which has 29 internal missing months in its full window, and does not establish random missingness. Different signal start dates mean full-sample Sharpes are not common-window rankings. The EP-only within-month permutation diagnostic uses 2,000 shuffles and an exchangeability assumption; it is not evidence that temporal dependence or common cross-sectional exposures have been fully modeled.

## Asset pricing

June formation uses prior-year accounting information available strictly before formation. Book-to-market for annual sorts uses prior-year book equity divided by prior-December market equity; characteristic-based monthly value sorts instead use the supplied daily PB field. These are intentionally different definitions and are named separately in code.

Annual 2×3 portfolios are held July–June. Monthly returns are value-weighted with prior-month capitalization, using the full observed holdings panel rather than next month's eligibility-filtered panel. Test assets are 25 portfolios formed from independent size/value quintile sorts with the same holding convention; statistical independence of portfolio returns is not assumed. CAPM, FF3, and FF5 are compared on common dates and identical test assets. These test assets are not the six monthly signal spreads, so GRS results cannot establish that the models explain those spreads.

The operating-profitability proxy is `(revenue - operating cost - selling expense - administrative expense) / positive book equity`. Missing expense fields in an otherwise available report are treated as zero; missing revenue/equity remains missing. Interest expense is unavailable. Asset growth uses current and previous annual assets as available at formation. Local whole-universe breakpoints replace U.S. NYSE breakpoints. These factors must be labeled **A-share adaptations**, not exact replications of official factors.

The market benchmark is an investable-universe value-weighted return, not an official all-market index. The risk-free proxy is one-year SHIBOR divided by 12; missing pre-SHIBOR months use 3% annualized. The beta analysis uses trailing 60-calendar-month excess-return regressions with at least 36 valid observations and predicts the following month's excess return.

GRS uses `Sigma = residual' residual / (T-K-1)` and factor covariance divided by `T-1`, with the corresponding CRAN prefactor `(T/N) × (T-N-K)/(T-K-1)`. Its finite-sample reference distribution assumes a stationary correctly specified model with the stronger conventional residual assumptions. HAC robustness of coefficient means does not make the GRS F reference distribution robust. Nonrejection is not proof of the model; comparing two model p values is not a formal nested-model improvement test.

## Limits that remain

1. The supplied exports include delisted stocks, but exhaustive historical security coverage and all delisting liquidation returns are not established.
2. Announcement-aware selection prevents use of a supplied future version; it cannot recover historical report vintages absent from the vendor export. PE/PB and adjustment histories are accepted vendor fields, not independently point-in-time archived observations.
3. Static industry labels and an approximate risk-free series limit historical precision.
4. Gross long–short spreads are academic portfolios with 100% long plus 100% short exposure. Fees, impact, stock borrowing, price limits, and executable close-to-close trading are not modeled. Results are not tradable alpha claims.
5. The holdout is retrospective, and conventional GRS assumptions may fail for financial return data.

## Primary references

- [Kenneth French: factor construction](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/f-f_5_factors_2x3.html).
- [CRAN GRS.test: reference implementation](https://github.com/cran/GRS.test/blob/master/R/GRS.test.R).
- [statsmodels: heteroskedasticity/autocorrelation robust covariance](https://www.statsmodels.org/stable/generated/statsmodels.regression.linear_model.RegressionResults.get_robustcov_results.html).
