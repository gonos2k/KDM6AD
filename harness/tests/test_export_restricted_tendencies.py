"""Numerical anchors for saved native finish-rate export helpers."""

import math
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from harness.summarize_native_satellite_case import (
    _append_water_column_changes,
    _finish_rate_formula,
    _load_restricted_confirmation,
    _new_water_column_accumulator,
    _packet_qc_by_flat,
    _source_pin_record,
    _same_f64_bits,
    _weighted_water_summary,
)


def test_finish_rate_formula_keeps_clip_and_cross_term_operation_order():
    before = np.zeros((12, 1, 3), dtype=np.float64)
    clean = np.zeros_like(before)
    before[0, 0] = (300.0, 280.0, 270.0)
    before[1, 0] = (0.001, 0.003, 0.005)
    before[2, 0] = (0.002, 0.004, 0.006)
    clean[0, 0] = (301.0, 280.5, 268.0)
    clean[1, 0] = (0.0015, 0.002, 0.004)
    clean[2, 0] = (0.001, 0.006, 0.003)
    config = {"dt": 20.0, "alpha": 1.6083624362945557, "mp_tend_lim": 0.05}

    got = _finish_rate_formula(before, clean, config)
    bound = config["dt"] * config["mp_tend_lim"]
    expected = np.empty((3, 1, 3), dtype=np.float64)
    for k in range(3):
        delta_th = clean[0, 0, k] - before[0, 0, k]
        m = bound if delta_th >= bound else (-bound if delta_th <= -bound else delta_th)
        delta_qv = clean[1, 0, k] - before[1, 0, k]
        _a = 1.0 + config["alpha"] * before[1, 0, k]
        b = 1.0 + config["alpha"] * clean[1, 0, k]
        mb = m * b
        cross = config["alpha"] * delta_qv
        cross = cross * clean[0, 0, k]
        expected[0, 0, k] = (mb + cross) / config["dt"]
        expected[1, 0, k] = delta_qv / config["dt"]
        expected[2, 0, k] = (clean[2, 0, k] - before[2, 0, k]) / config["dt"]
    assert _same_f64_bits(got, expected)


def test_water_summary_uses_per_call_den_times_delz_and_unweighted_columns():
    before = np.zeros((12, 2, 2), dtype=np.float64)
    raw, clean = before.copy(), before.copy()
    forcing = np.zeros((4, 2, 2), dtype=np.float64)
    forcing[0] = ((1.0, 2.0), (3.0, 4.0))
    forcing[3] = ((10.0, 20.0), (30.0, 40.0))
    before[1] = 1.0
    raw[1] = ((2.0, 1.0), (3.0, 2.0))
    clean[1] = ((1.5, 1.0), (2.5, 2.0))
    before[2] = 2.0
    raw[2] = 3.0
    clean[2] = 2.0

    report = _weighted_water_summary(before, raw, clean, forcing)
    assert report["weight"] == "actual applied_forcing[DEN] * applied_forcing[DELZ]"
    # Raw QV delta products: [1*10, 0*40, 2*90, 1*160], summed without area weights.
    assert report["changes_kg_m2_unweighted_over_columns"]["raw_minus_input"]["QV"] == math.fsum((10., 0., 180., 160.))
    assert report["changes_kg_m2_unweighted_over_columns"]["cleanup_minus_raw"]["QC"] == math.fsum((-10., -40., -90., -160.))


def test_water_accumulator_populates_raw_cleanup_and_applied_species_columns():
    before = np.zeros((12, 2, 2), dtype=np.float64)
    raw = before.copy()
    clean = before.copy()
    forcing = np.ones((4, 2, 2), dtype=np.float64)
    before[1:7] = 1.0
    raw[1:7] = 2.0
    clean[1:7] = 1.5
    accumulator = _new_water_column_accumulator(2)
    _append_water_column_changes(accumulator, before, raw, clean, forcing, np.arange(2))
    assert set(accumulator) == {
        "raw_minus_input_kg_m2", "cleanup_minus_raw_kg_m2", "applied_minus_input_kg_m2"
    }
    for key in accumulator:
        assert accumulator[key].shape == (6, 2)
    assert accumulator["raw_minus_input_kg_m2"][0].tolist() == [2.0, 2.0]
    assert accumulator["cleanup_minus_raw_kg_m2"][1].tolist() == [-1.0, -1.0]
    assert accumulator["applied_minus_input_kg_m2"][5].tolist() == [1.0, 1.0]


def test_raw_bit_comparison_rejects_dtype_coercion():
    value = np.array([1.0, 2.0], dtype=np.float64)
    assert _same_f64_bits(value, value.copy())
    assert not _same_f64_bits(value.astype(np.float32), value)


@pytest.mark.parametrize("start,count", ((0, 3), (65_536, 452)))
def test_packet_qc_reader_uses_level_count_not_chunk_width(tmp_path, start, count):
    levels = 39
    state = np.zeros((12, count, levels), dtype=np.float64)
    forcing = np.ones((4, count, levels), dtype=np.float64)
    state[1] = np.arange(count * levels, dtype=np.float64).reshape(count, levels)
    state[2] = state[1] + 0.5
    flat = np.arange(start, start + count, dtype=np.int32)
    packet = tmp_path / "packet.npz"
    np.savez_compressed(packet, state=state, forcing=forcing, flat_indices=flat)
    packet_sha = hashlib.sha256(packet.read_bytes()).hexdigest()
    manifest_bytes = json.dumps({"chunks": [{"path": "packet.npz", "sha256": packet_sha}]}).encode()
    (tmp_path / "manifest.json").write_bytes(manifest_bytes)
    qc, qv = _packet_qc_by_flat(
        {"paths": {"packets": str(tmp_path)}, "grid": {"levels": levels},
         "packet_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest()},
        0,
        flat,
    )
    assert np.array_equal(qc, state[2])
    assert np.array_equal(qv, state[1])


def test_restricted_confirmation_layout_needs_no_child_baseline(tmp_path):
    parent = tmp_path / "parent"
    confirm = tmp_path / "restricted_confirmation"
    parent.mkdir()
    confirm.mkdir()
    parent_id, candidate_id, control_sha = "parent-run", "restricted-run", "z-hash"
    chunks = [
        {"chunk_index": index, "start": index * 2, "stop": (index + 1) * 2,
         "artifact_sha256": f"{index:064x}"}
        for index in range(129)
    ]
    (parent / "CASE_MANIFEST.json").write_text(json.dumps({"run_id": parent_id}))
    (parent / "FINAL.json").write_text(json.dumps({"status": "COMPLETED_NO_ACCEPTABLE_UPDATE"}))
    (parent / "BASELINE.json").write_text(json.dumps({"full_domain": True, "globalZ": 123., "chunks": chunks}))
    (confirm / "CASE_MANIFEST.json").write_text(json.dumps({"run_id": candidate_id,
                                                              "candidate_control_z_sha256": control_sha}))
    confirmation = {
        "run_id": candidate_id, "parent_run_id": parent_id, "stage": "RESTRICTED_alpha_1p0",
        "status": "RESTRICTED_UPDATE_ACCEPTED", "controls_sha256": control_sha,
        "fixed_support_preserved": True, "globalZ": 123., "actual_objective": {"cost": 0.9},
        "chunks": [{"chunk_index": index} for index in range(129)],
    }
    (confirm / "CONFIRMATION.json").write_text(json.dumps(confirmation))
    assert not (confirm / "BASELINE.json").exists()
    result = _load_restricted_confirmation(parent, confirm)
    assert result[0]["run_id"] == parent_id
    assert result[3]["run_id"] == candidate_id
    assert result[4]["stage"] == "RESTRICTED_alpha_1p0"
    assert len(result[5]) == 129


def test_source_pin_lookup_selects_frozen_source_v3_alias():
    manifest = {"source_pins": {
        "/evidence/source_v2/oracle/kdm6/native_finish.py": "same-sha",
        "/evidence/source_v3/oracle/kdm6/native_finish.py": "same-sha",
    }}
    selected = _source_pin_record(manifest, "oracle/kdm6/native_finish.py")
    assert selected["path"] == "/evidence/source_v3/oracle/kdm6/native_finish.py"
    assert selected["sha256"] == "same-sha"


def test_source_pin_lookup_accepts_single_confirmation_checkout_pin():
    manifest = {"source_pins": {"/private/tmp/confirmation/harness/native_batch_microphysics.py": "capture-sha"}}
    selected = _source_pin_record(manifest, "harness/native_batch_microphysics.py")
    assert selected["path"] == "/private/tmp/confirmation/harness/native_batch_microphysics.py"
    assert selected["sha256"] == "capture-sha"


def test_export_full_confirmation_root_without_child_baseline_exercises_water_and_rate_paths(
    tmp_path, monkeypatch
):
    import harness.summarize_native_satellite_case as summary

    n, levels, chunk_count = 3, 39, 129
    parent = tmp_path / "parent"
    confirmation_root = tmp_path / "restricted-confirmation"
    audit_root = parent / "APPLIED_PHYSICS_AUDIT"
    audit_root.mkdir(parents=True)
    confirmation_root.mkdir()
    packet_root = tmp_path / "packets"
    packet_root.mkdir()
    output = tmp_path / "export"
    library = tmp_path / "candidate.dylib"
    library.write_bytes(b"fixture bytes; never loaded")
    lib_sha = hashlib.sha256(library.read_bytes()).hexdigest()
    source_pins = {str(library.resolve()): lib_sha}
    for suffix in ("harness/native_batch_microphysics.py", "oracle/kdm6/native_finish.py",
                   "oracle/kdm6/native_prep.py"):
        source_pins["/fixture/source_v3/" + suffix] = "physics-sha"
    config = {
        "paths": {"candidate_library": str(library), "packets": str(packet_root)},
        "grid": {"nx": n, "ny": 1, "levels": levels},
        "packet_manifest_sha256": "",
        "finish_configuration": {"dt": 20.0, "alpha": 1.6, "t0": 300.0, "mp_tend_lim": 0.05},
        "prep_configuration": {"ptop": 5000.0},
        "zero_out_configuration": {"mode": 2, "threshold": 1e-9},
        "experiment": {"factorial_mode": "norm_actual", "qr_transport": "actual_departure"},
    }
    parent_id, candidate_id, control_sha = "parent-run", "candidate-run", "control-sha"
    packet_manifest = {"chunks": [{"path": f"packet_{i:05d}.npz", "sha256": f"packet-{i}"}
                                  for i in range(chunk_count)]}
    packet_manifest_bytes = json.dumps(packet_manifest).encode()
    (packet_root / "manifest.json").write_bytes(packet_manifest_bytes)
    config["packet_manifest_sha256"] = hashlib.sha256(packet_manifest_bytes).hexdigest()
    parent_chunks = []
    parent_receipts = []
    for i in range(chunk_count):
        folder = parent / "baseline" / f"chunk_{i:05d}"
        attempt = folder / f"attempt_{i:05d}"
        attempt.mkdir(parents=True, exist_ok=True)
        artifact = attempt / "result.npz"
        artifact.write_bytes(f"baseline-artifact-{i}".encode())
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        binding = f"baseline-binding-{i}"
        entry = {"chunk_index": i, "start": 0, "stop": 1, "artifact": str(artifact),
                 "artifact_sha256": digest, "binding": binding}
        receipt = dict(entry)
        receipt_path = folder / "receipt.json"
        receipt_path.write_text(json.dumps(receipt))
        parent_chunks.append(entry)
        parent_receipts.append({"receipt_sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
                                "artifact_sha256": digest, "binding": binding})
    parent_case = {"run_id": parent_id, "source_pins": source_pins, "case_preparation": config}
    candidate_case = {"run_id": candidate_id, "candidate_control_z_sha256": control_sha,
                      "source_pins": source_pins, "case_preparation": config}
    (parent / "CASE_MANIFEST.json").write_text(json.dumps(parent_case))
    parent_manifest = {"full_domain": True, "globalZ": 21.0, "chunks": parent_chunks}
    (parent / "BASELINE.json").write_text(json.dumps(parent_manifest))
    (parent / "FINAL.json").write_text(json.dumps({"status": "COMPLETED_NO_ACCEPTABLE_UPDATE"}))
    confirmation_chunks = [{"chunk_index": i} for i in range(chunk_count)]
    confirmation = {
        "run_id": candidate_id, "parent_run_id": parent_id,
        "stage": "RESTRICTED_alpha_1p0", "status": "RESTRICTED_UPDATE_ACCEPTED",
        "fixed_support_preserved": True, "controls_sha256": control_sha,
        "globalZ": 21.0,
        "actual_objective": {"observation_numerator": 0.0, "regularization_numerator": 0.0,
                              "numerator": 0.0, "Z": 21.0, "cost": 0.0},
        "chunks": confirmation_chunks,
    }
    (confirmation_root / "CASE_MANIFEST.json").write_text(json.dumps(candidate_case))
    (confirmation_root / "CONFIRMATION.json").write_text(json.dumps(confirmation))
    assert not (confirmation_root / "BASELINE.json").exists()

    flat = np.arange(n, dtype=np.int64)
    mask = np.ones((n, 7), dtype=np.bool_)
    common = {"flat_index": flat, "finish": np.zeros((5, n, levels)), "mask": mask,
              "weights": np.ones((n, 7)), "source_eligible": mask.copy(),
              "obs_bt": np.zeros((n, 7)), "bt": np.zeros((n, 7)),
              "qv": np.zeros((n, levels))}
    candidate_arrays = {**common, "z": np.zeros((2, n, levels))}

    def fake_join(root, manifest, **kwargs):
        if Path(root).resolve() == parent.resolve():
            assert kwargs.get("trial", False) is False
            return common
        assert kwargs["trial"] is True
        assert kwargs["stage"] == confirmation["stage"]
        assert kwargs["baseline_sha_by_chunk"] == {
            entry["chunk_index"]: entry["artifact_sha256"] for entry in parent_chunks
        }
        return candidate_arrays

    def fake_read_chunk(root, entry, *, trial=False):
        assert trial is (Path(root).resolve() == confirmation_root.resolve())
        ci = int(entry["chunk_index"])
        return {"flat_index": np.array([ci % n]), "qv": np.zeros((1, levels)),
                "finish": np.zeros((5, 1, levels))}, entry

    def fake_capture(root, entry, names):
        if Path(root).resolve() == confirmation_root.resolve():
            values = {"applied_before": np.zeros((12, 1, levels)),
                      "applied_forcing": np.ones((4, 1, levels)),
                      "applied_raw": np.zeros((12, 1, levels)),
                      "applied_clean_replay": np.zeros((12, 1, levels)),
                      "applied_clean_matches_output": np.asarray(True),
                      "native_after_qv": np.zeros((1, levels))}
            values.update({name: np.zeros((1, levels)) for name in (
                "cloud_qc", "cloud_qr", "cloud_qi", "cloud_qs", "cloud_qg",
                "cloud_nn", "cloud_nc", "cloud_ni", "cloud_nr", "cloud_bg")})
        else:
            values = {"native_after_qv": np.zeros((1, levels)), "cloud_qc": np.zeros((1, levels))}
        return values, {"artifact_sha256": "fixture-artifact-sha"}

    monkeypatch.setattr(summary, "NATIVE_GRID_NX", n)
    monkeypatch.setattr(summary, "NATIVE_GRID_NY", 1)
    monkeypatch.setattr(summary, "_join_manifest", fake_join)
    monkeypatch.setattr(summary, "_read_chunk", fake_read_chunk)
    monkeypatch.setattr(summary, "_read_capture_arrays", fake_capture)
    monkeypatch.setattr(summary, "_packet_state_by_flat",
                        lambda *args: (np.zeros((12, 1, levels)), np.ones((4, 1, levels))))

    audit_chunks = []
    for ci in range(chunk_count):
        path = audit_root / f"chunk_{ci:05d}.npz"
        np.savez_compressed(
            path, rate_relation_residuals=np.zeros((3, 1, levels)),
            weights_kg_m2_by_level=np.ones((1, levels)),
            water_raw_minus_input_kg_m2=np.zeros((6, 1)),
            water_cleanup_minus_raw_kg_m2=np.zeros((6, 1)),
            water_applied_minus_input_kg_m2=np.zeros((6, 1)),
        )
        audit_chunks.append({"chunk_index": ci, "replay_npz": str(path),
                             "replay_npz_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                             "saved_artifact_sha256": parent_receipts[ci]["artifact_sha256"],
                             "saved_binding": parent_receipts[ci]["binding"],
                             "saved_receipt_sha256": parent_receipts[ci]["receipt_sha256"],
                             "source_packet_sha256": packet_manifest["chunks"][ci]["sha256"],
                             "water_column_totals_kg_m2": {
                                 key: {name: 0.0 for name in ("QV", "QC", "QR", "QI", "QS", "QG")}
                                 for key in ("raw_minus_input_kg_m2", "cleanup_minus_raw_kg_m2", "applied_minus_input_kg_m2")
                             }})
    (audit_root / "ledger.json").write_text(json.dumps({"run_id": parent_id,"phases": [{
        "all_replay_bit_gates_passed": True,"manifest_sha256": hashlib.sha256((parent/"BASELINE.json").read_bytes()).hexdigest(),
        "chunks": audit_chunks}]}))
    report = summary.export_restricted_tendencies(parent, confirmation_root, output)
    assert report["confirmation"]["fixed_support_preserved"] is True
    assert report["rate_relation_audit"]["confirmation"]["applied_clean_output_gates_passed"]
    assert set(report["exports"]) == {"H_RATE", "QV_RATE", "QC_RATE"}
    water_export = report["applied_water_diagnostics"]["per_column_export"]
    assert water_export["shape"] == [n, levels]
    with np.load(water_export["path"], allow_pickle=False) as data:
        assert data["baseline_raw_minus_input_kg_m2"].shape == (6, n)
        assert data["candidate_cleanup_minus_raw_kg_m2"].shape == (6, n)
        assert data["delta_applied_minus_input_kg_m2"].shape == (6, n)
        assert data["baseline_DEN_times_DELZ_kg_m2_by_level"].shape == (n, levels)
        assert np.array_equal(data["flat_index"], np.arange(n))
    with np.load(report["finish_inputs"]["finish_theta_coordinates"]["path"], allow_pickle=False) as data:
        assert data["before_theta"].shape == data["clean_theta"].shape == (n, levels)
        assert np.array_equal(data["flat_index"], np.arange(n))
    with np.load(report["finish_inputs"]["initial_qc"]["path"], allow_pickle=False) as data:
        assert data["initial_qc_kgkg"].shape == (n, levels)
        assert np.array_equal(data["flat_index"], np.arange(n))
    assert len(report["exporter_source_sha256"]) == 64
    for field in ("H_RATE", "QV_RATE", "QC_RATE"):
        with np.load(report["exports"][field]["path"], allow_pickle=False) as data:
            assert data["flat_index"].shape == (n,)
            assert data["baseline"].shape == data["candidate"].shape == data["delta"].shape == (n, levels)
