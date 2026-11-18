"""Applied NI sedimentation amounts, coordinate measures and noninterference."""

import pytest
import numpy as np
import torch

from kdm6.ice_number_budget import IceNumberAppliedLedger, summarize_ice_number_substep
from kdm6.sedimentation import (
    IceSubstepState,
    default_substep_advection_params,
    ice_substep_advection_torch,
)


def _tensor(rows, *, dtype=torch.float64):
    return torch.tensor(rows, dtype=dtype)


def _bits(value):
    integer = torch.int64 if value.dtype == torch.float64 else torch.int32
    return value.contiguous().view(integer)


def _run(ni, workn, delz, *, dend=None, qi=None, fall_qi=None, fall_ni=None,
         dt=1.0, mstep=1, mstep_col=None, n_current=1, number_ledger=None):
    if qi is None:
        qi = torch.zeros_like(ni)
    if dend is None:
        dend = torch.ones_like(ni)
    if fall_qi is None:
        fall_qi = torch.zeros_like(ni)
    if fall_ni is None:
        fall_ni = torch.zeros_like(ni)
    return ice_substep_advection_torch(
        IceSubstepState(qi=qi, ni=ni), fall_qi, fall_ni,
        torch.zeros_like(ni), workn, delz, dend,
        mstep=mstep, mstep_col=mstep_col, n_current=n_current,
        dtcld=dt, params=default_substep_advection_params(),
        number_ledger=number_ledger,
    )


def _same_bits(a, b):
    for field in ("qi", "ni"):
        assert torch.equal(_bits(getattr(a.state, field)), _bits(getattr(b.state, field)))
    for field in ("fall_qi", "fall_ni"):
        assert torch.equal(_bits(getattr(a, field)), _bits(getattr(b, field)))


@pytest.mark.parametrize("work,expected_after,expected_in,expected_loss", [
    (0.2, [8.0, 2.0], 2.0, 0.0),
    (0.8, [2.0, 2.0], 2.0, 6.0),
])
def test_two_layers_measure_actual_arrival_not_candidate(work, expected_after,
                                                          expected_in, expected_loss):
    ni = _tensor([[10.0, 0.0]])
    workn = _tensor([[work, 0.0]])
    delz = _tensor([[1.0, 1.0]])
    ledger = IceNumberAppliedLedger()
    plain = _run(ni, workn, delz)
    seen = _run(ni, workn, delz, number_ledger=ledger)
    _same_bits(plain, seen)
    record = ledger.records[0]
    assert record.before.tolist() == [[10.0, 0.0]]
    assert record.after.tolist() == [expected_after]
    assert record.applied_out[0, 0].item() == work * 10.0
    assert record.candidate_in[0, 1].item() == work * 10.0
    assert record.applied_in[0, 1].item() == expected_in
    assert bool(record.inflow_cap[0, 1]) is (work == 0.8)
    assert record.fall_after[0, 0].item() == work * 10.0
    balance = summarize_ice_number_substep(record)
    assert balance.weight_coordinate == "dz"
    assert balance.column_loss[0].item() == pytest.approx(expected_loss)
    assert balance.interface_difference[0, 0].item() == pytest.approx(expected_loss)
    assert balance.bottom_applied_out[0].item() == 0.0
    assert balance.bottom_raw_fall_candidate[0].item() == 0.0
    assert balance.closure_residual[0].abs().item() <= 1e-14


def test_three_layers_separate_top_projection_caps_and_density_measures():
    ni = _tensor([[10.0, 2.0, 3.0]])
    workn = _tensor([[2.0, 0.5, 0.25]])
    delz = _tensor([[1.0, 2.0, 4.0]])
    dend = _tensor([[0.7, 1.1, 1.8]])
    rho_d = _tensor([[0.5, 1.0, 2.0]])
    ledger = IceNumberAppliedLedger()
    plain = _run(ni, workn, delz, dend=dend)
    seen = _run(ni, workn, delz, dend=dend, number_ledger=ledger)
    _same_bits(plain, seen)
    record = ledger.records[0]
    assert record.after.tolist() == [[0.0, 1.0, 2.75]]
    assert record.candidate_out.tolist() == [[20.0, 1.0, 0.75]]
    assert record.applied_out.tolist() == [[20.0, 1.0, 0.75]]
    assert record.candidate_in.tolist() == [[0.0, 10.0, 0.5]]
    assert record.applied_in.tolist() == [[0.0, 0.0, 0.5]]
    assert record.projection.tolist() == [[10.0, 0.0, 0.0]]
    assert record.projection_active.tolist() == [[True, False, False]]
    assert record.inflow_cap.tolist() == [[False, True, False]]
    operator = summarize_ice_number_substep(record)
    assert operator.column_loss.tolist() == [13.0]
    assert operator.bottom_applied_out.tolist() == [3.0]
    assert operator.interface_difference.tolist() == [[20.0, 0.0]]
    assert operator.projection.tolist() == [10.0]
    assert operator.attributed_loss.tolist() == [13.0]
    assert operator.closure_residual.tolist() == [0.0]
    conditional = summarize_ice_number_substep(record, dry_density=rho_d)
    assert conditional.weight_coordinate == "rho_d*dz"
    assert conditional.column_loss.tolist() == [9.0]
    assert conditional.bottom_applied_out.tolist() == [6.0]
    assert conditional.interface_difference.tolist() == [[10.0, -2.0]]
    assert conditional.projection.tolist() == [5.0]
    assert conditional.attributed_loss.tolist() == [9.0]
    assert conditional.closure_residual.tolist() == [0.0]
    assert record.dend.tolist() == dend.tolist()


def test_bottom_outflow_cap_differs_from_raw_fall_candidate():
    ni = _tensor([[0.0, 2.0]])
    workn = _tensor([[0.0, 2.0]])
    delz = _tensor([[1.0, 3.0]])
    ledger = IceNumberAppliedLedger()
    plain = _run(ni, workn, delz)
    seen = _run(ni, workn, delz, number_ledger=ledger)
    _same_bits(plain, seen)
    record = ledger.records[0]
    assert record.candidate_out.tolist() == [[0.0, 4.0]]
    assert record.applied_out.tolist() == [[0.0, 2.0]]
    assert record.outflow_cap.tolist() == [[False, True]]
    balance = summarize_ice_number_substep(record)
    assert balance.column_loss.tolist() == [6.0]
    assert balance.bottom_applied_out.tolist() == [6.0]
    assert balance.bottom_raw_fall_candidate.tolist() == [12.0]
    assert balance.closure_residual.tolist() == [0.0]


def test_raw_bottom_candidate_survives_fall_accumulator_rounding():
    ni = _tensor([[1.0]], dtype=torch.float32)
    workn = _tensor([[1.0]], dtype=torch.float32)
    delz = _tensor([[1.0]], dtype=torch.float32)
    fall = _tensor([[2.0 ** 24]], dtype=torch.float32)
    ledger = IceNumberAppliedLedger()
    plain = _run(ni, workn, delz, fall_ni=fall)
    seen = _run(ni, workn, delz, fall_ni=fall, number_ledger=ledger)
    _same_bits(plain, seen)
    record = ledger.records[0]
    assert record.candidate_out.tolist() == [[1.0]]
    assert torch.equal(_bits(record.fall_before), _bits(record.fall_after))
    balance = summarize_ice_number_substep(record)
    assert balance.bottom_raw_fall_candidate.tolist() == [1.0]
    assert balance.bottom_accumulator_delta.tolist() == [0.0]
    assert balance.column_loss.tolist() == [1.0]
    assert balance.closure_residual.tolist() == [0.0]


@pytest.mark.parametrize("dtype", [torch.float32, torch.float64])
def test_single_layer_top_overshoot_and_signed_zero_bits(dtype):
    ni = _tensor([[10.0]], dtype=dtype)
    workn = _tensor([[2.0]], dtype=dtype)
    delz = _tensor([[3.0]], dtype=dtype)
    negative_zero = _tensor([[-0.0]], dtype=dtype)
    ledger = IceNumberAppliedLedger()
    plain = _run(ni, workn, delz, fall_ni=negative_zero)
    seen = _run(ni, workn, delz, fall_ni=negative_zero, number_ledger=ledger)
    _same_bits(plain, seen)
    record = ledger.records[0]
    assert record.applied_out.tolist() == [[20.0]]
    assert record.projection.tolist() == [[10.0]]
    assert record.projection_active.tolist() == [[True]]
    assert record.fall_before[0, 0].signbit().item()
    balance = summarize_ice_number_substep(record)
    assert balance.column_loss.tolist() == [30.0]
    assert balance.bottom_applied_out.tolist() == [60.0]
    assert balance.projection.tolist() == [30.0]
    assert balance.bottom_raw_fall_candidate.tolist() == [60.0]
    assert balance.interface_difference.shape == (1, 0)
    assert balance.closure_residual.tolist() == [0.0]


def test_nonuniform_density_changes_conditional_dry_inventory_without_ni_update():
    ni = _tensor([[10.0, 0.0]])
    workn = _tensor([[0.2, 0.0]])
    delz = _tensor([[1.0, 2.0]])
    dend = _tensor([[9.0, 7.0]])
    ledger = IceNumberAppliedLedger()
    _run(ni, workn, delz, dend=dend, number_ledger=ledger)
    record = ledger.records[0]
    operator = summarize_ice_number_substep(record)
    dry = summarize_ice_number_substep(record, dry_density=_tensor([[0.5, 1.5]]))
    assert operator.column_loss.tolist() == [0.0]
    assert dry.column_loss.tolist() == [-2.0]
    assert dry.interface_difference.tolist() == [[-2.0]]
    assert dry.closure_residual.tolist() == [0.0]


def test_float32_candidate_and_applied_words_match_separate_ordered_reference():
    ni = _tensor([[10.1, 2.3, 0.7]], dtype=torch.float32)
    workn = _tensor([[0.17, 0.23, 0.05]], dtype=torch.float32)
    delz = _tensor([[1.25, 0.75, 2.5]], dtype=torch.float32)
    ledger = IceNumberAppliedLedger()
    seen = _run(ni, workn, delz, dt=0.8, mstep=2, number_ledger=ledger)
    plain = _run(ni, workn, delz, dt=0.8, mstep=2)
    _same_bits(plain, seen)
    n = ni.numpy()[0]
    w = workn.numpy()[0]
    z = delz.numpy()[0]
    dt = np.float32(0.8)
    fall = np.zeros(3, dtype=np.float32)
    post = np.zeros(3, dtype=np.float32)
    candidate_out = np.zeros(3, dtype=np.float32)
    applied_out = np.zeros(3, dtype=np.float32)
    candidate_in = np.zeros(3, dtype=np.float32)
    applied_in = np.zeros(3, dtype=np.float32)
    previous_falk = np.float32(0.0)
    for k in range(3):
        falk = np.float32(np.float32(n[k] * w[k]) / np.float32(2.0))
        fall[k] = np.float32(fall[k] + falk)
        candidate_out[k] = np.float32(falk * dt)
        applied_out[k] = (candidate_out[k] if k == 0 else
                          np.minimum(candidate_out[k], n[k]))
        if k:
            candidate_in[k] = np.float32(
                np.float32(np.float32(previous_falk * z[k - 1]) / z[k]) * dt)
            applied_in[k] = np.minimum(candidate_in[k], post[k - 1])
        preclamp = np.float32(np.float32(n[k] - applied_out[k]) + applied_in[k])
        post[k] = np.maximum(preclamp, np.float32(0.0))
        previous_falk = falk
    record = ledger.records[0]
    for actual, expected in (
        (record.candidate_out[0].numpy(), candidate_out),
        (record.applied_out[0].numpy(), applied_out),
        (record.candidate_in[0].numpy(), candidate_in),
        (record.applied_in[0].numpy(), applied_in),
        (record.after[0].numpy(), post),
        (record.fall_after[0].numpy(), fall),
    ):
        assert np.array_equal(actual.view(np.uint32), expected.view(np.uint32))


def test_multicolumn_gate_and_repeated_substeps_record_only_applied_values():
    ni = _tensor([[10.0, 1.0], [10.0, 1.0]])
    workn = _tensor([[0.1, 0.1], [0.1, 0.1]])
    delz = _tensor([[1.0, 1.0], [1.0, 1.0]])
    msteps = _tensor([1.0, 2.0])
    ledger = IceNumberAppliedLedger()
    first = _run(ni, workn, delz, mstep_col=msteps, n_current=1, number_ledger=ledger)
    plain_first = _run(ni, workn, delz, mstep_col=msteps, n_current=1)
    _same_bits(first, plain_first)
    second = _run(first.state.ni, workn, delz, fall_qi=first.fall_qi,
                  fall_ni=first.fall_ni, mstep_col=msteps, n_current=2,
                  number_ledger=ledger)
    plain_second = _run(plain_first.state.ni, workn, delz, fall_qi=plain_first.fall_qi,
                        fall_ni=plain_first.fall_ni, mstep_col=msteps, n_current=2)
    _same_bits(second, plain_second)
    assert len(ledger.records) == 2
    assert ledger.records[0].gate.tolist() == [1.0, 1.0]
    assert ledger.records[1].gate.tolist() == [0.0, 1.0]
    assert ledger.records[1].mstep_divisor.tolist() == [1.0, 2.0]
    assert torch.equal(_bits(second.state.ni[0]), _bits(first.state.ni[0]))
    for record in ledger.records:
        balance = summarize_ice_number_substep(record)
        assert torch.all(balance.closure_residual.abs() < 1e-12)


def test_zero_dt_records_no_applied_state_change_but_raw_fall_accumulates():
    ni = _tensor([[5.0, 2.0]])
    workn = _tensor([[0.5, 0.25]])
    delz = _tensor([[1.0, 2.0]])
    ledger = IceNumberAppliedLedger()
    plain = _run(ni, workn, delz, dt=0.0)
    seen = _run(ni, workn, delz, dt=0.0, number_ledger=ledger)
    _same_bits(plain, seen)
    record = ledger.records[0]
    assert record.after.tolist() == ni.tolist()
    assert record.candidate_out.tolist() == [[0.0, 0.0]]
    assert record.applied_out.tolist() == [[0.0, 0.0]]
    assert record.fall_after.tolist() == [[2.5, 0.5]]
    balance = summarize_ice_number_substep(record)
    assert balance.column_loss.tolist() == [0.0]
    assert balance.bottom_raw_fall_candidate.tolist() == [0.0]


def test_diagnostic_preserves_smooth_jvp_and_vjp():
    workn = _tensor([[0.1, 0.1]])
    delz = _tensor([[1.0, 1.0]])
    ni = _tensor([[10.0, 1.0]])
    direction = _tensor([[1.0, -0.2]])

    def forward(value, *, capture):
        ledger = IceNumberAppliedLedger() if capture else None
        result = _run(value, workn, delz, number_ledger=ledger)
        if capture:
            assert len(ledger.records) == 1
            assert not ledger.records[0].after.requires_grad
        return result.state.ni

    plain_value, plain_jvp = torch.autograd.functional.jvp(
        lambda value: forward(value, capture=False), ni, direction)
    seen_value, seen_jvp = torch.autograd.functional.jvp(
        lambda value: forward(value, capture=True), ni, direction)
    assert torch.equal(_bits(plain_value), _bits(seen_value))
    assert torch.equal(_bits(plain_jvp), _bits(seen_jvp))
    plain_gradient = None
    for capture in (False, True):
        source = ni.clone().requires_grad_(True)
        result = forward(source, capture=capture)
        gradient = torch.autograd.grad((result * _tensor([[1.0, -2.0]])).sum(), source)[0]
        if capture:
            assert plain_gradient is not None
            assert torch.equal(_bits(gradient), _bits(plain_gradient))
        else:
            plain_gradient = gradient
