"""One native-column, value-only 2x2 experiment; no operational map is changed.

Runs each fixed experimental map in a fresh process with tracing off/on. Only
the first ice handoff and ice transfer rule vary; the main chain stays Legacy.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import subprocess

import numpy as np

from harness.same_call_water_budget import REQUEST, read_response, request_bytes, sha, same_bits, ledger

MODES = ("raw_cap", "norm_cap", "raw_actual", "norm_actual")
WATER = ("qv", "qc", "qr", "qi", "qs", "qg")
REQUEST_SHA = "4867805f5318f1ad28b05101ffc583d50000309ed80b81c4379fb9c9e77082e2"
BASELINE_RESPONSE_SHA = "93a357b011bab8724a1ff84ce278927abc24f88d9b5f42e1d10f94fa3949cf8d"


def parse_records(path):
    result = []
    for line in Path(path).read_text().splitlines():
        row = {}
        for token in line.split():
            key, value = token.split("=", 1)
            if key in row:
                raise ValueError("duplicate trace key")
            row[key] = value
        if not row:
            raise ValueError("empty trace record")
        result.append(row)
    return result


def number(row, name):
    value = float(row[name])
    if not math.isfinite(value):
        raise ValueError("nonfinite trace value")
    return value


def index(row, name):
    value = number(row, name)
    if not value.is_integer():
        raise ValueError("fractional trace index")
    return int(value)


def state_equivalent_budget(before, after, departure, arrival, weights):
    """Actual bottom departure differs from net bottom-layer depletion.

    All amounts use the declared state coordinate, not dimensional validation
    of the raw-velocity branch's attempted flux expressions.
    """
    arrays = [np.asarray(a, dtype=np.float64) for a in (before, after, departure, arrival, weights)]
    before, after, departure, arrival, weights = arrays
    if before.ndim != 1 or not before.size or any(a.shape != before.shape for a in arrays):
        raise ValueError("matched nonempty one-dimensional arrays required")
    if any(not np.isfinite(a).all() for a in arrays) or np.any(weights <= 0):
        raise ValueError("finite values and positive measures required")
    if any(np.any(a < 0) for a in arrays[:4]) or arrival[0] != 0:
        raise ValueError("nonnegative states/transfers and zero top inflow required")
    local = after-before+departure-arrival
    scale = np.maximum(1e-30, abs(before)+abs(after)+abs(departure)+abs(arrival))
    if np.any(abs(local) > 64*np.finfo(float).eps*scale):
        raise ValueError("state update and applied transfers disagree")
    out = departure*weights
    incoming = arrival*weights
    gaps = out[:-1]-incoming[1:]
    delta = math.fsum((after-before)*weights)
    bottom = float(out[-1])
    defect = math.fsum(gaps)
    residual = math.fsum((delta, bottom, defect))
    gate = 256*np.finfo(float).eps*max(1e-30,
        math.fsum((abs(before)+abs(after))*weights)+abs(bottom)+math.fsum(abs(gaps)))
    if abs(residual) > gate:
        raise ValueError("state-equivalent transfer identity failed")
    return {"column_change": delta, "actual_bottom_departure": bottom,
            "bottom_arrival": float(incoming[-1]),
            "net_bottom_depletion": float((before[-1]-after[-1])*weights[-1]),
            "interface_gaps": gaps.tolist(), "interface_gap_sum": defect,
            "identity_residual": residual, "numerical_gate": gate,
            "state_plus_bottom": math.fsum((delta, bottom))}


def ice_metrics(path, mode, s, f):
    actual = mode.endswith("actual")
    if actual:
        rows = parse_records(str(path)+".layers.tsv")
        if any(r.get("schema") != "kdm6.ice_factorial_layer.v1" or r.get("factor_mode") != mode for r in rows):
            raise ValueError("wrong conservative trace mode/schema")
        out_names = ("out_applied_qi", "out_applied_ni")
        in_names = ("arrival_applied_qi", "arrival_applied_ni")
    else:
        rows = [r for r in parse_records(path) if r.get("record") == "ice_layer"]
        if any(r.get("factor_mode") != mode for r in rows):
            raise ValueError("wrong legacy trace mode")
        out_names = ("out_applied_qi_kg_kg", "out_applied_ni_number_m3")
        in_names = ("arrival_applied_qi_kg_kg", "arrival_applied_ni_number_m3")
    levels = s.shape[1]
    if [index(r, "level_top0") for r in rows] != list(range(levels)):
        raise ValueError("missing, duplicate or unordered ice layers")
    if any(index(r, "column") != 0 or index(r, "substep") != 1 or
           number(r, "mstep") != 1 or number(r, "dtcld_s") != 20. or r.get("order") != "top_first" for r in rows):
        raise ValueError("only the selected single-substep native case is supported")
    rho = np.array([number(r, "DEND_kg_m3") for r in rows])
    dz = np.array([number(r, "DELZ_m") for r in rows])
    if not same_bits(rho, f[0, ::-1].copy()) or not same_bits(dz, f[3, ::-1].copy()):
        raise ValueError("ice trace measure differs from request")
    result = {}
    for j, field in enumerate(("QI", "NI")):
        before_name, after_name = (("QI_before_kg_kg", "QI_after_kg_kg") if j == 0 else
                                   ("NI_before_number_m3", "NI_after_number_m3"))
        values = [np.array([number(r, name) for r in rows]) for name in
                  (before_name, after_name, out_names[j], in_names[j])]
        expected = np.maximum(s[4, ::-1], 0) if j == 0 else np.clip(s[9, ::-1], 0, 1e6)
        if not same_bits(values[0], expected.copy()):
            raise ValueError("first ice state differs from request/entry clamps")
        result[field] = state_equivalent_budget(*values, rho*dz if j == 0 else dz)
    return result


def water_stages(path, mode, f):
    rows = parse_records(str(path)+".water.tsv")
    stages = ("pre_sed", "post_sed", "post_micro")
    if len(rows) != 3*f.shape[1]:
        raise ValueError("wrong water-stage record count")
    result = {}
    for stage in stages:
        group = [r for r in rows if r.get("stage") == stage]
        if [index(r, "level_bottom0") for r in group] != list(range(f.shape[1])):
            raise ValueError("missing/duplicate water-stage level")
        if any(r.get("schema") != "kdm6.ice_factorial_water_stage.v1" or r.get("factor_mode") != mode or
               index(r, "column") != 0 or index(r, "loops") != 1 or index(r, "subcycle") != 0 or
               number(r, "dt_call_s") != 20. or number(r, "dtcld_s") != 20. for r in group):
            raise ValueError("wrong water stage metadata")
        for name, expected in (("DEND_kg_m3", f[0]), ("DELZ_m", f[3])):
            if not same_bits(np.array([number(r, name) for r in group]), expected):
                raise ValueError("water-stage forcing differs from request")
        result[stage] = np.array([[number(r, name+"_kg_kg") for r in group] for name in WATER])
    return result


def contrast(cells):
    """Effects at each other-factor level and the two-factor interaction."""
    a, b, c, d = (float(cells[m]) for m in MODES)
    return {"normalization_at_cap": b-a, "normalization_at_actual": d-c,
            "actual_arrival_at_raw": c-a, "actual_arrival_at_normalized": d-b,
            "interaction": math.fsum((d, -c, -b, a))}


def run(request, executable, finish_reference, workspace, output):
    from harness.verify_native_finish_ad import _api, _zero_value, finish_value
    inputs = [Path(p).resolve() for p in (request, executable, finish_reference)]
    request, executable, finish_reference = inputs
    pins = {str(p): sha(p) for p in inputs}
    if sha(request) != REQUEST_SHA:
        raise ValueError("requires the qualified original native-column request")
    data = request.read_bytes()
    magic, version, levels, dt, land, nland, nsea = REQUEST.unpack_from(data)
    if magic != b"K6BUDG1\0" or version != 1 or levels != 39 or dt != 20. or len(data) != 48+16*levels*8:
        raise ValueError("requires the same admitted native 39-level, 20-second request")
    values = np.frombuffer(data, dtype="<f8", offset=48)
    s = values[:12*levels].reshape(12, levels).copy()
    f = values[12*levels:].reshape(4, levels).copy()
    if request_bytes(s, f, dt, land, nland, nsea) != data:
        raise ValueError("request operands cannot be roundtripped")
    reference = json.loads(finish_reference.read_text())
    cfg, zero = reference["configuration"], reference["zero_out"]
    if cfg["dt"] != dt or reference["source"]["levels"] != levels:
        raise ValueError("finish reference differs from request")
    workspace = Path(workspace).resolve()
    workspace.mkdir(parents=True, exist_ok=False)
    if Path(output).exists() or Path(output).is_symlink():
        raise ValueError("output must be new")
    def execute(label, mode, trace):
        directory = workspace/label
        directory.mkdir()
        response, tracepath = directory/"response.bin", directory/"ice.tsv"
        env = dict(os.environ, OMP_NUM_THREADS="1", MKL_NUM_THREADS="1", OMP_THREAD_LIMIT="1", OPENBLAS_NUM_THREADS="1")
        env.pop("KDM6_ICE_FACTORIAL_MODE", None)
        env.pop("KDM6_ICE_BOUNDARY_TRACE", None)
        if mode:
            env["KDM6_ICE_FACTORIAL_MODE"] = mode
        if trace:
            env["KDM6_ICE_BOUNDARY_TRACE"] = str(tracepath)
        done = subprocess.run([str(executable), "--input", str(request), "--output", str(response)],
                              env=env, check=True, capture_output=True, text=True)
        (directory/"run.log").write_text(done.stdout+done.stderr)
        result = read_response(response.read_bytes(), s, f)
        return result, response, tracepath
    _, baseline, _ = execute("unset_baseline", None, False)
    if sha(baseline) != BASELINE_RESPONSE_SHA:
        raise ValueError("unset experimental overlay differs from the original baseline")
    records, stages_by_mode = {}, {}
    weights = f[0]*f[3]
    for mode in MODES:
        _, off, _ = execute(mode+"_off", mode, False)
        (_, _, raw, flux), on, tracepath = execute(mode+"_on", mode, True)
        if off.read_bytes() != on.read_bytes():
            raise ValueError("instrumentation changes a treatment output")
        if mode == "raw_cap" and on.read_bytes() != baseline.read_bytes():
            raise ValueError("raw-cap arm differs from unset baseline")
        stages = water_stages(tracepath, mode, f)
        if not same_bits(stages["post_micro"], raw[1:7]):
            raise ValueError("post-microphysics trace differs from returned state")
        stages_by_mode[mode] = stages
        ice = ice_metrics(tracepath, mode, s, f)
        clean = raw.copy()
        clean[1] = np.maximum(raw[1], 0.)
        clean[2:7] = np.where(raw[2:7] < zero["threshold"], 0., raw[2:7])
        applied = finish_value(s[:3], _zero_value(raw[:3], _api().ZeroOutConfig(**zero)), _api().FinishConfig(**cfg))
        accounting = ledger(s, f, raw, clean, flux, dt)
        column = lambda a: math.fsum((a*weights).ravel())
        records[mode] = {"mode": mode, "ice": ice, "state_out": raw.tolist(),
            "applied_finish": applied.tolist(), "accounting": accounting,
            "whole_stage_changes": {"sedimentation": column(stages["post_sed"]-stages["pre_sed"]),
                "microphysics": column(stages["post_micro"]-stages["post_sed"])},
            "tendency": {"H_RATE_mass_weighted_mean_K_s": column(applied[1])/math.fsum(weights),
                "applied_total_water_rate_kg_m2_s": accounting["balance"]["applied_change_kg_m2"]/dt,
                "QV_RATE_column_kg_m2_s": column(applied[2])},
            "response_sha256": sha(on), "trace_off_on_bit_equal": True,
            "trace_sha256": sha(tracepath), "water_trace_sha256": sha(str(tracepath)+".water.tsv")}
        if mode.endswith("actual"):
            records[mode]["layer_trace_sha256"] = sha(str(tracepath)+".layers.tsv")
    baseline_stages = stages_by_mode["raw_cap"]
    for mode, stages in stages_by_mode.items():
        if not same_bits(stages["pre_sed"], baseline_stages["pre_sed"]) or not same_bits(
                stages["post_sed"][[0, 1, 2, 4, 5]], baseline_stages["post_sed"][[0, 1, 2, 4, 5]]):
            raise ValueError("non-ice sedimentation mass fields changed between arms")
    scalar_metrics = {
        "ice_QI_state_plus_bottom": {m:r["ice"]["QI"]["state_plus_bottom"] for m,r in records.items()},
        "whole_kernel_water_change": {m:r["accounting"]["balance"]["kernel_change_kg_m2"] for m,r in records.items()},
        "H_RATE_mass_weighted_mean_K_s": {m:r["tendency"]["H_RATE_mass_weighted_mean_K_s"] for m,r in records.items()}}
    if any(sha(p) != h for p,h in pins.items()):
        raise RuntimeError("pinned inputs changed")
    report = {"schema": "kdm6.ice_only_factorial.v1", "source_sha256": pins,
        "producer_sha256": sha(__file__), "state_in": s.tolist(), "forcing_in": f.tolist(),
        "dt_seconds": dt, "finish_configuration": cfg, "zero_out": zero, "modes": records,
        "contrasts": {name:contrast(values) for name,values in scalar_metrics.items()},
        "CLI_calls": 9, "main_sedimentation": "Legacy in every arm; five non-ice mass fields bit-identical after sedimentation",
        "candidate_selected": False, "new_derivative_validation": False,
        "limits": "one native column, fixed first ice schedule and forcing; value-only candidate comparison; raw-work flux units conditional, NI host basis uncertified; not operational adoption/full-host/RTTOV/forecast skill"}
    text = json.dumps(report, indent=2, allow_nan=False)+"\n"
    with Path(output).open("x") as stream:
        stream.write(text)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("request", "executable", "finish-reference", "workspace", "output"):
        parser.add_argument("--"+name, type=Path, required=True)
    args = parser.parse_args()
    result = run(args.request, args.executable, args.finish_reference, args.workspace, args.output)
    print(json.dumps({mode:{"QI":r["ice"]["QI"]["state_plus_bottom"],
        "raw_water":r["accounting"]["balance"]["kernel_change_kg_m2"]} for mode,r in result["modes"].items()}, indent=2))
