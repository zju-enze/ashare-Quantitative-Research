"""Market-only correction for unidentified recursive prefixes outside the used sample.

The frozen kernel remains the primary path. Only its prefix-rank failures are
re-evaluated; valid calibration/market rows retain the original computation.
"""
import numpy as np
from . import engine_dh as frozen
from .engine_dh import _empty_audit


def _required_prefix_errors(a, b, lags):
    y = np.column_stack((a, b)).astype(float)
    y -= y[0]
    centered = y - np.cumsum(y, axis=0) / np.arange(1, len(y)+1)[:, None]
    aa, bb = centered.T
    denominator = np.cumsum(bb*bb)
    if np.any(denominator[max(2, lags):-1] == 0):
        raise np.linalg.LinAlgError("recursive_regression_rank_deficient")
    errors = np.full(len(y), np.nan)
    errors[:2] = 0.
    identified = (np.arange(len(y)) >= 2) & (denominator != 0)
    errors[identified] = (aa[identified] - bb[identified]
        * np.cumsum(aa*bb)[identified] / denominator[identified])
    return errors


def _audit_used_prefix(a, b, lags=7):
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
        errors = _required_prefix_errors(a, b, lags)
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
    row = frozen.test_pair(task)
    row["prefix_guard_corrected"] = False
    if (row["compute_status"] == "numerically_ineligible"
            and row["placeholder_reason"] == "recursive_regression_rank_deficient"):
        row.update(_audit_used_prefix(task[1], task[2], lags=7))
        row["prefix_guard_corrected"] = row["compute_status"] == "valid"
    return row
