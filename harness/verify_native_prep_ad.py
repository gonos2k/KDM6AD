"""Offline native prep -> KDM -> cleanup -> finish first-order verification.

This column map excludes dynamics/RK, radiation, horizontal transport and RTTOV.
Opaque C buffers carry values and first-order products, never a live Torch graph.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np

from harness.verify_native_finish_ad import (
    KernelFinish, OUTPUT_FIELDS as FINISH_FIELDS, OUTPUT_SCALES as FINISH_SCALES,
    branch_codes, _api as finish_api,
)
from harness.verify_state_forcing_ad import Kernel, EPSILONS, sha

PREP_FIELDS = ("TH", "DEN", "PII", "P", "DELZ")
PREP_SCALES = np.array([1., 1., .01, 1e5, 1e3])[:, None]
# Declared before evaluating native data. One epsilon must pass every output.
FD_ATOL, FD_RTOL, DOT_RTOL = 1e-9, 3e-6, 1e-10


def _api():
    from oracle.kdm6 import native_prep
    return native_prep


def pack_state(state):
    """Value-only native serialization: L theta_m, L QV, scalar MU, L+1 PH."""
    return np.ascontiguousarray(np.concatenate([np.asarray(v).reshape(-1) for v in state]), dtype=np.float64)


def unpack_state(x, levels):
    if not isinstance(x, np.ndarray) or x.dtype != np.float64:
        raise TypeError("native state must be a binary64 ndarray")
    if x.shape != (3*levels+2,):
        raise ValueError("native state must contain L theta_m, L QV, scalar MU, L+1 PH")
    if not np.isfinite(x).all():
        raise ValueError("native state must be finite")
    return x[:levels], x[levels:2*levels], x[2*levels].reshape(()), x[2*levels+1:]


def _tensor_state(x, levels):
    import torch
    return _api().NativePrepState(*(torch.from_numpy(np.ascontiguousarray(v).reshape(v.shape))
                                    for v in unpack_state(x, levels)))


def _array_result(result):
    # Explicit first-order product serialization; no higher derivative contract.
    return np.ascontiguousarray(np.stack([v.numpy() for v in result]))


class Prep:
    def __init__(self, levels, geometry, config):
        import torch
        api = _api()
        self.levels = levels
        self.geometry = api.FrozenPrepGeometry(**{
            name: torch.from_numpy(np.ascontiguousarray(v, dtype=np.float64))
            for name, v in geometry.items()})
        self.config = api.NativePrepConfig(**config)

    def forward(self, x):
        return _array_result(_api().native_prep(
            _tensor_state(x, self.levels), self.geometry, self.config))

    def jvp(self, x, dx):
        return _array_result(_api().native_prep_jvp(
            _tensor_state(x, self.levels), self.geometry,
            _tensor_state(dx, self.levels), self.config))

    def vjp(self, x, u):
        import torch
        if not isinstance(u, np.ndarray) or u.dtype != np.float64:
            raise TypeError("prep cotangent must be a binary64 ndarray")
        if u.shape != (5, self.levels) or not np.isfinite(u).all():
            raise ValueError("prep cotangent must be finite with shape (5, L)")
        cotangent = _api().NativePrepResult(*(torch.from_numpy(np.ascontiguousarray(v)) for v in u))
        result = _api().native_prep_vjp(
            _tensor_state(x, self.levels), self.geometry, cotangent, self.config)
        return pack_state([v.numpy() for v in result])


@dataclass
class RecordedColumn:
    x: np.ndarray
    state: np.ndarray
    after: np.ndarray
    handle: object


class PrepKernelFinish:
    """G(X) feeds K's dry theta and all four forcing inputs before Z and R.

    Remaining ten KDM inputs retain their captured legacy/raw coordinates.
    The direct QV identity and direct old-state finish paths are both included.
    Caller must release each returned handle through ``finish.kernel.close``.
    """
    def __init__(self, prep, finish):
        self.prep, self.finish = prep, finish
        self.levels = prep.levels

    def _rest(self, rest):
        self.finish._check(rest, 10, "remaining kernel state")

    def forward(self, x, rest, *, record=False):
        self._rest(rest)
        native = unpack_state(x, self.levels)
        g = self.prep.forward(x)
        self.finish._check(g, 5, "prep output")
        state = np.ascontiguousarray(np.vstack((g[0], native[1], rest)))
        result, handle, after = self.finish.forward(state, np.ascontiguousarray(g[1:]), record=record)
        return result, RecordedColumn(x.copy(), state, after, handle)

    def jvp(self, record, dx, drest):
        self._rest(drest)
        direction = unpack_state(dx, self.levels)
        dg = self.prep.jvp(record.x, dx)
        self.finish._check(dg, 5, "prep tangent")
        ds = np.ascontiguousarray(np.vstack((dg[0], direction[1], drest)))
        return self.finish.jvp(record.state, record.after, record.handle, ds,
                               np.ascontiguousarray(dg[1:]))

    def vjp(self, record, u):
        gs, gf, _ = self.finish.vjp(record.state, record.after, record.handle, u)
        seed = np.ascontiguousarray(np.vstack((gs[0], gf)))
        gx = self.prep.vjp(record.x, seed)
        # QV also enters K directly, separately from recovered dry theta.
        gx[self.levels:2*self.levels] += gs[1]
        return gx, np.ascontiguousarray(gs[2:])


def check_stage(value, jvp, gradients, x, directions, u, fields, scales):
    """Fieldwise FD and dot checks with a shared eligible epsilon per direction."""
    _, signature = value(*x)
    reports = {}
    for name, (v0, v1) in directions.items():
        tangent = jvp(v0, v1)
        lhs = float(np.sum(tangent*u))
        rhs = float(np.sum(gradients[0]*v0)+np.sum(gradients[1]*v1))
        dot = abs(lhs-rhs)/max(abs(lhs), abs(rhs), 1e-12)
        trials = []
        for eps in EPSILONS:
            try:
                plus, bp = value(x[0]+eps*v0, x[1]+eps*v1)
                minus, bm = value(x[0]-eps*v0, x[1]-eps*v1)
            except ValueError as exc:
                trials.append({"epsilon": eps, "eligible": False, "reason": str(exc)})
                continue
            fd = (plus-minus)/(2*eps)
            error = np.max(np.abs((fd-tangent)/scales), axis=1)
            signal = np.maximum(np.max(np.abs(fd/scales), axis=1),
                                np.max(np.abs(tangent/scales), axis=1))
            ratio = error/(FD_ATOL+FD_RTOL*signal)
            eligible = bool(np.array_equal(bp, signature) and np.array_equal(bm, signature))
            if signature.size:
                eligible &= not bool(np.isin(signature[0], (-2, 2)).any())
            trials.append({"epsilon": eps, "eligible": eligible,
                           "max_tolerance_ratio": float(np.max(ratio)),
                           "per_output_tolerance_ratio": dict(zip(fields, map(float, ratio)))})
        eligible = [t for t in trials if t["eligible"]]
        best = min(eligible, key=lambda t: t["max_tolerance_ratio"]) if eligible else None
        reports[name] = {"dot_lhs": lhs, "dot_rhs": rhs, "dot_relative_error": dot,
                         "best_epsilon": None if best is None else best["epsilon"],
                         "best_max_tolerance_ratio": None if best is None else best["max_tolerance_ratio"],
                         "trials": trials,
                         "passed": bool(best and best["max_tolerance_ratio"] <= 1 and dot <= DOT_RTOL)}
    return {"directions": reports, "passed": bool(reports) and all(r["passed"] for r in reports.values())}


def native_directions(x, levels):
    phase = np.arange(levels)
    vectors = {}
    t, q, mu, ph = unpack_state(x, levels)
    for name, part in (("theta_m", .2*np.sin(.37*(phase+1))),
                       ("qv", .02*q*np.cos(.29*(phase+2))),
                       ("mu_total", np.array(10.)),
                       ("ph_interfaces", 2.*np.sin(.31*(np.arange(levels+1)+1)))):
        dx = [np.zeros_like(v) for v in (t, q, mu, ph)]
        dx[("theta_m", "qv", "mu_total", "ph_interfaces").index(name)] = part
        vectors[name] = pack_state(dx)
    vectors["mixed"] = sum(vectors.values())
    return vectors


def verify(args):
    from harness.native_prep_replay import load_native_prep_case
    root = Path(__file__).resolve().parents[1]
    sources = {name: Path(getattr(args, name)).resolve() for name in ("trace", "namelist", "checkpoint", "library")}
    for name, relative in {
        "prep_module": "oracle/kdm6/native_prep.py", "finish_module": "oracle/kdm6/native_finish.py",
        "prep_replay": "harness/native_prep_replay.py", "finish_replay": "harness/native_finish_replay.py",
        "finish_verifier": "harness/verify_native_finish_ad.py", "kernel_abi": "harness/verify_state_forcing_ad.py",
        "trace_parser": "harness/native_trace_records.py", "namelist_parser": "harness/run_ss_case.py",
        "checkpoint_reader": "harness/native_replay_compare.py",
    }.items():
        sources[name] = root/relative
    sources["verifier"] = Path(__file__).resolve()
    dest = Path(args.output)
    if dest.resolve() in sources.values() or dest.exists() or dest.is_symlink():
        raise ValueError("output must be new and distinct from inputs and sources")
    pinned = {name: sha(path) for name, path in sources.items()}
    case = load_native_prep_case(args.trace, args.namelist, args.checkpoint,
                                 args.step, args.i, args.j, args.levels)
    if not np.isfinite(args.xland) or np.float32(args.xland) != np.float32(case.xland):
        raise ValueError("xland differs from the selected native checkpoint column")
    if Path(_api().__file__).resolve() != sources["prep_module"]:
        raise ValueError("prep module resolved outside this source tree")
    if Path(finish_api().__file__).resolve() != sources["finish_module"]:
        raise ValueError("finish module resolved outside this source tree")
    prep = Prep(args.levels, case.geometry, case.config)
    x = pack_state(case.X)
    dirs = native_directions(x, args.levels)
    dummy = np.zeros((0, args.levels), dtype=np.float64)
    u = np.ascontiguousarray(np.sin(.23*(np.arange(5*args.levels).reshape(5, -1)+1))/PREP_SCALES)
    prep_report = check_stage(lambda xx, _: (prep.forward(xx), np.array([])),
                             lambda dx, _: prep.jvp(x, dx),
                             (prep.vjp(x, u), dummy), (x, dummy),
                             {n: (v, dummy) for n, v in dirs.items()}, u, PREP_FIELDS, PREP_SCALES)
    gauge = np.zeros_like(x)
    gauge[2*args.levels+1:] = 1.
    gauge_tangent = prep.jvp(x, gauge)
    prep_report["constant_ph_shift_maxabs_jvp"] = float(np.max(np.abs(gauge_tangent)))
    prep_report["constant_ph_shift_adjoint_sum"] = float(np.sum(prep.vjp(x, u)[2*args.levels+1:]))
    prep_report["passed"] &= bool(np.all(gauge_tangent == 0))
    captured = case.captured
    api = finish_api()
    kernel = Kernel(args.library, args.levels, captured.config["dt"], args.xland, *captured.ncmin)
    finish = KernelFinish(kernel, api.FinishConfig(**captured.config), api.ZeroOutConfig(**captured.zero))
    adapter = PrepKernelFinish(prep, finish)
    rest = np.ascontiguousarray(captured.state[2:])
    value, record = adapter.forward(x, rest, record=True)
    try:
        u = np.ascontiguousarray(np.sin(.23*(np.arange(5*args.levels).reshape(5, -1)+1))/FINISH_SCALES)
        def evaluate(xx, rr):
            result, rec = adapter.forward(xx, rr)
            try:
                return result, branch_codes(rec.state[:3], rec.after[:3], captured.config, captured.zero)
            finally:
                kernel.close(rec.handle)
        composed = check_stage(evaluate, lambda dx, dr: adapter.jvp(record, dx, dr),
                               adapter.vjp(record, u), (x, rest),
                               {n: (v, np.zeros_like(rest)) for n, v in dirs.items()},
                               u, FINISH_FIELDS, FINISH_SCALES)
        ablation = {}
        for name in ("theta_m", "mu_total", "ph_interfaces"):
            dx = dirs[name]
            dg = prep.jvp(x, dx)
            dq = unpack_state(dx, args.levels)[1]
            ds = np.ascontiguousarray(np.vstack((dg[0], dq, np.zeros_like(rest))))
            frozen = finish.jvp(record.state, record.after, record.handle, ds,
                                np.zeros((4, args.levels), dtype=np.float64))
            live = adapter.jvp(record, dx, np.zeros_like(rest))
            ablation[name] = dict(zip(FINISH_FIELDS, map(float, np.max(np.abs(live-frozen), axis=1))))
        composed["frozen_forcing_ablation_maxabs_per_output"] = ablation
        composed["scope"] = "R(S(X), Z(K(S(X),G(X)))); selected local prep state; no RK or RTTOV"
        if not np.isfinite(value).all():
            raise ValueError("nonfinite composed output")
    finally:
        kernel.close(record.handle)
    if any(sha(sources[n]) != h for n, h in pinned.items()):
        raise RuntimeError("a pinned input or source changed during verification")
    report = {"schema": "kdm6.native_prep_ad.v1", "input_sha256": pinned,
              "source": {n: str(v) for n, v in sources.items()},
              "selection": {n: getattr(args, n) for n in ("step", "i", "j", "levels", "xland")},
              "configuration": case.config, "phase_provenance": case.phase_provenance,
              "f32_replay": case.f32_replay, "fp64_prep": prep_report,
              "fp64_prep_kernel_finish": composed,
              "criteria": {"fd_scaled_absolute": FD_ATOL, "fd_relative": FD_RTOL,
                           "dot_relative": DOT_RTOL, "epsilons": EPSILONS,
                           "prep_scales": PREP_SCALES[:, 0].tolist(),
                           "finish_scales": FINISH_SCALES[:, 0].tolist()},
              "passed": bool(prep_report["passed"] and composed["passed"]),
              "limits": "offline reconstructed native prep operands; fixed hybrid geometry and constants; remaining ten kernel state directions untested here; legacy raw number basis; no complete host/RK/radiation/RTTOV/cost or HVP"}
    with dest.open("x") as stream:
        stream.write(json.dumps(report, indent=2, allow_nan=False)+"\n")
    print(json.dumps({"passed": report["passed"], "prep": prep_report["passed"], "composed": composed["passed"]}))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("trace", "namelist", "checkpoint", "library", "output"):
        parser.add_argument("--"+name, required=True, type=Path)
    for name in ("step", "i", "j"):
        parser.add_argument("--"+name, required=True, type=int)
    parser.add_argument("--levels", type=int, default=39)
    parser.add_argument("--xland", type=float, required=True)
    verify(parser.parse_args())
