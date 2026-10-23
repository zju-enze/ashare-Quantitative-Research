"""Check moment parameterization without generating a simulated sample."""
import unittest
from unittest.mock import patch
import numpy as np
from scipy.integrate import quad
from scipy.stats import t

from src.dgp_calibration import (moment_multiplier, volatility_coefficients,
                                 pair_matrices, generate_pair)


class MomentTests(unittest.TestCase):
    def test_fractional_moment_against_density_integration(self):
        for nu in (4.5, 6., 7.):
            scale = np.sqrt((nu-2)/nu)
            for a, b in ((.05,.92),(.16,.74),(.3,0.),(0.,.9),(.2,.01)):
                reference = quad(lambda z: 2*(a*z*z+b)**2.05 *
                                 t.pdf(z,nu,scale=scale), 0, np.inf,
                                 epsabs=1e-9, epsrel=1e-9)[0]
                self.assertAlmostEqual(moment_multiplier(a,b,nu),reference,places=8)

    def test_fourth_moment_and_feasible_mapping(self):
        for nu in (4.5,6.,7.):
            for share in (0.,.05,.3,1.):
                a,b=volatility_coefficients(share,1.,nu,.999999)
                self.assertAlmostEqual(moment_multiplier(a,b,nu),.999999,places=10)
                self.assertLess(a+b,1.)
                expected=(a+b)**2+(3*(nu-2)/(nu-4)-1)*a*a
                self.assertAlmostEqual(moment_multiplier(a,b,nu,4),expected,places=10)

    def test_known_cointegration_rank_and_roots(self):
        for phi in (1., .993):
            adjustment, short_run = pair_matrices(.03, phi)
            companion = np.block([[np.eye(2)+adjustment+short_run, -short_run],
                                  [np.eye(2), np.zeros((2,2))]])
            np.testing.assert_allclose(np.sort(np.linalg.eigvals(companion).real),
                                       np.sort([1.,phi,.03,.03]), atol=1e-10)
            self.assertEqual(np.linalg.matrix_rank(adjustment), int(phi < 1))

    def test_two_period_fixed_shock_response(self):
        spec = {'rho':.2, 'phi_alternative':.8, 'initialization_burn_in':0,
                'return_scale':1., 'heavy_tail_specific_nu':3.5,
                'innovation_variance_shares':{'market':.25,'industry':.25,'specific':.5},
                'drivers':{name:{'nu':nu,'alpha':0.,'beta':0.,'omega':1.}
                           for name,nu in [('market',6.),('industry',7.),('specific',4.5)]}}
        fixed = np.zeros((2,4))
        fixed[0,2] = 1/np.sqrt((4.5-2)/4.5)
        impulse = np.sqrt(.96*.5)
        with patch('numpy.random.default_rng') as rng:
            rng.return_value.standard_t.return_value = fixed
            null = generate_pair(spec,2,0)
            alternative = generate_pair(spec,2,0,cointegrated=True)
        np.testing.assert_allclose(null-np.log(100),
                                   [[impulse,0],[1.2*impulse,0]],atol=1e-12)
        np.testing.assert_allclose(alternative-np.log(100),
                                   [[impulse,0],[1.1*impulse,.1*impulse]],atol=1e-12)


if __name__ == '__main__':
    unittest.main()
