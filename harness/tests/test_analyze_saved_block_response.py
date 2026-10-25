"""Saved-data diagnostics do not require a private physics executable."""
import json
import math
from pathlib import Path

import numpy as np
import pytest

from harness.analyze_saved_block_response import (
    INV_DMC, PROFILE_FIELDS, analyze, finite_profile_projection, moment_diameter_ratio, main,
)


EVIDENCE = Path(__file__).resolve().parents[1] / "evidence/native_block22_response_2026-10-25"


def test_actual_saved_block_moments_optics_and_finite_projection():
    result = analyze(EVIDENCE / "input_manifest.json")
    assert result["new_model_calls"] == 0
    assert result["target"]["row0"] == 368
    assert result["target"]["RTTOV_layer1"] == 49
    assert [row["column_CFRAC_changed_layers"] for row in result["endpoints"]] == [0] * 4
    assert result["endpoints"][-1]["NC_ratio_to_baseline"] == pytest.approx(43.11352784801208)
    assert result["endpoints"][-1]["IR105_BT_delta_K"] == -11.405114380730254
    projection = result["baseline_K_finite_profile_projection"]["alpha1"]
    assert projection["total_K"][3] == -34.49579235681166
    assert projection["actual_minus_projection_K"][3] == 23.09067797608141
    assert result["block_IR105_distribution"]["alpha1"]["supported_columns"] == 291
    assert all(result["restricted_vs_original_alpha1_bitwise"].values())
    probe = result["saved_fixed_probe"]
    assert probe["saved_BT_JVP_K"][3] == 3368.277002079154
    assert probe["saved_BT_JVP_K"] == probe["reconstructed_BT_JVP_K"]
    assert "NOT the candidate" in probe["scope"]


def test_projection_retains_channel_layer_order_and_pressure_interfaces():
    before = {name: np.zeros(3 if name == "P_HALF" else 2) for name in PROFILE_FIELDS}
    after = {name: np.ones_like(values) for name, values in before.items()}
    k = {name: np.stack((np.ones_like(v), 2 * np.ones_like(v))) for name, v in before.items()}
    result = finite_profile_projection(k, before, after)
    assert result["by_field_K"]["P_HALF"] == [3.0, 6.0]
    assert result["total_K"] == [17.0, 34.0]
    assert "not native-input JVP" in result["scope"]
    k["P_HALF"] = np.ones((2, 2))
    with pytest.raises(ValueError, match="P_HALF"):
        finite_profile_projection(k, before, after)


def test_executed_reciprocal_predicts_the_saved_unclipped_diameter():
    predicted = moment_diameter_ratio(2.7397424437695553e-5, 2326956.2647002772,
        0.6318870522265209, 26.83008626722003, 0.00012037037714298889,
        100323293.71926157, 0.6318870522265209)
    assert INV_DMC == 0.3333333432674408
    assert abs(predicted - 12.532012900174163) < 3e-14
    assert INV_DMC != 1.0 / 3.0
    with pytest.raises(ValueError, match="positive finite"):
        moment_diameter_ratio(1, 0, 1, 1, 2, 1, 1)


def test_baseline_tangent_does_not_claim_to_equal_a_finite_nonlinear_change():
    before = {name: np.zeros(1) for name in PROFILE_FIELDS}
    after = {name: np.zeros(1) for name in PROFILE_FIELDS}
    after["T"][:] = 1
    k = {name: np.zeros((1, 1)) for name in PROFILE_FIELDS}
    k["T"][:] = 1  # exp(T)' at zero.
    predicted = finite_profile_projection(k, before, after)["total_K"][0]
    assert predicted == 1.0
    assert math.e - 1.0 - predicted > 0.7


def test_manifest_refuses_changed_target_before_loading_arrays(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({
        "schema": "kdm6.saved_block22_response_input.v1", "target_flat_index0": 0,
        "native_mass_level1": 18, "channel_id": 13,
    }))
    with pytest.raises(ValueError, match="manifest target"):
        analyze(tmp_path / "manifest.json")


def test_cli_cannot_overwrite_the_input_manifest():
    path = EVIDENCE / "input_manifest.json"
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        main(["--manifest", str(path), "--output-json", str(path)])
    assert path.read_bytes() == before


@pytest.mark.parametrize("dangling_link", [False, True])
def test_cli_rejects_occupied_plot_path_before_analysis(tmp_path, monkeypatch, dangling_link):
    output = tmp_path / "analysis.json"
    plots = tmp_path / "plots"
    if dangling_link:
        plots.symlink_to(tmp_path / "missing-target", target_is_directory=True)
    else:
        plots.mkdir()
        (plots / "keep.txt").write_bytes(b"unchanged")

    def unexpected_analysis(_):
        pytest.fail("output preflight must run before analysis")

    monkeypatch.setattr("harness.analyze_saved_block_response.analyze", unexpected_analysis)
    with pytest.raises(FileExistsError, match="fresh directory"):
        main(["--manifest", str(EVIDENCE / "input_manifest.json"),
              "--output-json", str(output), "--plot-dir", str(plots)])
    assert not output.exists()
    if dangling_link:
        assert plots.is_symlink() and not plots.exists()
    else:
        assert list(plots.iterdir()) == [plots / "keep.txt"]
        assert (plots / "keep.txt").read_bytes() == b"unchanged"


@pytest.mark.parametrize("output_relative,plots_relative", [
    ("analysis.json", "analysis.json"),
    ("analysis.json", "analysis.json/plots"),
    ("plots/analysis.json", "plots"),
])
def test_cli_rejects_overlapping_new_outputs_before_analysis(
        tmp_path, monkeypatch, output_relative, plots_relative):
    output = tmp_path / output_relative
    plots = tmp_path / plots_relative

    def unexpected_analysis(_):
        pytest.fail("output preflight must run before analysis")

    monkeypatch.setattr("harness.analyze_saved_block_response.analyze", unexpected_analysis)
    with pytest.raises(ValueError, match="must not overlap"):
        main(["--manifest", str(EVIDENCE / "input_manifest.json"),
              "--output-json", str(output), "--plot-dir", str(plots)])
    assert list(tmp_path.iterdir()) == []


def test_manifest_hash_gate_rejects_corrupt_data_before_numpy_decode(tmp_path):
    import hashlib
    inventory = tmp_path / "source_inventory.json"
    inventory.write_text('{}')
    (tmp_path / "bad.npz").write_bytes(b'not an array archive')
    path = tmp_path / "input_manifest.json"
    path.write_text(json.dumps({
        "schema": "kdm6.saved_block22_response_input.v1", "target_flat_index0": 11632,
        "native_mass_level1": 18, "channel_id": 13,
        "source_inventory_sha256": hashlib.sha256(inventory.read_bytes()).hexdigest(),
        "input_npz": {"file": "bad.npz", "sha256": '0' * 64, "bytes": 20},
    }))
    with pytest.raises(ValueError, match="hash/size"):
        analyze(path)
