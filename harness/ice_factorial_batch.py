"""Pack, execute, and decode fixed-size fp64 research batches.

NPZ inputs use state (12,N,L), forcing (4,N,L), and xland (N), matching
State::fields()/Forcing::fields() and the explicit native-column ordering.
The B-column protocol is documented in docs/ICE_FACTORIAL_BATCH_PROTOCOL.md.
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
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np

IN_MAGIC = b"K6BATI1\0"
OUT_MAGIC = b"K6BATO1\0"
VERSION = 1
MAX_B, MAX_L = 4096, 256
IN_HEADER = struct.Struct("<8sIII3d")
OUT_HEADER = struct.Struct("<8sIII")
TRACE_ENV_VARS = ("KDM6_ICE_BOUNDARY_TRACE", "KDM6_SUBSTEP_DUMP",
                  "KDM6_SAME_CALL_BUDGET_TRACE")


def _arrays(state, forcing, xland):
    raw_s, raw_f, raw_x = np.asarray(state), np.asarray(forcing), np.asarray(xland)
    if any(a.dtype.kind != "f" or a.dtype.itemsize != 8 for a in (raw_s, raw_f, raw_x)):
        raise ValueError("batch inputs must already be fp64; implicit f32 widening is not accepted")
    s = np.asarray(raw_s, dtype="<f8", order="C")
    f = np.asarray(raw_f, dtype="<f8", order="C")
    x = np.asarray(raw_x, dtype="<f8", order="C")
    if s.ndim != 3 or s.shape[0] != 12 or f.ndim != 3 or f.shape[0] != 4:
        raise ValueError("state/forcing must have shapes (12,B,L)/(4,B,L)")
    b, l = s.shape[1:]
    if f.shape[1:] != (b, l) or x.shape != (b,):
        raise ValueError("state, forcing, xland batch shapes differ")
    if not (1 <= b <= MAX_B and 1 <= l <= MAX_L):
        raise ValueError("B or L outside supported bounds")
    if not all(np.isfinite(a).all() for a in (s, f, x)):
        raise ValueError("input arrays must be finite")
    if not np.isin(x, (1.0, 2.0)).all():
        raise ValueError("xland values must be 1 (land) or 2 (sea)")
    if np.any(f <= 0):
        raise ValueError("rho, pii, p, and delz must be positive")
    return s, f, x


def pack_request(state, forcing, xland, dt, ncmin_land, ncmin_sea):
    s, f, x = _arrays(state, forcing, xland)
    meta = (float(dt), float(ncmin_land), float(ncmin_sea))
    if not all(math.isfinite(v) for v in meta) or dt <= 0 or ncmin_land < 0 or ncmin_sea < 0:
        raise ValueError("dt must be positive and ncmin thresholds finite/nonnegative")
    b, l = s.shape[1:]
    return IN_HEADER.pack(IN_MAGIC, VERSION, b, l, *meta) + s.tobytes() + f.tobytes() + x.tobytes()


def unpack_response(data):
    view = memoryview(data)
    if len(view) < OUT_HEADER.size:
        raise ValueError("response shorter than fixed header")
    magic, version, b, l = OUT_HEADER.unpack_from(view)
    if magic != OUT_MAGIC or version != VERSION or not (1 <= b <= MAX_B and 1 <= l <= MAX_L):
        raise ValueError("bad response header")
    per = b * l
    count = 12 * per + 4 * per + 12 * per + 3 * b
    if len(view) != OUT_HEADER.size + count * 8:
        raise ValueError("response length does not match B,L")
    a = np.frombuffer(view, dtype="<f8", offset=OUT_HEADER.size).copy()
    if not np.isfinite(a).all():
        raise ValueError("response contains nonfinite values")
    p = 0
    state_in = a[p:p + 12 * per].reshape(12, b, l); p += 12 * per
    forcing_in = a[p:p + 4 * per].reshape(4, b, l); p += 4 * per
    state_out = a[p:p + 12 * per].reshape(12, b, l); p += 12 * per
    precip = a[p:p + 3 * b].reshape(3, b)
    return {"B": b, "L": l, "state_in": state_in, "forcing_in": forcing_in,
            "state_out": state_out, "precip": precip}


def plan_chunks(ncolumns, chunk_size):
    if not isinstance(ncolumns, int) or ncolumns <= 0:
        raise ValueError("ncolumns must be a positive integer")
    if not isinstance(chunk_size, int) or not (1 <= chunk_size <= MAX_B):
        raise ValueError(f"chunk_size must be in 1..{MAX_B}")
    return [(start, min(start + chunk_size, ncolumns))
            for start in range(0, ncolumns, chunk_size)]


def _child_environment(mode, overrides=None):
    child = os.environ.copy()
    child.update({"OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
                  "OMP_THREAD_LIMIT": "1", "OPENBLAS_NUM_THREADS": "1"})
    for name in TRACE_ENV_VARS:
        child.pop(name, None)
    if overrides:
        child.update(overrides)
    child["KDM6_ICE_FACTORIAL_MODE"] = mode
    return child


def _same_bits(a, b):
    return np.asarray(a).shape == np.asarray(b).shape and np.asarray(a).tobytes() == np.asarray(b).tobytes()


def _validate_workers(workers):
    if type(workers) is not int or not (1 <= workers <= 10):
        raise ValueError("workers must be an integer in 1..10")


def plan_prepared_manifest(manifest_path, *, expected_chunk_size=512, workers=1):
    """Validate prepared native chunks and produce four-arm work descriptors.

    This reads NPZ metadata/arrays for exact coverage and SHA checks, but does
    not call the KDM6 executable. Original prepared boundaries are retained.
    """
    _validate_workers(workers)
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    coverage = manifest.get("coverage", {})
    total = coverage.get("columns_expected")
    if (manifest.get("schema") not in ("kdm6.ice_factorial_endpoint_preparation.v1",
                                         "kdm6.ice_factorial_endpoint_preparation.v2") or
            coverage.get("missing") != 0 or coverage.get("duplicate") != 0 or
            coverage.get("columns_written") != total or not isinstance(total, int) or total <= 0):
        raise ValueError("preparation manifest does not certify complete unique column coverage")
    expected_state = ("TH", "Q", "QC", "QR", "QI", "QS", "QG", "NN", "NC", "NI", "NR", "BG")
    expected_forcing = ("DEN", "PII", "P", "DELZ")
    mapping = manifest.get("mapping", {})
    if tuple(mapping.get("state_order", ())) != expected_state or tuple(
            mapping.get("forcing_order", ())) != expected_forcing:
        raise ValueError("prepared manifest field order differs from runtime contract")
    chunks = manifest.get("chunks", [])
    if not chunks:
        raise ValueError("preparation manifest has no chunks")
    cursor = 0
    records = []
    base = manifest_path.parent
    for idx, entry in enumerate(chunks):
        start, end = entry.get("start_flat"), entry.get("stop_flat_exclusive")
        if start != cursor or not isinstance(end, int) or not start < end <= total:
            raise ValueError("prepared chunks have a gap, overlap, or invalid extent")
        if end-start > expected_chunk_size:
            raise ValueError("prepared chunk exceeds the fixed experiment chunk size")
        path = base / entry["path"]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != entry.get("sha256"):
            raise ValueError(f"prepared chunk hash mismatch: {path.name}")
        with np.load(path) as z:
            s, f, x = _arrays(z["state"], z["forcing"], z["xland"])
            if s.shape[1] != end-start or z["flat_indices"].tolist() != list(range(start, end)):
                raise ValueError("prepared chunk arrays/flat indices disagree with manifest")
            if z["i"].shape != (end-start,) or z["j"].shape != (end-start,):
                raise ValueError("prepared chunk lacks its per-column i,j coordinates")
        records.append({"index": idx, "start": start, "end": end,
                        "source_npz": entry["path"], "source_sha256": digest,
                        "B": end-start, "L": s.shape[2]})
        cursor = end
    if cursor != total:
        raise ValueError("prepared chunks do not end at columns_expected")
    arms = {mode: [dict(row, mode=mode, output_prefix=f"{mode}/batch-{row['index']:05d}") for row in records]
            for mode in ("raw_cap", "norm_cap", "raw_actual", "norm_actual")}
    return {"schema": "kdm6.ice_factorial_batch_plan.v1", "execution": "dry_run_only",
            "columns": total, "levels": records[0]["L"], "fixed_chunk_columns": expected_chunk_size,
            "chunk_count": len(records),
            "prepared_bundle_bytes_total": sum(int(row.get("bytes", 0)) for row in chunks),
            "preparation_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "coverage": {"missing": 0, "duplicate": 0},
            "input_packet_dtype": "fp64 validated from every NPZ array; no implicit widening",
            "runtime_config": {"call": "one value-only kdm6_fn FnResult per request",
                "physics_variant": "Legacy main chain",
                "factor_mode_environment": "KDM6_ICE_FACTORIAL_MODE set to the arm name",
                "trace_environment": "KDM6_ICE_BOUNDARY_TRACE, KDM6_SUBSTEP_DUMP and KDM6_SAME_CALL_BUDGET_TRACE cleared unless explicitly overridden",
                "threads_per_worker": {"OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
                    "OMP_THREAD_LIMIT": "1", "OPENBLAS_NUM_THREADS": "1"},
                "workers_per_arm": workers,
                "arms_execution": "sequential; each arm may use workers_per_arm independent chunk processes",
                "max_concurrent_chunk_processes": workers,
                "chunking": "fixed prepared flat-column order, 512 columns except final 452-column chunk"},
            "arms": arms}


def execute_batches(executable, state, forcing, xland, output_dir, *, chunk_size,
                    dt, ncmin_land, ncmin_sea, mode, env=None):
    s, f, x = _arrays(state, forcing, xland)
    if mode not in ("raw_cap", "norm_cap", "raw_actual", "norm_actual"):
        raise ValueError("unsupported factorial mode")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for index, (start, end) in enumerate(plan_chunks(s.shape[1], chunk_size)):
        req = output_dir / f"batch-{index:05d}.request.bin"
        res = output_dir / f"batch-{index:05d}.response.bin"
        with req.open("xb") as stream:
            stream.write(pack_request(s[:, start:end], f[:, start:end], x[start:end],
                                      dt, ncmin_land, ncmin_sea))
        child_env = _child_environment(mode, env)
        subprocess.run([str(executable), "--input", str(req), "--output", str(res)],
                       check=True, env=child_env)
        decoded = unpack_response(res.read_bytes())
        if not _same_bits(decoded["state_in"], s[:, start:end]) or not _same_bits(
                decoded["forcing_in"], f[:, start:end]):
            raise ValueError("response echo differs from request inputs")
        records.append({"index": index, "start": start, "end": end,
                        "request": req.name, "response": res.name,
                        "request_sha256": hashlib.sha256(req.read_bytes()).hexdigest(),
                        "response_sha256": hashlib.sha256(res.read_bytes()).hexdigest()})
    return {"schema": "kdm6.ice_factorial_batch_run.v1", "mode": mode,
            "chunk_size": chunk_size, "ncolumns": s.shape[1], "levels": s.shape[2],
            "fixed_chunk_plan": records}


def execute_prepared_manifest(executable, manifest_path, output_dir, *, mode,
                              dt, ncmin_land, ncmin_sea, chunk_size=512,
                              workers=1, env=None):
    """Execute one arm over already prepared fixed native chunks.

    Calling this function executes KDM6. The CLI requires explicit --execute
    for this path; default manifest handling only validates a dry-run plan.
    """
    _validate_workers(workers)
    plan = plan_prepared_manifest(manifest_path, expected_chunk_size=chunk_size,
                                  workers=workers)
    if mode not in plan["arms"]:
        raise ValueError("unsupported factorial mode")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = Path(manifest_path)
    def run_row(row):
        with np.load(manifest_path.parent / row["source_npz"]) as z:
            s, f, x = _arrays(z["state"], z["forcing"], z["xland"])
        index = row["index"]
        req = output_dir / f"batch-{index:05d}.request.bin"
        res = output_dir / f"batch-{index:05d}.response.bin"
        with req.open("xb") as stream:
            stream.write(pack_request(s, f, x, dt, ncmin_land, ncmin_sea))
        child_env = _child_environment(mode, env)
        subprocess.run([str(executable), "--input", str(req), "--output", str(res)],
                       check=True, env=child_env)
        decoded = unpack_response(res.read_bytes())
        if decoded["B"] != row["B"] or decoded["L"] != row["L"] or not _same_bits(
                decoded["state_in"], s) or not _same_bits(decoded["forcing_in"], f):
            raise ValueError("response shape or echoed operands differ from prepared chunk")
        return {"index": index, "start": row["start"], "end": row["end"],
                "request": req.name, "response": res.name,
                "request_sha256": hashlib.sha256(req.read_bytes()).hexdigest(),
                "response_sha256": hashlib.sha256(res.read_bytes()).hexdigest(),
                "source_npz_sha256": row["source_sha256"]}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run_row, row) for row in plan["arms"][mode]]
        records = [future.result() for future in as_completed(futures)]
    records.sort(key=lambda row: row["index"])
    return {"schema": "kdm6.ice_factorial_batch_run.v1", "mode": mode,
            "chunk_size": chunk_size, "ncolumns": plan["columns"],
            "levels": plan["levels"], "workers": workers,
            "fixed_chunk_plan": records}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input-npz", type=Path)
    ap.add_argument("--plan-manifest", type=Path, help="validate native prepared chunks and print four-arm dry-run plan")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--execute", action="store_true", help="execute one selected arm")
    ap.add_argument("--executable", type=Path)
    ap.add_argument("--output-dir", type=Path)
    ap.add_argument("--chunk-size", type=int)
    ap.add_argument("--workers", type=int, default=1, help="prepared-manifest subprocess workers (1..10)")
    ap.add_argument("--mode", choices=("raw_cap", "norm_cap", "raw_actual", "norm_actual"))
    ap.add_argument("--dt", type=float)
    ap.add_argument("--ncmin-land", type=float)
    ap.add_argument("--ncmin-sea", type=float)
    ap.add_argument("--plan-json", type=Path)
    a = ap.parse_args()
    if a.plan_manifest:
        if a.dry_run and not a.execute:
            plan = plan_prepared_manifest(a.plan_manifest, expected_chunk_size=a.chunk_size or 512,
                                          workers=a.workers)
        elif a.execute and not a.dry_run:
            if not all((a.executable, a.output_dir, a.chunk_size, a.mode,
                        a.dt is not None, a.ncmin_land is not None, a.ncmin_sea is not None)):
                ap.error("manifest execution requires --executable, --output-dir, --chunk-size, --mode, --dt, and both ncmin thresholds")
            plan = execute_prepared_manifest(a.executable, a.plan_manifest, a.output_dir,
                mode=a.mode, dt=a.dt, ncmin_land=a.ncmin_land, ncmin_sea=a.ncmin_sea,
                chunk_size=a.chunk_size, workers=a.workers)
        else:
            ap.error("manifest requires exactly one of --dry-run or --execute")
        encoded = json.dumps(plan, indent=2, sort_keys=True) + "\n"
        if a.plan_json:
            a.plan_json.write_text(encoded)
        else:
            print(encoded, end="")
        return
    if a.dry_run or a.execute or a.workers != 1 or not all((a.input_npz, a.executable, a.output_dir, a.chunk_size,
                             a.mode, a.dt is not None, a.ncmin_land is not None,
                             a.ncmin_sea is not None)):
        ap.error("execution requires --input-npz, --executable, --output-dir, --chunk-size, --mode, --dt, and both ncmin thresholds")
    with np.load(a.input_npz) as z:
        plan = execute_batches(a.executable, z["state"], z["forcing"], z["xland"], a.output_dir,
                               chunk_size=a.chunk_size, dt=a.dt, ncmin_land=a.ncmin_land,
                               ncmin_sea=a.ncmin_sea, mode=a.mode)
    encoded = json.dumps(plan, indent=2, sort_keys=True) + "\n"
    if a.plan_json:
        a.plan_json.write_text(encoded)
    else:
        print(encoded, end="")


if __name__ == "__main__":
    main()
