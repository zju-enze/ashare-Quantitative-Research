"""Moment calculations for the empirically calibrated AR-GARCH drivers."""
from functools import lru_cache
import math

import numpy as np

from scipy.special import betaln, hyp2f1


@lru_cache(maxsize=16)
def _moment_constants(nu, order):
    power = order / 2
    remaining = nu / 2 - power
    ratio = math.exp(betaln(.5, remaining) - betaln(.5, nu / 2))
    return power, remaining, ratio


def moment_multiplier(alpha, beta, nu, order=4.1):
    """E[(alpha*z**2+beta)**(order/2)] for a unit-variance t innovation."""
    if alpha == 0:
        return beta ** (order / 2)
    if nu <= order:
        return math.inf
    power, remaining, ratio = _moment_constants(float(nu), float(order))
    a = alpha * (nu - 2)
    # Factoring the larger endpoint keeps the hypergeometric argument in [0,1].
    if a <= beta:
        return float(ratio * beta**power *
                     hyp2f1(-power, .5, .5 + remaining, 1 - a / beta))
    return float(ratio * a**power *
                 hyp2f1(-power, remaining, .5 + remaining, 1 - beta / a))


def volatility_coefficients(share, fraction, nu, moment_limit=None):
    """Map box-constrained coordinates into the variance/moment feasible region."""
    maximum = 1.
    if moment_limit is not None:
        maximum = (moment_limit / moment_multiplier(share, 1 - share, nu))**(2 / 4.1)
    persistence = fraction * maximum
    return persistence * share, persistence * (1 - share)


def pair_matrices(rho, phi):
    """VECM matrices with companion roots 1, phi, rho, rho."""
    spread_projection = np.array([[.5, -.5], [-.5, .5]])
    common_projection = np.eye(2) - spread_projection
    adjustment = -(1 - phi) * (1 - rho) * spread_projection
    short_run = rho * common_projection + phi * rho * spread_projection
    return adjustment, short_run


def generate_pair(spec, n_obs, seed, *, cointegrated=False, heavy_tail=False):
    """Draw log prices from the fitted pair DGP; callers choose when to simulate."""
    rho = spec['rho']
    phi = spec['phi_alternative'] if cointegrated else 1.
    adjustment, short_run = pair_matrices(rho, phi)
    drivers = [spec['drivers'][name] for name in
               ('market', 'industry', 'specific', 'specific')]
    nu = np.array([driver['nu'] for driver in drivers], dtype=float)
    if heavy_tail:
        nu[2:] = spec['heavy_tail_specific_nu']
    alpha = np.array([driver['alpha'] for driver in drivers])
    beta = np.array([driver['beta'] for driver in drivers])
    omega = np.array([driver['omega'] for driver in drivers])
    weights = np.sqrt([spec['innovation_variance_shares'][name] for name in
                       ('market', 'industry', 'specific')])
    burn = spec['initialization_burn_in']
    rng = np.random.default_rng(seed)
    z = rng.standard_t(nu, size=(burn + n_obs, 4)) * np.sqrt((nu - 2) / nu)
    h = np.ones(4)
    level, difference = np.zeros(2), np.zeros(2)
    values = np.empty((n_obs, 2))
    for t, shock in enumerate(z):
        epsilon = np.sqrt(h) * shock
        common = weights[0] * epsilon[0] + weights[1] * epsilon[1]
        innovation = np.sqrt(1 - rho*rho) * (common + weights[2] * epsilon[2:])
        difference = adjustment @ level + short_run @ difference + innovation
        level = level + difference
        h = omega + alpha * epsilon**2 + beta * h
        if t >= burn:
            values[t-burn] = level
    return np.log(100.) + spec['return_scale'] * values
