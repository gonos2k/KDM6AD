"""Independently replay the saved full-domain native f32 T/QV update.

This audit reads the public restricted-candidate NPZs and source-pinned saved
baseline arrays. It runs no KDM, RTTOV, host, optimizer, or observation code.
The requested input delta remains distinct from the candidate-state-minus-
background reconstruction, which can differ in its last f64 bits.
"""

from __future__ import annotations

import argparse
from io import BytesIO
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from harness.native_analysis_control import prepare_effective_analysis  # noqa: E402
from harness.native_satellite_objective import REGULARIZATION_LAMBDA, prepare_representable_control  # noqa: E402


SCHEMA = "kdm6.effective_analysis_audit.v1"
NX, NY, LEVELS = 234, 282, 39
COLUMNS = NX * NY
CHUNK_COLUMNS = 512
PARENT_RUN = Path("/Users/yhlee/KDM6AD-k/host/research_evidence/native_satellite_case_20261024/RUN_v4")
RESTRICTED_DATA = Path(__file__).resolve().parent / "evidence/native_satellite_restricted_2026-10-25/data"
BLOCK22_EVIDENCE = Path(__file__).resolve().parent / "evidence/native_block22_response_2026-10-25"
PUBLIC_CASE_DATA = Path(__file__).resolve().parent / "evidence/native_satellite_case_2026-10-25/data"
PUBLIC_SUPPORT_NPZ = PUBLIC_CASE_DATA / "observation_support.npz"
PUBLIC_STATE_NPZ = PUBLIC_CASE_DATA / "native_state_controls.npz"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "evidence/effective_analysis_2026-10-25/audit_v5"
BACKGROUND_CHECKPOINT_SHA256 = "7a353f1fa4f6636864ac169c9ee8d16869d1f38c8e998762c19659404cbb9c8e"


class AuditError(ValueError):
    """Unpinned or inconsistent saved effective-analysis inputs."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def same_bits(left, right) -> bool:
    a, b = np.asarray(left), np.asarray(right)
    return a.shape == b.shape and a.dtype == b.dtype and a.tobytes(order="C") == b.tobytes(order="C")


def _finite(value, name: str, shape=None, dtype=None) -> np.ndarray:
    array = np.asarray(value)
    if array.dtype.hasobject or array.dtype.kind not in "fiu b".replace(" ", ""):
        raise AuditError(f"{name} must be a real numeric non-object array")
    if dtype is not None and array.dtype != np.dtype(dtype):
        raise AuditError(f"{name} must have dtype {np.dtype(dtype)}")
    if shape is not None and array.shape != shape:
        raise AuditError(f"{name} shape {array.shape} differs from {shape}")
    if not np.isfinite(array).all():
        raise AuditError(f"{name} contains nonfinite values")
    return array


def _load_npz(path: Path, expected_sha: str | None = None) -> tuple[dict, str]:
    raw = Path(path).read_bytes()
    digest = sha256(raw)
    if expected_sha is not None and digest != expected_sha:
        raise AuditError(f"{path} differs from its manifest SHA-256")
    with np.load(BytesIO(raw), allow_pickle=False) as archive:
        arrays = {name: np.asarray(archive[name]) for name in archive.files}
    for name, value in arrays.items():
        _finite(value, f"{Path(path).name}.{name}")
    return arrays, digest


def _load_full_parent_baseline(public_baseline: Path | None = None) -> tuple[np.ndarray, np.ndarray, list[dict], dict]:
    if public_baseline is not None:
        arrays, digest = _load_npz(public_baseline)
        flat = _finite(arrays["flat_index"], "public baseline.flat_index", (COLUMNS,), np.int32)
        theta = _finite(arrays["theta_m"], "public baseline.theta_m", (COLUMNS, LEVELS), np.float64)
        qv = _finite(arrays["qv"], "public baseline.qv", (COLUMNS, LEVELS), np.float64)
        if not np.array_equal(flat, np.arange(COLUMNS, dtype=np.int32)):
            raise AuditError("public baseline flat indices do not cover native columns in order")
        if not same_bits(theta, theta.astype(np.float32).astype(np.float64)) or not same_bits(qv, qv.astype(np.float32).astype(np.float64)):
            raise AuditError("public baseline theta_m/QV are not exact widened binary32 states")
        return theta, qv, [], {
            "case_manifest_sha256": None,
            "run_id": None,
            "chunk_count": None,
            "mode": "public_native_state_controls_npz",
            "baseline_npz_sha256": digest,
        }
    case_manifest_path = PARENT_RUN / "CASE_MANIFEST.json"
    case_manifest_raw = case_manifest_path.read_bytes()
    case_manifest = json.loads(case_manifest_raw)
    grid = case_manifest.get("case_preparation", {}).get("grid", {})
    if (grid.get("nx"), grid.get("ny"), grid.get("levels"), grid.get("columns")) != (NX, NY, LEVELS, COLUMNS):
        raise AuditError("parent RUN_v4 grid metadata differs from native full-domain layout")
    theta = np.empty((COLUMNS, LEVELS), dtype=np.float64)
    qv = np.empty_like(theta)
    seen = np.zeros(COLUMNS, dtype=np.bool_)
    pins = []
    chunks = (COLUMNS + CHUNK_COLUMNS - 1) // CHUNK_COLUMNS
    for chunk in range(chunks):
        chunk_dir = PARENT_RUN / "baseline" / f"chunk_{chunk:05d}"
        receipt_path = chunk_dir / "receipt.json"
        receipt_raw = receipt_path.read_bytes()
        receipt = json.loads(receipt_raw)
        artifact = Path(receipt["artifact"])
        artifact_raw = artifact.read_bytes()
        artifact_sha = sha256(artifact_raw)
        if artifact_sha != receipt["artifact_sha256"]:
            raise AuditError(f"parent baseline chunk {chunk} result differs from receipt")
        start, stop = chunk * CHUNK_COLUMNS, min((chunk + 1) * CHUNK_COLUMNS, COLUMNS)
        if (receipt.get("chunk_index"), receipt.get("start"), receipt.get("stop"), receipt.get("columns")) != (chunk, start, stop, stop - start):
            raise AuditError(f"parent baseline chunk {chunk} metadata is not the original schedule")
        with np.load(BytesIO(artifact_raw), allow_pickle=False) as archive:
            flat = _finite(archive["flat_index"], f"parent chunk{chunk}.flat_index", (stop - start,), np.int32)
            theta_block = _finite(archive["theta_m"], f"parent chunk{chunk}.theta_m", (stop - start, LEVELS), np.float64)
            qv_block = _finite(archive["qv"], f"parent chunk{chunk}.qv", (stop - start, LEVELS), np.float64)
        expected_flat = np.arange(start, stop, dtype=np.int32)
        if not np.array_equal(flat, expected_flat) or seen[flat].any():
            raise AuditError(f"parent baseline chunk {chunk} flat-index order/coverage mismatch")
        theta[flat] = theta_block
        qv[flat] = qv_block
        seen[flat] = True
        pins.append({
            "chunk_index": chunk,
            "receipt_relative_path": str(receipt_path.relative_to(PARENT_RUN)),
            "receipt_sha256": sha256(receipt_raw),
            "artifact_sha256": artifact_sha,
            "flat_range": [start, stop],
        })
    if not seen.all():
        raise AuditError("parent RUN_v4 baseline does not cover all 65,988 columns")
    if not same_bits(theta, theta.astype(np.float32).astype(np.float64)) or not same_bits(qv, qv.astype(np.float32).astype(np.float64)):
        raise AuditError("parent baseline theta_m/QV are not exact widened binary32 states")
    return theta, qv, pins, {
        "case_manifest_sha256": sha256(case_manifest_raw),
        "run_id": case_manifest.get("run_id"),
        "chunk_count": chunks,
        "mode": "private_run_v4_receipt_reconstruction",
        "baseline_npz_sha256": None,
    }


def _flat_to_native(array: np.ndarray) -> np.ndarray:
    """Public flat order is flat=j*NX+i; helper uses native (i,k,j)."""
    if array.shape != (COLUMNS, LEVELS):
        raise AuditError(f"flat T/QV array shape {array.shape} differs from (65988,39)")
    return np.ascontiguousarray(array.reshape(NY, NX, LEVELS).transpose(1, 2, 0))


def _native_to_flat(array: np.ndarray) -> np.ndarray:
    if array.shape != (NX, LEVELS, NY):
        raise AuditError(f"native T/QV array shape {array.shape} differs from (234,39,282)")
    return np.ascontiguousarray(array.transpose(2, 0, 1).reshape(COLUMNS, LEVELS))


def _scalar_f32_update(background_t, background_q, request_t, request_q) -> dict:
    """Independent f32 cast/add replay, preserving each zero component's old bits."""
    old_t = np.asarray(background_t, dtype=np.float32)
    old_q = np.asarray(background_q, dtype=np.float32)
    req_t = np.asarray(request_t, dtype=np.float64)
    req_q = np.asarray(request_q, dtype=np.float64)
    if old_t.shape != old_q.shape or old_t.shape != req_t.shape or old_t.shape != req_q.shape:
        raise AuditError("scalar f32 replay operands must have matching shapes")
    if not np.isfinite(old_t).all() or not np.isfinite(old_q).all() or not np.isfinite(req_t).all() or not np.isfinite(req_q).all():
        raise AuditError("scalar f32 replay operands must be finite")
    req_t32 = np.asarray(req_t, dtype=np.float32)
    req_q32 = np.asarray(req_q, dtype=np.float32)
    requested_t = req_t != 0.0
    requested_q = req_q != 0.0
    underflow_t = requested_t & (req_t32 == np.float32(0.0))
    underflow_q = requested_q & (req_q32 == np.float32(0.0))
    overflow_t = requested_t & ~np.isfinite(req_t32)
    overflow_q = requested_q & ~np.isfinite(req_q32)
    if np.any(underflow_t) or np.any(underflow_q) or np.any(overflow_t) or np.any(overflow_q):
        raise AuditError("requested f64 increment underflows/overflows binary32")
    new_t = np.array(old_t, dtype=np.float32, order="C", copy=True)
    new_q = np.array(old_q, dtype=np.float32, order="C", copy=True)
    apply_t = req_t32 != np.float32(0.0)
    apply_q = req_q32 != np.float32(0.0)
    with np.errstate(over="ignore", invalid="ignore"):
        new_t[apply_t] = np.add(old_t[apply_t], req_t32[apply_t], dtype=np.float32)
        new_q[apply_q] = np.add(old_q[apply_q], req_q32[apply_q], dtype=np.float32)
        total_theta_m = np.add(new_t, np.float32(300.0), dtype=np.float32)
    if not np.isfinite(new_t).all() or not np.isfinite(new_q).all() or not np.isfinite(total_theta_m).all():
        raise AuditError("effective native f32 state is nonfinite")
    if np.any(new_q < np.float32(0.0)) or np.any(total_theta_m <= np.float32(0.0)):
        raise AuditError("effective native f32 state violates theta_m/QV validity")
    changed_t = new_t.view(np.uint32) != old_t.view(np.uint32)
    changed_q = new_q.view(np.uint32) != old_q.view(np.uint32)
    return {
        "background_theta_f32": old_t,
        "background_qv_f32": old_q,
        "requested_theta_f32": req_t32,
        "requested_qv_f32": req_q32,
        "effective_theta_f32": new_t,
        "effective_qv_f32": new_q,
        "changed_theta_mask": changed_t,
        "changed_qv_mask": changed_q,
        "changed_pair_mask": changed_t | changed_q,
        "requested_pair_mask": requested_t | requested_q,
        "underflow_theta_count": int(np.count_nonzero(underflow_t)),
        "underflow_qv_count": int(np.count_nonzero(underflow_q)),
        "overflow_theta_count": int(np.count_nonzero(overflow_t)),
        "overflow_qv_count": int(np.count_nonzero(overflow_q)),
    }


def _array_stats(array: np.ndarray) -> dict:
    value = np.asarray(array, dtype=np.float64)
    flat = value.ravel()
    return {
        "shape": list(value.shape),
        "nonzero_count": int(np.count_nonzero(value)),
        "min": float(np.min(value)) if value.size else 0.0,
        "max": float(np.max(value)) if value.size else 0.0,
        "max_abs": float(np.max(np.abs(value))) if value.size else 0.0,
        "mean_abs": float(np.mean(np.abs(value))) if value.size else 0.0,
        "sum_fsum": math.fsum(map(float, flat)),
    }


def _component_counts(delta_t, delta_q, changed_t, changed_q) -> dict:
    requested_t, requested_q = delta_t != 0.0, delta_q != 0.0
    changed_t = np.asarray(changed_t, dtype=np.bool_)
    changed_q = np.asarray(changed_q, dtype=np.bool_)
    requested_pairs = requested_t | requested_q
    changed_pairs = changed_t | changed_q
    return {
        "requested_nonzero_pairs": int(np.count_nonzero(requested_pairs)),
        "requested_nonzero_theta_components": int(np.count_nonzero(requested_t)),
        "requested_nonzero_qv_components": int(np.count_nonzero(requested_q)),
        "requested_nonzero_both_components": int(np.count_nonzero(requested_t & requested_q)),
        "changed_pairs": int(np.count_nonzero(changed_pairs)),
        "noop_requested_pairs": int(np.count_nonzero(requested_pairs & ~changed_pairs)),
        "changed_theta_components": int(np.count_nonzero(changed_t)),
        "changed_qv_components": int(np.count_nonzero(changed_q)),
        "changed_both_components": int(np.count_nonzero(changed_t & changed_q)),
        "theta_only_changed_pairs": int(np.count_nonzero(changed_t & ~changed_q)),
        "qv_only_changed_pairs": int(np.count_nonzero(changed_q & ~changed_t)),
        "empty_pairs": int(requested_pairs.size - np.count_nonzero(requested_pairs)),
        "zero_effect_requested_theta_components": int(np.count_nonzero(requested_t & ~changed_t)),
        "zero_effect_requested_qv_components": int(np.count_nonzero(requested_q & ~changed_q)),
    }


def _output_files(output_dir: Path, report: dict, arrays: dict) -> None:
    if output_dir.exists() or output_dir.is_symlink():
        raise FileExistsError(f"evidence directory must be new: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=False)
    arrays_path = output_dir / "effective_analysis_arrays.npz"
    with arrays_path.open("xb") as stream:
        np.savez_compressed(stream, **arrays)
        stream.flush()
    report = dict(report)
    report["outputs"] = {
        "arrays_file": arrays_path.name,
        "arrays_sha256": sha256_file(arrays_path),
        "arrays_bytes": arrays_path.stat().st_size,
    }
    report_path = output_dir / "audit.json"
    encoded = (json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    with report_path.open("xb") as stream:
        stream.write(encoded)
        stream.flush()


def audit(output_dir: Path = DEFAULT_OUTPUT, *, public_baseline: Path | None = None,
          support_path: Path = PUBLIC_SUPPORT_NPZ) -> dict:
    output_dir = Path(output_dir)
    if output_dir.exists() or output_dir.is_symlink():
        raise FileExistsError(f"evidence directory must be new: {output_dir}")

    candidate_delta_path = RESTRICTED_DATA / "candidate_input_delta.npz"
    candidate_state_path = RESTRICTED_DATA / "candidate_input_state.npz"
    controls_path = RESTRICTED_DATA / "restricted_controls.npz"
    sourcebound_path = RESTRICTED_DATA / "restricted_candidate_sourcebound.json"
    publication_path = RESTRICTED_DATA / "publication_manifest.json"
    summary_path = RESTRICTED_DATA / "summary.json"
    screen_path = RESTRICTED_DATA / "restricted_block_screen.json"
    checkpoint_manifest_path = RESTRICTED_DATA / "execution/CASE_MANIFEST.json"
    block22_manifest_path = BLOCK22_EVIDENCE / "input_manifest.json"
    block22_saved_path = BLOCK22_EVIDENCE / "saved_fields.npz"
    for path in (candidate_delta_path, candidate_state_path, controls_path, sourcebound_path,
                 publication_path, summary_path, screen_path, support_path,
                 block22_manifest_path, block22_saved_path, checkpoint_manifest_path):
        if not Path(path).is_file():
            raise FileNotFoundError(path)
    if public_baseline is None and not (PARENT_RUN / "CASE_MANIFEST.json").is_file():
        raise FileNotFoundError(PARENT_RUN / "CASE_MANIFEST.json")

    delta_arrays, delta_sha = _load_npz(candidate_delta_path)
    state_arrays, state_sha = _load_npz(candidate_state_path)
    controls_arrays, controls_file_sha = _load_npz(controls_path)
    sourcebound_raw = sourcebound_path.read_bytes()
    publication_raw = publication_path.read_bytes()
    summary_raw = summary_path.read_bytes()
    screen = json.loads(screen_path.read_text())
    checkpoint_manifest_raw = checkpoint_manifest_path.read_bytes()
    checkpoint_manifest = json.loads(checkpoint_manifest_raw)
    verified_checkpoint = checkpoint_manifest.get("case_preparation", {}).get("verified_sources", {}).get("checkpoint", {}).get("sha256")
    if verified_checkpoint != BACKGROUND_CHECKPOINT_SHA256:
        raise AuditError("source checkpoint SHA differs from the case manifest")
    support_sha = sha256_file(support_path)
    if support_sha != screen["input_artifact_sha256"]["observation_support.npz"]:
        raise AuditError("original pre-projection observation support differs from its hash pin")
    with np.load(support_path, allow_pickle=False) as support_archive:
        original_support = {name: np.asarray(support_archive[name]) for name in support_archive.files}
    original_active = _finite(original_support["active"], "observation_support.active", (2, COLUMNS, LEVELS), np.bool_)
    support_flat = _finite(original_support["flat_index"], "observation_support.flat_index", (COLUMNS,), np.int32)
    if not np.array_equal(support_flat, np.arange(COLUMNS, dtype=np.int32)):
        raise AuditError("original support flat indices do not cover native columns in order")
    block22_manifest_raw = block22_manifest_path.read_bytes()
    block22_saved_raw = block22_saved_path.read_bytes()
    sourcebound = json.loads(sourcebound_raw)
    publication = json.loads(publication_raw)
    summary = json.loads(summary_raw)
    block22_manifest = json.loads(block22_manifest_raw)
    if publication.get("accepted") is not True or summary.get("accepted") is not True:
        raise AuditError("restricted candidate is not the published accepted candidate")
    if sourcebound.get("schema") != "kdm6.native_satellite_restricted_candidate.v1":
        raise AuditError("restricted candidate source-bound schema differs")
    if float(sourcebound.get("selected_alpha")) != 1.0:
        raise AuditError("source-bound accepted candidate alpha is not 1.0")
    if controls_file_sha != sourcebound.get("control_npz_sha256"):
        raise AuditError("restricted control NPZ differs from its source-bound hash")
    controls_z_sha = sha256(np.ascontiguousarray(controls_arrays["z"], dtype=np.float64).tobytes(order="C"))
    if controls_z_sha != summary.get("controls_sha256") or controls_z_sha != sourcebound.get("control_z_sha256"):
        raise AuditError("restricted control array digest differs from published control hash")
    if sha256_file(candidate_delta_path) != publication["artifacts"][candidate_delta_path.name]["sha256"]:
        raise AuditError("candidate input delta NPZ differs from publication manifest")
    if sha256_file(candidate_state_path) != publication["artifacts"][candidate_state_path.name]["sha256"]:
        raise AuditError("candidate input state NPZ differs from publication manifest")

    flat = _finite(delta_arrays["flat_index"], "candidate_input_delta.flat_index", (COLUMNS,), np.int32)
    state_flat = _finite(state_arrays["flat_index"], "candidate_input_state.flat_index", (COLUMNS,), np.int32)
    expected_flat = np.arange(COLUMNS, dtype=np.int32)
    if not np.array_equal(flat, expected_flat) or not np.array_equal(state_flat, expected_flat):
        raise AuditError("restricted inputs must be complete ordered flat-index arrays")
    requested_theta = _finite(delta_arrays["delta_theta"], "delta_theta", (COLUMNS, LEVELS), np.float64)
    requested_qv = _finite(delta_arrays["delta_qv"], "delta_qv", (COLUMNS, LEVELS), np.float64)
    frozen_rows = np.asarray(delta_arrays["frozen_control_rows"])
    if frozen_rows.shape != (COLUMNS,) or frozen_rows.dtype != np.bool_:
        raise AuditError("frozen_control_rows must be bool[65988]")
    state_theta = _finite(state_arrays["theta_m"], "candidate theta_m", (COLUMNS, LEVELS), np.float64)
    state_qv = _finite(state_arrays["qv"], "candidate qv", (COLUMNS, LEVELS), np.float64)
    z = _finite(controls_arrays["z"], "restricted_controls.z", (2, COLUMNS, LEVELS), np.float64)
    if not same_bits(flat, state_flat):
        raise AuditError("candidate input state/delta flat index arrays differ")

    baseline_theta, baseline_qv, baseline_chunk_pins, baseline_info = _load_full_parent_baseline(public_baseline)
    if not same_bits(state_theta, baseline_theta + requested_theta) or not same_bits(state_qv, baseline_qv + requested_qv):
        raise AuditError("candidate input state is not exact f64 background plus the persisted request arrays")
    if not same_bits(controls_arrays["z"], controls_arrays["z"].astype(np.float64)):
        raise AuditError("restricted controls z must be finite f64")
    alpha = float(sourcebound["selected_alpha"])
    proposed_theta_formula = 0.2 * alpha * z[0]
    proposed_qv_formula = 0.02 * alpha * baseline_qv * z[1]
    delta_formula = {
        "theta_m_bitwise_matches_stored": same_bits(proposed_theta_formula, requested_theta),
        "qv_bitwise_matches_stored": same_bits(proposed_qv_formula, requested_qv),
        "theta_m_max_abs_difference": float(np.max(np.abs(proposed_theta_formula - requested_theta))),
        "qv_max_abs_difference": float(np.max(np.abs(proposed_qv_formula - requested_qv))),
    }
    if not delta_formula["theta_m_bitwise_matches_stored"] or not delta_formula["qv_bitwise_matches_stored"]:
        raise AuditError("stored request arrays differ from source-bound proposal scales*z")

    if summary.get("native_columns") != COLUMNS or summary.get("original_blocks") != 129:
        raise AuditError("published summary domain/block counts differ from full original grid")
    if sourcebound.get("freeze_blocks_0based") != summary.get("freeze_blocks_0based"):
        raise AuditError("source-bound and published frozen block masks differ")
    expected_frozen = np.isin(flat // CHUNK_COLUMNS, np.asarray(sourcebound["freeze_blocks_0based"], dtype=np.int64))
    if not np.array_equal(expected_frozen, frozen_rows):
        raise AuditError("frozen_control_rows differs from complete original block mask")
    if np.any(z[:, frozen_rows] != 0.0):
        raise AuditError("restricted control z is nonzero in a frozen original block")
    if original_active.shape != (2, COLUMNS, LEVELS):
        raise AuditError("original pre-projection active mask shape changed")
    active_after_freeze = original_active & ~frozen_rows[None, :, None]
    if np.any(original_active[:, frozen_rows] & (z[:, frozen_rows] != 0.0)):
        raise AuditError("accepted z is nonzero in a frozen block that remains active in the original mask")

    # Public block22 saved fields independently anchor the full-domain source extraction.
    if block22_manifest.get("input_npz", {}).get("sha256") != sha256(block22_saved_raw):
        raise AuditError("public saved block22 NPZ differs from its manifest")
    with np.load(BytesIO(block22_saved_raw), allow_pickle=False) as archive:
        block22 = {name: np.asarray(archive[name]) for name in archive.files}
    b22 = slice(11264, 11776)
    block22_checks = {
        "theta_m": same_bits(baseline_theta[b22], block22["baseline_theta_m"]),
        "qv": same_bits(baseline_qv[b22], block22["baseline_qv"]),
        "flat_index": same_bits(flat[b22], block22["flat_index"]),
    }
    if not all(block22_checks.values()):
        raise AuditError(f"full baseline reconstruction differs from public block22 anchor: {block22_checks}")

    old_t32, old_q32 = baseline_theta.astype(np.float32), baseline_qv.astype(np.float32)
    if not same_bits(baseline_theta, old_t32.astype(np.float64)) or not same_bits(baseline_qv, old_q32.astype(np.float64)):
        raise AuditError("saved background states are not exact widened binary32 values")
    scalar = _scalar_f32_update(baseline_theta, baseline_qv, requested_theta, requested_qv)
    request_mask = scalar["requested_pair_mask"]
    noops = request_mask & ~scalar["changed_pair_mask"]
    # The candidate-state subtraction is only an alternate reconstructed request;
    # never replace the persisted requested delta with this rounded subtraction.
    reconstructed_theta = state_theta - baseline_theta
    reconstructed_qv = state_qv - baseline_qv
    reconstructed_scalar = _scalar_f32_update(baseline_theta, baseline_qv, reconstructed_theta, reconstructed_qv)

    # Native Fortran ordering is (i,k,j); public NPZ flat order is flat=j*NX+i.
    def to_native(value):
        return np.ascontiguousarray(value.reshape(NY, NX, LEVELS).transpose(1, 2, 0))

    def to_flat(value):
        return np.ascontiguousarray(value.transpose(2, 0, 1).reshape(COLUMNS, LEVELS))

    unchanged = ~request_mask
    api_result = prepare_effective_analysis(
        to_native(old_t32), to_native(old_q32),
        to_native(requested_theta), to_native(requested_qv), to_native(unchanged),
        bounds=(1, NX, 1, LEVELS, 1, NY),
    )
    api_effective_theta = to_flat(api_result.effective_theta_m)
    api_effective_qv = to_flat(api_result.effective_qv)
    api_wire_theta = to_flat(api_result.delta_theta_m)
    api_wire_qv = to_flat(api_result.delta_qv)
    api_changed = to_flat(api_result.changed_mask)
    independent_api_checks = {
        "effective_theta_m_bitwise": same_bits(api_effective_theta, scalar["effective_theta_f32"]),
        "effective_qv_bitwise": same_bits(api_effective_qv, scalar["effective_qv_f32"]),
        "wire_delta_theta_m_bitwise": same_bits(api_wire_theta, np.where(scalar["changed_theta_mask"], scalar["requested_theta_f32"], np.float32(0.0))),
        "wire_delta_qv_bitwise": same_bits(api_wire_qv, np.where(scalar["changed_qv_mask"], scalar["requested_qv_f32"], np.float32(0.0))),
        "changed_pair_mask_bitwise": same_bits(api_changed, scalar["changed_pair_mask"]),
        "counts_equal_scalar": api_result.counts == {
            "requested_points": int(np.count_nonzero(request_mask)),
            "noop_points": int(np.count_nonzero(noops)),
            "applied_points": int(np.count_nonzero(scalar["changed_pair_mask"])),
            "empty_points": int(COLUMNS * LEVELS - np.count_nonzero(request_mask)),
            "requested_nonzero_components": int(np.count_nonzero(requested_theta) + np.count_nonzero(requested_qv)),
            "applied_components": int(np.count_nonzero(scalar["changed_theta_mask"]) + np.count_nonzero(scalar["changed_qv_mask"])),
            "zero_effect_components": int(np.count_nonzero((requested_theta != 0.0) & ~scalar["changed_theta_mask"]) + np.count_nonzero((requested_qv != 0.0) & ~scalar["changed_qv_mask"])),
        },
    }
    if not all(independent_api_checks.values()):
        raise AuditError(f"independent scalar f32 replay differs from prepare_effective_analysis: {independent_api_checks}")

    # Use the original pre-projection active mask. The 25 later-frozen blocks
    # stay marked active here, but their accepted z values are exactly zero.
    active_mask = original_active
    representable = prepare_representable_control(
        np.stack((baseline_theta, baseline_qv)), z, active_mask,
        horizontal_shape=(NY, NX),
        background_checkpoint_id=BACKGROUND_CHECKPOINT_SHA256,
    )
    representable_checks = {
        "request_theta_matches_stored_numeric": bool(np.array_equal(representable["requested_delta"][0], requested_theta)),
        "request_qv_matches_stored_numeric": bool(np.array_equal(representable["requested_delta"][1], requested_qv)),
        "candidate_theta_bitwise_matches_effective_api": same_bits(representable["candidate"][0], api_effective_theta.astype(np.float64)),
        "candidate_qv_bitwise_matches_effective_api": same_bits(representable["candidate"][1], api_effective_qv.astype(np.float64)),
        "applied_delta_theta_bitwise_matches_state_difference": same_bits(representable["applied_delta"][0], api_effective_theta.astype(np.float64) - baseline_theta),
        "applied_delta_qv_bitwise_matches_state_difference": same_bits(representable["applied_delta"][1], api_effective_qv.astype(np.float64) - baseline_qv),
    }
    if not all(representable_checks.values()):
        raise AuditError(f"representable-control z/state replay differs: {representable_checks}")

    eff_t = api_effective_theta.astype(np.float64)
    eff_q = api_effective_qv.astype(np.float64)
    realized_t = eff_t - baseline_theta
    realized_q = eff_q - baseline_qv
    requested_pair_counts = _component_counts(requested_theta, requested_qv, scalar["changed_theta_mask"], scalar["changed_qv_mask"])
    reconstructed_counts = _component_counts(reconstructed_theta, reconstructed_qv, reconstructed_scalar["changed_theta_mask"], reconstructed_scalar["changed_qv_mask"])
    if np.any(frozen_rows[:, None] & request_mask):
        raise AuditError("requested deltas are nonzero in frozen original control blocks")

    # Exact f64 reconstruction means candidate_input_state is the submitted proposal,
    # but its subtraction from background is a distinct last-bit arithmetic recipe.
    state_minus_delta_recipe = {
        "stored_request_theta_component_nonzero": int(np.count_nonzero(requested_theta)),
        "state_minus_background_theta_component_nonzero": int(np.count_nonzero(reconstructed_theta)),
        "stored_request_qv_component_nonzero": int(np.count_nonzero(requested_qv)),
        "state_minus_background_qv_component_nonzero": int(np.count_nonzero(reconstructed_qv)),
        "stored_vs_reconstructed_theta_exact_equal": same_bits(requested_theta, reconstructed_theta),
        "stored_vs_reconstructed_qv_exact_equal": same_bits(requested_qv, reconstructed_qv),
        "theta_max_abs_lastbit_difference": float(np.max(np.abs(requested_theta - reconstructed_theta))),
        "qv_max_abs_lastbit_difference": float(np.max(np.abs(requested_qv - reconstructed_qv))),
        "reconstructed_recipe_effect_counts": reconstructed_counts,
        "used_for_primary_effective_state": "persisted candidate_input_delta.npz requested deltas; candidate_state-baseline subtraction is reported only as an alternative recipe",
    }

    # The prior-like z term is only a coordinate norm diagnostic. It does not
    # evaluate the observation objective or a new RTTOV/KDM cost.
    z_effective = np.asarray(representable["z"], dtype=np.float64)
    prior_proposed = 0.5 * float(REGULARIZATION_LAMBDA) * math.fsum(float(v * v) for v in z[active_mask])
    prior_effective = 0.5 * float(REGULARIZATION_LAMBDA) * math.fsum(float(v * v) for v in z_effective[active_mask])
    prior_proposed_after_freeze = 0.5 * float(REGULARIZATION_LAMBDA) * math.fsum(float(v * v) for v in z[active_after_freeze])
    prior_effective_after_freeze = 0.5 * float(REGULARIZATION_LAMBDA) * math.fsum(float(v * v) for v in z_effective[active_after_freeze])
    prior_summary = summary["actual_objective"]["regularization_numerator"]
    if not math.isclose(prior_proposed, float(prior_summary), rel_tol=1e-13, abs_tol=1e-13):
        raise AuditError("proposed z prior norm differs from published regularization numerator")
    z_stats = {}
    for component, idx in (("theta_m", 0), ("qv", 1)):
        proposed = z[idx]
        effective = z_effective[idx]
        difference = effective - proposed
        z_stats[component] = {
            "proposed": _array_stats(proposed),
            "effective": _array_stats(effective),
            "effective_minus_proposed": _array_stats(difference),
            "different_coordinates": int(np.count_nonzero(effective != proposed)),
        "active_box_overshoots": int(np.count_nonzero(np.abs(effective[active_mask[idx]]) > 1.0)),
        }
    if np.any(np.abs(z_effective[active_mask]) > 1.0):
        raise AuditError("effective z overshoots source control bounds")

    api_counts = dict(api_result.counts)
    independent_counts = {
        "stored_requested_delta": requested_pair_counts,
        "state_minus_background_alternative": reconstructed_counts,
        "prepare_effective_analysis": api_counts,
        "prepare_representable_control": dict(representable["counts"]),
    }

    # Keep the published payload small and nonduplicative. Source requests,
    # baseline receipts, z and masks are already hash-pinned inputs; this file
    # carries the native-f32 replay product and fields needed to inspect it.
    arrays = {
        "flat_index": flat.copy(),
        "input_state_f32": np.stack((old_t32, old_q32)),
        "effective_wire_delta_f32": np.stack((api_wire_theta, api_wire_qv)),
        "effective_state_f32": np.stack((api_effective_theta, api_effective_qv)),
        "changed_component_mask": np.stack((scalar["changed_theta_mask"], scalar["changed_qv_mask"])),
        "changed_pair_mask": scalar["changed_pair_mask"],
        "effective_z": z_effective,
        "applied_delta_f64": np.stack((realized_t, realized_q)),
    }

    source_files = {
        "candidate_input_delta_npz": candidate_delta_path,
        "candidate_input_state_npz": candidate_state_path,
        "restricted_controls_npz": controls_path,
        "restricted_candidate_sourcebound_json": sourcebound_path,
        "publication_manifest_json": publication_path,
        "restricted_summary_json": summary_path,
        "restricted_block_screen_json": RESTRICTED_DATA / "restricted_block_screen.json",
        "restricted_case_manifest_json": checkpoint_manifest_path,
        "audit_producer_source": Path(__file__).resolve(),
        "original_preprojection_observation_support_npz": support_path,
        "public_block22_saved_fields_npz": block22_saved_path,
        "public_block22_input_manifest_json": block22_manifest_path,
        "parent_CASE_MANIFEST_json": PARENT_RUN / "CASE_MANIFEST.json" if public_baseline is None else None,
        "effective_helper_source": Path(__file__).resolve().parents[0] / "native_analysis_control.py",
        "representable_control_source": Path(__file__).resolve().parents[0] / "native_satellite_objective.py",
    }
    if public_baseline is not None:
        source_files["public_native_state_controls_npz"] = public_baseline
    input_hashes = {name: sha256_file(path) for name, path in source_files.items() if path is not None}
    report = {
        "schema": SCHEMA,
        "status": "SAVED_EFFECTIVE_STATE_REPLAY_COMPLETE_NO_MODEL_CALLS",
        "coordinate_contract": {
            "theta_m": "native WRF THM_2 moist potential-temperature perturbation coordinate in K; no dry-theta conversion is applied",
            "qv": "native QVAPOR mixing ratio in kg/kg dry air",
            "public_flat_order": "flat0=j*NX+i with level as second axis",
            "native_helper_order": "(i,k,j), one-based bounds (1,NX,1,L,1,NY)",
            "f32_update_order": "cast background and request to binary32; for nonzero request components compute float32(old + request32); zero request components retain old bits",
        },
        "source_inputs": {
            "parent_run_id": baseline_info["run_id"],
            "parent_case_manifest_sha256": baseline_info["case_manifest_sha256"],
            "parent_baseline_chunks": baseline_chunk_pins,
            "baseline_reconstruction_mode": baseline_info["mode"],
            "public_baseline_npz_sha256": baseline_info["baseline_npz_sha256"],
            "restricted_candidate_run_id": publication.get("run_id"),
            "restricted_parent_run_id": publication.get("parent_run_id"),
            "restricted_control_npz_sha256": controls_file_sha,
            "restricted_control_z_sha256": controls_z_sha,
            "candidate_input_delta_npz_sha256": delta_sha,
            "candidate_input_state_npz_sha256": state_sha,
            "background_checkpoint_sha256": BACKGROUND_CHECKPOINT_SHA256,
            "source_artifact_hashes": input_hashes,
            "audit_producer_sha256": input_hashes["audit_producer_source"],
            "source_helper_status": {
                "prepare_effective_analysis_vs_independent_scalar_bitwise": independent_api_checks,
                "prepare_representable_control_vs_effective_analysis": representable_checks,
            },
        },
        "domain": {"NX": NX, "NY": NY, "L": LEVELS, "columns": COLUMNS, "blocks": (len(baseline_chunk_pins) if baseline_chunk_pins else (COLUMNS + CHUNK_COLUMNS - 1) // CHUNK_COLUMNS)},
        "counts": independent_counts,
        "candidate_state_relation": {
            "candidate_theta_m_is_background_plus_stored_delta_bitwise": same_bits(state_theta, baseline_theta + requested_theta),
            "candidate_qv_is_background_plus_stored_delta_bitwise": same_bits(state_qv, baseline_qv + requested_qv),
            "stored_vs_state_minus_background": state_minus_delta_recipe,
        },
        "binary32": {
            "background_theta_m_exact_widened_float32": True,
            "background_qv_exact_widened_float32": True,
            "wire_underflow_components": {"theta_m": scalar["underflow_theta_count"], "qv": scalar["underflow_qv_count"]},
            "wire_overflow_components": {"theta_m": scalar["overflow_theta_count"], "qv": scalar["overflow_qv_count"]},
            "delta_stats": {
                "requested_theta_m": _array_stats(requested_theta),
                "requested_qv": _array_stats(requested_qv),
                "quantized_request_theta_m": _array_stats(scalar["requested_theta_f32"]),
                "quantized_request_qv": _array_stats(scalar["requested_qv_f32"]),
                "effective_wire_theta_m": _array_stats(api_wire_theta),
                "effective_wire_qv": _array_stats(api_wire_qv),
                "realized_state_change_theta_m": _array_stats(realized_t),
                "realized_state_change_qv": _array_stats(realized_q),
                "quantization_roundoff_theta_m": _array_stats(scalar["requested_theta_f32"].astype(np.float64) - requested_theta),
                "quantization_roundoff_qv": _array_stats(scalar["requested_qv_f32"].astype(np.float64) - requested_qv),
                "state_accumulation_roundoff_theta_m": _array_stats(realized_t - api_wire_theta.astype(np.float64)),
                "state_accumulation_roundoff_qv": _array_stats(realized_q - api_wire_qv.astype(np.float64)),
                "realized_minus_requested_theta_m": _array_stats(realized_t - requested_theta),
                "realized_minus_requested_qv": _array_stats(realized_q - requested_qv),
            },
            "effective_state_stats": {"theta_m": _array_stats(api_effective_theta), "qv": _array_stats(api_effective_qv)},
        },
        "control_z": {
            "alpha": alpha,
            "scales": {"theta_m": 0.2 * alpha, "qv": "0.02 * alpha * original baseline qv"},
            "requested_delta_formula_matches_stored": delta_formula,
            "proposed_vs_effective_z": z_stats,
            "active_mask_scope": "original pre-projection observation_support.active; later-frozen 25 full blocks remain marked active here but their accepted z/effective z are zero",
            "original_active_component_count": int(np.count_nonzero(active_mask)),
            "postprojection_active_component_count": int(np.count_nonzero(active_after_freeze)),
            "proposed_prior_numerator_coordinate_term": prior_proposed,
            "effective_prior_numerator_coordinate_term": prior_effective,
            "prior_numerator_change_coordinate_term": prior_effective - prior_proposed,
            "proposed_prior_after_freeze_coordinate_term": prior_proposed_after_freeze,
            "effective_prior_after_freeze_coordinate_term": prior_effective_after_freeze,
            "prior_unchanged_by_mask_projection": bool(prior_proposed == prior_proposed_after_freeze and prior_effective == prior_effective_after_freeze),
            "proposed_prior_matches_saved_screen_summary": math.isclose(prior_proposed, float(prior_summary), rel_tol=1e-13, abs_tol=1e-13),
            "cost_re_evaluation": "not performed; z-prior coordinate-norm diagnostics only, not an observation/cost re-evaluation or new optimizer policy",
        },
        "public_block22_anchor": {"sha256": input_hashes["public_block22_saved_fields_npz"], "baseline_fields_bitwise_match_parent": block22_checks},
        "calls_executed_by_this_audit": {"KDM6": 0, "RTTOV": 0, "host": 0},
        "interpretation_limits": [
            "Requested-pair count is computed from the persisted candidate_input_delta arrays, not from candidate_state minus background.",
            "The candidate-state-minus-background recipe is reported separately because f64 subtraction can change requested delta last bits.",
            "The only physics-related operation replayed is the native float32 state update; no KDM, RTTOV, host, observation, or cost model is executed.",
            "This is not an effective assimilation cost or a forecast/host-step replay.",
            ("Baseline was loaded from the published native_state_controls.npz; this run does not claim independent reconstruction from 129 private RUN_v4 receipts."
             if public_baseline is not None else
             "Baseline was independently reconstructed from 129 private RUN_v4 receipt-bound chunks."),
        ],
    }
    _output_files(output_dir, report, arrays)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--public-baseline", type=Path, default=None,
                        help="use a published native_state_controls.npz instead of private RUN_v4 receipts")
    parser.add_argument("--support", type=Path, default=PUBLIC_SUPPORT_NPZ,
                        help="hash-pinned observation_support.npz")
    args = parser.parse_args(argv)
    if args.output_dir.exists() or args.output_dir.is_symlink():
        raise FileExistsError(f"evidence directory must be new: {args.output_dir}")
    report = audit(args.output_dir, public_baseline=args.public_baseline, support_path=args.support)
    print(json.dumps({
        "output_dir": args.output_dir.name,
        "requested_pairs": report["counts"]["stored_requested_delta"]["requested_nonzero_pairs"],
        "changed_pairs": report["counts"]["stored_requested_delta"]["changed_pairs"],
        "noops": report["counts"]["stored_requested_delta"]["noop_requested_pairs"],
        "KDM6_calls": 0,
        "RTTOV_calls": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
