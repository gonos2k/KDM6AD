"""Historical source snapshots are independently pinned and fail on mutation."""

from pathlib import Path
import shutil

import pytest

from harness import historical_ice_sources as historical
from harness import make_ice_factorial_overlay as generator


def test_snapshot_and_actual_qr_observer_match_original_pins():
    root = historical.checked_factorial_root()
    assert {name: historical.digest(root / "src" / name)
            for name in historical.HISTORICAL_TU_SHA256} == dict(
                historical.HISTORICAL_TU_SHA256)
    coordinator = historical.checked_actual_qr_coordinator()
    assert historical.digest(coordinator) == historical.ACTUAL_QR_COORDINATOR_SHA256
    oracle = historical.historical_manifest_source(
        "oracle/kdm6/sedimentation.py", historical.ORACLE_SEDIMENTATION_SHA256)
    assert historical.digest(oracle) == historical.ORACLE_SEDIMENTATION_SHA256


def test_corrupted_historical_cpp_snapshot_is_rejected(tmp_path, monkeypatch):
    original = historical.checked_factorial_root()
    copy = tmp_path / "libtorch"
    shutil.copytree(original, copy)
    source = copy / "src/runtime.cpp"
    source.write_bytes(source.read_bytes() + b"\n// corruption\n")
    monkeypatch.setattr(historical, "LIBTORCH", copy)
    with pytest.raises(ValueError, match="historical source digest runtime.cpp"):
        historical.checked_factorial_root()


def test_generator_pin_rebase_does_not_change_historical_snapshot(monkeypatch):
    changed = dict(generator.FACTORIAL_SOURCE_PINS)
    changed["runtime.cpp"] = "0" * 64
    monkeypatch.setattr(generator, "FACTORIAL_SOURCE_PINS", changed)
    root = historical.checked_factorial_root()
    assert historical.digest(root / "src/runtime.cpp") == (
        historical.HISTORICAL_TU_SHA256["runtime.cpp"])
    source = historical.historical_manifest_source(
        "libtorch/src/runtime.cpp", historical.HISTORICAL_TU_SHA256["runtime.cpp"])
    assert source == root / "src/runtime.cpp"


def test_test_source_selection_is_receipt_hash_specific():
    old = historical.historical_manifest_source(
        "harness/tests/test_qr_boundary_evidence.py",
        "d0b2596990b568e542e063b8f2a52da36756cd31d92d308ec837e304de2287f2")
    newer = historical.historical_manifest_source(
        "harness/tests/test_qr_boundary_evidence.py",
        "a8282a85a3b3d57c402319fcb1a168dcd5b507a719f6b58cb4887f001605110e")
    assert old != newer
    assert historical.digest(old) != historical.digest(newer)


def test_unrecognized_source_digest_does_not_select_a_snapshot():
    relative = "harness/tests/test_qr_boundary_evidence.py"
    source = historical.historical_manifest_source(relative, "0" * 64)
    assert source == historical.REPO / Path(relative)
