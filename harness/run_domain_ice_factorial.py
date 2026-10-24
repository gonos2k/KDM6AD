"""Guarded execution for the prepared native-domain ice factorial.

The default is a validated dry-run plan. Actual KDM6 calls require --execute.
Each chunk is read once into immutable bytes, SHA-checked against the manifest,
decoded from that same buffer, and then packed into the versioned fp64 batch
protocol. Completed chunks resume only when all input/tool/mode/response hashes
match their durable receipt.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

import numpy as np

from harness.ice_factorial_batch import (
    _arrays,
    _child_environment,
    _same_bits,
    pack_request,
    unpack_response,
)

DEFAULT_MANIFEST = Path(
    "/Users/yhlee/KDM6AD-k/host/research_evidence/mp137_ice_factorial_20261023/domain_preparation_fp64_final/manifest.json"
)
DEFAULT_EXECUTABLE = Path(
    "/Users/yhlee/KDM6AD-k/host/research_evidence/mp137_ice_factorial_20261023/batch_tool_build/ice_factorial_batch"
)
EXPECTED_MANIFEST_SHA256 = (
    "24630a58b03e54d90cc4bb6c6167e0571b02d2d002095424b19789286914601d"
)
EXPECTED_TOOL_SHA256 = (
    "b8051d8b8c983dd91e98c98204d900b27da39054eceeb282d4f9e0025cf894e7"
)
MODES = ("raw_cap", "norm_cap", "raw_actual", "norm_actual")
CHUNK_SIZE = 512
TOTAL_COLUMNS = 65_988
LEVELS = 39
NATIVE_NX = 234
NATIVE_NY = 282
TIME_METRICS = {
    "wall": re.compile(r"([0-9]+(?:\.[0-9]+)?)\s+real\b"),
    "user": re.compile(r"([0-9]+(?:\.[0-9]+)?)\s+user\b"),
    "system": re.compile(r"([0-9]+(?:\.[0-9]+)?)\s+sys\b"),
    "peak_rss_bytes": re.compile(r"([0-9]+)\s+maximum resident set size\b"),
}


class GuardError(RuntimeError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_exclusive(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _publish_json_noclobber(path: Path, value: dict) -> None:
    payload = (
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.tmp.", dir=path.parent)
    temp = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temp, path)
    except FileExistsError as exc:
        raise GuardError(f"output already exists: {path}") from exc
    finally:
        temp.unlink(missing_ok=True)


def _paths_overlap(left: Path, right: Path) -> bool:
    """Conservatively include case aliases on case-sensitive hosts as well."""
    left_parts = tuple(part.casefold() for part in left.resolve().parts)
    right_parts = tuple(part.casefold() for part in right.resolve().parts)
    return (
        left_parts[: len(right_parts)] == right_parts
        or right_parts[: len(left_parts)] == left_parts
    )


def _preflight_plan_output(path: Path | None, output_dir: Path | None) -> Path | None:
    """A CLI report must be a fresh file outside the execution output tree."""
    if path is None:
        return
    if os.path.lexists(path):
        raise GuardError(f"--plan-json output already exists: {path}")
    destination = path.resolve()
    for parent in destination.parents:
        if os.path.lexists(parent) and not parent.is_dir():
            raise GuardError(f"--plan-json parent is not a directory: {parent}")
    if output_dir is not None:
        if _paths_overlap(destination, output_dir):
            raise GuardError("--plan-json must be outside the execution output tree")
    return destination


def _preflight_input_paths(
    path: Path | None, output_dir: Path | None, plan: dict
) -> None:
    """Protect input names even if a prepared chunk is currently missing."""
    sources = [Path(plan["manifest_path"]), Path(plan["tool_path"])]
    sources.extend(Path(row["source_path"]) for row in plan["chunks"])
    destination = path.resolve() if path is not None else None
    run_root = output_dir.resolve() if output_dir is not None else None
    for source in sources:
        source = source.resolve()
        if destination is not None and _paths_overlap(destination, source):
            raise GuardError("--plan-json overlaps a protected input path")
        if run_root is not None and _paths_overlap(run_root, source):
            raise GuardError("execution output directory overlaps a protected input")


def _contained_file(base: Path, relative: str) -> Path:
    candidate = (base / relative).resolve()
    if not candidate.is_relative_to(base.resolve()):
        raise GuardError("manifest chunk path escapes the preparation directory")
    return candidate


def _load_chunk_from_bytes(raw: bytes, entry: dict, expected_start: int):
    """Decode exactly these verified bytes; never reopen the chunk path."""
    with np.load(BytesIO(raw), allow_pickle=False) as z:
        required = {"state", "forcing", "xland", "flat_indices", "i", "j"}
        if set(z.files) != required:
            raise GuardError(f"unexpected prepared chunk fields: {z.files}")
        s, f, x = _arrays(z["state"], z["forcing"], z["xland"])
        b, levels = s.shape[1:]
        start, end = entry["start_flat"], entry["stop_flat_exclusive"]
        flat = z["flat_indices"]
        i, j = z["i"], z["j"]
        if (
            start != expected_start
            or end - start != b
            or levels != LEVELS
            or not np.issubdtype(flat.dtype, np.integer)
            or not np.array_equal(flat, np.arange(start, end, dtype=flat.dtype))
            or i.shape != (b,)
            or j.shape != (b,)
            or np.any(flat < 0)
            or np.any(flat >= TOTAL_COLUMNS)
            or not np.array_equal(i, flat % NATIVE_NX)
            or not np.array_equal(j, flat // NATIVE_NX)
            or np.any(j >= NATIVE_NY)
        ):
            raise GuardError(
                "chunk tensor shapes or native flat-column indices disagree with manifest"
            )
        if b != min(CHUNK_SIZE, TOTAL_COLUMNS - start):
            raise GuardError(
                "chunk B does not match the fixed 512/final-452 chunk identity"
            )
        return s, f, x


def build_plan(
    manifest_path: Path = DEFAULT_MANIFEST,
    executable: Path = DEFAULT_EXECUTABLE,
    *,
    manifest_sha: str = EXPECTED_MANIFEST_SHA256,
    tool_sha: str = EXPECTED_TOOL_SHA256,
    mode: str = "raw_cap",
    workers: int = 10,
    dt: float = 20.0,
    ncmin_land: float = 10.0,
    ncmin_sea: float = 10.0,
) -> dict:
    if mode not in MODES:
        raise GuardError(f"mode must be one of {MODES}")
    if type(workers) is not int or not 1 <= workers <= 10:
        raise GuardError("workers must be an integer in 1..10")
    if (
        not all(math.isfinite(x) for x in (dt, ncmin_land, ncmin_sea))
        or dt <= 0
        or min(ncmin_land, ncmin_sea) < 0
    ):
        raise GuardError("invalid dt or ncmin thresholds")
    manifest_path, executable = Path(manifest_path), Path(executable)
    manifest_bytes = manifest_path.read_bytes()
    actual_manifest_sha = sha256(manifest_bytes)
    if actual_manifest_sha != manifest_sha:
        raise GuardError(
            "preparation manifest SHA-256 differs from the admitted final manifest"
        )
    tool_bytes = executable.read_bytes()
    actual_tool_sha = sha256(tool_bytes)
    if actual_tool_sha != tool_sha:
        raise GuardError(
            "tool SHA-256 differs from the admitted experimental executable"
        )
    manifest = json.loads(manifest_bytes)
    coverage = manifest.get("coverage", {})
    if (
        manifest.get("schema") != "kdm6.ice_factorial_endpoint_preparation.v2"
        or coverage.get("columns_expected") != TOTAL_COLUMNS
        or coverage.get("columns_written") != TOTAL_COLUMNS
        or coverage.get("missing") != 0
        or coverage.get("duplicate") != 0
    ):
        raise GuardError(
            "manifest is not the admitted complete native endpoint preparation"
        )
    mapping = manifest.get("mapping", {})
    expected_state = [
        "TH",
        "Q",
        "QC",
        "QR",
        "QI",
        "QS",
        "QG",
        "NN",
        "NC",
        "NI",
        "NR",
        "BG",
    ]
    if mapping.get("state_order") != expected_state or mapping.get("forcing_order") != [
        "DEN",
        "PII",
        "P",
        "DELZ",
    ]:
        raise GuardError(
            "prepared state/forcing field order differs from the runtime ABI map"
        )
    chunks = manifest.get("chunks", [])
    expected_bounds = [
        (start, min(start + CHUNK_SIZE, TOTAL_COLUMNS))
        for start in range(0, TOTAL_COLUMNS, CHUNK_SIZE)
    ]
    if len(chunks) != len(expected_bounds):
        raise GuardError("manifest chunk count differs from fixed 512-column identity")
    rows = []
    for index, (entry, (start, end)) in enumerate(zip(chunks, expected_bounds)):
        if (
            entry.get("start_flat") != start
            or entry.get("stop_flat_exclusive") != end
            or entry.get("columns") != end - start
        ):
            raise GuardError(
                f"manifest chunk {index} is reordered or has unexpected boundaries"
            )
        rows.append(
            {
                "index": index,
                "start": start,
                "end": end,
                "source_path": str(
                    _contained_file(manifest_path.parent, entry["path"])
                ),
                "source_sha256": entry["sha256"],
                "B": end - start,
                "L": LEVELS,
                "manifest_sha256": actual_manifest_sha,
                "tool_sha256": actual_tool_sha,
                "mode": mode,
                "dt_seconds": dt,
                "ncmin_land": ncmin_land,
                "ncmin_sea": ncmin_sea,
            }
        )
    return {
        "schema": "kdm6.ice_factorial_guarded_execution_plan.v1",
        "execution": "dry_run_only",
        "manifest_path": str(manifest_path),
        "manifest_sha256": actual_manifest_sha,
        "tool_path": str(executable),
        "tool_sha256": actual_tool_sha,
        "mode": mode,
        "dt_seconds": dt,
        "ncmin_land": ncmin_land,
        "ncmin_sea": ncmin_sea,
        "columns": TOTAL_COLUMNS,
        "levels": LEVELS,
        "chunk_size": CHUNK_SIZE,
        "chunk_count": len(rows),
        "workers": workers,
        "arms_execute_sequentially": True,
        "threads_per_worker": {
            "OMP_NUM_THREADS": 1,
            "MKL_NUM_THREADS": 1,
            "OMP_THREAD_LIMIT": 1,
            "OPENBLAS_NUM_THREADS": 1,
        },
        "calls": 0,
        "chunks": rows,
    }


def _parse_time_log(text: str) -> dict:
    out = {}
    for key, pattern in TIME_METRICS.items():
        matches = list(pattern.finditer(text))
        match = matches[-1] if matches else None
        if match is None:
            raise GuardError(
                f"/usr/bin/time -l log is missing required {key} measurement"
            )
        out[key] = (
            int(match.group(1)) if key == "peak_rss_bytes" else float(match.group(1))
        )
    return out


def _run_timed(
    executable: Path, request: Path, response: Path, log_path: Path, mode: str
) -> dict:
    command = [
        "/usr/bin/time",
        "-l",
        str(executable),
        "--input",
        str(request),
        "--output",
        str(response),
    ]
    start = time.monotonic()
    with log_path.open("ab") as log:
        completed = subprocess.run(
            command, stdout=log, stderr=subprocess.STDOUT, env=_child_environment(mode)
        )
    elapsed = time.monotonic() - start
    log_text = log_path.read_text(errors="replace")
    resources = _parse_time_log(log_text)
    resources["wall_seconds_measured"] = elapsed
    if completed.returncode != 0:
        raise GuardError(
            f"batch process failed with status {completed.returncode}; see {log_path}"
        )
    return resources


def _expected_receipt(task: dict, request_sha: str, tensor_sha: str) -> dict:
    return {
        "schema": "kdm6.ice_factorial_chunk_receipt.v1",
        "manifest_sha256": task["manifest_sha256"],
        "source_chunk_sha256": task["source_sha256"],
        "tool_sha256": task["tool_sha256"],
        "mode": task["mode"],
        "dt_seconds": task["dt_seconds"],
        "ncmin_land": task["ncmin_land"],
        "ncmin_sea": task["ncmin_sea"],
        "request_sha256": request_sha,
        "tensor_sha256": tensor_sha,
        "index": task["index"],
        "start_flat": task["start"],
        "stop_flat_exclusive": task["end"],
        "B": task["B"],
        "L": task["L"],
    }


def _check_response(raw: bytes, s, f, task: dict) -> dict:
    decoded = unpack_response(raw)
    if decoded["B"] != task["B"] or decoded["L"] != task["L"]:
        raise GuardError("response B,L differs from the admitted chunk")
    if not _same_bits(decoded["state_in"], s) or not _same_bits(
        decoded["forcing_in"], f
    ):
        raise GuardError("response echo differs bitwise from verified request tensors")
    return decoded


def execute_one(task: dict, *, runner=_run_timed, resume: bool = False) -> dict:
    """Run or safely resume one already planned native chunk."""
    if task.get("mode") not in MODES:
        raise GuardError(f"mode must be one of {MODES}")
    if task.get("manifest_sha256") != EXPECTED_MANIFEST_SHA256:
        raise GuardError("task manifest SHA-256 is not the admitted final preparation")
    if task.get("tool_sha256") != EXPECTED_TOOL_SHA256:
        raise GuardError(
            "task tool SHA-256 is not the admitted experimental executable"
        )
    if task.get("L") != LEVELS or task.get("B") != task.get("end", 0) - task.get(
        "start", 0
    ):
        raise GuardError("task dimensions differ from fixed native chunk contract")
    source_path = Path(task["source_path"])
    source_bytes = source_path.read_bytes()
    if sha256(source_bytes) != task["source_sha256"]:
        raise GuardError(f"input chunk SHA-256 mismatch: {source_path.name}")
    entry = {"start_flat": task["start"], "stop_flat_exclusive": task["end"]}
    s, f, x = _load_chunk_from_bytes(source_bytes, entry, task["start"])
    request_bytes = pack_request(
        s, f, x, task["dt_seconds"], task["ncmin_land"], task["ncmin_sea"]
    )
    tensor_bytes = s.tobytes() + f.tobytes() + x.tobytes()
    request_sha, tensor_sha = sha256(request_bytes), sha256(tensor_bytes)
    gate = _expected_receipt(task, request_sha, tensor_sha)
    output = Path(task["output_dir"])
    output.mkdir(parents=True, exist_ok=True)
    stem = f"chunk-{task['index']:05d}"
    req_path, res_path = output / f"{stem}.request.bin", output / f"{stem}.response.bin"
    log_path, receipt_path = output / f"{stem}.log", output / f"{stem}.receipt.json"

    tool_path = Path(task["tool_path"])
    if sha256(tool_path.read_bytes()) != task["tool_sha256"]:
        raise GuardError("batch executable changed after plan admission")
    if receipt_path.exists():
        if not resume:
            raise GuardError(f"existing receipt requires --resume: {receipt_path}")
        receipt = json.loads(receipt_path.read_text())
        for key, expected in gate.items():
            if receipt.get(key) != expected:
                raise GuardError(
                    f"resume gate mismatch in {key} for chunk {task['index']}"
                )
        if receipt.get("tool_sha256_after") != task["tool_sha256"]:
            raise GuardError(
                f"resume gate mismatch in tool_sha256_after for chunk {task['index']}"
            )
        response_bytes = res_path.read_bytes()
        response_sha = sha256(response_bytes)
        if response_sha != receipt.get("response_sha256"):
            raise GuardError(f"resume response hash mismatch for chunk {task['index']}")
        _check_response(response_bytes, s, f, task)
        return {
            "index": task["index"],
            "status": "skipped_completed",
            "response_path": str(res_path),
            "response_sha256": response_sha,
            "resources": receipt.get("resources", {}),
        }

    if res_path.exists():
        raise GuardError(f"unreceipted response exists; refusing overwrite: {res_path}")
    if req_path.exists():
        if req_path.read_bytes() != request_bytes:
            raise GuardError(
                f"existing request differs; refusing overwrite: {req_path}"
            )
    else:
        _write_exclusive(req_path, request_bytes)
    resources = runner(tool_path, req_path, res_path, log_path, task["mode"])
    tool_after = sha256(tool_path.read_bytes())
    if tool_after != task["tool_sha256"]:
        raise GuardError("batch executable changed during chunk execution")
    if not res_path.is_file():
        raise GuardError(f"batch executable did not publish a response; see {log_path}")
    response_bytes = res_path.read_bytes()
    decoded = _check_response(response_bytes, s, f, task)
    response_sha = sha256(response_bytes)
    receipt = dict(
        gate,
        response_sha256=response_sha,
        resources=resources,
        tool_sha256_after=tool_after,
        status="complete",
    )
    _publish_json_noclobber(receipt_path, receipt)
    return {
        "index": task["index"],
        "status": "complete",
        "response_path": str(res_path),
        "response_sha256": response_sha,
        "resources": resources,
        "precip_shape": list(decoded["precip"].shape),
    }


def execute_plan(
    plan: dict,
    *,
    output_dir: Path,
    executable: Path,
    workers: int = 10,
    resume: bool = False,
    runner=_run_timed,
) -> dict:
    if type(workers) is not int or not 1 <= workers <= 10:
        raise GuardError("workers must be an integer in 1..10")
    output_dir, executable = Path(output_dir), Path(executable)
    output_dir.mkdir(parents=True, exist_ok=True)
    if not resume and any(output_dir.iterdir()):
        raise GuardError("output directory must be empty unless --resume is explicit")
    tasks = []
    for row in plan["chunks"]:
        tasks.append(
            {**row, "tool_path": str(executable), "output_dir": str(output_dir)}
        )
    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(execute_one, task, runner=runner, resume=resume)
            for task in tasks
        ]
        for future in as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda row: row["index"])
    return {
        "schema": "kdm6.ice_factorial_arm_run.v1",
        "mode": plan["mode"],
        "manifest_sha256": plan["manifest_sha256"],
        "tool_sha256": plan["tool_sha256"],
        "workers": workers,
        "columns": plan["columns"],
        "levels": plan["levels"],
        "completed_chunks": sum(x["status"] == "complete" for x in results),
        "resumed_chunks": sum(x["status"] == "skipped_completed" for x in results),
        "chunks": results,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--executable", type=Path, default=DEFAULT_EXECUTABLE)
    ap.add_argument("--output-dir", type=Path)
    ap.add_argument("--mode", choices=MODES, default="raw_cap")
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--dt", type=float, default=20.0)
    ap.add_argument("--ncmin-land", type=float, default=10.0)
    ap.add_argument("--ncmin-sea", type=float, default=10.0)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument(
        "--execute", action="store_true", help="required to call the KDM6 executable"
    )
    ap.add_argument("--plan-json", type=Path)
    args = ap.parse_args(argv)
    if args.execute and args.output_dir is None:
        ap.error("--execute requires --output-dir")
    args.plan_json = _preflight_plan_output(args.plan_json, args.output_dir)
    plan = build_plan(
        args.manifest,
        args.executable,
        mode=args.mode,
        workers=args.workers,
        dt=args.dt,
        ncmin_land=args.ncmin_land,
        ncmin_sea=args.ncmin_sea,
    )
    _preflight_input_paths(args.plan_json, args.output_dir, plan)
    if not args.execute:
        if args.plan_json:
            _publish_json_noclobber(args.plan_json, plan)
        else:
            print(json.dumps(plan, indent=2, sort_keys=True))
        return 0
    result = execute_plan(
        plan,
        output_dir=args.output_dir,
        executable=args.executable,
        workers=args.workers,
        resume=args.resume,
    )
    if args.plan_json:
        _publish_json_noclobber(args.plan_json, result)
    else:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
