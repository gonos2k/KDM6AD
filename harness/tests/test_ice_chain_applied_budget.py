"""QI/NI applied amounts from the actual resloping ice-chain call sequence."""

import pytest
import torch

from harness.ice_chain_applied_budget import IceChainAppliedCapture
from oracle.kdm6.coordinator import (
    CoordinatorForcing,
    CoordinatorState,
    default_coordinator_params,
    preamble_torch,
    sedimentation_chain_torch,
)
from oracle.kdm6.ice_number_budget import summarize_ice_number_substep
from oracle.kdm6.sedimentation import (
    default_substep_advection_params,
    substep_advection_torch,
)
from oracle.kdm6.water_budget import SedimentationLedger


def _bits(value):
    integer = torch.int32 if value.dtype == torch.float32 else torch.int64
    return value.contiguous().view(integer)


def _inputs(dtype):
    def full(value):
        return torch.full((2, 3), value, dtype=dtype)

    state = CoordinatorState(
        qv=full(0.005), qc=full(1e-6), qr=full(1e-6),
        qs=full(1e-8), qg=full(1e-8),
        qi=torch.tensor([[8e-8, 6e-8, 4e-8], [9e-8, 5e-8, 3e-8]], dtype=dtype),
        nc=full(1e5), nr=full(1e4),
        ni=torch.tensor([[40.0, 30.0, 20.0], [45.0, 25.0, 15.0]], dtype=dtype),
        brs=full(1e-7), t=full(263.15),
    )
    delz = torch.tensor([[300.0, 500.0, 700.0], [250.0, 450.0, 650.0]], dtype=dtype)
    density = torch.tensor([[0.8, 1.0, 1.2], [1.1, 0.9, 1.3]], dtype=dtype)
    forcing = CoordinatorForcing(p=full(8e4), den=density, delz=delz, dend=density)
    sea_mask = torch.zeros((2, 3), dtype=torch.bool)
    cp = default_coordinator_params()
    pre = preamble_torch(state, forcing, sea_mask, params=cp)
    work = (pre.slope.vt_r / delz, pre.slope.vtn_r / delz,
            pre.slope.vt_s / delz, pre.slope.vt_g / delz,
            pre.slope.vt_i / delz, pre.slope.vtn_i / delz)
    return state, forcing, sea_mask, cp, work


def _run(state, forcing, sea_mask, cp, work, *, capture=None,
         normalized=False, reslope=True, mstep_main=2, mstep_ice=2,
         mass_ledger=None, main_substep_fn=None):
    msteps = torch.tensor([1.0, 2.0], dtype=state.qi.dtype)
    return sedimentation_chain_torch(
        state, forcing, *work,
        mstep_main=mstep_main, mstep_ice=mstep_ice, dtcld=1.0,
        params=default_substep_advection_params(),
        reslope_params=cp if reslope else None,
        sea_mask=sea_mask,
        mstep_col_main=msteps, mstep_col_ice=msteps,
        ledger=mass_ledger, substep_fn=main_substep_fn,
        ice_substep_fn=capture,
        normalize_ice_handoff=normalized,
    )


def _same_bits(left, right):
    for field in left.state._fields:
        assert torch.equal(_bits(getattr(left.state, field)),
                           _bits(getattr(right.state, field))), field
    for field in ("rain_increment", "snow_increment", "graupel_increment"):
        assert torch.equal(_bits(getattr(left, field)), _bits(getattr(right, field))), field


@pytest.mark.parametrize("dtype", [torch.float32, torch.float64])
def test_actual_reslope_chain_pairs_qi_ni_and_preserves_all_outputs(dtype):
    state, forcing, mask, cp, work = _inputs(dtype)
    captures = {}
    for normalized in (False, True):
        capture = IceChainAppliedCapture()
        main_states = []

        def record_main(*args, **kwargs):
            result = substep_advection_torch(*args, **kwargs)
            main_states.append(result.state)
            return result

        with_mass = SedimentationLedger()
        plain_mass = SedimentationLedger()
        seen = _run(state, forcing, mask, cp, work, capture=capture,
                    normalized=normalized, mass_ledger=with_mass,
                    main_substep_fn=record_main)
        plain = _run(state, forcing, mask, cp, work, normalized=normalized,
                     mass_ledger=plain_mass)
        _same_bits(seen, plain)
        captures[normalized] = capture
        assert len(capture.records) == 2
        assert len(main_states) == 2
        main_final = main_states[-1]
        pre_main = preamble_torch(
            state._replace(qr=main_final.qr, nr=main_final.nr,
                           qs=main_final.qs, qg=main_final.qg, brs=main_final.brs),
            forcing, mask, params=cp)
        dz = forcing.delz
        first = capture.records[0]
        for actual, speed in ((first.work1_qi, pre_main.slope.vt_i),
                              (first.workn_qi, pre_main.slope.vtn_i)):
            expected = speed / dz if normalized else speed
            assert torch.equal(_bits(actual), _bits(expected))
        post_first = state._replace(
            qr=main_final.qr, nr=main_final.nr, qs=main_final.qs,
            qg=main_final.qg, brs=pre_main.progb.bg,
            qi=first.qi_after, ni=first.number.after)
        pre_ice = preamble_torch(post_first, forcing, mask, params=cp)
        second = capture.records[1]
        assert torch.equal(_bits(second.work1_qi), _bits(pre_ice.slope.vt_i / dz))
        assert torch.equal(_bits(second.workn_qi), _bits(pre_ice.slope.vtn_i / dz))
        for n, witness in enumerate(capture.records, start=1):
            assert witness.n_current == witness.number.n_current == n
            assert witness.number.gate.tolist() == ([1.0, 1.0] if n == 1 else [0.0, 1.0])
            assert torch.equal(_bits(witness.qi_before),
                               _bits(state.qi if n == 1 else capture.records[0].qi_after))
            assert torch.equal(_bits(witness.number.before),
                               _bits(state.ni if n == 1 else capture.records[0].number.after))
            expected_mass = ((forcing.dend * forcing.delz) *
                             (witness.qi_before - witness.qi_after)).sum(dim=-1)
            mass_loss = witness.mass.column_loss_by_species_kg_m2["qi"]
            assert torch.equal(_bits(mass_loss), _bits(expected_mass))
            mass_weight = forcing.dend * forcing.delz
            layer_loss = mass_weight * (witness.qi_before - witness.qi_after)
            accounted = (witness.qi_applied_out_mass - witness.qi_applied_in_mass -
                         witness.qi_projection_mass)
            mass_scale = (mass_weight * (witness.qi_before.abs() + witness.qi_after.abs()) +
                          witness.qi_applied_out_mass.abs() +
                          witness.qi_applied_in_mass.abs() +
                          witness.qi_projection_mass.abs())
            assert torch.all((layer_loss - accounted).abs() <=
                             32 * torch.finfo(dtype).eps * mass_scale)
            assert torch.equal(_bits(witness.qi_applied_out_mass[:, -1]),
                               _bits(witness.mass.bottom_actual_outflow_by_species_kg_m2["qi"]))
            assert torch.equal(
                _bits(witness.qi_applied_out_mass[:, :-1] - witness.qi_applied_in_mass[:, 1:]),
                _bits(witness.mass.interface_defect_detail_kg_m2["qi"]))
            number_balance = summarize_ice_number_substep(witness.number)
            record = witness.number
            scale = (record.delz * (record.before.abs() + record.after.abs() +
                                   record.applied_out.abs() + record.applied_in.abs() +
                                   record.projection.abs())).sum(dim=-1)
            eps = torch.finfo(dtype).eps
            assert torch.all(number_balance.closure_residual.abs() <= 32 * eps * scale)
            assert not witness.work1_qi.requires_grad and not witness.workn_qi.requires_grad
        # Every mass record, including the forwarded ice record, reaches the
        # caller's original cumulative ledger unchanged.
        actual_mass = with_mass.finalize(like=state.qi)
        expected_mass = plain_mass.finalize(like=state.qi)
        for species in ("qr", "qs", "qg", "qi"):
            for field in ("column_loss_by_species_kg_m2", "wrf_fallout_diag_by_species_kg_m2",
                          "interface_defect_by_species_kg_m2", "positivity_projection_by_species_kg_m2"):
                assert torch.equal(_bits(getattr(actual_mass, field)[species]),
                                   _bits(getattr(expected_mass, field)[species]))
        # The second column remains active at n=2; the first is called but gated.
        second = capture.records[1]
        assert torch.equal(_bits(second.number.before[0]), _bits(second.number.after[0]))
        assert torch.count_nonzero(second.number.applied_out[0]) == 0
        assert torch.count_nonzero(second.number.applied_in[0]) == 0
        assert torch.equal(_bits(second.qi_before[0]), _bits(second.qi_after[0]))
        assert not torch.equal(_bits(capture.records[0].workn_qi[1]),
                               _bits(second.workn_qi[1]))
    # The same post-main slope reaches the first ice call in two documented
    # coordinates: raw velocity by default and velocity/dz when normalized.
    raw = captures[False].records[0].workn_qi
    rate = captures[True].records[0].workn_qi
    assert torch.allclose(rate, raw / forcing.delz, rtol=8 * torch.finfo(dtype).eps, atol=0)


def test_no_reslope_uses_caller_work_for_each_ice_call():
    state, forcing, mask, cp, work = _inputs(torch.float64)
    capture = IceChainAppliedCapture()
    seen = _run(state, forcing, mask, cp, work, capture=capture,
                reslope=False, mstep_main=0, mstep_ice=2)
    plain = _run(state, forcing, mask, cp, work,
                 reslope=False, mstep_main=0, mstep_ice=2)
    _same_bits(seen, plain)
    assert len(capture.records) == 2
    for witness in capture.records:
        assert torch.equal(_bits(witness.work1_qi), _bits(work[4]))
        assert torch.equal(_bits(witness.workn_qi), _bits(work[5]))


def test_selected_chain_direction_jvp_vjp_and_fd_are_noninterfering():
    state, forcing, mask, cp, _work = _inputs(torch.float64)
    qi0, ni0 = state.qi, state.ni
    dqi = torch.zeros_like(qi0)
    dni = torch.zeros_like(ni0)
    dqi[1, 1] = qi0[1, 1]
    dni[1, 1] = -ni0[1, 1]

    def evaluate(qi, ni, *, observed=False, return_capture=False):
        trial = state._replace(qi=qi, ni=ni)
        pre = preamble_torch(trial, forcing, mask, params=cp)
        dz = forcing.delz
        work = (pre.slope.vt_r / dz, pre.slope.vtn_r / dz,
                pre.slope.vt_s / dz, pre.slope.vt_g / dz,
                pre.slope.vt_i / dz, pre.slope.vtn_i / dz)
        capture = IceChainAppliedCapture() if observed else None
        result = _run(trial, forcing, mask, cp, work, capture=capture, normalized=True)
        flattened = torch.cat(((result.state.qi * 1e8).reshape(-1), result.state.ni.reshape(-1)))
        return (flattened, capture) if return_capture else flattened

    primal_plain, jvp_plain = torch.autograd.functional.jvp(
        lambda qi, ni: evaluate(qi, ni), (qi0, ni0), (dqi, dni))
    primal_seen, jvp_seen = torch.autograd.functional.jvp(
        lambda qi, ni: evaluate(qi, ni, observed=True), (qi0, ni0), (dqi, dni))
    assert torch.equal(_bits(primal_plain), _bits(primal_seen))
    assert torch.equal(_bits(jvp_plain), _bits(jvp_seen))
    assert torch.count_nonzero(jvp_plain) > 0

    weights = torch.arange(1, primal_plain.numel() + 1, dtype=qi0.dtype)
    weights[1::2] *= -1
    gradients = []
    for observed in (False, True):
        qi = qi0.clone().requires_grad_(True)
        ni = ni0.clone().requires_grad_(True)
        output = evaluate(qi, ni, observed=observed)
        gradients.append(torch.autograd.grad((weights * output).sum(), (qi, ni)))
    for plain, seen in zip(*gradients):
        assert torch.equal(_bits(plain), _bits(seen))
    dot = ((gradients[0][0] * dqi).sum() + (gradients[0][1] * dni).sum())
    assert torch.allclose(dot, (weights * jvp_plain).sum(), rtol=2e-12, atol=1e-12)

    h = 1e-4
    _baseline, cap_baseline = evaluate(qi0, ni0, observed=True, return_capture=True)
    plus, cap_plus = evaluate(qi0 + h * dqi, ni0 + h * dni,
                              observed=True, return_capture=True)
    minus, cap_minus = evaluate(qi0 - h * dqi, ni0 - h * dni,
                                observed=True, return_capture=True)
    for baseline, before, after in zip(cap_baseline.records,
                                       cap_plus.records, cap_minus.records):
        for name in ("outflow_cap", "inflow_cap", "projection_active"):
            assert torch.equal(getattr(baseline.number, name), getattr(before.number, name))
            assert torch.equal(getattr(before.number, name), getattr(after.number, name))
        for name in ("qi_outflow_cap", "qi_inflow_cap", "qi_top_clamp"):
            assert torch.equal(baseline.mass.cap_flags[name], before.mass.cap_flags[name])
            assert torch.equal(before.mass.cap_flags[name], after.mass.cap_flags[name])
        assert torch.equal(baseline.number.gate, before.number.gate)
        assert torch.equal(before.number.gate, after.number.gate)
    fd = (plus - minus) / (2 * h)
    assert torch.allclose(fd, jvp_plain, rtol=2e-6, atol=2e-8)
