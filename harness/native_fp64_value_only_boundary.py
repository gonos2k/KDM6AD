"""Bounded f32-ABI vs opt-in fp64-value precision gate (explicit execution only).

This harness never changes the existing operational entry. It compares the
legacy DSO's default `kdm6_step_c`, the new DSO's default entry, and its
explicit `kdm6_native_fp64_value_c` against `kdm6_step_ad_c(value_only=1)` on
the exact same widened REAL4 operands. The direct-runtime reference executable
is used only for precip/rhog diagnostics and is itself an explicit model call.
"""
from __future__ import annotations

import argparse
import ctypes as ct
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import struct
import time
import re
from typing import NamedTuple

import numpy as np

REPO = Path(__file__).resolve().parents[1]
LEGACY_DSO = Path("/Users/yhlee/KDM6AD-k/host/research_evidence/actual_qr_20261024/build_final/libkdm6_actual_qr.2.0.0.dylib")
LEGACY_DSO_SHA256 = "5ef3b287cfff0a65e268f79d7f13f17540b5b477fcf647b3859ba61919ac0c99"
RUN_ROOT = Path("/Users/yhlee/KDM6AD-k/host/research_evidence/actual_qr_20261024/runs")
BLOCK_REQUESTS = {
    34: (RUN_ROOT / "chunk034_actual_on/request.bin", RUN_ROOT / "chunk034_actual_on/receipt.json"),
    40: (RUN_ROOT / "chunk040_actual_on/request.bin", RUN_ROOT / "chunk040_actual_on/receipt.json"),
}
IN_HEADER = struct.Struct("<8sIII3d")
REQUEST_MAGIC = b"K6BATI1\0"
REQUEST_VERSION = 1
REFERENCE_MAGIC = b"K6REF1\0\0"
REFERENCE_HEADER = struct.Struct("<8sIII3d64sQQiii")
FLOAT_PTR = ct.POINTER(ct.c_float)
DOUBLE_PTR = ct.POINTER(ct.c_double)
HANDLE_PTR = ct.POINTER(ct.c_void_p)
STATE_FIELDS = ("TH", "Q", "QC", "QR", "QI", "QS", "QG", "NN", "NC", "NI", "NR", "BG")
FORCING_FIELDS = ("DEN", "PII", "P", "DELZ")
WATER_STATE_ROWS = (1, 2, 3, 4, 5, 6)
TRACE_ENV_VARS = ("KDM6_ICE_BOUNDARY_TRACE", "KDM6_SUBSTEP_DUMP", "KDM6_SAME_CALL_BUDGET_TRACE")
THREAD_ENV = {"OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
              "OMP_THREAD_LIMIT": "1", "OPENBLAS_NUM_THREADS": "1", "OMP_DYNAMIC": "FALSE",
              "KDM6_ICE_FACTORIAL_MODE": "norm_actual",
              "KDM6_QR_TRANSPORT": "actual_departure"}


class BoundaryError(ValueError):
    pass


class BatchInput(NamedTuple):
    state: np.ndarray       # float64 source payload, [12,B,L]
    forcing: np.ndarray     # float64 source payload, [4,B,L]
    xland: np.ndarray       # float64 source payload, [B]
    dt: float
    ncmin_land: float
    ncmin_sea: float
    block_id: str
    input_sha256: str


class FullF64Reference(NamedTuple):
    state_out: np.ndarray   # float64 [12,B,L]
    precip: np.ndarray      # float64 [3,B], mm per column
    rhog: np.ndarray        # float64 [B,L], kg m-3
    widened_state: np.ndarray
    widened_forcing: np.ndarray
    widened_xland: np.ndarray
    fp_env_before: dict
    fp_env_after: dict


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _append_attempt(path: Path, record: dict):
    payload = (json.dumps(record, sort_keys=True, allow_nan=False) + "\n").encode()
    descriptor = os.open(Path(path), os.O_WRONLY | os.O_APPEND)
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("attempt ledger short write")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _persist_output_arrays(directory: Path, case: BatchInput, label: str,
                          attempt_log_path: Path, **arrays) -> dict:
    """Durably save one completed native result before the next ABI call."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{case.block_id}.{label}.npz"
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"forward output artifact already exists: {path}")
    with path.open("xb") as stream:
        np.savez_compressed(stream, **arrays)
        stream.flush()
        os.fsync(stream.fileno())
    receipt = {"path": path.name, "sha256": sha256_file(path),
               "bytes": path.stat().st_size, "call_label": label,
               "block_id": case.block_id, "request_sha256": case.input_sha256}
    _append_attempt(attempt_log_path, {"event": "FORWARD_OUTPUT_SAVED", **receipt})
    return receipt


def _persist_case_capture_metadata(directory: Path, case: BatchInput,
                                  attempt_log_path: Path, capture: dict) -> dict:
    """Persist call outputs, refusals, and FP-environment samples before analysis."""
    directory = Path(directory)
    path = directory / f"{case.block_id}.capture.json"
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"case capture already exists: {path}")
    payload = (json.dumps(capture, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    with path.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    receipt = {"path": path.name, "sha256": sha256_file(path), "bytes": path.stat().st_size,
               "block_id": case.block_id, "request_sha256": case.input_sha256}
    _append_attempt(attempt_log_path, {"event": "CASE_CAPTURE_METADATA_SAVED", **receipt})
    return receipt


def _call_with_attempt(path, case, label, dso, symbol, fn, *, dt, value_only=1, param_grad_flags=0):
    """Append a durable START record before one DSO call and a result after it."""
    selectors = {key: os.environ.get(key) for key in (
        "KDM6_ICE_FACTORIAL_MODE", "KDM6_QR_TRANSPORT")}
    forward_expected = bool(float(dt) > 0.0 and int(value_only) == 1 and int(param_grad_flags) == 0)
    start = {
        "event": "C_API_CALL_START", "time_ns": time.time_ns(),
        "label": label, "symbol": symbol, "dso_sha256": sha256_file(dso),
        "block_id": case.block_id, "request_sha256": case.input_sha256,
        "dt": float(dt), "value_only": int(value_only), "param_grad_flags": int(param_grad_flags),
        "selectors": selectors, "KDM6_forward_expected": forward_expected,
    }
    _append_attempt(path, start)
    try:
        result = fn()
    except BaseException as exc:
        _append_attempt(path, {
            "event": "C_API_CALL_EXCEPTION", "time_ns": time.time_ns(),
            "label": label, "exception_type": type(exc).__name__,
            "exception": str(exc), "KDM6_forward_may_have_run": forward_expected,
        })
        raise
    if isinstance(result, dict):
        result_code, handle, untouched = result["rc"], result["handle"], result["outputs_untouched"]
    elif isinstance(result, tuple) and len(result) >= 2:
        result_code, handle, untouched = result[0], result[1], False
    else:
        raise BoundaryError(f"unsupported C API call result shape for {label}: {type(result).__name__}")
    _append_attempt(path, {
        "event": "C_API_CALL_COMPLETE", "time_ns": time.time_ns(),
        "label": label, "rc": int(result_code),
        "handle_null": handle is None,
        "output_buffers_untouched": bool(untouched),
        "KDM6_forward_completed": bool(forward_expected and result_code == 0),
    })
    return result


def _finite_float_array(value, name, shape=None, dtype=np.float64):
    array = np.asarray(value)
    if array.dtype != np.dtype(dtype) or (shape is not None and array.shape != shape):
        raise BoundaryError(f"{name} expected {np.dtype(dtype)} {shape}, got {array.dtype} {array.shape}")
    if not np.isfinite(array).all():
        raise BoundaryError(f"{name} has nonfinite values")
    return array


def load_saved_batch_request(request_path: Path, receipt_path: Path, *, expected_block: int | None = None) -> BatchInput:
    """Read and pin a previously saved actual-QR B512 request; no executable call."""
    request_path, receipt_path = Path(request_path), Path(receipt_path)
    raw = request_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    receipt = json.loads(receipt_path.read_text())
    if digest != receipt.get("request_sha256"):
        raise BoundaryError(f"request differs from receipt: {request_path}")
    block = receipt.get("chunk")
    if expected_block is not None and block != expected_block:
        raise BoundaryError(f"expected block {expected_block}, received {block}")
    if receipt.get("condition") != "actual_on" or receipt.get("B") != 512 or receipt.get("L") != 39:
        raise BoundaryError("saved fixture is not an actual-on native B512/L39 request")
    if len(raw) < IN_HEADER.size:
        raise BoundaryError("saved batch request is shorter than its header")
    magic, version, batch, levels, dt, ncmin_land, ncmin_sea = IN_HEADER.unpack_from(raw)
    if magic != REQUEST_MAGIC or version != REQUEST_VERSION or batch != 512 or levels != 39:
        raise BoundaryError("saved request header differs from the native B512/L39 protocol")
    values = 12 * batch * levels + 4 * batch * levels + batch
    if len(raw) != IN_HEADER.size + values * 8:
        raise BoundaryError("saved request length differs from declared B,L")
    payload = np.frombuffer(raw, dtype="<f8", offset=IN_HEADER.size).copy()
    offset = 0
    state = payload[offset:offset + 12 * batch * levels].reshape(12, batch, levels)
    offset += 12 * batch * levels
    forcing = payload[offset:offset + 4 * batch * levels].reshape(4, batch, levels)
    offset += 4 * batch * levels
    xland = payload[offset:offset + batch]
    for name, value in (("state", state), ("forcing", forcing), ("xland", xland)):
        _finite_float_array(value, name, dtype=np.float64)
    if dt != 20.0 or not np.isin(xland, (1.0, 2.0)).all():
        raise BoundaryError("saved request has wrong dt or native XLAND values")
    return BatchInput(state, forcing, xland, dt, ncmin_land, ncmin_sea,
                      f"block{block:05d}", digest)


def from_npz(path: Path, *, block_id="fixture") -> BatchInput:
    """Read an offline fixture with float64 state/forcing/xland arrays."""
    path = Path(path)
    with np.load(path, allow_pickle=False) as archive:
        state = _finite_float_array(archive["state"], "state", dtype=np.float64)
        forcing = _finite_float_array(archive["forcing"], "forcing", dtype=np.float64)
        xland = _finite_float_array(archive["xland"], "xland", dtype=np.float64)
        dt = float(np.asarray(archive["dt"]).reshape(()))
        ncmin_land = float(np.asarray(archive["ncmin_land"]).reshape(()))
        ncmin_sea = float(np.asarray(archive["ncmin_sea"]).reshape(()))
    if state.ndim != 3 or state.shape[0] != 12 or forcing.shape != (4, *state.shape[1:]):
        raise BoundaryError("fixture state/forcing shapes must be (12,B,L)/(4,B,L)")
    if xland.shape != (state.shape[1],):
        raise BoundaryError("fixture xland must be (B,)")
    if not np.isin(xland, (1.0, 2.0)).all() or dt != 20.0:
        raise BoundaryError("fixture requires native XLAND and the fixed dt=20 s contract")
    return BatchInput(state, forcing, xland, dt, ncmin_land, ncmin_sea,
                      str(block_id), sha256_file(path))


def encode_batch_request(case: BatchInput) -> bytes:
    """Serialize the established K6BATI1 batch request; no executable call."""
    state = _finite_float_array(case.state, "request.state", dtype=np.float64)
    forcing = _finite_float_array(case.forcing, "request.forcing", dtype=np.float64)
    xland = _finite_float_array(case.xland, "request.xland", dtype=np.float64)
    if state.ndim != 3 or state.shape[0] != 12 or forcing.shape != (4, *state.shape[1:]):
        raise BoundaryError("request state/forcing must be (12,B,L)/(4,B,L)")
    batch, levels = state.shape[1:]
    if xland.shape != (batch,) or not np.isin(xland, (1.0, 2.0)).all():
        raise BoundaryError("request XLAND must be a native (B,) vector")
    if not math.isfinite(case.dt) or case.dt < 0.0:
        raise BoundaryError("request dt must be finite and nonnegative")
    if not math.isfinite(case.ncmin_land) or case.ncmin_land < 0.0 or not math.isfinite(case.ncmin_sea) or case.ncmin_sea < 0.0:
        raise BoundaryError("ncmin values must be finite and nonnegative")
    header = IN_HEADER.pack(REQUEST_MAGIC, REQUEST_VERSION, batch, levels,
                            float(case.dt), float(case.ncmin_land), float(case.ncmin_sea))
    return header + state.astype("<f8", copy=False).tobytes(order="C") + \
        forcing.astype("<f8", copy=False).tobytes(order="C") + xland.astype("<f8", copy=False).tobytes(order="C")


def make_nonsquare_probe_case(case: BatchInput, *, im=2, jme=4) -> BatchInput:
    """Select both land/sea columns from a source block in Fortran B=i*jme+j order."""
    if im * jme != 8:
        raise BoundaryError("bounded nonsquare probe uses exactly 2x4 columns")
    land = np.flatnonzero(case.xland == 1.0)
    sea = np.flatnonzero(case.xland == 2.0)
    if land.size < 4 or sea.size < 4:
        raise BoundaryError("source block lacks four land and four sea sentinel columns")
    selected = np.array([land[0], sea[0], land[1], sea[1],
                         land[2], sea[2], land[3], sea[3]], dtype=np.int64)
    result = BatchInput(case.state[:, selected].copy(), case.forcing[:, selected].copy(),
                        case.xland[selected].copy(), case.dt, case.ncmin_land,
                        case.ncmin_sea, f"{case.block_id}_nonsquare2x4", "")
    digest = hashlib.sha256(encode_batch_request(result)).hexdigest()
    return result._replace(input_sha256=digest)


def make_dt0_roundtrip_case(*, im=2, kme=3, jme=4) -> BatchInput:
    """Nonsquare identity probe carrying normals, subnormals and signed zeros."""
    batch = im * jme
    state = np.zeros((12, batch, kme), dtype=np.float64)
    state[0] = 300.0
    state[1] = 1.0e-3
    state[2:7] = 1.0e-5
    state[7:11] = 1.0e6
    state[11] = 1.0e-4
    tiny = float(np.nextafter(np.float32(0.0), np.float32(1.0), dtype=np.float32))
    state[0, 0, 0] = -0.0
    state[1, 1, 1] = tiny
    state[2, 2, 2] = -0.0
    state[8, 3, 0] = -tiny
    state[11, 7, 2] = -0.0
    forcing = np.ones((4, batch, kme), dtype=np.float64)
    forcing[0, 0, 0] = tiny
    forcing[1, 1, 1] = -0.0
    xland = np.array([1.0, 2.0, 2.0, 1.0, 1.0, 2.0, 2.0, 1.0], dtype=np.float64)
    case = BatchInput(state, forcing, xland, 0.0, 10.0, 10.0, "dt0_roundtrip_2x4", "")
    return case._replace(input_sha256=hashlib.sha256(encode_batch_request(case)).hexdigest())


def load_full_f64_reference(path: Path, case: BatchInput) -> FullF64Reference:
    """Read direct-runtime f64 state/precip/rhog output and widened-input echo."""
    raw = Path(path).read_bytes()
    if len(raw) < REFERENCE_HEADER.size:
        raise BoundaryError("direct-runtime reference is shorter than its header")
    (magic, version, batch, levels, dt, ncmin_land, ncmin_sea, request_sha,
     fpcr_before, fpcr_after, fe_round_before, fe_round_after, fe_nearest) = REFERENCE_HEADER.unpack_from(raw)
    if (magic != REFERENCE_MAGIC or version != 1 or batch != case.state.shape[1]
            or levels != case.state.shape[2] or request_sha.decode("ascii") != case.input_sha256
            or (dt, ncmin_land, ncmin_sea) != (case.dt, case.ncmin_land, case.ncmin_sea)):
        raise BoundaryError("direct-runtime reference header differs from the pinned request")
    count = (12 * batch * levels + 4 * batch * levels + batch +
             12 * batch * levels + 3 * batch + batch * levels)
    if len(raw) != REFERENCE_HEADER.size + count * 8:
        raise BoundaryError("direct-runtime reference length differs from its dimensions")
    values = np.frombuffer(raw, dtype="<f8", offset=REFERENCE_HEADER.size).copy()
    offset = 0
    state_in = values[offset:offset + 12 * batch * levels].reshape(12, batch, levels)
    offset += 12 * batch * levels
    forcing_in = values[offset:offset + 4 * batch * levels].reshape(4, batch, levels)
    offset += 4 * batch * levels
    xland_in = values[offset:offset + batch]
    offset += batch
    state_out = values[offset:offset + 12 * batch * levels].reshape(12, batch, levels)
    offset += 12 * batch * levels
    precip = values[offset:offset + 3 * batch].reshape(3, batch)
    offset += 3 * batch
    rhog = values[offset:offset + batch * levels].reshape(batch, levels)
    for name, value in (("reference state", state_out), ("reference precip", precip),
                        ("reference rhog", rhog), ("echo state", state_in),
                        ("echo forcing", forcing_in), ("echo xland", xland_in)):
        _finite_float_array(value, name, dtype=np.float64)
    def env_row(fpcr, fe_round):
        available = int(fpcr) != (1 << 64) - 1
        return {
            "fpcr": None if not available else f"0x{int(fpcr):016x}",
            "fpcr_rounding_mode_bits": None if not available else int((int(fpcr) >> 22) & 3),
            "fpcr_fz_bit24": None if not available else bool((int(fpcr) >> 24) & 1),
            "fegetround": int(fe_round),
            "fe_round_to_nearest": int(fe_round) == int(fe_nearest),
            "raw_fpcr_available": available,
        }
    return FullF64Reference(state_out, precip, rhog, state_in, forcing_in, xland_in,
                            env_row(fpcr_before, fe_round_before), env_row(fpcr_after, fe_round_after))


def widened_host_float32(case: BatchInput) -> BatchInput:
    """Apply the host f32 storage boundary once, then widen exactly to f64."""
    def widen(value, name):
        with np.errstate(over="ignore", invalid="ignore"):
            f32 = np.asarray(value, dtype=np.float32)
        if not np.isfinite(f32).all():
            raise BoundaryError(f"{name} is not representable as finite host float32")
        return f32.astype(np.float64)
    return BatchInput(
        widen(case.state, "state"), widen(case.forcing, "forcing"),
        widen(case.xland, "xland"), case.dt,
        float(np.float32(case.ncmin_land)), float(np.float32(case.ncmin_sea)),
        case.block_id, case.input_sha256,
    )


def batch_to_fortran_fields(fields: np.ndarray, *, im: int, kme: int, jme: int, dtype) -> list[np.ndarray]:
    """Convert [Nfields,B,K] with B=i*jme+j to per-field Fortran arrays."""
    raw = np.asarray(fields)
    if raw.ndim != 3 or raw.shape[1:] != (im * jme, kme):
        raise BoundaryError(f"logical fields must be [N,{im*jme},{kme}]")
    result = []
    for field in raw:
        array = np.empty((im, kme, jme), dtype=dtype, order="F")
        for i in range(im):
            for j in range(jme):
                array[i, :, j] = field[i * jme + j]
        result.append(array)
    return result


def fortran_fields_to_batch(fields: list[np.ndarray], *, im: int, kme: int, jme: int, dtype) -> np.ndarray:
    """Inverse of batch_to_fortran_fields, respecting the nonsquare XLAND layout."""
    output = np.empty((len(fields), im * jme, kme), dtype=dtype)
    for n, field in enumerate(fields):
        array = np.asarray(field)
        if array.shape != (im, kme, jme) or array.dtype != np.dtype(dtype) or not array.flags.f_contiguous:
            raise BoundaryError("Fortran field output has the wrong shape, dtype, or memory order")
        for i in range(im):
            for j in range(jme):
                output[n, i * jme + j] = array[i, :, j]
    return output


def batch_xland_to_fortran(xland, *, im: int, jme: int) -> np.ndarray:
    raw = np.asarray(xland)
    if raw.shape != (im * jme,) or raw.dtype != np.float32:
        raise BoundaryError("XLAND batch must be float32[B]")
    output = np.empty((im, jme), dtype=np.float32, order="F")
    for i in range(im):
        for j in range(jme):
            output[i, j] = raw[i * jme + j]
    return output


def widen_case_and_fortran(case: BatchInput, *, im: int, kme: int, jme: int):
    """Return exact common f32 inputs plus Fortran-layout storage for C ABI calls."""
    if (case.state.shape[1:] != (im * jme, kme)
            or case.forcing.shape[1:] != (im * jme, kme)):
        raise BoundaryError("case dimensions disagree with requested Fortran shape")
    widened = widened_host_float32(case)
    state32 = widened.state.astype(np.float32)
    forcing32 = widened.forcing.astype(np.float32)
    xland32 = widened.xland.astype(np.float32)
    state_f = batch_to_fortran_fields(state32, im=im, kme=kme, jme=jme, dtype=np.float32)
    forcing_f = batch_to_fortran_fields(forcing32, im=im, kme=kme, jme=jme, dtype=np.float32)
    xland_f = batch_xland_to_fortran(xland32, im=im, jme=jme)
    state64_f = batch_to_fortran_fields(widened.state, im=im, kme=kme, jme=jme, dtype=np.float64)
    forcing64_f = batch_to_fortran_fields(widened.forcing, im=im, kme=kme, jme=jme, dtype=np.float64)
    return widened, state_f, forcing_f, xland_f, state64_f, forcing64_f


def _p_float(array):
    return np.asarray(array).ctypes.data_as(FLOAT_PTR)


def _p_double(array):
    return np.asarray(array).ctypes.data_as(DOUBLE_PTR)


def _configure_c_api(lib, *, require_native_fp64=False):
    f32 = [FLOAT_PTR] * 12 + [FLOAT_PTR] * 4 + [ct.c_int] * 3 + [ct.c_double, ct.c_int, ct.c_int]
    f32 += [FLOAT_PTR] * 12 + [HANDLE_PTR, FLOAT_PTR, ct.c_double, ct.c_double]
    f32 += [FLOAT_PTR] * 4
    lib.kdm6_step_c.argtypes = f32
    lib.kdm6_step_c.restype = ct.c_int
    if hasattr(lib, "kdm6_native_fp64_value_c"):
        lib.kdm6_native_fp64_value_c.argtypes = f32
        lib.kdm6_native_fp64_value_c.restype = ct.c_int
    elif require_native_fp64:
        raise BoundaryError("new DSO lacks kdm6_native_fp64_value_c")
    lib.kdm6_step_ad_c.argtypes = _fp64_ad_signature()
    lib.kdm6_step_ad_c.restype = ct.c_int
    return lib


def _fp64_ad_signature():
    """Exact kdm6_step_ad_c header order: two packed inputs, dimensions, output."""
    return [DOUBLE_PTR, DOUBLE_PTR, ct.c_int, ct.c_int, ct.c_int, ct.c_double,
            ct.c_int, DOUBLE_PTR, HANDLE_PTR, FLOAT_PTR, ct.c_double, ct.c_double]


def _allocate_outputs(im, kme, jme, *, sentinel=None):
    def alloc(shape):
        out = np.empty(shape, dtype=np.float32, order="F")
        if sentinel is not None:
            out.fill(np.float32(sentinel))
        return out
    return ([alloc((im, kme, jme)) for _ in range(12)],
            [alloc((im, jme)) for _ in range(3)], alloc((im, kme, jme)))


def _call_step_float(lib, symbol, fields, forcing, xland, *, im, kme, jme,
                     dt, ncmin_land, ncmin_sea, value_only=1, param_grad_flags=0,
                     sentinel=None):
    state_out, precip_out, rhog_out = _allocate_outputs(im, kme, jme, sentinel=sentinel)
    initial_bytes = ([x.tobytes(order="F") for x in state_out]
                     + [x.tobytes(order="F") for x in precip_out] + [rhog_out.tobytes(order="F")])
    handle = ct.c_void_p(0x1234 if sentinel is not None else None)
    function = getattr(lib, symbol)
    rc = function(
        *[_p_float(x) for x in fields], *[_p_float(x) for x in forcing],
        im, kme, jme, float(dt), int(param_grad_flags), int(value_only),
        *[_p_float(x) for x in state_out], ct.byref(handle), _p_float(xland),
        float(ncmin_land), float(ncmin_sea), *[_p_float(x) for x in precip_out],
        _p_float(rhog_out),
    )
    out_bytes = ([x.tobytes(order="F") for x in state_out]
                 + [x.tobytes(order="F") for x in precip_out] + [rhog_out.tobytes(order="F")])
    outputs_untouched = out_bytes == initial_bytes
    state_batch = fortran_fields_to_batch(state_out, im=im, kme=kme, jme=jme, dtype=np.float32)
    precip_batch = np.empty((3, im * jme), dtype=np.float32)
    for i in range(im):
        for j in range(jme):
            for n in range(3):
                precip_batch[n, i * jme + j] = precip_out[n][i, j]
    rhog_batch = fortran_fields_to_batch([rhog_out], im=im, kme=kme, jme=jme, dtype=np.float32)[0]
    return {"rc": int(rc), "handle": handle.value, "state": state_batch,
            "precip": precip_batch, "rhog": rhog_batch,
            "outputs_untouched": outputs_untouched}


def _call_fp64_ad(lib, state64, forcing64, xland, *, im, kme, jme, dt, ncmin_land, ncmin_sea):
    state_out = np.empty(12 * im * kme * jme, dtype=np.float64)
    state_p = batch_to_fortran_fields(state64, im=im, kme=kme, jme=jme, dtype=np.float64)
    forcing_p = batch_to_fortran_fields(forcing64, im=im, kme=kme, jme=jme, dtype=np.float64)
    # kdm6_step_ad_c consumes field-major packed buffers, not one pointer per
    # field. Each field is a Fortran (im,kme,jme) block.
    state_packed = _pack_field_major_fortran(state_p)
    forcing_packed = _pack_field_major_fortran(forcing_p)
    handle = ct.c_void_p(0x1234)
    rc = lib.kdm6_step_ad_c(
        _p_double(state_packed), _p_double(forcing_packed),
        im, kme, jme, float(dt), 1,
        _p_double(state_out), ct.byref(handle), _p_float(xland),
        float(ncmin_land), float(ncmin_sea),
    )
    n = im * kme * jme
    unpacked = [np.array(state_out[i * n:(i + 1) * n].reshape((im, kme, jme), order="F"),
                          dtype=np.float64, order="F") for i in range(12)]
    output = fortran_fields_to_batch(unpacked, im=im, kme=kme, jme=jme, dtype=np.float64)
    return int(rc), handle.value, output


def _pack_field_major_fortran(fields):
    return np.concatenate([np.asarray(field).ravel(order="F") for field in fields])


def half_ulp_float32(value64):
    """Conservative half-ULP bound for one final binary32 storage cast."""
    value = np.asarray(value64, dtype=np.float64)
    with np.errstate(over="ignore", invalid="ignore"):
        rounded = value.astype(np.float32)
    if not np.isfinite(rounded).all():
        raise BoundaryError("f64 reference output overflows float32 writeback")
    up = np.nextafter(rounded, np.float32(np.inf), dtype=np.float32).astype(np.float64)
    down = np.nextafter(rounded, np.float32(-np.inf), dtype=np.float32).astype(np.float64)
    rounded64 = rounded.astype(np.float64)
    up_gap = np.where(np.isfinite(up), np.abs(up - rounded64), 0.0)
    down_gap = np.where(np.isfinite(down), np.abs(rounded64 - down), 0.0)
    ulp = np.maximum(up_gap, down_gap)
    return 0.5 * ulp


def float32_storage_roundtrip_probe():
    """Probe signed zero, normal, and subnormal binary32 widen/narrow preservation."""
    bits = np.array([0x00000000, 0x80000000, 0x00000001, 0x80000001,
                     0x007FFFFF, 0x00800000, 0x3F800000, 0x3F800001], dtype=np.uint32)
    values = bits.view(np.float32)
    widened = values.astype(np.float64)
    returned = widened.astype(np.float32)
    returned_bits = returned.view(np.uint32)
    return {
        "input_bits_hex": [f"{int(x):08x}" for x in bits],
        "roundtrip_bits_hex": [f"{int(x):08x}" for x in returned_bits],
        "all_bits_preserved": bool(np.array_equal(bits, returned_bits)),
        "subnormal_bits_preserved": bool(np.array_equal(bits[2:5], returned_bits[2:5])),
        "signed_zero_preserved": bool(np.array_equal(bits[:2], returned_bits[:2])),
    }


def capture_fp_environment(probe_library: Path | None = None):
    """Capture C fenv rounding plus raw AArch64 FPCR when the test probe is built."""
    if probe_library is None:
        libm = ct.CDLL(None)
        fegetround = libm.fegetround
        fegetround.argtypes, fegetround.restype = [], ct.c_int
        mode = int(fegetround())
        return {"fegetround": mode, "fpcr": None,
                "fpcr_rounding_mode": None, "fpcr_fz": None,
                "float32_roundtrip": float32_storage_roundtrip_probe(),
                "raw_fpcr_available": False}
    probe_library = Path(probe_library)
    lib = ct.CDLL(str(probe_library.resolve()))
    snapshot = lib.kdm6_fp_env_snapshot
    snapshot.argtypes = [ct.POINTER(ct.c_uint64), ct.POINTER(ct.c_int)]
    snapshot.restype = ct.c_int
    nearest = lib.kdm6_fe_tonearest
    nearest.argtypes, nearest.restype = [], ct.c_int
    fpcr, mode = ct.c_uint64(), ct.c_int()
    rc = snapshot(ct.byref(fpcr), ct.byref(mode))
    if rc != 0:
        raise BoundaryError(f"FP environment probe returned {rc}")
    raw = int(fpcr.value)
    has_fpcr = raw != (1 << 64) - 1
    return {
        "fegetround": int(mode.value),
        "fe_tonearest": int(nearest()),
        "fe_round_to_nearest": int(mode.value) == int(nearest()),
        "fpcr": None if not has_fpcr else f"0x{raw:016x}",
        "fpcr_rounding_mode_bits": None if not has_fpcr else int((raw >> 22) & 0x3),
        "fpcr_round_to_nearest": None if not has_fpcr else int((raw >> 22) & 0x3) == 0,
        "fpcr_fz_bit24": None if not has_fpcr else bool((raw >> 24) & 1),
        "fpcr_fz16_bit19": None if not has_fpcr else bool((raw >> 19) & 1),
        "float32_roundtrip": float32_storage_roundtrip_probe(),
        "raw_fpcr_available": has_fpcr,
    }


def _fp_environment_roundoff_compatible(snapshot):
    """Require measured nearest rounding and disabled float32 flush-to-zero."""
    probe = snapshot.get("float32_roundtrip")
    if probe is not None and (
        not isinstance(probe, dict) or probe.get("all_bits_preserved") is not True
    ):
        return False
    bits = snapshot.get("fpcr_rounding_mode_bits")
    return (
        snapshot.get("fe_round_to_nearest") is True
        and snapshot.get("raw_fpcr_available") is True
        and type(bits) is int and bits == 0
        and snapshot.get("fpcr_fz_bit24") is False
        and snapshot.get("fpcr_round_to_nearest", True) is True
    )


def _macho_file_backed_sections(path: Path) -> dict[tuple[str, str, str], bytes]:
    """Read file-backed Mach-O section payloads via the platform `otool` tool."""
    output = subprocess.run(["otool", "-l", str(path)], check=True,
                            capture_output=True, text=True).stdout.splitlines()
    sections = {}
    segment = None
    index = 0
    while index < len(output):
        line = output[index].strip()
        if line == "cmd LC_SEGMENT_64":
            segment = None
            for candidate in output[index + 1:index + 7]:
                match = re.match(r"segname (\S+)", candidate.strip())
                if match:
                    segment = match.group(1)
                    break
        elif line == "Section" and segment is not None:
            properties = {}
            for candidate in output[index + 1:index + 12]:
                match = re.match(r"\s*(sectname|segname|size|offset)\s+(\S+)", candidate)
                if match:
                    properties[match.group(1)] = match.group(2)
            if {"sectname", "segname", "size", "offset"}.issubset(properties):
                size, offset = int(properties["size"], 0), int(properties["offset"], 0)
                if size > 0 and offset > 0:
                    key = (segment, properties["segname"], properties["sectname"])
                    with Path(path).open("rb") as stream:
                        stream.seek(offset)
                        payload = stream.read(size)
                    if len(payload) != size:
                        raise BoundaryError(f"truncated Mach-O section {key} in {path}")
                    sections[key] = payload
        index += 1
    if not sections:
        raise BoundaryError(f"no file-backed Mach-O sections found in {path}")
    return sections


def verify_macho_section_identity(source: Path, execution_copy: Path) -> dict:
    """Require every file-backed section in the host copy to match its bridge DSO."""
    source_sections = _macho_file_backed_sections(Path(source))
    copy_sections = _macho_file_backed_sections(Path(execution_copy))
    if source_sections.keys() != copy_sections.keys():
        raise BoundaryError("host execution DSO has a different Mach-O section inventory")
    changed = ["/".join(key) for key in source_sections
               if source_sections[key] != copy_sections[key]]
    if changed:
        raise BoundaryError(f"host execution DSO section bytes differ from bridge: {changed}")
    return {"matching_file_backed_sections": len(source_sections),
            "section_payloads_bitwise_equal": True}


def _read_pinned_receipt(base_dir: Path, artifact: dict, expected_schema: str) -> tuple[dict, Path]:
    path = (base_dir / artifact["path"]).resolve()
    if not path.is_file() or sha256_file(path) != artifact["sha256"]:
        raise BoundaryError(f"receipt file/hash mismatch: {path}")
    value = json.loads(path.read_text())
    if value.get("schema") != expected_schema:
        raise BoundaryError(f"receipt schema mismatch: {path}")
    return value, path


def verify_build_and_reference_pins(manifest: dict, base_dir: Path) -> dict:
    """Bind execution to the prepared bridge, host-copy, and direct-runtime receipts."""
    pins = manifest.get("build_and_reference_pins")
    if not isinstance(pins, dict):
        raise BoundaryError("manifest lacks build_and_reference_pins")
    bridge, bridge_path = _read_pinned_receipt(
        base_dir, pins["bridge_build_receipt"], "kdm6.native_fp64_value_bridge_private_build.v1")
    host, host_path = _read_pinned_receipt(
        base_dir, pins["host_copy_build_receipt"], "kdm6.native_fp64_value_private_wrf_relink.v1")
    reference_set, reference_set_path = _read_pinned_receipt(
        base_dir, pins["reference_set_receipt"], "kdm6.native_fp64_value_only_direct_reference_set.v1")
    reference_build, reference_build_path = _read_pinned_receipt(
        base_dir, pins["reference_build_receipt"], "kdm6.native_fp64_value_only_reference_build.v1")
    fp_build, fp_build_path = _read_pinned_receipt(
        base_dir, pins["fp_env_probe_build_receipt"], "kdm6.fp_env_probe_build.v1")
    expected_bridge_sha = manifest["new_dso_source_sha256"]
    if (bridge.get("status") != "BUILT_UNTESTED_NO_MODEL_CALLS"
            or bridge.get("dso_sha256") != expected_bridge_sha
            or bridge.get("feature_macro") != "KDM6_ENABLE_NATIVE_FP64_VALUE_BRIDGE=1"
            or bridge.get("added_symbol") != "_kdm6_native_fp64_value_c"
            or bridge.get("KDM6_calls") != 0 or bridge.get("RTTOV_calls") != 0
            or bridge.get("host_steps") != 0 or not bridge.get("cxx_fp_contract_off")):
        raise BoundaryError("bridge build receipt does not describe the pinned value-only build")
    if (host.get("status") != "PRIVATE_BUILD_COMPLETE_UNTESTED_NO_HOST_CALLS"
            or host.get("capi_build_receipt_sha256") != sha256_file(bridge_path)
            or host.get("capi_dso_source_sha256") != expected_bridge_sha
            or host.get("capi_dso_execution_copy_sha256") != manifest["new_dso_sha256"]
            or host.get("capi_dso_execution_copy_path") != manifest["new_dso_absolute_path"]
            or host.get("expected_entry_contract", {}).get("symbol") != "_kdm6_native_fp64_value_c"
            or host.get("expected_entry_contract", {}).get("value_only") != 1
            or host.get("changed_archive_members") != ["kdm6_iso_c.o"]
            or host.get("KDM6_calls") != 0 or host.get("RTTOV_calls") != 0
            or host.get("host_steps") != 0):
        raise BoundaryError("host-copy build receipt does not bind the exact approved DSO")
    if (reference_set.get("status") != "COMPLETE_F64_REFERENCE_ONLY_NO_CAPI_TESTS"
            or reference_set.get("total_KDM6_forward_calls") != 3
            or reference_set.get("reference_archive_sha256") != manifest["reference_archive_sha256"]
            or reference_set.get("reference_driver_sha256") != manifest["reference_driver_sha256"]
            or reference_set.get("RTTOV_calls") != 0 or reference_set.get("host_steps") != 0
            or reference_set.get("optimizer_calls") != 0):
        raise BoundaryError("direct-runtime reference set receipt differs from the approved three-call set")
    files = reference_build.get("files", {})
    for key, expected in (("actual_qr_archive", manifest["reference_archive_sha256"]),
                          ("reference_driver", manifest["reference_driver_sha256"])):
        if files.get(key, {}).get("sha256") != expected:
            raise BoundaryError(f"reference build receipt {key} hash mismatch")
    if (reference_build.get("status") != "BUILD_COMPLETE_NO_MODEL_CALLS"
            or reference_build.get("KDM6_calls") != 0
            or reference_build.get("RTTOV_calls") != 0):
        raise BoundaryError("direct-runtime reference build receipt status mismatch")
    if (fp_build.get("status") != "BUILD_COMPLETE_NO_MODEL_CALLS"
            or fp_build.get("library_sha256") != manifest["fp_env_probe_sha256"]
            or fp_build.get("KDM6_calls") != 0 or fp_build.get("RTTOV_calls") != 0):
        raise BoundaryError("FP environment probe receipt mismatch")
    bridge_dso = (base_dir / manifest["new_dso_source_path"]).resolve()
    host_dso = Path(manifest["new_dso_absolute_path"])
    section_check = verify_macho_section_identity(bridge_dso, host_dso)
    return {
        "bridge_build_receipt_sha256": sha256_file(bridge_path),
        "host_copy_build_receipt_sha256": sha256_file(host_path),
        "reference_set_receipt_sha256": sha256_file(reference_set_path),
        "reference_build_receipt_sha256": sha256_file(reference_build_path),
        "fp_env_probe_build_receipt_sha256": sha256_file(fp_build_path),
        "bridge_dso_sha256": sha256_file(bridge_dso),
        "execution_copy_dso_sha256": sha256_file(host_dso),
        "host_copy_sections": section_check,
        "reference_archive_sha256": manifest["reference_archive_sha256"],
        "reference_driver_sha256": manifest["reference_driver_sha256"],
    }


def observed_water_roundoff(case: BatchInput, reference: FullF64Reference,
                            writeback_state, writeback_precip):
    """Measure output-cast error against the f64 reference and its half-ULP bound."""
    forcing = widened_host_float32(case).forcing
    ref_state = np.asarray(reference.state_out, dtype=np.float64)
    ref_precip = np.asarray(reference.precip, dtype=np.float64)
    new_state = np.asarray(writeback_state, dtype=np.float32).astype(np.float64)
    new_precip = np.asarray(writeback_precip, dtype=np.float32).astype(np.float64)
    layer_mass = forcing[0] * forcing[3]
    bounds, errors = {}, {}
    for row, name in zip(WATER_STATE_ROWS, ("QV", "QC", "QR", "QI", "QS", "QG")):
        bounds[name] = math.fsum(map(float, (layer_mass * half_ulp_float32(ref_state[row])).ravel()))
        errors[name] = math.fsum(map(float, (layer_mass * np.abs(new_state[row] - ref_state[row])).ravel()))
    precip_bound = math.fsum(map(float, half_ulp_float32(ref_precip).ravel()))
    precip_error = math.fsum(map(float, np.abs(new_precip - ref_precip).ravel()))
    total_bound = math.fsum(bounds.values()) + precip_bound
    total_error = math.fsum(errors.values()) + precip_error
    return {
        "species_cast_error_kg_m2": errors,
        "species_half_ulp_bound_kg_m2": bounds,
        "precip_cast_error_kg_m2": precip_error,
        "precip_half_ulp_bound_kg_m2": precip_bound,
        "combined_cast_error_kg_m2": total_error,
        "combined_half_ulp_bound_kg_m2": total_bound,
        "within_half_ulp_bound": bool(total_error <= total_bound),
        "scope": "final float32 storage roundoff only; no physical water closure or conservation claim",
    }


def water_roundoff_bound(reference_state, reference_precip, forcing):
    """Bound only final f64→f32 output rounding; not a conservation residual."""
    state = np.asarray(reference_state, dtype=np.float64)
    precip = np.asarray(reference_precip, dtype=np.float64)
    forcing = np.asarray(forcing, dtype=np.float64)
    if state.ndim != 3 or state.shape[0] != 12 or precip.shape != (3, state.shape[1]):
        raise BoundaryError("reference state/precip dimensions disagree")
    if forcing.shape != (4, *state.shape[1:]):
        raise BoundaryError("forcing must be [4,B,L]")
    dry_layer_mass = forcing[0] * forcing[3]
    if not np.isfinite(dry_layer_mass).all() or np.any(dry_layer_mass <= 0.0):
        raise BoundaryError("DEN*DELZ must be finite positive for the roundoff diagnostic")
    per_species = {}
    for row, name in zip(WATER_STATE_ROWS, ("QV", "QC", "QR", "QI", "QS", "QG")):
        value = state[row]
        bound = half_ulp_float32(value)
        weighted = dry_layer_mass * bound
        per_species[name] = math.fsum(map(float, weighted.ravel()))
    precip_bound = math.fsum(map(float, half_ulp_float32(precip).ravel()))  # mm == kg m-2 water equivalent
    total = math.fsum(per_species.values()) + precip_bound
    return {
        "state_species_roundoff_bound_kg_m2": per_species,
        "precip_roundoff_bound_kg_m2": precip_bound,
        "combined_output_storage_roundoff_bound_kg_m2": total,
        "mass_weight_source": "saved forcing DEN*DELZ (dry-air layer mass per area)",
        "precip_conversion": "mm water equivalent == kg m-2",
        "scope": "binary32 output storage roundoff bound only; not physical closure or conservation certification",
    }


def compare_f32_writeback(actual, reference_f64):
    expected = np.asarray(reference_f64, dtype=np.float32)
    got = np.asarray(actual)
    if got.dtype != np.float32 or got.shape != expected.shape:
        raise BoundaryError("writeback must be float32 and match the f64 candidate shape")
    return got.tobytes(order="C") == expected.tobytes(order="C")


@contextmanager
def _single_thread_environment(*, ice_mode="norm_actual", qr_transport="actual_departure"):
    names = set(THREAD_ENV) | set(TRACE_ENV_VARS)
    saved = {name: os.environ.get(name) for name in names}
    try:
        os.environ.update(THREAD_ENV)
        os.environ["KDM6_ICE_FACTORIAL_MODE"] = ice_mode
        os.environ["KDM6_QR_TRANSPORT"] = qr_transport
        for name in TRACE_ENV_VARS:
            os.environ.pop(name, None)
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def run_precision_case(case: BatchInput, legacy_dso: Path, new_dso: Path, *,
                       new_dso_sha256: str, full_f64_reference: FullF64Reference,
                       im: int, kme: int, jme: int, fp_env_probe: Path | None = None,
                       attempt_log_path: Path | None = None,
                       forward_artifact_dir: Path | None = None,
                       allow_native_execution=False):
    """Run all three C ABI paths. Deliberately disabled without explicit approval."""
    if allow_native_execution is not True:
        raise PermissionError("C ABI execution requires explicit root approval and allow_native_execution=True")
    if fp_env_probe is None:
        raise BoundaryError("approved ABI run requires the same-thread FPCR/fenv probe library")
    if attempt_log_path is None or not Path(attempt_log_path).is_file():
        raise BoundaryError("approved ABI run requires a pre-created append-only attempt log")
    if forward_artifact_dir is None:
        raise BoundaryError("approved ABI run requires a new per-forward artifact directory")
    legacy_dso, new_dso = Path(legacy_dso), Path(new_dso)
    if sha256_file(legacy_dso) != LEGACY_DSO_SHA256:
        raise BoundaryError("legacy reference DSO differs from the pinned actual-QR 5ef3 build")
    if sha256_file(new_dso) != new_dso_sha256:
        raise BoundaryError("new opt-in DSO differs from the supplied build receipt pin")
    widened, state_f32, forcing_f32, xland_f32, state64_f, forcing64_f = widen_case_and_fortran(
        case, im=im, kme=kme, jme=jme
    )
    state64 = widened.state
    forcing64 = widened.forcing
    xland_fortran = np.asfortranarray(xland_f32, dtype=np.float32)
    if (not np.array_equal(full_f64_reference.widened_state.view(np.uint64), state64.view(np.uint64))
            or not np.array_equal(full_f64_reference.widened_forcing.view(np.uint64), forcing64.view(np.uint64))
            or not np.array_equal(full_f64_reference.widened_xland.view(np.uint64), widened.xland.view(np.uint64))):
        raise BoundaryError("direct-runtime reference did not receive this exact widened host-f32 input")
    with _single_thread_environment(ice_mode="legacy", qr_transport="legacy"):
        fp_threadinit = capture_fp_environment(fp_env_probe)
        old_lib = _configure_c_api(ct.CDLL(str(legacy_dso.resolve())))
        new_lib = _configure_c_api(ct.CDLL(str(new_dso.resolve())), require_native_fp64=True)
        fp_after_library_init = capture_fp_environment(fp_env_probe)
        fp_before_calls = capture_fp_environment(fp_env_probe)
        old_f32 = _call_with_attempt(
            attempt_log_path, case, "legacy_old_f32", legacy_dso, "kdm6_step_c",
            lambda: _call_step_float(old_lib, "kdm6_step_c", state_f32, forcing_f32, xland_fortran,
                                     im=im, kme=kme, jme=jme, dt=case.dt,
                                     ncmin_land=case.ncmin_land, ncmin_sea=case.ncmin_sea), dt=case.dt)
        fp_after_old = capture_fp_environment(fp_env_probe)
        old_f32_artifact = _persist_output_arrays(
            forward_artifact_dir, case, "legacy_old_f32",
            attempt_log_path, state=old_f32["state"], precip=old_f32["precip"], rhog=old_f32["rhog"])
        new_default = _call_with_attempt(
            attempt_log_path, case, "new_default_f32", new_dso, "kdm6_step_c",
            lambda: _call_step_float(new_lib, "kdm6_step_c", state_f32, forcing_f32, xland_fortran,
                                     im=im, kme=kme, jme=jme, dt=case.dt,
                                     ncmin_land=case.ncmin_land, ncmin_sea=case.ncmin_sea), dt=case.dt)
        fp_after_default = capture_fp_environment(fp_env_probe)
        new_default_artifact = _persist_output_arrays(
            forward_artifact_dir, case, "new_default_f32",
            attempt_log_path, state=new_default["state"], precip=new_default["precip"], rhog=new_default["rhog"])
    # The old operational f32 path is tested under its legacy selector: the
    # actual-QR guard admits norm_actual only for the widened-f64 candidate.
    with _single_thread_environment(ice_mode="norm_actual", qr_transport="actual_departure"):
        fp_before_fp64_mode = capture_fp_environment(fp_env_probe)
        fp64_writeback = _call_with_attempt(
            attempt_log_path, case, "new_fp64_value", new_dso, "kdm6_native_fp64_value_c",
            lambda: _call_step_float(new_lib, "kdm6_native_fp64_value_c", state_f32, forcing_f32, xland_fortran,
                                     im=im, kme=kme, jme=jme, dt=case.dt,
                                     ncmin_land=case.ncmin_land, ncmin_sea=case.ncmin_sea), dt=case.dt)
        fp_after_fp64_value = capture_fp_environment(fp_env_probe)
        fp64_artifact = _persist_output_arrays(
            forward_artifact_dir, case, "new_fp64_value",
            attempt_log_path, state=fp64_writeback["state"], precip=fp64_writeback["precip"], rhog=fp64_writeback["rhog"])
        fp_before_fp64_ad = capture_fp_environment(fp_env_probe)
        ad_rc, ad_handle, f64_state = _call_with_attempt(
            attempt_log_path, case, "old_fp64_ad_value", legacy_dso, "kdm6_step_ad_c",
            lambda: _call_fp64_ad(old_lib, state64, forcing64, xland_fortran,
                                  im=im, kme=kme, jme=jme, dt=case.dt,
                                  ncmin_land=case.ncmin_land, ncmin_sea=case.ncmin_sea), dt=case.dt)
        fp_after_fp64_ad = capture_fp_environment(fp_env_probe)
        fp64_ad_artifact = _persist_output_arrays(
            forward_artifact_dir, case, "old_fp64_ad_value",
            attempt_log_path, state=f64_state)
        refusals = {
            "value_only_zero": _call_with_attempt(
                attempt_log_path, case, "reject_value_only_zero", new_dso, "kdm6_native_fp64_value_c",
                lambda: _call_step_float(new_lib, "kdm6_native_fp64_value_c", state_f32, forcing_f32, xland_fortran,
                                         im=im, kme=kme, jme=jme, dt=case.dt,
                                         ncmin_land=case.ncmin_land, ncmin_sea=case.ncmin_sea,
                                         value_only=0, sentinel=-12345.25),
                dt=case.dt, value_only=0,
            ),
            "value_only_unknown": _call_with_attempt(
                attempt_log_path, case, "reject_value_only_unknown", new_dso, "kdm6_native_fp64_value_c",
                lambda: _call_step_float(new_lib, "kdm6_native_fp64_value_c", state_f32, forcing_f32, xland_fortran,
                                         im=im, kme=kme, jme=jme, dt=case.dt,
                                         ncmin_land=case.ncmin_land, ncmin_sea=case.ncmin_sea,
                                         value_only=2, sentinel=-12345.25),
                dt=case.dt, value_only=2,
            ),
            "parameter_flags_nonzero": _call_with_attempt(
                attempt_log_path, case, "reject_param_grad_flags", new_dso, "kdm6_native_fp64_value_c",
                lambda: _call_step_float(new_lib, "kdm6_native_fp64_value_c", state_f32, forcing_f32, xland_fortran,
                                         im=im, kme=kme, jme=jme, dt=case.dt,
                                         ncmin_land=case.ncmin_land, ncmin_sea=case.ncmin_sea,
                                         param_grad_flags=1, sentinel=-12345.25),
                dt=case.dt, param_grad_flags=1,
            ),
        }
        fp_after_refusals = capture_fp_environment(fp_env_probe)
    fp_snapshots = {
        "threadinit": fp_threadinit,
        "after_library_init": fp_after_library_init,
        "before_abi_calls": fp_before_calls,
        "after_legacy_call": fp_after_old,
        "after_new_default_call": fp_after_default,
        "before_fp64_actual_mode_calls": fp_before_fp64_mode,
        "after_new_fp64_value_call": fp_after_fp64_value,
        "before_old_fp64_ad_call": fp_before_fp64_ad,
        "after_old_fp64_ad_call": fp_after_fp64_ad,
        "after_refusal_probes": fp_after_refusals,
        "direct_runtime_reference_before": full_f64_reference.fp_env_before,
        "direct_runtime_reference_after": full_f64_reference.fp_env_after,
        "direct_runtime_reference_kind": "separate direct-runtime process; f64-only reference output, no f32 writeback",
        "probe_library_sha256": sha256_file(fp_env_probe),
    }
    refusal_capture = {name: {"rc": result["rc"], "handle_null": result["handle"] is None,
                              "outputs_untouched": result["outputs_untouched"]}
                       for name, result in refusals.items()}
    capture_metadata = {
        "schema": "kdm6.native_fp64_value_only_case_capture.v1",
        "block_id": case.block_id,
        "request_sha256": case.input_sha256,
        "forward_output_artifacts": [old_f32_artifact, new_default_artifact,
                                      fp64_artifact, fp64_ad_artifact],
        "refusal_probes": refusal_capture,
        "fp_environment": fp_snapshots,
        "capture_complete_before_comparison": True,
    }
    capture_receipt = _persist_case_capture_metadata(
        forward_artifact_dir, case, attempt_log_path, capture_metadata)
    if any(call["rc"] != 0 or call["handle"] is not None for call in (old_f32, new_default, fp64_writeback)):
        raise BoundaryError("successful value-only call returned an error or non-NULL handle")
    if ad_rc != 0 or ad_handle is not None:
        raise BoundaryError("fp64 value-only AD-entry reference returned an error/handle")
    expected_refusal_codes = {"value_only_zero": -6, "value_only_unknown": -6,
                              "parameter_flags_nonzero": -3}
    for name, result in refusals.items():
        if result["rc"] != expected_refusal_codes[name] or result["handle"] is not None or not result["outputs_untouched"]:
            raise BoundaryError(f"new entry refusal contract failed for {name}: {result['rc']}")
    default_16 = all(compare_f32_writeback(a, b) for a, b in (
        (new_default["state"], old_f32["state"]),
        (new_default["precip"], old_f32["precip"]),
        (new_default["rhog"], old_f32["rhog"]),
    ))
    new16_vs_reference = all(compare_f32_writeback(a, b) for a, b in (
        (fp64_writeback["state"], f64_state),
        (fp64_writeback["precip"], full_f64_reference.precip),
        (fp64_writeback["rhog"], full_f64_reference.rhog),
    ))
    if full_f64_reference.state_out.shape != f64_state.shape or not np.array_equal(
        full_f64_reference.state_out.view(np.uint64), f64_state.view(np.uint64)
    ):
        raise BoundaryError("direct-runtime full-f64 reference disagrees with step_ad_c state candidate")
    roundoff = water_roundoff_bound(full_f64_reference.state_out, full_f64_reference.precip, forcing64)
    measured_roundoff = observed_water_roundoff(case, full_f64_reference,
                                                 fp64_writeback["state"], fp64_writeback["precip"])
    env_snapshots = tuple(value for key, value in fp_snapshots.items()
                          if key not in ("direct_runtime_reference_kind", "probe_library_sha256"))
    env_compatible = all(_fp_environment_roundoff_compatible(item) for item in env_snapshots)
    measured_roundoff["half_ulp_bound_environment_compatible"] = env_compatible
    measured_roundoff["half_ulp_bound_validated"] = bool(
        env_compatible and measured_roundoff["within_half_ulp_bound"]
    )
    return {
        "block_id": case.block_id,
        "request_sha256": case.input_sha256,
        "legacy_dso_sha256": sha256_file(legacy_dso),
        "new_dso_sha256": sha256_file(new_dso),
        "shape_fortran_im_kme_jme": [im, kme, jme],
        "inputs_exact_widened_f32": True,
        "physics_selectors_by_path": {
            "legacy_and_new_default_f32": {"KDM6_ICE_FACTORIAL_MODE": "legacy", "KDM6_QR_TRANSPORT": "legacy"},
            "new_fp64_value_and_old_fp64_ad_reference": {"KDM6_ICE_FACTORIAL_MODE": "norm_actual", "KDM6_QR_TRANSPORT": "actual_departure"},
        },
        "old_fp32_vs_new_default_all16_bitwise": default_16,
        "new_fp64_value_writeback_vs_step_ad_c_all12_state_bitwise": compare_f32_writeback(fp64_writeback["state"], f64_state),
        "new_fp64_value_writeback_vs_direct_runtime_all16_bitwise": new16_vs_reference,
        "refusal_probes": {name: {"rc": result["rc"], "handle_null": result["handle"] is None,
                                  "all_output_buffers_untouched": result["outputs_untouched"]}
                           for name, result in refusals.items()},
        "state_component_checks": {name: compare_f32_writeback(fp64_writeback["state"][i], f64_state[i])
                                    for i, name in enumerate(STATE_FIELDS)},
        "roundoff_water_bound": roundoff,
        "observed_roundoff_water_bound": measured_roundoff,
        "forward_output_artifacts": [old_f32_artifact, new_default_artifact,
                                      fp64_artifact, fp64_ad_artifact],
        "capture_metadata": capture_receipt,
        "fp_environment": {**fp_snapshots, "half_ulp_bound_environment_compatible": env_compatible},
        "scope": "precision-boundary comparison only; no physical-budget closure or host-step certification",
    }


def run_dt0_roundtrip_probe(legacy_dso: Path, new_dso: Path, *, new_dso_sha256: str,
                            fp_env_probe: Path | None = None, attempt_log_path: Path | None = None,
                            forward_artifact_dir: Path | None = None,
                            allow_native_execution=False):
    """Explicit dt=0 ABI identity probe for f32 normals/subnormals/signed-zero."""
    if allow_native_execution is not True:
        raise PermissionError("C ABI execution requires explicit root approval")
    if fp_env_probe is None:
        raise BoundaryError("dt=0 precision probe requires the same-thread FPCR/fenv helper")
    if attempt_log_path is None or not Path(attempt_log_path).is_file():
        raise BoundaryError("dt=0 probe requires the pre-created attempt log")
    if forward_artifact_dir is None:
        raise BoundaryError("dt=0 probe requires a new per-call artifact directory")
    case = make_dt0_roundtrip_case(im=2, kme=3, jme=4)
    if sha256_file(legacy_dso) != LEGACY_DSO_SHA256 or sha256_file(new_dso) != new_dso_sha256:
        raise BoundaryError("dt=0 probe DSO source pins differ")
    widened, state_f32, forcing_f32, xland_f32, state64_f, forcing64_f = widen_case_and_fortran(
        case, im=2, kme=3, jme=4
    )
    xland_fortran = np.asfortranarray(xland_f32, dtype=np.float32)
    expected_f32 = widened.state.astype(np.float32)
    with _single_thread_environment(ice_mode="legacy", qr_transport="legacy"):
        fp_before = capture_fp_environment(fp_env_probe)
        old_lib = _configure_c_api(ct.CDLL(str(Path(legacy_dso).resolve())))
        new_lib = _configure_c_api(ct.CDLL(str(Path(new_dso).resolve())), require_native_fp64=True)
        fp_init = capture_fp_environment(fp_env_probe)
        old_f32 = _call_with_attempt(
            attempt_log_path, case, "dt0_legacy_f32", legacy_dso, "kdm6_step_c",
            lambda: _call_step_float(old_lib, "kdm6_step_c", state_f32, forcing_f32, xland_fortran,
                                     im=2, kme=3, jme=4, dt=0.0,
                                     ncmin_land=case.ncmin_land, ncmin_sea=case.ncmin_sea), dt=0.0)
        old_f32_artifact = _persist_output_arrays(
            forward_artifact_dir, case, "dt0_legacy_f32", attempt_log_path,
            state=old_f32["state"], precip=old_f32["precip"], rhog=old_f32["rhog"])
        fp_after_old = capture_fp_environment(fp_env_probe)
        new_default = _call_with_attempt(
            attempt_log_path, case, "dt0_new_default_f32", new_dso, "kdm6_step_c",
            lambda: _call_step_float(new_lib, "kdm6_step_c", state_f32, forcing_f32, xland_fortran,
                                     im=2, kme=3, jme=4, dt=0.0,
                                     ncmin_land=case.ncmin_land, ncmin_sea=case.ncmin_sea), dt=0.0)
        new_default_artifact = _persist_output_arrays(
            forward_artifact_dir, case, "dt0_new_default_f32", attempt_log_path,
            state=new_default["state"], precip=new_default["precip"], rhog=new_default["rhog"])
        fp_after_default = capture_fp_environment(fp_env_probe)
    with _single_thread_environment(ice_mode="norm_actual", qr_transport="actual_departure"):
        new_fp64 = _call_with_attempt(
            attempt_log_path, case, "dt0_new_fp64_value", new_dso, "kdm6_native_fp64_value_c",
            lambda: _call_step_float(new_lib, "kdm6_native_fp64_value_c", state_f32, forcing_f32, xland_fortran,
                                     im=2, kme=3, jme=4, dt=0.0,
                                     ncmin_land=case.ncmin_land, ncmin_sea=case.ncmin_sea), dt=0.0)
        fp_after_new = capture_fp_environment(fp_env_probe)
        new_fp64_artifact = _persist_output_arrays(
            forward_artifact_dir, case, "dt0_new_fp64_value", attempt_log_path,
            state=new_fp64["state"], precip=new_fp64["precip"], rhog=new_fp64["rhog"])
        fp_before_ad = capture_fp_environment(fp_env_probe)
        ad_rc, ad_handle, f64_state = _call_with_attempt(
            attempt_log_path, case, "dt0_old_fp64_ad_value", legacy_dso, "kdm6_step_ad_c",
            lambda: _call_fp64_ad(old_lib, widened.state, widened.forcing, xland_fortran,
                                  im=2, kme=3, jme=4, dt=0.0,
                                  ncmin_land=case.ncmin_land, ncmin_sea=case.ncmin_sea), dt=0.0)
        fp_after_ad = capture_fp_environment(fp_env_probe)
        old_ad_artifact = _persist_output_arrays(
            forward_artifact_dir, case, "dt0_old_fp64_ad_value", attempt_log_path,
            state=f64_state)
    dt0_capture = {
        "schema": "kdm6.native_fp64_value_only_dt0_capture.v1",
        "block_id": case.block_id,
        "request_sha256": case.input_sha256,
        "call_output_artifacts": [old_f32_artifact, new_default_artifact,
                                   new_fp64_artifact, old_ad_artifact],
        "fp_environment": {
            "before_calls": fp_before,
            "after_library_init": fp_init,
            "after_legacy_f32": fp_after_old,
            "after_new_default_f32": fp_after_default,
            "after_new_fp64_value": fp_after_new,
            "before_old_fp64_ad": fp_before_ad,
            "after_old_fp64_ad": fp_after_ad,
            "probe_library_sha256": sha256_file(fp_env_probe),
        },
        "capture_complete_before_identity_checks": True,
    }
    dt0_capture_receipt = _persist_case_capture_metadata(
        forward_artifact_dir, case, attempt_log_path, dt0_capture)
    for name, result in (("legacy", old_f32), ("new_default", new_default), ("new_fp64", new_fp64)):
        if result["rc"] != 0 or result["handle"] is not None:
            raise BoundaryError(f"{name} dt=0 value call failed")
        if not np.array_equal(result["state"].view(np.uint32), expected_f32.view(np.uint32)):
            raise BoundaryError(f"{name} dt=0 path changed normal/subnormal/signed-zero state bits")
    if ad_rc != 0 or ad_handle is not None:
        raise BoundaryError("fp64 AD value-only dt=0 identity call failed")
    if not np.array_equal(f64_state.view(np.uint64), widened.state.view(np.uint64)):
        raise BoundaryError("fp64 AD dt=0 identity changed widened host-f32 state")
    all16_default_match = all(compare_f32_writeback(a, b) for a, b in (
        (new_default["state"], old_f32["state"]),
        (new_default["precip"], old_f32["precip"]),
        (new_default["rhog"], old_f32["rhog"]),
    ))
    zero_diagnostics = all(np.count_nonzero(a.view(np.uint32)) == 0 for a in (
        old_f32["precip"], old_f32["rhog"], new_default["precip"], new_default["rhog"],
        new_fp64["precip"], new_fp64["rhog"],
    ))
    snapshots = (fp_before, fp_init, fp_after_old, fp_after_default, fp_after_new)
    return {
        "block_id": case.block_id,
        "request_sha256": case.input_sha256,
        "dimensions_im_kme_jme": [2, 3, 4],
        "dt_seconds": 0.0,
        "float32_roundtrip_probe": float32_storage_roundtrip_probe(),
        "legacy_dt0_identity_all_state_bits": True,
        "new_default_dt0_identity_all_state_bits": True,
        "new_fp64_value_dt0_identity_all_state_bits": True,
        "fp64_ad_dt0_identity_all_state_bits": True,
        "legacy_vs_new_default_all16_bitwise": all16_default_match,
        "physics_selectors_by_path": {
            "legacy_and_new_default_f32": {"KDM6_ICE_FACTORIAL_MODE": "legacy", "KDM6_QR_TRANSPORT": "legacy"},
            "new_fp64_value_and_old_fp64_ad_reference": {"KDM6_ICE_FACTORIAL_MODE": "norm_actual", "KDM6_QR_TRANSPORT": "actual_departure"},
        },
        "all_precip_and_rhog_outputs_are_positive_zero": zero_diagnostics,
        "call_output_artifacts": [old_f32_artifact, new_default_artifact,
                                  new_fp64_artifact, old_ad_artifact],
        "capture_metadata": dt0_capture_receipt,
        "fp_environment_threadinit_and_after_calls": {
            "snapshots": list(snapshots),
            "half_ulp_bound_environment_compatible": all(_fp_environment_roundoff_compatible(x) for x in snapshots),
            "probe_library_sha256": sha256_file(fp_env_probe),
        },
        "scope": "dt=0 identity boundary test only; no microphysics state advance or conservation claim",
    }


def load_manifest_case(entry: dict, base_dir: Path) -> tuple[BatchInput, int, int, int]:
    """Load one pinned input request; this function never loads a DSO."""
    kind = entry.get("kind")
    if kind == "saved_request":
        request = (base_dir / entry["request"]).resolve()
        receipt = (base_dir / entry["receipt"]).resolve()
        case = load_saved_batch_request(request, receipt, expected_block=int(entry["block"]))
    elif kind == "fixture_npz":
        npz = (base_dir / entry["input_npz"]).resolve()
        if sha256_file(npz) != entry["input_npz_sha256"]:
            raise BoundaryError(f"fixture NPZ differs from manifest: {npz}")
        case = from_npz(npz, block_id=entry["id"])
        request = (base_dir / entry["request"]).resolve()
        request_bytes = encode_batch_request(case)
        request_sha = hashlib.sha256(request_bytes).hexdigest()
        if request_sha != entry["request_sha256"] or request.read_bytes() != request_bytes:
            raise BoundaryError(f"fixture request differs from input NPZ recipe: {request}")
        case = case._replace(input_sha256=request_sha)
    else:
        raise BoundaryError(f"unsupported boundary case kind: {kind!r}")
    im, kme, jme = (int(value) for value in entry["fortran_shape_im_kme_jme"])
    if case.state.shape[1:] != (im * jme, kme):
        raise BoundaryError(f"case {entry['id']} dimensions differ from the declared Fortran shape")
    if entry.get("request_sha256", case.input_sha256) != case.input_sha256:
        raise BoundaryError(f"case {entry['id']} request SHA differs")
    return case, im, kme, jme


def run_direct_runtime_reference_driver(driver: Path, case: BatchInput, request_path: Path,
                                        output_path: Path, *, attempt_log_path: Path | None = None,
                                        allow_native_execution=False):
    """Capture one full-f64 direct-runtime 16-field reference; explicit call gate."""
    if allow_native_execution is not True:
        raise PermissionError("direct-runtime reference execution requires explicit root approval")
    driver, request_path, output_path = map(Path, (driver, request_path, output_path))
    receipt_path = output_path.with_suffix(output_path.suffix + ".receipt.json")
    if attempt_log_path is None:
        attempt_log_path = output_path.with_suffix(output_path.suffix + ".attempt.jsonl")
    attempt_log_path = Path(attempt_log_path)
    if (not driver.is_file() or output_path.exists() or output_path.is_symlink()
            or receipt_path.exists() or receipt_path.is_symlink()
            or attempt_log_path.exists() or attempt_log_path.is_symlink()):
        raise FileExistsError("reference driver must exist and outputs must be new")
    request_bytes = encode_batch_request(case)
    request_sha = hashlib.sha256(request_bytes).hexdigest()
    if case.input_sha256 != request_sha:
        raise BoundaryError("direct-runtime reference input differs from the case request SHA")
    if request_path.exists():
        if request_path.is_symlink() or sha256_file(request_path) != request_sha:
            raise BoundaryError("preexisting reference request path differs from case bytes")
    else:
        with request_path.open("xb") as stream:
            stream.write(request_bytes)
            stream.flush()
            os.fsync(stream.fileno())
    command = [str(driver.resolve()), "--input", str(request_path.resolve()),
               "--output", str(output_path.resolve()), "--request-sha256", request_sha]
    start_event = {
        "event": "DIRECT_RUNTIME_REFERENCE_START", "time_ns": time.time_ns(),
        "driver_sha256": sha256_file(driver), "request_sha256": request_sha,
        "reference_output": str(output_path),
        "KDM6_forward_expected": int(case.dt > 0.0),
        "selectors": {"KDM6_ICE_FACTORIAL_MODE": "norm_actual",
                      "KDM6_QR_TRANSPORT": "actual_departure"},
    }
    with attempt_log_path.open("xb") as stream:
        stream.write((json.dumps(start_event, sort_keys=True) + "\n").encode())
        stream.flush()
        os.fsync(stream.fileno())
    try:
        with _single_thread_environment():
            subprocess.run(command, check=True, env=os.environ.copy())
    except BaseException as exc:
        _append_attempt(attempt_log_path, {
            "event": "DIRECT_RUNTIME_REFERENCE_EXCEPTION", "time_ns": time.time_ns(),
            "exception_type": type(exc).__name__, "exception": str(exc),
            "KDM6_forward_may_have_run": int(case.dt > 0.0),
        })
        raise
    reference = load_full_f64_reference(output_path, case)
    receipt = {
        "schema": "kdm6.native_fp64_value_only_direct_runtime_reference.v1",
        "status": "DIRECT_RUNTIME_REFERENCE_COMPLETE",
        "driver_sha256": sha256_file(driver),
        "request_sha256": request_sha,
        "request_bytes": request_path.stat().st_size,
        "reference_sha256": sha256_file(output_path),
        "reference_bytes": output_path.stat().st_size,
        "KDM6_forward_calls": 0 if case.dt <= 0.0 else 1,
        "RTTOV_calls": 0,
        "host_steps": 0,
        "optimizer_calls": 0,
        "runtime_selectors": {"KDM6_ICE_FACTORIAL_MODE": "norm_actual",
                              "KDM6_QR_TRANSPORT": "actual_departure"},
        "fp_environment_before": reference.fp_env_before,
        "fp_environment_after": reference.fp_env_after,
        "scope": "direct kdm6_fn reference; no C ABI bridge, host step or RTTOV call",
    }
    _append_attempt(attempt_log_path, {
        "event": "DIRECT_RUNTIME_REFERENCE_COMPLETE", "time_ns": time.time_ns(),
        "KDM6_forward_calls": receipt["KDM6_forward_calls"],
        "reference_sha256": receipt["reference_sha256"],
    })
    receipt["attempt_log_path"] = attempt_log_path.name
    receipt["attempt_log_sha256"] = sha256_file(attempt_log_path)
    encoded = (json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    with receipt_path.open("xb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    return receipt


def execute_boundary_manifest(manifest_path: Path, output_path: Path, *, expected_manifest_sha256: str,
                              allow_native_execution=False):
    """Run the explicitly approved DSO comparisons from a frozen manifest."""
    if allow_native_execution is not True:
        raise PermissionError("ABI comparisons require explicit root approval")
    manifest_path, output_path = Path(manifest_path), Path(output_path)
    if output_path.exists() or output_path.is_symlink():
        raise FileExistsError(f"new output only: {output_path}")
    attempt_log_path = output_path.with_suffix(output_path.suffix + ".attempts.jsonl")
    if attempt_log_path.exists() or attempt_log_path.is_symlink():
        raise FileExistsError(f"new attempt ledger only: {attempt_log_path}")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema") != "kdm6.native_fp64_value_only_boundary_inputs.v1":
        raise BoundaryError("boundary input manifest schema mismatch")
    if sha256_file(manifest_path) != expected_manifest_sha256:
        raise BoundaryError("boundary manifest SHA differs from supplied detached pin")
    base_dir = manifest_path.parent
    if sha256_file(Path(__file__).resolve()) != manifest.get("producer_source_sha256"):
        raise BoundaryError("executing harness source differs from frozen producer pin")
    test_path = (REPO / "harness/tests/test_native_fp64_value_only_boundary.py").resolve()
    if sha256_file(test_path) != manifest.get("producer_test_sha256"):
        raise BoundaryError("focused boundary tests differ from frozen producer pin")
    producer_snapshot = (base_dir / manifest["producer_snapshot_path"]).resolve()
    if sha256_file(producer_snapshot) != manifest.get("producer_snapshot_sha256"):
        raise BoundaryError("frozen producer snapshot receipt differs from manifest")
    snapshot_receipt = json.loads(producer_snapshot.read_text())
    if (snapshot_receipt.get("harness_source_sha256") != manifest["producer_source_sha256"]
            or snapshot_receipt.get("focused_test_sha256") != manifest["producer_test_sha256"]):
        raise BoundaryError("producer snapshot receipt does not bind executed code/tests")
    snapshot_dir = producer_snapshot.parent
    for key in ("harness_source", "focused_test"):
        record = snapshot_receipt["files"][key]
        if sha256_file(snapshot_dir / record["snapshot_path"]) != record["sha256"]:
            raise BoundaryError(f"frozen producer snapshot file hash mismatch: {key}")
    legacy = Path(manifest["legacy_dso_path"])
    new = (base_dir / manifest["new_dso_path"]).resolve()
    new_sha = manifest["new_dso_sha256"]
    env_probe = (base_dir / manifest["fp_env_probe_path"]).resolve()
    reference_driver = (base_dir / manifest["reference_driver_path"]).resolve()
    forward_artifact_dir = (base_dir / manifest["forward_artifact_dir"]).resolve()
    if forward_artifact_dir.exists() or forward_artifact_dir.is_symlink():
        raise FileExistsError(f"new forward artifact directory only: {forward_artifact_dir}")
    if sha256_file(legacy) != LEGACY_DSO_SHA256:
        raise BoundaryError("legacy actual-QR DSO pin mismatch")
    if sha256_file(new) != new_sha:
        raise BoundaryError("new DSO differs from its build pin")
    if sha256_file(env_probe) != manifest["fp_env_probe_sha256"]:
        raise BoundaryError("FP environment probe differs from its source pin")
    if sha256_file(reference_driver) != manifest["reference_driver_sha256"]:
        raise BoundaryError("direct-runtime reference driver differs from its source pin")
    build_and_reference_pins = verify_build_and_reference_pins(manifest, base_dir)

    prepared = []
    saved_blocks = set()
    has_nonsquare = False
    reference_call_counts = []
    for entry in manifest["cases"]:
        case, im, kme, jme = load_manifest_case(entry, base_dir)
        if entry["kind"] == "saved_request":
            saved_blocks.add(int(entry["block"]))
        if im > 1 and jme > 1:
            has_nonsquare = True
        reference_path = (base_dir / entry["reference_path"]).resolve()
        if sha256_file(reference_path) != entry["reference_sha256"]:
            raise BoundaryError(f"case {entry['id']} full-f64 reference hash mismatch")
        ref_receipt_path = (base_dir / entry["reference_receipt_path"]).resolve()
        if sha256_file(ref_receipt_path) != entry["reference_receipt_sha256"]:
            raise BoundaryError(f"case {entry['id']} direct-runtime reference receipt hash mismatch")
        ref_receipt = json.loads(ref_receipt_path.read_text())
        if (ref_receipt.get("status") != "DIRECT_RUNTIME_REFERENCE_COMPLETE"
                or ref_receipt.get("request_sha256") != case.input_sha256
                or ref_receipt.get("reference_sha256") != entry["reference_sha256"]
                or ref_receipt.get("driver_sha256") != manifest["reference_driver_sha256"]
                or ref_receipt.get("runtime_selectors") != {
                    "KDM6_ICE_FACTORIAL_MODE": "norm_actual",
                    "KDM6_QR_TRANSPORT": "actual_departure",
                }):
            raise BoundaryError(f"case {entry['id']} direct-runtime reference receipt binding mismatch")
        attempt_relpath = entry.get("reference_attempt_log_path", ref_receipt["attempt_log_path"])
        reference_attempt_path = (base_dir / attempt_relpath).resolve()
        if reference_attempt_path.name != Path(ref_receipt["attempt_log_path"]).name:
            raise BoundaryError(f"case {entry['id']} attempt-log path is not receipt-bound")
        if sha256_file(reference_attempt_path) != ref_receipt.get("attempt_log_sha256"):
            raise BoundaryError(f"case {entry['id']} direct-runtime attempt ledger hash mismatch")
        reference = load_full_f64_reference(reference_path, case)
        reference_call_counts.append(int(ref_receipt.get("KDM6_forward_calls", -1)))
        prepared.append((case, im, kme, jme, reference, ref_receipt, sha256_file(ref_receipt_path),
                         sha256_file(reference_attempt_path)))
    required_saved_blocks = set(int(value) for value in manifest.get("required_saved_blocks", [34, 40]))
    if not required_saved_blocks.issubset(saved_blocks) or not has_nonsquare:
        raise BoundaryError("manifest lacks its declared saved B512 blocks or non-square multi-column case")
    if any(count != 1 for count in reference_call_counts):
        raise BoundaryError("each positive-dt direct f64 reference receipt must record exactly one KDM forward")

    # Every input, receipt, DSO, tool, and reference is checked before the first
    # ABI call, so a malformed later case cannot leave a partial test campaign.
    attempt_log_path.parent.mkdir(parents=True, exist_ok=True)
    with attempt_log_path.open("xb") as stream:
        start = {"event": "BOUNDARY_CAMPAIGN_START", "time_ns": time.time_ns(),
                 "manifest_sha256": sha256_file(manifest_path),
                 "expected_precision_cases": len(prepared),
                 "expected_CAPI_entries": 7 * len(prepared) + 4,
                 "prior_CAPI_entries_spent": manifest["approved_call_budget"]["prior_CAPI_entries_spent"],
                 "global_CAPI_entries_if_complete": (manifest["approved_call_budget"]["prior_CAPI_entries_spent"]
                                                     + 7 * len(prepared) + 4),
                 "preexisting_direct_reference_forwards": sum(reference_call_counts),
                 "global_positive_dt_forward_requests_if_complete": (
                     manifest["approved_call_budget"]["prior_CAPI_forward_requests_spent"]
                     + sum(reference_call_counts) + 4 * len(prepared)),
                 "no_retry": True}
        stream.write((json.dumps(start, sort_keys=True) + "\n").encode())
        stream.flush()
        os.fsync(stream.fileno())
    results = []
    for case, im, kme, jme, reference, ref_receipt, ref_receipt_sha, ref_attempt_sha in prepared:
        results.append(run_precision_case(
            case, legacy, new, new_dso_sha256=new_sha, full_f64_reference=reference,
            im=im, kme=kme, jme=jme, fp_env_probe=env_probe,
            attempt_log_path=attempt_log_path,
            forward_artifact_dir=forward_artifact_dir,
            allow_native_execution=True,
        ))
    dt0 = run_dt0_roundtrip_probe(legacy, new, new_dso_sha256=new_sha,
                                  fp_env_probe=env_probe, attempt_log_path=attempt_log_path,
                                  forward_artifact_dir=forward_artifact_dir,
                                  allow_native_execution=True)
    _append_attempt(attempt_log_path, {"event": "BOUNDARY_CAMPAIGN_COMPLETE", "time_ns": time.time_ns(),
                                       "precision_cases_completed": len(results),
                                       "dt0_probe_completed": True})
    report = {
        "schema": "kdm6.native_fp64_value_only_boundary_result.v1",
        "manifest_sha256": sha256_file(manifest_path),
        "legacy_dso_sha256": sha256_file(legacy),
        "new_dso_sha256": sha256_file(new),
        "reference_driver_sha256": sha256_file(reference_driver),
        "fp_env_probe_sha256": sha256_file(env_probe),
        "build_and_reference_pins": build_and_reference_pins,
        "attempt_log_path": attempt_log_path.name,
        "attempt_log_sha256": sha256_file(attempt_log_path),
        "forward_artifact_directory": forward_artifact_dir.name,
        "resumed_after_prior_saved_case": manifest.get("resumed_after_prior_saved_case"),
        "cases": results,
        "direct_runtime_reference_receipts": [
            {"block_id": case.block_id, "receipt_sha256": ref_receipt_sha,
             "attempt_log_sha256": ref_attempt_sha, "KDM6_forward_calls": ref_receipt["KDM6_forward_calls"]}
            for case, _, _, _, _, ref_receipt, ref_receipt_sha, ref_attempt_sha in prepared
        ],
        "dt0_roundtrip_probe": dt0,
        "model_call_scope": {
            "native_f32_or_fp64_capi_physical_forwards": 4 * len(results),
            "direct_runtime_f64_reference_forwards": sum(reference_call_counts),
            "direct_runtime_reference_calls_by_case": reference_call_counts,
            "c_api_precision_entry_calls_including_three_rejections_per_case": 7 * len(results),
            "dt0_noop_value_capi_entry_calls": 4,
            "dt0_noop_kernel_forwards": 0,
            "prior_capi_forward_requests_spent": manifest["approved_call_budget"]["prior_CAPI_forward_requests_spent"],
            "prior_capi_forwards_with_saved_outputs": manifest["approved_call_budget"]["prior_CAPI_forwards_with_saved_outputs"],
            "prior_completed_cpp_reference_forwards": manifest["approved_call_budget"]["prior_completed_direct_runtime_forwards"],
            "prior_fp64_ad_api_return_status": "returned_but_rc_and_output_not_persisted; status_unavailable",
            "global_positive_dt_forward_requests_if_campaign_completes": (
                manifest["approved_call_budget"]["prior_CAPI_forward_requests_spent"]
                + manifest["approved_call_budget"]["prior_completed_direct_runtime_forwards"]
                + 4 * len(results)),
            "global_capi_entry_calls_if_campaign_completes": (
                manifest["approved_call_budget"]["prior_CAPI_entries_spent"]
                + 7 * len(results) + 4),
            "preentry_ctypes_exception_count_in_preserved_prior_attempt": 1,
            "attempt_log_lines": sum(1 for _ in attempt_log_path.open("rb")),
            "host_steps": 0,
            "optimizer_calls": 0,
            "reference_note": "direct-runtime calls are separately receipt-pinned; refusals and dt=0 identity probes do not enter the physical kernel",
        },
        "limits": [
            "The fp64-value bridge is a research-only full-f64 value map from host-f32 stored inputs with float32 writeback; it is not a new f32-physics certification.",
            "The reported half-ULP estimate bounds final output storage rounding only; it is not physical budget closure or conservation certification.",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    with output_path.open("xb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True,
                        help="hash-pinned block34/block40/nonsquare input and reference artifacts")
    parser.add_argument("--manifest-sha256", required=True,
                        help="detached SHA-256 pin; avoids self-referential manifest hashes")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute-abi-tests", action="store_true",
                        help="explicitly authorizes DSO calls; omit for read-only preparation")
    args = parser.parse_args(argv)
    if not args.execute_abi_tests:
        raise PermissionError("no ABI calls were run; pass --execute-abi-tests only after root approval")
    report = execute_boundary_manifest(args.manifest, args.output,
                                       expected_manifest_sha256=args.manifest_sha256,
                                       allow_native_execution=True)
    print(json.dumps({"case_count": len(report["cases"]),
                      "all_default16": all(x["old_fp32_vs_new_default_all16_bitwise"] for x in report["cases"]),
                      "all_fp64_reference16": all(x["new_fp64_value_writeback_vs_direct_runtime_all16_bitwise"] for x in report["cases"]),
                      "output": args.output.name}, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
