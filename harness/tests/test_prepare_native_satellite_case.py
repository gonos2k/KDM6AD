import hashlib
from pathlib import Path

import numpy as np
import pytest

from harness.prepare_native_satellite_case import (
    CasePreparationError,
    _CACHE,
    _physical_experiment,
    _prep_batch,
    load_case_block,
    validate_packet_manifest,
)


def _test_prep_config():
    return {
        "ptop": 5000.0,
        "rd": 287.0,
        "p0": 100000.0,
        "t0": 300.0,
        "alpha": 1.6083624362945557,
        "gamma": 1.399999976158142,
        "kappa": 0.2857142984867096,
        "g": 9.8100004196167,
    }


def _small_manifest():
    chunk_entries = []
    for index, (start, stop) in enumerate(((0, 4), (4, 6))):
        chunk_entries.append(
            {
                "start_flat": start,
                "stop_flat_exclusive": stop,
                "columns": stop - start,
                "path": f"chunk_{start:05d}_{stop:05d}.npz",
                "bytes": 1,
                "sha256": f"{index + 1:064x}",
            }
        )
    return {
        "schema": "kdm6.ice_factorial_endpoint_preparation.v2",
        "chunk_columns": 4,
        "coverage": {
            "columns_expected": 6,
            "columns_written": 6,
            "missing": 0,
            "duplicate": 0,
            "included_edges": True,
        },
        "mapping": {
            "state_order": [
                "TH",
                "Q",
                "QC",
                "QR",
                "QI",
                "QS",
                "QG",
                "NN",
                "NC",
                "NI",
                "NR",
                "BG",
            ],
            "forcing_order": ["DEN", "PII", "P", "DELZ"],
            "mu_total": "float32(MUB + MU_2), native addition before widening",
        },
        "chunks": chunk_entries,
    }


def test_packet_manifest_requires_all_columns_and_unpadded_final_chunk():
    manifest = _small_manifest()
    chunks = validate_packet_manifest(manifest, nx=3, ny=2, chunk_columns=4)
    assert [chunk["columns"] for chunk in chunks] == [4, 2]
    manifest["chunks"][1]["columns"] = 4
    manifest["chunks"][1]["stop_flat_exclusive"] = 8
    with pytest.raises(CasePreparationError, match="manifest chunk"):
        validate_packet_manifest(manifest, nx=3, ny=2, chunk_columns=4)


def test_current_physics_experiment_drops_old_single_target_plan_fields():
    archived = {
        "schema": "historical single target",
        "factorial_mode": "norm_actual",
        "qr_transport": "actual_departure",
        "batch_columns": 512,
        "levels": 39,
        "dt_seconds": 20.0,
        "ncmin_land": 10.0,
        "ncmin_sea": 10.0,
        "targets": [{"i_1based": 131, "j_1based": 88}],
        "directions": ["theta_m", "qv"],
        "epsilons": [0.01],
        "scope": "old one-cell study",
    }
    current = _physical_experiment(archived)
    assert set(current) == {
        "schema",
        "factorial_mode",
        "qr_transport",
        "batch_columns",
        "levels",
        "dt_seconds",
        "ncmin_land",
        "ncmin_sea",
    }
    assert (
        "targets" not in current
        and "directions" not in current
        and "scope" not in current
    )


def _make_test_config(tmp_path):
    nx, ny, levels, columns = 3, 2, 2, 6
    prep_config = _test_prep_config()
    theta_m = np.full((columns, levels), np.float32(1.25), dtype=np.float32).astype(
        np.float64
    )
    qv = np.full((columns, levels), np.float32(0.004), dtype=np.float32).astype(
        np.float64
    )
    mu = np.full(columns, 91000.0, dtype=np.float64)
    ph = np.broadcast_to(
        np.array([0.0, 10000.0, 20000.0], dtype=np.float32).astype(np.float64),
        (columns, 3),
    ).copy()
    geometry = {
        "phb": np.zeros((columns, 3), dtype=np.float32).astype(np.float64),
        "c3h": np.zeros((columns, 2), dtype=np.float32).astype(np.float64),
        "c4h": np.full((columns, 2), np.float32(50000.0), dtype=np.float32).astype(
            np.float64
        ),
        "c3f": np.broadcast_to(
            np.array([0.9, 0.6, 0.3], dtype=np.float32).astype(np.float64), (columns, 3)
        ).copy(),
        "c4f": np.zeros((columns, 3), dtype=np.float32).astype(np.float64),
    }
    expected = _prep_batch(theta_m, qv, mu, ph, geometry, prep_config)
    packet_state = np.zeros((12, 6, levels), dtype=np.float64)
    packet_state[0] = expected[0]
    packet_state[1] = qv
    packet_state[2:] = 0.002
    packet_state[8, 1, 0] = -1e-8
    packet_state[9, 4, 1] = -2e-8
    packet_forcing = expected[1:]
    packet_xland = np.array([1, 2, 1, 2, 1, 2], dtype=np.float64)
    manifest = _small_manifest()
    manifest["coverage"]["negative_raw_state_values_by_field"] = {
        name: int(np.count_nonzero(packet_state[row] < 0.0))
        for row, name in enumerate(
            ("TH", "Q", "QC", "QR", "QI", "QS", "QG", "NN", "NC", "NI", "NR", "BG")
        )
    }
    manifest["coverage"]["negative_condensate_values_preserved"] = {
        name: manifest["coverage"]["negative_raw_state_values_by_field"][name]
        for name in ("QC", "QG", "QI", "QR", "QS")
    }
    packet_root = tmp_path / "packets"
    packet_root.mkdir()
    cache = {
        "checkpoint": {
            "THM_2": theta_m.T.reshape(levels, ny, nx).astype(np.float32),
            "QVAPOR": qv.T.reshape(levels, ny, nx).astype(np.float32),
            "PH_2": ph.T.reshape(levels + 1, ny, nx).astype(np.float32),
            "PHB": geometry["phb"].T.reshape(levels + 1, ny, nx).astype(np.float32),
            "C3H": np.zeros(levels, dtype=np.float32),
            "C4H": np.full(levels, 50000.0, dtype=np.float32),
            "C3F": np.array([0.9, 0.6, 0.3], dtype=np.float32),
            "C4F": np.zeros(levels + 1, dtype=np.float32),
            "FNM": np.ones(levels, dtype=np.float32),
            "FNP": np.ones(levels, dtype=np.float32),
            "MUB": np.full((ny, nx), 90000.0, dtype=np.float32),
            "MU_2": np.full((ny, nx), 1000.0, dtype=np.float32),
        },
        "inputs": {},
        "source_valid": np.ones((columns, 7), dtype=bool),
        "reference": {
            "p_lay_hpa": np.ones(69),
            "p_half_hpa": np.ones(70),
            "t_k": np.ones(69),
            "q_ppmv": np.ones(69),
            "o3_ppmv": np.ones(69),
            "co2_ppmv": np.ones(69),
            "fixed_upper_count": 27,
        },
        "fastem": (3.0, 5.0, 15.0, 0.1, 0.3),
        "checkpoint_sha256": "a" * 64,
        "observation_sha256": "b" * 64,
    }
    checkpoint = cache["checkpoint"]
    for name, value in {
        "XLAND": packet_xland,
        "HGT": np.zeros(columns),
        "TSK": np.full(columns, 290.0),
        "T2": np.full(columns, 289.0),
        "Q2": np.full(columns, 0.01),
        "U10": np.full(columns, 2.0),
        "V10": np.full(columns, 1.0),
        "SINALPHA": np.zeros(columns),
        "COSALPHA": np.ones(columns),
        "SNOWC": np.zeros(columns),
        "SEAICE": np.zeros(columns),
        "EMISS": np.full(columns, 0.98),
        "XLAT": np.arange(columns, dtype=np.float32) + 30.0,
        "XLONG": np.arange(columns, dtype=np.float32) + 120.0,
    }.items():
        checkpoint[name] = np.asarray(value, dtype=np.float32).reshape(ny, nx)
    inputs = cache["inputs"]
    inputs.update(
        {
            "obs_bt": np.full((columns, 7), 250.0),
            "obs_dqf": np.zeros((columns, 7), dtype=np.uint8),
            "obs_qc": np.zeros((columns, 7), dtype=np.float64),
            "model_lat": checkpoint["XLAT"].copy(),
            "model_lon": checkpoint["XLONG"].copy(),
            "ko_nearest_row": np.zeros((ny, nx), dtype=np.int32),
            "ko_nearest_col": np.arange(columns, dtype=np.int32).reshape(ny, nx),
            "ko_nearest_flat_index": np.arange(columns, dtype=np.int32).reshape(ny, nx),
            "ko_distance_m": np.full((ny, nx), 100.0),
            "ko_nearest_lat_deg": (np.arange(columns).reshape(ny, nx) + 31.0).astype(
                np.float64
            ),
            "ko_nearest_lon_deg": (np.arange(columns).reshape(ny, nx) + 121.0).astype(
                np.float64
            ),
            "ami_geometry_zenangle_deg": np.full((ny, nx), 35.0),
            "ami_geometry_azangle_deg": np.full((ny, nx), 180.0),
            "ami_geometry_sunzenangle_deg": np.zeros((ny, nx)),
            "ami_geometry_sunazangle_deg": np.zeros((ny, nx)),
            "ami_geometry_lat_deg": (np.arange(columns).reshape(ny, nx) + 31.0).astype(
                np.float64
            ),
            "ami_geometry_lon_deg": (np.arange(columns).reshape(ny, nx) + 121.0).astype(
                np.float64
            ),
            "ami_geometry_elevation_km": np.zeros((ny, nx)),
        }
    )
    _CACHE["d" * 64] = cache
    paths = {"packets": str(packet_root)}
    exp = {
        "schema": "kdm6.native_satellite_case_physics.v1",
        "factorial_mode": "norm_actual",
        "qr_transport": "actual_departure",
        "batch_columns": 4,
        "levels": levels,
        "dt_seconds": 20.0,
        "ncmin_land": 10.0,
        "ncmin_sea": 10.0,
    }
    config = {
        "schema": "kdm6.native_satellite_case_config.v1",
        "paths": paths,
        "grid": {"nx": nx, "ny": ny, "levels": levels, "columns": columns},
        "experiment": exp,
        "packet_manifest": manifest,
        "packet_manifest_sha256": "c" * 64,
        "prep_configuration": prep_config,
        "cache_key": "d" * 64,
        "observation_qualification": {"unique_pixel_id_count": columns},
    }
    for entry in manifest["chunks"]:
        start, stop = entry["start_flat"], entry["stop_flat_exclusive"]
        flat = np.arange(start, stop, dtype=np.int32)
        chunk = packet_root / entry["path"]
        np.savez(
            chunk,
            state=packet_state[:, start:stop].copy(),
            forcing=packet_forcing[:, start:stop].copy(),
            xland=packet_xland[start:stop].copy(),
            flat_indices=flat,
            i=(flat % nx).astype(np.int32),
            j=(flat // nx).astype(np.int32),
        )
        data = chunk.read_bytes()
        entry["bytes"] = len(data)
        entry["sha256"] = hashlib.sha256(data).hexdigest()
    return config, packet_state


def test_case_block_uses_checkpoint_prep_without_rewriting_packet_and_keeps_full_b(
    tmp_path,
):
    config, expected_state = _make_test_config(tmp_path)
    full = load_case_block(config, 0)
    tail = load_case_block(config, 1)
    assert full["flat_indices"].tolist() == [0, 1, 2, 3]
    assert tail["flat_indices"].tolist() == [4, 5]
    assert tail["B"] == 2  # no padding to B512
    assert full["packet_state"].tobytes() == expected_state[:, :4].tobytes()
    assert full["rest"].shape == (10, 4, 2)
    assert full["prep_allclose"].all()
    assert np.max(full["prep_maxabs_vs_packet"]) < 1.0e-13
    assert full["initial_admission"]["negative_nc"].tolist() == [
        False,
        True,
        False,
        False,
    ]
    assert tail["initial_admission"]["negative_ni"].tolist() == [True, False]
    assert full["initial_admission"]["cost_eligible"].tolist() == [
        True,
        False,
        True,
        True,
    ]
    assert full["obs_qc_raw"].dtype == np.float64
    assert full["obs_qc_codes"].dtype == np.int32
    assert full["obs_source_valid"].all()
    assert full["reference"]["fixed_upper_count"] == 27
    assert len(full["surface_profiles"]) == full["B"]
    assert full["rttov_geometry"]["latitude"].tobytes() == full["model_lat"].tobytes()
    assert full["pixel_lat"].tobytes() == full["ko_geometry_pixel_lat"].tobytes()
    assert full["initial_admission"]["original_full_b_retained"]
    assert full["initial_admission"]["original_packet_state_unchanged"]


def test_case_block_rejects_wrong_packet_hash_and_out_of_range_chunk(tmp_path):
    config, _ = _make_test_config(tmp_path)
    config["packet_manifest"]["chunks"][0]["sha256"] = "0" * 64
    with pytest.raises(CasePreparationError, match="differs from its manifest pin"):
        load_case_block(config, 0)
    with pytest.raises(IndexError):
        load_case_block(config, 2)


def test_packet_payload_audit_checks_all_chunks_and_negative_raw_counts(tmp_path):
    config, _ = _make_test_config(tmp_path)
    from harness.prepare_native_satellite_case import verify_packet_chunks

    result = verify_packet_chunks(
        Path(config["paths"]["packets"]),
        config["packet_manifest"],
        nx=3,
        ny=2,
        levels=2,
        chunk_columns=4,
    )
    assert result["chunks_hashed_and_checked"] == 2
    assert result["columns_checked"] == 6
    assert result["missing"] == 0
    assert result["duplicate"] == 0
    assert result["negative_raw_state_values_by_field"]["NC"] == 1
    assert result["negative_raw_state_values_by_field"]["NI"] == 1


def test_numpy_prep_reconstruction_matches_reference_prep_operator():
    pytest.importorskip("torch", reason="independent oracle prep reference requires Torch")
    from harness.verify_native_prep_ad import Prep, pack_state

    levels = 2
    theta = np.array([1.25, 1.3], dtype=np.float64)
    qv = np.array([0.004, 0.003], dtype=np.float64)
    mu = np.asarray(91000.0)
    ph = np.array([0.0, 10000.0, 20000.0], dtype=np.float64)
    geometry = {
        "phb": np.zeros(3, dtype=np.float64),
        "c3h": np.zeros(2, dtype=np.float64),
        "c4h": np.full(2, 50000.0, dtype=np.float64),
        "c3f": np.array([0.9, 0.6, 0.3], dtype=np.float64),
        "c4f": np.zeros(3, dtype=np.float64),
    }
    config = _test_prep_config()
    from harness.prepare_native_satellite_case import _prep_batch

    batch = _prep_batch(
        theta[None],
        qv[None],
        mu.reshape(1),
        ph[None],
        {name: value[None] for name, value in geometry.items()},
        config,
    )[:, 0]
    reference = Prep(levels, geometry, config).forward(pack_state((theta, qv, mu, ph)))
    np.testing.assert_allclose(batch, reference, rtol=2e-13, atol=1e-13)
