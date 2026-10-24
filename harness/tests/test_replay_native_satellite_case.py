"""Published native-case arithmetic is replayable without private executables."""
import json
from pathlib import Path

import pytest

from harness.replay_native_satellite_case import replay


EVIDENCE = Path(__file__).resolve().parents[1] / "evidence" / "native_satellite_case_2026-10-25" / "data"


def test_actual_published_case_cost_controls_and_lost_support():
    result = replay(EVIDENCE)
    assert result["status"] == "REPLAY_PASSED"
    assert result["native_columns"] == 65988
    assert result["blocks"] == 129
    assert result["globalZ"] == 381528
    assert result["baseline_J"] == 11.153458878209252
    assert result["published_dot_relative_error"] <= 1e-10
    assert [(v["alpha"], v["lost_profiles"], v["lost_channel_cells"]) for v in result["trials"]] == [
        (1.0, 29, 203), (0.5, 18, 126), (0.25, 13, 91)
    ]
    assert result["new_KDM_RTTOV_host_calls"] == 0


def test_manifest_cannot_redirect_arithmetic_input_outside_bundle(tmp_path):
    outside = tmp_path / "outside.npz"
    outside.write_bytes(b"this must not be opened as an NPZ")
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    names = ["../outside.npz", "scope.json", "summary.json", "channel_bt.npz",
             "observation_support.npz", "native_state_controls.npz",
             "baseline_native_gradient_cost.npz", "baseline_native_tangent.npz",
             "native_control_delta.npz", "trials/trials.json"]
    (bundle / "publication_manifest.json").write_text(json.dumps({
        "schema": "kdm6.native_satellite_publication_pack.v1",
        "artifacts": {name: {} for name in names},
    }))
    with pytest.raises(ValueError, match="escapes the evidence directory"):
        replay(bundle)
