"""Verified recovery of completed RTTOV K output, never a new RTTOV call.

The recovery manifest is a separate post-run input: it does not rewrite the
original run identity. Fresh profile values/configuration must match before a
preserved response can enter a new first-order evaluation. FD/trial callers do
not use this path. Historical dynamic-library bytes were not attested by the
original run, so replay is not a claim of historical runtime bit parity.
"""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import re

import numpy as np

_MANIFESTS = {}


def file_sha(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            result.update(block)
    return result.hexdigest()


def case_input_files(case):
    case = Path(case)
    paths = [p for p in (case / "in").rglob("*") if p.is_file()]
    paths += [case / "out" / name for name in ("rttov_test.txt", "run.sh", "env.sh")]
    return {str(path.relative_to(case)): file_sha(path) for path in sorted(paths)}


def tree_identity(files):
    encoded = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _read_json(path, expected):
    encoded = Path(path).read_bytes()
    if hashlib.sha256(encoded).hexdigest() != expected:
        raise ValueError(f"recovery source changed: {path}")
    return json.loads(encoded)


def load_recovery(config):
    path = config.get("rttov_replay_manifest")
    if path is None:
        return None
    digest = config["rttov_replay_sha256"]
    key = (str(Path(path).resolve()), digest)
    if key in _MANIFESTS:
        return _MANIFESTS[key]
    manifest = _read_json(path, digest)
    if manifest.get("schema") != "kdm6.native_satellite_rttov_recovery_manifest.v3":
        raise ValueError("unsupported RTTOV recovery manifest")
    entries = manifest.get("entries", [])
    if sorted(entry.get("chunk_index", -1) for entry in entries) != [0, 34, 40, 128]:
        raise ValueError(
            "recovery must contain each of the four designated pilot chunks exactly once"
        )
    original = _read_json(
        manifest["source_case_manifest"], manifest["source_case_manifest_sha256"]
    )
    run_root = Path(manifest["run_root"]).resolve()
    if (
        Path(manifest["source_case_manifest"]).resolve()
        != run_root / "CASE_MANIFEST.json"
    ):
        raise ValueError("recovery original run path/manifest identity differs")
    if (
        tree_identity({k: v for k, v in original.items() if k != "run_id"})
        != original["run_id"]
    ):
        raise ValueError("original case run_id does not bind its saved manifest")
    if manifest["source_pins"] != original["source_pins"]:
        raise ValueError("recovery source pins differ from the original run")
    # These original assets/sources remain preserved. The original runtime did
    # not hash every DSO; recovery receipts retain that qualification explicitly.
    for source, expected in original["source_pins"].items():
        if file_sha(source) != expected:
            raise ValueError(f"original recovery input/source changed: {source}")
    old = original["case_preparation"]["verified_sources"]
    new = config["verified_sources"]
    for name in (
        "checkpoint",
        "observations",
        "packet_manifest",
        "prep_reference",
        "finish_reference",
    ):
        if old[name]["sha256"] != new[name]["sha256"]:
            raise ValueError(f"recovery belongs to different {name}")
    root = Path(__file__).resolve().parents[1]
    from oracle.kdm6.obs._rttov_reference import rttov_ascii

    if (
        file_sha(rttov_ascii.__file__) != manifest["parser_source_sha256"]
        or file_sha(manifest["parser_source"]) != manifest["parser_source_sha256"]
    ):
        raise ValueError("recovery curator and executed parser identities differ")
    for relative in (
        "oracle/kdm6/obs/ami_bt_coordinate.py",
        "oracle/kdm6/obs/rttov_input_builder.py",
        "oracle/kdm6/obs/rttov_case_writer.py",
        "oracle/kdm6/obs/rttov_runner.py",
        "oracle/kdm6/obs/rttov_obs_operator.py",
    ):
        matches = [
            value
            for name, value in original["source_pins"].items()
            if name.endswith("/" + relative)
        ]
        if len(matches) != 1 or matches[0] != file_sha(root / relative):
            raise ValueError(f"recovery observation arithmetic/IO changed: {relative}")
    manifest = dict(
        manifest,
        original_run_id=original["run_id"],
        recovery_manifest_sha256=digest,
        original_preparation=original["case_preparation"],
    )
    _MANIFESTS[key] = manifest
    return manifest


def _same_bits(left, right, name):
    a, b = np.asarray(left), np.asarray(right)
    if a.shape != b.shape or a.dtype != b.dtype or a.tobytes() != b.tobytes():
        raise ValueError(f"recovery input differs at {name}")


def _validate_origin(entry, manifest, rin):
    root = Path(manifest["run_root"]).resolve()
    index = entry["chunk_index"]
    folder = root / "baseline" / f"chunk_{index:05d}"
    if entry["mode"] == "raw_k":
        case = Path(entry["case_path"]).resolve()
        if (
            case.name != "case_k"
            or not case.parent.name.startswith("rttov_")
            or case.parent.parent != folder
        ):
            raise ValueError(
                "raw recovery case does not belong to its original baseline chunk"
            )
        if root / entry["case_path_from_run_root"] != case:
            raise ValueError("raw recovery source-run path aliases disagree")
        return
    if Path(entry["receipt_path"]).resolve() != folder / "receipt.json":
        raise ValueError("cached receipt is outside its original baseline chunk")
    receipt = _read_json(entry["receipt_path"], entry["receipt_sha256"])
    expected_binding = tree_identity(
        {
            "run_id": manifest["original_run_id"],
            "stage": "baseline",
            "chunk": index,
            "baseline_sha": None,
            "controls_sha": None,
        }
    )
    if (
        receipt.get("binding") != expected_binding
        or entry["receipt_binding"] != expected_binding
    ):
        raise ValueError("cached receipt belongs to a different original run/stage")
    chunk = manifest["original_preparation"]["packet_manifest"]["chunks"][index]
    if (
        receipt["chunk_index"] != index
        or receipt["start"] != chunk["start_flat"]
        or receipt["stop"] != chunk["stop_flat_exclusive"]
        or receipt["columns"] != chunk["columns"]
    ):
        raise ValueError("cached original chunk range differs")
    artifact = Path(entry["artifact_path"]).resolve()
    if (
        artifact != Path(receipt["artifact"]).resolve()
        or artifact.parent.parent != folder
        or not artifact.parent.name.startswith("attempt_")
        or artifact.name != "result.npz"
    ):
        raise ValueError("cached artifact does not belong to its original receipt")
    rt = receipt["RTTOV_receipt"]
    flags = rt.get("driver_flags", {})
    if (
        rt.get("mode") != "K"
        or rt.get("baseline_operator") is not True
        or rt.get("K_calls") != 1
        or rt.get("direct_calls") != 0
        or rt.get("nprofiles") != rin.nprofiles
        or rt.get("channels") != list(rin.config.channels)
        or rt.get("pressure_gradients") is not True
        or rt.get("bt_coordinate") != "kma_v3_0"
        or rt.get("config_hashes") != [rin.config_hash]
        or rt.get("config_hash") != rin.config_hash
        or flags.get("K_template_do_k") is not True
        or flags.get("K_template_do_direct") is not False
    ):
        raise ValueError(
            "cached receipt does not describe the requested baseline K operator"
        )


def _npz_result(entry, rin, block, rows, profile_arrays, profile_valid):
    receipt = _read_json(entry["receipt_path"], entry["receipt_sha256"])
    if receipt["artifact_sha256"] != entry["artifact_sha256"]:
        raise ValueError("cached observation receipt/artifact hash mismatch")
    encoded = Path(entry["artifact_path"]).read_bytes()
    if hashlib.sha256(encoded).hexdigest() != entry["artifact_sha256"]:
        raise ValueError("cached observation artifact changed")
    with np.load(io.BytesIO(encoded), allow_pickle=False) as archive:
        saved = {name: archive[name] for name in archive.files}
    _same_bits(saved["flat_index"], block["flat_indices"], "flat indices")
    _same_bits(
        saved["profile_rows"].astype(np.int64),
        np.asarray(rows, dtype=np.int64),
        "profile row map",
    )
    if (
        receipt["RTTOV_receipt"]["source_flat_indices"]
        != block["flat_indices"][rows].tolist()
    ):
        raise ValueError("cached RTTOV/native profile ownership differs")
    if rin.config_hash != entry["RTTOV_config_hash"]:
        raise ValueError("cached RTTOV geometry/surface/configuration differs")
    for name, value in profile_arrays.items():
        _same_bits(saved["profile_" + name], value, name)
    _same_bits(saved["obs_bt"], block["obs_bt"], "observations")
    _same_bits(saved["source_dqf"], block["obs_dqf"], "source DQF")
    _same_bits(saved["source_qc"], block["obs_qc_raw"], "source QC")
    _same_bits(saved["profile_valid"], profile_valid, "profile eligibility")
    eligible = (
        (block["obs_dqf"] == 0) & (block["obs_qc_raw"] == 0) & profile_valid[:, None]
    )
    mask = eligible & (saved["quality"] == 0)
    _same_bits(saved["source_eligible"], eligible, "pre-RT eligibility")
    _same_bits(saved["mask"], mask, "baseline support")
    _same_bits(
        saved["weights"], mask.astype(np.float64), "unique-owner baseline weights"
    )
    keys = [name for name in profile_arrays if name != "CFRAC"]
    return (
        saved["bt"][rows].copy(),
        {name: saved["K_" + name].copy() for name in keys},
        saved["quality"][rows].copy(),
        {"artifact_sha256": entry["artifact_sha256"]},
    )


def _native_ids_from_angles(case, block):
    latitude = block["native_surface"]["model_lat_deg"]
    longitude = block["native_surface"]["model_lon_deg"]
    positions = {
        (f"{lat:.6f}", f"{lon:.6f}"): int(flat)
        for lat, lon, flat in zip(latitude, longitude, block["flat_indices"])
    }
    if len(positions) != len(latitude):
        raise ValueError("native coordinates do not uniquely identify profile owners")
    result = []
    directories = sorted((Path(case) / "in/profiles").iterdir())
    for directory in directories:
        if not directory.is_dir():
            continue
        text = (directory / "angles.txt").read_text()
        values = []
        for name in ("latitude", "longitude"):
            match = re.search(rf"(?mi)^\s*{name}\s*=\s*([^\s,]+)", text)
            if match is None:
                raise ValueError(
                    "original RTTOV profile lacks native ownership coordinates"
                )
            values.append(f"{float(match[1]):.6f}")
        if tuple(values) not in positions:
            raise ValueError("original RTTOV profile has no matching native owner")
        result.append(positions[tuple(values)])
    return result


def _raw_result(entry, rin, block, rows, fresh_case):
    from oracle.kdm6.obs.ami_bt_coordinate import (
        read_ami_filters,
        read_kma_calibration,
        transform_rttov_to_kma,
    )
    from oracle.kdm6.obs._rttov_reference.rttov_ascii import parse_rttov_ascii_blocks
    from oracle.kdm6.obs.rttov_case_writer import _resolve_coef_path, add_cloud_k_slots
    from oracle.kdm6.obs.rttov_runner import parse_rttov_k_case

    original = Path(entry["case_path"])
    if set(entry.get("raw_outputs", {})) != {
        "out/k/radiance.txt",
        "out/k/profiles_k.txt",
        "out/rttov_test.log",
    }:
        raise ValueError("raw recovery omits a consumed output or execution log hash")
    old_files = case_input_files(original)
    fresh_files = case_input_files(fresh_case)
    if (
        old_files != entry["input_files"]
        or tree_identity(old_files) != entry["input_tree_sha"]
        or fresh_files != old_files
    ):
        raise ValueError(
            "regenerated RTTOV input tree/config differs from the completed raw call"
        )
    if _native_ids_from_angles(original, block) != block["flat_indices"][rows].tolist():
        raise ValueError("original raw RTTOV/native owner sequence differs")
    for name, digest in entry["raw_outputs"].items():
        if file_sha(original / name) != digest:
            raise ValueError(f"completed RTTOV raw output changed: {name}")
    failure = entry.get("source_failure_log", {})
    failure_path = original / failure.get("path", "missing_failure_receipt")
    if (
        failure.get("path") != "out/run.failure.txt"
        or not failure_path.is_file()
        or file_sha(failure_path) != failure.get("sha256")
        or failure_path.read_text().strip() != failure.get("text", "").strip()
        or not re.fullmatch(
            r"ValueError: invalid numeric token in RTTOV ASCII block: '[+-]?\d+\.\d+[+-]\d{3,}'",
            failure_path.read_text().strip(),
        )
    ):
        raise ValueError(
            "raw recovery lacks the attested parser-only failure after successful execution"
        )
    if (
        rin.nprofiles != entry["nprofiles"]
        or len(rin.config.channels) != entry["channels_per_profile"]
    ):
        raise ValueError("recovery profile/channel counts differ")
    out = parse_rttov_k_case(
        original / "out",
        nchannels=len(rin.config.channels),
        expected_nprofiles=rin.nprofiles,
    )
    add_cloud_k_slots(out.k, nlay=rin.nlayers)
    blocks = parse_rttov_ascii_blocks(original / "out/k/radiance.txt")
    radiance = np.asarray(blocks["RADIANCE%TOTAL"], dtype=np.float64).reshape(
        rin.nprofiles, len(rin.config.channels)
    )
    bt, k, _ = transform_rttov_to_kma(
        out.bt,
        radiance,
        out.k,
        rin.config.channels,
        read_ami_filters(_resolve_coef_path(original)),
        read_kma_calibration(),
    )
    return (
        bt,
        k,
        out.rad_quality,
        {
            "raw_outputs_sha256": entry["raw_outputs"],
            "input_tree_sha256": entry["input_tree_sha"],
        },
    )


def recover_k(
    rin, block, rows, profile_arrays, profile_valid, config, fresh_case, template
):
    manifest = load_recovery(config)
    if manifest is None:
        return None
    entries = [
        entry
        for entry in manifest["entries"]
        if entry["chunk_index"] == block["chunk_index"]
    ]
    if not entries:
        return None
    if len(entries) != 1:
        raise ValueError("duplicate recovery entry for one native chunk")
    entry = entries[0]
    _validate_origin(entry, manifest, rin)
    if entry["mode"] == "npz_k":
        bt, k, quality, details = _npz_result(
            entry, rin, block, rows, profile_arrays, profile_valid
        )
    elif entry["mode"] == "raw_k":
        from oracle.kdm6.obs.rttov_case_writer import write_rttov_case

        write_rttov_case(rin, fresh_case, fixture_case_dir=template, overwrite=False)
        bt, k, quality, details = _raw_result(entry, rin, block, rows, fresh_case)
    else:
        raise ValueError("unsupported RTTOV recovery mode")
    return (
        bt,
        k,
        quality,
        {
            "mode": entry["mode"],
            "source_original_run_id": manifest["original_run_id"],
            "recovery_manifest_sha256": manifest["recovery_manifest_sha256"],
            "fixed_parser_sha256": file_sha(
                Path(__file__).resolve().parents[1]
                / "oracle/kdm6/obs/_rttov_reference/rttov_ascii.py"
            ),
            "new_RTTOV_calls": 0,
            "historical_dynamic_library_bytes_attested": False,
            "scope": "preserved-output replay under original run attribution, not historical runtime parity",
            **details,
        },
    )
