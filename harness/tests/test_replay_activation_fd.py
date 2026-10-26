from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from harness import replay_activation_fd as replay


def test_profile_ratios_are_checked_coordinatewise_not_by_field_maxnorm():
    fd = np.array([[2.0e-8, 1.0e6]], dtype=np.float64)
    jvp = np.array([[0.0, 1.0e6]], dtype=np.float64)
    result = replay.coordinate_ratios(fd, jvp, atol=1.0e-8, rtol=3.0e-5)
    field_maxnorm_ratio = np.max(np.abs(fd - jvp)) / (
        1.0e-8 + 3.0e-5 * np.max(np.maximum(np.abs(fd), np.abs(jvp)))
    )
    assert field_maxnorm_ratio < 1.0
    assert result["coordinate_count"] == 2
    assert result["passing_coordinates"] == 1
    assert not result["passed"]
    assert result["max_coordinate_ratio"] > 1.0
    assert result["worst_coordinate"] == [0, 0]


def test_descriptor_rejects_pack_escape_and_hash_or_byte_mismatch(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"saved")
    with pytest.raises(replay.ReplayError, match="escapes"):
        replay._descriptor(pack, {"file": "../outside.bin", "sha256": hashlib.sha256(b"saved").hexdigest(), "bytes": 5}, "escape")

    inside = pack / "input.bin"
    inside.write_bytes(b"saved")
    with pytest.raises(replay.ReplayError, match="SHA-256"):
        replay._descriptor(pack, {"file": "input.bin", "sha256": "0" * 64, "bytes": 5}, "bad-hash")
    with pytest.raises(replay.ReplayError, match="byte count"):
        replay._descriptor(pack, {"file": "input.bin", "sha256": hashlib.sha256(b"saved").hexdigest(), "bytes": 6}, "bad-size")


def test_cli_preflights_new_output_before_opening_manifest(tmp_path):
    output = tmp_path / "preserved.json"
    output.write_text('{"keep":true}')
    with pytest.raises(FileExistsError, match="must be new"):
        replay.main(["--manifest", str(tmp_path / "missing.json"), "--output", str(output)])
    assert output.read_text() == '{"keep":true}'


ACTUAL_MANIFEST = Path(__file__).parents[1] / "evidence/block22_activation_2026-10-25/input_manifest.json"


@pytest.mark.skipif(not ACTUAL_MANIFEST.is_file(), reason="restricted private FD pack is not present in this checkout")
def test_saved_campaign_replays_arithmetic_and_preserves_joint33_failure():
    report = replay.replay(ACTUAL_MANIFEST)
    assert report["replay_matches_recorded_arithmetic"]
    assert not report["experiment_joint33pass"]
    direction = report["accepted_fullB_direction"]
    assert direction["actual_parent_recipe_byte_equal"]
    assert direction["accepted_proposal_numeric_equal"]
    assert not direction["accepted_proposal_byte_equal"]
    assert direction["theta_m_signed_zero_sign_mismatches"] == 8619
    assert direction["qv_signed_zero_sign_mismatches"] == 8619
    assert direction["accepted_z_vs_alpha025_bundle_signed_zero_sign_mismatches"] == [8619, 8619]
    assert report["control_zero_history"]["signed_zero_bit_differences_per_component"] == [8619, 8619]
    eps_1e6 = next(item for item in report["per_epsilon"] if item["epsilon"] == 1.0e-6)
    assert eps_1e6["native17_pass_target"]
    assert eps_1e6["BTcost8_pass"]
    assert not eps_1e6["profile8_pass"]
    assert not eps_1e6["joint33_pass"]
    assert eps_1e6["CFRAC_zero_change_check"]["plus_changed_coordinates"] == 0
    assert eps_1e6["CFRAC_zero_change_check"]["minus_changed_coordinates"] == 0


@pytest.mark.skipif(not ACTUAL_MANIFEST.is_file(), reason="restricted private FD pack is not present in this checkout")
def test_cli_writes_replay_report_to_new_path(tmp_path):
    output = tmp_path / "replay.json"
    assert replay.main(["--manifest", str(ACTUAL_MANIFEST), "--output", str(output)]) == 0
    report = json.loads(output.read_text())
    assert report["replay_matches_recorded_arithmetic"]
    assert not report["experiment_joint33pass"]
