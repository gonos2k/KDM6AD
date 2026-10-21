"""Synthetic composition checks, executed in the mandatory Torch Oracle CI."""

from pathlib import Path
import sys

import numpy as np
import pytest

# Oracle CI runs from oracle/. The composition intentionally imports the
# public harness adapter and its opaque-kernel protocol from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from harness.native_microphysics_obs import MicrophysicsObservationState
from harness.verify_native_finish_ad import KernelFinish
from harness.verify_native_prep_ad import Prep, pack_state
from oracle.kdm6.native_finish import FinishConfig, ZeroOutConfig


class LinearKernel:
    """Small exact state/forcing map with a hand-written transpose."""
    def __init__(self, levels):
        self.levels = levels
        self.a = np.eye(12)
        self.a[0, 1] = .02
        self.a[1, 0] = 1e-5
        for row in range(2, 12):
            self.a[row, 0] = 1e-6
            self.a[row, (row+1) % 12] += 1e-3
        self.b = np.zeros((12, 4))
        self.b[:, 0] = 1e-6
        self.b[:, 1] = 1e-5
        self.b[:, 2] = 1e-8
        self.b[:, 3] = 1e-9
        self.bias = np.zeros((12, levels))

    def forward(self, state, forcing, *, record=False):
        handle = (state.copy(), forcing.copy()) if record else None
        after = self.a @ state + self.b @ forcing
        after[0] += .02
        after[1] += .001
        after += self.bias
        return after, handle

    def jvp(self, handle, ds, df):
        return self.a @ ds + self.b @ df

    def vjp(self, handle, u):
        return self.a.T @ u, self.b.T @ u

    def close(self, handle):
        pass


def make_adapter(threshold=1e-3):
    levels = 3
    geometry = {
        "phb": np.zeros(levels+1),
        "c3h": np.array([.85, .55, .25]),
        "c4h": np.zeros(levels),
        "c3f": np.array([1., .7, .4, .1]),
        "c4f": np.zeros(levels+1),
    }
    config = dict(ptop=5000., rd=287., p0=100000., t0=300.,
                  alpha=1.6083624362945557, gamma=1.3999999761581421,
                  kappa=.2857142984867096, g=9.8100004196167)
    prep = Prep(levels, geometry, config)
    kernel = LinearKernel(levels)
    finish = KernelFinish(kernel, FinishConfig(dt=20., alpha=config["alpha"], t0=300.,
                                               mp_tend_lim=3.),
                          ZeroOutConfig(mode=2, threshold=threshold))
    return MicrophysicsObservationState(prep, finish), kernel


def inputs():
    levels = 3
    x = pack_state((np.array([-20., -15., -10.]), np.array([.001, .004, .01]),
                    np.array(50000.), np.array([0., 50000., 110000., 180000.])))
    # Rest rows: QC, QR, QI, QS, QG, NN, NC, NI, NR, BG.
    rest = np.array([
        [2e-3, 3e-3, 4e-3], [5e-4, 1.5e-3, 7e-4], [2e-3, 6e-4, 4e-3],
        [1e-4, 2e-3, 1e-4], [2e-3, 3e-3, 2e-3],
        [1e5, 2e5, 3e5], [2e5, 3e5, 4e5], [3e5, 4e5, 5e5],
        [4e5, 5e5, 6e5], [5e5, 6e5, 7e5],
    ], dtype=np.float64)
    assert rest.shape == (10, levels)
    return x, rest


def test_composed_forward_cleanup_post_eos_jvp_vjp_and_fd():
    adapter, _ = make_adapter()
    x, rest = inputs()
    y, record = adapter.forward(x, rest, record=True)
    try:
        levels = adapter.levels
        assert y.shape == (10*levels+1,)
        assert np.all(np.isfinite(y))
        # QI is retained; QS is below threshold and zeroed before finish/observation.
        qv = y[levels:2*levels]
        qc, qi, qs = y[5*levels+1:6*levels+1], y[6*levels+1:7*levels+1], y[7*levels+1:8*levels+1]
        assert np.all(qv > 0.) and np.all(qc > 0.) and np.all(qi > 0.)
        assert qs[0] == 0. and qs[2] == 0.
        # NC and NI are number fields: this cleanup stage passes them through unchanged.
        assert np.array_equal(y[8*levels+1:9*levels+1], record.raw_after[8])
        assert np.array_equal(y[9*levels+1:10*levels+1], record.raw_after[9])

        rng = np.random.default_rng(817)
        dx = np.ascontiguousarray(rng.normal(size=x.shape)*np.array([.1]*levels+[1e-4]*levels+[1.]+[1.]*4))
        dr = np.ascontiguousarray(rng.normal(size=rest.shape)*np.maximum(np.abs(rest), 1e-4)*1e-3)
        uy = np.ascontiguousarray(rng.normal(size=y.shape))
        dy = adapter.jvp(record, dx, dr)
        gx, gr = adapter.vjp(record, uy)
        lhs = float(dy @ uy)
        rhs = float(gx @ dx + np.sum(gr*dr))
        assert np.isclose(lhs, rhs, rtol=2e-10, atol=2e-9)

        eps = 2e-5
        yp, rp = adapter.forward(x+eps*dx, rest+eps*dr)
        ym, rm = adapter.forward(x-eps*dx, rest-eps*dr)
        try:
            assert np.array_equal(adapter.branch_signature(rp), adapter.branch_signature(record))
            assert np.array_equal(adapter.branch_signature(rm), adapter.branch_signature(record))
            fd = (yp-ym)/(2*eps)
            scale = np.maximum(1., np.maximum(np.abs(fd), np.abs(dy)))
            assert np.max(np.abs(fd-dy)/scale) < 2e-5
        finally:
            adapter.close(rp)
            adapter.close(rm)
    finally:
        adapter.close(record)


def test_qi_qs_cleanup_threshold_tie_is_refused_for_derivatives():
    adapter, kernel = make_adapter(threshold=1e-3)
    x, rest = inputs()
    _, initial = adapter.forward(x, rest, record=True)
    tie_bias = 1e-3-initial.raw_after[4, 0]
    adapter.close(initial)
    kernel.bias[4, 0] = tie_bias
    y, record = adapter.forward(x, rest, record=True)
    try:
        assert record.raw_after[4, 0] == 1e-3  # QI exact tie in raw K state.
        with pytest.raises(ValueError, match="discontinuity tie"):
            adapter.jvp(record, np.zeros_like(x), np.zeros_like(rest))
        signature = adapter.branch_signature(record)
        assert signature.shape == (7, adapter.levels)
        assert signature[4, 0] == 2
    finally:
        adapter.close(record)

