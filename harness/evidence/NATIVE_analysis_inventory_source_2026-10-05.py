#!/usr/bin/env python3
"""Signed state-inventory changes from retained analysis arrays; no model run.

Use the existing G33 water species and two state functions, with an immutable
background measure at every endpoint. No boundary flux, phase-rate or work term
is inferred from a state difference. This does not perform an S17 closure test.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
from pathlib import Path
import subprocess
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))
import g33_refine_analyze as thermo  # noqa: E402

FIELDS = ROOT / "harness/evidence/NATIVE_KMA_analysis_fields_2026-10-05.npz"
WINDOW = ROOT / "harness/evidence/NATIVE_KMA_window_arrays_2026-10-05.npz"
RECEIPT = ROOT / "harness/evidence/NATIVE_KMA_window_result_2026-10-05.json"
PAIRS = {"analysis_increment": ("xb", "xa"),
         "slot_analysis_difference": ("xslot_b", "xslot_a"),
         "background_model_net_change": ("xb", "xslot_b"),
         "analysis_model_net_change": ("xa", "xslot_a")}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    receipt = json.loads(RECEIPT.read_text())
    if sha(FIELDS) != receipt["full_domain_fields_sha256"] or sha(WINDOW) != receipt["arrays_sha256"]:
        raise ValueError("retained native inputs do not match their execution receipt")
    with np.load(FIELDS, allow_pickle=False) as archive:
        values = {key: archive[key].copy() for key in archive.files}
    with np.load(WINDOW, allow_pickle=False) as archive:
        initial = archive["initial_state"].copy()
        forcing = archive["initial_forcing"].copy()
    if forcing.shape != (4, 39) or values["xb_qv"].shape != (1, 39):
        raise ValueError("this calculation is limited to the retained native C5 column")
    if not np.array_equal(values["xb_qv"][0].view(np.uint64), initial[1].view(np.uint64)):
        raise ValueError("background humidity differs from the retained initial state")
    if int(values["sub_idx"][0]) != receipt["selected_column"]["flat_b"]:
        raise ValueError("selected column identity differs")
    rho_m, pii, _, dz = forcing
    rho_d = rho_m / (1.0 + values["xb_qv"][0])
    if not np.isfinite(forcing).all() or np.any(rho_d <= 0) or np.any(dz <= 0):
        raise ValueError("invalid frozen column measure")
    measures = {"fixed_background_dry": rho_d * dz, "operator_moist": rho_m * dz}
    states = {}
    for prefix in ("xb", "xa", "xslot_b", "xslot_a"):
        fields = {s: values[f"{prefix}_{s}"][0] for s in ("th",) + thermo.MASS}
        if any(not np.isfinite(v).all() for v in fields.values()):
            raise ValueError(f"nonfinite {prefix} state")
        if any(np.any(fields[s] < 0) for s in thermo.MASS):
            raise ValueError(f"negative water species in {prefix}")
        run = {("state", s, 0, k): float(v) for s, array in fields.items()
               for k, v in enumerate(array)}
        run.update({("forcing", "pii", 0, k): float(v) for k, v in enumerate(pii)})
        states[prefix] = dict(fields=fields,
            phase_enthalpy=np.array([thermo._h_consistent(run, "state", 0, k) for k in range(39)]),
            operator_potential=np.array([thermo._h_code(run, "state", 0, k) for k in range(39)]))

    inventories, differences, identities = {}, {}, {}
    for name, weight in measures.items():
        inventories[name] = {}
        differences[name] = {}
        for prefix, state in states.items():
            water = {s: math.fsum((weight * state["fields"][s]).tolist()) for s in thermo.MASS}
            inventories[name][prefix] = dict(water_kg_m2=math.fsum(water.values()),
                species_kg_m2=water,
                phase_enthalpy_J_m2=math.fsum((weight * state["phase_enthalpy"]).tolist()),
                operator_potential_J_m2=math.fsum((weight * state["operator_potential"]).tolist()))
        for label, (before, after) in PAIRS.items():
            a, b = states[after], states[before]
            water = {s: math.fsum((weight * (a["fields"][s] - b["fields"][s])).tolist())
                     for s in thermo.MASS}
            differences[name][label] = dict(water_kg_m2=math.fsum(water.values()),
                species_kg_m2=water,
                phase_enthalpy_J_m2=math.fsum((weight * (a["phase_enthalpy"]-b["phase_enthalpy"])).tolist()),
                operator_potential_J_m2=math.fsum((weight * (a["operator_potential"]-b["operator_potential"])).tolist()))
        d = differences[name]
        identities[name] = {key: d["slot_analysis_difference"][key]
            - math.fsum((d["analysis_increment"][key], d["analysis_model_net_change"][key],
                         -d["background_model_net_change"][key]))
            for key in ("water_kg_m2", "phase_enthalpy_J_m2", "operator_potential_J_m2")}

    # A constant reference offset per kg water changes delta-H by offset*delta-W.
    # This is a coordinate identity, not an alternative fitted thermodynamic law.
    delta_w = differences["fixed_background_dry"]["analysis_increment"]["water_kg_m2"]
    result = dict(
        artifact_role="offline_conditional_analysis_inventory",
        executed_path="retained arrays -> fixed measures -> existing G33 state functions",
        selected_column=receipt["selected_column"]["flat_b"], n_native_levels=39,
        fixed_forcing=dict(rho_m=rho_m.tolist(), pii=pii.tolist(), dz=dz.tolist()),
        fixed_background_rho_d=rho_d.tolist(),
        inventories=inventories, signed_differences=differences,
        endpoint_difference_identity_residuals=identities,
        enthalpy_convention=dict(reference_temperature_K=thermo.T0C,
            cpd=thermo.CPD, cpv=thermo.CPV, cliq=thermo.CLIQ, cice=thermo.CICE,
            latent_vapor_at_reference_J_kg=thermo.XLV, latent_fusion_at_reference_J_kg=thermo.XLF,
            phase_function="g33_refine_analyze._h_consistent",
            operator_potential="g33_refine_analyze._h_code",
            is_approved_host_enthalpy=False),
        reference_offset_identity=dict(formula="delta_H_new = delta_H_old + C_water * delta_W",
            applies_to="g33_refine_analyze._h_consistent with a common offset in all water phases",
            coefficient_delta_W_kg_m2=delta_w),
        missing_closure_terms=dict(net_boundary_mass_flux=None, net_boundary_enthalpy_flux=None,
                                  external_heat=None, pressure_work=None, applied_process_extents=None),
        interpretation=dict(analysis_inventory_change_is_not_model_conservation_residual=True,
            model_net_changes_are_not_measured_boundary_fluxes=True,
            is_water_budget_closed=False, is_S17_enthalpy_closed=False,
            scientific_analysis_approved=False),
        regime_definition=dict(model="background slot-time sum over native qc+qi+qs exceeds 1e-5 kg/kg",
            observation="valid KMA IR105 below 270 K", is_independent_cloud_mask=False,
            recorded_label="cloudy_clear", observed_IR105_K=float(values["y_bt"][0, 5])),
        source_sha256=sha(__file__), input_hashes={str(p.relative_to(ROOT)): sha(p) for p in (FIELDS, WINDOW, RECEIPT)},
        state_function_source_sha256=sha(ROOT / "harness/g33_refine_analyze.py"),
        arithmetic_environment=dict(python=platform.python_version(), numpy=np.__version__),
        repository_head=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps(differences["fixed_background_dry"], indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
