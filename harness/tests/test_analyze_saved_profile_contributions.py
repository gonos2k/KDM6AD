from fractions import Fraction
import json
import math
from pathlib import Path

import numpy as np
import pytest

from harness.analyze_saved_profile_contributions import (
    AttributionError,
    CHANNELS,
    DIRECTIONS,
    PROFILE_COMPONENTS,
    analyze,
    decompose_direction,
)


def _expected_field(k, tangent):
    terms = [
        Fraction.from_float(float(np.float64(a) * np.float64(b)))
        for a, b in zip(k, tangent)
    ]
    return float(sum(terms, Fraction()))


def make_record(scale=1.0, *, candidate=False):
    layers = 2
    profile = {
        key: np.linspace(0.1, 0.2, layers + (key == "P_HALF"), dtype=np.float64)
        for key in PROFILE_COMPONENTS
    }
    profile_k = {}
    for idx, key in enumerate(PROFILE_COMPONENTS, start=1):
        n = profile[key].size
        values = np.empty((1, len(CHANNELS), n), dtype=np.float64)
        for channel in range(len(CHANNELS)):
            values[0, channel] = scale * (idx + channel + np.arange(n) / 10.0)
        profile_k[key] = values
    seed = np.linspace(-0.3, 0.4, len(CHANNELS), dtype=np.float64)
    direction_checks = {}
    for dindex, name in enumerate(DIRECTIONS, start=1):
        tangent = {
            key: np.linspace(
                dindex / 5.0, -dindex / 7.0, profile[key].size, dtype=np.float64
            )
            for key in PROFILE_COMPONENTS
        }
        bt = np.empty(len(CHANNELS), dtype=np.float64)
        for channel in range(len(CHANNELS)):
            bt[channel] = math.fsum(
                _expected_field(profile_k[key][0, channel], tangent[key])
                for key in PROFILE_COMPONENTS
            )
        dot = math.fsum(float(a * b) for a, b in zip(seed, bt))
        direction_checks[name] = {
            "profile_tangent": {key: value.tolist() for key, value in tangent.items()},
            "BT_JVP": [bt.tolist()],
            "cost_directional_derivative": dot,
            "dot_lhs": dot,
            "dot_rhs": dot,
            "direction_x": np.arange(119, dtype=np.float64).tolist(),
        }
        if candidate:
            direction_checks[name]["rest_direction"] = np.zeros((10, 39)).tolist()
    return {
        "profile": {key: value.tolist() for key, value in profile.items()},
        "profile_K": {key: value.tolist() for key, value in profile_k.items()},
        "cost_BT_seed": [seed.tolist()],
        "BT_KMA": [[0.0] * len(CHANNELS)],
        "observation_BT_KMA": [[-float(value) for value in seed]],
        "quality": [[0.0] * len(CHANNELS)],
        "mask": [[1.0] * len(CHANNELS)],
        "geometry": {"lat": 1.0, "lon": 2.0},
        "surface": {"surface_type": 1},
        "cost": 1.0,
        "direction_checks": direction_checks,
        "experiment": {
            "factorial_mode": "norm_actual",
            "qr_transport": "actual_departure",
            "batch_columns": 512,
            "levels": 39,
        }
        if candidate
        else {},
        "target": {
            "i_1based": 131,
            "j_1based": 88,
            "flat_index0": 20488,
            "batch_index0": 40,
            "row_in_batch0": 8,
        },
        "i": 131,
        "j": 88,
        "flat_index": 20488,
        "chunk": 40,
        "local_row": 8,
        "B": 512,
        "L": 39,
    }


def test_analytic_affine_fixture_decomposes_each_profile_component_and_cost_seed():
    result = make_record()
    item = decompose_direction(result, "theta_m")
    channel = 3
    key = "HYDRO_DEFF7"
    kernel = np.asarray(result["profile_K"][key], dtype=np.float64)[0, channel]
    tangent = np.asarray(
        result["direction_checks"]["theta_m"]["profile_tangent"][key],
        dtype=np.float64,
    )
    expected = _expected_field(kernel, tangent)
    assert item["profile_component_bt_jvp_by_channel_K"][key][channel] == expected
    liquid = math.fsum(
        item["profile_component_bt_jvp_by_channel_K"][k][channel]
        for k in ("HYDRO6", "HYDRO_DEFF6")
    )
    assert item["profile_group_bt_jvp_by_channel_K"]["liquid_total"][channel] == liquid
    ice = math.fsum(
        item["profile_component_bt_jvp_by_channel_K"][k][channel]
        for k in ("HYDRO7", "HYDRO_DEFF7")
    )
    assert item["profile_group_bt_jvp_by_channel_K"]["ice_total"][channel] == ice
    assert item["profile_group_bt_jvp_by_channel_K"]["direct_pressure_K_total"][
        channel
    ] == math.fsum(
        item["profile_component_bt_jvp_by_channel_K"][k][channel]
        for k in ("P", "P_HALF")
    )
    assert item["arithmetic_envelope"]["bt_matches_stored_by_channel"]
    assert item["arithmetic_envelope"]["cost_matches_stored_dot"]


@pytest.mark.parametrize("missing", ["P", "P_HALF", "HYDRO6", "HYDRO_DEFF7"])
def test_missing_profile_kernel_component_fails_closed(missing):
    result = make_record()
    del result["profile_K"][missing]
    with pytest.raises(AttributionError, match="missing required keys"):
        decompose_direction(result, "theta_m")


def test_profile_grid_or_channel_shape_mismatch_fails_closed():
    result = make_record()
    result["profile_K"]["P_HALF"] = np.zeros((1, len(CHANNELS), 2)).tolist()
    with pytest.raises(AttributionError, match="shape"):
        decompose_direction(result, "theta_m")
    result = make_record()
    result["cost_BT_seed"] = [[1.0]]
    result["BT_KMA"] = [[0.0]]
    with pytest.raises(AttributionError, match="shape"):
        decompose_direction(result, "theta_m")


def test_offline_analysis_outputs_candidate_and_reference_profile_terms(tmp_path):
    candidate = make_record(scale=1.0001, candidate=True)
    reference = make_record(scale=1.0, candidate=False)
    candidate_path, reference_path = (
        tmp_path / "candidate.json",
        tmp_path / "reference.json",
    )
    candidate_path.write_text(json.dumps(candidate))
    reference_path.write_text(json.dumps(reference))
    output = tmp_path / "profile_contributions.json"
    result = analyze(candidate_path, reference_path, output)
    assert result["arithmetic_envelope"]["bt_and_dot_totals_match_saved_results"]
    assert set(result["directions"]) == set(DIRECTIONS)
    block = result["directions"]["mixed"]["candidate"]
    assert "direct_pressure_K_total" in block["profile_group_bt_jvp_by_channel_K"]
    assert "HYDRO_DEFF6" in block["profile_component_bt_jvp_by_channel_K"]
    assert output.is_file()
    assert result["input_comparison_contract"]["direction_x_bit_equal_by_direction"]
    assert result["reference_rest_direction_contract"] is None
    assert any(
        "reference rest equality is unverified" in limit for limit in result["limits"]
    )


@pytest.mark.parametrize("key", ["observation_BT_KMA", "quality", "mask"])
def test_analyze_rejects_candidate_reference_observation_contract_mismatch(
    tmp_path, key
):
    candidate = make_record(scale=1.0001, candidate=True)
    reference = make_record(scale=1.0, candidate=False)
    reference[key][0][0] += 0.125
    if key == "observation_BT_KMA":
        reference["cost_BT_seed"][0][0] -= 0.125
    elif key == "mask":
        reference["cost_BT_seed"][0][0] *= reference[key][0][0]
    candidate_path, reference_path = _write_pair(tmp_path, candidate, reference)
    with pytest.raises(AttributionError, match="arrays differ"):
        analyze(candidate_path, reference_path, tmp_path / "out.json")


def test_analyze_rejects_direction_mismatch_before_comparing_contributions(tmp_path):
    candidate = make_record(scale=1.0001, candidate=True)
    reference = make_record(scale=1.0, candidate=False)
    reference["direction_checks"]["mixed"]["direction_x"][17] += 1.0
    candidate_path, reference_path = _write_pair(tmp_path, candidate, reference)
    with pytest.raises(AttributionError, match="input directions differ"):
        analyze(candidate_path, reference_path, tmp_path / "out.json")


def test_analyze_rejects_geometry_surface_and_candidate_rest_mutations(tmp_path):
    for field in ("geometry", "surface"):
        candidate = make_record(scale=1.0001, candidate=True)
        reference = make_record(scale=1.0, candidate=False)
        reference[field]["mutated"] = True
        candidate_path, reference_path = _write_pair(tmp_path, candidate, reference)
        with pytest.raises(AttributionError, match=f"{field} metadata differ"):
            analyze(candidate_path, reference_path, tmp_path / f"{field}.json")
    candidate = make_record(scale=1.0001, candidate=True)
    reference = make_record(scale=1.0, candidate=False)
    candidate["direction_checks"]["qv"]["rest_direction"][0][0] = 1.0
    candidate_path, reference_path = _write_pair(tmp_path, candidate, reference)
    with pytest.raises(AttributionError, match="must be serialized as zero"):
        analyze(candidate_path, reference_path, tmp_path / "rest.json")


def test_analyze_rejects_cost_seed_inconsistent_with_own_huber_inputs(tmp_path):
    candidate = make_record(scale=1.0001, candidate=True)
    reference = make_record(scale=1.0, candidate=False)
    candidate["cost_BT_seed"][0][0] += 0.01
    candidate_path, reference_path = _write_pair(tmp_path, candidate, reference)
    with pytest.raises(AttributionError, match="own saved BT/observation/mask Huber"):
        analyze(candidate_path, reference_path, tmp_path / "out.json")


def _write_pair(tmp_path, candidate, reference):
    candidate_path = tmp_path / "candidate.json"
    reference_path = tmp_path / "reference.json"
    candidate_path.write_text(json.dumps(candidate))
    reference_path.write_text(json.dumps(reference))
    return candidate_path, reference_path


def test_real_saved_results_use_public_controller_snapshot_without_private_tree(
    tmp_path,
):
    repo_root = Path(__file__).resolve().parents[2]
    prepared = json.loads(
        (
            repo_root
            / "harness/evidence/norm_actual_observation_2026-10-24/prepared.json"
        ).read_text()
    )
    pinned_hash = next(
        digest
        for path, digest in prepared["source_sha256"].items()
        if path.endswith("/v4_final/pilot.py")
    )
    prepared["source_sha256"] = {"/missing/private/host/v4_final/pilot.py": pinned_hash}
    prepared_path = tmp_path / "prepared.json"
    prepared_path.write_text(json.dumps(prepared))
    output = tmp_path / "portable-analysis.json"
    result = analyze(
        repo_root
        / "harness/evidence/actual_qr_transport_2026-10-24/observation_result.json",
        repo_root
        / "harness/evidence/norm_actual_observation_2026-10-24/native13188_cost.json",
        output,
        reference_prepared=prepared_path,
    )
    contract = result["reference_rest_direction_contract"]
    assert contract["path"] == (
        "harness/evidence/norm_actual_observation_2026-10-24/"
        "execution_sources/final_coupling.py.txt"
    )
    assert contract["sha256"] == pinned_hash
    assert not Path(contract["archived_execution_path"]).is_file()
    assert contract["saved_reference_rest_direction_array"] is False
