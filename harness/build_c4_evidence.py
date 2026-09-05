#!/usr/bin/env python3
"""C4 Gate A evidence manifest builder (conservative-interface-v1).

Collects, into artifacts/c4/evidence_manifest.json:
  - public repo commit (+dirty flag) and the pinned base 48d8c32
  - sha256 of the four host Fortran sources (2 legacy never-modify + 2 new),
    kdm6_iso_c.F, and the installed libkdm6_c binary (symlink resolved)
  - scheme IDs and the ID→backend map
  - toolchain versions (gfortran/mpif90/clang/torch/OS)
  - the Gate A scope-check report (run in-process)
  - fixture provenance (Gate B driver + C3 fixture source hashes)
  - optional Gate B / Gate D result logs (paths passed in, content embedded)

The private host tree is NOT a git repo (gitignored inside the public repo),
so "host commit" is recorded as the file-sha pin set itself.

Owner-run tool: requires the private host tree. The public PR carries the
manifest OUTPUT, never the host sources.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")


def schema_digest(variables: dict) -> str:
    """Digest the declared variable contract, excluding its own seal.

    A schema is an explicit campaign input, not a count guessed from whatever
    variables happen to be present.  Descriptors use the normalized dtype
    string, ordered dimensions, and optional dimension sizes (``None`` means
    that the size is campaign-dependent, normally ``Time``).
    """
    import numpy as np
    normalized = {}
    for name, desc in sorted(variables.items()):
        if not isinstance(name, str) or not isinstance(desc, dict):
            raise ValueError("schema variables must map names to descriptors")
        dims = desc.get("dimensions")
        if not isinstance(dims, list) or not all(isinstance(d, str) for d in dims):
            raise ValueError(f"schema variable {name!r} has invalid dimensions")
        try:
            dtype = np.dtype(desc["dtype"]).str
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"schema variable {name!r} has invalid dtype") from exc
        item = {"dimensions": dims, "dtype": dtype}
        if "shape" in desc:
            shape = desc["shape"]
            if not isinstance(shape, list) or len(shape) != len(dims):
                raise ValueError(f"schema variable {name!r} has invalid shape")
            if not all(x is None or x == "*" or isinstance(x, int) for x in shape):
                raise ValueError(f"schema variable {name!r} has invalid shape entries")
            item["shape"] = shape
        normalized[name] = item
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_expected_schema(spec) -> dict:
    """Load a sealed expected schema supplied by the C4 campaign.

    The manifest must carry ``schema_id``, ``schema_sha256`` and a ``variables``
    mapping.  The digest is over the normalized mapping returned by
    :func:`schema_digest`; accepting an unsealed list would recreate the
    arbitrary-minimum-count gap this gate is intended to close.
    """
    if spec is None:
        return None
    source = str(spec) if isinstance(spec, (str, Path)) else "inline"
    if isinstance(spec, (str, Path)):
        path = Path(spec)
        try:
            raw = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"cannot read expected C4 schema {path}: {exc}") from exc
    else:
        raw = spec
    if not isinstance(raw, dict):
        raise SystemExit("expected C4 schema must be a JSON object")
    schema_id = raw.get("schema_id")
    supplied = raw.get("schema_sha256")
    variables = raw.get("variables")
    if not isinstance(schema_id, str) or not schema_id.strip():
        raise SystemExit("expected C4 schema lacks a non-empty schema_id")
    if not isinstance(supplied, str) or not _HEX64.fullmatch(supplied):
        raise SystemExit("expected C4 schema lacks a valid schema_sha256 seal")
    if not isinstance(variables, dict) or not variables:
        raise SystemExit("expected C4 schema lacks a non-empty variables mapping")
    campaign_id = raw.get("campaign_id")
    if campaign_id is not None and (
            not isinstance(campaign_id, str) or not _HEX64.fullmatch(campaign_id)):
        raise SystemExit("expected C4 schema has an invalid campaign_id")
    try:
        digest = schema_digest(variables)
    except ValueError as exc:
        raise SystemExit(f"invalid expected C4 schema: {exc}") from exc
    if digest.lower() != supplied.lower():
        raise SystemExit("expected C4 schema digest does not match its variables")
    if "Times" not in variables:
        raise SystemExit("expected C4 schema must declare Times explicitly")
    return {"schema_id": schema_id, "schema_sha256": supplied.lower(),
            "variables": variables, "source": source,
            "campaign_id": campaign_id.lower() if isinstance(campaign_id, str) else None}


def _schema_matches(a, b, expected: dict) -> tuple[bool, list[str]]:
    """Check exact variable/dimension/dtype schema against a sealed contract."""
    import numpy as np
    expected_vars = expected["variables"]
    actual_a = set(a.variables)
    actual_b = set(b.variables)
    errors = []
    if actual_a != set(expected_vars):
        errors.append(f"mp37 variable set differs from expected: missing={sorted(set(expected_vars)-actual_a)} extra={sorted(actual_a-set(expected_vars))}")
    if actual_b != set(expected_vars):
        errors.append(f"mp137 variable set differs from expected: missing={sorted(set(expected_vars)-actual_b)} extra={sorted(actual_b-set(expected_vars))}")
    for side, ds in (("mp37", a), ("mp137", b)):
        for name, desc in expected_vars.items():
            if name not in ds.variables:
                continue
            var = ds.variables[name]
            try:
                want_dtype = np.dtype(desc["dtype"]).str
            except (TypeError, ValueError):
                continue
            if tuple(var.dimensions) != tuple(desc["dimensions"]):
                errors.append(f"{side}:{name} dimensions {var.dimensions} != expected {tuple(desc['dimensions'])}")
            if var.dtype.str != want_dtype:
                errors.append(f"{side}:{name} dtype {var.dtype.str} != expected {want_dtype}")
            if "shape" in desc:
                for dim, got, want in zip(var.dimensions, var.shape, desc["shape"]):
                    if want is not None and want != "*" and got != want:
                        errors.append(f"{side}:{name} dimension {dim} size {got} != expected {want}")
    times = expected_vars.get("Times", {})
    if "Time" not in times.get("dimensions", []):
        errors.append("expected C4 Times descriptor must include Time dimension")
    return not errors, errors


def _producer_campaign_id(controls: dict) -> str:
    """Use the producer's campaign-id function, including its exact payload."""
    try:
        from run_ss_case import campaign_id_from_controls
    except (ImportError, ModuleNotFoundError):
        # ``build_c4_evidence.py`` is also loaded by focused tests via an
        # importlib path, where the harness directory is not on sys.path.
        import importlib.util
        path = Path(__file__).with_name("run_ss_case.py")
        spec = importlib.util.spec_from_file_location("run_ss_case", path)
        if spec is None or spec.loader is None:
            raise SystemExit("cannot load campaign identity producer")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        campaign_id_from_controls = module.campaign_id_from_controls
    try:
        return campaign_id_from_controls(controls)
    except (TypeError, ValueError, KeyError) as exc:
        raise SystemExit(f"run_identity controls cannot produce campaign_id: {exc}") from exc


def _pair_identity(rundir: Path, *, require_status: bool = False) -> dict:
    """Read and internally validate the producer's stable pair identity."""
    path = Path(rundir) / "run_identity.json"
    if not path.is_file():
        raise SystemExit(f"{rundir}: C4 pair identity is missing (run_identity.json)")
    try:
        record = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"{rundir}: invalid run_identity.json: {exc}") from exc
    if not isinstance(record, dict):
        raise SystemExit(f"{rundir}: run_identity.json is not an object")
    campaign_id = record.get("campaign_id")
    if not isinstance(campaign_id, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", campaign_id):
        raise SystemExit(f"{rundir}: run_identity.json lacks a valid campaign_id")
    controls = record.get("controls")
    if not isinstance(controls, dict):
        raise SystemExit(f"{rundir}: run_identity.json lacks producer controls")
    expected_campaign = _producer_campaign_id(controls)
    if campaign_id.lower() != expected_campaign.lower():
        raise SystemExit(
            f"{rundir}: campaign_id does not match producer campaign_id_from_controls")
    if record.get("experiment_valid") is not True:
        raise SystemExit(f"{rundir}: C4 pair identity is not an experiment-valid run")
    if record.get("exit_code") != 0:
        raise SystemExit(f"{rundir}: C4 pair identity has nonzero exit_code")
    status_path = Path(rundir) / "experiment_valid.json"
    if not status_path.is_file():
        if require_status:
            raise SystemExit(
                f"{rundir}: C4 pair identity lacks producer experiment_valid.json")
        return record
    if require_status:
        # Reuse the producer-status consumer used by the MPI attribution tool,
        # including its executable before/after/final consistency checks.  C4
        # must not pair a run identity with a sibling status that is only
        # superficially valid.
        try:
            import g33_mpi_divergence as mpi_identity
        except (ImportError, ModuleNotFoundError):
            import importlib.util
            mpi_path = Path(__file__).with_name("g33_mpi_divergence.py")
            mpi_spec = importlib.util.spec_from_file_location(
                "g33_mpi_divergence", mpi_path)
            if mpi_spec is None or mpi_spec.loader is None:
                raise SystemExit("cannot load producer-status consumer")
            mpi_identity = importlib.util.module_from_spec(mpi_spec)
            mpi_spec.loader.exec_module(mpi_identity)
        mpi_identity._validate_producer_status(Path(rundir))
    try:
        status = json.loads(status_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"{rundir}: invalid experiment_valid.json: {exc}") from exc
    if not isinstance(status, dict):
        raise SystemExit(f"{rundir}: experiment_valid.json is not an object")
    if status.get("experiment_valid") is not record.get("experiment_valid"):
        raise SystemExit(
            f"{rundir}: run_identity experiment_valid disagrees with producer status")
    if status.get("exit_code") != record.get("exit_code"):
        raise SystemExit(
            f"{rundir}: run_identity exit_code disagrees with producer status")
    if status.get("experiment_valid") is True:
        if status.get("model_completed") is not True:
            raise SystemExit(
                f"{rundir}: producer status marks a valid run without model_completed=true")
        reasons = status.get("invalid_reasons")
        if not isinstance(reasons, list) or reasons:
            raise SystemExit(
                f"{rundir}: producer status has invalid_reasons={reasons!r} for a valid run")
    for key in ("requested_proc_grid", "actual_proc_grid"):
        if key in status and status.get(key) != record.get(key):
            raise SystemExit(
                f"{rundir}: run_identity {key} disagrees with producer status")
    return record


def _schema_binding(expected: dict | None, identities: tuple[dict, dict],
                    campaign_id: str) -> None:
    """Bind optional producer schema metadata to the requested caller schema.

    The variable-map digest is an integrity check over that map.  It does not
    authenticate the caller's claim that the map describes this campaign.  If
    a producer emits schema metadata, this consumer cross-checks it; otherwise
    the explicitly supplied expected schema remains the caller-owned contract.
    """
    if expected is None:
        return
    declared_campaign = expected.get("campaign_id")
    if declared_campaign is not None and declared_campaign != campaign_id.lower():
        raise SystemExit(
            "expected C4 schema campaign_id does not match the paired run campaign")
    for label, identity in zip(("A", "B"), identities):
        nested = identity.get("expected_schema")
        if not isinstance(nested, dict) and isinstance(identity.get("schema"), dict):
            nested = identity.get("schema")
        nested = nested if isinstance(nested, dict) else {}
        schema_id = nested.get("schema_id", identity.get("expected_schema_id",
                                                            identity.get("schema_id")))
        schema_sha = nested.get("schema_sha256", identity.get(
            "expected_schema_sha256", identity.get("schema_sha256")))
        if schema_id is None and schema_sha is None:
            continue
        if (not isinstance(schema_id, str) or schema_id != expected["schema_id"]
                or not isinstance(schema_sha, str)
                or not _HEX64.fullmatch(schema_sha)
                or schema_sha.lower() != expected["schema_sha256"]):
            raise SystemExit(
                f"producer {label} schema identity does not match the requested C4 schema")


def _require_pair_identity(run_a: Path, run_b: Path, *,
                           expected_schemes: tuple[str, str] | None = None,
                           expected_schema: dict | None = None,
                           require_status: bool = False) -> dict:
    ia, ib = (_pair_identity(run_a, require_status=require_status),
              _pair_identity(run_b, require_status=require_status))
    if ia["campaign_id"].lower() != ib["campaign_id"].lower():
        raise SystemExit("C4 runs have different campaign_id values; refusing to pair unrelated runs")
    if ia.get("controls") != ib.get("controls"):
        raise SystemExit("C4 runs have contradictory campaign controls")
    # The identity is shared, while each side records its own arm.  A producer
    # that omits the role leaves the pair unverifiable; writing the same role
    # twice is not a two-arm parity pair.
    role_a, role_b = ia.get("scheme"), ib.get("scheme")
    if not isinstance(role_a, str) or not isinstance(role_b, str):
        raise SystemExit("C4 pair identity must declare a scheme role for both runs")
    if role_a == role_b:
        raise SystemExit(f"C4 pair has the same scheme role ({role_a!r}) on both runs")
    if expected_schemes is not None and {role_a, role_b} != set(expected_schemes):
        raise SystemExit(
            f"C4 pair must contain intended scheme arms {expected_schemes}, "
            f"got {(role_a, role_b)}")
    _schema_binding(expected_schema, (ia, ib), ia["campaign_id"])
    return {"campaign_id": ia["campaign_id"].lower(),
            "a": {"scheme": role_a}, "b": {"scheme": role_b}}


def cmd_out(args: list[str]) -> str:
    try:
        lines = subprocess.run(args, capture_output=True, text=True,
                               timeout=60).stdout.strip().splitlines()
        return lines[0] if lines else "UNAVAILABLE (no output)"
    except Exception as e:  # toolchain probe only — record the failure, don't die
        return f"UNAVAILABLE ({e})"


FATAL_RE = re.compile(
    r"MPI_ABORT|SIGSEGV|forrtl: severe|Fatal error in|NaN (BEFORE|after)")


def verify_recert_run(rundir: Path, np: int = 4) -> dict:
    """Fail-closed per-run verification of one 12h recert run (mirrors the
    host verify_run.sh contract): exit_code==0, SUCCESS COMPLETE WRF in every
    rank log (==np), no fatal/NaN marker. The SUCCESS COMPLETE WRF marker is
    the FULL-DURATION completeness proof — WRF prints it only after the entire
    integration finishes — so it is stronger than any frame count. (This case's
    --history 60 + base history_interval_s=20 emit 12 hourly frames drifting
    +20s/frame: 00:00:00 … 11:03:40; the 13th frame at ~12:04:00 falls past the
    12:00:00 run end, so 12 frames is the COMPLETE output, not truncation —
    verified against the `_12:00:00 wrf: SUCCESS COMPLETE WRF` marker.)
    The recert contract declares one forecast history stream per run; rollover or
    additional history files make the run incomplete until they are explicitly
    handled by a separate multi-file contract. Returns a dict with every checked
    fact and a single `verified` bool."""
    r: dict = {"rundir": str(rundir), "exists": rundir.is_dir(),
               "output_contract": "exactly one forecast history file"}
    if not r["exists"]:
        r["verified"] = False
        return r
    ec = (rundir / "exit_code").read_text().strip() if (rundir / "exit_code").exists() else None
    r["exit_code"] = ec
    # Validate rank IDENTITIES, not just the count: the run dir must contain
    # EXACTLY the rsl.error.0000 … {np-1} logs — no missing rank (a rank that
    # crashed without writing) and no stray extra (a stale log from a different
    # np decomposition would let a bare count slip through). The precise
    # 4-digit glob excludes backup/temp files (rsl.error.0000.bak/.tmp) that a
    # bare `rsl.error.*` would sweep in. Each rank log is read exactly once.
    rank_texts = {p.name: p.read_text(errors="replace")
                  for p in rundir.glob("rsl.error.[0-9][0-9][0-9][0-9]")}
    found_ranks = set(rank_texts)
    required_ranks = {f"rsl.error.{i:04d}" for i in range(np)}
    r["rank_logs"] = sorted(found_ranks)
    r["rank_ids_ok"] = (found_ranks == required_ranks)
    r["missing_ranks"] = sorted(required_ranks - found_ranks)
    r["extra_rank_logs"] = sorted(found_ranks - required_ranks)
    n_success = sum(1 for name in required_ranks
                    if "SUCCESS COMPLETE WRF" in rank_texts.get(name, ""))
    r["success_ranks"] = n_success
    # full-duration proof: the master rank (0000) reached SUCCESS at run end.
    # Require the 12:00:00 marker (this is the 12h recert) AND capture the sim
    # end time so the caller can test whether the LAST history frame actually
    # reaches it (the history cadence may stop short of the terminal state).
    r["reached_full_duration"] = bool(re.search(
        r"_12:00:00 wrf: SUCCESS COMPLETE WRF", rank_texts.get("rsl.error.0000", "")))
    m_end = re.search(r"_(\d\d:\d\d:\d\d) wrf: SUCCESS COMPLETE WRF",
                      rank_texts.get("rsl.error.0000", ""))
    r["run_end_time"] = m_end.group(1) if m_end else None
    fatal = sum(1 for t in rank_texts.values() if FATAL_RE.search(t))
    for p in sorted(rundir.glob("*.stdout")):
        if FATAL_RE.search(p.read_text(errors="replace")):
            fatal += 1
    r["fatal_markers"] = fatal
    # A run directory is a single declared history stream.  The old `or [0]`
    # selection silently ignored rollover/additional outputs, so a divergent
    # second file could sit beside a verified first file.  Refuse the whole run
    # unless exactly one supported output exists.
    # Keep malformed candidates in the manifest so an output directory or
    # special path cannot masquerade as a history file.  Open/hash only a
    # regular file after the exact-one contract has passed.
    fcst = sorted(rundir.glob("klfs_lc05_fcst.*")) + sorted(rundir.glob("wrfout_d01_*"))
    r["forecast_files"] = [str(p) for p in fcst]
    r["output_files_ok"] = len(fcst) == 1 and fcst[0].is_file()
    if len(fcst) == 1 and fcst[0].is_file():
        fcst_path = fcst[0]
        try:
            import netCDF4 as nc
            with nc.Dataset(str(fcst_path)) as d:
                r["frames"] = d.dimensions["Time"].size if "Time" in d.dimensions else 1
        except Exception as exc:
            r["frames"] = 0
            r["output_files_ok"] = False
            r["fcst"] = None
            r["forecast_sha256"] = None
            r["output_error"] = f"forecast history is not readable NetCDF: {exc}"
        else:
            r["fcst"] = str(fcst_path)
            r["forecast_sha256"] = hashlib.sha256(fcst_path.read_bytes()).hexdigest()
    else:
        r["frames"] = 0
        r["fcst"] = None
        r["forecast_sha256"] = None
        if fcst:
            if len(fcst) == 1 and not fcst[0].is_file():
                r["output_error"] = (
                    "forecast candidate is not a regular file: "
                    f"{fcst[0].name}")
            else:
                r["output_error"] = (
                    "expected exactly one forecast history file, found "
                    f"{len(fcst)}: {[p.name for p in fcst]}")
    r["verified"] = (ec == "0" and r["rank_ids_ok"] and n_success == np
                     and fatal == 0 and r["reached_full_duration"]
                     and r["output_files_ok"]
                     and r["frames"] >= 1)
    return r


def strict_bitwise_all_frames(f37: str, f137: str,
                              min_common_numeric: int | None = None,
                              expected_schema=None) -> dict:
    """Raw-bit (uint-view) comparison across EVERY common frame.
    FAIL-CLOSED — strict_bitwise is True ONLY if:
      * the variable SETS are identical (no only_a / only_b),
      * the frame counts are identical (na == nb, same cadence),
      * either a sealed expected_schema matches exactly, or the number of common
        NUMERIC variables meets min_common_numeric — a malformed/degenerate file
        pair with a tiny common set must never pass,
      * and for EVERY frame, every one of those numeric variables was actually
        compared and matched (n_match == numeric_common AND n_diff == 0). A
        frame where variables were only skipped (nothing compared) fails."""
    import numpy as np
    import netCDF4 as nc
    expected = _load_expected_schema(expected_schema)
    if min_common_numeric is None:
        # A sealed schema defines the requested population.  The historical
        # fallback remains available to direct generic callers, but it is never
        # used as the C4 campaign contract.
        if expected is not None:
            min_common_numeric = 0
            for descriptor in expected["variables"].values():
                try:
                    if np.dtype(descriptor["dtype"]).kind in ("f", "i", "u"):
                        min_common_numeric += 1
                except (KeyError, TypeError, ValueError):
                    pass
        else:
            min_common_numeric = 250
    a = nc.Dataset(f37); b = nc.Dataset(f137)
    a.set_auto_maskandscale(False); b.set_auto_maskandscale(False)
    na = a.dimensions["Time"].size if "Time" in a.dimensions else 1
    nb = b.dimensions["Time"].size if "Time" in b.dimensions else 1
    nframes = min(na, nb)
    common = sorted(set(a.variables) & set(b.variables))
    only_a = sorted(set(a.variables) - set(b.variables))
    only_b = sorted(set(b.variables) - set(a.variables))
    numeric_common = [v for v in common
                      if a.variables[v].dtype.kind in ("f", "i", "u")]
    ncnum = len(numeric_common)
    # 'Times' (and any char var) is EXACT-equality checked, not skipped: two
    # files with identical numeric arrays but different timestamps must NOT be
    # certified identical. char_diff feeds both `times_equal` and `strict_bitwise`.
    char_common = [v for v in common if a.variables[v].dtype.kind in ("S", "U")]
    per_frame = []
    times_equal = True
    last_time = None
    empty_numeric = {
        v for v in numeric_common
        if any(size == 0 for size in a.variables[v].shape)
        or any(size == 0 for size in b.variables[v].shape)
    }
    schema_ok, schema_errors = (True, [])
    if expected is not None:
        schema_ok, schema_errors = _schema_matches(a, b, expected)
    all_ok = ((not only_a) and (not only_b) and (na == nb) and nframes >= 1
              and ncnum >= min_common_numeric and schema_ok)
    itype = {1: np.uint8, 2: np.uint16, 4: np.uint32, 8: np.uint64}

    def frame_value(var, frame):
        if "Time" not in var.dimensions:
            return np.asarray(var[:])
        axis = var.dimensions.index("Time")
        index = [slice(None)] * var.ndim
        index[axis] = frame
        return np.asarray(var[tuple(index)])

    for fr in range(nframes):
        n_match = n_diff = n_skip = char_diff = 0
        for v in char_common:
            va, vb = a.variables[v], b.variables[v]
            # NetCDF dimension names/order are part of cell identity.  Equal
            # shaped arrays with ('Time','x','y') vs ('Time','y','x') must not
            # be called equal merely because their raw bytes happen to match.
            if (va.dimensions != vb.dimensions or va.shape != vb.shape
                    or va.dtype != vb.dtype):
                char_diff += 1
                continue
            ca = frame_value(va, fr)
            cb = frame_value(vb, fr)
            if ca.shape != cb.shape or ca.tobytes() != cb.tobytes():
                char_diff += 1
        if "Times" in char_common:
            last_time = frame_value(a.variables["Times"], fr).tobytes().decode(
                errors="replace").strip("\x00 ")
        for v in common:
            va, vb = a.variables[v], b.variables[v]
            if va.dtype.kind not in ("f", "i", "u"):
                n_skip += 1; continue
            if (va.dimensions != vb.dimensions or va.shape != vb.shape
                    or va.dtype != vb.dtype):
                n_diff += 1
                continue
            xa = frame_value(va, fr)
            xb = frame_value(vb, fr)
            if xa.shape != xb.shape or xa.dtype != xb.dtype:
                n_diff += 1; continue
            if xa.size == 0 or xb.size == 0:
                empty_numeric.add(v)
                continue
            # .view() needs a contiguous buffer; NetCDF slices may not be.
            ua = np.ascontiguousarray(xa).view(itype[xa.dtype.itemsize])
            ub = np.ascontiguousarray(xb).view(itype[xb.dtype.itemsize])
            if int(np.count_nonzero(ua != ub)) == 0:
                n_match += 1
            else:
                n_diff += 1
        per_frame.append({"frame": fr, "match": n_match, "diff": n_diff,
                          "skip": n_skip, "numeric": ncnum, "char_diff": char_diff})
        if char_diff:
            times_equal = False
        # a frame is clean ONLY if every numeric common var was compared and
        # matched AND every char var (Times) is byte-exact — never on an
        # empty/all-skipped comparison.
        if not (n_diff == 0 and n_match == ncnum and n_match > 0 and char_diff == 0):
            all_ok = False
    result = {"frames_compared": nframes, "common_variables": len(common),
            "common_numeric_variables": ncnum,
            "common_char_variables": len(char_common),
            "min_common_numeric_required": min_common_numeric,
            "only_in_mp37": only_a, "only_in_mp137": only_b,
            "empty_numeric_variables": sorted(empty_numeric),
            "insufficient": bool(empty_numeric or ncnum == 0 or nframes < 1),
            "times_equal": times_equal, "last_compared_time": last_time,
            "per_frame": per_frame, "strict_bitwise": all_ok,
            "schema_provenance": ({"required": True,
                                    "schema_id": expected["schema_id"],
                                    "schema_sha256": expected["schema_sha256"],
                                    "campaign_id": expected.get("campaign_id"),
                                    "source": expected["source"],
                                    "matches": schema_ok,
                                    "errors": schema_errors}
                                   if expected is not None else
                                   {"required": False,
                                    "mode": "minimum_common_numeric"})}
    a.close(); b.close()
    return result


def legacy_12h_block(runs_dir: Path, expected_schema=None) -> dict:
    """Assemble the fail-closed legacy 12h x np4 recertification block from the
    latest mp37/mp137 recert run dirs. strict_bitwise is recorded True ONLY
    when both runs verify, share a pair identity, and every requested schema
    field in every common frame is raw-bit equal. The frame
    count is cadence-derived, not hardcoded: this case's --history 60 + base
    history_interval_s=20 emits 12 hourly frames drifting +20s/frame
    (00:00:00 … 11:03:40); the 13th at ~12:04:00 falls past the 12:00:00 end,
    so 12 IS the complete count. Completeness is proven by the per-run
    `_12:00:00 wrf: SUCCESS COMPLETE WRF` marker, never by a frame threshold."""
    def latest(glob):
        cands = sorted(runs_dir.glob(glob))
        return cands[-1] if cands else None
    if expected_schema is None:
        for candidate in (runs_dir / "expected_schema.json",
                          runs_dir / "c4_expected_schema.json"):
            if candidate.is_file():
                expected_schema = candidate
                break
    d37 = latest("mp37_recert12h_*")
    d137 = latest("mp137_recert12h_*")
    block: dict = {
        "mp37_run": str(d37) if d37 else None,
        "mp137_run": str(d137) if d137 else None,
        "mp37": verify_recert_run(d37) if d37 else {"verified": False, "note": "no mp37 recert run"},
        "mp137": verify_recert_run(d137) if d137 else {"verified": False, "note": "no mp137 recert run"},
    }
    both_verified = bool(block["mp37"].get("verified")
                         and block["mp137"].get("verified"))
    if both_verified:
        expected = _load_expected_schema(expected_schema) if expected_schema is not None else None
        try:
            pair = _require_pair_identity(
                d37, d137, expected_schemes=("37", "137"),
                expected_schema=expected, require_status=True)
        except SystemExit as exc:
            block["comparison"] = None
            block["strict_bitwise"] = False
            block["note"] = str(exc)
            return block
        block["pair_identity"] = pair
        if expected_schema is None:
            block["comparison"] = None
            block["strict_bitwise"] = False
            block["note"] = ("C4 comparison requires a sealed expected schema "
                              "bound to the requested campaign; a minimum numeric "
                              "count is not an output-schema contract")
            return block
        cmp = strict_bitwise_all_frames(
            block["mp37"]["fcst"], block["mp137"]["fcst"],
            expected_schema=expected)
        block["comparison"] = cmp
        block["strict_bitwise"] = bool(cmp["strict_bitwise"])
        # Terminal-state coverage is NOT implied by run completion: the history
        # cadence can stop short of the sim end. Record, honestly, whether the
        # LAST compared history frame actually reaches the run-end time. Here it
        # does not (last frame 11:03:40 vs run end 12:00:00), so the certified
        # claim is "all GENERATED history frames are bitwise", NOT "terminal
        # 12:00:00 state is bitwise". Closing that gap needs a 12:00 history/
        # restart frame (a separate follow-up), not this run's history.
        run_end = block["mp37"].get("run_end_time")
        last_t = cmp.get("last_compared_time")
        block["terminal_state"] = {
            "run_end_time": run_end,
            "last_compared_time": last_t,
            "times_equal_all_frames": bool(cmp.get("times_equal")),
            "terminal_time_compared": bool(run_end and last_t
                                           and last_t.endswith(run_end)),
            "coverage_note": (
                "history cadence emits no frame AT the run-end time; the last "
                "comparable state precedes it, so terminal-state parity is NOT "
                "asserted by this recert — only run completion + all-generated-"
                "frame bitwise parity are"),
        }
    else:
        block["comparison"] = None
        block["strict_bitwise"] = False
        block["note"] = ("recertification INCOMPLETE — both runs must verify "
                         "(exit_code=0, exactly np rank logs all with SUCCESS "
                         "COMPLETE WRF, reached 12:00:00, 0 fatal/NaN) before a "
                         "bitwise verdict is recorded")
    return block


def terminal_parity_block(runs_dir: Path, expected_schema=None) -> dict:
    """Assemble the fail-closed TERMINAL-STATE parity block from the latest
    mp37/mp137 *_termparity_* run dirs (12 h x np4, history_interval_s=0 => exact
    hourly frames 00:00:00 … 12:00:00). Unlike the recert (whose last frame is
    11:03:40), this REQUIRES the last compared frame to be exactly 12:00:00 —
    closing the terminal-coverage gap. PASS iff both runs verify AND every frame
    (incl. the 12:00:00 terminal) is raw-bit + Times exact."""
    def latest(glob):
        cands = sorted(runs_dir.glob(glob))
        return cands[-1] if cands else None
    d37 = latest("mp37_termparity_*")
    d137 = latest("mp137_termparity_*")
    if not (d37 and d137):
        return {"terminal_run_present": False, "terminal_parity": False,
                "note": "no terminal-parity run yet (run_terminal_parity.sh); "
                        "the 12h recert proves all-generated-frame parity only, "
                        "NOT terminal 12:00:00-state parity"}
    block: dict = {
        "terminal_run_present": True,
        "mp37_run": str(d37), "mp137_run": str(d137),
        "mp37": verify_recert_run(d37), "mp137": verify_recert_run(d137),
    }
    both_verified = bool(block["mp37"].get("verified")
                         and block["mp137"].get("verified"))
    if both_verified:
        expected = _load_expected_schema(expected_schema) if expected_schema is not None else None
        try:
            pair = _require_pair_identity(
                d37, d137, expected_schemes=("37", "137"),
                expected_schema=expected, require_status=True)
        except SystemExit as exc:
            block["comparison"] = None
            block["terminal_parity"] = False
            block["note"] = str(exc)
            return block
        block["pair_identity"] = pair
        if expected_schema is None:
            block["comparison"] = None
            block["terminal_parity"] = False
            block["note"] = ("terminal C4 comparison requires a sealed expected "
                              "schema bound to the requested campaign")
            return block
        cmp = strict_bitwise_all_frames(
            block["mp37"]["fcst"], block["mp137"]["fcst"],
            expected_schema=expected)
        run_end = block["mp37"].get("run_end_time")
        last_t = cmp.get("last_compared_time")
        reached = bool(run_end and last_t and last_t.endswith(run_end))
        block["comparison"] = cmp
        block["run_end_time"] = run_end
        block["last_compared_time"] = last_t
        block["times_equal_all_frames"] = bool(cmp.get("times_equal"))
        block["terminal_time_compared"] = reached
        # terminal parity requires BOTH the all-frame raw-bit AND that the last
        # compared frame actually IS the terminal state.
        block["terminal_parity"] = bool(cmp["strict_bitwise"] and reached)
    else:
        block["comparison"] = None
        block["terminal_parity"] = False
        block["note"] = ("terminal run INCOMPLETE — both runs must verify before "
                         "a terminal-state verdict is recorded")
    return block


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", type=Path, default=REPO / "host" / "KIM-meso_v1.0")
    ap.add_argument("--gateb-log", type=Path, default=None,
                    help="Gate B driver output to embed")
    ap.add_argument("--g3-report", type=Path, default=None,
                    help="gateb_g3_check.py JSON report to embed")
    ap.add_argument("--gated-log", type=Path, action="append", default=[],
                    help="Gate D strict_bitwise_nc output(s) to embed (repeatable)")
    ap.add_argument("--recert-runs", type=Path, default=None,
                    help="SS runs/ dir holding mp37/mp137_recert12h_* — assembles "
                         "the fail-closed legacy 12h x np4 recertification block")
    ap.add_argument("--recert-log", type=Path, default=None,
                    help="legacy12h_recert.log to embed verbatim")
    ap.add_argument("--terminal-runs", type=Path, default=None,
                    help="SS runs/ dir holding mp37/mp137_termparity_* — assembles "
                         "the fail-closed TERMINAL-STATE (12:00:00) parity block")
    ap.add_argument("--terminal-log", type=Path, default=None,
                    help="terminal_parity.log to embed verbatim")
    ap.add_argument("--expected-schema", type=Path, default=None,
                    help="sealed JSON schema for the requested C4 campaign; "
                         "required before a recert parity verdict")
    ap.add_argument("--out", type=Path, default=REPO / "artifacts" / "c4" /
                    "evidence_manifest.json")
    args = ap.parse_args()

    phys = args.host / "phys"
    dylib = (REPO / "libtorch" / "install" / "lib" / "libkdm6_c.dylib").resolve()

    head = cmd_out(["git", "-C", str(REPO), "rev-parse", "HEAD"])
    main_commit = cmd_out(["git", "-C", str(REPO), "rev-parse", "origin/main"])
    # `dirty` must reflect whether the EVIDENCE INPUTS (libtorch/oracle/harness
    # + docs other than this file) differ from HEAD — NOT the manifest itself.
    # The manifest is a self-written artifact: its freshly generated bytes would
    # otherwise always mark docs/ dirty, making `producer_commit` unreproducible
    # (built-on-a-dirty-tree) even for a fully committed closeout. Excluding the
    # output path means a clean committed checkout regenerates to dirty=false.
    diff_paths = ["libtorch", "oracle", "harness", "docs"]
    try:
        diff_paths.append(f":(exclude){args.out.resolve().relative_to(REPO)}")
    except ValueError:
        pass  # --out lives outside the repo tree: nothing to exclude
    dirty = subprocess.run(["git", "-C", str(REPO), "diff", "--quiet", "HEAD",
                            "--", *diff_paths],
                           capture_output=True).returncode != 0

    manifest = {
        "artifact": "conservative-interface-v1 C4 evidence",
        "public_repo": {
            "base_commit": "48d8c32",
            "producer_commit": head,
            "head_commit": head,
            "main_commit": main_commit,
            "tracked_tree_dirty_vs_head": dirty,
        },
        "private_host": {
            "path": str(args.host),
            "git": "not a git repo (gitignored in the public repo); "
                   "pinned by the sha256 set below",
        },
        "scheme_ids": {
            "37": "legacy KDM6 Fortran (never modified)",
            "137": "legacy KDM6AD C++ (never modified)",
            "237": "conservative-interface-v1 corrected Fortran reference",
            "337": "conservative-interface-v1 C++ (kdm6_step_v2_c physics_variant=1)",
        },
        "sha256": {
            "module_mp_kdm6.F": sha256(phys / "module_mp_kdm6.F"),
            "module_mp_kdm6ad.F": sha256(phys / "module_mp_kdm6ad.F"),
            "module_mp_kdm6_cons.F": sha256(phys / "module_mp_kdm6_cons.F"),
            "module_mp_kdm6ad_cons.F": sha256(phys / "module_mp_kdm6ad_cons.F"),
            "kdm6_iso_c.F": sha256(phys / "kdm6_iso_c.F"),
            "libkdm6_c(resolved)": sha256(dylib),
        },
        "libkdm6_c_resolved_path": str(dylib),
        "toolchain": {
            "os": f"{platform.system()} {platform.release()} {platform.machine()}",
            "gfortran": cmd_out(["gfortran", "--version"]),
            "mpif90": cmd_out(["mpif90", "--version"]),
            "clang": cmd_out(["clang", "--version"]),
            "torch": cmd_out([sys.executable, "-c",
                              "import torch; print(torch.__version__)"]),
        },
        "fixtures": {
            "gateb_driver.f90": sha256(args.host / "test" / "kdm6_cons_gateb" /
                                       "gateb_driver.f90"),
            "test_conservative_interface.cpp":
                sha256(REPO / "libtorch" / "tests" /
                       "test_conservative_interface.cpp"),
            "cons_fortran_scope_manifest.json":
                sha256(REPO / "harness" / "cons_fortran_scope_manifest.json"),
        },
    }

    # Gate A scope check, run in-process for the embedded report.
    scope = subprocess.run(
        [sys.executable, str(REPO / "harness" / "check_cons_fortran_scope.py"),
         "--legacy", str(phys / "module_mp_kdm6.F"),
         "--cons", str(phys / "module_mp_kdm6_cons.F"),
         "--legacy-wrapper", str(phys / "module_mp_kdm6ad.F")],
        capture_output=True, text=True)
    try:
        scope_report = json.loads(scope.stdout)
        scope_json_ok = True
    except json.JSONDecodeError:
        # the checker crashed before emitting its JSON report — surface the
        # raw output instead of masking it with a JSONDecodeError traceback.
        # Invalid JSON is itself a Gate A FAILURE (see the `ok` gate below):
        # a rc=0 with garbage output must NEVER read as PASS.
        scope_report = {"error": "scope checker produced no valid JSON",
                        "stdout": scope.stdout, "stderr": scope.stderr}
        scope_json_ok = False
    manifest["gate_a_scope_check"] = {
        "returncode": scope.returncode,
        "json_valid": scope_json_ok,
        "report": scope_report,
    }

    # Owner adjudication (2026-07-17) + the established cross-tree rate-dump
    # comparison scopes (compare_rate_dump.py refuses anything beyond these
    # without an explicit --min-fields opt-in).
    manifest["adjudication_2026_07_17"] = {
        "gate_b_g1_g2_g3_substitution": "APPROVED — standalone Gate B only; "
                                        "Gate D and C5 remain strict bitwise",
        "frozen_libtorch_instrumentation": "APPROVED — diagnostic-only, "
                                           "compile-time OFF default, separate "
                                           "diag branch, non-invasiveness gate",
        "production_numeric_changes_before_dump_evidence": "HELD",
        "fifth_fortran_physics_edit": "NOT pre-approved (reference stays "
                                      "reference; Case B requires re-opened "
                                      "Gate A adjudication)",
        "gate_d_conservative": "RESOLVED via C4-S1 (Case C shared C++ parity "
                               "fix, owner-approved 2026-07-18) — post-fix Gate D "
                               "short campaign 237<->337 measured FULL STRICT "
                               "BITWISE (see gate_d block)",
    }
    # C4-S1 shared parity exception (Case C, owner adjudication 2026-07-18).
    merge26 = cmd_out(["git", "-C", str(REPO), "rev-parse", "0b767e2"])
    # Full file list changed by the fix (merge-parents diff) — cmd_out only
    # returns the first line, so capture the whole list here.
    fix_files = subprocess.run(
        ["git", "-C", str(REPO), "diff", "--name-only", "0b767e2^1", "0b767e2"],
        capture_output=True, text=True).stdout.splitlines()
    manifest["c4s1_shared_piacw_fix"] = {
        "classification": "Case C — shared C++ reference-parity defect",
        "change": "libtorch/src/cold.cpp cloud_water_riming_torch piacw: "
                  "raw f64 PI -> path-conditional pi_t (operational f32 = "
                  "Fortran REAL(4) pi; fp64 DA keeps double pi)",
        "merge_commit": merge26,
        "files_changed": [f.strip() for f in fix_files],
        "binary_sha256": sha256(dylib),
        "fortran_modified": any(f.strip().endswith((".F", ".f90", ".F90"))
                                for f in fix_files),
        "tests": "test_cwr_piacw_pi_staging_f32_witness (RED->GREEN) + "
                 "_fp64_invariance; ctest 17/17; oracle parity 4/4",
    }
    manifest["gate_b_g3_3_status"] = {
        "verdict": "OPEN",
        "note": "piacw fixed the Gate D residual but NOT the standalone "
                "multi-subcycle G3.3 ULP-envelope exceedance (closure3 cons "
                "77852 > legacy 77312; species-iso 2188 > 1164 — unchanged "
                "pre/post fix). Attribution pending on "
                "analysis/c4-g3.3-first-divergence; Gate B is NOT closed as "
                "G1/G2/G3 until G3.3 is attributed or its metric re-adjudicated.",
    }
    if args.recert_runs is not None:
        manifest["legacy_12h_np4_recertification"] = legacy_12h_block(
            args.recert_runs, expected_schema=args.expected_schema)
        if args.recert_log and args.recert_log.exists():
            manifest["legacy_12h_np4_recertification"]["log"] = args.recert_log.read_text()
    if args.terminal_runs is not None:
        manifest["terminal_state_parity"] = terminal_parity_block(
            args.terminal_runs, expected_schema=args.expected_schema)
        if args.terminal_log and args.terminal_log.exists():
            manifest["terminal_state_parity"]["log"] = args.terminal_log.read_text()
    manifest["gate_d_bisection_verdict_2026_07_17"] = {
        "seed_rate": "piacw (cloud-water accretion by ice, qc->qi)",
        "first_diverging_op": "the ×π multiply in cloud_water_riming_torch's "
                              "piacw chain: C++ raw f64 PI vs Fortran REAL(4) pi",
        "proof": "all inputs bitwise to the last double bit (paired f32 + "
                 "raw-64-bit dumps); offline ladder replication over ALL "
                 "28729 diverging cells: fort==f32-π chain 28729/28729, "
                 "cpp==f64-π chain 28729/28729, cross-assignments 0; all "
                 "100 state-flip cells ⊂ piacw-diff set",
        "classification": "legacy-SHARED latent class (not Case A / not "
                          "Case B): same idiom already fixed for psacw/"
                          "pgacw/paacw via path-conditional pi_t; piacw "
                          "left on raw PI; invisible in legacy "
                          "certifications (zero straddle flips), exposed "
                          "by the variant's supercooled cloud-ice "
                          "population",
        "rhox_suspect": "REFUTED (rhox bitwise in paired dumps)",
        "fix_adjudication_historical": "piacw raw PI -> pi_t touches SHARED "
                                       "legacy C++ (outside the Case-A "
                                       "conservative-only pre-approval); "
                                       "provably moves legacy C++ piacw ONTO "
                                       "legacy Fortran; legacy re-cert scope "
                                       "required",
        "superseded_by": "RESOLVED — owner approved as Case C (2026-07-18); "
                         "merged PR #26 (0b767e2); legacy 12h x np4 recert PASS "
                         "(see legacy_12h_np4_recertification). This bisection "
                         "block is the historical investigation record, not an "
                         "open item.",
        "instrumentation": "diag/c4-poststateupdate-bisection only; "
                           "working tree reverted; Gate A re-verified "
                           "PASS; clean dylib sha reproduced; restored "
                           "237/337 runs STRICT BITWISE == pre-diag "
                           "baselines",
    }
    manifest["rate_dump_scope"] = {
        "graupel": {"fields": 8, "scope": "full list established", "verdict": "BITWISE"},
        "warmrates": {"fields": "first 8 of fort's 10 (--min-fields 8)",
                      "verdict": "BITWISE"},
        "ncrates": {"fields": "first 13 of fort 34 / cpp 23 (--min-fields 13; "
                              "trailing dbg_*/aux captures are capture-point "
                              "artifacts, not rates)",
                    "verdict": "BITWISE"},
    }

    if args.gateb_log and args.gateb_log.exists():
        text = args.gateb_log.read_text()
        # A VERDICT LINE, not a substring of the whole log. `"GATE B: PASS" in
        # text` is wrong in both directions and silent in both: a log that says
        # "expected GATE B: PASS, got FAIL" reports a pass, and a producer that
        # rewords its verdict reports a fail forever. Nothing in this repository
        # emits the string -- it comes from an external log -- so nothing here
        # would notice either. A log carrying no recognisable verdict now
        # records `None` and says so, instead of defaulting to a claim.
        verdicts = {ln.strip() for ln in text.splitlines()
                    if ln.strip() in ("GATE B: PASS", "GATE B: FAIL")}
        if verdicts == {"GATE B: PASS"}:
            gate_b_pass = True
        elif verdicts == {"GATE B: FAIL"}:
            gate_b_pass = False
        else:
            gate_b_pass = None
        manifest["gate_b"] = {
            "log": str(args.gateb_log),
            "pass": gate_b_pass,
            "verdict_lines": sorted(verdicts),
            "output": text,
        }
    if args.g3_report and args.g3_report.exists():
        manifest["gate_b_g3"] = json.loads(args.g3_report.read_text())
    if args.gated_log:
        manifest["gate_d"] = [
            {"log": str(p), "output": p.read_text()}
            for p in args.gated_log if p.exists()
        ]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, indent=2) + "\n")
    # Gate A passes ONLY if the checker exited 0 AND emitted a VALID JSON
    # report AND that report self-reports pass:true. A rc=0 with invalid or
    # non-passing JSON must fail loud — never a silent PASS.
    ok = (scope.returncode == 0
          and scope_json_ok
          and isinstance(scope_report, dict)
          and scope_report.get("pass") is True)
    print(f"wrote {args.out}  (gate A scope: {'PASS' if ok else 'FAIL'})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
