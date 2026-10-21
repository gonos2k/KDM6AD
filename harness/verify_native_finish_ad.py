"""Check captured f32 finish values and local fp64 R(s,Z(K(s,F))) derivatives.

This offline first-order verifier does not integrate the host or evaluate RTTOV.
Torch is imported lazily so trace/error checks remain usable without it.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np

from harness.native_finish_replay import replay_arm64_theta_m_finish
from harness.native_trace_records import read_native_trace
from harness.run_ss_case import _namelist_assignments
from harness.verify_state_forcing_ad import Kernel, STATE_FIELDS, FORCING_FIELDS, EPSILONS, sha

OUTPUT_FIELDS = ("T_NEW_AFTER", "H_RATE", "QV_RATE", "QC_RATE", "TH_PHY_M_T0")
OUTPUT_SCALES = np.array([1., 1e-3, 1e-6, 1e-6, 1.])[:, None]
FD_ATOL, FD_RTOL, DOT_RTOL = 1e-9, 3e-6, 1e-10


def _api():
    from oracle.kdm6 import native_finish as api
    return api


def _tensor_state(values):
    import torch
    return _api().ThermoState(*(torch.from_numpy(np.ascontiguousarray(x, dtype=np.float64))
                                for x in values))


def _array_result(values):
    # Explicit value serialization of first-order operator products. This
    # verifier never accepts a live Python graph through the opaque C ABI.
    return np.ascontiguousarray(np.stack([x.numpy() for x in values]), dtype=np.float64)


def finish_value(before, after, config):
    return _array_result(_api().native_finish(_tensor_state(before), _tensor_state(after), config))


def finish_jvp(before, after, d_before, d_after, config):
    return _array_result(_api().native_finish_jvp(
        _tensor_state(before), _tensor_state(after), _tensor_state(d_before),
        _tensor_state(d_after), config))


def finish_vjp(before, after, cotangent, config):
    import torch
    api = _api()
    u = api.NativeFinishResult(*(torch.from_numpy(np.ascontiguousarray(x)) for x in cotangent))
    old, new = api.native_finish_vjp(_tensor_state(before), _tensor_state(after), u, config)
    return _array_result(old), _array_result(new)


def _zero_value(after, config):
    return _array_result(_api().post_microphysics_thermo(_tensor_state(after), config))


def _zero_jvp(after, direction, config):
    return _array_result(_api().post_microphysics_jvp(
        _tensor_state(after), _tensor_state(direction), config))


def _zero_vjp(after, cotangent, config):
    return _array_result(_api().post_microphysics_vjp(
        _tensor_state(after), _tensor_state(cotangent), config))


class KernelFinish:
    """First-order composition with an opaque state+forcing KDM backend.

    The direct old-state R_s path and post-MP Z_y pullback are explicit.
    This is a column kernel/finish adapter, not a full-host HostTransition.
    """
    def __init__(self, kernel, finish_config, zero_config):
        self.kernel, self.config, self.zero = kernel, finish_config, zero_config

    def _check(self, value, fields, name):
        if not isinstance(value, np.ndarray) or value.dtype != np.float64:
            raise TypeError(f"{name} must be a binary64 ndarray")
        if value.shape != (fields, self.kernel.levels):
            raise ValueError(f"{name} must have shape ({fields}, {self.kernel.levels})")
        if not np.isfinite(value).all():
            raise ValueError(f"{name} must be finite")

    def forward(self, state, forcing, *, record=False):
        self._check(state, 12, "state")
        self._check(forcing, 4, "forcing")
        after, handle = self.kernel.forward(state, forcing, record=record)
        try:
            self._check(after, 12, "kernel output")
            clean = _zero_value(after[:3], self.zero)
            result = finish_value(state[:3], clean, self.config)
        except BaseException:
            self.kernel.close(handle)
            raise
        return result, handle, after

    def jvp(self, state, after, handle, ds, df):
        self._check(state, 12, "state")
        self._check(after, 12, "recorded kernel output")
        self._check(ds, 12, "state direction")
        self._check(df, 4, "forcing direction")
        dy = self.kernel.jvp(handle, np.ascontiguousarray(ds), np.ascontiguousarray(df))
        self._check(dy, 12, "kernel tangent")
        clean = _zero_value(after[:3], self.zero)
        dz = _zero_jvp(after[:3], dy[:3], self.zero)
        return finish_jvp(state[:3], clean, ds[:3], dz, self.config)

    def vjp(self, state, after, handle, cotangent):
        self._check(state, 12, "state")
        self._check(after, 12, "recorded kernel output")
        self._check(cotangent, 5, "finish cotangent")
        clean = _zero_value(after[:3], self.zero)
        direct, new = finish_vjp(state[:3], clean, cotangent, self.config)
        kernel_u = np.zeros_like(state)
        kernel_u[:3] = _zero_vjp(after[:3], new, self.zero)
        gs, gf = self.kernel.vjp(handle, kernel_u)
        self._check(gs, 12, "kernel state adjoint")
        self._check(gf, 4, "kernel forcing adjoint")
        old = np.zeros_like(state)
        old[:3] = direct
        return gs + old, gf, old


@dataclass
class TraceCase:
    state: np.ndarray
    forcing: np.ndarray
    before: np.ndarray
    after: np.ndarray
    config: dict
    zero: dict
    ncmin: tuple[float, float]
    f32_replay: dict


def bits32(value):
    return int(np.asarray(value, dtype=np.float32).view(np.uint32))


def load_case(trace, namelist, step, i, j, levels):
    """Load a d01 interior capture; verify handoffs and the existing f32 map."""
    if min(step, i, j, levels) <= 0:
        raise ValueError("step, indices and levels must be positive")
    nml = _namelist_assignments(Path(namelist).read_text())
    def first(name):
        return float(nml[name][0].replace("D", "E").replace("d", "e"))
    if first("use_theta_m") != 1 or first("no_mp_heating") != 0 or first("mp_physics") != 137:
        raise ValueError("only the captured MP137 moist-theta/heating-enabled path is supported")
    if not (1 < i < first("e_we")-1 and 1 < j < first("e_sn")-1):
        raise ValueError("this adapter supports interior columns, excluding boundary zero_outb")
    if levels != first("e_vert")-1:
        raise ValueError("use the complete native mass-level column declared in the namelist")
    mode = first("mp_zero_out")
    if mode != int(mode) or int(mode) not in (0, 1, 2):
        raise ValueError("unsupported mp_zero_out mode")
    threshold = float(np.float32(first("mp_zero_out_thresh")))
    if not np.isfinite(threshold) or threshold < 0:
        raise ValueError("mp_zero_out_thresh must be finite and nonnegative")
    rows = read_native_trace(trace)
    inputs = [rows[("MP_INPUT", step, i, k, j)] for k in range(1, levels+1)]
    outputs = [rows[("MP_OUTPUT", step, i, k, j)] for k in range(1, levels+1)]
    pres = [rows[("FINISH_PRE", step, i, k, j)] for k in range(1, levels+1)]
    posts = [rows[("FINISH_POST", step, i, k, j)] for k in range(1, levels+1)]
    config = {name: float(pres[0].value(field)) for name, field in
              (("dt", "dt"), ("alpha", "ALPHA"), ("t0", "T0"), ("mp_tend_lim", "MP_TEND_LIM"))}
    numerator = first("time_step_fract_num") if "time_step_fract_num" in nml else 0.
    denominator = first("time_step_fract_den") if "time_step_fract_den" in nml else 1.
    if denominator <= 0 or bits32(first("time_step")+numerator/denominator) != bits32(config["dt"]):
        raise ValueError("trace/namelist time steps differ")
    if bits32(first("mp_tend_lim")) != bits32(config["mp_tend_lim"]):
        raise ValueError("trace/namelist heating limit differs")
    checks, mismatches, aliases = 0, [], 0
    for k, (s, y, pre, post) in enumerate(zip(inputs, outputs, pres, posts), 1):
        for field in ("dt", "ALPHA", "T0", "MP_TEND_LIM"):
            if bits32(pre.value(field)) != bits32(pres[0].value(field)):
                raise ValueError("finish configuration changes across levels")
        if any(bits32(r.value("dt")) != bits32(config["dt"]) for r in (s, y, post)):
            raise ValueError("trace time steps differ")
        if bits32(post.value("T0")) != bits32(config["t0"]):
            raise ValueError("finish T0 differs")
        raw_qv, raw_qc = y.value("Q"), y.value("QC")
        clean_qv = np.maximum(raw_qv, np.float32(0)) if mode == 2 else raw_qv
        clean_qc = np.float32(0) if mode != 0 and raw_qc < threshold else raw_qc
        pairs = ((pre.value("H_PRE"), s.value("TH")),
                 (pre.value("QV_PRE"), s.value("Q")),
                 (pre.value("TH_PLUS"), y.value("TH")),
                 (pre.value("QV_PLUS"), clean_qv))
        if any(bits32(a) != bits32(b) for a, b in pairs):
            raise ValueError(f"MP/finish handoff differs at layer {k}")
        aliases += len(pairs)
        replay = replay_arm64_theta_m_finish(dict(zip(pre.fields, pre.values)))
        replay["QC_RATE"] = np.float32(np.float32(clean_qc - s.value("QC")) / pre.value("dt"))
        for name, actual in replay.items():
            expected = pre.value(name) if name in pre.fields else post.value(name)
            checks += 1
            if bits32(actual) != bits32(expected):
                mismatches.append({"k": k, "field": name, "actual_bits": bits32(actual),
                                   "expected_bits": bits32(expected)})
    if mismatches:
        raise ValueError(f"captured f32 finish replay differs: {mismatches}")
    state = np.ascontiguousarray([[r.value(n) for r in inputs] for n in STATE_FIELDS], dtype=np.float64)
    forcing = np.ascontiguousarray([[r.value(n) for r in inputs] for n in FORCING_FIELDS], dtype=np.float64)
    after = np.ascontiguousarray([[r.value(n) for r in outputs] for n in ("TH", "Q", "QC")], dtype=np.float64)
    if mode == 2:
        after[1] = np.maximum(after[1], 0)
    if mode != 0:
        after[2] = np.where(after[2] < threshold, 0, after[2])
    return TraceCase(state, forcing, state[:3].copy(), after, config,
                     {"mode": int(mode), "threshold": threshold},
                     (float(np.float32(first("ncmin_land"))), float(np.float32(first("ncmin_sea")))),
                     {"checked_values": checks, "raw_bit_mismatches": 0,
                      "checked_handoff_pairs": aliases})


def branch_codes(before, raw_after, config, zero=None):
    """Value-only finish/zero-out branch signature for eligible FD trials."""
    bound = config["dt"] * config["mp_tend_lim"]
    raw = raw_after[0]-before[0]
    clip = np.where(raw > bound, 1, np.where(raw < -bound, -1, 0))
    if bound > 0:
        clip = np.where(raw == bound, 2, np.where(raw == -bound, -2, clip))
    else:
        clip = np.full_like(clip, 3)
    signature = [clip]
    if zero is not None:
        mode, threshold = zero["mode"], zero["threshold"]
        signature += [np.where(raw_after[1] > 0, 1, 0) if mode == 2 else np.ones_like(clip),
                      np.where(raw_after[2] >= threshold, 1, 0) if mode else np.ones_like(clip)]
    return np.stack(signature)


def branch_summary(codes):
    return {"clip_counts": {str(n): int((codes[0] == n).sum()) for n in (-2, -1, 0, 1, 2, 3)},
            "zero_out_signature_rows": [row.astype(int).tolist() for row in codes[1:]]}


def check_stage(value, jvp, gradients, x, directions, u):
    """Independent FD with one common, branch-preserving epsilon per direction."""
    _, signature = value(*x)
    reports = {}
    for name, (v0, v1) in directions.items():
        if not (np.any(v0) or np.any(v1)):
            reports[name] = {"tested": False, "reason": "zero native direction; no coverage claimed"}
            continue
        tangent = jvp(v0, v1)
        lhs = float(np.sum(tangent*u))
        rhs = float(np.sum(gradients[0]*v0)+np.sum(gradients[1]*v1))
        dot_error = abs(lhs-rhs)/max(abs(lhs), abs(rhs), 1e-12)
        trials = []
        for eps in EPSILONS:
            plus, bp = value(x[0]+eps*v0, x[1]+eps*v1)
            minus, bm = value(x[0]-eps*v0, x[1]-eps*v1)
            fd = (plus-minus)/(2*eps)
            error = np.max(np.abs((fd-tangent)/OUTPUT_SCALES), axis=1)
            signal = np.maximum(np.max(np.abs(fd/OUTPUT_SCALES), axis=1),
                                np.max(np.abs(tangent/OUTPUT_SCALES), axis=1))
            ratio = error/(FD_ATOL+FD_RTOL*signal)
            eligible = bool(np.array_equal(bp, signature) and np.array_equal(bm, signature)
                            and not np.isin(signature[0], (-2, 2)).any())
            trials.append({"epsilon": eps, "branch_preserved": eligible,
                           "max_tolerance_ratio": float(np.max(ratio)),
                           "per_output_tolerance_ratio": dict(zip(OUTPUT_FIELDS, map(float, ratio))),
                           "per_output_scaled_absolute_error": dict(zip(OUTPUT_FIELDS, map(float, error)))})
        admissible = [t for t in trials if t["branch_preserved"]]
        best = min(admissible, key=lambda t: t["max_tolerance_ratio"]) if admissible else None
        reports[name] = {"tested": True, "dot_lhs": lhs, "dot_rhs": rhs,
                         "dot_relative_error": dot_error, "trials": trials,
                         "best_epsilon": None if best is None else best["epsilon"],
                         "best_max_tolerance_ratio": None if best is None else best["max_tolerance_ratio"],
                         "passed": bool(best and best["max_tolerance_ratio"] <= 1 and dot_error <= DOT_RTOL)}
    tested = [r for r in reports.values() if r["tested"]]
    return {"branch_signature": branch_summary(signature), "directions": reports,
            "passed": bool(tested) and all(r["passed"] for r in tested)}


def verify(args):
    root = Path(__file__).resolve().parents[1]
    module_path = root/"oracle/kdm6/native_finish.py"
    sources = {"trace": Path(args.trace).resolve(), "namelist": Path(args.namelist).resolve(),
               "library": Path(args.library).resolve(), "verifier": Path(__file__).resolve(),
               "finish_module": module_path, "f32_replay_module": root/"harness/native_finish_replay.py",
               "namelist_parser_module": root/"harness/run_ss_case.py",
               "trace_parser_module": root/"harness/native_trace_records.py",
               "kernel_abi_module": root/"harness/verify_state_forcing_ad.py"}
    dest = Path(args.output)
    if dest.resolve() in sources.values() or dest.exists() or dest.is_symlink():
        raise ValueError("output must be new and distinct from inputs and sources")
    pinned = {name: sha(path) for name, path in sources.items()}
    case = load_case(args.trace, args.namelist, args.step, args.i, args.j, args.levels)
    api = _api()
    if Path(api.__file__).resolve() != module_path:
        raise ValueError("finish module did not resolve to this source tree")
    config, zero = api.FinishConfig(**case.config), api.ZeroOutConfig(**case.zero)
    phase = np.arange(args.levels)
    u = np.ascontiguousarray(np.sin(.23*(np.arange(5*args.levels).reshape(5, -1)+1))/OUTPUT_SCALES)
    vb = np.stack((.2*np.sin(.37*(phase+1)), .02*case.before[1]*np.cos(.29*(phase+2)),
                   .02*case.before[2]*np.sin(.31*(phase+1))))
    va = np.stack((.2*np.cos(.41*(phase+1)), .02*case.after[1]*np.sin(.27*(phase+2)),
                   .02*case.after[2]*np.cos(.33*(phase+1))))
    finish_dirs = {}
    for which, base in (("before", vb), ("after", va)):
        for k, field in enumerate(("theta", "qv", "qc")):
            direction = np.zeros_like(base)
            direction[k] = base[k]
            finish_dirs[f"{which}_{field}"] = (direction, np.zeros_like(base)) if which == "before" else (np.zeros_like(base), direction)
    finish_dirs["mixed"] = (vb, va)
    finish = check_stage(
        lambda b, a: (finish_value(b, a, config), branch_codes(b, a, case.config)),
        lambda db, da: finish_jvp(case.before, case.after, db, da, config),
        finish_vjp(case.before, case.after, u, config), (case.before, case.after), finish_dirs, u)
    kernel = Kernel(args.library, args.levels, case.config["dt"], args.xland, *case.ncmin)
    adapter = KernelFinish(kernel, config, zero)
    base_out, handle, raw_after = adapter.forward(case.state, case.forcing, record=True)
    try:
        ds = np.zeros_like(case.state)
        ds[:3] = vb
        df = .01*case.forcing*np.sin(.31*(phase[None, :]+np.arange(4)[:, None]+1))
        directions = {"state_theta_qv_qc": (ds, np.zeros_like(df))}
        for k, field in enumerate(FORCING_FIELDS):
            only = np.zeros_like(df)
            only[k] = df[k]
            directions["forcing_"+field] = (np.zeros_like(ds), only)
        directions["mixed"] = (ds, df)
        gs, gf, direct = adapter.vjp(case.state, raw_after, handle, u)
        def composed_value(s, f):
            result, h, y = adapter.forward(s, f)
            kernel.close(h)
            return result, branch_codes(s[:3], y[:3], case.config, case.zero)
        composed = check_stage(composed_value,
            lambda vs, vf: adapter.jvp(case.state, raw_after, handle, vs, vf),
            (gs, gf), (case.state, case.forcing), directions, u)
        composed["direct_old_state_vjp_contribution_for_state_direction"] = float(np.sum(direct*ds))
        composed["state_dot_rhs_without_direct_old_state"] = float(np.sum((gs-direct)*ds))
        composed["scope"] = "R_s + R_y Z_y K_s, R_y Z_y K_F; no host forcing generation/RK/RTTOV"
        if not np.isfinite(base_out).all():
            raise ValueError("nonfinite composed forward")
    finally:
        kernel.close(handle)
    if any(sha(sources[name]) != h for name, h in pinned.items()):
        raise RuntimeError("a pinned input or source changed during verification")
    report = {"schema": "kdm6.applied_finish_ad.v1", "source": vars(args).copy(),
              "input_sha256": pinned,
              "configuration": case.config, "zero_out": case.zero,
              "output_order": OUTPUT_FIELDS, "output_scales": OUTPUT_SCALES[:, 0].tolist(),
              "criteria": {"fd_scaled_absolute": FD_ATOL, "fd_relative": FD_RTOL, "dot_relative": DOT_RTOL},
              "f32_value_replay": case.f32_replay, "fp64_finish": finish, "fp64_kernel_zero_finish": composed,
              "passed": finish["passed"] and composed["passed"],
              "limits": "interior column; local branch map; zero native directions not certified; kernel integer schedules not exposed; no host integration or observation evaluation"}
    report["source"] = {k: str(v) if isinstance(v, Path) else v for k, v in report["source"].items()}
    serialized = json.dumps(report, indent=2, allow_nan=False)+"\n"
    with dest.open("x") as stream:
        stream.write(serialized)
    print(json.dumps({"passed": report["passed"], "f32": case.f32_replay,
                      "finish": finish["passed"], "composed": composed["passed"]}, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("trace", "namelist", "library", "output"):
        p.add_argument("--"+name, required=True, type=Path)
    for name in ("step", "i", "j"):
        p.add_argument("--"+name, required=True, type=int)
    p.add_argument("--levels", type=int, default=39)
    p.add_argument("--xland", type=float, required=True)
    verify(p.parse_args())
