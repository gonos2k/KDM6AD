#!/usr/bin/env python3
"""Strict C++ A/B/C non-invasiveness gate for the G3.3-M overlays.

A = canonical objects, instrumentation macro absent.
B = diagnostic overlay objects, macro present, every G33 environment variable absent.
C = the SAME diagnostic executable as B, with a harness-sealed dump environment.

For each algorithm (legacy/conservative) and fixture (closure3/species_iso), the
15 returned fields are validated and their complete raw-bit output streams must
be byte-identical A == B == C.  C must additionally produce exactly the sealed
container set.  Numerical diagnostics are derived from evidence rather than
producer verdicts; the current schema supports the rain-family effective CFL
(qr/nr), mstep, metric-floor and surface-sign checks.  It does not claim that
this rain-family CFL is the total main-chain maximum over snow/graupel.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import g33_derived as gdv
import g33_dump as gd
import g33_expectation as ge
import g33_run_env as gre

EXIT_SKIP, EXIT_DRIVER, EXIT_EVIDENCE, EXIT_FIDELITY = 2, 3, 4, 5
QCRMIN, DTCLD = 1.0e-9, 20.0
CASES = {"closure3": (3, 4), "species_iso": (4, 4)}
ALGORITHMS = ("legacy", "conservative")
STATE_FIELDS = ("th", "qv", "qc", "qr", "qi", "qs", "qg",
                "nccn", "nc", "ni", "nr", "bg")
INCREMENT_FIELDS = ("rain_increment", "snow_increment", "graupel_increment")
EXPECTED_FIELDS = STATE_FIELDS + INCREMENT_FIELDS
_HEX = re.compile(r"^[0-9a-f]+$")


def _die(code: int, message: str) -> None:
    print(message, file=sys.stderr, flush=True)
    raise SystemExit(code)


def _schedule(algorithm: str, case_name: str) -> dict:
    B, K = CASES[case_name]
    return {
        "case_id": f"abc-{case_name}",
        "pair_id": f"abc-{algorithm}",
        "backend": "cpp",
        "algorithm": algorithm,
        "B": B,
        "K": K,
        "loops": 1,
        # The fixture uses dt=20 s and ~8 km layers.  This is a declared
        # one-substep schedule, not a producer-reported count: if execution ever
        # needs n=2, the sealed container set makes C fail immediately.
        "mstepmax_main": [1],
        "mstepmax_ice": [1],
        "species_scope": ["qr", "nr"],
        "qcrmin": QCRMIN,
        "dtcld": DTCLD,
        "instrumented_stages": list(ge.CPP_OVERLAY_STAGES),
    }


def _clean_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if not k.startswith("KDM6_G33_")}


def parse_output(raw: bytes, algorithm: str, case_name: str) -> dict:
    """Validate the driver's complete raw-bit protocol; reject empty/truncated data."""
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise gd.G33Corruption(f"ABC output is not ASCII: {exc}") from None
    lines = text.splitlines()
    B, K = CASES[case_name]
    if not lines or lines[0] != f"KDM6ABC 1 {algorithm} {case_name} {B} {K}":
        raise gd.G33Corruption("ABC output has a missing or wrong header")
    if lines[-1:] != ["END"]:
        raise gd.G33Corruption("ABC output has no terminal END marker")
    if len(lines) != len(EXPECTED_FIELDS) + 2:
        raise gd.G33Corruption(
            f"ABC output has {len(lines) - 2} fields, expected {len(EXPECTED_FIELDS)}")

    parsed = {}
    for expected_name, line in zip(EXPECTED_FIELDS, lines[1:-1]):
        tok = line.split()
        if len(tok) < 7 or tok[0] != "FIELD" or tok[1] != expected_name:
            raise gd.G33Corruption(
                f"ABC field order/name mismatch: expected {expected_name!r}, got {line!r}")
        dtype = tok[2]
        if dtype not in ("f32", "f64"):
            raise gd.G33Corruption(f"ABC field {expected_name} has dtype {dtype!r}")
        try:
            ndim = int(tok[3])
        except ValueError:
            raise gd.G33Corruption(f"ABC field {expected_name} has invalid ndim") from None
        shape_start, shape_end = 4, 4 + ndim
        if ndim not in (1, 2) or len(tok) <= shape_end:
            raise gd.G33Corruption(f"ABC field {expected_name} has malformed shape")
        try:
            shape = tuple(int(v) for v in tok[shape_start:shape_end])
            numel = int(tok[shape_end])
        except ValueError:
            raise gd.G33Corruption(f"ABC field {expected_name} has non-integer shape/count") from None
        want_shape = (B, K) if expected_name in STATE_FIELDS else (B,)
        if shape != want_shape or numel != math.prod(shape):
            raise gd.G33Corruption(
                f"ABC field {expected_name} shape/count {(shape, numel)} != {want_shape}")
        words = tok[shape_end + 1:]
        width = 8 if dtype == "f32" else 16
        if len(words) != numel or any(len(w) != width or not _HEX.fullmatch(w) for w in words):
            raise gd.G33Corruption(f"ABC field {expected_name} has malformed raw-bit words")
        bits = [int(w, 16) for w in words]
        if dtype == "f32":
            nonfinite = [i for i, u in enumerate(bits) if ((u >> 23) & 0xff) == 0xff]
        else:
            nonfinite = [i for i, u in enumerate(bits) if ((u >> 52) & 0x7ff) == 0x7ff]
        if nonfinite:
            raise gd.G33Corruption(
                f"ABC field {expected_name} contains non-finite values at {nonfinite[:8]}")
        if expected_name in parsed:
            raise gd.G33Corruption(f"duplicate ABC field {expected_name}")
        parsed[expected_name] = {"dtype": dtype, "shape": shape, "bits": bits}
    return parsed


def _run(driver: Path, algorithm: str, case_name: str, *, env: dict[str, str], cwd: Path) -> bytes:
    cwd.mkdir(parents=True, exist_ok=False)
    result = subprocess.run(
        [str(driver), algorithm, case_name], cwd=cwd, env=env,
        capture_output=True,
    )
    if result.returncode != 0:
        _die(EXIT_DRIVER,
             f"FAIL ABC driver {driver.name} {algorithm}/{case_name} rc={result.returncode}\n"
             f"stdout:\n{result.stdout.decode(errors='replace')}\n"
             f"stderr:\n{result.stderr.decode(errors='replace')}")
    parse_output(result.stdout, algorithm, case_name)
    return result.stdout


def _record(records: list[dict], *, stage: str, field: str,
            op_id: str | None = None, species: str | None = None) -> dict:
    hits = []
    for record in records:
        if record.get("stage") != stage or record.get("field") != field:
            continue
        if op_id is not None and record.get("op_id") != op_id:
            continue
        if species is not None and record.get("species") != species:
            continue
        hits.append(record)
    if len(hits) != 1:
        raise gd.G33Corruption(
            f"{len(hits)} records match stage={stage} field={field} op={op_id} species={species}")
    return hits[0]


def _values(record: dict) -> np.ndarray:
    vals = gdv.unpack_values(record["dtype"], record["payload"])
    return np.asarray(vals)


def _validate_c_evidence(outdir: Path, env: dict[str, str], schedule: dict) -> dict:
    contract_path = outdir / "run_contract.json"
    body = contract_path.read_bytes()
    sealed_sha = env["KDM6_G33_RUN_CONTRACT_SHA256"]
    if hashlib.sha256(body).hexdigest() != sealed_sha:
        raise gd.G33Corruption("C run_contract.json does not match its independent seal")
    try:
        contract = json.loads(body.decode("utf-8"))
        specs = contract["containers"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise gd.G33Corruption(f"malformed C run contract: {exc}") from None

    generated = ge.run_index(schedule)["containers"]
    keys = ("container_id", "outer_loop", "chain", "n", "first_op_seq_id",
            "last_op_seq_id", "record_count", "path")
    if [{k: c[k] for k in keys} for c in specs] != generated:
        raise gd.G33Corruption("C sealed container table differs from independent run_index()")

    dump_dir = Path(env["KDM6_G33_DUMP_DIR"])
    expected_paths = sorted(c["path"] for c in specs)
    actual_paths = sorted(p.name for p in dump_dir.glob("*.g33"))
    if actual_paths != expected_paths:
        raise gd.G33Corruption(
            f"C container set differs\n  actual: {actual_paths}\n  sealed: {expected_paths}")

    containers = {}
    all_records = []
    for spec in specs:
        container = gd.read_container(dump_dir / spec["path"])
        h = container["header"]
        expected_header = {
            "case_id": schedule["case_id"], "pair_id": schedule["pair_id"],
            "backend": "cpp", "algorithm": schedule["algorithm"],
            "B": schedule["B"], "K": schedule["K"],
            "container_id": spec["container_id"],
            "run_contract_sha256": sealed_sha,
            "descriptor_sha256": spec["descriptor_sha256"],
            "binary_sha256": env["KDM6_G33_BINARY_SHA256"],
        }
        for key, want in expected_header.items():
            if h.get(key) != want:
                raise gd.G33Corruption(
                    f"C {spec['container_id']} header {key}={h.get(key)!r}, expected {want!r}")
        containers[spec["container_id"]] = container
        all_records.extend(container["records"])

    observed = {ge.record_key(r) for r in all_records}
    expected = ge.expected_key_set(schedule)
    if observed != expected:
        raise gd.G33Corruption(
            f"C logical record set differs: missing={len(expected-observed)} extra={len(observed-expected)}")
    op_seq = sorted(int(r["op_seq_id"]) for r in all_records)
    if op_seq != list(range(len(all_records))):
        raise gd.G33Corruption("C global op_seq does not tile 0..N-1 exactly")

    # Numerical diagnostics from actual substep evidence.  The current first
    # scope records rain mass/number fall rates, so this is explicitly a
    # rain-family CFL, not the total max that also includes snow/graupel.
    rain_cfl_max = 0.0
    rain_substep_cfl_max = 0.0
    boundary_proxy_min = math.inf
    msteps = []
    floor_count = 0
    cap_bound_count = 0
    for spec in specs:
        if spec["chain"] != "main":
            continue
        records = containers[spec["container_id"]]["records"]
        pre = {name: _record(records, stage="substep_pre", field=name)
               for name in ("work1_qr", "workn_qr", "mstep_input_native",
                            "mstep_native", "mstep_decoded_i32", "mstep_exact_integer",
                            "gate_native", "gate_decoded_u8", "gate_exact_01",
                            "active_mask", "dend_raw", "dend_safe",
                            "dend_floor_active", "delz_raw", "delz_safe",
                            "delz_floor_active", "qcrmin_effective", "dtcld_effective")}
        gdv.check_producer_flags(
            {k: (r["dtype"], r["payload"]) for k, r in pre.items()},
            int(spec["n"]), QCRMIN, DTCLD)
        B, K = schedule["B"], schedule["K"]
        w1 = _values(pre["work1_qr"]).astype(np.float64).reshape(B, K)
        wn = _values(pre["workn_qr"]).astype(np.float64).reshape(B, K)
        mstep = _values(pre["mstep_native"]).astype(np.float64)
        dt = _values(pre["dtcld_effective"]).astype(np.float64)
        cfl = np.maximum(w1, wn).max(axis=1) * dt
        sub_cfl = cfl / mstep
        if (sub_cfl < 0).any() or not np.isfinite(sub_cfl).all() or (sub_cfl > 1.0 + 1e-12).any():
            raise gd.G33Corruption(
                f"rain-family effective CFL invalid in {spec['container_id']}: {sub_cfl.tolist()}")
        rain_cfl_max = max(rain_cfl_max, float(cfl.max(initial=0.0)))
        rain_substep_cfl_max = max(rain_substep_cfl_max, float(sub_cfl.max(initial=0.0)))
        boundary_proxy_min = min(
            boundary_proxy_min,
            float(np.abs((cfl + 1.0) - np.rint(cfl + 1.0)).min(initial=math.inf)))
        msteps.extend(int(v) for v in mstep)
        floor_count += int(_values(pre["dend_floor_active"]).sum())
        floor_count += int(_values(pre["delz_floor_active"]).sum())

        for species, op_id in (("qr", "QR_OUTFLOW"), ("nr", "NR_OUTFLOW")):
            pre_cap = [r for r in records if r.get("stage") == "op"
                       and r.get("species") == species and r.get("op_id") == op_id
                       and r.get("field") == "outflow_pre_cap"]
            reservoir = [r for r in records if r.get("stage") == "op"
                         and r.get("species") == species and r.get("op_id") == op_id
                         and r.get("field") == "source_reservoir"]
            if len(pre_cap) != len(reservoir):
                raise gd.G33Corruption(f"{op_id} cap operands have different record counts")
            for left, right in zip(pre_cap, reservoir):
                a, b = _values(left), _values(right)
                if a.shape != b.shape:
                    raise gd.G33Corruption(f"{op_id} cap operands have different shapes")
                cap_bound_count += int(np.count_nonzero(a > b))

    if not msteps or min(msteps) < 1 or max(msteps) > 100:
        raise gd.G33Corruption(f"invalid or missing mstep diagnostics: {msteps}")
    if any(v == 100 for v in msteps):
        raise gd.G33Corruption("A/B/C synthetic fixture reached the mstep=100 saturation cap")
    if floor_count:
        raise gd.G33Corruption(f"A/B/C valid-metric fixture activated {floor_count} metric floors")

    surface_specs = [s for s in specs if s["container_id"].endswith("_surface")]
    if len(surface_specs) != 1:
        raise gd.G33Corruption("C run has no unique surface container")
    surface_records = containers[surface_specs[0]["container_id"]]["records"]
    surface_negative = 0
    for name in ("bottom_fall_qr", "bottom_fall_qs", "bottom_fall_qg", "bottom_fall_qi"):
        vals = _values(_record(surface_records, stage="surface", field=name))
        if not np.isfinite(vals).all():
            raise gd.G33Corruption(f"surface {name} is non-finite")
        surface_negative += int(np.count_nonzero(vals < 0))
    if surface_negative:
        raise gd.G33Corruption(
            f"surface clamp would hide {surface_negative} negative bottom-fall values")

    return {
        "containers": len(specs),
        "rain_cfl_max": rain_cfl_max,
        "rain_substep_cfl_max": rain_substep_cfl_max,
        "boundary_proxy_min": boundary_proxy_min,
        "mstep_min": min(msteps), "mstep_max": max(msteps),
        "floor_count": floor_count, "cap_bound_count": cap_bound_count,
    }


def _first_diff(a: bytes, b: bytes) -> str:
    aa, bb = a.splitlines(), b.splitlines()
    for i, (x, y) in enumerate(zip(aa, bb), 1):
        if x != y:
            return f"line {i}\n  A: {x[:160]!r}\n  B: {y[:160]!r}"
    return f"different line counts {len(aa)} vs {len(bb)}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical-driver", type=Path, required=True)
    parser.add_argument("--diagnostic-driver", type=Path, required=True)
    args = parser.parse_args()
    for path in (args.canonical_driver, args.diagnostic_driver):
        if not path.is_file():
            _die(EXIT_SKIP, f"SKIP: ABC driver not found: {path}")
        path.resolve()

    root = Path(tempfile.mkdtemp(prefix="g33-abc-"))
    try:
        clean = _clean_env()
        for algorithm in ALGORITHMS:
            for case_name in CASES:
                label = f"{algorithm}-{case_name}"
                out_a = _run(args.canonical_driver.resolve(), algorithm, case_name,
                             env=clean, cwd=root / f"{label}-A")
                out_b = _run(args.diagnostic_driver.resolve(), algorithm, case_name,
                             env=clean, cwd=root / f"{label}-B")
                leaked = list((root / f"{label}-B").rglob("*.g33"))
                leaked += list((root / f"{label}-B").rglob("*.tmp"))
                if leaked:
                    _die(EXIT_EVIDENCE, f"B env-off run emitted evidence: {leaked}")

                schedule = _schedule(algorithm, case_name)
                evidence = root / f"{label}-C-evidence"
                env_c = gre.build_env(
                    schedule, evidence, binary=args.diagnostic_driver.resolve(),
                    column_map=[[i, 0, i, i] for i in range(schedule["B"])],
                    run_uuid=f"abc-{algorithm}-{case_name}-{uuid.uuid4().hex[:10]}",
                    column_layout_id=f"abc-{case_name}-{schedule['B']}col")
                out_c = _run(args.diagnostic_driver.resolve(), algorithm, case_name,
                             env={**clean, **env_c}, cwd=root / f"{label}-C")

                if out_a != out_b:
                    _die(EXIT_FIDELITY, f"FAIL A!=B {label}: {_first_diff(out_a, out_b)}")
                if out_a != out_c:
                    _die(EXIT_FIDELITY, f"FAIL A!=C {label}: {_first_diff(out_a, out_c)}")
                diag = _validate_c_evidence(evidence, env_c, schedule)
                digest = hashlib.sha256(out_a).hexdigest()[:16]
                print(
                    f"ABC PASS {algorithm}/{case_name} sha={digest} "
                    f"containers={diag['containers']} mstep={diag['mstep_min']}..{diag['mstep_max']} "
                    f"rain_Cmax={diag['rain_cfl_max']:.6g} "
                    f"rain_Csub={diag['rain_substep_cfl_max']:.6g} "
                    f"rain_boundary_proxy={diag['boundary_proxy_min']:.6g} "
                    f"floors={diag['floor_count']} cap_bound={diag['cap_bound_count']}")
        print("C++ A/B/C NON-INVASIVENESS PASS — 4 algorithm/case pairs, strict raw-bit")
    except gd.G33Corruption as exc:
        _die(EXIT_EVIDENCE, f"FAIL ABC evidence: {exc}")
    except BaseException:
        print(f"(ABC evidence preserved at {root})", file=sys.stderr)
        raise
    else:
        shutil.rmtree(root)


if __name__ == "__main__":
    main()
