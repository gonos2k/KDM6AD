#!/usr/bin/env python3
"""Read one retained host snapshot and compare declared layer-mass measures.

No forecast, physics or radiance run. Float64 evaluation of decoded fields is
separate from the explicitly reconstructed NumPy float32 arithmetic; neither is
a capture of the host's live RK/physics operands or a boundary-flux budget.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
from pathlib import Path
import platform

import netCDF4
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HOST = Path("/Users/yhlee/KDM6AD-k/host/KIM-meso_v1.0")
EXECUTION_SOURCE = ROOT / "harness/evidence/NATIVE_KMA_window_source_2026-10-05.py"
RECEIPT = ROOT / "harness/evidence/NATIVE_KMA_window_result_2026-10-05.json"
WINDOW = ROOT / "harness/evidence/NATIVE_KMA_window_arrays_2026-10-05.npz"
FIELDS = ROOT / "harness/evidence/NATIVE_KMA_analysis_fields_2026-10-05.npz"
HOST_SOURCES = (
    "Registry/registry.hyb_coord", "share/module_model_constants.F",
    "dyn_em/module_em.F", "dyn_em/module_big_step_utilities_em.F",
    "dyn_em/module_first_rk_step_part1.F", "dyn_em/module_small_step_em.F",
    "dyn_em/nest_init_utils.F", "dyn_em/module_initialize_real.F",
    "phys/module_physics_init.F")
VECTORS = ("DNW", "ZNW", "C1H", "C2H", "C3H", "C4H", "C3F", "C4F")
WATER = ("qv", "qc", "qr", "qi", "qs", "qg")


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    tree = ast.parse(EXECUTION_SOURCE.read_text())
    forecast = next(Path(ast.literal_eval(n.value.args[0])) for n in tree.body
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "FORECAST" for t in n.targets))
    receipt = json.loads(RECEIPT.read_text())
    if sha(forecast) != receipt["forecast_sha256"] or sha(WINDOW) != receipt["arrays_sha256"] or sha(FIELDS) != receipt["full_domain_fields_sha256"]:
        raise ValueError("retained snapshot or array hash differs from the execution receipt")
    with np.load(WINDOW, allow_pickle=False) as z:
        forcing, qv = z["initial_forcing"].copy(), z["initial_state"][1].copy()
    with np.load(FIELDS, allow_pickle=False) as z:
        states = {k: z[k].copy() for k in z.files}
    t, j, i = 1, 156, 72
    with netCDF4.Dataset(forecast) as ds:
        when = str(netCDF4.chartostring(ds["Times"][t:t+1])[0])
        if when != "2025-07-19_00:00:20" or int(ds.HYBRID_OPT) != 2 or int(ds.HYPSOMETRIC_OPT) != 2:
            raise ValueError("unexpected retained snapshot configuration")
        mu, mub, ptop = (float(ds["MU"][t,j,i]), float(ds["MUB"][t,j,i]), float(ds["P_TOP"][t]))
        vector = {k: np.asarray(ds[k][t], dtype=np.float64) for k in VECTORS}
        mapfactor = float(ds["MAPFAC_M"][t,j,i])
        field_metadata = {k: dict(dtype=str(ds[k].dtype), units=getattr(ds[k], "units", ""),
            description=getattr(ds[k], "description", "")) for k in ("MU", "MUB", "P_TOP") + VECTORS}
        saved_p = np.asarray(ds["P"][t,:,j,i], dtype=np.float64) + np.asarray(ds["PB"][t,:,j,i], dtype=np.float64)
    if forcing.shape != (4,39) or not np.array_equal(saved_p, forcing[2]):
        raise ValueError("snapshot centers do not match retained native forcing")
    if np.any(vector["DNW"] >= 0) or not all(np.isfinite(v).all() for v in vector.values()):
        raise ValueError("invalid native vertical coordinate")
    gravity = 9.81  # Nominal source constant; float32 diagnostic is explicit below.
    total = mu + mub
    pressure_thickness = -(vector["C1H"]*total + vector["C2H"])*vector["DNW"]
    hybrid = pressure_thickness/gravity
    diagnostic = forcing[0]/(1+qv)*forcing[3]
    p_interface = vector["C3F"]*total + vector["C4F"] + ptop
    p_mid = vector["C3H"]*total + vector["C4H"] + ptop
    if np.any(hybrid <= 0) or np.any(p_interface <= 0) or np.any(np.diff(p_interface) >= 0):
        raise ValueError("invalid reconstructed dry-pressure coordinate")
    hypsometric = p_mid*np.log(p_interface[:-1]/p_interface[1:])/gravity
    # Deliberate float32 reconstruction, not an observed Fortran intermediate.
    total32 = np.float32(np.float32(mu)+np.float32(mub))
    metric32 = np.float32(np.float32(vector["C1H"])*total32 + np.float32(vector["C2H"]))
    thickness32 = np.float32(-metric32*np.float32(vector["DNW"]))
    mass32 = np.float32(thickness32/np.float32(gravity))
    measures = {"hybrid_coordinate_decoded_f64": hybrid,
                "background_diagnostic_density_times_dz": diagnostic,
                "hypsometric_log_pressure_depth_f64": hypsometric}
    deltas = {}
    for name, w in measures.items():
        deltas[name] = {}
        for label, before, after in (("initial_analysis", "xb", "xa"),
                                     ("slot_analysis", "xslot_b", "xslot_a")):
            terms = {s: math.fsum((w*(states[f"{after}_{s}"][0]-states[f"{before}_{s}"][0])).tolist()) for s in WATER}
            deltas[name][label] = dict(species_kg_m2=terms, total_water_kg_m2=math.fsum(terms.values()))
    result = dict(
        artifact_role="one_snapshot_host_mass_reference_audit", model_or_radiance_executed=False,
        selected=dict(time_index=t, time_utc=when, i_zero_based=i, j_zero_based=j, flat_b=j*234+i),
        coordinate=dict(hybrid_opt=2, hypsometric_opt=2, MU_Pa=mu, MUB_Pa=mub, P_TOP_Pa=ptop,
                        nominal_gravity_m_s2=gravity, MAPFAC_M=mapfactor, vectors={k:v.tolist() for k,v in vector.items()}),
        field_metadata=field_metadata,
        measure_definitions=dict(hybrid="-(C1H*(MU+MUB)+C2H)*DNW/g",
            diagnostic="rho_m/(1+initial_background_qv)*dz",
            hypsometric="p_dry_mid*log(p_dry_lower/p_dry_upper)/g"),
        layer_weights_kg_m2={k:v.tolist() for k,v in measures.items()},
        total_layer_weights_kg_m2={k:math.fsum(v.tolist()) for k,v in measures.items()},
        comparison=dict(max_diagnostic_minus_hybrid_relative_to_hybrid=float(np.max(abs(diagnostic-hybrid)/hybrid)),
            worst_native_bottom_up_layer=int(np.argmax(abs(diagnostic-hybrid)/hybrid)),
            max_diagnostic_minus_hypsometric_relative=float(np.max(abs(diagnostic-hypsometric)/hypsometric)),
            decoded_pressure_depth_sum_Pa=math.fsum(pressure_thickness.tolist()), full_column_MU_plus_MUB_Pa=total),
        explicit_numpy_f32_reconstruction=dict(is_live_Fortran_trace=False, total_mass_pressure_Pa=float(total32),
            pressure_depth_terms_f64_sum_Pa=math.fsum(thickness32.astype(float).tolist()),
            layer_mass_terms_f64_sum_kg_m2=math.fsum(mass32.astype(float).tolist())),
        analysis_inventory_changes=deltas,
        scope=dict(native_snapshot_not_host_staged_operands=True, no_mapfactor_in_per_physical_m2_measure=True,
            physical_cell_total_not_evaluated=True, optical_density_policy_changed=False,
            runtime_density_policy_changed=False, complete_S2_approval=False, complete_S17_approval=False,
            net_boundary_mass_flux=None, net_boundary_enthalpy_flux=None),
        input_hashes={str(p):sha(p) for p in (forecast, WINDOW, FIELDS, RECEIPT)},
        active_private_source_hashes={str(HOST/p):sha(HOST/p) for p in HOST_SOURCES},
        source_sha256=sha(__file__), environment=dict(python=platform.python_version(), numpy=np.__version__, netCDF4=netCDF4.__version__))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    print(json.dumps(result["total_layer_weights_kg_m2"]))
    print(json.dumps(result["comparison"]))


if __name__ == "__main__":
    main()
