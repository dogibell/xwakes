import numpy as np

import xwakes as xw

from scipy.constants import c as clight

import xtrack as xt
p = xt.Particles(p0c=7e12, zeta=np.linspace(-1, 1, 1000))
p.x[p.zeta > 0] += 1e-3
p.y[p.zeta > 0] += 1e-3
p_ref = p.copy()

wake = xw.WakeResonator(
    r=1e8, q=1e7, f_r=1e9,
    # kind=['dipolar_x', 'dipolar_y'],
    kind=xw.Yokoya('circular'),
)
wake.configure_for_tracking(zeta_range=(-1, 1), num_slices=100)

import xfields as xf
xfwake = xf.Wakefield(components=[
        xf.ResonatorWake(
            r_shunt=1e8, q_factor=1e7, frequency=1e9,
            source_exponents=(1, 0), test_exponents=(0, 0),
            kick='px')],
        zeta_range=(-1, 1), num_slices=100)

wake.track(p)
xfwake.track(p_ref)

import matplotlib.pyplot as plt
plt.close('all')
plt.plot(p.zeta, p.px, label='xwakes')
plt.plot(p_ref.zeta, p_ref.px, '--', label='xfields')

plt.legend()

plt.show()