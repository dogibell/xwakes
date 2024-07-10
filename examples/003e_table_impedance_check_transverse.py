import numpy as np
import pandas as pd
import xwakes as xw
import xobjects as xo

from scipy.constants import c as clight
from scipy.interpolate import interp1d

beta0 = 0.1
plane = 'y'
wake_type = 'dipolar'

wake_data = pd.read_csv(
    './comparison_rw_for_xwakes/WydipWLHC_1layers10.00mm_precise.dat',
    skiprows=1, names=['z', 'wydip'], sep=' ')
imp_data = pd.read_csv(
    './comparison_rw_for_xwakes/ZydipWLHC_1layers10.00mm_precise.dat',
    skiprows=1, names=['f', 'ReZydip', 'ImZydip'], sep=' '
)

Z_first_quadrant = interp1d(imp_data['f'], imp_data['ReZydip'] + 1j * imp_data['ImZydip'])
def Z_function(omega):
    isscalar = np.isscalar(omega)
    if isscalar:
        omega = np.array([omega])
    mask_zero = np.abs(omega) < imp_data['f'][0]
    if mask_zero.any():
        raise ValueError('Frequency too low')
    mask_positive = omega > 0
    mask_negative = omega < 0
    out = np.zeros_like(omega, dtype=complex)
    out[mask_positive] = Z_first_quadrant(omega[mask_positive])
    out[mask_negative] = Z_first_quadrant(-omega[mask_negative])
    out[mask_negative] = -np.conj(out[mask_negative])
    return out[0] if isscalar else out

table = pd.DataFrame(
    {'time': wake_data['z'].values / clight, 'dipolar_y': wake_data['wydip'].values}
)

wake = xw.WakeFromTable(table=table)


assert len(wake.components) == 1
assert wake.components[0].plane == plane
assert wake.components[0].source_exponents == {
    'dipolar_x': (1, 0), 'dipolar_y': (0, 1),
    'quadrupolar_x': (0, 0), 'quadrupolar_y': (0, 0)}[f'{wake_type}_{plane}']
assert wake.components[0].test_exponents == {
    'dipolar_x': (0, 0), 'dipolar_y': (0, 0),
    'quadrupolar_x': (1, 0), 'quadrupolar_y': (0, 1)}[f'{wake_type}_{plane}']

z = np.linspace(-100, 100, 10_000_000)
t = np.linspace(-100/beta0/clight, 100/beta0/clight, 10_000_000)

w_vs_zeta = wake.components[0].function_vs_zeta(z, beta0=beta0, dzeta=1e-20)
w_vs_t = wake.components[0].function_vs_t(t, beta0=beta0, dt=1e-20)

# # Assert that the function is positive at close to zero from the right
# assert wake.components[0].function_vs_t(1e-10, beta0=beta0, dt=1e-20) > 0
# assert wake.components[0].function_vs_t(-1e-10, beta0=beta0, dt=1e-20) == 0

# # Zeta has opposite sign compared to t
# assert wake.components[0].function_vs_zeta(-1e-3, beta0=beta0, dzeta=1e-20) > 0
# assert wake.components[0].function_vs_zeta(+1e-3, beta0=beta0, dzeta=1e-20) == 0

omega = np.linspace(-10e9, 10e9, 50)

Z_from_zeta = omega * (1 + 1j)
Z_from_t = omega * (1 + 1j)
dz = z[1] - z[0]
dt = t[1] - t[0]
for ii, oo in enumerate(omega):
    print(ii, end='\r', flush=True)
    Z_from_zeta[ii] = 1j/beta0/clight * np.sum(w_vs_zeta
                * np.exp(1j * oo * z / beta0 / clight)) * dz
    Z_from_t[ii] = 1j * np.sum(
                w_vs_t * np.exp(-1j * oo * t)) * dt

Z_analytical = Z_function(omega/2/np.pi)

# f_test_sign = 1e9
# xo.assert_allclose(wake.components[0].impedance(-f_test_sign).real,
#                    -wake.components[0].impedance(f_test_sign).real,
#                    atol=0, rtol=1e-8)
# xo.assert_allclose(wake.components[0].impedance(-f_test_sign).imag,
#                    wake.components[0].impedance(f_test_sign).imag,
#                    atol=0, rtol=1e-8)

# xo.assert_allclose(
#     Z_from_zeta, Z_analytical, rtol=0, atol=1e-4 * np.max(np.abs(Z_analytical)))
# xo.assert_allclose(
#     Z_from_t, Z_analytical, rtol=0, atol=1e-4 * np.max(np.abs(Z_analytical)))

import matplotlib.pyplot as plt
plt.close('all')
plt.figure(1)
spre = plt.subplot(211)
plt.plot(omega, Z_from_zeta.real, label='Re Zx from zeta')
plt.plot(omega, Z_from_t.real, '--', label='Re Zx from t')
plt.plot(omega, Z_analytical.real, '-.', label='Re Zx from xwakes')
plt.legend()

spim = plt.subplot(212, sharex=spre)
plt.plot(omega, Z_from_zeta.imag, label='Im Zx from zeta')
plt.plot(omega, Z_from_t.imag, '--', label='Im Zx from t')
plt.plot(omega, Z_analytical.imag, '-.', label='Im Zx from xwakes')

plt.figure(2)
plt.plot(z, w_vs_zeta)
plt.xlabel('z [m]')
plt.ylabel('Wx(z)')

plt.figure(3)
plt.plot(t, w_vs_t)
plt.xlabel('t [s]')
plt.ylabel('Wx(t)')



plt.show()


