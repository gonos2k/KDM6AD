"""Historical source snapshots are independently pinned and fail on mutation."""

from pathlib import Path
import importlib
import json
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
    coordinator_oracle = historical.historical_manifest_source(
        "oracle/kdm6/coordinator.py", historical.ORACLE_COORDINATOR_SHA256)
    assert historical.digest(coordinator_oracle) == historical.ORACLE_COORDINATOR_SHA256


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


@pytest.mark.parametrize("relative", (
    "libtorch/src/no_such_subdir/runtime.cpp",
    "libtorch/src/../src/runtime.cpp",
    "libtorch/src//runtime.cpp",
    "libtorch/src/./runtime.cpp",
    "/libtorch/src/runtime.cpp",
    "libtorch\\src\\runtime.cpp",
))
def test_noncanonical_or_missing_cpp_path_cannot_select_snapshot(relative):
    with pytest.raises(ValueError):
        historical.historical_manifest_source(
            relative, historical.HISTORICAL_TU_SHA256["runtime.cpp"])


def test_existing_wrong_path_with_historical_bytes_is_not_authenticated(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    wrong = repo / "libtorch/src/alias/runtime.cpp"
    wrong.parent.mkdir(parents=True)
    wrong.write_bytes((historical.LIBTORCH / "src/runtime.cpp").read_bytes())
    monkeypatch.setattr(historical, "REPO", repo)
    with pytest.raises(ValueError, match=r"historical C\+\+ source path mismatch"):
        historical.historical_manifest_source(
            "libtorch/src/alias/runtime.cpp",
            historical.HISTORICAL_TU_SHA256["runtime.cpp"])


def test_exact_historical_cmake_and_actual_qr_paths_resolve():
    cmake = historical.historical_manifest_source(
        "libtorch/CMakeLists.txt", historical.CMAKE_SHA256)
    actual_qr = historical.historical_manifest_source(
        "libtorch/src/coordinator.cpp", historical.ACTUAL_QR_COORDINATOR_SHA256)
    assert historical.digest(cmake) == historical.CMAKE_SHA256
    assert historical.digest(actual_qr) == historical.ACTUAL_QR_COORDINATOR_SHA256


def test_wrong_historical_test_and_oracle_paths_are_rejected():
    test_sha = "59291e79057e654fe92ef697c220a02b27108f07fa20f6dc54d03387269799fc"
    with pytest.raises(ValueError, match="historical test source path mismatch"):
        historical.historical_manifest_source(
            "harness/tests/alias/test_actual_qr_evidence.py", test_sha)
    with pytest.raises(ValueError, match="historical oracle source path mismatch"):
        historical.historical_manifest_source(
            "oracle/kdm6/alias/sedimentation.py",
            historical.ORACLE_SEDIMENTATION_SHA256)
    with pytest.raises(ValueError, match="historical oracle coordinator path mismatch"):
        historical.historical_manifest_source(
            "oracle/kdm6/alias/coordinator.py",
            historical.ORACLE_COORDINATOR_SHA256)


def test_source_path_symlink_cannot_escape_repo(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    source = repo / "libtorch/src/runtime.cpp"
    source.parent.mkdir(parents=True)
    outside = tmp_path / "outside.cpp"
    outside.write_text("historical bytes cannot be selected by a symlink")
    source.symlink_to(outside)
    monkeypatch.setattr(historical, "REPO", repo)
    with pytest.raises(ValueError, match="historical source path escapes root"):
        historical.historical_manifest_source("libtorch/src/runtime.cpp", "0" * 64)


def test_archived_test_source_symlink_is_not_an_authenticated_copy(tmp_path, monkeypatch):
    relative = "harness/tests/test_actual_qr_evidence.py"
    expected = "59291e79057e654fe92ef697c220a02b27108f07fa20f6dc54d03387269799fc"
    original = historical.historical_manifest_source(relative, expected)
    outside = tmp_path / "outside.py"
    outside.write_bytes(original.read_bytes())
    root = tmp_path / "archive"
    linked = root / "test_sources" / expected / relative
    linked.parent.mkdir(parents=True)
    linked.symlink_to(outside)
    monkeypatch.setattr(historical, "ROOT", root)
    with pytest.raises(ValueError, match="historical source path escapes root"):
        historical.historical_manifest_source(relative, expected)


def test_archived_cpp_source_symlink_is_not_authenticated(tmp_path, monkeypatch):
    source_root = historical.checked_factorial_root()
    copy = tmp_path / "libtorch"
    shutil.copytree(source_root, copy)
    outside = tmp_path / "outside.cpp"
    original = copy / "src/runtime.cpp"
    outside.write_bytes(original.read_bytes())
    original.unlink()
    original.symlink_to(outside)
    monkeypatch.setattr(historical, "LIBTORCH", copy)
    with pytest.raises(ValueError, match="historical source path escapes root"):
        historical.checked_factorial_root()


def test_archive_ancestor_symlink_is_not_authenticated(tmp_path, monkeypatch):
    source_root = historical.checked_factorial_root()
    outside = tmp_path / "outside"
    shutil.copytree(source_root, outside / "libtorch")
    alias = tmp_path / "archive"
    alias.symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(historical, "LIBTORCH", alias / "libtorch")
    with pytest.raises(ValueError, match="historical source root contains symlink"):
        historical.checked_factorial_root()


def test_applied_transfer_consumer_rejects_rekeyed_manifest(monkeypatch):
    consumer = importlib.import_module("harness.tests.test_applied_transfer_evidence")
    manifest_path = consumer.E / "manifest.json"
    original_read_text = Path.read_text

    def altered_read_text(path, *args, **kwargs):
        raw = original_read_text(path, *args, **kwargs)
        if path == manifest_path:
            manifest = json.loads(raw)
            sources = manifest["source_sha256"]
            sources["libtorch/src/no_such_subdir/runtime.cpp"] = sources.pop(
                "libtorch/src/runtime.cpp")
            return json.dumps(manifest)
        return raw

    monkeypatch.setattr(Path, "read_text", altered_read_text)
    with pytest.raises(ValueError, match=r"historical C\+\+ source path mismatch"):
        consumer.test_historical_source_and_artifact_pins()
