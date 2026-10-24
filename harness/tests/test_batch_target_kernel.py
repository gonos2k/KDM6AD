from dataclasses import dataclass

import numpy as np
import pytest

from harness.batch_target_kernel import BatchTargetKernel
from harness.native_number_boundary import (
    ADMISSION_SCHEMA,
    NUMBER_FIELDS,
    NUMBER_UNITS,
    NativeDryNumberKernel,
    NumberBasisAdmission,
)


@dataclass
class AffineHandle:
    recorded: bool
    closed: bool = False


class AffineBatch:
    """Small dense full-batch map with deliberate cross-column coupling."""

    def __init__(self, batch, levels):
        self.B, self.L = batch, levels
        nin = (12 + 4) * batch * levels
        nout = 12 * batch * levels
        rng = np.random.default_rng(81)
        self.matrix = rng.normal(size=(nout, nin)) / np.sqrt(nin)
        self.bias = rng.normal(size=nout)
        self.close_calls = 0

    def _flatten(self, state, forcing):
        return np.concatenate((state.reshape(-1), forcing.reshape(-1)))

    def forward(self, state, forcing, *, record=False):
        self.last_inputs = (state.copy(), forcing.copy())
        value = self.matrix @ self._flatten(state, forcing) + self.bias
        return value.reshape(12, self.B, self.L), AffineHandle(record)

    def jvp(self, handle, dstate, dforcing):
        assert handle.recorded and not handle.closed
        return (self.matrix @ self._flatten(dstate, dforcing)).reshape(
            12, self.B, self.L
        )

    def vjp(self, handle, cotangent):
        assert handle.recorded and not handle.closed
        grad = self.matrix.T @ cotangent.reshape(-1)
        state_size = 12 * self.B * self.L
        return (
            grad[:state_size].reshape(12, self.B, self.L),
            grad[state_size:].reshape(4, self.B, self.L),
        )

    def close(self, handle):
        if not handle.closed:
            handle.closed = True
            self.close_calls += 1


def test_selected_adapter_is_exact_projection_of_cross_coupled_batch_map():
    batch, levels, target = 3, 2, 1
    backend = AffineBatch(batch, levels)
    state = (
        np.arange(12 * batch * levels, dtype=np.float64).reshape(12, batch, levels) / 17
    )
    forcing = (1 + np.arange(4 * batch * levels, dtype=np.float64)).reshape(
        4, batch, levels
    ) / 9
    baseline_state, baseline_forcing = state.copy(), forcing.copy()
    adapter = BatchTargetKernel(backend, state, forcing, target, dt=20.0)
    state_target = state[:, target].copy() + 0.2
    forcing_target = forcing[:, target].copy() - 0.03

    full_state, full_forcing = state.copy(), forcing.copy()
    full_state[:, target], full_forcing[:, target] = state_target, forcing_target
    expected = (
        backend.matrix @ backend._flatten(full_state, full_forcing) + backend.bias
    ).reshape(12, batch, levels)[:, target]
    value, handle = adapter.forward(state_target, forcing_target, record=True)
    np.testing.assert_allclose(value, expected, rtol=0, atol=2e-15)

    # The map has real cross-column terms: selected output depends on the
    # fixed background, and target perturbations can affect non-target output.
    out_index = (2 * batch + target) * levels + 1
    state_offset = (5 * batch + 0) * levels + 0
    assert backend.matrix[out_index, state_offset] != 0.0

    ds = np.zeros((12, levels), dtype=np.float64)
    df = np.zeros((4, levels), dtype=np.float64)
    ds[4] = [0.3, -0.2]
    df[3] = [0.05, -0.04]
    full_ds = np.zeros_like(state)
    full_df = np.zeros_like(forcing)
    full_ds[:, target], full_df[:, target] = ds, df
    expected_jvp = (backend.matrix @ backend._flatten(full_ds, full_df)).reshape(
        12, batch, levels
    )[:, target]
    tangent = adapter.jvp(handle, ds, df)
    np.testing.assert_allclose(tangent, expected_jvp, rtol=0, atol=2e-15)
    full_tangent = (backend.matrix @ backend._flatten(full_ds, full_df)).reshape(
        12, batch, levels
    )
    assert np.any(full_tangent[:, [0, 2], :] != 0.0)

    u = np.zeros((12, levels), dtype=np.float64)
    u[3] = [0.6, -0.1]
    full_u = np.zeros_like(state)
    full_u[:, target] = u
    full_gradient = backend.matrix.T @ full_u.reshape(-1)
    state_size = 12 * batch * levels
    full_gs = full_gradient[:state_size].reshape(12, batch, levels)
    full_gf = full_gradient[state_size:].reshape(4, batch, levels)
    gs, gf = adapter.vjp(handle, u)
    np.testing.assert_allclose(gs, full_gs[:, target], rtol=0, atol=2e-15)
    np.testing.assert_allclose(gf, full_gf[:, target], rtol=0, atol=2e-15)
    assert abs(np.sum(u * tangent) - np.sum(gs * ds) - np.sum(gf * df)) < 1e-12

    eps = 1e-5
    plus = adapter.forward(state_target + eps * ds, forcing_target + eps * df)[0]
    minus = adapter.forward(state_target - eps * ds, forcing_target - eps * df)[0]
    np.testing.assert_allclose(
        (plus - minus) / (2 * eps), tangent, rtol=1e-9, atol=1e-10
    )
    adapter.close(handle)
    assert backend.close_calls == 1
    np.testing.assert_array_equal(state, baseline_state)
    np.testing.assert_array_equal(forcing, baseline_forcing)


def test_trials_are_independent_and_frozen_baseline_is_not_exposed_mutably():
    backend = AffineBatch(2, 3)
    state = np.ones((12, 2, 3), dtype=np.float64)
    forcing = np.full((4, 2, 3), 2.0, dtype=np.float64)
    adapter = BatchTargetKernel(backend, state, forcing, 0)
    base_y = adapter.forward(state[:, 0], forcing[:, 0])[0]
    trial = state[:, 0].copy()
    trial[1, 2] += 8.0
    adapter.forward(trial, forcing[:, 0])
    repeat = adapter.forward(state[:, 0], forcing[:, 0])[0]
    np.testing.assert_array_equal(base_y, repeat)
    np.testing.assert_array_equal(adapter.baseline_state, state)
    np.testing.assert_array_equal(adapter.baseline_forcing, forcing)
    with pytest.raises(ValueError):
        adapter.baseline_state[0, 0, 0] = 100.0
    with pytest.raises(ValueError):
        adapter.baseline_forcing[0, 0, 0] = 100.0
    np.testing.assert_array_equal(state, np.ones_like(state))
    np.testing.assert_array_equal(forcing, np.full_like(forcing, 2.0))


def test_handle_owner_recording_staleness_and_idempotent_close():
    state = np.zeros((12, 2, 4), dtype=np.float64)
    forcing = np.ones((4, 2, 4), dtype=np.float64)
    first = BatchTargetKernel(AffineBatch(2, 4), state, forcing, 0)
    second = BatchTargetKernel(AffineBatch(2, 4), state, forcing, 0)
    _, recorded = first.forward(state[:, 0], forcing[:, 0], record=True)
    with pytest.raises(TypeError, match="not created"):
        second.jvp(recorded, np.zeros((12, 4)), np.zeros((4, 4)))
    _, value_only = first.forward(state[:, 0], forcing[:, 0], record=False)
    with pytest.raises(ValueError, match="record=True"):
        first.vjp(value_only, np.zeros((12, 4)))
    first.close(recorded)
    first.close(recorded)
    with pytest.raises(ValueError, match="closed"):
        first.jvp(recorded, np.zeros((12, 4)), np.zeros((4, 4)))
    with pytest.raises(ValueError, match="closed"):
        first.vjp(recorded, np.zeros((12, 4)))


@pytest.mark.parametrize("target", [-1, 2, True, 1.2])
def test_invalid_target_rejected(target):
    with pytest.raises((TypeError, ValueError)):
        BatchTargetKernel(
            AffineBatch(2, 2), np.zeros((12, 2, 2)), np.ones((4, 2, 2)), target
        )


def test_inputs_and_full_backend_shapes_are_validated():
    state = np.zeros((12, 2, 3), dtype=np.float64)
    forcing = np.ones((4, 2, 3), dtype=np.float64)
    adapter = BatchTargetKernel(AffineBatch(2, 3), state, forcing, 1)
    with pytest.raises(TypeError, match="float64"):
        adapter.forward(state[:, 1].astype(np.float32), forcing[:, 1])
    with pytest.raises(ValueError, match="shape"):
        adapter.forward(state[:, 1], forcing[:, 1, :2])

    class BadBackend(AffineBatch):
        def forward(self, state, forcing, *, record=False):
            return np.zeros((12, self.B, self.L - 1), dtype=np.float64), None

    bad = BatchTargetKernel(BadBackend(2, 3), state, forcing, 1)
    with pytest.raises(ValueError, match="full backend output"):
        bad.forward(state[:, 1], forcing[:, 1])


def test_adapter_matches_native_dry_number_kernel_protocol_joint_keyword_and_dt():
    batch, levels, target = 3, 4, 1
    backend = AffineBatch(batch, levels)
    baseline_state = np.ones((12, batch, levels), dtype=np.float64)
    baseline_forcing = np.full((4, batch, levels), 2.0, dtype=np.float64)
    adapter = BatchTargetKernel(
        backend, baseline_state, baseline_forcing, target, dt=20.0
    )
    assert adapter.levels == levels
    assert adapter.dt == 20.0
    admission = NumberBasisAdmission(
        schema=ADMISSION_SCHEMA,
        origin="verified_dry_producer",
        source_id="test-affine-batch-source",
        source_sha256="1" * 64,
        receipt_sha256="2" * 64,
        field_units={name: NUMBER_UNITS for name in NUMBER_FIELDS},
    )
    dry_kernel = NativeDryNumberKernel(adapter, admission=admission)

    state = np.full((12, levels), 0.2, dtype=np.float64)
    state[7:11] = np.arange(4, dtype=np.float64)[:, None] + 1.0
    forcing = np.full((4, levels), 2.0, dtype=np.float64)
    value, handle = dry_kernel.forward(state, forcing, joint=True, record=True)
    expected_volume_state = state.copy()
    expected_volume_state[7:11] *= forcing[0][None, :]
    np.testing.assert_array_equal(
        backend.last_inputs[0][:, target, :], expected_volume_state
    )
    assert value.shape == (12, levels)

    ds = np.full_like(state, 0.01)
    df = np.full_like(forcing, 0.02)
    tangent = dry_kernel.jvp(handle, ds, df)
    cotangent = np.linspace(0.1, 1.2, 12 * levels, dtype=np.float64).reshape(12, levels)
    gs, gf = dry_kernel.vjp(handle, cotangent)
    np.testing.assert_allclose(
        np.sum(cotangent * tangent),
        np.sum(gs * ds) + np.sum(gf * df),
        rtol=2e-13,
        atol=2e-13,
    )
    dry_kernel.close(handle)
    assert backend.close_calls == 1


def test_joint_false_is_rejected_clearly():
    state = np.zeros((12, 2, 3), dtype=np.float64)
    forcing = np.ones((4, 2, 3), dtype=np.float64)
    adapter = BatchTargetKernel(AffineBatch(2, 3), state, forcing, 0)
    with pytest.raises(ValueError, match="requires joint=True"):
        adapter.forward(state[:, 0], forcing[:, 0], joint=False)


def test_dt_metadata_cannot_override_implicit_or_declared_backend_timestep():
    state = np.zeros((12, 2, 3), dtype=np.float64)
    forcing = np.ones((4, 2, 3), dtype=np.float64)
    backend = AffineBatch(
        2, 3
    )  # Missing dt means the established BatchKernel20s contract.
    with pytest.raises(ValueError, match="differs from backend dt"):
        BatchTargetKernel(backend, state, forcing, 0, dt=30.0)
    assert BatchTargetKernel(backend, state, forcing, 0).dt == 20.0
    backend.dt = 30.0
    with pytest.raises(ValueError, match="differs from backend dt"):
        BatchTargetKernel(backend, state, forcing, 0)
    assert BatchTargetKernel(backend, state, forcing, 0, dt=30.0).dt == 30.0
