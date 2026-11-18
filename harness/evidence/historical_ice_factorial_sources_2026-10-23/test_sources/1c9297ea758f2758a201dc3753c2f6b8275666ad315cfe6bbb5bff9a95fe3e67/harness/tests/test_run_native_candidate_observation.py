import hashlib
import json
import os

import numpy as np
import pytest

from harness.run_native_candidate_observation import (
    EXPERIMENT,
    direction_vectors,
    experiment_metadata,
    make_number_source_bindings,
    require_nonempty_mask,
    require_exact_packet_qv,
    save_prepared,
    save_result,
    select_library,
    validate_output_directory,
    validate_endpoint_eligibility,
    verify_library_transport,
    _runtime_environment,
)


def test_experiment_definition_drives_native_target_directions_and_epsilons():
    experiment = experiment_metadata()
    assert experiment["factorial_mode"] == "norm_actual"
    assert experiment["qr_transport"] == "actual_departure"
    assert experiment["batch_columns"] == 512 and experiment["levels"] == 39
    assert experiment["targets"] == [
        {
            "i_1based": 131,
            "j_1based": 88,
            "flat_index0": 20488,
            "batch_index0": 40,
            "row_in_batch0": 8,
        }
    ]
    assert [row["name"] for row in experiment["directions"]] == [
        "theta_m",
        "qv",
        "mixed",
    ]
    assert experiment["epsilons"] == [1e-2, 3e-3, 1e-3]
    x = np.linspace(0.1, 1.0, 119, dtype=np.float64)
    rest = np.ones((10, 39), dtype=np.float64)
    before = x.copy()
    dirs = direction_vectors(x, rest, experiment)
    assert list(dirs) == ["theta_m", "qv", "mixed"]
    np.testing.assert_array_equal(dirs["mixed"][0], dirs["theta_m"][0] + dirs["qv"][0])
    assert all(not np.any(dr) for _, dr in dirs.values())
    np.testing.assert_array_equal(x, before)
    np.testing.assert_array_equal(rest, np.ones_like(rest))


def test_library_role_is_metadata_separate_from_qr_mode(tmp_path):
    candidate = tmp_path / "candidate.dylib"
    base = tmp_path / "base.dylib"
    candidate.write_bytes(b"candidate library")
    base.write_bytes(b"base library")
    paths = {"candidate_library": candidate, "base_library": base}
    chosen = select_library(paths, "candidate")
    other = select_library(paths, "base")
    assert chosen["role"] == "candidate" and other["role"] == "base"
    assert chosen["sha256"] != other["sha256"]
    assert EXPERIMENT["factorial_mode"] == "norm_actual"
    assert experiment_metadata()["factorial_mode"] == "norm_actual"


def test_actual_qr_requires_hash_bound_build_and_overlay_attestation(tmp_path):
    library_path = tmp_path / "kernel.dylib"
    library_path.write_bytes(b"actual QR library")
    overlay_path = tmp_path / "overlay.json"
    overlay = {
        "schema": "kdm6.actual_qr_overlay.v1",
        "candidate_mode": "actual_departure",
        "required_ice_mode": "norm_actual",
        "default": "legacy",
        "mode_environment": "KDM6_QR_TRANSPORT",
    }
    overlay_bytes = (json.dumps(overlay) + "\n").encode()
    overlay_path.write_bytes(overlay_bytes)
    source_path = tmp_path / "overlay.cpp"
    source_path.write_bytes(b"source")
    receipt_path = tmp_path / "receipt.json"
    source_hashes = {
        str(overlay_path.resolve()): hashlib.sha256(overlay_bytes).hexdigest(),
        str(source_path.resolve()): hashlib.sha256(
            source_path.read_bytes()
        ).hexdigest(),
    }
    receipt_path.write_text(
        json.dumps(
            {
                "library_sha256": hashlib.sha256(library_path.read_bytes()).hexdigest(),
                "source_sha256": source_hashes,
            }
        )
    )
    lib = select_library({"candidate_library": library_path}, "candidate")
    admitted = verify_library_transport(
        lib, "actual_departure", receipt_path, overlay_path
    )
    assert admitted["qr_transport"] == "actual_departure"
    assert admitted["transport_attestation"]["candidate_mode"] == "actual_departure"
    source_path.write_bytes(b"changed source")
    with pytest.raises(ValueError, match="source pin changed"):
        verify_library_transport(lib, "actual_departure", receipt_path, overlay_path)


def test_legacy_transport_does_not_require_actual_qr_receipt(tmp_path):
    base = tmp_path / "base.dylib"
    base.write_bytes(b"legacy library")
    lib = select_library({"base_library": base}, "base")
    selected = verify_library_transport(lib, "legacy", None, None)
    assert selected["role"] == "base"
    assert selected["qr_transport"] == "legacy"
    assert (
        selected["transport_attestation"]
        == "legacy requested; no actual-departure claim"
    )


def test_qr_environment_is_set_for_call_and_restored_afterward(monkeypatch):
    monkeypatch.setenv("KDM6_QR_TRANSPORT", "preexisting")
    monkeypatch.setenv("KDM6_ICE_FACTORIAL_MODE", "other")
    monkeypatch.setenv("KDM6_ACTUAL_QR_TRACE", "/tmp/external-trace.tsv")
    with _runtime_environment(
        {"factorial_mode": "norm_actual", "qr_transport": "actual_departure"}
    ):
        assert os.environ["KDM6_ICE_FACTORIAL_MODE"] == "norm_actual"
        assert os.environ["KDM6_QR_TRANSPORT"] == "actual_departure"
        assert os.environ["OMP_NUM_THREADS"] == "1"
        assert "KDM6_ACTUAL_QR_TRACE" not in os.environ
    assert os.environ["KDM6_QR_TRANSPORT"] == "preexisting"
    assert os.environ["KDM6_ICE_FACTORIAL_MODE"] == "other"
    assert os.environ["KDM6_ACTUAL_QR_TRACE"] == "/tmp/external-trace.tsv"
    with _runtime_environment(
        {"factorial_mode": "norm_actual", "qr_transport": "legacy"}
    ):
        assert "KDM6_QR_TRANSPORT" not in os.environ
    assert os.environ["KDM6_QR_TRANSPORT"] == "preexisting"


def test_number_receipt_binding_names_match_native_dry_number_contract():
    from harness.native_number_qualification import _validate_bindings

    experiment = experiment_metadata()
    target = experiment["targets"][0]
    native_x = np.arange(3 * experiment["levels"] + 2, dtype=np.float64)
    bindings = make_number_source_bindings(
        "a" * 64, "b" * 64, "c" * 64, native_x, target, experiment, "d" * 64
    )
    validated = _validate_bindings(bindings, experiment["levels"])
    assert {
        "trace",
        "namelist",
        "checkpoint",
        "step",
        "i",
        "j",
        "levels",
        "base_native_X_sha256",
    }.issubset(validated)
    assert validated["trace"] == "a" * 64
    assert validated["source_artifact_kind"].endswith(
        "not a target native MP_INPUT record"
    )


def test_nonempty_quality_mask_is_required():
    np.testing.assert_array_equal(
        require_nonempty_mask(np.array([0.0, 1.0])), [0.0, 1.0]
    )
    with pytest.raises(ValueError, match="no usable"):
        require_nonempty_mask(np.zeros(7))


def test_number_receipt_bindings_match_existing_native_dry_protocol():
    from harness.native_number_qualification import _validate_bindings

    experiment = experiment_metadata()
    target = experiment["targets"][0]
    native_x = np.arange(3 * experiment["levels"] + 2, dtype=np.float64)
    bindings = make_number_source_bindings(
        "a" * 64,
        "b" * 64,
        "c" * 64,
        native_x,
        target,
        experiment,
        "d" * 64,
    )
    validated = _validate_bindings(bindings, experiment["levels"])
    assert validated["trace"] == "a" * 64
    assert validated["namelist"] == "b" * 64
    assert validated["checkpoint"] == "c" * 64
    assert validated["step"] == 2 and validated["i"] == 131 and validated["j"] == 88
    assert validated["levels"] == 39
    assert (
        validated["base_native_X_sha256"]
        == hashlib.sha256(native_x.tobytes()).hexdigest()
    )
    assert validated["source_artifact_kind"].endswith(
        "not a target native MP_INPUT record"
    )


def test_checkpoint_qv_must_match_packet_qv_bitwise():
    qv = np.array([0.01, 0.02, 0.03], dtype=np.float64)
    require_exact_packet_qv(qv, qv.copy())
    changed = qv.copy()
    changed[1] = np.nextafter(changed[1], np.inf)
    with pytest.raises(ValueError, match="differs bitwise"):
        require_exact_packet_qv(qv, changed)


def test_endpoint_eligibility_retains_each_independent_gate():
    reference = {
        "quality": np.array([0, 0, 1], dtype=np.int32),
        "mask": np.array([1, 1, 0], dtype=np.float64),
        "endpoint_cfrac": np.array([0.2, 0.3]),
        "endpoint_signature": np.array([[1, 1], [0, 1]], dtype=np.int8),
    }
    assert validate_endpoint_eligibility(reference, reference.copy()) == {
        "quality": True,
        "mask": True,
        "endpoint_cfrac": True,
        "endpoint_signature": True,
        "eligible": True,
    }
    changed = dict(reference)
    changed["endpoint_signature"] = reference["endpoint_signature"].copy()
    changed["endpoint_signature"][0, 1] = 0
    result = validate_endpoint_eligibility(reference, changed)
    assert not result["endpoint_signature"] and not result["eligible"]


def test_save_result_reuses_one_experiment_definition_and_preserves_endpoint_arrays(
    tmp_path,
):
    experiment = experiment_metadata()
    prepared = {"experiment": experiment, "target": experiment["targets"][0]}
    result = {
        "experiment": experiment_metadata(),
        "target": experiment["targets"][0],
        "endpoint_cfrac": [0.1, 0.2],
        "endpoint_signature": [[1, 0]],
        "direction_checks": {
            "theta_m": {
                "trials": [
                    {
                        "plus_endpoint_cfrac": [0.1, 0.2],
                        "minus_endpoint_cfrac": [0.1, 0.2],
                        "plus_endpoint_signature": [[1, 0]],
                        "minus_endpoint_signature": [[1, 0]],
                    }
                ]
            }
        },
    }
    save_prepared(tmp_path, prepared)
    save_result(tmp_path, prepared, result)
    saved_prepared = json.loads((tmp_path / "prepared.json").read_text())
    saved_result = json.loads((tmp_path / "baseline.json").read_text())
    assert saved_prepared["experiment"] == saved_result["experiment"]
    assert saved_result["endpoint_cfrac"] == [0.1, 0.2]
    assert saved_result["endpoint_signature"] == [[1, 0]]
    assert saved_result["direction_checks"]["theta_m"]["trials"][0][
        "plus_endpoint_signature"
    ] == [[1, 0]]


def test_output_preflight_rejects_source_input_overlap_and_symlink(tmp_path):
    source = tmp_path / "repo"
    source.mkdir()
    template = tmp_path / "template"
    template.mkdir()
    packets = tmp_path / "packets"
    packets.mkdir()
    safe = validate_output_directory(
        tmp_path / "output",
        {"template": template, "packets": packets},
        source_root=source,
    )
    assert safe == (tmp_path / "output").resolve()
    with pytest.raises(ValueError, match="source tree"):
        validate_output_directory(source / "output", {}, source_root=source)
    with pytest.raises(ValueError, match="overlaps input template"):
        validate_output_directory(
            template / "output", {"template": template}, source_root=source
        )
    target = tmp_path / "link_target"
    target.mkdir()
    link = tmp_path / "output_link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="must be new"):
        validate_output_directory(link, {}, source_root=source)
    alias = tmp_path / "parent_link"
    alias.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="traverse a symlink"):
        validate_output_directory(alias / "output", {}, source_root=source)
