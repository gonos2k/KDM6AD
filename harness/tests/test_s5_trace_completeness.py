"""Fail-closed tests for the published S5 trace manifests and NPZ payloads."""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import s5_g4_halo_trace as halo_replay  # noqa: E402
import s5_g4_selected_trace as c2_replay  # noqa: E402

DATA = ROOT / "evidence" / "data"
C2 = DATA / "S5_G4_C2_selected_trace_2026-09-25.json"
HALO = DATA / "S5_G4_exact2_halo_stencil_trace_2026-09-25.json"


def _mutated_package(tmp_path: Path, manifest_path: Path, mutate):
    manifest = json.loads(manifest_path.read_text())
    file_key = "npz_file" if "npz_file" in manifest else "trace_file"
    source_npz = manifest_path.with_name(manifest[file_key])
    with np.load(source_npz, allow_pickle=False) as archive:
        arrays = {name: archive[name].copy() for name in archive.files}
    mutate(manifest, arrays)
    output_npz = tmp_path / manifest[file_key]
    np.savez_compressed(output_npz, **arrays)
    hash_key = "npz_sha256" if "npz_sha256" in manifest else "trace_sha256"
    size_key = "npz_bytes" if "npz_bytes" in manifest else "trace_bytes"
    manifest[hash_key] = hashlib.sha256(output_npz.read_bytes()).hexdigest()
    manifest[size_key] = output_npz.stat().st_size
    output_manifest = tmp_path / manifest_path.name
    output_manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return output_manifest


def test_c2_replay_rejects_record_and_npz_pair_removed_with_rehashed_manifest(tmp_path):
    def shrink(manifest, arrays):
        record = manifest["selected_records"].pop()
        arrays.pop(f"serial__{record['array_key']}")
        arrays.pop(f"x2__{record['array_key']}")
        manifest["selected_record_count"] -= 1
        manifest["raw_word_count"] = (
            2 * sum(math.prod(row["shape"])
                    for row in manifest["selected_records"]) + 2)

    mutant = _mutated_package(tmp_path, C2, shrink)
    with pytest.raises(ValueError, match="selected-record universe"):
        c2_replay.replay(mutant)


def test_c2_replay_rejects_same_count_j_coordinate_relabel(tmp_path):
    def relabel(manifest, _arrays):
        row = manifest["selected_records"][0]
        row["j_bounds"] = [2, 283]  # same 282 values, shifted coordinate origin

    mutant = _mutated_package(tmp_path, C2, relabel)
    with pytest.raises(ValueError, match="selected-record universe"):
        c2_replay.replay(mutant)


def test_c2_replay_rejects_uint64_widened_npz_with_recomputed_digest(tmp_path):
    def widen(_manifest, arrays):
        for key, value in arrays.items():
            arrays[key] = value.astype(np.uint64)

    mutant = _mutated_package(tmp_path, C2, widen)
    with pytest.raises(ValueError, match="big-endian uint32"):
        c2_replay.replay(mutant)


def test_halo_replay_rejects_i235_caller_pair_removed_with_rehashed_manifest(tmp_path):
    def shrink(manifest, arrays):
        index = next(i for i, row in enumerate(manifest["selected_caller_input_records"])
                     if row["stage"] == 1 and row["i"] == 235
                     and row["field"] == "rdy")
        row = manifest["selected_caller_input_records"].pop(index)
        arrays.pop(f"serial__{row['key']}")
        arrays.pop(f"x2__{row['key']}")
        manifest["selected_input_record_count"] -= 1

    mutant = _mutated_package(tmp_path, HALO, shrink)
    with pytest.raises(ValueError, match="caller-input key/coordinate universe"):
        halo_replay.replay(mutant)


def test_halo_replay_rejects_same_count_j_coordinate_relabel(tmp_path):
    def relabel(manifest, _arrays):
        row = manifest["selected_caller_input_records"][0]
        row["j_bounds"] = [1, 284]  # same 284 values, shifted first stencil j

    mutant = _mutated_package(tmp_path, HALO, relabel)
    with pytest.raises(ValueError, match="caller-input key/coordinate universe"):
        halo_replay.replay(mutant)


def test_halo_replay_rejects_uint64_widened_npz_with_recomputed_digest(tmp_path):
    def widen(_manifest, arrays):
        for key, value in arrays.items():
            arrays[key] = value.astype(np.uint64)

    mutant = _mutated_package(tmp_path, HALO, widen)
    with pytest.raises(ValueError, match="big-endian uint32"):
        halo_replay.replay(mutant)
