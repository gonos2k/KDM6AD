"""Contract tests for the persistent native-step control wire protocol.

These exercise packet validation and binary32 arithmetic only. They do not
run or certify the host model.
"""
from __future__ import annotations

import struct

import numpy as np
import pytest

from harness.native_step_control import (
    HeatingUpdate,
    atomic_write_command,
    encode_command,
    read_applied,
    read_ready,
)


BOUNDS = (1, 234, 1, 39, 1, 282)


def _bits(value: float) -> int:
    return struct.unpack(">I", struct.pack(">f", value))[0]


def _ready(*, step=6, domain=1, timestamp="2025-07-19_00:02:00", bounds=BOUNDS):
    return (
        "KDM6AD_READY_V1\n"
        f"{step:010d} {domain:010d}\n"
        f"{timestamp}\n"
        + " ".join(f"{v:010d}" for v in bounds)
        + "\n"
    ).encode("ascii")


def _ack(step, rows=()):
    return (f"KDM6AD_APPLIED_V1\n{step:010d} {len(rows):010d}\n"
            + "".join(row + "\n" for row in rows)).encode("ascii")


def _ack_row(update, old_bits, delta_bits=None, new_bits=None):
    delta_bits = _bits(update.delta) if delta_bits is None else delta_bits
    old = np.asarray([old_bits], dtype=np.uint32).view(np.float32)[0]
    delta = np.asarray([delta_bits], dtype=np.uint32).view(np.float32)[0]
    if new_bits is None:
        new_bits = _bits(np.float32(old + delta))
    return (f"H_DIABATIC {update.i:010d} {update.k:010d} {update.j:010d} "
            f"{old_bits:08X} {delta_bits:08X} {new_bits:08X}")


def _write(tmp_path, name, data):
    path = tmp_path / name
    path.write_bytes(data)
    return path


def test_encode_command_has_exact_ascii_packet_and_binary32_delta():
    updates = (HeatingUpdate(2, 6, 4, 0.1),)
    expected = (
        "KDM6AD_STEP_V1\n"
        "0000000006 0000000001\n"
        f"H_DIABATIC 0000000002 0000000006 0000000004 {_bits(0.1):08X}\n"
    ).encode("ascii")
    assert encode_command(6, updates, BOUNDS) == expected


def test_encode_command_allows_empty_identity_without_float_operation():
    packet = encode_command(6, (), BOUNDS)
    assert packet == b"KDM6AD_STEP_V1\n0000000006 0000000000\n"


@pytest.mark.parametrize("delta", [0.0, -0.0, 1e-50, float("inf"), -float("inf"), float("nan"), 1e100])
def test_encode_command_rejects_zero_nonfinite_or_unrepresentable_binary32_delta(delta):
    with pytest.raises(ValueError):
        encode_command(6, (HeatingUpdate(2, 6, 4, delta),), BOUNDS)


@pytest.mark.parametrize("update", [
    HeatingUpdate(0, 6, 4, 0.1),
    HeatingUpdate(235, 6, 4, 0.1),
    HeatingUpdate(2, 40, 4, 0.1),
    HeatingUpdate(2, 6, 283, 0.1),
    HeatingUpdate(True, 6, 4, 0.1),
    HeatingUpdate(2**31, 6, 4, 0.1),
])
def test_encode_command_rejects_out_of_domain_or_non_int32_indices(update):
    with pytest.raises(ValueError):
        encode_command(6, (update,), BOUNDS)


def test_encode_command_rejects_duplicate_points_and_invalid_bounds():
    update = HeatingUpdate(2, 6, 4, 0.1)
    with pytest.raises(ValueError, match="duplicate"):
        encode_command(6, (update, update), BOUNDS)
    with pytest.raises(ValueError, match="reversed"):
        encode_command(6, (), (2, 1, 1, 39, 1, 282))
    with pytest.raises(ValueError, match="bounds"):
        encode_command(6, (), (1, 234, 1, 39, 1))


def test_atomic_command_publish_is_complete_and_refuses_overwrite(tmp_path):
    path = tmp_path / "command_0000000006.txt"
    packet = encode_command(6, (), BOUNDS)
    atomic_write_command(path, packet)
    assert path.read_bytes() == packet
    with pytest.raises(FileExistsError):
        atomic_write_command(path, packet)


def test_read_ready_accepts_exact_expected_step_domain_time_and_bounds(tmp_path):
    path = _write(tmp_path, "ready.txt", _ready())
    ready = read_ready(path, expected_step=6)
    assert (ready.step, ready.domain, ready.time, ready.bounds) == (
        6, 1, "2025-07-19_00:02:00", BOUNDS)


@pytest.mark.parametrize("packet,expected", [
    (_ready().replace(b"KDM6AD_READY_V1", b"KDM6AD_READY_V2"), 6),
    (_ready().replace(b"2025-07-19_00:02:00", b"2025-07-19_00:02:60"), 6),
    (_ready(domain=2), 6),
    (_ready().replace(b"0000000234", b"0000000000", 1), 6),
    (_ready() + b"extra\n", 6),
    (_ready()[:-1], 6),
    (_ready().replace(b"\n", b"\r\n"), 6),
])
def test_read_ready_rejects_malformed_packets(tmp_path, packet, expected):
    path = _write(tmp_path, "bad_ready.txt", packet)
    with pytest.raises(ValueError):
        read_ready(path, expected_step=expected)


def test_read_ready_rejects_step_mismatch(tmp_path):
    path = _write(tmp_path, "ready.txt", _ready(step=7))
    with pytest.raises(ValueError, match="step/domain"):
        read_ready(path, expected_step=6)


def test_read_applied_echoes_binary32_delta_and_preserves_signed_zero_bits(tmp_path):
    update = HeatingUpdate(2, 6, 4, 0.25)
    row = _ack_row(update, 0x80000000)  # old H is negative zero; do not decimal-round-trip it.
    path = _write(tmp_path, "applied.txt", _ack(6, (row,)))
    applied, = read_applied(path, expected_step=6, updates=(update,))
    assert applied.update == update
    assert applied.old_bits == 0x80000000
    assert applied.delta_bits == _bits(0.25)
    assert applied.new_bits == _bits(0.25)


def test_read_applied_empty_identity_has_no_rows(tmp_path):
    path = _write(tmp_path, "applied.txt", _ack(6))
    assert read_applied(path, expected_step=6, updates=()) == ()


@pytest.mark.parametrize("packet", [
    b"KDM6AD_APPLIED_V2\n0000000006 0000000001\n",
    b"KDM6AD_APPLIED_V1\n0000000007 0000000001\n",
    b"KDM6AD_APPLIED_V1\n0000000006 0000000000\n",
])
def test_read_applied_rejects_wrong_header_step_or_count(tmp_path, packet):
    update = HeatingUpdate(2, 6, 4, 0.25)
    path = _write(tmp_path, "bad_applied.txt", packet)
    with pytest.raises(ValueError):
        read_applied(path, expected_step=6, updates=(update,))


@pytest.mark.parametrize("row", [
    "H_DIABATIC 0000000003 0000000006 0000000004 3F800000 3E800000 3FA00000",  # wrong point
    "H_DIABATIC 0000000002 0000000006 0000000004 3F800000 7F800000 7F800000",  # nonfinite delta
    "H_DIABATIC 0000000002 0000000006 0000000004 3F800000 3E000000 3FA00000",  # delta differs
    "H_DIABATIC 0000000002 0000000006 0000000004 3F800000 3E80000Z 3FA00000",  # malformed hex
    "H_DIABATIC 0000000002 0000000006 0000000004 3F800000 3E800000 3F000000",  # wrong sum
])
def test_read_applied_rejects_malformed_coordinate_or_value_row(tmp_path, row):
    update = HeatingUpdate(2, 6, 4, 0.25)
    path = _write(tmp_path, "bad_row.txt", _ack(6, (row,)))
    with pytest.raises(ValueError):
        read_applied(path, expected_step=6, updates=(update,))


def test_read_applied_rejects_missing_extra_truncated_and_reordered_rows(tmp_path):
    a, b = HeatingUpdate(2, 6, 4, 0.25), HeatingUpdate(3, 7, 5, -0.5)
    row_a, row_b = _ack_row(a, _bits(1.0)), _ack_row(b, _bits(2.0))
    for name, packet, updates in (
        ("missing", _ack(6), (a,)),
        ("extra", _ack(6, (row_a, row_b)), (a,)),
        ("truncated", _ack(6, (row_a,)).rstrip(b"\n"), (a,)),
        ("reordered", _ack(6, (row_b, row_a)), (a, b)),
    ):
        path = _write(tmp_path, f"{name}.txt", packet)
        with pytest.raises(ValueError):
            read_applied(path, expected_step=6, updates=updates)


def test_read_applied_rejects_binary32_delta_that_does_not_change_memory(tmp_path):
    # A nonzero binary32 delta may round away when added to a much larger memory.
    update = HeatingUpdate(2, 6, 4, 1e-45)
    delta_bits = _bits(float(np.float32(update.delta)))
    old_bits = _bits(1.0)
    assert delta_bits != 0
    row = _ack_row(update, old_bits, delta_bits=delta_bits, new_bits=old_bits)
    path = _write(tmp_path, "no_change.txt", _ack(6, (row,)))
    with pytest.raises(ValueError):
        read_applied(path, expected_step=6, updates=(update,))
