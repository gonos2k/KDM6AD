from __future__ import annotations

import hashlib
import struct
from pathlib import Path

import pytest

from harness import replay_s8_native_abi_capture as replay


def _one_call_record(
    dimensions: tuple[int, int, int] = (1, 1, 1),
    *,
    struct_size: int = 336,
    abi_version: int = 2,
    value_only: int = 1,
    physics_variant: int = 1,
    dt: float = 20.0,
    host_real_bytes: int = 4,
) -> bytes:
    im, kme, jme = dimensions
    n = im * kme * jme
    ncol = im * jme
    entry = struct.pack(
        ">8s8i3di",
        b"S8BGIN01",
        struct_size, abi_version, im, kme, jme, value_only, 0, physics_variant,
        dt, 10.0, 10.0, 0,
    )
    inputs = b"\0" * ((16 * n + ncol) * 4)
    returned = struct.pack(">8sii", b"S8RETN01", 0, 0)
    outputs = b"\0" * ((13 * n + 3 * ncol) * 4)
    host = struct.pack(">8si", b"S8HOST01", host_real_bytes)
    copyback = b"\0" * (13 * n * host_real_bytes)
    return entry + inputs + returned + outputs + host + copyback


def _fixture_path() -> Path:
    return Path(__file__).parent / "fixtures" / "s8_synthetic_v2_capture.bin"


def _pin_test_raw_manifest(monkeypatch, raw: bytes) -> None:
    monkeypatch.setattr(replay, "EXPECTED_CAPTURE_BYTES", len(raw))
    monkeypatch.setattr(replay, "EXPECTED_CAPTURE_SHA256", hashlib.sha256(raw).hexdigest())
    monkeypatch.setattr(replay, "EXPECTED_DIMENSIONS", (1, 1, 1))


def test_capture_parser_accepts_one_complete_typed_record() -> None:
    fixture = _fixture_path().read_bytes()
    assert fixture == _one_call_record()
    captures = replay._parse_capture_records(
        fixture, expected_call_count=1, expected_dimensions=(1, 1, 1)
    )
    assert len(captures) == 1
    replay.validate_capture_schema(captures[0])


def test_capture_schema_rejects_missing_or_short_f32_fields() -> None:
    capture = replay._parse_capture_records(
        _one_call_record(), expected_call_count=1, expected_dimensions=(1, 1, 1)
    )[0]
    capture.inputs.pop()
    with pytest.raises(ValueError, match="exactly 17"):
        replay.validate_capture_schema(capture)

    capture = replay._parse_capture_records(
        _one_call_record(), expected_call_count=1, expected_dimensions=(1, 1, 1)
    )[0]
    capture.outputs[0] = capture.outputs[0][:-1]
    with pytest.raises(ValueError, match="lengths/types"):
        replay.validate_capture_schema(capture)


def test_capture_parser_rejects_duplicate_event_record() -> None:
    record = _one_call_record()
    with pytest.raises(ValueError, match="more than 1"):
        replay._parse_capture_records(
            record + record, expected_call_count=1, expected_dimensions=(1, 1, 1)
        )


def test_capture_parser_rejects_truncated_or_relocated_event() -> None:
    record = _one_call_record()
    with pytest.raises(ValueError, match="truncated"):
        replay._parse_capture_records(
            record[:-1], expected_call_count=1, expected_dimensions=(1, 1, 1)
        )
    with pytest.raises(ValueError, match="expected S8BGIN01"):
        replay._parse_capture_records(
            b"x" + record, expected_call_count=1, expected_dimensions=(1, 1, 1)
        )


def test_private_capture_manifest_is_pinned_and_rejects_shrink(tmp_path) -> None:
    assert replay.EXPECTED_CAPTURE_BYTES == 211804960
    assert replay.EXPECTED_CAPTURE_SHA256 == (
        "ac543e94c6c9b9e5b3a099f6854c487a300dc3d6e568c3b5948599454d7801a6"
    )
    assert replay.EXPECTED_CALL_COUNT == 1
    assert replay.EXPECTED_DIMENSIONS == (232, 39, 139)
    assert replay.EXPECTED_CAPTURE_RUN_ID.endswith("231740_p34969")
    assert replay.EXPECTED_SAVED_TIMES == (
        "2025-07-19_00:00:00", "2025-07-19_00:00:20"
    )

    shrunk = tmp_path / "shrunk-capture.bin"
    shrunk.write_bytes(_one_call_record())
    with pytest.raises(ValueError, match="byte length.*pinned"):
        replay.parse_capture(shrunk)


def test_parse_capture_rejects_tampered_and_truncated_raw_files(tmp_path, monkeypatch) -> None:
    good = _fixture_path().read_bytes()
    path = tmp_path / "synthetic-capture.bin"
    path.write_bytes(good)
    _pin_test_raw_manifest(monkeypatch, good)
    assert len(replay.parse_capture(path)) == 1

    tampered = bytearray(good)
    tampered[-1] ^= 1
    path.write_bytes(tampered)
    with pytest.raises(ValueError, match="SHA-256"):
        replay.parse_capture(path)

    truncated = good[:-1]
    path.write_bytes(truncated)
    monkeypatch.setattr(replay, "EXPECTED_CAPTURE_BYTES", len(truncated))
    monkeypatch.setattr(replay, "EXPECTED_CAPTURE_SHA256", hashlib.sha256(truncated).hexdigest())
    with pytest.raises(ValueError, match="truncated"):
        replay.parse_capture(path)


def test_parse_capture_rejects_truncated_or_tampered_gzip(tmp_path, monkeypatch) -> None:
    import gzip

    raw = _fixture_path().read_bytes()
    packed = gzip.compress(raw, mtime=0)
    path = tmp_path / "synthetic-capture.bin.gz"
    path.write_bytes(packed)
    _pin_test_raw_manifest(monkeypatch, raw)
    monkeypatch.setattr(replay, "EXPECTED_COMPRESSED_BYTES", len(packed))
    monkeypatch.setattr(replay, "EXPECTED_COMPRESSED_SHA256", hashlib.sha256(packed).hexdigest())
    assert len(replay.parse_capture(path)) == 1

    tampered = bytearray(packed)
    tampered[-5] ^= 1
    path.write_bytes(tampered)
    with pytest.raises(ValueError, match="compressed capture SHA-256"):
        replay.parse_capture(path)

    truncated = packed[:-4]
    path.write_bytes(truncated)
    monkeypatch.setattr(replay, "EXPECTED_COMPRESSED_BYTES", len(truncated))
    monkeypatch.setattr(replay, "EXPECTED_COMPRESSED_SHA256", hashlib.sha256(truncated).hexdigest())
    with pytest.raises((EOFError, OSError, ValueError)):
        replay.parse_capture(path)


@pytest.mark.parametrize(
    "changed_record, expected_error",
    [
        (_one_call_record(struct_size=332), "ABI metadata"),
        (_one_call_record(abi_version=3), "ABI metadata"),
        (_one_call_record(dt=10.0), "ABI metadata"),
        (_one_call_record(physics_variant=2), "ABI metadata"),
        (_one_call_record(value_only=0), "ABI metadata"),
        (_one_call_record(host_real_bytes=8), "host copyback"),
    ],
)
def test_parse_capture_rejects_changed_abi_metadata(
    tmp_path, monkeypatch, changed_record: bytes, expected_error: str
) -> None:
    changed = changed_record
    path = tmp_path / "changed-abi.bin"
    path.write_bytes(changed)
    _pin_test_raw_manifest(monkeypatch, changed)
    with pytest.raises(ValueError, match=expected_error):
        replay.parse_capture(path)


class _FakeFunction:
    def __init__(self, function):
        self.function = function

    def __call__(self, *args):
        return self.function(*args)


class _ZeroOutputLibrary:
    kdm6_get_abi_version_c = _FakeFunction(lambda: 2)
    kdm6_step_v2_args_size_c = _FakeFunction(lambda: 336)
    kdm6_step_v2_c = _FakeFunction(lambda _args: 0)


def test_replay_flags_mutated_return_and_host_copyback() -> None:
    capture = replay._parse_capture_records(
        _fixture_path().read_bytes(), expected_call_count=1, expected_dimensions=(1, 1, 1)
    )[0]
    capture.outputs[12] = b"\x00\x00\x00\x01"
    result = replay.replay_one(_ZeroOutputLibrary(), capture, 0)
    assert not result["replay_matches_capture"]
    assert result["replay_mismatches"][0]["field"] == "rain_increment"
    assert result["copyback_matches_capture"]

    capture = replay._parse_capture_records(
        _fixture_path().read_bytes(), expected_call_count=1, expected_dimensions=(1, 1, 1)
    )[0]
    capture.host_outputs[0] = b"\x00\x00\x00\x01"
    result = replay.replay_one(_ZeroOutputLibrary(), capture, 0)
    assert result["replay_matches_capture"]
    assert not result["copyback_matches_capture"]
    assert result["copyback_mismatches"][0]["field"] == "th"
