#!/usr/bin/env python3
"""One experimental selector-2/dry-number fp64 step from a native 5 km frame."""

import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kdm6.io.frame_reader import read_wrfout_frame
from kdm6.state import FORCING_FIELDS, PROG_FIELDS


CONFIG = dict(physics_variant=2, dry_number=1, precision="float64", dt_seconds=20.0,
              ncmin_land_volume=10.0, ncmin_sea_volume=10.0,
              nccn_policy="as_stored", finite_difference_width=1e-4,
              density_policy="existing_ProgB", observations="not_evaluated")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify_state(state, label="state"):
    """Report runner input checks separately from strict pair-state admission.

    These surface checks do not certify the full KDM6 numerical domain or a
    physical/observational state. Defined finite operator outputs are checked
    only after the caller actually executes the operator.
    """
    try:
        values = np.asarray(state)
        shape_ok = values.ndim == 2 and values.shape[0] == 12 and values.shape[1] > 0
        finite = shape_ok and bool(np.isfinite(values).all())
    except (TypeError, ValueError):
        shape_ok = finite = False

    numerical_inputs = bool(
        shape_ok and finite and (values[0] > 0).all() and (values[1:] >= 0).all()
    )
    pair_admitted = False
    if numerical_inputs:
        pair_admitted = True
        for mass, moment in (("qc", "nc"), ("qr", "nr"), ("qi", "ni"), ("qg", "bg")):
            q, n = (values[PROG_FIELDS.index(name)] for name in (mass, moment))
            if ((q > 0) & (n <= 0)).any() or ((q == 0) & (n > 0)).any():
                pair_admitted = False
                break
    return dict(
        state_label=str(label),
        numerical_input_checks_passed=numerical_inputs,
        strict_pair_state_admitted=bool(pair_admitted),
        observational_admission=False,
    )


def validate_state(state, label):
    if state.ndim != 2 or state.shape[0] != 12 or state.shape[1] == 0:
        raise ValueError(f"{label}: expected 12 fields and nonempty native levels")
    if not np.isfinite(state).all() or (state[0] <= 0).any() or (state[1:] < 0).any():
        raise ValueError(f"{label}: requires finite positive temperature and nonnegative state")
    for mass, moment in (("qc", "nc"), ("qr", "nr"), ("qi", "ni"), ("qg", "bg")):
        q, n = (state[PROG_FIELDS.index(name)] for name in (mass, moment))
        if ((q > 0) & (n <= 0)).any() or ((q == 0) & (n > 0)).any():
            raise ValueError(f"{label}: unsupported {mass}/{moment} moment pair")


def load_library(path):
    lib = ctypes.CDLL(str(Path(path).resolve()))
    pointer = ctypes.POINTER(ctypes.c_double)
    lib.kdm6_get_abi_version_c.restype = ctypes.c_int
    if lib.kdm6_get_abi_version_c() != 2:
        raise ValueError("requires KDM6 C ABI version 2")
    lib.kdm6_step_ad_number_c.restype = ctypes.c_int
    lib.kdm6_step_ad_number_c.argtypes = [
        pointer, pointer, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_double,
        ctypes.c_int, pointer, ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_float), ctypes.c_double, ctypes.c_double,
        ctypes.c_uint32, ctypes.c_int64]
    for name in ("kdm6_handle_jvp_c", "kdm6_handle_vjp_c"):
        fn = getattr(lib, name)
        fn.restype = ctypes.c_int
        fn.argtypes = [ctypes.c_void_p, pointer, pointer]
    lib.kdm6_handle_closep_c.restype = ctypes.c_int
    lib.kdm6_handle_closep_c.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
    return lib


def check_call(code, name):
    if code != 0:
        raise RuntimeError(f"{name} failed with C ABI status {code}")


def step(lib, state, forcing, xland, value_only):
    pointer = ctypes.POINTER(ctypes.c_double)
    output = np.empty_like(state)
    handle = ctypes.c_void_p()
    land = ctypes.c_float(xland)
    try:
        check_call(lib.kdm6_step_ad_number_c(
            state.ctypes.data_as(pointer), forcing.ctypes.data_as(pointer),
            1, state.shape[1], 1, CONFIG["dt_seconds"], int(value_only),
            output.ctypes.data_as(pointer), ctypes.byref(handle), ctypes.byref(land),
            CONFIG["ncmin_land_volume"], CONFIG["ncmin_sea_volume"],
            CONFIG["physics_variant"], CONFIG["dry_number"]), "forward")
        if bool(handle.value) == value_only:
            raise RuntimeError("C ABI returned the wrong graph/value-only handle state")
        return output, handle
    except Exception:
        if handle.value:
            check_call(lib.kdm6_handle_closep_c(ctypes.byref(handle)), "close")
        raise


def run_column(lib, state, forcing, xland):
    state = np.ascontiguousarray(state, dtype=np.float64)
    forcing = np.ascontiguousarray(forcing, dtype=np.float64)
    input_assessment = classify_state(state, "input")
    validate_state(state, "input")
    if forcing.shape != (4, state.shape[1]) or not np.isfinite(forcing).all() or (forcing <= 0).any():
        raise ValueError("forcing: requires four finite positive native profiles")
    if xland not in (1.0, 2.0):
        raise ValueError("XLAND must be 1 or 2")
    if not (state[PROG_FIELDS.index("qi")] > 0).any():
        raise ValueError("supported ice candidate requires a nonzero input ice profile")
    direction = np.zeros_like(state)
    for field, scale in (("qi", 1.0), ("qv", 0.01), ("nc", 0.01)):
        index = PROG_FIELDS.index(field)
        direction[index] = scale * state[index]
    h = CONFIG["finite_difference_width"]
    validate_state(state + h * direction, "plus input")
    validate_state(state - h * direction, "minus input")
    output, handle = step(lib, state, forcing, xland, False)
    pointer = ctypes.POINTER(ctypes.c_double)
    try:
        tangent = np.empty_like(state)
        check_call(lib.kdm6_handle_jvp_c(handle, direction.ctypes.data_as(pointer),
                                        tangent.ctypes.data_as(pointer)), "JVP")
        if not np.isfinite(tangent).all() or not np.max(np.abs(tangent)) > 0:
            raise ValueError("JVP must be finite and nonzero")
        covector = np.ascontiguousarray(tangent / np.max(np.abs(tangent)))
        adjoint = np.empty_like(state)
        check_call(lib.kdm6_handle_vjp_c(handle, covector.ctypes.data_as(pointer),
                                        adjoint.ctypes.data_as(pointer)), "VJP")
        if not np.isfinite(adjoint).all() or not np.max(np.abs(adjoint)) > 0:
            raise ValueError("VJP must be finite and nonzero")
    finally:
        check_call(lib.kdm6_handle_closep_c(ctypes.byref(handle)), "close")
        if handle.value:
            raise RuntimeError("closed handle was not nulled")
    validate_state(output, "output")
    value, _ = step(lib, state, forcing, xland, True)
    plus, _ = step(lib, np.ascontiguousarray(state + h * direction), forcing, xland, True)
    minus, _ = step(lib, np.ascontiguousarray(state - h * direction), forcing, xland, True)
    for label, result in (("value-only output", value), ("plus output", plus), ("minus output", minus)):
        validate_state(result, label)
    difference = (plus - minus) / (2 * h)
    if not np.isfinite(difference).all():
        raise ValueError("finite difference contains nonfinite values")
    lhs, rhs = float(np.sum(covector * tangent)), float(np.sum(direction * adjoint))
    dual_scale = max(abs(lhs), abs(rhs))
    if not np.isfinite([lhs, rhs]).all() or dual_scale == 0:
        raise ValueError("duality products must be finite and nonzero")
    errors = np.max(np.abs(tangent - difference), axis=1)
    scales = np.maximum(np.max(np.abs(tangent), axis=1), np.max(np.abs(difference), axis=1))
    relative = np.divide(errors, scales, out=np.zeros_like(errors), where=scales > 0)
    # Diagnostic estimate of endpoint output quantization, not a relaxed gate.
    quantization = np.max(np.abs(np.spacing(plus)) + np.abs(np.spacing(minus)), axis=1) / (2 * h)
    checks = dict(graph_value_bits_equal=np.array_equal(output.view(np.uint64), value.view(np.uint64)),
                  duality_relative=abs(lhs - rhs) / dual_scale,
                  finite_difference_max_abs=dict(zip(PROG_FIELDS, errors.tolist())),
                  finite_difference_relative=dict(zip(PROG_FIELDS, relative.tolist())),
                  endpoint_quantization_estimate=dict(zip(PROG_FIELDS, quantization.tolist())),
                  finite_difference_passed=bool(np.all(relative <= 1e-5)))
    checks.update(input_assessment)
    checks["operator_executed"] = True
    checks["operator_outputs_finite"] = True
    checks["numerical_checks_passed"] = bool(checks["graph_value_bits_equal"]
        and checks["duality_relative"] <= 1e-12 and checks["finite_difference_passed"])
    arrays = dict(state_in=state, forcing=forcing, state_out=output, direction=direction,
                  xland=np.array(xland), covector=covector, jvp=tangent, vjp=adjoint,
                  value_only_output=value, plus_output=plus, minus_output=minus,
                  finite_difference=difference)
    return arrays, checks


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--i", type=int, required=True, help="zero-based native column i")
    parser.add_argument("--j", type=int, required=True, help="zero-based native column j")
    parser.add_argument("--time-index", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True, help="new result directory")
    args = parser.parse_args(argv)
    if args.output.exists():
        raise ValueError("output directory already exists")
    input_digest, library_digest = sha256(args.input), sha256(args.library)
    import netCDF4
    with netCDF4.Dataset(args.input) as ds:
        if float(getattr(ds, "DX", 0)) != 5000 or float(getattr(ds, "DY", 0)) != 5000:
            raise ValueError("requires retained native 5 km input")
        nx, ny = len(ds.dimensions["west_east"]), len(ds.dimensions["south_north"])
        if not (0 <= args.i < nx and 0 <= args.j < ny and 0 <= args.time_index < len(ds.dimensions["Time"])):
            raise ValueError("column or time index is outside the input frame")
    frame = read_wrfout_frame(str(args.input), args.time_index, nccn_policy="as_stored")
    index = args.j * nx + args.i
    state = np.stack([field[index].numpy() for field in frame.state])
    forcing = np.stack([field[index].numpy() for field in frame.forcing])
    arrays, checks = run_column(load_library(args.library), state, forcing, float(frame.xland[index]))
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[2],
                              capture_output=True, text=True)
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=Path(__file__).resolve().parents[2],
                           capture_output=True, text=True)
    if input_digest != sha256(args.input) or library_digest != sha256(args.library):
        raise ValueError("input or library changed during execution")
    result = dict(configuration=CONFIG, source_revision=revision.stdout.strip() or None,
                  source_dirty=bool(dirty.stdout) if dirty.returncode == 0 else None,
                  status="NUMERICAL_PASS" if checks["numerical_checks_passed"] else "NUMERICAL_CHECK_FAILED",
                  input_sha256=input_digest, library_sha256=library_digest,
                  runner_sha256=sha256(__file__), python=platform.python_version(),
                  column=dict(i=args.i, j=args.j, time_index=args.time_index,
                              xland=float(frame.xland[index]), native_levels=state.shape[1],
                              valid_time=frame.meta.get("valid_time_utc")),
                  checks=checks,
                  numerical_input_checks_passed=checks["numerical_input_checks_passed"],
                  strict_pair_state_admitted=checks["strict_pair_state_admitted"],
                  observational_admission=False,
                  operator_executed=checks["operator_executed"],
                  operator_outputs_finite=checks["operator_outputs_finite"],
                  physical_number_basis_resolved=False,
                  accepted_observation_cost=False, operational_approval=False,
                  branch_certification="not_measured")
    args.output.mkdir(parents=True, exist_ok=False)
    np.savez(args.output / "arrays.npz", **arrays, fields=np.array(PROG_FIELDS),
             forcing_fields=np.array(FORCING_FIELDS))
    (args.output / "result.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if checks["numerical_checks_passed"] else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError, RuntimeError, AttributeError) as error:
        print(f"column run failed: {error}", file=sys.stderr)
        sys.exit(1)
