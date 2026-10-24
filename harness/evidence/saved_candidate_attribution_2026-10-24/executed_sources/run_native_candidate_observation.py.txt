"""Run a bounded endpoint-initialized native observation-cost experiment.

This composes the existing prep, selected B512 KDM, cleanup/finish, EOS,
native profile/cloud, and RTTOV operators. It performs no host step, DA update,
or forecast. The default experiment and its target/directions/epsilons are
defined once in ``EXPERIMENT`` and copied into both preparation and result
records. No model or RTTOV work is performed on import.
"""

from __future__ import annotations

import argparse
import copy
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil

import numpy as np


REPO = Path(__file__).resolve().parents[1]
PATHS = {
    "checkpoint": Path(
        "/Users/yhlee/KDM6AD-k/host/research_evidence/mp137_two_step_20261020/"
        "TWO_STEP_SAVED_DA/calls/live_yws3nddy/wrfrst_d01_2025-07-19_00:00:40"
    ),
    "namelist": Path(
        "/Users/yhlee/KDM6AD-k/host/research_evidence/mp137_two_step_20261020/"
        "TWO_STEP_SAVED_DA/calls/live_yws3nddy/namelist.output"
    ),
    "observations": Path(
        "/Users/yhlee/KDM6AD-k/host/research_evidence/ko7_model_domain_20261014/INPUTS.npz"
    ),
    "time_audit": Path(
        "/Users/yhlee/KDM6AD-k/host/research_evidence/ko7_first_analysis_20261014/"
        "OBSERVATION_TIME_AUDIT.json"
    ),
    "template": Path(
        "/Users/yhlee/KDM6AD-k/host/research_evidence/"
        "postcleanup_smoke_20261015_2241/ko7_one_column/temporary/"
        "worker-84479/cases/column_04835/probe/w0_0_64d9cl5d/case"
    ),
    "packets": Path(
        "/Users/yhlee/KDM6AD-k/host/research_evidence/"
        "mp137_ice_factorial_20261023/domain_preparation_fp64_final"
    ),
    "prep_reference": REPO
    / "harness/evidence/native_prep_ad_2026-10-21/native39_prep_ad.json",
    "finish_reference": REPO
    / "harness/evidence/applied_finish_ad_2026-10-21/native39_finish_ad.json",
    "candidate_library": Path(
        "/Users/yhlee/KDM6AD-k/host/research_evidence/actual_qr_20261024/"
        "build_final/libkdm6_actual_qr.2.0.0.dylib"
    ),
    "candidate_build_receipt": Path(
        "/Users/yhlee/KDM6AD-k/host/research_evidence/actual_qr_20261024/"
        "build_final/receipt.json"
    ),
    "candidate_overlay_manifest": Path(
        "/Users/yhlee/KDM6AD-k/host/research_evidence/actual_qr_20261024/"
        "overlay_final/source_sha256.json"
    ),
    "base_library": Path(
        "/Users/yhlee/KDM6AD-k/host/research_evidence/"
        "localized_ice_stage_20261024_c2f9214a/ad_build/"
        "libkdm6_ice_factorial_ad.2.0.0.dylib"
    ),
    "rttov_template_executable": Path(
        "/Users/yhlee/AD-RTTOV/external/rttov14/src/bin/rttov_test.exe"
    ),
}
EXPECTED_RTTOV_SHA256 = (
    "0909d289778d3ea91f6300fd8c5f88e5e1dcc0528d260aec94f3aab0bc7692fd"
)

EXPERIMENT = {
    "schema": "kdm6.native_candidate_observation_experiment.v1",
    "factorial_mode": "norm_actual",
    "qr_transport": "actual_departure",
    "step": 2,
    "batch_columns": 512,
    "levels": 39,
    "dt_seconds": 20.0,
    "ncmin_land": 10.0,
    "ncmin_sea": 10.0,
    "targets": [
        {
            "i_1based": 131,
            "j_1based": 88,
            "flat_index0": 20488,
            "batch_index0": 40,
            "row_in_batch0": 8,
        }
    ],
    "directions": [
        {
            "name": "theta_m",
            "formula": "dx_theta=0.2*sin(0.37*(k+1)); other x/rest entries are zero",
        },
        {
            "name": "qv",
            "formula": "dx_qv=0.02*x_qv*cos(0.29*(k+2)); other x/rest entries are zero",
        },
        {"name": "mixed", "formula": "theta_m direction plus qv direction"},
    ],
    "epsilons": [1.0e-2, 3.0e-3, 1.0e-3],
    "eligibility_scope": "RTTOV quality/mask, cloud fraction and finish/cleanup signature only; candidate QR cap masks and KDM integer schedules are not recorded at FD endpoints",
    "scope": "Single native target, fixed B512 background; baseline value, joint first-order JVP/VJP and eligible directional finite differences. No host integration, assimilation update, or forecast.",
}

SOURCE_FILES = (
    "harness/batch_target_kernel.py",
    "harness/verify_localized_ice_ad.py",
    "harness/native_microphysics_obs.py",
    "harness/native_number_boundary.py",
    "harness/native_number_qualification.py",
    "harness/verify_native_prep_ad.py",
    "harness/verify_native_finish_ad.py",
    "harness/verify_native_obs_ad.py",
    "harness/verify_microphysics_obs_ad.py",
)


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def select_library(paths, role="candidate", override=None):
    if role not in ("candidate", "base"):
        raise ValueError("library_role must be 'candidate' or 'base'")
    path = Path(override) if override is not None else Path(paths[f"{role}_library"])
    if not path.is_file():
        raise FileNotFoundError(f"selected {role} library is missing: {path}")
    return {
        "role": role,
        "path": str(path.resolve()),
        "sha256": sha256_file(path),
    }


def validate_endpoint_eligibility(reference, trial):
    """Return replayable equality checks for one finite-difference endpoint."""
    keys = ("quality", "mask", "endpoint_cfrac", "endpoint_signature")
    checks = {
        key: bool(np.array_equal(np.asarray(reference[key]), np.asarray(trial[key])))
        for key in keys
    }
    checks["eligible"] = all(checks.values())
    return checks


def verify_library_transport(library, qr_transport, build_receipt, overlay_manifest):
    """Admit actual-QR mode only for the receipt-pinned candidate binary.

    Library role and QR transport remain independent metadata. A path named
    "candidate" is not evidence by itself; actual_departure requires the
    recorded build SHA and the matching actual-QR overlay manifest.
    """
    if qr_transport not in ("legacy", "actual_departure"):
        raise ValueError("qr_transport must be legacy or actual_departure")
    receipt_path = Path(build_receipt) if build_receipt is not None else None
    overlay_path = Path(overlay_manifest) if overlay_manifest is not None else None
    if qr_transport == "legacy" and (receipt_path is None or overlay_path is None):
        return {
            **library,
            "qr_transport": qr_transport,
            "build_receipt_path": None if receipt_path is None else str(receipt_path),
            "build_receipt_sha256": None,
            "overlay_manifest_path": None
            if overlay_path is None
            else str(overlay_path),
            "overlay_manifest_sha256": None,
            "transport_attestation": "legacy requested; no actual-departure claim",
        }
    if receipt_path is None or overlay_path is None:
        raise ValueError(
            "actual_departure requires a build receipt and overlay manifest"
        )
    receipt_bytes = receipt_path.read_bytes()
    receipt = json.loads(receipt_bytes)
    if receipt.get("library_sha256") != library["sha256"]:
        raise ValueError("selected library SHA differs from its build receipt")
    source_hashes = receipt.get("source_sha256")
    if not isinstance(source_hashes, dict) or not source_hashes:
        raise ValueError("candidate build receipt lacks source_sha256 pins")
    overlay_resolved = str(overlay_path.resolve())
    expected_overlay_hash = source_hashes.get(overlay_resolved)
    if (
        expected_overlay_hash is None
        or sha256_file(overlay_path) != expected_overlay_hash
    ):
        raise ValueError(
            "candidate overlay manifest is not pinned by the build receipt"
        )
    overlay = json.loads(overlay_path.read_text())
    if (
        overlay.get("schema") != "kdm6.actual_qr_overlay.v1"
        or overlay.get("candidate_mode") != "actual_departure"
        or overlay.get("required_ice_mode") != "norm_actual"
        or overlay.get("default") != "legacy"
        or overlay.get("mode_environment") != "KDM6_QR_TRANSPORT"
    ):
        raise ValueError(
            "overlay manifest does not attest norm_actual/actual_departure"
        )
    for pinned_path, expected_sha in source_hashes.items():
        path = Path(pinned_path)
        if not path.is_file() or sha256_file(path) != expected_sha:
            raise ValueError(f"candidate build source pin changed: {pinned_path}")
    return {
        **library,
        "qr_transport": qr_transport,
        "build_receipt_path": str(receipt_path.resolve()),
        "build_receipt_sha256": sha256_file(receipt_path),
        "overlay_manifest_path": overlay_resolved,
        "overlay_manifest_sha256": expected_overlay_hash,
        "transport_attestation": {
            "schema": overlay["schema"],
            "candidate_mode": overlay["candidate_mode"],
            "required_ice_mode": overlay["required_ice_mode"],
            "default": overlay["default"],
        },
        "build_source_sha256": source_hashes,
    }


def resolve_paths(overrides=None):
    paths = dict(PATHS)
    if overrides:
        unknown = set(overrides) - set(paths)
        if unknown:
            raise ValueError(f"unknown path keys: {sorted(unknown)}")
        paths.update({name: Path(value) for name, value in overrides.items()})
    return {name: Path(value).resolve() for name, value in paths.items()}


def experiment_metadata(experiment=EXPERIMENT):
    """Return a JSON-safe copy reused in both prepared and result artifacts."""
    return copy.deepcopy(experiment)


def target_geometry(target, *, nx=234, batch_columns=512):
    i, j = target["i_1based"], target["j_1based"]
    flat = (j - 1) * nx + i - 1
    chunk, row = divmod(flat, batch_columns)
    expected = (target["flat_index0"], target["batch_index0"], target["row_in_batch0"])
    if (flat, chunk, row) != expected:
        raise ValueError("experiment target flat/chunk/row mapping is inconsistent")
    return {**target, "flat_index0": flat, "batch_index0": chunk, "row_in_batch0": row}


def make_number_source_bindings(
    request_sha,
    namelist_sha,
    checkpoint_sha,
    native_x,
    target,
    experiment,
    source_chunk_sha,
):
    """Build the exact versioned NativeDryNumberKernel provenance contract."""
    return {
        "trace": request_sha,
        "namelist": namelist_sha,
        "checkpoint": checkpoint_sha,
        "step": experiment["step"],
        "i": target["i_1based"],
        "j": target["j_1based"],
        "levels": experiment["levels"],
        "base_native_X_sha256": hashlib.sha256(native_x.tobytes()).hexdigest(),
        "source_artifact_kind": "captured original B512 packet row; not a target native MP_INPUT record",
        "source_chunk_sha256": source_chunk_sha,
        "flat_index0": target["flat_index0"],
        "batch_row0": target["row_in_batch0"],
    }


def direction_vectors(x, rest, experiment=EXPERIMENT):
    """Build exactly the three pinned T/Q control directions."""
    levels = int(experiment["levels"])
    if (
        not isinstance(x, np.ndarray)
        or x.dtype != np.float64
        or x.shape != (3 * levels + 2,)
    ):
        raise TypeError("x must be finite float64 shape (3L+2)")
    if (
        not isinstance(rest, np.ndarray)
        or rest.dtype != np.float64
        or rest.shape != (10, levels)
    ):
        raise TypeError("rest must be finite float64 shape (10,L)")
    if not np.isfinite(x).all() or not np.isfinite(rest).all():
        raise ValueError("direction base arrays must be finite")
    k = np.arange(levels, dtype=np.float64)
    theta = np.zeros_like(x)
    theta[:levels] = 0.2 * np.sin(0.37 * (k + 1))
    qv = np.zeros_like(x)
    qv[levels : 2 * levels] = 0.02 * x[levels : 2 * levels] * np.cos(0.29 * (k + 2))
    zeros = np.zeros_like(rest)
    requested = {row["name"] for row in experiment["directions"]}
    available = {
        "theta_m": (theta, zeros.copy()),
        "qv": (qv, zeros.copy()),
        "mixed": (theta + qv, zeros.copy()),
    }
    if requested != set(available):
        raise ValueError(
            "EXPERIMENT directions must identify theta_m, qv, and mixed exactly"
        )
    return {
        name: available[name]
        for name in (row["name"] for row in experiment["directions"])
    }


def require_nonempty_mask(mask, label="RTTOV quality-zero mask"):
    mask = np.asarray(mask)
    if mask.size == 0 or not np.any(mask):
        raise ValueError(f"no usable {label}; observation cost is rejected")
    return mask


def require_exact_packet_qv(checkpoint_qv, packet_state_qv):
    """Bind the prep source QV to the selected B512 packet row by exact bits."""
    if (
        not isinstance(checkpoint_qv, np.ndarray)
        or checkpoint_qv.dtype != np.float64
        or not isinstance(packet_state_qv, np.ndarray)
        or packet_state_qv.dtype != np.float64
        or checkpoint_qv.shape != packet_state_qv.shape
        or not np.isfinite(checkpoint_qv).all()
        or not np.isfinite(packet_state_qv).all()
        or np.ascontiguousarray(checkpoint_qv).tobytes()
        != np.ascontiguousarray(packet_state_qv).tobytes()
    ):
        raise ValueError("checkpoint QV differs bitwise from selected B512 packet row")


def paths_overlap(left, right):
    left, right = Path(left).resolve(), Path(right).resolve()
    return left == right or left in right.parents or right in left.parents


def validate_output_directory(output_dir, paths, *, source_root=REPO):
    original = Path(output_dir).absolute()
    if original.exists() or original.is_symlink():
        raise ValueError("output directory must be new and must not be a symlink")
    if any(parent.is_symlink() for parent in original.parents if parent.exists()):
        raise ValueError("output directory path must not traverse a symlink")
    resolved = original.resolve()
    if paths_overlap(resolved, source_root):
        raise ValueError("output directory must not overlap the public source tree")
    for name, path in paths.items():
        if paths_overlap(resolved, path):
            raise ValueError(f"output directory overlaps input {name}: {path}")
    return resolved


def collect_source_pins(paths, library, *, source_root=REPO):
    source_root = Path(source_root).resolve()
    pinned = {str(Path(__file__).resolve()): sha256_file(__file__)}
    for key in ("build_receipt_path", "overlay_manifest_path"):
        path = library.get(key)
        if path:
            pinned[str(Path(path).resolve())] = sha256_file(path)
    for path, expected in library.get("build_source_sha256", {}).items():
        pinned[str(Path(path).resolve())] = expected
    for key in (
        "checkpoint",
        "namelist",
        "observations",
        "time_audit",
        "prep_reference",
        "finish_reference",
        "rttov_template_executable",
    ):
        pinned[str(paths[key])] = sha256_file(paths[key])
    pinned[library["path"]] = library["sha256"]
    packets_manifest = paths["packets"] / "manifest.json"
    pinned[str(packets_manifest)] = sha256_file(packets_manifest)
    from oracle.kdm6.obs.rttov_case_writer import _resolve_coef_path

    pinned[str(_resolve_coef_path(paths["template"]))] = sha256_file(
        _resolve_coef_path(paths["template"])
    )
    for relative in SOURCE_FILES:
        path = source_root / relative
        pinned[str(path)] = sha256_file(path)
    for path in sorted((source_root / "oracle/kdm6").rglob("*.py")):
        pinned[str(path)] = sha256_file(path)
    calibration = source_root / "oracle/kdm6/obs/data/gk2a_ami_cal_202507190000.json"
    pinned[str(calibration)] = sha256_file(calibration)
    for directory in ("in", "out"):
        for path in sorted((paths["template"] / directory).rglob("*")):
            if path.is_file():
                pinned[str(path)] = sha256_file(path)
    for name in ("run.sh", "env.sh", "rttov_test.txt"):
        path = paths["template"] / "out" / name
        if path.exists():
            pinned[str(path)] = sha256_file(path)
    return pinned


def _read_checkpoint_column(checkpoint, target):
    import netCDF4

    i, j = target["i_1based"], target["j_1based"]
    with netCDF4.Dataset(checkpoint) as dataset:
        dataset.set_auto_maskandscale(False)

        def column(name):
            return np.asarray(
                dataset.variables[name][0, :, j - 1, i - 1], dtype=np.float32
            ).astype(np.float64)

        def scalar(name):
            return float(np.float32(dataset.variables[name][0, j - 1, i - 1]))

        geometry = {"phb": column("PHB")}
        for key in ("C3H", "C4H", "C3F", "C4F"):
            geometry[key.lower()] = np.asarray(
                dataset.variables[key][0], dtype=np.float32
            ).astype(np.float64)
        mu = float(np.float32(np.float32(scalar("MUB")) + np.float32(scalar("MU_2"))))
        native_surface = {
            key: scalar(key)
            for key in (
                "TSK",
                "T2",
                "Q2",
                "U10",
                "V10",
                "SINALPHA",
                "COSALPHA",
                "XLAND",
                "SNOWC",
                "SEAICE",
                "HGT",
                "XLAT",
                "XLONG",
            )
        }
        thm, qv, ph = column("THM_2"), column("QVAPOR"), column("PH_2")
    return geometry, mu, native_surface, thm, qv, ph


def prepare_inputs(
    paths,
    target,
    *,
    library_role="candidate",
    library_override=None,
    experiment=EXPERIMENT,
    workdir,
    library_metadata=None,
):
    with _runtime_environment(experiment):
        return _prepare_inputs_impl(
            paths,
            target,
            library_role=library_role,
            library_override=library_override,
            experiment=experiment,
            workdir=workdir,
            library_metadata=library_metadata,
        )


def _prepare_inputs_impl(
    paths,
    target,
    *,
    library_role="candidate",
    library_override=None,
    experiment=EXPERIMENT,
    workdir,
    library_metadata=None,
):
    """Prepare one selected target while retaining its immutable B512 context."""
    import torch

    from harness.batch_target_kernel import BatchTargetKernel
    from harness.native_microphysics_obs import MicrophysicsObservationState
    from harness.native_number_boundary import NativeDryNumberKernel
    from harness.native_number_qualification import (
        apply_receipt,
        make_kernel_coordinate_receipt,
    )
    from harness.verify_localized_ice_ad import BatchKernel
    from harness.verify_native_finish_ad import KernelFinish, _api as finish_api
    from harness.verify_native_prep_ad import Prep, pack_state
    from harness.verify_native_obs_ad import load_snapshot

    paths = resolve_paths(paths)
    experiment = experiment_metadata(experiment)
    target = target_geometry(target, batch_columns=experiment["batch_columns"])
    if target["batch_index0"] != 40 or target["row_in_batch0"] != 8:
        raise ValueError(
            "this archived candidate observation is bound to B512 chunk 40 row 8"
        )
    if library_metadata is None:
        library = select_library(paths, library_role, library_override)
        receipt_path = (
            paths["candidate_build_receipt"] if library_role == "candidate" else None
        )
        overlay_path = (
            paths["candidate_overlay_manifest"] if library_role == "candidate" else None
        )
        library = verify_library_transport(
            library, experiment["qr_transport"], receipt_path, overlay_path
        )
    else:
        library = copy.deepcopy(library_metadata)
        if library["role"] != library_role:
            raise ValueError(
                "selected library role differs from prepared library metadata"
            )
    if sha256_file(paths["rttov_template_executable"]) != EXPECTED_RTTOV_SHA256:
        raise ValueError("RTTOV executable changed from its pinned binary")
    torch.set_num_threads(1)
    packet_manifest = json.loads((paths["packets"] / "manifest.json").read_text())
    chunk = target["batch_index0"]
    chunk_entry = packet_manifest["chunks"][chunk]
    chunk_path = paths["packets"] / chunk_entry["path"]
    if sha256_file(chunk_path) != chunk_entry["sha256"]:
        raise ValueError("endpoint B512 packet chunk changed")
    with np.load(chunk_path, allow_pickle=False) as archive:
        batch_state = archive["state"].copy()
        batch_forcing = archive["forcing"].copy()
        xland = archive["xland"].copy()
    if batch_state.shape != (12, experiment["batch_columns"], experiment["levels"]):
        raise ValueError("endpoint packet does not match experiment B512/L39")

    geometry, mu, native_surface, thm, qv, ph = _read_checkpoint_column(
        paths["checkpoint"], target
    )
    require_exact_packet_qv(qv, batch_state[1, target["row_in_batch0"]].copy())
    prep_config = json.loads(paths["prep_reference"].read_text())["configuration"]
    prep = Prep(experiment["levels"], geometry, prep_config)
    x = pack_state((thm, qv, np.array(mu), ph))
    prep_out = prep.forward(x)
    packet_target = np.concatenate(
        (
            batch_state[0, target["row_in_batch0"]][None],
            batch_forcing[:, target["row_in_batch0"]],
        ),
        axis=0,
    )
    prep_error = float(np.max(np.abs(prep_out - packet_target)))
    if not np.allclose(prep_out, packet_target, rtol=2e-13, atol=1e-13):
        raise ValueError(
            "scalar native prep no longer matches selected B512 packet row"
        )

    volume_state = np.ascontiguousarray(
        np.vstack((prep_out[0], qv, batch_state[2:, target["row_in_batch0"]]))
    )
    forcing = np.ascontiguousarray(prep_out[1:])
    request_path = paths["packets"] / chunk_entry["path"]
    request_sha = sha256_file(request_path)
    # NativeDryNumberKernel's receipt protocol requires the legacy keys
    # trace/namelist/checkpoint/step/i/j/levels/base_native_X_sha256. Keep the
    # packet artifact label and range details as additional provenance fields.
    bindings = make_number_source_bindings(
        request_sha,
        sha256_file(paths["namelist"]),
        sha256_file(paths["checkpoint"]),
        x,
        target,
        experiment,
        chunk_entry["sha256"],
    )
    receipt = make_kernel_coordinate_receipt(
        volume_state,
        forcing,
        source_id=f"B512_endpoint_selected_{target['i_1based']}_{target['j_1based']}",
        source_sha256=request_sha,
        source_bindings=bindings,
    )
    receipt_path = Path(workdir) / "number_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, allow_nan=False) + "\n")
    dry_state, admission = apply_receipt(
        receipt, volume_state, forcing, bindings, sha256_file(receipt_path)
    )

    raw_batch = BatchKernel(library["path"], xland, experiment["levels"])
    selected_batch = BatchTargetKernel(
        raw_batch,
        batch_state,
        batch_forcing,
        target["row_in_batch0"],
        dt=experiment["dt_seconds"],
    )
    kernel = NativeDryNumberKernel(selected_batch, admission=admission)
    finish_reference = json.loads(paths["finish_reference"].read_text())
    api = finish_api()
    finish = KernelFinish(
        kernel,
        api.FinishConfig(**finish_reference["configuration"]),
        api.ZeroOutConfig(**finish_reference["zero_out"]),
    )
    microphysics = MicrophysicsObservationState(prep, finish)

    snapshot = load_snapshot(
        paths["checkpoint"],
        paths["observations"],
        i=target["i_1based"],
        j=target["j_1based"],
        expected_time="2025-07-19_00:00:40",
        nominal_time="2025-07-19_00:00:00",
        time_audit=paths["time_audit"],
        namelist=paths["namelist"],
        all_sky=True,
        levels=experiment["levels"],
    )
    return {
        "experiment": experiment,
        "target": target,
        "paths": paths,
        "library": library,
        "source_sha256": collect_source_pins(paths, library),
        "prep": prep,
        "microphysics": microphysics,
        "x": np.ascontiguousarray(x),
        "rest": np.ascontiguousarray(dry_state[2:]),
        "state": volume_state,
        "forcing": forcing,
        "native_surface": native_surface,
        "prep_scalar_maxabs_vs_packet": prep_error,
        "number_receipt": receipt,
        "number_receipt_sha256": sha256_file(receipt_path),
        "snapshot": snapshot,
        "workdir": Path(workdir),
    }


def _make_directions(x, experiment):
    levels = experiment["levels"]
    k = np.arange(levels, dtype=np.float64)
    theta = np.zeros_like(x)
    theta[:levels] = 0.2 * np.sin(0.37 * (k + 1))
    qv = np.zeros_like(x)
    qv[levels : 2 * levels] = 0.02 * x[levels : 2 * levels] * np.cos(0.29 * (k + 2))
    return {"theta_m": theta, "qv": qv, "mixed": theta + qv}


def _check_pins(pins):
    changed = [path for path, expected in pins.items() if sha256_file(path) != expected]
    if changed:
        raise RuntimeError(f"pinned inputs changed during observation run: {changed}")


def verify_case(prepared):
    with _runtime_environment(prepared["experiment"]):
        return _verify_case_impl(prepared)


def _verify_case_impl(prepared):
    """Evaluate one baseline and its pinned three T/Q directional checks."""
    import torch

    from harness.verify_microphysics_obs_ad import observation_arrays
    from harness.verify_native_obs_ad import (
        CHANNELS,
        CLOUD_KEYS,
        PROFILE_KEYS,
    )
    from oracle.kdm6.obs import native_cloud_profile as cloud_api
    from oracle.kdm6.obs import native_profile_builder as profile_api
    from oracle.kdm6.obs.model_profile_builder import qv_to_q_ppmv_moist
    from oracle.kdm6.obs.obs_loss import compute_obs_loss
    from oracle.kdm6.obs.rttov_case_writer import _resolve_coef_path, make_live_run_k
    from oracle.kdm6.obs.rttov_input_builder import RttovInputConfig
    from oracle.kdm6.obs.rttov_obs_operator import RttovObsOp

    torch.set_num_threads(1)
    experiment = prepared["experiment"]
    workdir = prepared["workdir"]
    microphysics = prepared["microphysics"]
    x, rest = prepared["x"], prepared["rest"]
    y, record = microphysics.forward(x, rest, record=True)
    calls = []
    result = {
        "schema": "kdm6.native_candidate_observation_result.v1",
        "experiment": experiment_metadata(experiment),
        "target": prepared["target"],
        "library": prepared["library"],
        "source_sha256": prepared["source_sha256"],
        "number_receipt_sha256": prepared["number_receipt_sha256"],
        "prep_scalar_maxabs_vs_packet": prepared["prep_scalar_maxabs_vs_packet"],
        "scope": experiment["scope"],
        "direction_checks": {},
    }
    kdm_forward_calls = 0
    try:
        snapshot = prepared["snapshot"]
        native = prepared["native_surface"]
        geometry = profile_api.FrozenNativeProfileGeometry(
            **{
                key: torch.from_numpy(value.copy())
                for key, value in snapshot.geometry.items()
            }
        )
        config = profile_api.NativeObservationConfig(**snapshot.constants)
        reference = profile_api.UpperReferenceProfile(
            **{
                key: torch.from_numpy(value.copy())
                for key, value in snapshot.reference.items()
            },
            fixed_upper_count=27,
        )
        fields = tuple(
            torch.from_numpy(value.copy()).requires_grad_()
            for value in observation_arrays(y, experiment["levels"])
        )

        def project(*values):
            return cloud_api.native_to_rttov_cloud_profile(
                profile_api.NativeObservationState(*values[:4]),
                cloud_api.NativeCloudState(*values[5:]),
                geometry,
                config,
                reference,
                rho_d=values[4],
                xland=snapshot.xland,
                ncmin_land=snapshot.ncmin[0],
                ncmin_sea=snapshot.ncmin[1],
            )

        profile = project(*fields)
        flat_index = prepared["target"]["flat_index0"]
        with np.load(prepared["paths"]["observations"], allow_pickle=False) as obs:
            ge = {
                "zenangle": float(
                    obs["ami_geometry_zenangle_deg"].reshape(-1)[flat_index]
                ),
                "azangle": float(
                    obs["ami_geometry_azangle_deg"].reshape(-1)[flat_index]
                ),
                "sunzenangle": 0.0,
                "sunazangle": 0.0,
                "latitude": native["XLAT"],
                "longitude": native["XLONG"],
                "elevation": native["HGT"] / 1000.0,
            }
        q2_ppmv = float(
            qv_to_q_ppmv_moist(
                torch.tensor(native["Q2"], dtype=torch.float64),
                gas_units=2,
                qv_convention="mixing_ratio_kgkg_dry",
            )
        )
        wind_u = native["U10"] * native["COSALPHA"] - native["V10"] * native["SINALPHA"]
        wind_v = native["V10"] * native["COSALPHA"] + native["U10"] * native["SINALPHA"]
        surface = {
            "skin": {
                "surftype": 2
                if native["SEAICE"] > 0.5
                else (1 if native["XLAND"] == 2 else 0),
                "watertype": 1,
                "t": native["TSK"],
                "salinity": 35.0,
                "foam_fraction": 0.0,
                "snow_fraction": native["SNOWC"],
                "fastem": [3.0, 5.0, 15.0, 0.1, 0.3],
            },
            "near_surface": {
                "t2m": native["T2"],
                "q2m": q2_ppmv,
                "wind_u10m": wind_u,
                "wind_v10m": wind_v,
                "wind_fetch": 0.0,
            },
        }
        template_text = (
            prepared["paths"]["template"] / "out/rttov_test.txt"
        ).read_text()
        if "rt_all%solar                    = .FALSE." not in template_text:
            raise ValueError("thermal-only RTTOV template config changed")
        trial_template = workdir / "template"
        shutil.copytree(prepared["paths"]["template"], trial_template)
        actual_impl = make_live_run_k(
            workdir / "trial",
            fixture_case_dir=trial_template,
            ami_kma_bt=True,
            timeout=180,
        )
        cache = {}

        def actual(rttov_input):
            bt, k_profile, quality = actual_impl(rttov_input)
            cache["k"] = {
                key: np.asarray(value).copy() for key, value in k_profile.items()
            }
            calls.append(rttov_input.config_hash)
            return bt, k_profile, quality

        rttov_config = RttovInputConfig(
            coef_id=sha256_file(_resolve_coef_path(prepared["paths"]["template"])),
            channels=CHANNELS,
            pressure_gradients=True,
            geometry=ge,
            surface=surface,
        )

        def profile_values(profile_value):
            return (
                profile_value.t_lay,
                profile_value.q_lay,
                profile_value.p_lay,
                profile_value.p_half,
                profile_value.clw,
                profile_value.ciw,
                profile_value.deff_liq,
                profile_value.deff_ice,
            )

        baseline_bt, quality = RttovObsOp.apply(
            actual, rttov_config, *profile_values(profile), profile.cfrac
        )
        mask = torch.from_numpy(snapshot.obs_mask) * (quality == 0).to(torch.float64)
        require_nonempty_mask(mask.detach().numpy())
        observation = torch.from_numpy(snapshot.observation)
        cost = compute_obs_loss(baseline_bt, {"bt": observation}, mask, 1.0, delta=1.0)
        seed_bt = (
            torch.autograd.grad(cost, baseline_bt, retain_graph=True)[0]
            .detach()
            .numpy()
        )
        base_k = cache["k"]
        output_gradients = torch.autograd.grad(cost, fields)
        flat_output_gradient = np.concatenate(
            [value.detach().numpy().reshape(-1) for value in output_gradients]
        )
        gx, grest = microphysics.vjp(record, flat_output_gradient)
        kdm_forward_calls += 1
        baseline_cf = profile.cfrac.detach().numpy().copy()
        baseline_signature = microphysics.branch_signature(record).copy()
        baseline_quality = quality.detach().numpy().copy()
        baseline_mask = mask.detach().numpy().copy()
        baseline_endpoint = {
            "quality": baseline_quality,
            "mask": baseline_mask,
            "endpoint_cfrac": baseline_cf,
            "endpoint_signature": baseline_signature,
        }
        result.update(
            {
                "cost": float(cost.detach()),
                "BT_KMA": baseline_bt.detach().numpy().tolist(),
                "observation_BT_KMA": snapshot.observation.tolist(),
                "quality": baseline_quality.tolist(),
                "mask": baseline_mask.tolist(),
                "geometry": ge,
                "surface": surface,
                "native_surface_raw": prepared["native_surface"],
                "endpoint_cfrac": baseline_cf.tolist(),
                "endpoint_signature": baseline_signature.tolist(),
                "native_x_cost_gradient": gx.tolist(),
                "rest_cost_gradient": grest.tolist(),
                "cost_BT_seed": seed_bt.tolist(),
                "post_finish_cost_covector": flat_output_gradient.tolist(),
                "post_finish_state": y.tolist(),
                "profile": {
                    key: value.detach().numpy().tolist()
                    for key, value in zip(
                        PROFILE_KEYS + CLOUD_KEYS, profile_values(profile)
                    )
                },
                "profile_K": {
                    key: value.tolist()
                    for key, value in base_k.items()
                    if key in PROFILE_KEYS + CLOUD_KEYS
                },
            }
        )

        def evaluate_trial(trial_x):
            nonlocal kdm_forward_calls
            trial_y, trial_record = microphysics.forward(trial_x, rest, record=False)
            kdm_forward_calls += 1
            try:
                trial_fields = tuple(
                    torch.from_numpy(value.copy())
                    for value in observation_arrays(trial_y, experiment["levels"])
                )
                trial_profile = project(*trial_fields)
                bt, trial_quality = RttovObsOp.apply(
                    actual,
                    rttov_config,
                    *profile_values(trial_profile),
                    trial_profile.cfrac,
                )
                trial_mask = torch.from_numpy(snapshot.obs_mask) * (
                    trial_quality == 0
                ).to(torch.float64)
                require_nonempty_mask(trial_mask.detach().numpy())
                trial_cost = compute_obs_loss(
                    bt, {"bt": observation}, trial_mask, 1.0, delta=1.0
                )
                trial = {
                    "cost": float(trial_cost.detach()),
                    "bt": bt.detach().numpy().copy(),
                    "quality": trial_quality.detach().numpy().copy(),
                    "mask": trial_mask.detach().numpy().copy(),
                    "endpoint_cfrac": trial_profile.cfrac.detach().numpy().copy(),
                    "endpoint_signature": microphysics.branch_signature(
                        trial_record
                    ).copy(),
                }
                trial["endpoint_eligibility"] = validate_endpoint_eligibility(
                    baseline_endpoint, trial
                )
                return trial
            finally:
                microphysics.close(trial_record)

        directions = _make_directions(x, experiment)
        for direction_spec in experiment["directions"]:
            name = direction_spec["name"]
            dx = directions[name]
            dr = np.zeros_like(rest)
            dy = microphysics.jvp(record, dx, dr)
            jvp_fields = tuple(
                torch.from_numpy(value.copy())
                for value in observation_arrays(dy, experiment["levels"])
            )
            _, profile_tangent = torch.autograd.functional.jvp(
                lambda *values: profile_values(project(*values)), fields, jvp_fields
            )
            dbt = sum(
                np.einsum("pcl,l->pc", base_k[key], value.detach().numpy())
                for key, value in zip(PROFILE_KEYS + CLOUD_KEYS, profile_tangent)
            )
            lhs = float(np.sum(dbt * seed_bt))
            rhs = float(np.sum(gx * dx))
            dot = abs(lhs - rhs) / max(abs(lhs), abs(rhs), 1e-12)
            trials = []
            for epsilon in experiment["epsilons"]:
                plus = evaluate_trial(x + epsilon * dx)
                minus = evaluate_trial(x - epsilon * dx)
                eligible = bool(
                    plus["endpoint_eligibility"]["eligible"]
                    and minus["endpoint_eligibility"]["eligible"]
                )
                bt_fd = (plus["bt"] - minus["bt"]) / (2 * epsilon)
                cost_fd = (plus["cost"] - minus["cost"]) / (2 * epsilon)
                bt_ratio = abs(bt_fd - dbt) / (
                    1e-8 + 3e-5 * np.maximum(abs(bt_fd), abs(dbt))
                )
                cost_ratio = abs(cost_fd - rhs) / (
                    1e-8 + 3e-5 * max(abs(cost_fd), abs(rhs))
                )
                trials.append(
                    {
                        "epsilon": epsilon,
                        "eligible": bool(eligible),
                        "BT_FD": bt_fd.tolist(),
                        "cost_FD": float(cost_fd),
                        "plus_cost": plus["cost"],
                        "minus_cost": minus["cost"],
                        "plus_BT": plus["bt"].tolist(),
                        "minus_BT": minus["bt"].tolist(),
                        "plus_endpoint_cfrac": plus["endpoint_cfrac"].tolist(),
                        "minus_endpoint_cfrac": minus["endpoint_cfrac"].tolist(),
                        "plus_endpoint_signature": plus["endpoint_signature"].tolist(),
                        "minus_endpoint_signature": minus[
                            "endpoint_signature"
                        ].tolist(),
                        "plus_quality": plus["quality"].tolist(),
                        "minus_quality": minus["quality"].tolist(),
                        "plus_mask": plus["mask"].tolist(),
                        "minus_mask": minus["mask"].tolist(),
                        "plus_endpoint_eligibility": plus["endpoint_eligibility"],
                        "minus_endpoint_eligibility": minus["endpoint_eligibility"],
                        "max_BT_tolerance_ratio": float(np.max(bt_ratio)),
                        "cost_tolerance_ratio": float(cost_ratio),
                        "passed": bool(
                            eligible and max(np.max(bt_ratio), cost_ratio) <= 1.0
                        ),
                    }
                )
            result["direction_checks"][name] = {
                "direction_spec": direction_spec,
                "BT_JVP": dbt.tolist(),
                "cost_directional_derivative": rhs,
                "dot_lhs": lhs,
                "dot_rhs": rhs,
                "dot_relative_error": dot,
                "direction_x": dx.tolist(),
                "rest_direction": dr.tolist(),
                "profile_tangent": {
                    key: value.detach().numpy().tolist()
                    for key, value in zip(PROFILE_KEYS + CLOUD_KEYS, profile_tangent)
                },
                "post_finish_tangent": dy.tolist(),
                "trials": trials,
                "passed": bool(dot <= 1e-10 and any(row["passed"] for row in trials)),
            }
        result["RTTOV_calls"] = len(calls)
        result["KDM_forward_calls"] = kdm_forward_calls
        result["branch_signature"] = baseline_signature.tolist()
        result["passed"] = all(
            row["passed"] for row in result["direction_checks"].values()
        )
        _check_pins(prepared["source_sha256"])
        return result
    finally:
        microphysics.close(record)


def _write_json_new(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def save_prepared(case_dir, prepared_record):
    """Persist source/experiment identity before any model or RTTOV calls."""
    case_dir = Path(case_dir)
    _write_json_new(case_dir / "prepared.json", prepared_record)


def save_result(case_dir, prepared_record, result):
    case_dir = Path(case_dir)
    if prepared_record["experiment"] != result["experiment"]:
        raise ValueError("prepared/result experiment definitions differ")
    prepared_path = case_dir / "prepared.json"
    if not prepared_path.is_file():
        raise ValueError("prepared.json must be saved before baseline results")
    saved_prepared = json.loads(prepared_path.read_text())
    if saved_prepared != prepared_record:
        raise ValueError("saved prepared.json differs from result provenance")
    _write_json_new(case_dir / "baseline.json", result)


@contextmanager
def _runtime_environment(experiment):
    mode = experiment["factorial_mode"]
    qr_transport = experiment["qr_transport"]
    if mode != "norm_actual":
        raise ValueError("this experiment is pinned to factorial_mode=norm_actual")
    if qr_transport not in ("legacy", "actual_departure"):
        raise ValueError("qr_transport must be legacy or actual_departure")
    values = {
        "KDM6_ICE_FACTORIAL_MODE": mode,
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "OMP_THREAD_LIMIT": "1",
        "OPENBLAS_NUM_THREADS": "1",
    }
    if qr_transport == "actual_departure":
        if mode != "norm_actual":
            raise ValueError("actual_departure requires factorial_mode=norm_actual")
        values["KDM6_QR_TRANSPORT"] = "actual_departure"
    else:
        values["KDM6_QR_TRANSPORT"] = None
    for key in (
        "KDM6_ICE_BOUNDARY_TRACE",
        "KDM6_RAIN_BOUNDARY_TRACE",
        "KDM6_ACTUAL_QR_TRACE",
        "KDM6_SUBSTEP_DUMP",
        "KDM6_SAME_CALL_BUDGET_TRACE",
    ):
        values[key] = None
    old = {key: os.environ.get(key) for key in values}
    try:
        for key, value in values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--library-role", choices=("candidate", "base"), default="candidate"
    )
    parser.add_argument(
        "--library", type=Path, help="explicit library path; role remains metadata only"
    )
    parser.add_argument(
        "--qr-transport",
        choices=("legacy", "actual_departure"),
        default=EXPERIMENT["qr_transport"],
        help="independent QR transport selector; actual_departure requires an attested candidate build",
    )
    for name, path in PATHS.items():
        option = "--" + name.replace("_", "-")
        parser.add_argument(option, type=Path, default=path)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    paths = resolve_paths({name: getattr(args, name) for name in PATHS})
    try:
        output_dir = validate_output_directory(args.output_dir, paths)
    except ValueError as exc:
        parser.error(str(exc))
    experiment = experiment_metadata()
    experiment["qr_transport"] = args.qr_transport
    library = select_library(paths, args.library_role, args.library)
    receipt_path = (
        paths["candidate_build_receipt"] if args.library_role == "candidate" else None
    )
    overlay_path = (
        paths["candidate_overlay_manifest"]
        if args.library_role == "candidate"
        else None
    )
    library = verify_library_transport(
        library, args.qr_transport, receipt_path, overlay_path
    )
    output_dir.mkdir(parents=True)
    results = []
    for target in experiment["targets"]:
        case_target = target_geometry(target, batch_columns=experiment["batch_columns"])
        case_dir = output_dir / f"column_{case_target['flat_index0']:05d}"
        case_dir.mkdir()
        prepared = prepare_inputs(
            paths,
            target,
            library_role=args.library_role,
            library_override=library["path"],
            experiment=experiment,
            workdir=case_dir,
            library_metadata=library,
        )
        prepared_record = {
            "schema": "kdm6.native_candidate_observation_prepared.v1",
            "experiment": experiment_metadata(experiment),
            "target": prepared["target"],
            "library": prepared["library"],
            "source_sha256": prepared["source_sha256"],
            "number_receipt": prepared["number_receipt"],
            "number_receipt_sha256": prepared["number_receipt_sha256"],
            "prep_scalar_maxabs_vs_packet": prepared["prep_scalar_maxabs_vs_packet"],
            "scope": experiment["scope"],
        }
        save_prepared(case_dir, prepared_record)
        result = verify_case(prepared)
        save_result(case_dir, prepared_record, result)
        results.append(result)
    summary = {
        "schema": "kdm6.native_candidate_observation_run.v1",
        "experiment": experiment_metadata(experiment),
        "library": library,
        "targets": [
            {
                "i_1based": r["target"]["i_1based"],
                "j_1based": r["target"]["j_1based"],
                "case_dir": f"column_{r['target']['flat_index0']:05d}",
                "cost": r["cost"],
                "passed": r["passed"],
            }
            for r in results
        ],
        "RTTOV_calls": sum(r["RTTOV_calls"] for r in results),
        "KDM_forward_calls": sum(r["KDM_forward_calls"] for r in results),
        "scope": experiment["scope"],
    }
    with (output_dir / "pilot_results.json").open("x") as stream:
        json.dump(summary, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return 0 if all(result["passed"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
