"""Blocked research ABI reader; successful copying does not establish coverage."""

import ctypes as C
import math
import struct

LIMIT = 2_000_000
NO_CAUSE = (1 << 64) - 1


class Meta(C.Structure):
    _fields_ = (
        [("abi_version", C.c_uint32), ("struct_size", C.c_uint32)]
        + [
            (name, C.c_char * size)
            for name, size in (
                ("input_id", 128),
                ("mode", 32),
                ("family", 32),
                ("stage", 64),
                ("field", 64),
                ("source_hook", 128),
            )
        ]
        + [
            (name, C.c_uint64)
            for name in (
                "context_epoch",
                "runtime_call",
                "one_step_call",
                "outer_loop",
                "substep_n",
                "event_ordinal",
                "causal_index",
            )
        ]
        + [
            (name, C.c_int64)
            for name in ("b_zero", "k_zero", "native_level_bottom_first", "B", "K")
        ]
        + [(name, C.c_uint32) for name in ("role", "dtype", "scope", "reason")]
    )


def bind(lib):
    count = lib.kdm6_batch5_condition_v2_count_c
    meta = lib.kdm6_batch5_condition_v2_meta_c
    raw = lib.kdm6_batch5_condition_v2_raw_c
    verify = lib.kdm6_batch5_condition_v2_verify_absences_c
    count.argtypes = [C.c_void_p, C.c_uint64, C.POINTER(C.c_uint64)]
    meta.argtypes = [C.c_void_p, C.c_uint64, C.c_uint64, C.POINTER(Meta), C.c_size_t]
    raw.argtypes = [C.c_void_p, C.c_uint64, C.c_uint64, C.POINTER(C.c_uint64)]
    verify.argtypes = [C.c_void_p, C.c_uint64, C.POINTER(C.c_uint64)]
    for fn in (count, meta, raw, verify):
        fn.restype = C.c_int
    return count, meta, raw, verify


def _read_u64(fn, *args):
    values = []
    for sentinel in (0xAAAAAAAAAAAAAAAA, 0x5555555555555555):
        out = C.c_uint64(sentinel)
        if fn(*args, C.byref(out)):
            raise RuntimeError("ABI copy failed")
        values.append(out.value)
    if values[0] != values[1]:
        raise RuntimeError("ABI output not fully written")
    return values[0]


def _read_meta(fn, handle, token, index):
    copies = []
    for sentinel in (0xAA, 0x55):
        obj = Meta()
        C.memset(C.byref(obj), sentinel, C.sizeof(obj))
        obj.abi_version = 2
        obj.struct_size = C.sizeof(obj)
        if fn(handle, token, index, C.byref(obj), C.sizeof(obj)):
            raise RuntimeError("metadata failed")
        copies.append(obj)
    if any(
        getattr(copies[0], name) != getattr(copies[1], name)
        for name, _ in Meta._fields_
    ):
        raise RuntimeError("metadata not fully written")
    return copies[0]


def read_records(
    lib, *, input_id, mode, runtime_call, handle=None, token=0, max_records=LIMIT
):
    """Copy a committed same-thread context; raise on any partial or malformed result."""
    if (
        mode not in ("capture_on_value", "center_joint_graph")
        or not input_id
        or type(runtime_call) is not int
        or runtime_call < 1
    ):
        raise ValueError("call identity")
    graph = mode == "center_joint_graph"
    if (graph and (not handle or type(token) is not int or token < 1)) or (
        not graph and (handle or token != 0)
    ):
        raise ValueError("handle binding")
    if type(max_records) is not int or not 0 <= max_records <= LIMIT:
        raise ValueError("record limit")
    count, meta, raw, verify = bind(lib)
    n = _read_u64(count, handle, token)
    if n > max_records:
        raise RuntimeError("count exceeds limit")
    rows = []
    ordinals = {}
    epoch = None
    for i in range(n):
        m = _read_meta(meta, handle, token, i)
        if (m.abi_version, m.struct_size) != (2, C.sizeof(Meta)):
            raise RuntimeError("metadata ABI mismatch")
        names = ("input_id", "mode", "family", "stage", "field", "source_hook")
        try:
            row = {name: getattr(m, name).decode("ascii") for name in names}
        except UnicodeError as exc:
            raise RuntimeError("invalid label") from exc
        if (
            any(not row[name] for name in names)
            or (row["input_id"], row["mode"], m.runtime_call)
            != (input_id, mode, runtime_call)
            or not m.context_epoch
        ):
            raise RuntimeError("metadata identity")
        if epoch is not None and epoch != m.context_epoch:
            raise RuntimeError("mixed context epoch")
        epoch = m.context_epoch
        for name, _ in Meta._fields_[8:]:
            row[name] = getattr(m, name)
        if row["scope"] == 1:
            valid = (
                (m.B, m.K, m.b_zero) == (1, 39, 0)
                and 0 <= m.k_zero < 39
                and m.native_level_bottom_first == 39 - m.k_zero
            )
        elif row["scope"] == 2:
            valid = (m.B, m.K, m.b_zero, m.k_zero, m.native_level_bottom_first) == (
                1,
                -1,
                0,
                -1,
                -1,
            )
        else:
            valid = row["scope"] == 3 and (
                m.B,
                m.K,
                m.b_zero,
                m.k_zero,
                m.native_level_bottom_first,
            ) == (-1, -1, -1, -1, -1)
        if not valid or m.role not in (1, 2, 3, 4, 5) or m.dtype not in (1, 2, 3, 4, 5):
            raise RuntimeError("metadata shape or enum")
        if (m.role == 4 and m.scope != 3) or (m.role != 4 and m.scope not in (1, 2)):
            raise RuntimeError("role scope mismatch")
        key = tuple(
            row[k]
            for k in (
                "runtime_call",
                "one_step_call",
                "outer_loop",
                "family",
                "substep_n",
                "scope",
                "b_zero",
                "k_zero",
                "B",
                "K",
                "stage",
                "field",
                "source_hook",
                "role",
            )
        )
        expected_ordinal = ordinals.get(key, 0)
        if m.event_ordinal != expected_ordinal:
            raise RuntimeError("duplicate or noncontiguous event ordinal")
        ordinals[key] = expected_ordinal + 1
        if m.role == 5:
            if m.dtype != 5 or m.reason not in (1, 2, 3) or m.causal_index >= i:
                raise RuntimeError("absence metadata")
        elif (
            m.reason != 0
            or m.causal_index != NO_CAUSE
            or m.dtype == 5
            or (m.role in (1, 2) and m.dtype != 1)
            or (m.role == 3 and m.dtype not in (2, 3))
        ):
            raise RuntimeError("record metadata")
        row["raw_hex"] = None
        if not graph and m.role != 5:
            bits = _read_u64(raw, handle, token, i)
            if (m.dtype == 1 and bits > 1) or (m.dtype == 2 and bits >> 32):
                raise RuntimeError("invalid raw word")
            if m.dtype in (2, 3):
                width = 4 if m.dtype == 2 else 8
                if not math.isfinite(
                    struct.unpack(
                        ">f" if width == 4 else ">d", bits.to_bytes(width, "big")
                    )[0]
                ):
                    raise RuntimeError("nonfinite raw word")
            row["raw_hex"] = format(bits, "08x" if m.dtype == 2 else "016x")
        rows.append(row)
    for row in rows:
        if row["role"] != 5:
            continue
        cause = rows[row["causal_index"]]
        context = (
            "input_id",
            "mode",
            "context_epoch",
            "runtime_call",
            "one_step_call",
            "outer_loop",
            "family",
            "substep_n",
            "scope",
            "b_zero",
            "k_zero",
            "native_level_bottom_first",
            "B",
            "K",
            "event_ordinal",
        )
        if (
            cause["role"] != 1
            or any(cause[k] != row[k] for k in context)
            or (not graph and cause["raw_hex"] != "0000000000000000")
        ):
            raise RuntimeError("invalid causal predicate")
    if not graph:
        verified = _read_u64(verify, handle, token)
        if verified != sum(r["role"] == 5 for r in rows):
            raise RuntimeError("absence verification failed")
    return {
        "status": "SPEC_ONLY_BLOCKED",
        "records": rows,
        "graph_metadata_only": graph,
    }
