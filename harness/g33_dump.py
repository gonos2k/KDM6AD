#!/usr/bin/env python3
"""G3.3-M op-provenance dump container — Python reference writer/reader.

Format `KDG33OP` v1 (see docs/C4_G3_3_OP_PROVENANCE_PROTOCOL.md §7). A single,
self-verifying binary container per (case, backend). Layout — all ints little-
endian u32, all JSON utf-8, all PAYLOADS raw NATIVE-width bits (real32→uint32,
real64→uint64, int32→int32, logical→uint8), each element big-endian, flattened
row-major in the DECLARED canonical-k order:

    magic  b"KDG33OP\\n"                (8)
    format_version                      (u32)
    header_json_len, header_json        (u32, utf-8)
    record*  {  b"REC1"                 (u32 sentinel 0x31434552)
                key_json_len, key_json  (u32, utf-8)
                payload_len, payload }  (u32, raw native BE bits)
    footer  b"FOOT"                     (u32 sentinel 0x544f4f46)
            footer_json_len, footer_json(u32, utf-8)

The reader is FAIL-CLOSED: any structural, provenance, completeness, dtype/shape,
sha, or degeneracy violation raises G33Corruption. Completeness against the
INDEPENDENT expectation manifest (g33_expectation.py) is checked by the
comparator, NOT here — the header's record_count_expected is informational only.

The writer is used by the Python synthetic tests; the C++/Fortran diagnostic
overlays emit the identical byte layout (helpers land with steps 6/11).
"""
from __future__ import annotations

import hashlib
import math
import json
import os
import re
import struct
from pathlib import Path

_SAFE_ID = re.compile(r"^[A-Za-z0-9_.-]+$")   # no path separators, no ".."

MAGIC = b"KDG33OP\n"
FORMAT_VERSION = 2
_REC = b"REC1"
_FOOT = b"FOOT"

# dtype code -> (element byte width, struct pack/unpack of the NATIVE bits as an
# unsigned big-endian integer). f32/f64 are stored as their raw uint bit pattern
# so native-precision differences survive (never pre-rounded — §2).
_DTYPES = {"f32": 4, "f64": 8, "i32": 4, "u8": 1}

# Resource bounds (P1-8). A corrupt length field must not turn a local evidence
# file into an unbounded allocation or a multi-minute parse.
MAX_FILE_BYTES = 512 * 1024 * 1024
MAX_HEADER_BYTES = 1 * 1024 * 1024
MAX_KEY_BYTES = 64 * 1024
MAX_PAYLOAD_BYTES = 64 * 1024 * 1024
MAX_RECORDS = 2_000_000
MAX_B = 100_000
MAX_K = 10_000
MAX_ELEMS = 64 * 1024 * 1024

# branch-selection enum (P0-6): a bare boolean hides a TIE, where both backends
# produce the SAME value from DIFFERENT branch semantics — exactly the case a
# first-divergence gate must not blur.
BRANCH_LEFT_SELECTED = 0
BRANCH_RIGHT_SELECTED = 1
BRANCH_TIE = 2
BRANCH_VALUES = (0, 1, 2)


class G33Corruption(Exception):
    """Raised by G33Reader on ANY fail-closed rejection."""


def _u32(x: int) -> bytes:
    return struct.pack("<I", x)


def _read_u32(buf: bytes, off: int) -> tuple[int, int]:
    if off + 4 > len(buf):
        raise G33Corruption("truncated: u32 past end of file")
    return struct.unpack_from("<I", buf, off)[0], off + 4


def _no_dup_keys(pairs):
    # json.loads keeps the LAST duplicate key, so a value injected through an
    # unescaped string ("...","producer_commit":"forged") would silently override
    # the attested one. Duplicate keys are corruption, not a merge.
    seen = {}
    for k, v in pairs:
        if k in seen:
            raise G33Corruption(f"duplicate JSON key {k!r} (injection or corruption)")
        seen[k] = v
    return seen


def _parse_json(raw: bytes, what: str):
    # a fail-closed reader NEVER leaks a raw decode/JSON error — corrupt bytes in
    # any JSON block are a G33Corruption, not an unhandled traceback.
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_no_dup_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise G33Corruption(f"corrupt {what} JSON: {e}") from None


def pack_payload_bits(dtype: str, bits) -> bytes:
    """AUTHORITATIVE raw-bit packer: `bits` are the exact unsigned bit patterns.

    The value-based helper below routes through a Python float, which can quiet a
    signaling NaN and canonicalise distinct NaN payloads — while the C++ writer
    memcpy's the true pattern. Anything that must reproduce a backend's bits
    EXACTLY (NaN payloads, signalling NaN, raw-bit fixtures) must use this path.
    """
    if dtype not in _DTYPES:
        raise ValueError(f"unknown dtype {dtype!r}")
    w = _DTYPES[dtype]
    fmt = {4: ">I", 8: ">Q", 1: ">B"}[w]
    lim = (1 << (8 * w)) - 1
    out = []
    for b in bits:
        b = int(b)
        if not 0 <= b <= lim:
            raise ValueError(f"bit pattern {b!r} out of range for {dtype}")
        out.append(struct.pack(fmt, b))
    return b"".join(out)


def unpack_payload_bits(dtype: str, payload: bytes) -> list:
    """Inverse of pack_payload_bits: the exact unsigned bit patterns, as written.

    Symmetric to the packer for the same reason — decoding to Python floats to
    compare would canonicalise NaN payloads on the READ side, so two backends
    disagreeing only in a NaN mantissa would compare equal. A first-divergence
    gate cannot afford that: the raw view is the comparison, not a debug aid.
    """
    if dtype not in _DTYPES:
        raise ValueError(f"unknown dtype {dtype!r}")
    w = _DTYPES[dtype]
    if len(payload) % w:
        raise G33Corruption(f"payload of {len(payload)} bytes is not a multiple of {w}")
    fmt = {4: ">I", 8: ">Q", 1: ">B"}[w]
    return [struct.unpack(fmt, payload[i:i + w])[0] for i in range(0, len(payload), w)]


def decode_exact_integers(dtype: str, payload: bytes):
    """Decode a float payload to integers, reporting which values are EXACT.

    Returns (values, exact_flags). A value is exact when the float is integral
    to the bit — 2.0000002 decodes to 2 like 2.0 does, and int32(2) cannot tell
    them apart, which is precisely the confusion this gate exists to detect.
    """
    if dtype not in ("f32", "f64"):
        raise ValueError(f"decode_exact_integers needs a float dtype, got {dtype}")
    fmt = ">f" if dtype == "f32" else ">d"
    w = _DTYPES[dtype]
    if len(payload) % w:
        raise G33Corruption(f"payload of {len(payload)} bytes is not a multiple of {w}")
    vals, exact = [], []
    for i in range(0, len(payload), w):
        v = struct.unpack(fmt, payload[i:i + w])[0]
        ok = math.isfinite(v) and float(v).is_integer()
        vals.append(int(v) if ok else None)
        exact.append(ok)
    return vals, exact


def derive_mstepmax(dtype: str, mstep_native_payload: bytes) -> int:
    """mstepmax, DERIVED offline from the raw mstep bits.

    mstepmax is max_b(mstep_b), so the comparator can compute it from evidence
    the producer already emits. Dumping it from the producer would have required
    naming `int /*mstepmax*/`, an unnamed production parameter — a production
    edit for a value that is not independent of what is already recorded. This
    is also the stronger arrangement: a producer that reports both an operand
    and a summary OF that operand is attesting to its own arithmetic.
    """
    vals, exact = decode_exact_integers(dtype, mstep_native_payload)
    if not vals:
        raise G33Corruption("empty mstep_native payload")
    if not all(exact):
        raise G33Corruption(
            "mstep_native contains a non-integral value — mstepmax cannot be "
            "derived from a substep count that is not exactly an integer")
    return max(vals)


def pack_payload(dtype: str, values) -> bytes:
    """CONVENIENCE packer from Python values (tests/fixtures).

    f32/f64 go through a Python float, so an exotic NaN payload may be
    canonicalised — use pack_payload_bits() when the exact pattern matters.
    """
    if dtype not in _DTYPES:
        raise ValueError(f"unknown dtype {dtype!r}")
    # `>f` / `>d` already emit the big-endian IEEE-754 bit pattern, so the old
    # pack-LE -> unpack-int -> pack-BE roundtrip was redundant. Verified
    # byte-identical across zero, -0.0, subnormals, min/max normal, inf and nan.
    if dtype == "f32":
        return b"".join(struct.pack(">f", float(v)) for v in values)
    if dtype == "f64":
        return b"".join(struct.pack(">d", float(v)) for v in values)
    if dtype == "i32":
        return b"".join(struct.pack(">i", int(v)) for v in values)
    return bytes(int(v) & 0xFF for v in values)  # u8


class G33Writer:
    """Fail-closed container writer (§7e). Writes .tmp, then atomic rename on
    finalize(); NEVER writes the COMPLETE footer from atexit/destructor."""

    def __init__(self, path, header: dict):
        _validate_header(header)
        self.path = Path(path)
        self.tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        if self.path.exists():
            raise G33Corruption(f"refuse to overwrite existing container {self.path}")
        if self.tmp.exists():
            raise G33Corruption(f"stale .tmp present (crashed/concurrent writer?): {self.tmp}")
        required = {"producer_commit", "binary_sha256", "case_id", "pair_id",
                    "backend", "algorithm", "B", "K", "column_layout_id",
                    "column_index_map", "canonical_k_order", "run_uuid",
                    "process_id", "owner_thread_id", "record_count_expected",
                    "container_id", "global_op_seq_start", "global_op_seq_end"}
        missing = required - set(header)
        if missing:
            raise G33Corruption(f"header missing fields: {sorted(missing)}")
        self.header = dict(header)
        self._f = open(self.tmp, "wb")
        self._f.write(MAGIC)
        self._f.write(_u32(FORMAT_VERSION))
        hj = json.dumps(self.header, sort_keys=True).encode("utf-8")
        self._f.write(_u32(len(hj)))
        self._f.write(hj)
        self._payload_hash = hashlib.sha256()
        self._n = 0
        self._seen_seq: set[int] = set()
        self._last_osi = None
        self._finalized = False

    def record(self, key: dict, dtype: str, shape, payload: bytes) -> None:
        if self._finalized:
            raise G33Corruption("record() after finalize()")
        if dtype not in _DTYPES:
            raise G33Corruption(f"record dtype {dtype!r} unknown")
        seq = key.get("seq_no")
        if not isinstance(seq, int):
            raise G33Corruption("record key missing integer seq_no")
        if seq in self._seen_seq:
            raise G33Corruption(f"duplicate seq_no {seq}")
        if seq != self._n:
            raise G33Corruption(f"seq_no {seq} out of order (expected {self._n})")
        osi = key.get("op_seq_id")
        if isinstance(osi, bool) or not isinstance(osi, int) or osi < 0:
            raise G33Corruption("record key missing integer op_seq_id (v2 requires it)")
        if self._last_osi is not None and osi <= self._last_osi:
            raise G33Corruption(f"op_seq_id {osi} is not strictly increasing")
        # The declared window is enforced HERE as well as in the reader. Writer-side
        # is what makes it a fail-fast: a run whose containers execute out of the
        # declared order stops at the first offending record instead of completing
        # and leaving the contradiction to be found (or not) at read time.
        lo, hi = self.header["global_op_seq_start"], self.header["global_op_seq_end"]
        if not (lo <= osi <= hi):
            raise G33Corruption(
                f"op_seq_id {osi} outside the declared window [{lo}, {hi}] — the "
                f"container executed outside its run_index-declared position")
        self._last_osi = osi
        n_elem = 1
        for s in shape:
            n_elem *= int(s)
        if len(payload) != n_elem * _DTYPES[dtype]:
            raise G33Corruption(
                f"payload size {len(payload)} != {n_elem}*{_DTYPES[dtype]} for shape {shape} dtype {dtype}")
        kj = json.dumps({**key, "dtype": dtype, "shape": list(shape),
                         "payload_size": len(payload)}, sort_keys=True).encode("utf-8")
        self._f.write(_REC)
        self._f.write(_u32(len(kj)))
        self._f.write(kj)
        self._f.write(_u32(len(payload)))
        self._f.write(payload)
        self._payload_hash.update(payload)
        self._seen_seq.add(seq)
        self._n += 1

    def finalize(self) -> None:
        if self._finalized:
            raise G33Corruption("double finalize()")
        footer = {"record_count_actual": self._n,
                  "payload_sha256": self._payload_hash.hexdigest(),
                  "complete": True}
        fj = json.dumps(footer, sort_keys=True).encode("utf-8")
        self._f.write(_FOOT)
        self._f.write(_u32(len(fj)))
        self._f.write(fj)
        self._f.flush()
        os.fsync(self._f.fileno())
        self._f.close()
        # §7a: .tmp -> flush/close -> VERIFY -> atomic rename. The verify step was
        # missing: a short write (disk full — a known hazard on this host) would
        # otherwise be PUBLISHED to the final path and the .tmp evidence deleted.
        # Re-parse the closed temp file with the same fail-closed reader used by
        # consumers; only a container that already reads as valid may be published.
        try:
            read_container(self.tmp)
        except G33Corruption as e:
            raise G33Corruption(
                f"post-close verification failed, refusing to publish {self.path} "
                f"(.tmp kept for inspection): {e}") from None
        # Publish atomically WITHOUT clobbering (matches the C++ writer): os.link
        # fails with FileExistsError if the final path was created concurrently
        # after our constructor's no-overwrite check — never destroy another
        # writer's completed container (Path.replace/os.rename would clobber it).
        try:
            os.link(self.tmp, self.path)
        except FileExistsError:
            raise G33Corruption(
                f"refuse to clobber concurrently-created {self.path} (.tmp kept)") from None
        os.unlink(self.tmp)
        self._finalized = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_):
        # On an exception the .tmp is abandoned WITHOUT a footer — never a
        # silently-complete container. Explicit finalize() is the only success.
        if not self._finalized:
            try:
                self._f.close()
            except Exception:
                pass
        return False


def _validate_header(header: dict) -> None:
    """Header schema, shared by BOTH the writer and the reader.

    It lived inline in read_container(), so the WRITER accepted anything: a
    string/bool/negative process_id, a column map with duplicate or out-of-range
    entries — all produced a container that only failed later at read time, or
    never, if nothing read it back. Validating where the bytes are PRODUCED is
    what makes an invalid container impossible rather than merely detectable.
    """
    # v2 schema. process_id is an INT: the C++ overlay emits getpid() as a JSON
    # number, so requiring a string made every REAL overlay container unreadable
    # (the standalone C++ test used "1" and masked it). container_id and the
    # global op_seq range are new in v2 — they tie a per-substep container back to
    # the independent run index.
    _required = {"producer_commit": str, "binary_sha256": str, "case_id": str,
                 "pair_id": str, "backend": str, "algorithm": str,
                 "B": int, "K": int, "column_layout_id": str,
                 "column_index_map": list, "canonical_k_order": str,
                 "run_uuid": str, "process_id": int, "owner_thread_id": str,
                 "container_id": str, "descriptor_sha256": str,
                 "resolved_binary_path": str, "resolved_binary_sha256": str,
                 "global_op_seq_start": int, "global_op_seq_end": int}
    for _k, _t in _required.items():
        if _k not in header:
            raise G33Corruption(f"header missing required field {_k!r}")
        if isinstance(header[_k], bool) or not isinstance(header[_k], _t):
            raise G33Corruption(
                f"header field {_k!r} has type {type(header[_k]).__name__}, expected {_t.__name__}")
    if header["process_id"] < 0:
        raise G33Corruption(f"negative process_id {header['process_id']}")
    if header["backend"] not in ("cpp", "fortran"):
        raise G33Corruption(f"unknown backend {header['backend']!r}")
    if header["algorithm"] not in ("legacy", "conservative"):
        raise G33Corruption(f"unknown algorithm {header['algorithm']!r}")
    if not re.fullmatch(r"[0-9a-f]{64}", header["descriptor_sha256"]):
        raise G33Corruption("descriptor_sha256 is not a sha256 hex digest")
    if not re.fullmatch(r"[0-9a-f]{64}", header["resolved_binary_sha256"]):
        raise G33Corruption("resolved_binary_sha256 is not a sha256 hex digest")
    # The producer refuses this mismatch at run time; requiring it here as well
    # closes the other producers — a hand-built container, or a writer that
    # never resolved anything and echoed the sealed value it was given.
    if header["resolved_binary_sha256"] != header["binary_sha256"]:
        raise G33Corruption(
            "resolved_binary_sha256 does not match the sealed binary_sha256 — "
            "the container was produced by a binary the evidence does not describe")
    if not header["resolved_binary_path"]:
        raise G33Corruption("empty resolved_binary_path")
    if not _SAFE_ID.match(header["container_id"]):
        raise G33Corruption(f"container_id {header['container_id']!r} is not a safe id")
    if not (1 <= header["B"] <= MAX_B) or not (1 <= header["K"] <= MAX_K):
        raise G33Corruption(f"out-of-range dims B={header['B']} K={header['K']}")
    if header["global_op_seq_start"] < 0 or header["global_op_seq_end"] < header["global_op_seq_start"]:
        raise G33Corruption("invalid global_op_seq range")
    _validate_column_map(header["column_index_map"], header["B"])


def read_container(path) -> dict:
    """Parse + FAIL-CLOSED validate a container. Returns
    {header, records:[{key.., payload:bytes}], footer}. Raises G33Corruption."""
    _p = Path(path)
    if _p.stat().st_size > MAX_FILE_BYTES:
        raise G33Corruption(f"container exceeds MAX_FILE_BYTES ({MAX_FILE_BYTES})")
    buf = _p.read_bytes()
    if buf[:8] != MAGIC:
        raise G33Corruption("bad magic (not a KDG33OP container)")
    off = 8
    ver, off = _read_u32(buf, off)
    if ver != FORMAT_VERSION:
        raise G33Corruption(f"format_version {ver} != {FORMAT_VERSION}")
    hlen, off = _read_u32(buf, off)
    if hlen > MAX_HEADER_BYTES:
        raise G33Corruption(f"header length {hlen} exceeds MAX_HEADER_BYTES")
    if off + hlen > len(buf):
        raise G33Corruption("truncated header")
    header = _parse_json(buf[off:off + hlen], "header"); off += hlen
    if not isinstance(header, dict):
        raise G33Corruption("header is not a JSON object")
    _validate_header(header)

    records = []
    payload_hash = hashlib.sha256()
    seen_seq: set[int] = set()
    footer = None
    while True:
        if off + 4 > len(buf):
            raise G33Corruption("truncated before footer (no COMPLETE marker)")
        marker = buf[off:off + 4]; off += 4
        if marker == _FOOT:
            flen, off = _read_u32(buf, off)
            if off + flen != len(buf):
                raise G33Corruption("footer length does not reach EOF (trailing/again bytes)")
            footer = _parse_json(buf[off:off + flen], "footer"); off += flen
            break
        if marker != _REC:
            raise G33Corruption(f"bad record/footer sentinel {marker!r}")
        if len(records) >= MAX_RECORDS:
            raise G33Corruption(f"record count exceeds MAX_RECORDS ({MAX_RECORDS})")
        klen, off = _read_u32(buf, off)
        if klen > MAX_KEY_BYTES:
            raise G33Corruption(f"record key length {klen} exceeds MAX_KEY_BYTES")
        if off + klen > len(buf):
            raise G33Corruption("truncated record key")
        key = _parse_json(buf[off:off + klen], "record key"); off += klen
        plen, off = _read_u32(buf, off)
        if plen > MAX_PAYLOAD_BYTES:
            raise G33Corruption(f"record payload length {plen} exceeds MAX_PAYLOAD_BYTES")
        if off + plen > len(buf):
            raise G33Corruption("truncated record payload")
        payload = buf[off:off + plen]; off += plen
        if key.get("payload_size") != plen:
            raise G33Corruption(f"record payload_size {key.get('payload_size')} != actual {plen}")
        dtype = key.get("dtype"); shape = key.get("shape")
        if dtype not in _DTYPES or not isinstance(shape, list):
            raise G33Corruption("record missing/invalid dtype or shape")
        n_elem = 1
        for s in shape:
            # reject 0 and bool too: a zero dim makes an EMPTY payload "valid",
            # which is a degenerate record the completeness check cannot see.
            if isinstance(s, bool) or not isinstance(s, int) or s < 1:
                raise G33Corruption(f"record shape element {s!r} is not a positive int")
            n_elem *= s
            if n_elem > MAX_ELEMS:                      # checked multiplication
                raise G33Corruption(f"record shape {shape} exceeds MAX_ELEMS")
        if plen != n_elem * _DTYPES[dtype]:
            raise G33Corruption(f"record payload {plen} != {n_elem}*{_DTYPES[dtype]}")
        seq = key.get("seq_no")
        if isinstance(seq, bool) or not isinstance(seq, int):
            raise G33Corruption("record missing integer seq_no")
        # v2: seq_no must be EXACTLY contiguous from 0. Rejecting only duplicates
        # let records be reordered or a gap left behind while the logical-key
        # multiset still matched — and a comparator that reads file order as
        # "first-divergence order" would then be reading a lie.
        if seq != len(records):
            raise G33Corruption(f"seq_no {seq} out of order (expected {len(records)})")
        seen_seq.add(seq)
        osi = key.get("op_seq_id")
        if isinstance(osi, bool) or not isinstance(osi, int) or osi < 0:
            raise G33Corruption(f"record {seq} missing integer op_seq_id (v2 requires it)")
        if not (header["global_op_seq_start"] <= osi <= header["global_op_seq_end"]):
            raise G33Corruption(
                f"record {seq} op_seq_id {osi} outside the header range "
                f"[{header['global_op_seq_start']}, {header['global_op_seq_end']}]")
        if records and osi <= records[-1]["op_seq_id"]:
            raise G33Corruption(f"op_seq_id {osi} is not strictly increasing")
        payload_hash.update(payload)
        records.append({**key, "payload": payload})

    if not isinstance(footer, dict):
        raise G33Corruption("footer is not a JSON object")
    if footer.get("complete") is not True:
        raise G33Corruption("missing/incomplete COMPLETE footer")
    if footer.get("record_count_actual") != len(records):
        raise G33Corruption(
            f"footer record_count_actual {footer.get('record_count_actual')} != {len(records)} parsed")
    if footer.get("payload_sha256") != payload_hash.hexdigest():
        raise G33Corruption("payload_sha256 mismatch (corrupt/tampered payloads)")
    return {"header": header, "records": records, "footer": footer}


def _validate_column_map(cmap, B: int) -> None:
    """Full structural check. Length alone let malformed maps through: duplicate
    B_index, duplicate Fortran (i,j), missing/duplicate cpp_flat_index, wrong
    field count or type, out-of-range values — any of which silently mis-pairs
    Fortran and C++ columns in the comparator."""
    if len(cmap) != B:
        raise G33Corruption(f"column_index_map has {len(cmap)} entries, expected B={B}")
    b_idx, cpp_idx, fij = [], [], []
    for e in cmap:
        if not isinstance(e, list) or len(e) != 4:
            raise G33Corruption(f"column_index_map entry {e!r} must be [B_index, i, j, cpp_flat]")
        for x in e:
            if isinstance(x, bool) or not isinstance(x, int) or x < 0:
                raise G33Corruption(f"column_index_map entry {e!r} has a non-int/negative field")
        b_idx.append(e[0]); fij.append((e[1], e[2])); cpp_idx.append(e[3])
    if sorted(b_idx) != list(range(B)):
        raise G33Corruption("column_index_map B_index is not a 0..B-1 permutation")
    if sorted(cpp_idx) != list(range(B)):
        raise G33Corruption("column_index_map cpp_flat_index is not a 0..B-1 permutation")
    if len(set(fij)) != B:
        raise G33Corruption("column_index_map Fortran (i,j) pairs are not unique")


def verify_attestation(header: dict, attestation: dict) -> None:
    """§7d: a container's self-reported provenance is trusted ONLY when it agrees
    with the harness-computed run_attestation. Raises G33Corruption on any drift."""
    for field in ("producer_commit", "binary_sha256", "case_id", "pair_id",
                  "backend", "algorithm", "run_uuid"):
        want = attestation.get(field)
        got = header.get(field)
        if want is None:
            raise G33Corruption(f"attestation missing {field}")
        if got != want:
            raise G33Corruption(f"provenance drift on {field}: header={got!r} attestation={want!r}")
