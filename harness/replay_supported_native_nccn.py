"""Fixed two-direction replay of the selected native NCCN column."""
from __future__ import annotations

import gzip
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.replay_nccn_native_fd import _moment_failures

EVIDENCE = ROOT / "harness/evidence"
DEFAULT_TRACE = EVIDENCE / "supported_native_nccn_trace_2026-10-03.tsv.gz"
DEFAULT_MASKS = EVIDENCE / "supported_native_nccn_masks_2026-10-03.tsv.gz"
FIELDS = ("th", "qv", "qc", "qr", "qi", "qs", "qg", "nccn", "nc", "ni", "nr", "bg")
ARRAY_DIMS = {tag: (12, 39) for tag in (
    "STATE_IN BASE_OUT V_MIX JV_MIX JTU_MIX FD_MIX V_NN JV_NN JTU_NN FD_NN "
    "MIX_STATE_PLUS MIX_STATE_MINUS MIX_OUT_PLUS MIX_OUT_MINUS "
    "NN_STATE_PLUS NN_STATE_MINUS NN_OUT_PLUS NN_OUT_MINUS"
).split()}
ARRAY_DIMS["FORCING"] = (4, 39)
CALLS = ((1, "STATE_IN", "BASE_OUT"), (2, "MIX_STATE_PLUS", "MIX_OUT_PLUS"),
         (3, "MIX_STATE_MINUS", "MIX_OUT_MINUS"), (4, "NN_STATE_PLUS", "NN_OUT_PLUS"),
         (5, "NN_STATE_MINUS", "NN_OUT_MINUS"))
FD_LIMIT, DUAL_LIMIT = 1e-5, 1e-12


class TraceError(ValueError):
    pass


def _read(path):
    path = Path(path)
    if not path.is_file():
        raise TraceError(f"missing trace: {path}")
    try:
        compressed = path.read_bytes()
        raw = gzip.decompress(compressed)
        lines = raw.decode("ascii").splitlines()
    except (OSError, EOFError, UnicodeError) as exc:
        raise TraceError(f"invalid gzip ASCII trace: {exc}") from exc
    if not lines or any(not line.strip() for line in lines):
        raise TraceError("empty trace or blank record")
    return lines, hashlib.sha256(raw).hexdigest(), hashlib.sha256(compressed).hexdigest()


def _num(token, where):
    try:
        x = float.fromhex(token) if "0x" in token.lower() else float(token)
    except ValueError as exc:
        raise TraceError(f"invalid {where}: {token}") from exc
    if not math.isfinite(x):
        raise TraceError(f"nonfinite {where}")
    return x


def _eq(x, y):
    return x.hex() == y.hex()


def parse_trace(path=DEFAULT_TRACE):
    lines, raw_sha, zip_sha = _read(path)
    headers = (
        "KDM6_NCCN_TWO_DIRECTION_TRACE_V1", "ITIMESTEP 2",
        "GLOBAL_CELL_IJ_1BASED 142 50", "TILE_LOCAL_IJ_1BASED 141 49",
        "DIMS_IM_KM_JM 232 39 141",
        "SELECTORS variant=2 dry_number=1 state_order=th,qv,qc,qr,qi,qs,qg,nccn,nc,ni,nr,bg forcing_order=rho,pii,p,delz",
    )
    pos = 0
    def header(expected):
        nonlocal pos
        if pos >= len(lines) or lines[pos] != expected:
            raise TraceError(f"header mismatch at line {pos + 1}: {expected}")
        pos += 1
    def scalar(tag, expected):
        nonlocal pos
        if pos >= len(lines):
            raise TraceError(f"missing {tag} header")
        p = lines[pos].split(); pos += 1
        if len(p) != 2 or p[0] != tag or _num(p[1], tag) != expected:
            raise TraceError(f"invalid {tag} header")

    for h in headers[:5]: header(h)
    scalar("DT", 20.0); scalar("H_FD", 1e-4)
    if pos >= len(lines): raise TraceError("missing NCMIN_LAND_SEA")
    p = lines[pos].split(); pos += 1
    if len(p) != 3 or p[0] != "NCMIN_LAND_SEA" or tuple(_num(x, "ncmin") for x in p[1:]) != (10., 10.):
        raise TraceError("invalid NCMIN_LAND_SEA")
    scalar("XLAND", 2.0); header(headers[5])

    arrays = {tag: {} for tag in ARRAY_DIMS}; fd = {}; dual = {}; pass_flags = None
    for lineno, line in enumerate(lines[pos:], pos + 1):
        p = line.split(); tag = p[0]
        if tag in ARRAY_DIMS:
            if len(p) != 4: raise TraceError(f"malformed {tag} line {lineno}")
            try: f, k = int(p[1]), int(p[2])
            except ValueError as exc: raise TraceError(f"bad {tag} index") from exc
            nf, nk = ARRAY_DIMS[tag]
            if not (1 <= f <= nf and 1 <= k <= nk): raise TraceError(f"{tag} index out of range")
            if (f, k) in arrays[tag]: raise TraceError(f"duplicate {tag} index {(f, k)}")
            arrays[tag][(f, k)] = _num(p[3], f"{tag}{f},{k}")
        elif tag in ("MIX_DUALITY", "NN_DUALITY"):
            if len(p) != 5 or tag in dual or p[1:3] != ["0", "0"]:
                raise TraceError(f"malformed or duplicate {tag}")
            dual[tag] = tuple(_num(x, tag) for x in p[3:])
        elif tag == "FD_PASS_MIX_NN":
            if len(p) != 3 or pass_flags is not None or p[1:] not in (["0", "0"], ["0", "1"], ["1", "0"], ["1", "1"]):
                raise TraceError("malformed or duplicate FD_PASS_MIX_NN")
            pass_flags = tuple(map(int, p[1:]))
        elif tag == "FD_FIELD":
            if len(p) != 9: raise TraceError(f"malformed FD_FIELD line {lineno}")
            try: f, worst = int(p[1]), int(p[5])
            except ValueError as exc: raise TraceError("invalid FD_FIELD index") from exc
            if not 1 <= f <= 12 or f in fd or not 1 <= worst <= 12:
                raise TraceError(f"duplicate/out-of-range FD_FIELD {f}")
            fd[f] = tuple(_num(x, f"FD_FIELD{f}") for x in p[2:5]) + (worst,) + tuple(_num(x, f"FD_FIELD{f}") for x in p[6:])
        else:
            raise TraceError(f"unknown trace tag {tag} at line {lineno}")
    if set(dual) != {"MIX_DUALITY", "NN_DUALITY"} or pass_flags is None or set(fd) != set(range(1, 13)):
        raise TraceError("missing duality or FD summary records")
    shaped = {}
    for tag, (nf, nk) in ARRAY_DIMS.items():
        expected = {(f, k) for f in range(1, nf + 1) for k in range(1, nk + 1)}
        if set(arrays[tag]) != expected: raise TraceError(f"incomplete {tag} coverage")
        shaped[tag] = [[arrays[tag][(f, k)] for k in range(1, nk + 1)] for f in range(1, nf + 1)]
    return dict(arrays=shaped, fd=fd, duality=dual, pass_flags=pass_flags,
                raw_sha256=raw_sha, compressed_sha256=zip_sha, h=1e-4,
                metadata=dict(itimestep=2, global_ij_1based=[142, 50],
                              tile_ij_1based=[141, 49], dims_im_km_jm=[232, 39, 141],
                              dt=20., h_fd=1e-4, ncmin_land_sea=[10., 10.], xland=2.))


def parse_masks(path=DEFAULT_MASKS):
    lines, raw_sha, zip_sha = _read(path)
    if lines[0] != "call_counter k1based NinVol(hex) NoutVol(hex) DeltaVol(hex) RhoDry(hex) zero_mask":
        raise TraceError("raw-mask header mismatch")
    rows = {}
    for lineno, line in enumerate(lines[1:], 2):
        p = line.split()
        if len(p) != 7: raise TraceError(f"malformed mask line {lineno}")
        try: call, k, bit = int(p[0]), int(p[1]), int(p[6])
        except ValueError as exc: raise TraceError(f"invalid mask index line {lineno}") from exc
        if not 1 <= call <= 5 or not 1 <= k <= 39 or bit not in (0, 1):
            raise TraceError(f"mask index/bit out of range line {lineno}")
        key = (call, k)
        if key in rows: raise TraceError(f"duplicate mask row {key}")
        nin, nout, delta, rho = (_num(x, f"mask{key}") for x in p[2:6])
        if rho <= 0 or not _eq(nout - nin, delta) or bit != int(delta == 0.):
            raise TraceError(f"mask disagrees with raw DeltaVol at {key}")
        rows[key] = (nin, nout, delta, rho, bit)
    if set(rows) != {(c, k) for c in range(1, 6) for k in range(1, 40)}:
        raise TraceError("mask trace must cover each of 5 calls x 39 levels")
    return dict(rows=rows, raw_sha256=raw_sha, compressed_sha256=zip_sha)


def replay(trace_path=DEFAULT_TRACE, mask_path=DEFAULT_MASKS):
    t, m = parse_trace(trace_path), parse_masks(mask_path)
    a, h = t["arrays"], t["h"]
    input_tags = {1: "STATE_IN", 2: "MIX_STATE_PLUS", 3: "MIX_STATE_MINUS", 4: "NN_STATE_PLUS", 5: "NN_STATE_MINUS"}
    output_tags = {1: "BASE_OUT", 2: "MIX_OUT_PLUS", 3: "MIX_OUT_MINUS", 4: "NN_OUT_PLUS", 5: "NN_OUT_MINUS"}
    dirs = {"mix": ("V_MIX", "JV_MIX", "JTU_MIX", "FD_MIX", "MIX_STATE_PLUS", "MIX_STATE_MINUS", "MIX_OUT_PLUS", "MIX_OUT_MINUS"),
            "nn": ("V_NN", "JV_NN", "JTU_NN", "FD_NN", "NN_STATE_PLUS", "NN_STATE_MINUS", "NN_OUT_PLUS", "NN_OUT_MINUS")}
    endpoints_ok = fd_ok = directions_ok = True
    fd_metrics, fd_pass = {"mix": {}, "nn": {}}, {"mix": True, "nn": True}
    for f, name in enumerate(FIELDS):
        for k in range(39):
            x = a["STATE_IN"][f][k]
            vm = x * (1. if name == "qi" else .01 if name in ("qv", "nc") else 0.)
            vn = x * .01 if name == "nccn" else 0.
            directions_ok &= _eq(vm, a["V_MIX"][f][k]) and _eq(vn, a["V_NN"][f][k])
            for d, (vtag, jtag, _, ftag, plus, minus, outp, outm) in dirs.items():
                endpoints_ok &= _eq(x + h * a[vtag][f][k], a[plus][f][k])
                endpoints_ok &= _eq(x - h * a[vtag][f][k], a[minus][f][k])
                fd = (a[outp][f][k] - a[outm][f][k]) / (2. * h)
                fd_ok &= _eq(fd, a[ftag][f][k])
    if not directions_ok: raise TraceError("direction differs from the fixed mixed/NCCN-only policy")
    if not endpoints_ok: raise TraceError("state endpoint differs from input +/- h*V")
    if not fd_ok: raise TraceError("stored FD differs from recomputed output endpoints")

    worst_mix = max(range(1, 13), key=lambda f: (t["fd"][f][2], -f))
    if any(t["fd"][f][3] != worst_mix for f in range(1, 13)):
        raise TraceError("mixed FD_FIELD worst-field value is inconsistent")
    for d, (vtag, jtag, _, ftag, *_) in dirs.items():
        for f, name in enumerate(FIELDS):
            errors = [abs(a[ftag][f][k] - a[jtag][f][k]) for k in range(39)]
            scales = [max(abs(a[ftag][f][k]), abs(a[jtag][f][k])) for k in range(39)]
            err, scale = max(errors), max(scales)
            rel = 0. if err == 0 and scale == 0 else (math.inf if scale == 0 else err / scale)
            summary = t["fd"][f + 1]
            ix = 0 if d == "mix" else 4
            if any(not _eq(q, r) for q, r in zip((err, scale, rel), summary[ix:ix + 3])):
                raise TraceError(f"FD_FIELD {f+1} {d} metrics mismatch")
            fd_pass[d] &= math.isfinite(rel) and rel <= FD_LIMIT
            fd_metrics[d][name] = dict(max_abs=err, scale=scale, relative=rel)
    expected_pass = (int(fd_pass["mix"]), int(fd_pass["nn"]))
    if expected_pass != t["pass_flags"]: raise TraceError("FD_PASS_MIX_NN mismatch")

    dual = {}
    for d, (vtag, jtag, jt_tag, *_rest) in dirs.items():
        v = [x for row in a[vtag] for x in row]; j = [x for row in a[jtag] for x in row]
        jt = [x for row in a[jt_tag] for x in row]
        left, right = math.fsum(x*x for x in j), math.fsum(x*y for x, y in zip(v, jt))
        rel = abs(left-right)/max(abs(left), abs(right), sys.float_info.min)
        nleft, nright = t["duality"]["MIX_DUALITY" if d == "mix" else "NN_DUALITY"]
        dual[d] = dict(left_fsum=left, right_fsum=right, relative=rel,
                       native_left_sum=nleft, native_right_sum=nright,
                       passed=math.isfinite(rel) and rel <= DUAL_LIMIT)

    mask_rows, nidx = m["rows"], FIELDS.index("nccn")
    masks_by_call, reconstruction_exact, direct_diff_count = {c: [] for c in range(1, 6)}, True, 0
    for call, input_tag, output_tag in CALLS:
        for k in range(1, 40):
            nin, nout, delta, rho, zero = mask_rows[(call, k)]
            n = a[input_tag][nidx][k-1]
            expected_rho = a["FORCING"][0][k-1] / (1.0 + a[input_tag][1][k-1])
            if not _eq(rho, expected_rho): raise TraceError("raw dry density does not match entry forcing/qv")
            if not _eq(n * rho, nin): raise TraceError(f"raw N_in does not match state NCCN*rho at {call},{k}")
            chosen = n + delta/rho if zero else nout/rho
            direct = nout/rho
            actual = a[output_tag][nidx][k-1]
            reconstruction_exact &= _eq(chosen, actual)
            direct_diff_count += int(not _eq(direct, actual))
            masks_by_call[call].append(zero)
    if not reconstruction_exact: raise TraceError("raw return branch does not reproduce output NCCN bits")
    branch_local = all(masks_by_call[c] == masks_by_call[1] for c in range(2, 6))

    state_tags = ("STATE_IN", "BASE_OUT", "MIX_STATE_PLUS", "MIX_STATE_MINUS", "MIX_OUT_PLUS", "MIX_OUT_MINUS",
                  "NN_STATE_PLUS", "NN_STATE_MINUS", "NN_OUT_PLUS", "NN_OUT_MINUS")
    admitted, preconditions = {}, {}
    for tag in state_tags:
        state = np.asarray(a[tag], dtype=np.float64)
        preconditions[tag] = bool(np.isfinite(state).all() and (state[0] > 0).all() and (state[1:] >= 0).all())
        admitted[tag] = preconditions[tag] and not any(_moment_failures(state.tolist()).values())
    forcing = np.asarray(a["FORCING"], dtype=np.float64)
    forcing_valid = bool(np.isfinite(forcing).all() and (forcing > 0).all())
    numerical_pass = all(fd_pass.values()) and all(x["passed"] for x in dual.values()) and forcing_valid
    strict_states_pass = all(admitted.values()) and all(preconditions.values())
    branch_local_fd_pass = bool(numerical_pass and branch_local)
    supported = bool(branch_local_fd_pass and strict_states_pass and reconstruction_exact)
    return dict(
        trace_sha256=t["raw_sha256"], mask_trace_sha256=m["raw_sha256"],
        trace_compressed_sha256=t["compressed_sha256"], mask_compressed_sha256=m["compressed_sha256"],
        metadata=t["metadata"], numerical_pass=numerical_pass, field_relative=fd_metrics, duality=dual,
        runner_preconditions_passed=preconditions, strict_pair_admitted=admitted,
        strict_pair_state_admitted_all_states=strict_states_pass, forcing_valid=forcing_valid,
        return_reconstruction_bitwise_equal=reconstruction_exact, direct_return_mismatch_count=direct_diff_count,
        return_branch_local=branch_local, branch_crossing=not branch_local,
        branch_local_fd_pass=branch_local_fd_pass,
        raw_mask_zero_count_per_call={str(c): sum(masks_by_call[c]) for c in range(1, 6)},
        raw_mask_changed_count_per_call={str(c): 39-sum(masks_by_call[c]) for c in range(1, 6)},
        raw_masks_identical_across_calls=branch_local, supported_diagnostic_pass=supported,
        physical_number_basis_resolved=False, physical_nccn_process_approved=False,
        observational_admission=False,
        status="SUPPORTED_NATIVE_DIAGNOSTIC_PASS" if supported else (
            "NUMERICAL_PASS_BRANCH_CROSSING" if numerical_pass and not branch_local else "NATIVE_DIAGNOSTIC_CHECK_FAILED"),
    )


def main():
    paths = sys.argv[1:]
    if len(paths) not in (0, 2):
        print("usage: replay_supported_native_nccn.py [TRACE.tsv.gz MASKS.tsv.gz]", file=sys.stderr)
        return 2
    try:
        result = replay(*(paths or (DEFAULT_TRACE, DEFAULT_MASKS)))
    except TraceError as exc:
        print(json.dumps({"status": "INVALID_TRACE", "error": str(exc)}, indent=2, allow_nan=False))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0 if result["supported_diagnostic_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
