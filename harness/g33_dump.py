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
import json
import struct
from pathlib import Path

MAGIC = b"KDG33OP\n"
FORMAT_VERSION = 1
_REC = b"REC1"
_FOOT = b"FOOT"

# dtype code -> (element byte width, struct pack/unpack of the NATIVE bits as an
# unsigned big-endian integer). f32/f64 are stored as their raw uint bit pattern
# so native-precision differences survive (never pre-rounded — §2).
_DTYPES = {"f32": 4, "f64": 8, "i32": 4, "u8": 1}


class G33Corruption(Exception):
    """Raised by G33Reader on ANY fail-closed rejection."""


def _u32(x: int) -> bytes:
    return struct.pack("<I", x)


def _read_u32(buf: bytes, off: int) -> tuple[int, int]:
    if off + 4 > len(buf):
        raise G33Corruption("truncated: u32 past end of file")
    return struct.unpack_from("<I", buf, off)[0], off + 4


def _parse_json(raw: bytes, what: str):
    # a fail-closed reader NEVER leaks a raw decode/JSON error — corrupt bytes in
    # any JSON block are a G33Corruption, not an unhandled traceback.
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise G33Corruption(f"corrupt {what} JSON: {e}") from None


def pack_payload(dtype: str, values) -> bytes:
    """Native-width big-endian raw bits for a flat list of values.
    f32/f64 keep their exact bit pattern; i32 two's-complement; u8 a byte."""
    if dtype not in _DTYPES:
        raise ValueError(f"unknown dtype {dtype!r}")
    if dtype == "f32":
        return b"".join(struct.pack(">I", struct.unpack("<I", struct.pack("<f", float(v)))[0]) for v in values)
    if dtype == "f64":
        return b"".join(struct.pack(">Q", struct.unpack("<Q", struct.pack("<d", float(v)))[0]) for v in values)
    if dtype == "i32":
        return b"".join(struct.pack(">i", int(v)) for v in values)
    return bytes(int(v) & 0xFF for v in values)  # u8


class G33Writer:
    """Fail-closed container writer (§7e). Writes .tmp, then atomic rename on
    finalize(); NEVER writes the COMPLETE footer from atexit/destructor."""

    def __init__(self, path, header: dict):
        self.path = Path(path)
        self.tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        if self.path.exists():
            raise G33Corruption(f"refuse to overwrite existing container {self.path}")
        if self.tmp.exists():
            raise G33Corruption(f"stale .tmp present (crashed/concurrent writer?): {self.tmp}")
        required = {"producer_commit", "binary_sha256", "case_id", "pair_id",
                    "backend", "algorithm", "B", "K", "column_layout_id",
                    "column_index_map", "canonical_k_order", "run_uuid",
                    "process_id", "owner_thread_id", "record_count_expected"}
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
        if self._seen_seq and seq <= max(self._seen_seq):
            raise G33Corruption(f"non-monotone seq_no {seq} (<= {max(self._seen_seq)})")
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
        self._f.close()
        self.tmp.replace(self.path)  # atomic
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


def read_container(path) -> dict:
    """Parse + FAIL-CLOSED validate a container. Returns
    {header, records:[{key.., payload:bytes}], footer}. Raises G33Corruption."""
    buf = Path(path).read_bytes()
    if buf[:8] != MAGIC:
        raise G33Corruption("bad magic (not a KDG33OP container)")
    off = 8
    ver, off = _read_u32(buf, off)
    if ver != FORMAT_VERSION:
        raise G33Corruption(f"format_version {ver} != {FORMAT_VERSION}")
    hlen, off = _read_u32(buf, off)
    if off + hlen > len(buf):
        raise G33Corruption("truncated header")
    header = _parse_json(buf[off:off + hlen], "header"); off += hlen

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
        klen, off = _read_u32(buf, off)
        if off + klen > len(buf):
            raise G33Corruption("truncated record key")
        key = _parse_json(buf[off:off + klen], "record key"); off += klen
        plen, off = _read_u32(buf, off)
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
            n_elem *= int(s)
        if plen != n_elem * _DTYPES[dtype]:
            raise G33Corruption(f"record payload {plen} != {n_elem}*{_DTYPES[dtype]}")
        seq = key.get("seq_no")
        if not isinstance(seq, int):
            raise G33Corruption("record missing integer seq_no")
        if seq in seen_seq:
            raise G33Corruption(f"duplicate seq_no {seq}")
        seen_seq.add(seq)
        payload_hash.update(payload)
        records.append({**key, "payload": payload})

    if not footer or footer.get("complete") is not True:
        raise G33Corruption("missing/incomplete COMPLETE footer")
    if footer.get("record_count_actual") != len(records):
        raise G33Corruption(
            f"footer record_count_actual {footer.get('record_count_actual')} != {len(records)} parsed")
    if footer.get("payload_sha256") != payload_hash.hexdigest():
        raise G33Corruption("payload_sha256 mismatch (corrupt/tampered payloads)")
    return {"header": header, "records": records, "footer": footer}


def verify_attestation(header: dict, attestation: dict) -> None:
    """§7d: a container's self-reported provenance is trusted ONLY when it agrees
    with the harness-computed run_attestation. Raises G33Corruption on any drift."""
    for field in ("producer_commit", "binary_sha256", "case_id", "pair_id",
                  "backend", "algorithm"):
        want = attestation.get(field)
        got = header.get(field)
        if want is None:
            raise G33Corruption(f"attestation missing {field}")
        if got != want:
            raise G33Corruption(f"provenance drift on {field}: header={got!r} attestation={want!r}")
