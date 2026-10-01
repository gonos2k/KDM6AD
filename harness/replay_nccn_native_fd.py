"""Fixed-schema, no-Torch replay of the staged native NCCN FD trace."""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import sys
from pathlib import Path


DEFAULT_TRACE = (
    Path(__file__).resolve().parent
    / "evidence"
    / "nccn_native_fd_trace_2026-10-02.tsv.gz"
)
STATE_NAMES = (
    "th", "qv", "qc", "qr", "qi", "qs", "qg", "nccn", "nc", "ni", "nr", "bg"
)
FORCING_NAMES = ("rho", "pii", "p", "delz")
ARRAY_DIMS = {
    "STATE_IN": (12, 39),
    "STATE_PLUS": (12, 39),
    "STATE_MINUS": (12, 39),
    "OUT_BASE": (12, 39),
    "OUT_PLUS": (12, 39),
    "OUT_MINUS": (12, 39),
    "V": (12, 39),
    "JV": (12, 39),
    "JTU": (12, 39),
    "FD": (12, 39),
    "FORCING": (4, 39),
    "XLAND": (1, 1),
}
FD_REL_LIMIT = 1.0e-5
DUALITY_LIMIT = 1.0e-12


class TraceError(ValueError):
    """A malformed or inconsistent fixed-case native trace."""


def _read_lines(path: Path) -> tuple[list[str], bytes]:
    if not path.is_file():
        raise TraceError(f"trace not found: {path}")
    try:
        with gzip.open(path, "rb") as stream:
            raw = stream.read()
        lines = raw.decode("ascii").splitlines()
    except (OSError, EOFError, UnicodeError) as exc:
        raise TraceError(f"cannot read gzip ASCII trace: {exc}") from exc
    if not lines or any(not line.strip() for line in lines):
        raise TraceError("trace is empty or contains blank lines")
    return lines, raw


def _float(token: str, context: str) -> float:
    try:
        value = float(token)
    except ValueError as exc:
        raise TraceError(f"invalid numeric value for {context}: {token!r}") from exc
    if not math.isfinite(value):
        raise TraceError(f"nonfinite value for {context}")
    return value


def _expect_scalar_header(parts: list[str], label: str, expected: float) -> None:
    if len(parts) != 2 or parts[0] != label:
        raise TraceError(f"expected {label} metadata")
    actual = _float(parts[1], label)
    if actual != expected:
        raise TraceError(f"unexpected {label}: {actual!r}")


def parse_trace(path: str | Path = DEFAULT_TRACE) -> dict:
    """Parse the exact fixed case; require full, unique one-based coverage."""
    trace_path = Path(path)
    lines, raw = _read_lines(trace_path)
    cursor = 0

    def take_line() -> str:
        nonlocal cursor
        if cursor >= len(lines):
            raise TraceError("truncated trace metadata")
        line = lines[cursor]
        cursor += 1
        return line

    def header(expected: str) -> None:
        line = take_line()
        if line != expected:
            raise TraceError(f"trace header mismatch at line {cursor}: expected {expected!r}")

    header("KDM6_NCCN_ZERO_FD_TRACE_V1")
    parts = take_line().split()
    if parts != ["kme", "39"]:
        raise TraceError("kme metadata must be 39")
    _expect_scalar_header(take_line().split(), "dt", 20.0)
    _expect_scalar_header(take_line().split(), "h", 1.0e-4)
    _expect_scalar_header(take_line().split(), "ncmin_land", 10.0)
    _expect_scalar_header(take_line().split(), "ncmin_sea", 10.0)
    header("selectors physics_variant=2 dry_number=1 value_only_base=0 value_only_endpoints=1")
    header("cell global_i=200 global_j=152 tile_i=199 tile_j=10")
    header("STATE_SHAPE 1 39 1 12")
    header("FORCING_SHAPE 1 39 1 4")
    header("XLAND_SHAPE 1 1")
    header("state_order=th,qv,qc,qr,qi,qs,qg,nccn,nc,ni,nr,bg")
    header("forcing_order=rho,pii,p,delz")

    arrays: dict[str, dict[tuple[int, int], float]] = {tag: {} for tag in ARRAY_DIMS}
    fd_fields: dict[int, tuple[float, float, float]] = {}
    fd_pass_worst: tuple[int, int] | None = None
    summary_started = False
    for line_no, line in enumerate(lines[cursor:], cursor + 1):
        parts = line.split()
        tag = parts[0]
        if tag in ARRAY_DIMS:
            if summary_started:
                raise TraceError(f"array record after summary at line {line_no}")
            if len(parts) != 4:
                raise TraceError(f"malformed {tag} record at line {line_no}")
            try:
                first, second = int(parts[1]), int(parts[2])
            except ValueError as exc:
                raise TraceError(f"invalid {tag} index at line {line_no}") from exc
            nfirst, nsecond = ARRAY_DIMS[tag]
            if not (1 <= first <= nfirst and 1 <= second <= nsecond):
                raise TraceError(f"{tag} index out of range at line {line_no}")
            key = (first, second)
            if key in arrays[tag]:
                raise TraceError(f"duplicate {tag} index {key}")
            arrays[tag][key] = _float(parts[3], f"{tag}{key}")
        elif tag == "FD_PASS_WORST_FIELD":
            summary_started = True
            if len(parts) != 3 or fd_pass_worst is not None:
                raise TraceError(f"malformed or duplicate FD_PASS_WORST_FIELD at line {line_no}")
            try:
                fd_pass_worst = (int(parts[1]), int(parts[2]))
            except ValueError as exc:
                raise TraceError(f"invalid FD_PASS_WORST_FIELD at line {line_no}") from exc
            if fd_pass_worst[0] not in (0, 1) or not 1 <= fd_pass_worst[1] <= 12:
                raise TraceError("FD_PASS_WORST_FIELD values are out of range")
        elif tag == "FD_FIELD":
            summary_started = True
            if len(parts) != 5:
                raise TraceError(f"malformed FD_FIELD at line {line_no}")
            try:
                field = int(parts[1])
            except ValueError as exc:
                raise TraceError(f"invalid FD_FIELD number at line {line_no}") from exc
            if not 1 <= field <= 12 or field in fd_fields:
                raise TraceError(f"duplicate or out-of-range FD_FIELD {field}")
            fd_fields[field] = tuple(_float(v, f"FD_FIELD {field}") for v in parts[2:])
        else:
            raise TraceError(f"unknown record tag {tag!r} at line {line_no}")

    if fd_pass_worst is None:
        raise TraceError("missing FD_PASS_WORST_FIELD")
    if set(fd_fields) != set(range(1, 13)):
        raise TraceError("FD_FIELD coverage must contain each field 1..12 exactly once")
    for tag, (nfirst, nsecond) in ARRAY_DIMS.items():
        expected = {(i, k) for i in range(1, nfirst + 1) for k in range(1, nsecond + 1)}
        if set(arrays[tag]) != expected:
            missing = sorted(expected - set(arrays[tag]))[:4]
            raise TraceError(f"{tag} coverage incomplete; missing {missing}")

    shaped = {
        tag: [[arrays[tag][(i, k)] for k in range(1, nsecond + 1)]
              for i in range(1, nfirst + 1)]
        for tag, (nfirst, nsecond) in ARRAY_DIMS.items()
    }
    return {
        "metadata": {
            "kme": 39,
            "dt": 20.0,
            "h": 1.0e-4,
            "ncmin_land": 10.0,
            "ncmin_sea": 10.0,
            "physics_variant": 2,
            "dry_number": 1,
            "value_only_base": 0,
            "value_only_endpoints": 1,
            "cell": {"global_i": 200, "global_j": 152, "tile_i": 199, "tile_j": 10},
            "state_shape": [1, 39, 1, 12],
            "forcing_shape": [1, 39, 1, 4],
            "xland_shape": [1, 1],
            "state_order": list(STATE_NAMES),
            "forcing_order": list(FORCING_NAMES),
        },
        "arrays": shaped,
        "reported_fd_pass": fd_pass_worst[0],
        "reported_worst_field": fd_pass_worst[1],
        "reported_fd_fields": fd_fields,
        "trace_sha256": hashlib.sha256(raw).hexdigest(),
        "compressed_sha256": hashlib.sha256(trace_path.read_bytes()).hexdigest(),
    }


def _same_float(a: float, b: float) -> bool:
    return a.hex() == b.hex()


def _moment_failures(state: list[list[float]]) -> dict[str, int]:
    pairs = (("qc/nc", 2, 8), ("qr/nr", 3, 10),
             ("qi/ni", 4, 9), ("qg/bg", 6, 11))
    return {
        # A pair is inconsistent when exactly one moment is active. This
        # catches both positive condensate with zero number and qg==0 with
        # positive bg; either case is outside the strict paired-state policy.
        name: sum((mass < 0.0 or number < 0.0) or ((mass == 0.0) != (number == 0.0))
                  for mass, number in zip(state[mass_i], state[number_i]))
        for name, mass_i, number_i in pairs
    }


def replay(path: str | Path = DEFAULT_TRACE) -> dict:
    """Recompute endpoint arithmetic, FD fields and duality without Torch."""
    trace = parse_trace(path)
    a = trace["arrays"]
    h = trace["metadata"]["h"]
    # The direction is fixed by the measured producer, not inferred from
    # arbitrary endpoint differences in a supplied trace.
    for f in range(12):
        for k in range(39):
            expected = (a["STATE_IN"][f][k] if f == 4 else
                        0.01 * a["STATE_IN"][f][k] if f in (1, 8) else 0.0)
            if not _same_float(expected, a["V"][f][k]):
                raise TraceError("direction differs from the declared native mixed seed")
    endpoint_exact = True
    fd_exact = True
    computed_fd = [[0.0] * 39 for _ in range(12)]
    for f in range(12):
        for k in range(39):
            state_in = a["STATE_IN"][f][k]
            direction = a["V"][f][k]
            plus = state_in + h * direction
            minus = state_in - h * direction
            endpoint_exact &= _same_float(plus, a["STATE_PLUS"][f][k])
            endpoint_exact &= _same_float(minus, a["STATE_MINUS"][f][k])
            value = (a["OUT_PLUS"][f][k] - a["OUT_MINUS"][f][k]) / (2.0 * h)
            computed_fd[f][k] = value
            fd_exact &= _same_float(value, a["FD"][f][k])
    if not endpoint_exact:
        raise TraceError("STATE_PLUS/MINUS do not match STATE_IN +/- h*V")
    if not fd_exact:
        raise TraceError("stored FD differs from recomputed centered endpoints")

    computed_fields: dict[int, dict[str, float]] = {}
    rels: list[float] = []
    field_pass = True
    for f in range(12):
        errors = [abs(computed_fd[f][k] - a["JV"][f][k]) for k in range(39)]
        scales = [max(abs(computed_fd[f][k]), abs(a["JV"][f][k])) for k in range(39)]
        max_abs = max(errors)
        scale = max(scales)
        relative = 0.0 if scale == 0.0 and max_abs == 0.0 else (math.inf if scale == 0.0 else max_abs / scale)
        reported = trace["reported_fd_fields"][f + 1]
        metrics = (max_abs, scale, relative)
        if any(not _same_float(x, y) for x, y in zip(metrics, reported)):
            raise TraceError(f"FD_FIELD {f + 1} does not match recomputed per-field metrics")
        field_pass &= math.isfinite(relative) and relative <= FD_REL_LIMIT
        rels.append(relative)
        computed_fields[f + 1] = {
            "max_abs_error": max_abs,
            "scale": scale,
            "relative_maxnorm_error": relative,
        }
    worst_field = max(range(1, 13), key=lambda f: (rels[f - 1], -f))
    if trace["reported_fd_pass"] != int(field_pass) or trace["reported_worst_field"] != worst_field:
        raise TraceError("FD_PASS_WORST_FIELD does not match recomputed pass/worst field")

    jv = [value for row in a["JV"] for value in row]
    v = [value for row in a["V"] for value in row]
    jtu = [value for row in a["JTU"] for value in row]
    # Specify the independent reduction: builtin sum changed for floats in
    # Python 3.12. Native SUM's measured residue remains in the run receipt.
    try:
        left_dot = math.fsum(value * value for value in jv)
        right_dot = math.fsum(x * y for x, y in zip(v, jtu))
    except (OverflowError, ValueError) as exc:
        raise TraceError("nonfinite or overflowing duality reduction") from exc
    if not all(math.isfinite(x) and x != 0.0 for x in (left_dot, right_dot)):
        raise TraceError("duality products must be finite and nonzero")
    duality = abs(left_dot - right_dot) / max(abs(left_dot), abs(right_dot))
    duality_pass = math.isfinite(duality) and duality <= DUALITY_LIMIT
    numerical_pass = bool(endpoint_exact and fd_exact and field_pass and duality_pass)

    input_failures = _moment_failures(a["STATE_IN"])
    output_failures = _moment_failures(a["OUT_BASE"])
    scalar_domain = all(
        all(x > 0.0 for x in a[tag][0]) and
        all(x >= 0.0 for row in a[tag][1:] for x in row)
        for tag in ("STATE_IN", "STATE_PLUS", "STATE_MINUS", "OUT_BASE", "OUT_PLUS", "OUT_MINUS")
    ) and all(x > 0.0 for row in a["FORCING"] for x in row) and a["XLAND"][0][0] in (1.0, 2.0)
    all_pair_failures = {tag: _moment_failures(a[tag]) for tag in (
        "STATE_IN", "STATE_PLUS", "STATE_MINUS", "OUT_BASE", "OUT_PLUS", "OUT_MINUS")}
    moment_admitted = scalar_domain and not any(
        count for failures in all_pair_failures.values() for count in failures.values())
    supported = bool(numerical_pass and moment_admitted)
    accepted = False  # Replay is diagnostic only; it never grants physics approval.
    status = "NUMERICAL_PASS_UNADMITTED_STATE" if numerical_pass and not moment_admitted else (
        "NUMERICAL_PASS_UNAPPROVED" if numerical_pass else "NUMERICAL_CHECK_FAILED"
    )
    return {
        "trace_sha256": trace["trace_sha256"],
        "compressed_sha256": trace["compressed_sha256"],
        "metadata": trace["metadata"],
        "array_shapes": {tag: [len(a[tag]), len(a[tag][0])] for tag in ARRAY_DIMS},
        "numerical_pass": numerical_pass,
        "supported": supported,
        "accepted": accepted,
        "status": status,
        "field_relative_maxnorm_error": {str(k): v["relative_maxnorm_error"] for k, v in computed_fields.items()},
        "field_metrics": computed_fields,
        "worst_field": worst_field,
        "fd_threshold": FD_REL_LIMIT,
        "duality_relative": duality,
        "duality_reduction": "math.fsum of individually rounded binary64 products; not native SUM operation-order replay",
        "duality_threshold": DUALITY_LIMIT,
        "duality_left_jv_squared": left_dot,
        "duality_right_v_jtu": right_dot,
        "moment_admission": {
            "admitted": moment_admitted,
            "input_one_sided_pair_level_counts": input_failures,
            "baseline_output_one_sided_pair_level_counts": output_failures,
            "all_state_pair_level_counts": all_pair_failures,
            "policy": "strict pair-state support only: reject negative moments or exactly one zero for qc/nc, qr/nr, qi/ni, qg/bg at all six input/output states; not full physical DSD approval",
        },
        "physical_moment_admission": False,
        "physical_number_basis_resolved": False,
        "operational_approval": False,
        "accepted_observation_cost": False,
    }


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TRACE
    try:
        result = replay(path)
    except TraceError as exc:
        print(json.dumps({"status": "INVALID_TRACE", "error": str(exc)}, indent=2, allow_nan=False))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0 if result["supported"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
