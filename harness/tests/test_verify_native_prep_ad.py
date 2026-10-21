"""Value-only mechanics tests for the prep/kernel/finish chain.

The fakes here prove adapter wiring and verifier refusal behavior only; they
are not a native-value or scientific validation of the prep equations.
"""
from __future__ import annotations

import sys
from types import SimpleNamespace

import numpy as np
import pytest

import harness.verify_native_prep_ad as verify


class _FakePrep:
    """Linear map with distinct coefficients for each prep/forcing output."""
    def __init__(self, levels=2, *, bad_shape=False):
        self.levels = levels
        self.bad_shape = bad_shape

    def _unpack(self, x):
        return verify.unpack_state(x, self.levels)

    def forward(self, x):
        thm, qv, mu, ph = self._unpack(x)
        out = np.vstack((
            2.0*thm + 3.0*qv,
            np.full(self.levels, 4.0*mu),
            5.0*ph[:-1],
            6.0*ph[1:],
            7.0*(ph[1:]-ph[:-1]),
        ))
        return out[:-1] if self.bad_shape else out

    def jvp(self, x, dx):
        dthm, dqv, dmu, dph = self._unpack(dx)
        return np.vstack((
            2.0*dthm + 3.0*dqv,
            np.full(self.levels, 4.0*dmu),
            5.0*dph[:-1],
            6.0*dph[1:],
            7.0*(dph[1:]-dph[:-1]),
        ))

    def vjp(self, x, cotangent):
        u = np.asarray(cotangent)
        levels = self.levels
        grad_thm = 2.0*u[0]
        grad_qv = 3.0*u[0]
        grad_mu = np.asarray(4.0*np.sum(u[1:2]), dtype=np.float64).reshape(())
        grad_ph = np.zeros(levels+1, dtype=np.float64)
        grad_ph[:-1] += 5.0*u[2]
        grad_ph[1:] += 6.0*u[3]
        grad_ph[:-1] -= 7.0*u[4]
        grad_ph[1:] += 7.0*u[4]
        return verify.pack_state((grad_thm, grad_qv, grad_mu, grad_ph))


class _FakeFinish:
    def __init__(self, levels=2, *, bad_rest=False):
        self.levels = levels
        self.bad_rest = bad_rest
        self.forward_calls = 0
        self.seen_state = None
        self.seen_forcing = None
        self.gs = np.zeros((12, levels), dtype=np.float64)
        self.gf = np.zeros((4, levels), dtype=np.float64)

    def _check(self, value, rows, label):
        if not isinstance(value, np.ndarray) or value.dtype != np.float64:
            raise TypeError(f"{label} must be binary64")
        if value.shape != (rows, self.levels):
            raise ValueError(f"{label} shape mismatch")
        if not np.isfinite(value).all():
            raise ValueError(f"{label} must be finite")

    def forward(self, state, forcing, *, record=False):
        self.forward_calls += 1
        self._check(state, 12, "kernel state")
        self._check(forcing, 4, "kernel forcing")
        self.seen_state = state.copy()
        self.seen_forcing = forcing.copy()
        handle = object() if record else None
        return np.zeros((5, self.levels), dtype=np.float64), handle, state[:3].copy()

    def jvp(self, state, after, handle, ds, df):
        self._check(ds, 12, "state direction")
        self._check(df, 4, "forcing direction")
        weights_s = np.arange(1, 13, dtype=np.float64)[:, None]
        weights_f = np.array([13., 17., 19., 23.])[:, None]
        scalar = (weights_s*ds).sum(axis=0) + (weights_f*df).sum(axis=0)
        return np.tile(scalar, (5, 1))

    def vjp(self, state, after, handle, cotangent):
        return self.gs.copy(), self.gf.copy(), np.zeros((3, self.levels), dtype=np.float64)


def _native_x(levels=2):
    # pack_state layout: L theta_m, L QV, scalar MU, L+1 PH.
    return np.array([280., 281., .01, .02, 50000., 10., 20., 30.], dtype=np.float64)


def test_adapter_preserves_qv_identity_and_all_four_forcing_rows():
    levels = 2
    x = _native_x(levels)
    prep = _FakePrep(levels)
    finish = _FakeFinish(levels)
    adapter = verify.PrepKernelFinish(prep, finish)
    rest = np.arange(20, dtype=np.float64).reshape(10, levels)

    value, record = adapter.forward(x, rest, record=True)
    expected_g = prep.forward(x)
    assert value.shape == (5, levels)
    np.testing.assert_array_equal(finish.seen_state[0], expected_g[0])
    np.testing.assert_array_equal(finish.seen_state[1], [.01, .02])
    np.testing.assert_array_equal(finish.seen_state[2:], rest)
    # The K ABI order is DEN, PII, P, DELZ; all rows have distinct sources.
    np.testing.assert_array_equal(finish.seen_forcing, expected_g[1:])

    # Inject independent K cotangents so the prep pullback sees all four
    # forcing slots and QV's separate identity path is exercised explicitly.
    finish.gs[0] = [2., 3.]
    finish.gs[1] = [5., 7.]
    finish.gs[2:] = np.arange(20, dtype=np.float64).reshape(10, levels) + 1.
    finish.gf[:] = np.array([[11., 12.], [13., 14.], [17., 18.], [19., 20.]])
    gx, grest = adapter.vjp(record, np.ones((5, levels), dtype=np.float64))
    prep_seed = np.vstack((finish.gs[0], finish.gf))
    expected_gx = prep.vjp(x, prep_seed)
    expected_gx[levels:2*levels] += finish.gs[1]
    np.testing.assert_array_equal(gx, expected_gx)
    np.testing.assert_array_equal(grest, finish.gs[2:])

    # Exercise full adapter JVP using four independently nonzero prep rows.
    dx = np.array([.1, -.2, .003, -.004, 2., 1., 2., -1.], dtype=np.float64)
    drest = np.arange(20, dtype=np.float64).reshape(10, levels)/10.
    tangent = adapter.jvp(record, dx, drest)
    dg = prep.jvp(x, dx)
    ds = np.vstack((dg[0], verify.unpack_state(dx, levels)[1], drest))
    weights_s = np.arange(1, 13, dtype=np.float64)[:, None]
    weights_f = np.array([13., 17., 19., 23.])[:, None]
    expected = np.tile((weights_s*ds).sum(axis=0) + (weights_f*dg[1:]).sum(axis=0), (5, 1))
    np.testing.assert_array_equal(tangent, expected)


def test_adapter_refuses_malformed_metadata_before_kernel_forward():
    x = _native_x()
    rest = np.zeros((10, 2), dtype=np.float64)
    finish = _FakeFinish()
    with pytest.raises(ValueError, match="remaining kernel state shape"):
        verify.PrepKernelFinish(_FakePrep(), finish).forward(x, rest[:-1])
    assert finish.forward_calls == 0

    bad_prep_finish = _FakeFinish()
    with pytest.raises(ValueError, match="prep output shape mismatch"):
        verify.PrepKernelFinish(_FakePrep(bad_shape=True), bad_prep_finish).forward(x, rest)
    assert bad_prep_finish.forward_calls == 0

    with pytest.raises(ValueError, match="native state must contain"):
        verify.PrepKernelFinish(_FakePrep(), _FakeFinish()).forward(x[:-1], rest)


def test_adapter_refuses_nonfinite_or_wrong_dtype_prep_output_before_kernel():
    class BadOutput(_FakePrep):
        def __init__(self, *, dtype=None, nonfinite=False):
            super().__init__()
            self.dtype, self.nonfinite = dtype, nonfinite

        def forward(self, x):
            result = super().forward(x)
            if self.dtype is not None:
                return result.astype(self.dtype)
            if self.nonfinite:
                result[2, 0] = np.nan
            return result

    x, rest = _native_x(), np.zeros((10, 2), dtype=np.float64)
    for prep, error in ((BadOutput(dtype=np.float32), "binary64"),
                        (BadOutput(nonfinite=True), "finite")):
        finish = _FakeFinish()
        with pytest.raises((ValueError, TypeError), match=error):
            verify.PrepKernelFinish(prep, finish).forward(x, rest)
        assert finish.forward_calls == 0


def test_verifier_rejects_output_alias_before_hash_or_input_reads(tmp_path, monkeypatch):
    trace = tmp_path/"trace.hex"
    trace.write_bytes(b"leave this input untouched")
    args = SimpleNamespace(trace=trace, namelist=tmp_path/"nml",
                           checkpoint=tmp_path/"cp", library=tmp_path/"lib",
                           output=trace, step=2, i=3, j=4, levels=39, xland=2.0)

    def should_not_read(*args, **kwargs):
        raise AssertionError("input hashing/loading started before output-alias refusal")

    monkeypatch.setattr(verify, "sha", should_not_read)
    fake_replay = SimpleNamespace(load_native_prep_case=should_not_read)
    monkeypatch.setitem(sys.modules, "harness.native_prep_replay", fake_replay)
    before = trace.read_bytes()
    with pytest.raises(ValueError, match="output must be new and distinct"):
        verify.verify(args)
    assert trace.read_bytes() == before


def test_check_stage_rejects_one_bad_output_field_even_when_dot_ignores_it():
    x0 = np.array([0.], dtype=np.float64)
    x1 = np.array([0.], dtype=np.float64)
    v = np.array([1.], dtype=np.float64)
    zero = np.array([0.], dtype=np.float64)

    def value(a, b):
        return np.vstack((a, a)), np.empty(0, dtype=np.int64)

    def jvp(da, db):
        return np.vstack((da, 1000.*da))

    reports = verify.check_stage(value, jvp, (v, zero), (x0, x1),
                                 {"theta": (v, zero)}, np.array([[1.], [0.]]),
                                 ("small", "bad"), np.ones((2, 1)))
    assert not reports["passed"]
    assert reports["directions"]["theta"]["best_max_tolerance_ratio"] > 1.
    assert reports["directions"]["theta"]["trials"]


@pytest.mark.parametrize("ineligible", ["branch", "domain"])
def test_check_stage_fails_closed_when_no_fd_trial_is_eligible(ineligible):
    x0 = np.array([0.], dtype=np.float64)
    x1 = np.array([0.], dtype=np.float64)
    v = np.array([1.], dtype=np.float64)
    zero = np.array([0.], dtype=np.float64)

    def value(a, b):
        if ineligible == "domain" and a[0] < 0.:
            raise ValueError("outside prep domain")
        signature = np.array([int(a[0] > 0.)], dtype=np.int64) if ineligible == "branch" else np.empty(0, dtype=np.int64)
        return np.vstack((a,)), signature

    reports = verify.check_stage(value, lambda da, db: np.vstack((da,)),
                                 (v, zero), (x0, x1), {"theta": (v, zero)},
                                 np.ones((1, 1)), ("out",), np.ones((1, 1)))
    direction = reports["directions"]["theta"]
    assert not reports["passed"]
    assert direction["best_epsilon"] is None
    assert all(not trial["eligible"] for trial in direction["trials"])
