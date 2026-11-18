#!/usr/bin/env python3
"""Trace the PR #504 synthetic ice column through one post-fall microphysics pass."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import torch

from harness.ice_chain_applied_budget import IceChainAppliedCapture
from harness.tests.test_ice_chain_applied_budget import _inputs, _run
from oracle.kdm6.cloud_dsd import (
    default_cloud_dsd_params,
    diag_cloud_slope_torch,
    diag_qcr_torch,
)
from oracle.kdm6.coordinator import (
    apply_threshold_cleanup_torch,
    build_default_aux_torch,
    default_cold_phase_params,
    default_melt_freeze_phase_params,
    default_warm_phase_params,
    kdm62d_one_step_torch,
    preamble_torch,
)
from oracle.kdm6.sensitivity_diagnostics import SensitivityTrace
from oracle.kdm6.thermo import compute_cpm, compute_xl

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
STAGES = (
    "d1_melt", "d2_d4_freeze", "warm", "cold", "d5_melt",
    "ice_mass_budget", "warm_limited", "cold_limited", "d5_limited",
    "state_update", "picons", "satadj", "cleanup", "dsd_limiter",
)
VALUE_STAGES = ("d1_melt", "d2_d4_freeze", "state_update", "picons",
                "satadj", "cleanup", "dsd_limiter")


def require(value, message):
    if not value:
        raise ValueError(message)


def verify_sources():
    pins = json.loads((ROOT / "source_manifest.json").read_bytes())
    for relative, expected in pins.items():
        path = REPO / relative
        require(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected,
                "source digest " + relative)


def flip_namedtuple(value):
    return type(value)(*(field.flip(-1) for field in value))


def bits_equal(left, right):
    return torch.equal(left.contiguous().view(torch.int64),
                       right.contiguous().view(torch.int64))


def first_column_top(value, field):
    """Trace state is WRF bottom-first; report the same top-first order as sedimentation."""
    return getattr(value, field)[0].flip(-1).detach().cpu().tolist()


def check_rate_accounting(trace):
    update = trace.by_name("state_update")[0]
    cold = trace.by_name("cold_limited")[0].rates
    melt = trace.by_name("d5_limited")[0].rates
    q_before, q_after = update.state_in.qi[0], update.state_out.qi[0]
    n_before, n_after = update.state_in.ni[0], update.state_out.ni[0]
    q_terms = ("psaut", "praci", "psaci", "pgaci")
    q_sources = ("pinud", "pidep", "piacw", "pmulcs", "pmulcg", "pmulrs", "pmulrg")
    n_sinks = ("nraci", "nsaci", "ngaci", "niacr", "nsaut")
    n_sources = ("ninud", "nmulcs", "nmulcg", "nmulrs", "nmulrg")
    q_delta, n_delta, q_other, n_other = [], [], [], []
    for k in range(q_before.numel()):
        q_rate = math.fsum(float(getattr(cold, name)[0, k]) for name in q_sources)
        q_rate -= math.fsum(float(getattr(cold, name)[0, k]) for name in q_terms)
        q_amount = (float(melt.pinuc[0, k]) + float(melt.pfrzdtc[0, k]) -
                    float(melt.pimlt_qi[0, k]))
        n_rate = math.fsum(float(getattr(cold, name)[0, k]) for name in n_sources)
        n_rate -= math.fsum(float(getattr(cold, name)[0, k]) for name in n_sinks)
        n_amount = (float(melt.ninuc[0, k]) + float(melt.nfrzdtc[0, k]) -
                    float(melt.pimlt_ni[0, k]))
        require(not bool(cold.ice_complete_sublim[0, k]), "complete sublimation branch")
        q_expected = float(q_before[k]) + q_rate * update.dtcld + q_amount
        n_expected = float(n_before[k]) + n_rate * update.dtcld + n_amount
        q_scale = abs(float(q_before[k])) + abs(q_rate * update.dtcld) + abs(q_amount)
        n_scale = abs(float(n_before[k])) + abs(n_rate * update.dtcld) + abs(n_amount)
        eps = torch.finfo(q_before.dtype).eps
        require(abs(float(q_after[k]) - q_expected) <= 128 * eps * q_scale,
                "applied QI rate accounting")
        require(abs(float(n_after[k]) - n_expected) <= 128 * eps * n_scale,
                "applied NI rate accounting")
        q_delta.append(float(q_after[k] - q_before[k]))
        n_delta.append(float(n_after[k] - n_before[k]))
        q_other.append(q_rate - float(cold.pinud[0, k]) - float(cold.pidep[0, k]))
        n_other.append(n_rate - float(cold.ninud[0, k]))
    return {
        "pinud_qi_rate": cold.pinud[0].flip(-1).detach().tolist(),
        "pidep_qi_rate": cold.pidep[0].flip(-1).detach().tolist(),
        "ninud_ni_rate": cold.ninud[0].flip(-1).detach().tolist(),
        "qi_state_update_delta": list(reversed(q_delta)),
        "ni_state_update_delta": list(reversed(n_delta)),
        "qi_other_net_rate": list(reversed(q_other)),
        "ni_other_net_rate": list(reversed(n_other)),
        "complete_sublimation": cold.ice_complete_sublim[0].flip(-1).detach().tolist(),
    }


def main():
    torch.set_num_threads(1)
    verify_sources()
    state, forcing, mask, params, work = _inputs(torch.float64)
    ice_capture = IceChainAppliedCapture()
    sedimented = _run(state, forcing, mask, params, work,
                      capture=ice_capture, normalized=False)
    plain_sed = _run(state, forcing, mask, params, work, normalized=False)
    for name in sedimented.state._fields:
        require(bits_equal(getattr(sedimented.state, name),
                           getattr(plain_sed.state, name)), "sediment observer " + name)
    for name in ("rain_increment", "snow_increment", "graupel_increment"):
        require(bits_equal(getattr(sedimented, name), getattr(plain_sed, name)),
                "sediment surface " + name)
    require(len(ice_capture.records) == 2, "ice substep count")
    first, second = ice_capture.records
    require(first.number.gate.tolist() == [1.0, 1.0] and
            second.number.gate.tolist() == [0.0, 1.0], "synthetic gate schedule")
    require(torch.count_nonzero(first.qi_after[0]) == 0 and
            torch.all(first.number.after[0] > 0), "first ice orphan state")
    require(bits_equal(first.qi_after[0], sedimented.state.qi[0]) and
            bits_equal(first.number.after[0], sedimented.state.ni[0]),
            "first column unchanged by gated second ice substep")
    # Runtime reclamps BRS before sedimentation and derives mstep from the
    # initial normalized speeds. The PR #504 fixture bypasses both choices.
    pre_sed = preamble_torch(state, forcing, mask, params=params)
    pre_sed_brs = state._replace(brs=pre_sed.progb.bg)
    require(not bits_equal(pre_sed_brs.brs[0], state.brs[0]),
            "runtime pre-sed BRS contrast must be active")
    reclamped_sed = _run(pre_sed_brs, forcing, mask, params, work,
                         normalized=False)
    for name in sedimented.state._fields:
        require(bits_equal(getattr(reclamped_sed.state, name),
                           getattr(sedimented.state, name)),
                "BRS reclamp sensitivity " + name)
    for name in ("rain_increment", "snow_increment", "graupel_increment"):
        require(bits_equal(getattr(reclamped_sed, name), getattr(sedimented, name)),
                "BRS reclamp surface " + name)
    with torch.no_grad():
        vmax_main = torch.maximum(torch.maximum(work[0], work[1]),
                                   torch.maximum(work[2], work[3])).amax(dim=-1)
        vmax_ice = torch.maximum(work[4], work[5]).amax(dim=-1)
        selected_main = torch.clamp(torch.floor(vmax_main * 1.0 + 1.0), 1, 100)
        selected_ice = torch.clamp(torch.floor(vmax_ice * 1.0 + 1.0), 1, 100)
    require(selected_main.tolist() == [1.0, 1.0] and
            selected_ice.tolist() == [1.0, 1.0], "runtime-selected mstep contrast")

    # The chain uses top-first order; the one-step microphysics function consumes
    # WRF bottom-first order. This is the same flip performed by runtime._kdm6_pure.
    entry = flip_namedtuple(state)
    post_fall = flip_namedtuple(sedimented.state)
    micro_forcing = flip_namedtuple(forcing)
    micro_mask = mask.flip(-1)
    cloud_params = default_cloud_dsd_params()
    cloud_slope = diag_cloud_slope_torch(
        post_fall.qc, post_fall.nc, micro_forcing.dend,
        params=cloud_params, ncmin_tensor=None)
    aux = build_default_aux_torch(
        post_fall, micro_forcing, cloud_slope, thermo_params=params.thermo)
    aux = aux._replace(qcr=diag_qcr_torch(micro_mask, params=cloud_params,
                                           ref=post_fall.qc))
    common = dict(
        full_params=params, warm_params=default_warm_phase_params(),
        cold_params=default_cold_phase_params(),
        mf_params=default_melt_freeze_phase_params(),
        dtcld=1.0, ncmin_tensor=None, nccn=None,
        entry_cpm=compute_cpm(entry.qv, params=params.thermo),
        entry_xl=compute_xl(entry.t, params=params.thermo),
    )
    trace = SensitivityTrace()
    traced = kdm62d_one_step_torch(post_fall, micro_forcing, aux, micro_mask,
                                   diagnostic_trace=trace, diagnostic_step=0, **common)
    plain = kdm62d_one_step_torch(post_fall, micro_forcing, aux, micro_mask,
                                  **common)
    for name in traced._fields:
        require(bits_equal(getattr(traced, name), getattr(plain, name)),
                "microphysics trace noninterference " + name)
    require(tuple(record.name for record in trace.records) == STAGES, "microphysics stage order")
    require(bits_equal(trace.by_name("d1_melt")[0].state_in.qi[0].flip(-1),
                       sedimented.state.qi[0]) and
            bits_equal(trace.by_name("d1_melt")[0].state_in.ni[0].flip(-1),
                       sedimented.state.ni[0]), "post-fall to microphysics input")
    d1 = trace.by_name("d1_melt")[0]
    require(bits_equal(d1.state_in.qi[0], d1.state_out.qi[0]) and
            bits_equal(d1.state_in.ni[0], d1.state_out.ni[0]),
            "D1 selected ice pair unchanged")
    early_cleanup = apply_threshold_cleanup_torch(post_fall)
    require(torch.all(early_cleanup.qi[0] == 0) and
            torch.all(early_cleanup.ni[0] == 0), "early paired cleanup control")

    snapshots = {}
    for name in VALUE_STAGES:
        record = trace.by_name(name)[0]
        snapshots[name] = {
            "qi_before_top_first": first_column_top(record.state_in, "qi"),
            "ni_before_top_first": first_column_top(record.state_in, "ni"),
            "qi_after_top_first": first_column_top(record.state_out, "qi"),
            "ni_after_top_first": first_column_top(record.state_out, "ni"),
        }
    freeze = trace.by_name("d2_d4_freeze")[0]
    q_created = freeze.rates.pinuc[0] + freeze.rates.pfrzdtc[0]
    n_created = freeze.rates.ninuc[0] + freeze.rates.nfrzdtc[0]
    require(torch.all(freeze.state_in.qi[0] == 0) and
            torch.all(freeze.state_out.qi[0] > 1e-15) and
            torch.all(q_created > 0) and torch.all(n_created > 0),
            "D2-D4 ice creation")
    eps = torch.finfo(post_fall.qi.dtype).eps
    for before, after, amount, label in (
        (freeze.state_in.qi[0], freeze.state_out.qi[0], q_created, "QI"),
        (freeze.state_in.ni[0], freeze.state_out.ni[0], n_created, "NI"),
    ):
        scale = before.abs() + after.abs() + amount.abs()
        require(torch.all(((after - before) - amount).abs() <= 128 * eps * scale),
                "D2-D4 applied " + label + " accounting")
    update = trace.by_name("state_update")[0]
    require(torch.all(update.state_out.qi[0] > update.state_in.qi[0]) and
            torch.all(update.state_out.ni[0] > update.state_in.ni[0]),
            "applied cold ice growth")
    for name in ("picons", "satadj", "cleanup", "dsd_limiter"):
        record = trace.by_name(name)[0]
        require(bits_equal(record.state_in.qi[0], record.state_out.qi[0]) and
                bits_equal(record.state_in.ni[0], record.state_out.ni[0]),
                "unchanged selected ice moments at " + name)
    require(torch.all(trace.by_name("cleanup")[0].state_in.qi[0] > 1e-15),
            "paired cleanup keeps newly active ice")
    require(bits_equal(traced.qi[0], trace.by_name("dsd_limiter")[0].state_out.qi[0]) and
            bits_equal(traced.ni[0], trace.by_name("dsd_limiter")[0].state_out.ni[0]),
            "final microphysics stage handoff")
    branch = {}
    for name in ("picons", "dsd_limiter"):
        record = trace.by_name(name)[0]
        branch[name] = {
            label: record.branch[index, 0].flip(-1).detach().tolist()
            for index, label in enumerate(record.metadata["branch_labels"])
        }
    branch["cleanup_keep_qi"] = (
        trace.by_name("cleanup")[0].state_in.qi[0].flip(-1) > 1e-15).tolist()
    require(branch["picons"]["ice_active"] == [True] * 3 and
            branch["picons"]["cold_temperature"] == [True] * 3 and
            branch["picons"]["large_diameter"] == [False] * 3 and
            branch["picons"]["reclassify"] == [False] * 3,
            "Picons selected branch")
    require(branch["cleanup_keep_qi"] == [True] * 3,
            "paired cleanup selected branch")
    require(branch["dsd_limiter"]["ice_active"] == [True] * 3 and
            branch["dsd_limiter"]["ice_too_small"] == [False] * 3 and
            branch["dsd_limiter"]["ice_too_large"] == [False] * 3 and
            branch["dsd_limiter"]["ice_final_ncmin_gate"] == [True] * 3,
            "DSD selected ice branch")
    rates = check_rate_accounting(trace)
    print(json.dumps({
        "status": "ICE_POST_SED_FATE_REPLAY_PASSED",
        "scientific_status": "INCONCLUSIVE",
        "scope": "PR504 synthetic first column, manually fixed mstep [1,2], legacy raw first-ice handoff, one nccn=None microphysics pass",
        "runtime_setup_contrast": {
            "brs_before_top_first": state.brs[0].detach().tolist(),
            "brs_after_pre_sed_reclamp_top_first": pre_sed_brs.brs[0].detach().tolist(),
            "reclamp_changes_this_chain_output": False,
            "manual_ice_mstep_by_column": [1, 2],
            "runtime_selected_main_mstep_by_column": selected_main.tolist(),
            "runtime_selected_ice_mstep_by_column": selected_ice.tolist(),
        },
        "orientation": {"sedimentation": "top-first", "microphysics": "WRF bottom-first",
                        "reported_arrays": "top-first"},
        "post_first_ice": {"qi": first.qi_after[0].detach().tolist(),
                           "ni": first.number.after[0].detach().tolist()},
        "post_full_sedimentation": {"qi": sedimented.state.qi[0].detach().tolist(),
                                     "ni": sedimented.state.ni[0].detach().tolist()},
        "early_cleanup_control": {
            "qi": early_cleanup.qi[0].flip(-1).detach().tolist(),
            "ni": early_cleanup.ni[0].flip(-1).detach().tolist(),
        },
        "snapshots": snapshots,
        "branches": branch,
        "d2_d4_applied_amounts": {
            "qi_pinuc_plus_pfrzdtc": q_created.flip(-1).detach().tolist(),
            "ni_ninuc_plus_nfrzdtc": n_created.flip(-1).detach().tolist(),
        },
        "applied_cold_rates": rates,
        "final_microphysics": {"qi": traced.qi[0].flip(-1).detach().tolist(),
                               "ni": traced.ni[0].flip(-1).detach().tolist()},
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
