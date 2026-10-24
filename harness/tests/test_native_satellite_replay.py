from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from harness import native_satellite_replay as replay


PROFILE_NAMES = (
    "T",
    "Q",
    "P",
    "P_HALF",
    "HYDRO6",
    "HYDRO7",
    "HYDRO_DEFF6",
    "HYDRO_DEFF7",
    "CFRAC",
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _profile_fixture(tmp_path: Path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    artifact = tmp_path / "result.npz"
    receipt_path = tmp_path / "receipt.json"
    flat = np.asarray([80, 81], dtype=np.int32)
    rows = np.asarray([1], dtype=np.int64)
    profile_arrays = {
        name: np.asarray([[i + 0.25, i + 0.5]], dtype=np.float64)
        for i, name in enumerate(PROFILE_NAMES)
    }
    profile_arrays["P_HALF"] = np.asarray([[100.0, 50.0, 1.0]], dtype=np.float64)
    profiles_valid = np.asarray([False, True], dtype=bool)
    obs_dqf = np.zeros((2, 7), dtype=np.uint8)
    obs_dqf[1, 1] = 1
    obs_qc = np.zeros((2, 7), dtype=np.float64)
    obs_qc[1, 2] = 1.0
    quality = np.zeros((2, 7), dtype=np.int32)
    quality[1, 3] = 2
    eligible = (obs_dqf == 0) & (obs_qc == 0) & profiles_valid[:, None]
    mask = eligible & (quality == 0)

    saved = {
        "flat_index": flat.copy(),
        "profile_rows": rows.copy(),
        "obs_bt": np.full((2, 7), 250.0, dtype=np.float64),
        "source_dqf": obs_dqf.copy(),
        "source_qc": obs_qc.copy(),
        "profile_valid": profiles_valid.copy(),
        "source_eligible": eligible.copy(),
        "quality": quality.copy(),
        "mask": mask.copy(),
        "weights": mask.astype(np.float64),
        "bt": np.arange(14, dtype=np.float64).reshape(2, 7) + 200.0,
    }
    for name, values in profile_arrays.items():
        saved["profile_" + name] = values.copy()
        if name != "CFRAC":
            saved["K_" + name] = np.arange(
                7 * values.shape[1], dtype=np.float64
            ).reshape(1, 7, values.shape[1]) + len(name)

    np.savez(artifact, **saved)
    artifact_sha = _sha(artifact)
    receipt = {
        "artifact_sha256": artifact_sha,
        "RTTOV_receipt": {"source_flat_indices": [int(flat[rows[0]])]},
    }
    receipt_path.write_text(json.dumps(receipt))
    entry = {
        "artifact_path": str(artifact),
        "artifact_sha256": artifact_sha,
        "receipt_path": str(receipt_path),
        "receipt_sha256": _sha(receipt_path),
        "RTTOV_config_hash": "rin-config-v1",
    }
    rin = SimpleNamespace(config_hash="rin-config-v1")
    block = {
        "flat_indices": flat.copy(),
        "obs_bt": saved["obs_bt"].copy(),
        "obs_dqf": obs_dqf.copy(),
        "obs_qc_raw": obs_qc.copy(),
    }
    return entry, rin, block, rows, profile_arrays, profiles_valid, saved


def _write_npz(entry, saved):
    artifact = Path(entry["artifact_path"])
    np.savez(artifact, **saved)
    entry["artifact_sha256"] = _sha(artifact)
    receipt_path = Path(entry["receipt_path"])
    receipt = json.loads(receipt_path.read_text())
    receipt["artifact_sha256"] = entry["artifact_sha256"]
    receipt_path.write_text(json.dumps(receipt))
    entry["receipt_sha256"] = _sha(receipt_path)


def test_npz_cache_replay_preserves_full_batch_contract(tmp_path):
    entry, rin, block, rows, profiles, valid, saved = _profile_fixture(tmp_path)

    bt, k_fields, quality, receipt = replay._npz_result(
        entry, rin, block, rows, profiles, valid
    )

    np.testing.assert_array_equal(bt, saved["bt"][rows])
    np.testing.assert_array_equal(quality, saved["quality"][rows])
    assert set(k_fields) == set(PROFILE_NAMES) - {"CFRAC"}
    for name in PROFILE_NAMES:
        assert saved["profile_" + name].tobytes() == profiles[name].tobytes()
        if name != "CFRAC":
            assert k_fields[name].tobytes() == saved["K_" + name].tobytes()
    assert receipt == {"artifact_sha256": entry["artifact_sha256"]}
    assert saved["flat_index"].shape == (2,)
    assert saved["profile_valid"].tolist() == [False, True]
    assert saved["source_eligible"].shape == (2, 7)
    assert saved["mask"].shape == saved["weights"].shape == (2, 7)


@pytest.mark.parametrize("field", ["T", "P_HALF", "CFRAC"])
def test_npz_replay_rejects_changed_profile_values(tmp_path, field):
    entry, rin, block, rows, profiles, valid, _ = _profile_fixture(tmp_path)
    changed = {name: value.copy() for name, value in profiles.items()}
    changed[field][0, 0] = np.nextafter(changed[field][0, 0], np.inf)

    with pytest.raises(ValueError, match=field):
        replay._npz_result(entry, rin, block, rows, changed, valid)


def test_npz_replay_rejects_profile_row_owner_and_config_drift(tmp_path):
    entry, rin, block, rows, profiles, valid, saved = _profile_fixture(tmp_path)

    changed_rows = saved.copy()
    changed_rows["profile_rows"] = np.asarray([0], dtype=np.int64)
    _write_npz(entry, changed_rows)
    with pytest.raises(ValueError, match="profile row map"):
        replay._npz_result(entry, rin, block, rows, profiles, valid)

    entry, rin, block, rows, profiles, valid, _ = _profile_fixture(tmp_path / "second")
    block["flat_indices"][1] = 99
    with pytest.raises(ValueError, match="flat indices"):
        replay._npz_result(entry, rin, block, rows, profiles, valid)

    entry, rin, block, rows, profiles, valid, _ = _profile_fixture(tmp_path / "third")
    rin.config_hash = "different-rin-config"
    with pytest.raises(ValueError, match="configuration"):
        replay._npz_result(entry, rin, block, rows, profiles, valid)


@pytest.mark.parametrize(
    ("field", "mutator", "message"),
    [
        ("source_dqf", lambda a: a.__setitem__((1, 0), 2), "source DQF"),
        ("source_qc", lambda a: a.__setitem__((1, 0), 3.0), "source QC"),
        ("profile_valid", lambda a: a.__setitem__(1, False), "profile eligibility"),
        (
            "source_eligible",
            lambda a: a.__setitem__((1, 0), False),
            "pre-RT eligibility",
        ),
        ("mask", lambda a: a.__setitem__((1, 0), False), "baseline support"),
        (
            "weights",
            lambda a: a.__setitem__((1, 0), 0.5),
            "unique-owner baseline weights",
        ),
    ],
)
def test_npz_replay_rejects_changed_observation_support(
    tmp_path, field, mutator, message
):
    entry, rin, block, rows, profiles, valid, saved = _profile_fixture(tmp_path)
    changed = {name: value.copy() for name, value in saved.items()}
    mutator(changed[field])
    _write_npz(entry, changed)

    with pytest.raises(ValueError, match=message):
        replay._npz_result(entry, rin, block, rows, profiles, valid)


def test_npz_replay_rejects_artifact_tampering(tmp_path):
    entry, rin, block, rows, profiles, valid, _ = _profile_fixture(tmp_path)
    with Path(entry["artifact_path"]).open("ab") as stream:
        stream.write(b"tampered")

    with pytest.raises(ValueError, match="artifact changed"):
        replay._npz_result(entry, rin, block, rows, profiles, valid)


def _write_raw_case(case: Path):
    (case / "in/profiles/001").mkdir(parents=True)
    (case / "in/profiles/001/atm").mkdir()
    (case / "in/profiles/001/atm/q.txt").write_text("q profile\n")
    (case / "in/profiles/001/angles.txt").write_text(
        "latitude = 35.100000\nlongitude = 129.200000\n"
    )
    (case / "in/channels.txt").write_text("10 11\n")
    (case / "in/lprofiles.txt").write_text("1 1\n")
    for rel, contents in (
        ("out/rttov_test.txt", "NML config"),
        ("out/run.sh", "run command"),
        ("out/env.sh", "environment"),
    ):
        path = case / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents)


def test_raw_case_input_tree_detects_changed_and_missing_q_file(tmp_path):
    case = tmp_path / "case"
    _write_raw_case(case)
    before = replay.case_input_files(case)
    before_identity = replay.tree_identity(before)

    q_file = case / "in/profiles/001/atm/q.txt"
    q_file.write_text("changed q profile\n")
    changed = replay.case_input_files(case)
    assert changed != before
    assert replay.tree_identity(changed) != before_identity

    q_file.unlink()
    missing = replay.case_input_files(case)
    assert "in/profiles/001/atm/q.txt" not in missing
    assert replay.tree_identity(missing) != before_identity


def _write_angles(case: Path, entries):
    for index, (latitude, longitude) in enumerate(entries, start=1):
        folder = case / "in/profiles" / f"{index:03d}"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "angles.txt").write_text(
            f"latitude = {latitude:.6f}\nlongitude = {longitude:.6f}\n"
        )


def test_native_angle_owners_are_unique_and_in_input_order(tmp_path):
    case = tmp_path / "case"
    _write_angles(case, [(35.1, 129.2), (35.2, 129.3)])
    block = {
        "flat_indices": np.asarray([44, 45], dtype=np.int32),
        "native_surface": {
            "model_lat_deg": np.asarray([35.1, 35.2]),
            "model_lon_deg": np.asarray([129.2, 129.3]),
        },
    }
    assert replay._native_ids_from_angles(case, block) == [44, 45]

    duplicate_block = {
        "flat_indices": np.asarray([44, 45], dtype=np.int32),
        "native_surface": {
            "model_lat_deg": np.asarray([35.1, 35.1]),
            "model_lon_deg": np.asarray([129.2, 129.2]),
        },
    }
    with pytest.raises(ValueError, match="uniquely identify"):
        replay._native_ids_from_angles(case, duplicate_block)

    wrong_owner_case = tmp_path / "wrong_owner"
    _write_angles(wrong_owner_case, [(35.9, 129.9)])
    with pytest.raises(ValueError, match="no matching native owner"):
        replay._native_ids_from_angles(wrong_owner_case, block)


def test_raw_replay_rejects_missing_native_owner_before_parsing(tmp_path):
    pytest.importorskip("torch", reason="oracle package imports its Torch runtime")
    case = tmp_path / "raw_case"
    _write_raw_case(case)
    for rel in ("out/k/radiance.txt", "out/k/profiles_k.txt", "out/rttov_test.log"):
        path = case / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("raw output")
    files = replay.case_input_files(case)
    entry = {
        "mode": "raw_k",
        "chunk_index": 0,
        "case_path": str(case),
        "input_files": files,
        "input_tree_sha": replay.tree_identity(files),
        "raw_outputs": {
            rel: replay.file_sha(case / rel)
            for rel in (
                "out/k/radiance.txt",
                "out/k/profiles_k.txt",
                "out/rttov_test.log",
            )
        },
    }
    fresh_case = tmp_path / "fresh_case"
    shutil.copytree(case, fresh_case)
    _write_angles(case, [(35.1, 129.2)])
    shutil.rmtree(fresh_case)
    shutil.copytree(case, fresh_case)
    files = replay.case_input_files(case)
    entry["input_files"] = files
    entry["input_tree_sha"] = replay.tree_identity(files)

    block = {
        "flat_indices": np.asarray([44, 45], dtype=np.int32),
        "native_surface": {
            "model_lat_deg": np.asarray([35.1, 35.2]),
            "model_lon_deg": np.asarray([129.2, 129.3]),
        },
    }
    with pytest.raises(ValueError, match="owner sequence differs"):
        replay._raw_result(
            entry, SimpleNamespace(), block, np.asarray([0, 1]), fresh_case
        )


def _npz_origin_fixture(tmp_path, *, chunk_index=0):
    run_root = tmp_path / "original_run"
    folder = run_root / "baseline" / f"chunk_{chunk_index:05d}"
    attempt = folder / "attempt_test"
    attempt.mkdir(parents=True)
    artifact = attempt / "result.npz"
    artifact.write_bytes(b"cached result")
    chunks = [
        {
            "start_flat": i * 512,
            "stop_flat_exclusive": min((i + 1) * 512, 65988),
            "columns": min(512, 65988 - i * 512),
        }
        for i in range(129)
    ]
    run_id = "original-run-id"
    expected_binding = replay.tree_identity(
        {
            "run_id": run_id,
            "stage": "baseline",
            "chunk": chunk_index,
            "baseline_sha": None,
            "controls_sha": None,
        }
    )
    rin = SimpleNamespace(
        nprofiles=1,
        config=SimpleNamespace(channels=[10]),
        config_hash="rin-config-hash",
    )
    receipt = {
        "binding": expected_binding,
        "chunk_index": chunk_index,
        "start": chunks[chunk_index]["start_flat"],
        "stop": chunks[chunk_index]["stop_flat_exclusive"],
        "columns": chunks[chunk_index]["columns"],
        "artifact": str(artifact),
        "RTTOV_receipt": {
            "mode": "K",
            "baseline_operator": True,
            "K_calls": 1,
            "direct_calls": 0,
            "nprofiles": 1,
            "channels": [10],
            "pressure_gradients": True,
            "bt_coordinate": "kma_v3_0",
            "config_hashes": [rin.config_hash],
            "config_hash": rin.config_hash,
            "driver_flags": {
                "K_template_do_k": True,
                "K_template_do_direct": False,
            },
        },
    }
    receipt_path = folder / "receipt.json"
    receipt_path.write_text(json.dumps(receipt))
    entry = {
        "mode": "npz_k",
        "chunk_index": chunk_index,
        "receipt_path": str(receipt_path),
        "receipt_sha256": _sha(receipt_path),
        "receipt_binding": expected_binding,
        "artifact_path": str(artifact),
    }
    manifest = {
        "run_root": str(run_root),
        "original_run_id": run_id,
        "original_preparation": {"packet_manifest": {"chunks": chunks}},
    }
    return entry, manifest, rin, receipt


def test_npz_origin_rejects_foreign_binding_and_chunk_range(tmp_path):
    entry, manifest, rin, receipt = _npz_origin_fixture(tmp_path)
    receipt["binding"] = "foreign-run-binding"
    Path(entry["receipt_path"]).write_text(json.dumps(receipt))
    entry["receipt_sha256"] = _sha(Path(entry["receipt_path"]))
    with pytest.raises(ValueError, match="different original run/stage"):
        replay._validate_origin(entry, manifest, rin)

    entry, manifest, rin, receipt = _npz_origin_fixture(tmp_path / "range")
    receipt["start"] += 1
    Path(entry["receipt_path"]).write_text(json.dumps(receipt))
    entry["receipt_sha256"] = _sha(Path(entry["receipt_path"]))
    with pytest.raises(ValueError, match="range differs"):
        replay._validate_origin(entry, manifest, rin)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("mode", "direct", "baseline K operator"),
        ("config_hash", "other-config", "baseline K operator"),
        ("K_calls", 0, "baseline K operator"),
        ("direct_calls", 1, "baseline K operator"),
    ],
)
def test_npz_origin_rejects_nonmatching_operator_contract(
    tmp_path, field, value, message
):
    entry, manifest, rin, receipt = _npz_origin_fixture(tmp_path)
    receipt["RTTOV_receipt"][field] = value
    Path(entry["receipt_path"]).write_text(json.dumps(receipt))
    entry["receipt_sha256"] = _sha(Path(entry["receipt_path"]))

    with pytest.raises(ValueError, match=message):
        replay._validate_origin(entry, manifest, rin)


@pytest.mark.parametrize("path_kind", ["receipt", "artifact"])
def test_npz_origin_rejects_paths_outside_original_chunk(tmp_path, path_kind):
    entry, manifest, rin, receipt = _npz_origin_fixture(tmp_path)
    if path_kind == "receipt":
        entry["receipt_path"] = str(tmp_path / "foreign_receipt.json")
    else:
        foreign = tmp_path / "outside_attempt.npz"
        foreign.write_bytes(b"not original artifact")
        entry["artifact_path"] = str(foreign)
        receipt["artifact"] = str(foreign)
        Path(entry["receipt_path"]).write_text(json.dumps(receipt))
        entry["receipt_sha256"] = _sha(Path(entry["receipt_path"]))

    with pytest.raises(
        ValueError, match="outside its original baseline chunk|does not belong"
    ):
        replay._validate_origin(entry, manifest, rin)


def test_raw_origin_rejects_case_outside_original_chunk(tmp_path):
    entry, manifest, _rin, _receipt = _npz_origin_fixture(tmp_path, chunk_index=34)
    outside = tmp_path / "foreign" / "rttov_other" / "case_k"
    outside.mkdir(parents=True)
    entry.update(
        mode="raw_k",
        case_path=str(outside),
        case_path_from_run_root="baseline/chunk_00034/rttov_wrong/case_k",
    )
    with pytest.raises(
        ValueError, match="does not belong to its original baseline chunk"
    ):
        replay._validate_origin(entry, manifest, SimpleNamespace())


def test_unknown_recovery_mode_is_rejected_after_origin_validation(
    tmp_path, monkeypatch
):
    entry, manifest, rin, _receipt = _npz_origin_fixture(tmp_path)
    entry["mode"] = "direct"
    monkeypatch.setattr(
        replay, "load_recovery", lambda config: {"entries": [entry], **manifest}
    )

    with pytest.raises(ValueError, match="unsupported RTTOV recovery mode"):
        replay.recover_k(
            rin,
            {"chunk_index": 0},
            np.asarray([0]),
            {},
            np.asarray([True]),
            {},
            tmp_path / "fresh",
            tmp_path / "template",
        )


def test_load_recovery_requires_all_four_designated_chunks_before_source_read(tmp_path):
    path = tmp_path / "recovery.json"
    manifest = {
        "schema": "kdm6.native_satellite_rttov_recovery_manifest.v3",
        "entries": [{"chunk_index": 0}],
        "source_case_manifest": str(tmp_path / "deliberately-absent.json"),
    }
    path.write_text(json.dumps(manifest))

    with pytest.raises(ValueError, match="each of the four designated pilot chunks"):
        replay.load_recovery(
            {"rttov_replay_manifest": path, "rttov_replay_sha256": _sha(path)}
        )


def test_load_recovery_rejects_curator_parser_identity_drift(tmp_path):
    pytest.importorskip("torch", reason="oracle parser package imports its Torch runtime")
    from oracle.kdm6.obs._rttov_reference import rttov_ascii

    run_root = tmp_path / "original_run"
    run_root.mkdir()
    source_path = run_root / "CASE_MANIFEST.json"
    verified = {
        name: {"sha256": f"{index:064x}"}
        for index, name in enumerate(
            (
                "checkpoint",
                "observations",
                "packet_manifest",
                "prep_reference",
                "finish_reference",
            ),
            start=1,
        )
    }
    original = {
        "case_preparation": {"verified_sources": verified},
        "source_pins": {},
    }
    original["run_id"] = replay.tree_identity(original)
    source_path.write_text(json.dumps(original))
    entries = [{"chunk_index": index} for index in (0, 34, 40, 128)]
    recovery = {
        "schema": "kdm6.native_satellite_rttov_recovery_manifest.v3",
        "entries": entries,
        "source_case_manifest": str(source_path),
        "source_case_manifest_sha256": _sha(source_path),
        "run_root": str(run_root),
        "source_pins": {},
        "parser_source": rttov_ascii.__file__,
        "parser_source_sha256": "0" * 64,
    }
    recovery_path = tmp_path / "recovery.json"
    recovery_path.write_text(json.dumps(recovery))
    config = {
        "rttov_replay_manifest": recovery_path,
        "rttov_replay_sha256": _sha(recovery_path),
        "verified_sources": verified,
    }

    with pytest.raises(
        ValueError, match="curator and executed parser identities differ"
    ):
        replay.load_recovery(config)


@pytest.mark.parametrize(
    ("failure_text", "correct_hash"),
    [
        ("ValueError: invalid numeric token in RTTOV ASCII block: '0.1-101'", False),
        ("ValueError: unrelated parser or runtime failure", True),
    ],
)
def test_raw_replay_requires_attested_parser_only_failure(
    tmp_path, failure_text, correct_hash
):
    pytest.importorskip("torch", reason="raw observation parser enters the oracle package")
    case = tmp_path / "case"
    _write_raw_case(case)
    _write_angles(case, [(35.1, 129.2)])
    for rel in (
        "out/k/radiance.txt",
        "out/k/profiles_k.txt",
        "out/rttov_test.log",
        "out/run.failure.txt",
    ):
        path = case / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            failure_text if rel.endswith("run.failure.txt") else "raw output"
        )
    fresh = tmp_path / "fresh"
    shutil.copytree(case, fresh)
    entry = {
        "raw_outputs": {
            rel: replay.file_sha(case / rel)
            for rel in (
                "out/k/radiance.txt",
                "out/k/profiles_k.txt",
                "out/rttov_test.log",
            )
        },
        "case_path": str(case),
        "input_files": replay.case_input_files(case),
        "input_tree_sha": replay.tree_identity(replay.case_input_files(case)),
        "source_failure_log": {
            "path": "out/run.failure.txt",
            "sha256": replay.file_sha(case / "out/run.failure.txt")
            if correct_hash
            else "0" * 64,
            "text": failure_text,
        },
    }
    block = {
        "flat_indices": np.asarray([44], dtype=np.int32),
        "native_surface": {
            "model_lat_deg": np.asarray([35.1]),
            "model_lon_deg": np.asarray([129.2]),
        },
    }

    with pytest.raises(ValueError, match="parser-only failure"):
        replay._raw_result(entry, SimpleNamespace(), block, np.asarray([0]), fresh)


def test_raw_replay_requires_hashes_for_all_consumed_outputs(tmp_path):
    pytest.importorskip("torch", reason="raw observation parser enters the oracle package")
    entry = {
        "case_path": str(tmp_path / "unused_case"),
        "raw_outputs": {"out/k/radiance.txt": "unused"},
    }

    with pytest.raises(ValueError, match="omits a consumed output"):
        replay._raw_result(
            entry, SimpleNamespace(), {}, np.asarray([], dtype=int), tmp_path
        )
