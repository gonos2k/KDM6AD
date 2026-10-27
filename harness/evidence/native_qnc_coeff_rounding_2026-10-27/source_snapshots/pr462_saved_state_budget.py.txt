"""Decompose the saved seven-cell QNC PD→RK3 update in exact raw coordinates.

Every input is an already stored binary32 word. Fractions describe exact
algebra on those words and isolate later f32 stage/store differences. They
are not physical particle-number units or an emitted-FMA trace.
"""
from __future__ import annotations

from fractions import Fraction

import numpy as np

from harness.analyze_native_qnc_state7_trace import STAR_IJK
from harness.analyze_qnc_weighted_ledger import analyze_weighted_ledger


def _fraction(bits: int) -> Fraction:
    value = np.asarray([bits], dtype=np.uint32).view(np.float32)[0]
    if not np.isfinite(value):
        raise ValueError("state budget requires finite binary32 words")
    return Fraction.from_float(float(value))


def _amount(value: Fraction) -> dict[str, object]:
    return {"exact": str(value), "approximately": float(value)}


def analyze_saved_state_budget(state_trace, shared_trace: dict, *, run_id: str) -> dict:
    owner = shared_trace["owner_call_id"]
    records = shared_trace["records"]
    prior_face_ledger = analyze_weighted_ledger(shared_trace, run_id=run_id)
    totals = {name: Fraction(0) for name in
              ("face_boundary", "pd_scalar_source", "pd_storage_arithmetic",
               "advection_tendency_arithmetic", "rk_state_arithmetic", "state_change")}
    cells = {}

    for coord in STAR_IJK:
        i, j, k = coord
        face_coord = (i, k, j)

        def state(stage: str, field: str) -> Fraction:
            rk = 0 if stage == "PRE_MICROPHYSICS" else 3
            return _fraction(int(state_trace.at(coord, rk, stage, field).bits))

        def face(field: str) -> Fraction:
            return _fraction(records[(owner, "RK3_POST", *face_coord, field)])

        def difference(upper: str, lower: str, low_upper: str, low_lower: str) -> Fraction:
            return face(upper) - face(lower) + face(low_upper) - face(low_lower)

        pd, rk = "RKSCALAR_PD_BEFORE", "RKSCALAR_BEFORE"
        c1, c2 = state(pd, "C1H"), state(pd, "C2H")
        mu_base, mu_pd = state(pd, "MU_BASE"), state(pd, "MU_OLD_ARG")
        dt, source = state(pd, "DT_RK"), state(pd, "SCALAR_TEND")
        old_pre, old_saved = state(pd, "SCALAR_OLD"), state("RKSCALAR_PD_AFTER", "SCALAR_OLD")
        if state(pd, "MU_NEW_ARG") != mu_pd or state(rk, "SCALAR_TEND") != 0:
            raise ValueError(f"PD mass/source contract differs at {coord}")
        a_pd = c1 * (mu_pd + mu_base) + c2
        a_old = c1 * (state(rk, "MU_OLD") + state(rk, "MU_BASE")) + c2
        a_new = c1 * (state(rk, "MU_NEW") + state(rk, "MU_BASE")) + c2
        if a_pd == 0 or a_new == 0 or a_pd != a_old:
            raise ValueError(f"PD and final RK old mass factor disagree at {coord}")
        if state("RKSCALAR_PD_AFTER", "SCALAR_OLD") != state(rk, "SCALAR_OLD"):
            raise ValueError(f"prepared old buffer not handed to RK at {coord}")
        mx, rz = face("MSFTX"), face("RDZW")
        msfty = state(rk, "MSFTY")
        if (mx == 0 or rz == 0 or msfty == 0 or
                int(state_trace.at(coord, 3, rk, "MSFTY").bits) != records[(owner, "RK3_POST", *face_coord, "MSFTY")]):
            raise ValueError(f"zero/mismatched map metric at {coord}")
        shared_dt_bits = int(shared_trace["calls"][owner]["dt_bits_hex"], 16)
        if state(rk, "DT_RK") != dt or dt != _fraction(shared_dt_bits):
            raise ValueError(f"RK and shared-face timestep differ at {coord}")
        rx, ry = face("RDX"), face("RDY")
        face_tendency = (
            -rz * difference("FZ_TOP", "FZ_BOTTOM", "FZ_LOW_TOP", "FZ_LOW_BOTTOM")
            -mx * rx * difference("FX_EAST", "FX_WEST", "FX_LOW_EAST", "FX_LOW_WEST")
            -mx * ry * difference("FY_NORTH", "FY_SOUTH", "FY_LOW_NORTH", "FY_LOW_SOUTH")
        )
        recorded_adv = state(rk, "ADVECT_TEND")
        prepared_exact = (a_pd * old_pre + dt * source) / a_pd
        prepared_effective = old_saved
        baseline = (a_old * prepared_exact + dt * face_tendency * msfty) / a_new
        with_pd = (a_old * prepared_effective + dt * face_tendency * msfty) / a_new
        with_adv = (a_old * prepared_effective + dt * recorded_adv * msfty) / a_new
        actual = state("RKSCALAR_AFTER", "QNC")
        four = {
            "exact_saved_face_and_pd_baseline": baseline,
            "pd_old_buffer_storage_effect": with_pd - baseline,
            "advection_tendency_arithmetic_effect": with_adv - with_pd,
            "final_rk_arithmetic_and_storage_effect": actual - with_adv,
        }
        if sum(four.values()) != actual:
            raise ValueError(f"target-style decomposition did not close at {coord}")
        beta = -1 / (mx * msfty * rz)
        terms = {
            "face_boundary": beta * dt * msfty * face_tendency,
            "pd_scalar_source": beta * dt * source,
            "pd_storage_arithmetic": beta * a_old * (prepared_effective - prepared_exact),
            "advection_tendency_arithmetic": beta * dt * msfty * (recorded_adv - face_tendency),
            "rk_state_arithmetic": beta * a_new * (actual - with_adv),
        }
        state_change = beta * (a_new * actual - a_old * old_pre)
        if sum(terms.values()) != state_change:
            raise ValueError(f"weighted state ledger did not close at {coord}")
        for name, value in terms.items():
            totals[name] += value
        totals["state_change"] += state_change
        cells[f"i{i}_j{j}_k{k}"] = {
            "pd_prepared_old_exact": _amount(prepared_exact),
            "pd_prepared_old_recorded": _amount(prepared_effective),
            "recorded_face_tendency_exact_algebra": _amount(face_tendency),
            "recorded_advect_tendency": _amount(recorded_adv),
            "rk_old_mass_factor_exact": _amount(a_old),
            "rk_new_mass_factor_exact": _amount(a_new),
            "immediate_rk_qnc_recorded": _amount(actual),
            "target_style_four_terms": {name: _amount(value) for name, value in four.items()},
            "weighted_terms": {name: _amount(value) for name, value in terms.items()},
            "weighted_state_change": _amount(state_change),
            "closure_exact": "0",
        }
    if totals["state_change"] != sum(value for name, value in totals.items() if name != "state_change"):
        raise ValueError("seven-cell weighted state ledger did not close")
    face_total = Fraction(prior_face_ledger["exact_face_total"]["exact"])
    residual = Fraction(prior_face_ledger["recorded_minus_exact_face"]["exact"])
    if totals["face_boundary"] != 20 * face_total:
        raise ValueError("new state ledger face term differs from prior 30-face perimeter")
    if totals["advection_tendency_arithmetic"] != 20 * residual:
        raise ValueError("new state ledger advection term differs from prior f32 residual")
    return {
        "schema": "kdm6.native_qnc_saved_state_budget.v1",
        "run_id": run_id,
        "state_trace_sha256": state_trace.sha256,
        "shared_face_trace_sha256": shared_trace["sha256"],
        "native_operator_weight": "beta=-1/(MSFTX*MSFTY*RDZW), not certified physical mass/volume",
        "cells": cells,
        "seven_cell_terms": {name: _amount(value) for name, value in totals.items()},
        "seven_cell_closure_exact": "0",
        "prior_face_internal_cancellation_pairs": len(prior_face_ledger["internal_face_component_pairs"]),
        "prior_face_perimeter_incidences": prior_face_ledger["perimeter_face_incidences"],
        "limits": {
            "saved_binary32_inputs_only": True,
            "physical_number_units_certified": False,
            "full_timestep_or_domain_budget_certified": False,
            "emitted_fma_instruction_certified": False,
            "admissible_analysis_or_RTTOV_cost": False,
        },
    }
