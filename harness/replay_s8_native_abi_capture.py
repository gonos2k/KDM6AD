#!/usr/bin/env python3
"""Replay and verify the binary ABI-boundary capture from the S8 mp337 run."""

from __future__ import annotations

import argparse
import ctypes
import gzip
import hashlib
import io
import json
import struct
import sys
from dataclasses import dataclass
from pathlib import Path


STATE_NAMES = (
    "th", "qv", "qc", "qr", "qi", "qs", "qg", "nccn", "nc", "ni", "nr", "bg"
)
FORCING_NAMES = ("rho", "pii", "p", "delz")
INCREMENT_NAMES = ("rain_increment", "snow_increment", "graupel_increment")
RETURN_NAMES = STATE_NAMES + INCREMENT_NAMES + ("rhog",)
HOST_NAMES = STATE_NAMES + ("diag_rhog",)

# This replayer is intentionally bound to the one accepted private mp337 run.
# The byte hash protects the record framing and payload as a unit; the explicit
# fields below make the expected case/step contract reviewable without decoding
# 200 MiB of raw capture.
EXPECTED_CAPTURE_SHA256 = "ac543e94c6c9b9e5b3a099f6854c487a300dc3d6e568c3b5948599454d7801a6"
EXPECTED_CAPTURE_BYTES = 211804960
EXPECTED_COMPRESSED_SHA256 = "30b8be6e4d1e19d3517ec05cd5984e81b6b0d65e956bd7192f098cf6bedbccdb"
EXPECTED_COMPRESSED_BYTES = 59248645
EXPECTED_CALL_COUNT = 1
EXPECTED_DIMENSIONS = (232, 39, 139)
EXPECTED_STRUCT_SIZE = 336
EXPECTED_ABI_VERSION = 2
EXPECTED_DT = 20.0
EXPECTED_PHYSICS_VARIANT = 1
EXPECTED_VALUE_ONLY = 1
EXPECTED_CASE_ID = "LC05 retained 5 km full-domain case"
EXPECTED_CAPTURE_RUN_ID = "mp337_s8_mp337_capture3_0min20s_hist0_20260925_231740_p34969"
EXPECTED_CAPTURE_FORECAST_SHA256 = "14dbf6067f552c2e1fbda3d8317f1492eb61639657e5f304bde0457a7d6837d2"
EXPECTED_SAVED_TIMES = ("2025-07-19_00:00:00", "2025-07-19_00:00:20")


class StepV2Args(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("abi_version", ctypes.c_uint32),
        ("im", ctypes.c_int32),
        ("kme", ctypes.c_int32),
        ("jme", ctypes.c_int32),
        ("dt", ctypes.c_double),
        ("value_only", ctypes.c_int32),
        ("param_grad_flags", ctypes.c_int32),
        ("th", ctypes.c_void_p),
        ("qv", ctypes.c_void_p),
        ("qc", ctypes.c_void_p),
        ("qr", ctypes.c_void_p),
        ("qi", ctypes.c_void_p),
        ("qs", ctypes.c_void_p),
        ("qg", ctypes.c_void_p),
        ("nccn", ctypes.c_void_p),
        ("nc", ctypes.c_void_p),
        ("ni", ctypes.c_void_p),
        ("nr", ctypes.c_void_p),
        ("bg", ctypes.c_void_p),
        ("rho", ctypes.c_void_p),
        ("pii", ctypes.c_void_p),
        ("p", ctypes.c_void_p),
        ("delz", ctypes.c_void_p),
        ("th_out", ctypes.c_void_p),
        ("qv_out", ctypes.c_void_p),
        ("qc_out", ctypes.c_void_p),
        ("qr_out", ctypes.c_void_p),
        ("qi_out", ctypes.c_void_p),
        ("qs_out", ctypes.c_void_p),
        ("qg_out", ctypes.c_void_p),
        ("nccn_out", ctypes.c_void_p),
        ("nc_out", ctypes.c_void_p),
        ("ni_out", ctypes.c_void_p),
        ("nr_out", ctypes.c_void_p),
        ("bg_out", ctypes.c_void_p),
        ("handle", ctypes.POINTER(ctypes.c_void_p)),
        ("xland", ctypes.c_void_p),
        ("ncmin_land", ctypes.c_double),
        ("ncmin_sea", ctypes.c_double),
        ("rain_increment", ctypes.c_void_p),
        ("snow_increment", ctypes.c_void_p),
        ("graupel_increment", ctypes.c_void_p),
        ("rhog_out", ctypes.c_void_p),
        ("physics_variant", ctypes.c_uint32),
    ]


@dataclass
class Capture:
    struct_size: int
    abi_version: int
    im: int
    kme: int
    jme: int
    value_only: int
    param_grad_flags: int
    physics_variant: int
    dt: float
    ncmin_land: float
    ncmin_sea: float
    handle_before: int
    inputs: list[bytes]
    rc: int
    handle_after: int
    outputs: list[bytes]
    host_real_bytes: int
    host_outputs: list[bytes]


class Reader:
    def __init__(self, raw: bytes | io.BufferedIOBase):
        self.stream = io.BytesIO(raw) if isinstance(raw, bytes) else raw
        self.offset = 0
        self.digest = hashlib.sha256()
        self._pending = b""

    def take(self, size: int) -> bytes:
        chunks = [self._pending] if self._pending else []
        self._pending = b""
        have = sum(map(len, chunks))
        while have < size:
            chunk = self.stream.read(size - have)
            if not chunk:
                raise ValueError(f"truncated capture at byte {self.offset} (need {size})")
            chunks.append(chunk)
            have += len(chunk)
        out = b"".join(chunks)
        self.offset += size
        self.digest.update(out)
        return out

    def has_more(self) -> bool:
        if self._pending:
            return True
        self._pending = self.stream.read(1)
        return bool(self._pending)

    def unpack(self, fmt: str) -> tuple:
        size = struct.calcsize(fmt)
        return struct.unpack(fmt, self.take(size))


def big_endian_words_to_host(raw: bytes, word_bytes: int) -> bytes:
    if len(raw) % word_bytes:
        raise ValueError("captured array byte length is not a whole number of words")
    return b"".join(raw[i:i + word_bytes][::-1]
                    for i in range(0, len(raw), word_bytes))


def _parse_capture_records(
    raw: bytes | io.BufferedIOBase | Reader,
    *,
    expected_call_count: int,
    expected_dimensions: tuple[int, int, int],
) -> list[Capture]:
    reader = raw if isinstance(raw, Reader) else Reader(raw)
    captures = []
    for _ in range(expected_call_count):
        (magic, struct_size, abi_version, im, kme, jme, value_only,
         param_grad_flags, physics_variant, dt, ncmin_land, ncmin_sea,
         handle_before) = reader.unpack(">8s8i3di")
        if magic != b"S8BGIN01":
            raise ValueError(f"expected S8BGIN01 at record {len(captures)}, got {magic!r}")
        if min(im, kme, jme) <= 0:
            raise ValueError("capture has invalid dimensions")
        if (im, kme, jme) != expected_dimensions:
            raise ValueError(
                f"capture dimensions {(im, kme, jme)} differ from expected {expected_dimensions}"
            )
        n = im * kme * jme
        ncol = im * jme
        inputs = [reader.take(n * 4) for _ in range(16)] + [reader.take(ncol * 4)]

        magic, rc, handle_after = reader.unpack(">8sii")
        if magic != b"S8RETN01":
            raise ValueError(f"expected S8RETN01 at record {len(captures)}, got {magic!r}")
        outputs = [reader.take(n * 4) for _ in range(12)]
        outputs.extend(reader.take(ncol * 4) for _ in range(3))
        outputs.append(reader.take(n * 4))

        magic, host_real_bytes = reader.unpack(">8si")
        if magic != b"S8HOST01":
            raise ValueError(f"expected S8HOST01 at record {len(captures)}, got {magic!r}")
        host_outputs = [reader.take(n * host_real_bytes) for _ in range(13)]
        captures.append(Capture(
            struct_size, abi_version, im, kme, jme, value_only, param_grad_flags,
            physics_variant, dt, ncmin_land, ncmin_sea, handle_before, inputs,
            rc, handle_after, outputs, host_real_bytes, host_outputs,
        ))
    if reader.has_more():
        raise ValueError(
            f"capture contains more than {expected_call_count} ABI calls or trailing bytes"
        )
    if len(captures) != expected_call_count:
        raise ValueError(
            f"capture contains {len(captures)} ABI calls; expected exactly {expected_call_count}"
        )
    return captures


def validate_capture_schema(capture: Capture) -> None:
    n = capture.im * capture.kme * capture.jme
    ncol = capture.im * capture.jme
    expected_input_bytes = [n * 4] * 16 + [ncol * 4]
    expected_output_bytes = [n * 4] * 12 + [ncol * 4] * 3 + [n * 4]
    expected_host_bytes = [n * capture.host_real_bytes] * 13
    if len(capture.inputs) != len(STATE_NAMES) + len(FORCING_NAMES) + 1:
        raise ValueError("capture must contain exactly 17 typed f32 input fields")
    if len(capture.outputs) != len(RETURN_NAMES):
        raise ValueError("capture must contain exactly 16 typed f32 C return fields")
    if len(capture.host_outputs) != len(HOST_NAMES):
        raise ValueError("capture must contain exactly 13 typed host copyback fields")
    if [len(raw) for raw in capture.inputs] != expected_input_bytes:
        raise ValueError("capture input field lengths/types do not match the f32 ABI schema")
    if [len(raw) for raw in capture.outputs] != expected_output_bytes:
        raise ValueError("capture return field lengths/types do not match the f32 ABI schema")
    if capture.host_real_bytes != 4 or [len(raw) for raw in capture.host_outputs] != expected_host_bytes:
        raise ValueError("capture host copyback fields do not match the f32 host schema")


def parse_capture(path: Path) -> list[Capture]:
    compressed = path.suffix == ".gz"
    if compressed:
        compressed_bytes = path.stat().st_size
        if compressed_bytes != EXPECTED_COMPRESSED_BYTES:
            raise ValueError(
                f"compressed capture byte length {compressed_bytes} differs from pinned {EXPECTED_COMPRESSED_BYTES}"
            )
        if file_sha256(path) != EXPECTED_COMPRESSED_SHA256:
            raise ValueError("compressed capture SHA-256 differs from the pinned artifact")
        stream = gzip.open(path, "rb")
    else:
        if path.stat().st_size != EXPECTED_CAPTURE_BYTES:
            raise ValueError(
                f"capture byte length {path.stat().st_size} differs from pinned {EXPECTED_CAPTURE_BYTES}"
            )
        stream = path.open("rb")
    with stream:
        reader = Reader(stream)
        captures = _parse_capture_records(
            reader,
            expected_call_count=EXPECTED_CALL_COUNT,
            expected_dimensions=EXPECTED_DIMENSIONS,
        )
        if reader.offset != EXPECTED_CAPTURE_BYTES:
            raise ValueError(
                f"decoded capture byte length {reader.offset} differs from pinned {EXPECTED_CAPTURE_BYTES}"
            )
        if reader.digest.hexdigest() != EXPECTED_CAPTURE_SHA256:
            raise ValueError("decoded capture SHA-256 differs from the pinned capture")
    for capture in captures:
        if (capture.struct_size != EXPECTED_STRUCT_SIZE
                or capture.abi_version != EXPECTED_ABI_VERSION
                or capture.dt != EXPECTED_DT
                or capture.physics_variant != EXPECTED_PHYSICS_VARIANT
                or capture.value_only != EXPECTED_VALUE_ONLY):
            raise ValueError("capture ABI metadata differs from the pinned mp337 step contract")
        validate_capture_schema(capture)
    return captures


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def replay_one(lib: ctypes.CDLL, capture: Capture, index: int) -> dict:
    if sys.byteorder != "little":
        raise RuntimeError("the host ABI capture is little-endian; replay requires a little-endian host")
    if capture.value_only != 1 or capture.physics_variant != 1:
        raise ValueError("capture is not mp337's value_only=1, variant=1 call")
    if capture.rc != 0 or capture.handle_before != 0 or capture.handle_after != 0:
        raise ValueError("captured host call did not return OK with a null value-only handle")
    if capture.host_real_bytes != 4:
        raise ValueError(f"host copy-back precision is {capture.host_real_bytes} bytes, expected f32")

    array_f32 = ctypes.c_float * (capture.im * capture.kme * capture.jme)
    ncol = capture.im * capture.jme
    array_col = ctypes.c_float * ncol
    inputs = [array_f32.from_buffer_copy(big_endian_words_to_host(raw, 4))
              for raw in capture.inputs[:16]]
    xland = array_col.from_buffer_copy(big_endian_words_to_host(capture.inputs[16], 4))
    outputs = [array_f32() for _ in range(12)]
    increments = [array_col() for _ in range(3)]
    rhog = array_f32()
    handle = ctypes.c_void_p()

    args = StepV2Args()
    args.struct_size = lib.kdm6_step_v2_args_size_c()
    args.abi_version = lib.kdm6_get_abi_version_c()
    if args.struct_size != capture.struct_size or args.abi_version != capture.abi_version:
        raise ValueError("replay library ABI version/struct size differs from captured host call")
    args.im, args.kme, args.jme = capture.im, capture.kme, capture.jme
    args.dt = capture.dt
    args.value_only = capture.value_only
    args.param_grad_flags = capture.param_grad_flags
    input_fields = STATE_NAMES + FORCING_NAMES
    output_fields = tuple(name + "_out" for name in STATE_NAMES)
    for name, array in zip(input_fields, inputs):
        setattr(args, name, ctypes.cast(array, ctypes.c_void_p))
    for name, array in zip(output_fields, outputs):
        setattr(args, name, ctypes.cast(array, ctypes.c_void_p))
    args.handle = ctypes.pointer(handle)
    args.xland = ctypes.cast(xland, ctypes.c_void_p)
    args.ncmin_land = capture.ncmin_land
    args.ncmin_sea = capture.ncmin_sea
    args.rain_increment = ctypes.cast(increments[0], ctypes.c_void_p)
    args.snow_increment = ctypes.cast(increments[1], ctypes.c_void_p)
    args.graupel_increment = ctypes.cast(increments[2], ctypes.c_void_p)
    args.rhog_out = ctypes.cast(rhog, ctypes.c_void_p)
    args.physics_variant = capture.physics_variant

    rc = lib.kdm6_step_v2_c(ctypes.byref(args))
    if rc != 0 or handle.value is not None:
        raise RuntimeError(f"replay call {index} returned rc={rc}, handle={handle.value}")
    replay_outputs = [ctypes.string_at(array, ctypes.sizeof(array)) for array in outputs]
    replay_outputs.extend(ctypes.string_at(array, ctypes.sizeof(array)) for array in increments)
    replay_outputs.append(ctypes.string_at(rhog, ctypes.sizeof(rhog)))

    mismatches = []
    for name, replay_raw, captured_raw in zip(RETURN_NAMES, replay_outputs, capture.outputs):
        captured_host_order = big_endian_words_to_host(captured_raw, 4)
        if replay_raw != captured_host_order:
            first = next(i for i, (a, b) in enumerate(zip(replay_raw, captured_host_order)) if a != b)
            mismatches.append({"field": name, "first_byte": first,
                               "replay_sha256": sha256(replay_raw),
                               "captured_sha256": sha256(captured_raw)})
    copyback_mismatches = []
    for name, captured_raw, host_raw in zip(STATE_NAMES, capture.outputs[:12], capture.host_outputs[:12]):
        captured_host_order = big_endian_words_to_host(captured_raw, 4)
        host_host_order = big_endian_words_to_host(host_raw, capture.host_real_bytes)
        if captured_host_order != host_host_order:
            first = next(i for i, (a, b) in enumerate(zip(captured_host_order, host_host_order)) if a != b)
            copyback_mismatches.append({"field": name, "first_byte": first})
    rhog_capture = big_endian_words_to_host(capture.outputs[15], 4)
    rhog_host = big_endian_words_to_host(capture.host_outputs[12], capture.host_real_bytes)
    if rhog_capture != rhog_host:
        first = next(i for i, (a, b) in enumerate(zip(rhog_capture, rhog_host)) if a != b)
        copyback_mismatches.append({"field": "diag_rhog", "first_byte": first})

    return {
        "call_index": index,
        "abi_version": capture.abi_version,
        "struct_size": capture.struct_size,
        "dimensions_im_kme_jme": [capture.im, capture.kme, capture.jme],
        "dt": capture.dt,
        "value_only": capture.value_only,
        "physics_variant": capture.physics_variant,
        "captured_rc": capture.rc,
        "captured_handle_before_after": [capture.handle_before, capture.handle_after],
        "input_sha256": {name: sha256(raw) for name, raw in zip(STATE_NAMES + FORCING_NAMES + ("xland",), capture.inputs)},
        "return_sha256": {name: sha256(raw) for name, raw in zip(RETURN_NAMES, capture.outputs)},
        "replay_matches_capture": not mismatches,
        "copyback_matches_capture": not copyback_mismatches,
        "replay_mismatches": mismatches,
        "copyback_mismatches": copyback_mismatches,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture", type=Path)
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    lib = ctypes.CDLL(str(args.library))
    lib.kdm6_get_abi_version_c.argtypes = []
    lib.kdm6_get_abi_version_c.restype = ctypes.c_int
    lib.kdm6_step_v2_args_size_c.argtypes = []
    lib.kdm6_step_v2_args_size_c.restype = ctypes.c_uint32
    lib.kdm6_step_v2_c.argtypes = [ctypes.POINTER(StepV2Args)]
    lib.kdm6_step_v2_c.restype = ctypes.c_int

    captures = parse_capture(args.capture)
    if not captures:
        raise SystemExit("capture file contains no ABI calls")
    results = [replay_one(lib, cap, i) for i, cap in enumerate(captures)]
    payload = {
        "capture": str(args.capture),
        "capture_sha256": EXPECTED_CAPTURE_SHA256,
        "capture_byte_length": EXPECTED_CAPTURE_BYTES,
        "capture_artifact_sha256": file_sha256(args.capture),
        "capture_artifact_byte_length": args.capture.stat().st_size,
        "case_identity": {
            "case_id": EXPECTED_CASE_ID,
            "run_id": EXPECTED_CAPTURE_RUN_ID,
            "selected_call_dimensions_im_kme_jme": list(EXPECTED_DIMENSIONS),
            "dt_seconds": EXPECTED_DT,
            "saved_times": list(EXPECTED_SAVED_TIMES),
            "forecast_sha256": EXPECTED_CAPTURE_FORECAST_SHA256,
            "authentication": (
                "provenance association to private run receipts; those receipts "
                "are not included or authenticated by this public arithmetic replay"
            ),
        },
        "capture_manifest": {
            "byte_length": EXPECTED_CAPTURE_BYTES,
            "expected_call_count": EXPECTED_CALL_COUNT,
            "field_counts": {
                "inputs_f32": 17,
                "c_returns_f32": 16,
                "host_copyback_f32": 13,
            },
        },
        "library": str(args.library),
        "library_sha256": sha256(args.library.read_bytes()),
        "call_count": len(results),
        "calls": results,
        "pass": all(call["replay_matches_capture"] and call["copyback_matches_capture"] for call in results),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not payload["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
