"""Compare one native kernel's values/JVP/VJP with ice tracing off and on.

This is a first-order instrumentation noninterference check, not a new full
derivative, tendency, RTTOV or conservation certificate. Each library/mode is
evaluated in a fresh CPU process with the same saved operands and fixed seeds.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np


PRODUCTS = ("state", "jvp", "state_vjp", "forcing_vjp", "applied_finish",
            "finish_jvp", "finish_state_vjp", "finish_forcing_vjp")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def evaluate(case, library, output, finish_reference):
    from harness.verify_state_forcing_ad import Kernel, OUTPUT_SCALES
    from harness.verify_native_finish_ad import KernelFinish, _api, _zero_value, finish_value
    c = case["kernel_contract"]
    if c["physics_variant"] != 0 or c["dry_number"] != 0:
        raise ValueError("requires legacy internal-volume operands")
    s = np.ascontiguousarray(case["same_call"]["state_in"], dtype=np.float64)
    f = np.ascontiguousarray(case["same_call"]["forcing_in"], dtype=np.float64)
    if s.ndim != 2 or s.shape[0] != 12 or f.shape != (4, s.shape[1]):
        raise ValueError("invalid saved operand layout")
    if not np.isfinite(s).all() or not np.isfinite(f).all():
        raise ValueError("nonfinite saved operands")
    phase = np.arange(s.shape[1], dtype=np.float64)
    ds = np.zeros_like(s)
    ds[0] = .2*np.sin(.37*(phase+1))
    ds[1] = .02*s[1]*np.cos(.29*(phase+2))
    df = np.ascontiguousarray(.01*f*np.sin(.31*(phase[None, :]+np.arange(4)[:, None]+1)))
    u = np.ascontiguousarray(np.sin(.23*(np.arange(s.size).reshape(s.shape)+1))/OUTPUT_SCALES)
    reference = json.loads(Path(finish_reference).read_text())
    cfg, zero = reference["configuration"], reference["zero_out"]
    selection = reference["source"]
    snapshot = case["native_snapshot"]
    if (cfg["dt"] != c["dt_seconds"] or
            [selection["i"], selection["j"]] != snapshot["native_indices_1based"] or
            selection["levels"] != s.shape[1] or
            reference["input_sha256"]["namelist"] not in case["source_sha256"].values()):
        raise ValueError("finish reference does not match the pinned native case")
    fu = np.ascontiguousarray(np.sin(.19*(np.arange(5*s.shape[1]).reshape(5, -1)+1)) /
                              np.array([1., 1e-3, 1e-6, 1e-6, 1.])[:, None])
    kernel = Kernel(library, s.shape[1], c["dt_seconds"], c["xland"], *c["ncmin_land_sea"])
    value, handle = kernel.forward(s, f, record=True)
    try:
        tangent = kernel.jvp(handle, ds, df)
        gs, gf = kernel.vjp(handle, u)
        finish = KernelFinish(kernel, _api().FinishConfig(**cfg), _api().ZeroOutConfig(**zero))
        applied = finish_value(s[:3], _zero_value(value[:3], finish.zero), finish.config)
        finish_tangent = finish.jvp(s, value, handle, ds, df)
        finish_gs, finish_gf, _ = finish.vjp(s, value, handle, fu)
    finally:
        kernel.close(handle)
    # Explicit serialization of opaque first-order ABI results, never a live graph.
    with Path(output).open("xb") as stream:
        np.savez(stream, state=value, jvp=tangent, state_vjp=gs, forcing_vjp=gf,
                 applied_finish=applied, finish_jvp=finish_tangent,
                 finish_state_vjp=finish_gs, finish_forcing_vjp=finish_gf,
                 state_direction=ds, forcing_direction=df, cotangent=u, finish_cotangent=fu)


def compare_products(reference, other):
    result = {}
    for key in PRODUCTS:
        a, b = reference[key], other[key]
        valid = a.dtype == b.dtype == np.dtype("float64") and a.shape == b.shape
        finite = bool(np.isfinite(a).all() and np.isfinite(b).all())
        equal = valid and finite and a.tobytes() == b.tobytes()
        result[key] = {"count": a.size, "finite": finite,
                       "raw_bit_equal": bool(equal),
                       "maxabs_difference": float(np.max(abs(a-b))) if valid and finite else None}
    return result


def run(case_path, control, instrumented, workspace, output, trace_variable, finish_reference):
    paths = [Path(p).resolve() for p in (case_path, control, instrumented, finish_reference)]
    case_path, control, instrumented, finish_reference = paths
    pins = {str(p): sha(p) for p in paths}
    case = json.loads(case_path.read_text())
    if case.get("schema") != "kdm6.same_call_water_budget.v1":
        raise ValueError("requires the saved same-call v1 case")
    if Path(output).exists() or Path(output).is_symlink():
        raise ValueError("output must be new")
    workspace = Path(workspace).resolve()
    workspace.mkdir(parents=True, exist_ok=False)
    products, traces = {}, {}
    for mode, library, trace_on in (("control", control, False),
                                    ("instrumented_off", instrumented, False),
                                    ("instrumented_on", instrumented, True)):
        product = workspace/(mode+".npz")
        env = dict(os.environ, OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
                   OMP_THREAD_LIMIT="1", OPENBLAS_NUM_THREADS="1")
        env.pop(trace_variable, None)
        if trace_on:
            env[trace_variable] = str(workspace/(mode+".trace"))
        done = subprocess.run([sys.executable, "-m", "harness.verify_ice_trace_ad_noninterference",
            "--worker-case", str(case_path), "--worker-library", str(library),
            "--worker-output", str(product), "--finish-reference", str(finish_reference)],
            env=env, check=True, capture_output=True, text=True)
        (workspace/(mode+".log")).write_text(done.stdout+done.stderr)
        with np.load(product, allow_pickle=False) as data:
            products[mode] = {key: data[key].copy() for key in data.files}
        traces[mode] = {"products_sha256": sha(product)}
        if trace_on:
            trace = Path(env[trace_variable])
            if not trace.is_file() or trace.stat().st_size == 0:
                raise ValueError("trace-on graph evaluation emitted no trace")
            traces[mode]["trace_sha256"] = sha(trace)
    comparisons = {mode: compare_products(products["control"], products[mode])
                   for mode in ("instrumented_off", "instrumented_on")}
    passed = all(p["raw_bit_equal"] for group in comparisons.values() for p in group.values())
    if any(sha(path) != digest for path, digest in pins.items()):
        raise RuntimeError("pinned inputs changed during evaluation")
    report = {"schema": "kdm6.ice_trace_ad_noninterference.v2", "source_sha256": pins,
              "producer_sha256": sha(__file__), "native_column": case["native_snapshot"],
              "kernel_wrapper_sha256": sha(Path(__file__).with_name("verify_state_forcing_ad.py")),
              "finish_adapter_sha256": sha(Path(__file__).with_name("verify_native_finish_ad.py")),
              "kernel_contract": case["kernel_contract"], "comparisons": comparisons,
              "products": traces, "processes": 3, "passed": passed,
              "limits": "one native point and fixed seeds; kernel plus cleanup/applied-finish noninterference, not new independent FD, full-host/RK or RTTOV AD validation"}
    serialized = json.dumps(report, indent=2, allow_nan=False)+"\n"
    with Path(output).open("x") as stream:
        stream.write(serialized)
    if not passed:
        raise RuntimeError("instrumentation changes a first-order product")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("case", "control", "instrumented", "workspace", "output", "worker-case", "worker-library", "worker-output"):
        parser.add_argument("--"+name, type=Path)
    parser.add_argument("--trace-variable", default="KDM6_ICE_BOUNDARY_TRACE")
    parser.add_argument("--finish-reference", type=Path,
        default=Path(__file__).parents[1]/"harness/evidence/applied_finish_ad_2026-10-21/native39_finish_ad.json")
    args = parser.parse_args()
    if args.worker_case:
        if args.worker_library is None or args.worker_output is None:
            parser.error("worker requires library and output")
        evaluate(json.loads(args.worker_case.read_text()), args.worker_library, args.worker_output, args.finish_reference)
    else:
        if any(getattr(args, name) is None for name in ("case", "control", "instrumented", "workspace", "output")):
            parser.error("requires case/control/instrumented/workspace/output")
        print(json.dumps({"passed": run(args.case, args.control, args.instrumented, args.workspace,
            args.output, args.trace_variable, args.finish_reference)["passed"]}))
