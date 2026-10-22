"""NumPy-only tests for the versioned C^-1 K_legacy C boundary."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from harness.native_number_boundary import (
    ADMISSION_SCHEMA, NUMBER_FIELDS, NUMBER_ROWS, NUMBER_UNITS,
    NativeDryNumberKernel, NumberBasisAdmission,
)


class LinearLegacyKernel:
    """Small opaque-kernel stand-in with an independent exact transpose."""
    levels = 3
    dt = 20.0

    def __init__(self):
        self.a = np.eye(12, dtype=np.float64)
        self.a[0, 8] = .03
        self.a[1, 7] = .07
        self.a[8, 1] = .4
        self.a[9, 2] = -.2
        self.a[10, 11] = .1
        self.b = np.zeros((12, 4), dtype=np.float64)
        self.b[:, 0] = np.linspace(.02, .08, 12)
        self.b[8, 2] = .0001
        self.b[9, 3] = .0003
        self.bias = np.zeros((12, self.levels), dtype=np.float64)
        self.bias[7:11] = np.array([[.3], [.7], [1.1], [1.5]])
        self.last_state = None
        self.last_forcing = None
        self.handles = []
        self.fail_output = False

    def forward(self, state, forcing, *, joint=True, record=False):
        self.last_state = state.copy()
        self.last_forcing = forcing.copy()
        out = self.a @ state + self.b @ forcing + self.bias
        h = {"record": bool(record), "closed": False}
        self.handles.append(h)
        if self.fail_output:
            return out[:-1], h
        return out, h

    def jvp(self, handle, ds, df):
        if handle["closed"]:
            raise ValueError("closed fake handle")
        return self.a @ ds + self.b @ df

    def vjp(self, handle, u):
        if handle["closed"]:
            raise ValueError("closed fake handle")
        return self.a.T @ u, self.b.T @ u

    def close(self, handle):
        if handle is not None:
            if handle["closed"]:
                raise ValueError("fake handle double close")
            handle["closed"] = True


class IdentityLegacyKernel(LinearLegacyKernel):
    def __init__(self):
        super().__init__()
        self.a[:] = np.eye(12)
        self.b[:] = 0.
        self.bias[:] = 0.


def admission(*, origin="verified_dry_producer", **updates):
    values = dict(
        schema=ADMISSION_SCHEMA,
        origin=origin,
        source_id="captured-native-number-source-20261022-01",
        source_sha256="1"*64,
        receipt_sha256="2"*64,
        field_units={name: NUMBER_UNITS for name in NUMBER_FIELDS},
    )
    values.update(updates)
    return NumberBasisAdmission(**values)


def input_arrays():
    levels = 3
    state = np.array([
        [280., 282., 284.], [.001, .004, .009], [1e-4, 2e-4, 3e-4],
        [1e-5, 2e-5, 3e-5], [2e-5, 4e-5, 6e-5], [3e-5, 6e-5, 9e-5],
        [5e-5, 7e-5, 9e-5], [80., 110., 130.], [100., 140., 170.],
        [20., 30., 50.], [400., 500., 600.], [1e-8, 2e-8, 3e-8],
    ], dtype=np.float64)
    forcing = np.array([
        [1.1, 1.3, 1.6], [1.02, 1.01, .98], [95000., 80000., 60000.],
        [100., 300., 800.],
    ], dtype=np.float64)
    assert state.shape == (12, levels) and forcing.shape == (4, levels)
    return state, forcing


def test_boundary_forward_is_exact_c_inverse_k_c_and_preserves_forcing():
    raw = LinearLegacyKernel()
    wrapped = NativeDryNumberKernel(raw, admission=admission())
    state, forcing = input_arrays()
    original_state, original_forcing = state.copy(), forcing.copy()
    output, handle = wrapped.forward(state, forcing, record=True)
    rho = forcing[0]
    expected_volume_in = state.copy()
    expected_volume_in[list(NUMBER_ROWS)] *= rho
    expected_volume_out = raw.a @ expected_volume_in + raw.b @ forcing + raw.bias
    expected = expected_volume_out.copy()
    expected[list(NUMBER_ROWS)] /= rho
    np.testing.assert_array_equal(raw.last_state, expected_volume_in)
    np.testing.assert_array_equal(raw.last_forcing, forcing)  # native physical bundle untouched
    np.testing.assert_array_equal(output, expected)
    np.testing.assert_array_equal(state, original_state)  # no in-place rescaling
    np.testing.assert_array_equal(forcing, original_forcing)
    for row in range(12):
        if row not in NUMBER_ROWS:
            np.testing.assert_array_equal(output[row], expected_volume_out[row])
    np.testing.assert_array_equal(handle.dry_input, state)
    np.testing.assert_array_equal(handle.volume_input, expected_volume_in)
    np.testing.assert_array_equal(handle.volume_output, expected_volume_out)
    np.testing.assert_array_equal(handle.forcing, forcing)
    np.testing.assert_array_equal(handle.rho_dry, rho)
    wrapped.close(handle)
    assert raw.handles[0]["closed"]


def test_identity_kernel_cancels_density_boundary_with_nonunit_rho():
    raw = IdentityLegacyKernel()
    wrapped = NativeDryNumberKernel(raw, admission=admission())
    state, forcing = input_arrays()
    before = state.copy()
    output, handle = wrapped.forward(state, forcing, record=True)
    np.testing.assert_allclose(output, before, rtol=2e-16, atol=1e-14)
    assert not np.all(forcing[0] == 1.)
    u = np.ones_like(state)
    gs, gf = wrapped.vjp(handle, u)
    np.testing.assert_allclose(gs, np.ones_like(state), rtol=2e-16, atol=1e-14)
    # Algebraic cancellation is zero; two independent fp64 multiply/divide paths
    # leave a small roundoff residual at this non-unit density.
    np.testing.assert_allclose(gf[0], 0., rtol=0., atol=2e-13)
    wrapped.close(handle)


def test_jvp_vjp_match_full_chain_dot_and_independent_directional_fd():
    raw = LinearLegacyKernel()
    wrapped = NativeDryNumberKernel(
        raw, admission=admission(origin="derived_kernel_volume_coordinate")
    )
    state, forcing = input_arrays()
    output, handle = wrapped.forward(state, forcing, record=True)
    rng = np.random.default_rng(20261022)
    ds = np.ascontiguousarray(rng.normal(size=state.shape)*np.maximum(1., np.abs(state))*1e-3)
    df = np.ascontiguousarray(rng.normal(size=forcing.shape)*np.maximum(1., np.abs(forcing))*1e-4)
    u = np.ascontiguousarray(rng.normal(size=output.shape))

    dy = wrapped.jvp(handle, ds, df)
    gs, gf = wrapped.vjp(handle, u)
    lhs = float(np.sum(dy*u))
    rhs = float(np.sum(gs*ds)+np.sum(gf*df))
    assert np.isclose(lhs, rhs, rtol=2e-13, atol=2e-10)

    eps = 1e-5
    yp, hp = wrapped.forward(state+eps*ds, forcing+eps*df)
    ym, hm = wrapped.forward(state-eps*ds, forcing-eps*df)
    try:
        fd = (yp-ym)/(2*eps)
        scale = np.maximum(1., np.maximum(np.abs(fd), np.abs(dy)))
        assert np.max(np.abs(fd-dy)/scale) < 2e-8
    finally:
        wrapped.close(hp)
        wrapped.close(hm)

    # Forcing DEN receives both K's own physical derivative and C/C^-1 terms.
    volume_seed = u.copy()
    rho = handle.rho_dry
    volume_seed[list(NUMBER_ROWS)] /= rho
    raw_gs, raw_gf = raw.vjp(raw.handles[0], volume_seed)
    expected_entry = np.sum(handle.dry_input[list(NUMBER_ROWS)]*
                            raw_gs[list(NUMBER_ROWS)], axis=0)
    expected_exit = -np.sum(handle.volume_output[list(NUMBER_ROWS)]*
                            u[list(NUMBER_ROWS)], axis=0)/(rho*rho)
    assert np.allclose(gf[0], raw_gf[0]+expected_entry+expected_exit, rtol=1e-14, atol=5e-14)
    assert not np.array_equal(gf[0], raw_gf[0])
    wrapped.close(handle)


def test_admission_refuses_missing_unknown_registry_only_and_incomplete_units():
    raw = LinearLegacyKernel()
    with pytest.raises(TypeError, match="explicit NumberBasisAdmission"):
        NativeDryNumberKernel(raw, admission=None)
    for origin in ("unknown", "legacy_raw", "registry_only"):
        with pytest.raises(ValueError, match="origin"):
            admission(origin=origin)
    with pytest.raises(ValueError, match="schema"):
        admission(schema="kdm6.legacy_raw.v0")
    with pytest.raises(ValueError, match="exactly NN/NC/NI/NR"):
        admission(field_units={"NC": NUMBER_UNITS, "NI": NUMBER_UNITS})
    with pytest.raises(ValueError, match="lowercase 64-hex"):
        admission(receipt_sha256="registry-label-only")

    # A receipt-shaped external value is accepted by protocol, not by class identity.
    @dataclass(frozen=True)
    class ExternalAdmission:
        schema: str
        origin: str
        source_id: str
        source_sha256: str
        receipt_sha256: str
        field_units: dict
    accepted = ExternalAdmission(**admission().__dict__)
    wrapped = NativeDryNumberKernel(raw, admission=accepted)
    assert wrapped.admission.origin == "verified_dry_producer"


def test_invalid_den_or_negative_admitted_count_refuses_before_backend_without_mutation():
    raw = LinearLegacyKernel()
    wrapped = NativeDryNumberKernel(raw, admission=admission())
    state, forcing = input_arrays()
    state_before, forcing_before = state.copy(), forcing.copy()
    bad_forcing = forcing.copy()
    bad_forcing[0, 1] = 0.
    with pytest.raises(ValueError, match="DEN must be positive"):
        wrapped.forward(state, bad_forcing, record=True)
    assert raw.handles == []
    bad_state = state.copy()
    bad_state[9, 0] = -1e-8
    with pytest.raises(ValueError, match="counts must be nonnegative"):
        wrapped.forward(bad_state, forcing, record=True)
    assert raw.handles == []
    np.testing.assert_array_equal(state, state_before)
    np.testing.assert_array_equal(forcing, forcing_before)


def test_record_ownership_value_only_refusal_and_failed_output_cleanup():
    raw = LinearLegacyKernel()
    wrapped = NativeDryNumberKernel(raw, admission=admission())
    state, forcing = input_arrays()
    _, value_handle = wrapped.forward(state, forcing, record=False)
    with pytest.raises(ValueError, match="record=True"):
        wrapped.jvp(value_handle, np.zeros_like(state), np.zeros_like(forcing))
    wrapped.close(value_handle)
    assert raw.handles[-1]["closed"]

    other = NativeDryNumberKernel(LinearLegacyKernel(), admission=admission())
    _, recorded = wrapped.forward(state, forcing, record=True)
    with pytest.raises(TypeError, match="not created"):
        other.jvp(recorded, np.zeros_like(state), np.zeros_like(forcing))
    wrapped.close(recorded)
    with pytest.raises(ValueError, match="closed"):
        wrapped.vjp(recorded, np.zeros_like(state))

    # A number-only entry point lacks independent forcing partials and cannot
    # be represented as a full recorded boundary derivative.
    calls = len(raw.handles)
    with pytest.raises(ValueError, match="requires the full"):
        wrapped.forward(state, forcing, joint=False, record=True)
    assert len(raw.handles) == calls

    raw.fail_output = True
    with pytest.raises(ValueError, match="legacy kernel output"):
        wrapped.forward(state, forcing, record=True)
    assert raw.handles[-1]["closed"]
