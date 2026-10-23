"""DH (2018), DOI 10.1111/obes.12214, bivariate development implementation.

Accepted manuscript pp. 7-9; Appendix S1 sums t=p+2,...,T.
Constant means only, no deterministic drift. No defactoring or bootstrap.
"""
import numpy as np
from statsmodels.stats.multitest import multipletests


def recursive_errors(a, b):
    """Paper's recursively demeaned prefix regression, A normalized on B."""
    y = np.column_stack((a, b)).astype(float)
    # Remove the initial level first to avoid cancellation at large price levels.
    y -= y[0]
    centered = y - np.cumsum(y, axis=0) / np.arange(1, len(y) + 1)[:, None]
    aa, bb = centered.T
    denominator = np.cumsum(bb * bb)
    if np.any(denominator[2:] == 0):
        raise np.linalg.LinAlgError("recursive_regression_rank_deficient")
    errors = np.zeros(len(y))
    errors[2:] = aa[2:] - bb[2:] * np.cumsum(aa * bb)[2:] / denominator[2:]
    return errors


def _empty_audit(T, lags):
    return dict(N_input=T, N_effective=max(0, T-lags-1), lags=int(lags),
               covariance_denominator=T, DH_executed=False, Q=None, df=2,
               p_raw=None, log_p=None, p_for_adjustment=1.,
               compute_status="numerically_ineligible", placeholder_reason=None,
               p_zero_origin=None, adjustment_A=None, adjustment_B=None,
               t_A=None, t_B=None, residual_correlation=None,
               control_rank=None, control_condition=None, covariance_condition=None,
               instrument_denominator=None, instrument_residual_ss=None)


def dh_audit(a, b, lags=7):
    """One joint rank-zero test; covariance normalization is original T."""
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if a.ndim != 1 or b.ndim != 1 or a.shape != b.shape:
        raise ValueError("Aligned one-dimensional pair inputs required")
    if not isinstance(lags, (int, np.integer)) or lags < 0:
        raise ValueError("lags must be a nonnegative integer")
    T = len(a)
    row = _empty_audit(T, lags)
    if T-lags-1 <= 2*lags+2:
        row["placeholder_reason"] = "insufficient_observations"
        return row
    if not np.isfinite(a).all() or not np.isfinite(b).all():
        row["placeholder_reason"] = "nonfinite_input"
        return row
    try:
        errors = recursive_errors(a, b)
        differences = np.diff(np.column_stack((a, b)), axis=0)
        target = differences[lags:]
        error = errors[lags:-1]
        instrument = np.sign(error)
        rhs = np.column_stack((error, instrument, target))
        if lags:
            controls = np.column_stack(
                [differences[lags-j:len(differences)-j] for j in range(1, lags+1)])
            fit, _, rank, singular = np.linalg.lstsq(controls, rhs, rcond=None)
            row.update(control_rank=int(rank),
                       control_condition=float(singular[0]/singular[-1]))
            if rank != 2*lags:
                row["placeholder_reason"] = "lag_design_rank_deficient"
                return row
            rhs -= controls @ fit
        else:
            row.update(control_rank=0, control_condition=1.)
        er, zr, dy = rhs[:, 0], rhs[:, 1], rhs[:, 2:]
        denominator, zss = float(zr @ er), float(zr @ zr)
        row.update(instrument_denominator=denominator, instrument_residual_ss=zss)
        if denominator == 0 or zss <= 0:
            row["placeholder_reason"] = "singular_instrument"
            return row
        adjustment = (zr @ dy) / denominator
        residuals = dy - er[:, None]*adjustment
        omega = residuals.T @ residuals / T
        row["DH_executed"] = True
        if not np.isfinite(omega).all() or np.linalg.matrix_rank(omega) != 2:
            row["placeholder_reason"] = "residual_covariance_rank_deficient"
            return row
        scale = np.sqrt(np.diag(omega))
        correlation = omega / np.outer(scale, scale)
        np.linalg.cholesky(correlation)
        t = adjustment * abs(denominator) / (np.sqrt(zss)*scale)
        Q = float(t @ np.linalg.solve(correlation, t))
        if not np.isfinite(Q) or Q < 0 or not np.isfinite(t).all():
            row["placeholder_reason"] = "nonfinite_or_negative_statistic"
            return row
        log_p = -Q/2
        p = float(np.exp(log_p))
        row.update(Q=Q, log_p=log_p, p_raw=p, p_for_adjustment=p,
                   adjustment_A=float(adjustment[0]), adjustment_B=float(adjustment[1]),
                   t_A=float(t[0]), t_B=float(t[1]),
                   residual_correlation=float(correlation[0, 1]),
                   covariance_condition=float(np.linalg.cond(correlation)),
                   compute_status="valid",
                   p_zero_origin="exp_underflow" if p == 0 else None)
    except np.linalg.LinAlgError as error:
        row["placeholder_reason"] = str(error)
    return row


def test_pair(task):
    candidate, a, b, gate_a, gate_b = task
    row = dict(candidate, I1_A_status=gate_a["status"], I1_B_status=gate_b["status"])
    if not gate_a["compatible"] or not gate_b["compatible"]:
        row.update(_empty_audit(len(a), 7))
        row.update(compute_status="precheck_placeholder", N_effective=None,
                   placeholder_reason="I1_incompatible")
    else:
        row.update(dh_audit(a, b))
    return row


def global_holm(results, alpha=.05):
    """Keep every frozen candidate, including precheck/numerical placeholders."""
    table = results.copy()
    if table.empty:
        raise ValueError("A nonempty frozen family is required")
    if table.candidate_id.duplicated().any() or not table.M_GLOBAL.eq(len(table)).all():
        raise ValueError("Incomplete or duplicate frozen GLOBAL family")
    valid = table.compute_status.eq("valid")
    if not table.compute_status.isin(
            ["valid", "precheck_placeholder", "numerically_ineligible"]).all():
        raise ValueError("Unexplained terminal status")
    p = table.p_for_adjustment.to_numpy(float)
    if not np.isfinite(p).all() or ((p < 0) | (p > 1)).any():
        raise ValueError("Invalid correction inputs")
    if not table.loc[~valid, "p_for_adjustment"].eq(1.).all():
        raise ValueError("Unavailable candidates must retain p=1")
    reject, adjusted, _, _ = multipletests(p, alpha=alpha, method="holm")
    table["p_GLOBAL_Holm"] = adjusted
    table["reject_GLOBAL_Holm"] = reject
    return table, table.loc[valid & reject].copy()
