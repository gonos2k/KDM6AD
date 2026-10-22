"""Value-only, same-call fp64 column capture and water accounting.

The optional C++ research tool returns state and precipitation from ONE legacy
FnResult. This module does not run WRF, RTTOV or AD or modify a physics map.
Snow/ice and graupel outputs are overlapping subsets of total precipitation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import subprocess

import numpy as np

from harness.audit_applied_budget import split_changes
from harness.native_number_qualification import apply_receipt
from harness.run_ss_case import _namelist_assignments

REQUEST = struct.Struct("<8sII4d")
RESPONSE = struct.Struct("<8sII")
MAX_LEVELS = 256
SCHEMA = "kdm6.same_call_water_budget.v1"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def array(value, shape, name):
    out = np.asarray(value, dtype="<f8")
    if out.shape != shape or not np.isfinite(out).all():
        raise ValueError(f"{name} must be finite with shape {shape}")
    return out


def same_bits(a, b):
    return a.shape == b.shape and a.tobytes() == b.tobytes()


def request_bytes(state, forcing, dt, xland, ncmin_land, ncmin_sea):
    state = np.asarray(state, dtype="<f8")
    if state.ndim != 2 or state.shape[0] != 12 or not 1 <= state.shape[1] <= MAX_LEVELS:
        raise ValueError("state requires 12 rows and 1..256 levels")
    state = array(state, state.shape, "state")
    forcing = array(forcing, (4, state.shape[1]), "forcing")
    meta = (dt, xland, ncmin_land, ncmin_sea)
    if any(isinstance(v, bool) or not np.isfinite(v) for v in meta):
        raise ValueError("metadata must be finite real scalars")
    if dt <= 0 or xland not in (1., 2.) or min(ncmin_land, ncmin_sea) < 0:
        raise ValueError("invalid dt, xland or ncmin")
    if np.any(forcing <= 0):
        raise ValueError("all four forcing fields must be positive")
    return REQUEST.pack(b"K6BUDG1\0", 1, state.shape[1], *meta) + state.tobytes() + forcing.tobytes()


def read_response(payload, state, forcing):
    """Require exact shape/length and bitwise echo of the requested operands."""
    if len(payload) < RESPONSE.size:
        raise ValueError("truncated response header")
    magic, version, levels = RESPONSE.unpack_from(payload)
    if magic != b"K6BOUT1\0" or version != 1 or not 1 <= levels <= MAX_LEVELS:
        raise ValueError("unsupported response magic, version or levels")
    if len(payload) != RESPONSE.size + (28*levels+3)*8:
        raise ValueError("response length does not match levels")
    state = array(state, (12, levels), "requested state")
    forcing = array(forcing, (4, levels), "requested forcing")
    values = np.frombuffer(payload, dtype="<f8", offset=RESPONSE.size)
    if not np.isfinite(values).all():
        raise ValueError("response contains nonfinite values")
    s = values[:12*levels].reshape(12, levels).copy()
    f = values[12*levels:16*levels].reshape(4, levels).copy()
    out = values[16*levels:28*levels].reshape(12, levels).copy()
    flux = values[-3:].copy()
    if not same_bits(state, s) or not same_bits(forcing, f):
        raise ValueError("response operands differ from request bits")
    if np.any(flux < 0) or flux[1]+flux[2] > flux[0] + 32*np.finfo(float).eps*max(1., flux[0]):
        raise ValueError("invalid total/subset precipitation diagnostics")
    return s, f, out, flux


def ledger(state, forcing, raw, clean, flux, dt):
    """Measure a residual, without treating a valid diagnostic as closure.

    The fixed 256*eps inventory-scale gate is a numerical diagnostic, declared
    independently of the measured case. It is not a bound on legacy physics.
    A failed gate is retained; no compensating residual source is invented.
    """
    state = np.asarray(state, dtype=np.float64)
    if state.ndim != 2 or state.shape[0] != 12 or state.shape[1] < 1:
        raise ValueError("requires twelve nonempty state rows")
    levels = state.shape[1]
    state = array(state, (12, levels), "state")
    forcing = array(forcing, (4, levels), "forcing")
    raw, clean = (array(v, state.shape, n) for v, n in ((raw, "raw"), (clean, "clean")))
    flux = array(flux, (3,), "precipitation")
    if np.any(forcing <= 0) or np.any(flux < 0):
        raise ValueError("forcing must be positive and precipitation nonnegative")
    weights = forcing[0]*forcing[3]
    if not np.isfinite(weights).all():
        raise ValueError("density-thickness weights overflow")
    split = split_changes(state[1:7], raw[1:7], clean[1:7], dt, weights)
    # fsum avoids loss from reducing large inventories then subtracting them.
    def weighted(a):
        return math.fsum(float(v) for v in (a*weights).ravel())
    initial, final = weighted(state[1:7]), weighted(raw[1:7])
    delta = weighted(raw[1:7]-state[1:7])
    cleanup = weighted(clean[1:7]-raw[1:7])
    applied = weighted(clean[1:7]-state[1:7])
    residual = math.fsum((delta, float(flux[0])))
    bound = 256*np.finfo(float).eps*max(1., abs(initial)+abs(final)+abs(float(flux[0])))
    return {"schema": SCHEMA, "levels": levels, "dt_seconds": dt,
            "weight_contract": {"formula": "same-call DEN * DELZ", "units": "kg_dry_air m-2",
                "rho_d_kg_m3": forcing[0].tolist(), "delz_m": forcing[3].tolist(),
                "weights_kg_m2": weights.tolist(), "column_dry_mass_kg_m2": math.fsum(weights)},
            "precipitation": {"total_export_kg_m2": float(flux[0]), "total_precip_mm": float(flux[0]),
                "snow_ice_subset_mm": float(flux[1]), "graupel_subset_mm": float(flux[2]),
                "top_influx_kg_m2": 0.,
                "contract": "total includes rain+snow+graupel+ice; subsets not added; no extra dt; zero external top inflow"},
            "water": split, "balance": {"initial_water_kg_m2": initial,
                "raw_final_water_kg_m2": final, "kernel_change_kg_m2": delta,
                "cleanup_change_kg_m2": cleanup, "applied_change_kg_m2": applied,
                "kernel_plus_export_residual_kg_m2": residual,
                "applied_plus_export_residual_kg_m2": math.fsum((applied, float(flux[0]))),
                "criterion": "abs(kernel delta + total export) <= 256*eps*max(1,abs(Win)+abs(Wout)+abs(export))",
                "numerical_gate_kg_m2": float(bound), "within_numerical_gate": bool(abs(residual) <= bound)},
            "diagnostic_complete": bool(split["algebraic_split_verified"]),
            "closed_water_budget_certified": False,
            "limits": "fixed layer measure; no RK mass/energy/number closure, named-process attribution, AD or new RTTOV/native run"}


def stage_changes(text, levels, dt):
    """Recompute the forensic trace, refusing missing/duplicate/mixed records.

    The generated runtime emits pre_sed in top-first order. All other stages
    use WRF bottom-first order. Decimal records have 17 significant digits,
    sufficient to roundtrip the captured binary64 values.
    """
    stages = ("entry", "pre_sed", "post_sed", "post_micro", "exit")
    rows = {stage: {} for stage in stages}
    columns = set()
    for line in text.splitlines():
        tokens = [part.split("=", 1) for part in line.split()]
        if any(len(t) != 2 for t in tokens) or len(dict(tokens)) != len(tokens):
            raise ValueError("malformed or duplicate trace keys")
        row = dict(tokens)
        stage, kind = row["stage"], row["record"]
        if (stage not in rows or kind not in ("level", "column") or int(row["column"]) != 0 or
                float(row["dt_call"]) != dt or int(row["loops"]) != 1 or float(row["dtcld"]) != dt or
                int(row["subcycle"]) != {"entry": -1, "exit": 1}.get(stage, 0)):
            raise ValueError("trace case/stage metadata differ")
        if kind == "column":
            if stage in columns:
                raise ValueError("duplicate trace column record")
            columns.add(stage)
            continue
        index = int(row["level"])
        if index not in range(levels) or index in rows[stage]:
            raise ValueError("duplicate or invalid trace level")
        rows[stage][index] = row
    if columns != set(stages) or any(len(v) != levels for v in rows.values()):
        raise ValueError("missing stage/level records")
    fields = ("qv", "qc", "qr", "qi", "qs", "qg")
    q, weights = {}, None
    for stage in stages:
        ordered = [rows[stage][k] for k in range(levels)]
        if stage == "pre_sed":
            ordered.reverse()
        f = array([[float(r[name]) for r in ordered] for name in ("DEN_kg_m3", "DELZ_m")],
                  (2, levels), "trace forcing")
        if np.any(f <= 0) or (weights is not None and not same_bits(f, weights)):
            raise ValueError("trace weights differ across stages")
        weights = f
        q[stage] = array([[float(r[name+"_kg_kg"]) for r in ordered] for name in fields],
                         (6, levels), "trace water")
    transitions = list(zip(stages[:-1], stages[1:])) + [("entry", "exit")]
    result = {}
    for before, after in transitions:
        # Preserve the published diagnostic's multiplication order explicitly.
        delta = (q[after]-q[before])*weights[0]*weights[1]
        result[before+"_to_"+after+"_kg_m2"] = math.fsum(delta.ravel())
    for name, before, after in (("sedimentation", "pre_sed", "post_sed"),
                                ("microphysics", "post_sed", "post_micro")):
        delta = (q[after]-q[before])*weights[0]*weights[1]
        result[name+"_species_kg_m2"] = {field: math.fsum(delta[k]) for k, field in enumerate(fields)}
    return result


def validate_controls(report, receipt, nml, xland):
    """Bind non-array KDM controls to the saved native source, before execution."""
    def first(key):
        return float(nml[key][0].replace("D", "e").replace("d", "e"))
    c = report["kernel_contract"]
    denominator = first("time_step_fract_den")
    if denominator <= 0:
        raise ValueError("invalid fractional time step denominator")
    dt = first("time_step") + first("time_step_fract_num")/denominator
    if (c["dt_seconds"] != dt or c["xland"] != xland or
            c["ncmin_land_sea"] != [first("ncmin_land"), first("ncmin_sea")]):
        raise ValueError("KDM scalar controls differ from pinned native inputs")
    for key in ("trace", "checkpoint", "namelist"):
        if report["input_sha256"][key] != receipt["source_bindings"][key]:
            raise ValueError("report source binding differs from receipt")
    b = receipt["source_bindings"]
    snapshot = report["native_snapshot"]
    if (snapshot["native_indices_1based"] != [b["i"], b["j"]] or
            snapshot["native_levels"] != b["levels"]):
        raise ValueError("native snapshot differs from receipt")


def run(report_path, admission_path, namelist, checkpoint, executable, workspace, output):
    paths = [Path(p).resolve() for p in (report_path, admission_path, namelist, checkpoint, executable)]
    report_path, admission_path, namelist, checkpoint, executable = paths
    pins = {str(p): sha(p) for p in paths}
    if Path(output).exists() or Path(output).is_symlink():
        raise ValueError("output must be new")
    report = json.loads(report_path.read_text())
    if report.get("schema") != "kdm6.microphysics_observation_ad.native_dry_numbers.v1":
        raise ValueError("requires the versioned dry-number composition report")
    receipt = json.loads(admission_path.read_text())
    boundary = report["number_boundary"]
    if boundary["admission"] != receipt:
        raise ValueError("report and admission differ")
    f = array(receipt["base_forcing"], (4, receipt["levels"]), "base forcing")
    original = array(receipt["base_volume_state"], (12, receipt["levels"]), "base volume state")
    dry, _ = apply_receipt(receipt, original, f, receipt["source_bindings"], sha(admission_path))
    s = dry.copy()
    s[7:11] *= f[0]
    if not same_bits(s, np.asarray(boundary["kernel_volume_input"], dtype="<f8")):
        raise ValueError("internal KDM operands differ from the admitted roundtrip")
    if sha(namelist) != receipt["source_bindings"]["namelist"]:
        raise ValueError("namelist does not match receipt")
    if sha(checkpoint) != receipt["source_bindings"]["checkpoint"]:
        raise ValueError("checkpoint does not match receipt")
    nml = _namelist_assignments(namelist.read_text())
    def first(key):
        return float(nml[key][0].replace("D", "e").replace("d", "e"))
    if any(first(k) != v for k, v in {"mp_physics": 137, "mp_zero_out": 2, "mp_zero_out_all": 0}.items()):
        raise ValueError("requires the captured interior MP137 cleanup path")
    threshold = float(np.float32(first("mp_zero_out_thresh")))
    if not np.isfinite(threshold) or threshold < 0:
        raise ValueError("invalid cleanup threshold")
    c = report["kernel_contract"]
    if c["physics_variant"] != 0 or c["dry_number"] != 0:
        raise ValueError("requires legacy/internal-volume KDM")
    from netCDF4 import Dataset  # private native snapshot dependency, only for capture
    binding = receipt["source_bindings"]
    with Dataset(checkpoint) as dataset:
        xland_field = dataset.variables["XLAND"]
        if xland_field.dimensions != ("Time", "south_north", "west_east"):
            raise ValueError("unexpected native XLAND layout")
        xland = xland_field[0, binding["j"]-1, binding["i"]-1]
        if np.ma.is_masked(xland):
            raise ValueError("native XLAND is missing")
    validate_controls(report, receipt, nml, float(xland))
    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=False)
    request, response = workspace/"request.bin", workspace/"response.bin"
    request.write_bytes(request_bytes(s, f, c["dt_seconds"], c["xland"], *c["ncmin_land_sea"]))
    env = dict(os.environ, OMP_NUM_THREADS="1", MKL_NUM_THREADS="1", OMP_THREAD_LIMIT="1", OPENBLAS_NUM_THREADS="1")
    completed = subprocess.run([str(executable), "--input", str(request), "--output", str(response)],
                               env=env, capture_output=True, text=True, check=True)
    (workspace/"tool.log").write_text(completed.stdout+completed.stderr)
    s, f, raw, flux = read_response(response.read_bytes(), s, f)
    clean = raw.copy()
    clean[1] = np.maximum(raw[1], 0.)
    clean[2:7] = np.where(raw[2:7] < threshold, 0., raw[2:7])
    result = ledger(s, f, raw, clean, flux, c["dt_seconds"])
    prior_raw = array(boundary["kernel_volume_output"], s.shape, "prior raw output")
    result.update(kernel_contract=c, number_boundary_version=boundary["version"],
        native_snapshot=report["native_snapshot"], source_sha256=pins,
        request_sha256=sha(request), response_sha256=sha(response),
        same_call={"KDM_calls": 1, "precision": "binary64", "state_in": s.tolist(),
            "forcing_in": f.tolist(), "state_out": raw.tolist(), "clean_after": clean.tolist(),
            "input_echo_bitwise_equal": True},
        cleanup={"mode": 2, "threshold": threshold, "no_water_compensation": True},
        comparison_to_prior={"state_out_raw_bit_equal": same_bits(raw, prior_raw),
            "state_out_maxabs_difference": float(np.max(abs(raw-prior_raw))),
            "clean_water_raw_bit_equal": same_bits(clean[1:7], np.asarray(report["clean_after"], dtype="<f8")[1:7])})
    if any(sha(p) != pin for p, pin in pins.items()):
        raise RuntimeError("source inputs changed during capture")
    serialized = json.dumps(result, indent=2, allow_nan=False)+"\n"
    with Path(output).open("x") as stream:
        stream.write(serialized)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("report", "admission", "namelist", "checkpoint", "executable", "workspace", "output"):
        parser.add_argument("--"+name, required=True, type=Path)
    args = parser.parse_args()
    result = run(args.report, args.admission, args.namelist, args.checkpoint, args.executable, args.workspace, args.output)
    print(json.dumps({"diagnostic_complete": result["diagnostic_complete"], **result["balance"]}, indent=2))
