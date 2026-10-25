"""One bounded native-domain KO7 analysis with streaming first-order products.

This is an offline local microphysics/observation map, not a host timestep.
Completed chunk receipts are reusable only with the same case, source pins,
stage, frozen support and trial controls. No operational install is modified.
"""

from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import multiprocessing
import os
from pathlib import Path
import platform
import re
import resource
import shutil
import subprocess
import sys
import time
import traceback
import uuid

import numpy as np

REPO = Path(__file__).resolve().parents[1]
_EXPECTED_FAILURE_RUN_ID = None  # Invocation-local failure-output ownership.
PILOTS = (0, 34, 40, 128)
CHANNELS = tuple(range(10, 17))
PROFILE_FIELDS = (
    "T",
    "Q",
    "P",
    "P_HALF",
    "HYDRO6",
    "HYDRO7",
    "HYDRO_DEFF6",
    "HYDRO_DEFF7",
)
CASE_SETTINGS = {
    "model_snapshot_time": "2025-07-19_00:00:40",
    "KO_nominal_slot": "202507190000",
    "grid": [282, 234, 39],
    "channels": list(CHANNELS),
    "chunk_columns": 512,
    "physics": "norm_actual+actual_departure_QR",
    "local_physics_dt_seconds": 20,
    "theta_m_scale_K": 0.2,
    "qv_relative_scale": 0.02,
    "regularization_lambda": 1.0,
    "huber_delta": 1.0,
    "observation_sigma_K": 1.0,
    "bias_K": 0.0,
    "trial_alphas": [1.0, 0.5, 0.25],
    "model_quality_required": 0,
    "fixed_baseline_support": True,
    "native_host_steps": 0,
}

RESTRICTED_STAGE = "RESTRICTED_alpha_1p0"
RESTRICTED_FREEZE_BLOCKS = (
    1,
    35,
    51,
    52,
    53,
    54,
    60,
    62,
    64,
    66,
    67,
    69,
    70,
    73,
    82,
    89,
    91,
    93,
    100,
    102,
    108,
    109,
    113,
    118,
    124,
)
PARENT_PUBLICATION = (
    "harness/evidence/native_satellite_case_2026-10-25/data/publication_manifest.json"
)


def validate_request(request):
    if request.get("schema") != "kdm6.native_satellite_case_request.v1":
        raise ValueError("unsupported case request schema")
    if identity(request.get("settings")) != identity(CASE_SETTINGS):
        raise ValueError("case settings differ from the supported bounded experiment")
    epsilons = request.get("fd_epsilons")
    if (
        not isinstance(epsilons, list)
        or len(epsilons) != 2
        or any(
            type(v) not in (float, int) or not math.isfinite(v) or v <= 0
            for v in epsilons
        )
        or len(set(epsilons)) != 2
    ):
        raise ValueError("case requires two distinct positive FD epsilons")
    timeout = request.get("rttov_timeout_seconds", 900.0)
    if (
        type(timeout) not in (int, float)
        or not math.isfinite(timeout)
        or not 0 < timeout <= 3600
    ):
        raise ValueError("RTTOV wall limit must be finite and in (0,3600] seconds")


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def identity(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, allow_nan=False, separators=(",", ":")
        ).encode()
    ).hexdigest()


def publish_json(path, value):
    """Publish a complete JSON file without overwriting a race winner."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, indent=2, allow_nan=False) + "\n"
    temporary = path.parent / (".publish_" + uuid.uuid4().hex)
    try:
        with temporary.open("x") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def save_chunk(folder, arrays, metadata, binding):
    """An abandoned attempt is never a completed chunk or a resume source."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    attempt = folder / ("attempt_" + uuid.uuid4().hex)
    attempt.mkdir()
    artifact = attempt / "result.npz"
    with artifact.open("xb") as stream:
        np.savez_compressed(stream, **arrays)
        stream.flush()
        os.fsync(stream.fileno())
    receipt = dict(
        metadata, binding=binding, artifact=str(artifact), artifact_sha256=sha(artifact)
    )
    publish_json(folder / "receipt.json", receipt)
    return receipt


def read_chunk(folder, binding):
    receipt_path = Path(folder) / "receipt.json"
    if not receipt_path.exists():
        return None
    receipt = json.loads(receipt_path.read_text())
    if receipt.get("binding") != binding:
        raise ValueError(f"completed chunk belongs to a different run/stage: {folder}")
    artifact = Path(receipt["artifact"])
    if artifact.parent.parent.resolve() != Path(folder).resolve():
        raise ValueError("completed artifact is outside its chunk directory")
    if sha(artifact) != receipt["artifact_sha256"]:
        raise ValueError("completed chunk artifact changed")
    return receipt


def load_arrays(receipt):
    encoded = Path(receipt["artifact"]).read_bytes()
    if hashlib.sha256(encoded).hexdigest() != receipt["artifact_sha256"]:
        raise ValueError("completed chunk bytes changed before decoding")
    with np.load(io.BytesIO(encoded), allow_pickle=False) as archive:
        return {name: archive[name] for name in archive.files}


def source_pins(config):
    from harness.run_native_candidate_observation import (
        collect_source_pins,
        select_library,
        verify_library_transport,
    )

    paths = {key: Path(value) for key, value in config["paths"].items()}
    library = verify_library_transport(
        select_library(paths),
        "actual_departure",
        paths["candidate_build_receipt"],
        paths["candidate_overlay_manifest"],
    )
    pins = collect_source_pins(paths, library)
    nml = (paths["template"] / "out/rttov_test.txt").read_text()
    prefix = re.search(r"defn%coef_prefix\s*=\s*'([^']+)'", nml)
    hydro = re.search(
        r"defn%f_hydrotable\s*=\s*'([^']+)'",
        (paths["template"] / "in/coef.txt").read_text(),
    )
    if prefix is None or hydro is None:
        raise ValueError("all-sky case must identify its executed hydrotable")
    hydro_path = (Path(prefix[1]) / hydro[1]).resolve()
    pins[str(hydro_path)] = sha(hydro_path)
    ko_directory = Path(
        config.get("ko_source_directory", "/Users/yhlee/KDM6AD-k/GK2A/00")
    )
    for path in sorted(ko_directory.glob("gk2a_ami_le1b_*_ko*lc_202507190000.nc")):
        pins[str(path.resolve())] = sha(path)
    for name in (
        "prepare_native_satellite_case.py",
        "native_batch_microphysics.py",
        "native_observation_batch.py",
        "native_satellite_objective.py",
        "native_satellite_replay.py",
        "run_native_satellite_case.py",
        "summarize_native_satellite_case.py",
    ):
        path = REPO / "harness" / name
        if path.exists():
            pins[str(path)] = sha(path)
    for entry in config["packet_manifest"]["chunks"]:
        pins[str(paths["packets"] / entry["path"])] = entry["sha256"]
    if config.get("rttov_replay_manifest"):
        recovery_path = Path(config["rttov_replay_manifest"])
        recovery = json.loads(recovery_path.read_text())
        pins[str(recovery_path)] = config["rttov_replay_sha256"]
        pins[recovery["parser_source"]] = recovery["parser_source_sha256"]
        pins[recovery["source_case_manifest"]] = recovery["source_case_manifest_sha256"]
        pins.update(recovery["source_pins"])
        for entry in recovery["entries"]:
            if entry["mode"] == "npz_k":
                pins[entry["receipt_path"]] = entry["receipt_sha256"]
                pins[entry["artifact_path"]] = entry["artifact_sha256"]
            else:
                old_case = Path(entry["case_path"])
                for relative, digest in {
                    **entry["input_files"],
                    **entry["raw_outputs"],
                }.items():
                    pins[str(old_case / relative)] = digest
                failure = entry.get("source_failure_log", {})
                if failure:
                    pins[str(old_case / failure["path"])] = failure["sha256"]
    # Pin current readable dynamic dependencies as well as the executable.
    # System shared-cache images are identified by the OS/runtime metadata.
    if sys.platform == "darwin":
        queue = [paths["rttov_template_executable"], paths["candidate_library"]]
        import torch

        queue += list((Path(torch.__file__).parent / "lib").glob("*.dylib"))
        seen = set()
        while queue:
            binary = Path(queue.pop()).resolve()
            if binary in seen or not binary.is_file():
                continue
            seen.add(binary)
            pins[str(binary)] = sha(binary)
            lines = subprocess.check_output(
                ["otool", "-L", str(binary)], text=True
            ).splitlines()[1:]
            for line in lines:
                name = line.strip().split(" (", 1)[0]
                if name.startswith("/") and Path(name).is_file():
                    queue.append(Path(name))
    return pins


def check_pins(pins):
    for name, expected in pins.items():
        if sha(name) != expected:
            raise ValueError(f"pinned source/input changed: {name}")


def fixed_direction(block):
    """Declared native-input probe, independent of model BT and the gradient."""
    phase = np.arange(block["L"], dtype=np.float64)[None, :]
    flat = block["flat_indices"][:, None]
    admitted = block["initial_admission"]["cost_eligible"][:, None]
    theta = 0.2 * np.sin(0.37 * (phase + 1) + 0.013 * flat) * admitted
    qv = 0.02 * block["qv"] * np.cos(0.29 * (phase + 2) + 0.017 * flat) * admitted
    return np.ascontiguousarray(theta), np.ascontiguousarray(qv)


def tensor(value):
    import torch

    return torch.from_numpy(np.ascontiguousarray(value, dtype=np.float64))


def numpy(value):
    # Explicit first-order checkpoint serialization, never a replacement AD path.
    return np.array(value.detach().cpu().numpy(), copy=True)


def make_physics(config, block):
    from harness.native_batch_microphysics import (
        BatchPrepGeometry,
        NativeBatchMicrophysics,
        make_batch_kernel,
    )
    from oracle.kdm6.native_finish import FinishConfig, ZeroOutConfig
    from oracle.kdm6.native_prep import NativePrepConfig

    kernel = make_batch_kernel(
        config["paths"]["candidate_library"], block["xland"], block["L"]
    )
    return NativeBatchMicrophysics(
        kernel,
        BatchPrepGeometry(
            **{name: tensor(value) for name, value in block["geometry"].items()}
        ),
        NativePrepConfig(**config["prep_configuration"]),
        FinishConfig(**config["finish_configuration"]),
        ZeroOutConfig(**config["zero_out_configuration"]),
    )


def contract_k(k_values, profile_tangents, rows, batch):
    """The actual external first-order K, contracted with a profile JVP."""
    if len(rows) == 0:
        return (
            np.zeros((batch, len(CHANNELS)), dtype=np.float64),
            {
                name: np.empty((0, len(CHANNELS)), dtype=np.float64)
                for name in PROFILE_FIELDS
            },
        )
    total = np.zeros((len(rows), len(CHANNELS)), dtype=np.float64)
    components = {}
    for name in PROFILE_FIELDS:
        k = np.asarray(k_values[name], dtype=np.float64)
        tangent = np.asarray(profile_tangents[name], dtype=np.float64)
        if k.shape[:2] != total.shape or k.shape[2:] != tangent.shape[1:]:
            raise ValueError(f"profile K/JVP metadata differs for {name}")
        products = k * tangent[:, None, :]
        component = np.array(
            [[math.fsum(map(float, row)) for row in profile] for profile in products]
        )
        components[name] = component
    if len(rows):
        total = np.array(
            [
                [
                    math.fsum(float(components[name][b, c]) for name in PROFILE_FIELDS)
                    for c in range(len(CHANNELS))
                ]
                for b in range(len(rows))
            ]
        )
    full = np.zeros((batch, len(CHANNELS)), dtype=np.float64)
    full[rows] = total
    return full, components


def finite_dot(left, right):
    product = np.asarray(left, dtype=np.float64) * np.asarray(right, dtype=np.float64)
    if not np.isfinite(product).all():
        raise ValueError("nonfinite first-order product")
    return math.fsum(map(float, product.ravel()))


def evaluate_block(
    config, block, workspace, *, record, baseline=None, delta=None, z=None,
    effective_input=None,
):
    import torch
    from harness.native_batch_microphysics import NativeBatchDirection
    from harness.native_observation_batch import evaluate_observation_batch, profile_jvp
    from harness.native_satellite_objective import (
        active_control_mask,
        build_fixed_support,
        check_trial_support,
        objective_chunk,
    )

    started = time.monotonic()
    model = make_physics(config, block)
    captured_value_call = None
    if config.get("capture_value_state", False):
        if record:
            raise ValueError("applied-state capture is value-only")
        original_forward = model.kernel.forward
        capture = {}

        def forward_with_value_capture(state, forcing, *, record):
            if record:
                raise ValueError("applied-state capture cannot record an AD call")
            captured_state = np.array(state, dtype=np.float64, order="C", copy=True)
            captured_forcing = np.array(forcing, dtype=np.float64, order="C", copy=True)
            result, handle = original_forward(state, forcing, record=False)
            capture["state"] = captured_state
            capture["forcing"] = captured_forcing
            capture["raw"] = np.array(result, dtype=np.float64, order="C", copy=True)
            return result, handle

        model.kernel.forward = forward_with_value_capture
        captured_value_call = capture
    theta_np, qv_np = block["theta_m"].copy(), block["qv"].copy()
    if effective_input is not None:
        if (effective_input.dtype != np.float64
                or effective_input.shape != (2,) + theta_np.shape
                or not np.isfinite(effective_input).all()):
            raise ValueError("effective_input must be a finite binary64 native T/Q pair")
        theta_np, qv_np = effective_input[0].copy(), effective_input[1].copy()
    elif delta is not None:
        theta_np += delta[0]
        qv_np += delta[1]
    theta = tensor(theta_np).requires_grad_(record)
    qv = tensor(qv_np).requires_grad_(record)
    inputs = (
        theta,
        qv,
        tensor(block["mu"]),
        tensor(block["ph"]),
        tensor(block["rest"]),
    )
    direction_theta, direction_qv = fixed_direction(block)
    if record:
        direction = NativeBatchDirection(
            tensor(direction_theta),
            tensor(direction_qv),
            torch.zeros_like(inputs[3]),
            torch.zeros_like(inputs[4]),
        )
        output, tangent = model.forward_with_jvp(*inputs, direction=direction)
    else:
        with torch.no_grad():
            output = model(*inputs)
        tangent = None
    observed = evaluate_observation_batch(
        block, output, config, Path(workspace), with_k=record
    )
    bt_tensor, quality = observed["bt"], observed["quality"]
    bt = numpy(bt_tensor)
    profile_valid = observed["profile_valid"]
    if baseline is None:
        support = build_fixed_support(
            block["obs_dqf"],
            block["obs_qc_codes"],
            profile_valid,
            quality,
            block["obs_bt"],
            allow_empty=True,
        )
    else:
        support = {
            "m0": baseline["mask"],
            "weights": baseline["weights"],
            "source_eligible": baseline["source_eligible"],
            "Z_partial": float(baseline["weights"].sum()),
        }
    support_error = None
    if baseline is not None:
        try:
            check_trial_support(support, quality, bt)
        except ValueError as exc:
            support_error = str(exc)
    try:
        cost = objective_chunk(bt, block["obs_bt"], support)
    except ValueError:
        if baseline is None:
            raise
        cost = {"numerator": None}
    arrays = {
        "flat_index": block["flat_indices"],
        "obs_bt": block["obs_bt"],
        "bt": bt,
        "quality": quality,
        "mask": support["m0"],
        "weights": support["weights"],
        "source_eligible": support["source_eligible"],
        "reasons": observed["reasons"],
        "profile_valid": profile_valid,
        "theta_m": theta_np,
        "qv": qv_np,
        "active": active_control_mask(support["m0"], block["qv"]),
        "finish": np.stack([numpy(value) for value in output.finish]),
        "rho_d": numpy(output.rho_d),
        "pixel_row": block["pixel_row"],
        "pixel_col": block["pixel_col"],
        "pixel_flat_index": block["pixel_flat_index"],
        "pixel_distance_m": block["pixel_distance_m"],
        "source_dqf": block["obs_dqf"],
        "source_qc": block["obs_qc_raw"],
        "initial_negative_nc": block["initial_admission"]["negative_nc"],
        "initial_negative_ni": block["initial_admission"]["negative_ni"],
        "initial_negative_bg": np.any(block["rest"][9] < 0, axis=1),
    }
    if captured_value_call is not None:
        required_capture = {"state", "forcing", "raw"}
        if set(captured_value_call) != required_capture:
            raise RuntimeError("value-only KDM state capture did not observe one call")
        raw_tensor = torch.as_tensor(
            captured_value_call["raw"],
            dtype=torch.float64,
            device=output.native_profile.thm_pert.device,
        )
        clean_replay = numpy(model._clean(raw_tensor))
        actual_clean = np.concatenate(
            (
                numpy(output.native_profile.qv)[None, ...],
                np.stack([numpy(value) for value in output.cloud_state], axis=0),
            ),
            axis=0,
        )
        clean_matches_output = np.array_equal(clean_replay[1:], actual_clean)
        if not clean_matches_output:
            raise RuntimeError(
                "serialized raw KDM output cleanup differs from the captured value output"
            )
        arrays.update(
            applied_before=captured_value_call["state"],
            applied_forcing=captured_value_call["forcing"],
            applied_raw=captured_value_call["raw"],
            applied_clean_replay=clean_replay,
            applied_clean_matches_output=np.asarray(
                clean_matches_output, dtype=np.bool_
            ),
        )
    for name, value in output.native_profile._asdict().items():
        arrays["native_after_" + name] = numpy(value)
    for name, value in output.cloud_state._asdict().items():
        arrays["cloud_" + name] = numpy(value)
    rows = np.asarray(observed["rows"], dtype=np.int64)
    arrays["profile_rows"] = rows
    for name, value in observed["profile_arrays"].items():
        arrays["profile_" + name] = value
    dot = None
    if record:
        dprofile = profile_jvp(block, output, tangent, config, rows)
        dbt, components = contract_k(observed["k"], dprofile, rows, block["B"])
        seed = tensor(cost["bt_cotangent_numerator"])
        # Even an empty-support chunk is a full-B first-order evaluation.
        linked_bt = bt_tensor + 0.0 * output.native_profile.thm_pert.sum()
        gradients = torch.autograd.grad(linked_bt, (theta, qv), grad_outputs=seed)
        grad_theta, grad_qv = map(numpy, gradients)
        if not np.isfinite(grad_theta).all() or not np.isfinite(grad_qv).all():
            raise ValueError("nonfinite native T/Q gradient")
        lhs = finite_dot(cost["bt_cotangent_numerator"], dbt)
        rhs = math.fsum(
            (finite_dot(grad_theta, direction_theta), finite_dot(grad_qv, direction_qv))
        )
        dot = {
            "lhs": lhs,
            "rhs": rhs,
            "relative_error": abs(lhs - rhs) / max(abs(lhs), abs(rhs), 1e-12),
        }
        arrays.update(
            grad_theta_numerator=grad_theta,
            grad_qv_numerator=grad_qv,
            direction_theta=direction_theta,
            direction_qv=direction_qv,
            bt_jvp=dbt,
        )
        for name in PROFILE_FIELDS:
            arrays["K_" + name] = (
                np.asarray(observed["k"][name])
                if len(rows)
                else np.empty((0, len(CHANNELS), dprofile[name].shape[1]))
            )
            arrays["profile_jvp_" + name] = dprofile[name]
            arrays["BT_jvp_" + name] = components[name]
    if delta is not None:
        arrays.update(delta_theta=delta[0], delta_qv=delta[1], z=z)
    metadata = {
        "chunk_index": block["chunk_index"],
        "start": block["start_flat"],
        "stop": block["stop_flat"],
        "columns": block["B"],
        "Z_partial": float(support["weights"].sum()),
        "observation_numerator": cost["numerator"],
        "dot": dot,
        "support_preserved": support_error is None,
        "support_error": support_error,
        "valid_observations": int(support["m0"].sum()),
        "wall_seconds": time.monotonic() - started,
        "cumulative_process_peak_RSS_bytes": int(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        )
        * (1 if sys.platform == "darwin" else 1024),
        "cumulative_child_peak_RSS_bytes": int(
            resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        )
        * (1 if sys.platform == "darwin" else 1024),
        "calls": {
            "KDM_forward": model.kernel.forward_calls,
            "KDM_JVP": int(record),
            "KDM_VJP": int(record),
            "RTTOV_K": int(observed.get("receipt", {}).get("K_calls", 0)),
            "RTTOV_K_replayed": int(observed.get("receipt", {}).get("K_recovered", 0)),
            "RTTOV_direct": int(observed.get("receipt", {}).get("direct_calls", 0)),
        },
        "RTTOV_receipt": observed.get("receipt", {}),
    }
    if captured_value_call is not None:
        metadata["applied_value_capture"] = {
            "schema": "kdm6.native_applied_value_capture.v1",
            "state_order": [
                "THM_PREP",
                "QV",
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
            "applied_before_row0": "prepared dry theta (includes 300 K reference), not native moist theta_m input control",
            "clean_replay": "same adapter _clean applied to captured raw kernel output; no additional KDM call",
            "clean_matches_output": True,
        }
    return arrays, metadata


def chunk_binding(run_id, stage, index, *, baseline_sha=None, controls_sha=None):
    return identity(
        dict(
            run_id=run_id,
            stage=stage,
            chunk=index,
            baseline_sha=baseline_sha,
            controls_sha=controls_sha,
        )
    )


def evaluate_representable_block(config, block, workspace, *, record, baseline, control):
    """Evaluate an original full-B block at the prepared effective input.

    The stored prior coordinate and observation input describe the same state.
    Original baseline support is retained even when ``record=True`` at a later
    optimization point. This does not differentiate binary32 preparation.
    """
    checkpoint_id = config.get("verified_sources", {}).get("checkpoint", {}).get("sha256")
    if not checkpoint_id or checkpoint_id != control.get("background_checkpoint_id"):
        raise ValueError("effective control and physical evaluator require the same complete background checkpoint")
    rows = np.asarray(block["flat_indices"])
    candidate = np.asarray(control["candidate"])[:, rows, :]
    applied_delta = np.asarray(control["applied_delta"])[:, rows, :]
    effective_z = np.asarray(control["z"])[:, rows, :]
    original = np.stack((block["theta_m"], block["qv"]))
    reconstructed = np.where(applied_delta == 0.0, original, original + applied_delta)
    if (candidate.dtype != np.float64 or candidate.shape != original.shape
            or not np.isfinite(candidate).all()
            or reconstructed.tobytes() != candidate.tobytes()):
        raise ValueError("effective candidate is not reproducible from the original block input")
    scale = np.stack((np.full_like(original[0], 0.2), 0.02 * original[1]))
    actual_z = np.divide(candidate - original, scale, out=np.zeros_like(scale),
                         where=scale > 0.0)
    if (effective_z.tobytes() != actual_z.tobytes()
            or np.any(np.abs(actual_z) > 1.0)):
        raise ValueError("effective prior coordinate differs from the evaluated native input")
    arrays, metadata = evaluate_block(
        config, block, workspace, record=record, baseline=baseline,
        delta=(applied_delta[0], applied_delta[1]), z=effective_z,
        effective_input=candidate,
    )
    if (arrays["theta_m"].tobytes() != candidate[0].tobytes()
            or arrays["qv"].tobytes() != candidate[1].tobytes()):
        raise RuntimeError("observation calculation did not use the prepared effective input")
    arrays.update(
        requested_z=np.asarray(control["requested_z"])[:, rows, :],
        requested_delta=np.asarray(control["requested_delta"])[:, rows, :],
        wire_delta=np.asarray(control["wire_delta"])[:, rows, :],
    )
    metadata["control_application"] = {
        "contract": "binary32 wire delta then binary32 native addition; evaluated as exact widened effective input",
        "background_sha256": control["background_sha256"],
        "background_checkpoint_id": control["background_checkpoint_id"],
        "global_effective_counts": control["counts"],
        "observation_and_prior_use_effective_state": True,
        "quantizer_differentiated": False,
    }
    return arrays, metadata


def write_stage(path, value):
    if path.exists():
        if json.loads(path.read_text()) != value:
            raise ValueError(f"stage summary differs from completed summary: {path}")
    else:
        publish_json(path, value)


def _worker_init():
    import torch

    torch.set_num_threads(1)


def _execute_chunk_job(job):
    from harness.prepare_native_satellite_case import load_case_block

    config, root, run_id, index, stage, base, delta, z, controls_sha = job
    root = Path(root)
    folder = root / stage / f"chunk_{index:05d}"
    binding = chunk_binding(
        run_id,
        stage,
        index,
        baseline_sha=None if base is None else base["artifact_sha256"],
        controls_sha=controls_sha,
    )
    receipt = read_chunk(folder, binding)
    if receipt is not None:
        return receipt, True
    block = load_case_block(config, index)
    temporary = folder / ("rttov_" + uuid.uuid4().hex)
    arrays, metadata = evaluate_block(
        config,
        block,
        temporary,
        record=base is None,
        baseline=None if base is None else load_arrays(base),
        delta=delta,
        z=z,
    )
    receipt = save_chunk(folder, arrays, metadata, binding)
    shutil.rmtree(temporary, ignore_errors=True)
    return receipt, False


def execute_jobs(jobs, workers):
    """Keep at most `workers` independent, single-thread full-B jobs active."""
    receipts = []

    def collect(result):
        receipt, resumed = result
        receipts.append(receipt)
        print(
            json.dumps(
                {
                    "stage": jobs[0][4],
                    "completed": len(receipts),
                    "chunk": receipt["chunk_index"],
                    "columns": receipt["columns"],
                    "resumed": resumed,
                    "wall_seconds": receipt["wall_seconds"],
                    "cost_numerator": receipt["observation_numerator"],
                    "dot": receipt["dot"],
                    "support_preserved": receipt["support_preserved"],
                }
            ),
            flush=True,
        )

    if workers == 1:
        for job in jobs:
            collect(_execute_chunk_job(job))
    else:
        remaining = iter(jobs)
        with ProcessPoolExecutor(
            max_workers=workers,
            mp_context=multiprocessing.get_context("spawn"),
            initializer=_worker_init,
        ) as executor:
            pending = set()
            for _ in range(workers):
                job = next(remaining, None)
                if job is not None:
                    pending.add(executor.submit(_execute_chunk_job, job))
            try:
                while pending:
                    finished, pending = wait(pending, return_when=FIRST_COMPLETED)
                    for future in finished:
                        collect(future.result())
                        job = next(remaining, None)
                        if job is not None:
                            pending.add(executor.submit(_execute_chunk_job, job))
            except BaseException:
                for future in pending:
                    future.cancel()
                raise
    return sorted(receipts, key=lambda item: item["chunk_index"])


def run_baseline(config, root, run_id, indices, *, workers=1):
    jobs = [
        (config, str(root), run_id, index, "baseline", None, None, None, None)
        for index in indices
    ]
    return execute_jobs(jobs, workers)


def baseline_summary(receipts, *, full_domain):
    from harness.native_satellite_objective import global_normalizer

    if full_domain:
        if [row["chunk_index"] for row in receipts] != list(range(129)):
            raise ValueError("baseline is missing or duplicates an original chunk")
        expected_start = 0
        for row in receipts:
            if (
                row["start"] != expected_start
                or row["stop"] - row["start"] != row["columns"]
            ):
                raise ValueError("baseline chunk range is missing or overlapping")
            expected_start = row["stop"]
        if expected_start != 65988:
            raise ValueError("baseline does not cover the full native domain")
    Z = global_normalizer(receipts)
    numerator = math.fsum(row["observation_numerator"] for row in receipts)
    lhs = math.fsum(row["dot"]["lhs"] for row in receipts)
    rhs = math.fsum(row["dot"]["rhs"] for row in receipts)
    error = abs(lhs - rhs) / max(abs(lhs), abs(rhs), 1e-12)
    return {
        "schema": "kdm6.native_satellite_baseline.v1",
        "chunks": receipts,
        "full_domain": full_domain,
        "processed_columns": sum(row["columns"] for row in receipts),
        "globalZ": Z,
        "objective": {
            "J_observation": numerator / Z,
            "J_background": 0.0,
            "J_total": numerator / Z,
        },
        "dot": {
            "lhs": lhs / Z,
            "rhs": rhs / Z,
            "relative_error": error,
            "max_chunk_relative_error": max(
                row["dot"]["relative_error"] for row in receipts
            ),
            "passed": error <= 1e-10
            and all(row["dot"]["relative_error"] <= 1e-10 for row in receipts),
        },
        "call_totals": {
            key: sum(row["calls"][key] for row in receipts)
            for key in receipts[0]["calls"]
        },
    }


def run_fd(config, root, run_id, summary, epsilons):
    from harness.prepare_native_satellite_case import load_case_block

    base_by_index = {row["chunk_index"]: row for row in summary["chunks"]}
    selected = [index for index in PILOTS if index in base_by_index]
    if len(selected) != len(PILOTS):
        raise ValueError("FD requires all four original pilot chunks")
    probe_dots = []
    for index in selected:
        baseline = load_arrays(base_by_index[index])
        dtheta = baseline["direction_theta"] * baseline["active"][0]
        dqv = baseline["direction_qv"] * baseline["active"][1]
        probe_dots.extend(
            (
                finite_dot(baseline["grad_theta_numerator"], dtheta),
                finite_dot(baseline["grad_qv_numerator"], dqv),
            )
        )
    numerator_ad = math.fsum(probe_dots)
    trials = []
    for epsilon in epsilons:
        endpoint_sums = []
        eligible = True
        endpoint_receipts = []
        for sign in (1, -1):
            sign_sum = []
            for index in selected:
                base = base_by_index[index]
                baseline = load_arrays(base)
                block = load_case_block(config, index)
                dtheta = baseline["direction_theta"] * baseline["active"][0]
                dqv = baseline["direction_qv"] * baseline["active"][1]
                delta = (sign * epsilon * dtheta, sign * epsilon * dqv)
                z_probe = np.stack(
                    (
                        delta[0] / 0.2,
                        np.divide(
                            delta[1],
                            0.02 * block["qv"],
                            out=np.zeros_like(delta[1]),
                            where=block["qv"] > 0,
                        ),
                    )
                )
                label = f"fd_eps_{epsilon:g}_{'plus' if sign > 0 else 'minus'}"
                folder = root / label / f"chunk_{index:05d}"
                binding = chunk_binding(
                    run_id,
                    label,
                    index,
                    baseline_sha=base["artifact_sha256"],
                    controls_sha=hashlib.sha256(np.stack(delta).tobytes()).hexdigest(),
                )
                receipt = read_chunk(folder, binding)
                if receipt is None:
                    temporary = folder / ("rttov_" + uuid.uuid4().hex)
                    arrays, metadata = evaluate_block(
                        config,
                        block,
                        temporary,
                        record=False,
                        baseline=baseline,
                        delta=delta,
                        z=z_probe,
                    )
                    receipt = save_chunk(folder, arrays, metadata, binding)
                    shutil.rmtree(temporary, ignore_errors=True)
                endpoint_receipts.append(receipt)
                eligible &= (
                    receipt["support_preserved"]
                    and receipt["observation_numerator"] is not None
                )
                if receipt["observation_numerator"] is not None:
                    # The fixed-background regularizer is included; its
                    # symmetric endpoint contributions cancel analytically.
                    endpoint_z = load_arrays(receipt)["z"]
                    penalty = 0.5 * finite_dot(endpoint_z, endpoint_z)
                    sign_sum.append(
                        math.fsum((receipt["observation_numerator"], penalty))
                    )
            endpoint_sums.append(math.fsum(sign_sum))
        fd = (endpoint_sums[0] - endpoint_sums[1]) / (2 * epsilon * summary["globalZ"])
        ad = numerator_ad / summary["globalZ"]
        ratio = abs(fd - ad) / (1e-8 + 3e-5 * max(abs(fd), abs(ad)))
        trials.append(
            {
                "epsilon": epsilon,
                "AD": ad,
                "FD": fd,
                "tolerance_ratio": ratio,
                "eligible": bool(eligible),
                "passed": bool(eligible and ratio <= 1.0),
                "endpoints": endpoint_receipts,
            }
        )
    result = {
        "scope": "sparse active-control T/Q direction supported on four original full-B chunks; unchanged chunks cancel, prior included",
        "trials": trials,
        "passed": any(row["passed"] for row in trials),
    }
    write_stage(root / "FD.json", result)
    return result


def assemble_controls(summary):
    from harness.native_satellite_objective import bounded_control_step

    arrays = [load_arrays(row) for row in summary["chunks"]]
    flat = np.concatenate([row["flat_index"] for row in arrays])
    if not np.array_equal(flat, np.arange(234 * 282)):
        raise ValueError("full-domain controls require every native index exactly once")
    baseline = np.stack(
        (
            np.concatenate([row["theta_m"] for row in arrays]),
            np.concatenate([row["qv"] for row in arrays]),
        )
    )
    native_gradient = (
        np.stack(
            (
                np.concatenate([row["grad_theta_numerator"] for row in arrays]),
                np.concatenate([row["grad_qv_numerator"] for row in arrays]),
            )
        )
        / summary["globalZ"]
    )
    scale = np.stack((np.full_like(baseline[0], 0.2), 0.02 * baseline[1]))
    active = np.concatenate([row["active"] for row in arrays], axis=1)
    unit = bounded_control_step(baseline, native_gradient, scale, active, 1.0)
    return baseline, active, unit


def run_trials(config, root, run_id, summary, *, workers=1):
    from harness.native_satellite_objective import cost_decreased, finalize_objective

    baseline, active, unit = assemble_controls(summary)
    trials = []
    if unit["max_abs_scaled_gradient"] == 0.0:
        return None, trials, "verified zero active control gradient"
    for alpha in (1.0, 0.5, 0.25):
        label = "TRIAL_alpha_" + str(alpha).replace(".", "p")
        z = alpha * unit["direction_z"]
        delta = np.stack((0.2 * z[0], 0.02 * baseline[1] * z[1]))
        controls_sha = hashlib.sha256(np.ascontiguousarray(z).tobytes()).hexdigest()
        jobs = []
        for base in summary["chunks"]:
            index, start, stop = base["chunk_index"], base["start"], base["stop"]
            jobs.append(
                (
                    config,
                    str(root),
                    run_id,
                    index,
                    label,
                    base,
                    delta[:, start:stop],
                    z[:, start:stop],
                    controls_sha,
                )
            )
        receipts = execute_jobs(jobs, workers)
        valid = all(
            row["support_preserved"] and row["observation_numerator"] is not None
            for row in receipts
        )
        objective = None
        acceptance = {
            "accepted": False,
            "reason": "lost baseline support or invalid profile",
        }
        if valid:
            objective = finalize_objective(
                [row["observation_numerator"] for row in receipts],
                summary["globalZ"],
                z,
                active,
            )
            acceptance = cost_decreased(
                summary["objective"]["J_total"], objective["cost"]
            )
            acceptance["accepted"] = acceptance["decreased"]
        result = {
            "alpha": alpha,
            "chunks": receipts,
            "controls_sha256": controls_sha,
            "globalZ": summary["globalZ"],
            "full_domain": True,
            "objective_valid": valid,
            "objective": objective,
            "acceptance": acceptance,
        }
        write_stage(root / (label + ".json"), result)
        trials.append(label + ".json")
        if acceptance["accepted"]:
            return label + ".json", trials, "same-support cost decrease"
    return None, trials, "no acceptable update within the fixed three-trial budget"


def _validate_parent_chunk(parent_root, stage, row, public_row):
    """Load one parent result only after binding its receipt and artifact bytes."""
    index = row["chunk_index"]
    folder = parent_root / stage / f"chunk_{index:05d}"
    receipt_path = folder / "receipt.json"
    if receipt_path.is_symlink() or not receipt_path.is_file():
        raise ValueError(f"parent {stage} chunk {index} has no regular receipt")
    receipt = json.loads(receipt_path.read_text())
    if sha(receipt_path) != public_row["receipt_sha256"]:
        raise ValueError(f"parent {stage} receipt {index} differs from published hash")
    for key in (
        "chunk_index",
        "start",
        "stop",
        "columns",
        "binding",
        "artifact_sha256",
    ):
        expected = row.get(key)
        if key == "stop":
            expected = row.get("stop")
        if receipt.get(key) != expected:
            raise ValueError(f"parent {stage} receipt {index} disagrees on {key}")
    artifact = Path(receipt["artifact"])
    resolved_folder = folder.resolve(strict=True)
    resolved_artifact = artifact.resolve(strict=True)
    if (
        artifact.is_symlink()
        or resolved_artifact.parent.parent != resolved_folder
        or sha(resolved_artifact) != row["artifact_sha256"]
        or public_row["artifact_sha256"] != row["artifact_sha256"]
    ):
        raise ValueError(f"parent {stage} chunk {index} artifact binding differs")
    if Path(row["artifact"]).resolve(strict=True) != resolved_artifact:
        raise ValueError(f"parent {stage} chunk {index} artifact path differs")
    arrays = load_arrays(row)
    expected_flat = np.arange(row["start"], row["stop"], dtype=np.int32)
    if not np.array_equal(arrays.get("flat_index"), expected_flat):
        raise ValueError(f"parent {stage} chunk {index} native indices differ")
    if row["stop"] - row["start"] != row["columns"]:
        raise ValueError(f"parent {stage} chunk {index} interval length differs")
    return arrays


def _check_parent_source_overlay(parent_manifest):
    """Require source_v3 physics bytes unchanged; allow this runner/objective overlay."""
    source_pins = parent_manifest.get("source_pins")
    if not isinstance(source_pins, dict) or not source_pins:
        raise ValueError("parent CASE_MANIFEST has no source pins")
    check_pins(source_pins)
    roots = []
    for name in source_pins:
        marker = "/source_v3/"
        if marker in name:
            roots.append(name.split(marker, 1)[0] + "/source_v3")
    if not roots:
        raise ValueError("parent source pins do not identify source_v3")
    source_root = Path(roots[0])
    if any(Path(value) != source_root for value in roots):
        raise ValueError("parent source pins reference multiple source_v3 snapshots")
    allowed_overlays = {
        "harness/run_native_satellite_case.py",
        "harness/native_satellite_objective.py",
        "harness/summarize_native_satellite_case.py",
    }
    differences = {}
    for name, expected_sha in source_pins.items():
        marker = "/source_v3/"
        if marker not in name:
            continue
        relative = name.split(marker, 1)[1]
        current = REPO / relative
        if not current.is_file():
            raise ValueError(f"current source_v3 counterpart is missing: {relative}")
        current_sha = sha(current)
        if current_sha != expected_sha:
            if relative not in allowed_overlays:
                raise ValueError(
                    f"physical/source_v3 file differs from parent: {relative}"
                )
            differences[relative] = {
                "parent_source_v3_sha256": expected_sha,
                "current_orchestration_sha256": current_sha,
                "scope": "reviewed restricted-confirmation orchestration/helper overlay",
            }
    return differences


def _baseline_direction(summary):
    """Rebuild the original full-field direction, preserving its signed zeros."""
    arrays = [load_arrays(row) for row in summary["chunks"]]
    flat = np.concatenate([row["flat_index"] for row in arrays])
    if not np.array_equal(flat, np.arange(65988, dtype=np.int32)):
        raise ValueError("restricted candidate requires complete parent native indices")
    baseline = np.stack(
        (
            np.concatenate([row["theta_m"] for row in arrays]),
            np.concatenate([row["qv"] for row in arrays]),
        )
    )
    gradient = (
        np.stack(
            (
                np.concatenate([row["grad_theta_numerator"] for row in arrays]),
                np.concatenate([row["grad_qv_numerator"] for row in arrays]),
            )
        )
        / summary["globalZ"]
    )
    scale = np.stack((np.full_like(baseline[0], 0.2), 0.02 * baseline[1]))
    active = np.concatenate([row["active"] for row in arrays], axis=1)
    if active.shape != gradient.shape or active.dtype != np.bool_:
        raise ValueError("parent active-control mask differs from gradient arrays")
    direction = _fullfield_direction(gradient, scale, active)
    return flat, baseline, active, direction


def _fullfield_direction(gradient, scale, active):
    """Apply the original full-array `-Sg/max(abs(Sg))` operation order."""
    gradient = np.asarray(gradient)
    scale = np.asarray(scale)
    active = np.asarray(active)
    if (
        gradient.dtype != np.float64
        or scale.dtype != np.float64
        or active.dtype != np.bool_
        or gradient.shape != scale.shape
        or gradient.shape != active.shape
        or not np.isfinite(gradient).all()
        or not np.isfinite(scale).all()
    ):
        raise ValueError(
            "restricted direction inputs must be matching finite float64/bool arrays"
        )
    scaled = np.where(active, scale * gradient, 0.0)
    maximum = float(np.max(np.abs(scaled)))
    if not math.isfinite(maximum) or maximum <= 0.0:
        raise ValueError("parent baseline has no finite active direction")
    # This full-array division preserves the declared signed-zero bytes.
    return -scaled / maximum


def _read_public_parent_bundle(candidate):
    public_root = REPO / "harness/evidence/native_satellite_case_2026-10-25/data"
    manifest_path = public_root / "publication_manifest.json"
    if sha(manifest_path) != candidate["parent_publication_manifest_sha256"]:
        raise ValueError(
            "candidate does not bind the checked parent publication manifest"
        )
    manifest = json.loads(manifest_path.read_text())
    if (
        manifest.get("run_id") != candidate["parent_run_id"]
        or manifest.get("status") != "COMPLETED_NO_ACCEPTABLE_UPDATE"
        or manifest.get("schema")
        not in (
            "kdm6.native_satellite_publication_pack.v1",
            "kdm6.native_satellite_publication_pack.v2",
        )
    ):
        raise ValueError("published parent run identity/status differs")

    def read(name):
        record = manifest.get("artifacts", {}).get(name)
        if not isinstance(record, dict):
            raise ValueError(f"parent publication does not pin {name}")
        path = (public_root / name).resolve(strict=True)
        if public_root.resolve() not in path.parents:
            raise ValueError(f"parent publication artifact escapes bundle: {name}")
        if path.stat().st_size != record["bytes"] or sha(path) != record["sha256"]:
            raise ValueError(f"parent publication artifact hash differs: {name}")
        return json.loads(path.read_text())

    def read_npz(name):
        record = manifest.get("artifacts", {}).get(name)
        if not isinstance(record, dict):
            raise ValueError(f"parent publication does not pin {name}")
        path = (public_root / name).resolve(strict=True)
        if public_root.resolve() not in path.parents:
            raise ValueError(f"parent publication artifact escapes bundle: {name}")
        if path.stat().st_size != record["bytes"] or sha(path) != record["sha256"]:
            raise ValueError(f"parent publication artifact hash differs: {name}")
        with np.load(path, allow_pickle=False) as archive:
            return {key: np.array(archive[key], copy=True) for key in archive.files}

    return manifest, read, read_npz, public_root


def _restricted_screen(
    parent_root,
    baseline_summary,
    old_trial,
    baseline_rows,
    trial_rows,
    z,
    active,
    frozen_blocks,
):
    from harness.native_satellite_objective import (
        check_trial_support,
        finalize_objective,
        objective_chunk,
    )

    numerators = []
    expected_by_chunk = {}
    for base_row in baseline_summary["chunks"]:
        index = base_row["chunk_index"]
        base_arrays = baseline_rows[index]
        trial_arrays = trial_rows[index]
        chosen = base_arrays if index in frozen_blocks else trial_arrays
        support = {
            "m0": base_arrays["mask"],
            "weights": base_arrays["weights"],
            "source_eligible": base_arrays["source_eligible"],
        }
        check_trial_support(support, chosen["quality"], chosen["bt"])
        cost = objective_chunk(chosen["bt"], base_arrays["obs_bt"], support)
        numerators.append(cost["numerator"])
        expected_by_chunk[index] = chosen
    screen = finalize_objective(numerators, baseline_summary["globalZ"], z, active)
    return screen, expected_by_chunk


def _make_restricted_jobs(
    config,
    root,
    run_id,
    baseline_summary,
    z,
    baseline_rows,
    frozen_blocks,
    controls_sha,
):
    jobs = []
    expected_indices = list(range(129))
    rows = baseline_summary["chunks"]
    if [row["chunk_index"] for row in rows] != expected_indices:
        raise ValueError(
            "restricted confirmation parent chunks are missing or duplicated"
        )
    expected_start = 0
    for base in rows:
        start, stop, index = base["start"], base["stop"], base["chunk_index"]
        if start != expected_start or stop - start != base["columns"]:
            raise ValueError(
                "restricted confirmation parent partition overlaps or skips"
            )
        expected_columns = 512 if index < 128 else 452
        if base["columns"] != expected_columns:
            raise ValueError("restricted confirmation must keep 128×B512 plus B452")
        expected_start = stop
        base_arrays = baseline_rows[index]
        flat = base_arrays["flat_index"]
        if not np.array_equal(flat, np.arange(start, stop, dtype=np.int32)):
            raise ValueError(f"restricted parent chunk {index} has reordered indices")
        zi = np.ascontiguousarray(z[:, start:stop, :])
        delta = np.stack((0.2 * zi[0], 0.02 * base_arrays["qv"] * zi[1]))
        if index in frozen_blocks:
            if np.any(zi) or np.any(delta):
                raise ValueError(f"frozen parent block {index} has nonzero controls")
        jobs.append(
            (
                config,
                str(root),
                run_id,
                index,
                RESTRICTED_STAGE,
                base,
                delta,
                zi,
                controls_sha,
            )
        )
    if expected_start != 65988:
        raise ValueError("restricted confirmation does not cover the full native grid")
    return jobs


def run_restricted_confirmation(args):
    """Confirm one parent-hash-bound projected alpha=1 candidate over 129 blocks."""
    global _EXPECTED_FAILURE_RUN_ID
    from harness.prepare_native_satellite_case import load_case_config
    from harness.run_native_candidate_observation import (
        _runtime_environment,
        EXPERIMENT,
    )
    from harness.native_satellite_objective import (
        COST_ACCEPT_ATOL,
        COST_ACCEPT_RTOL,
        cost_decreased,
        finalize_objective,
        restrict_control_blocks,
    )
    from oracle.kdm6.obs.rttov_runner import _child_env
    import torch

    parent_root = args.parent_run.resolve(strict=True)
    if (
        parent_root == parent_root.parent
        or not (parent_root / "CASE_MANIFEST.json").is_file()
    ):
        raise ValueError(
            "--parent-run must identify the completed native satellite run"
        )
    if args.candidate_json.is_symlink():
        raise ValueError("--candidate-json must not be a symlink")
    candidate_path = args.candidate_json.resolve(strict=True)
    if not candidate_path.is_file():
        raise ValueError("--candidate-json must be a regular file")
    candidate = json.loads(candidate_path.read_text())
    expected_candidate_keys = {
        "schema",
        "experiment_type",
        "parent_run_id",
        "parent_publication_manifest_sha256",
        "freeze_blocks_0based",
        "selected_alpha",
        "direction_recipe",
        "renormalize_after_projection",
        "control_npz",
        "control_npz_sha256",
        "control_z_sha256",
        "globalZ",
        "fixed_baseline_support",
        "expected_screen_J_total",
        "expected_screen_J_obs",
        "expected_screen_J_prior",
        "cost_accept_atol",
        "cost_accept_rtol",
        "max_full_domain_confirmation_runs",
        "workers",
        "threads_per_worker_and_child",
        "export_applied_tendencies",
        "screen_audit_sha256",
        "plan_sha256",
        "proposal_basis",
        "signed_zero_qualification",
        "scope",
        "supersedes_candidate_spec_sha256",
        "screen_source_scope",
    }
    if (
        set(candidate) != expected_candidate_keys
        or candidate.get("schema") != "kdm6.native_satellite_restricted_candidate.v1"
    ):
        raise ValueError("restricted candidate schema/fields differ")
    if (
        candidate["freeze_blocks_0based"] != list(RESTRICTED_FREEZE_BLOCKS)
        or type(candidate["selected_alpha"]) not in (int, float)
        or float(candidate["selected_alpha"]) != 1.0
        or not math.isfinite(float(candidate["expected_screen_J_total"]))
        or candidate["experiment_type"] != "restricted_block_confirmation_v1"
        or candidate["renormalize_after_projection"] is not False
        or candidate["globalZ"] != 381528.0
        or candidate["fixed_baseline_support"] is not True
        or candidate["cost_accept_atol"] != COST_ACCEPT_ATOL
        or candidate["cost_accept_rtol"] != COST_ACCEPT_RTOL
        or candidate["max_full_domain_confirmation_runs"] != 1
        or candidate["threads_per_worker_and_child"] != 1
        or candidate["export_applied_tendencies"] != ["H_RATE", "QV_RATE", "QC_RATE"]
        or candidate["direction_recipe"]
        != "d0=-where(active,S*g_native,0)/max(abs(where(active,S*g_native,0))); assign +0.0 to both control coordinates in every frozen original block"
        or candidate["screen_source_scope"]
        != "Independent source-bound arithmetic audit; physics execution authority remains immutable parent source_v3 plus separately pinned confirmation orchestration."
    ):
        raise ValueError(
            "restricted candidate must be the pinned alpha=1 block projection"
        )
    if args.workers is None:
        args.workers = candidate["workers"]
    if (
        type(candidate["workers"]) is not int
        or candidate["workers"] not in (1, 2, 3)
        or args.workers != candidate["workers"]
    ):
        raise ValueError("restricted worker count must match the candidate manifest")
    candidate_root = candidate_path.parent.resolve(strict=True)
    control_rel = Path(candidate["control_npz"])
    if control_rel.is_absolute() or ".." in control_rel.parts:
        raise ValueError("restricted control NPZ path must be relative to its manifest")
    raw_candidate_npz = candidate_root / control_rel
    if raw_candidate_npz.is_symlink():
        raise ValueError("restricted control NPZ must not be a symlink")
    candidate_npz = raw_candidate_npz.resolve(strict=True)
    if candidate_root not in candidate_npz.parents:
        raise ValueError(
            "restricted control NPZ must be owned by the candidate directory"
        )
    if sha(candidate_npz) != candidate["control_npz_sha256"]:
        raise ValueError("restricted control NPZ hash differs")
    screen_audit_path = candidate_root / "restricted_block_screen.json"
    if (
        screen_audit_path.is_symlink()
        or sha(screen_audit_path) != candidate["screen_audit_sha256"]
    ):
        raise ValueError("restricted candidate screen audit hash differs")
    screen_audit = json.loads(screen_audit_path.read_text())
    if (
        screen_audit.get("schema") != "kdm6.native_satellite_restricted_block_screen.v1"
        or screen_audit.get("status") != "SCREENED_CANDIDATE_READY"
        or screen_audit.get("new_kdm_rttov_host_calls") != 0
        or screen_audit.get("parent_run_id") != candidate["parent_run_id"]
        or screen_audit.get("parent_publication_manifest_sha256")
        != candidate["parent_publication_manifest_sha256"]
        or screen_audit.get("restricted_direction", {}).get("alpha_1_control_z_sha256")
        != candidate["control_z_sha256"]
    ):
        raise ValueError("restricted source-bound screen audit identity differs")
    superseded_spec = (
        REPO
        / "harness/evidence/native_satellite_restricted_2026-10-25/restricted_candidate.json"
    )
    if (
        superseded_spec.is_symlink()
        or not superseded_spec.is_file()
        or sha(superseded_spec) != candidate["supersedes_candidate_spec_sha256"]
    ):
        raise ValueError(
            "restricted source-bound candidate does not bind its preserved prior spec"
        )
    with np.load(candidate_npz, allow_pickle=False) as archive:
        if set(archive.files) != {"z"}:
            raise ValueError("restricted control NPZ must contain only z")
        candidate_z = np.array(archive["z"], copy=True)
    if (
        candidate_z.dtype != np.float64
        or candidate_z.shape != (2, 65988, 39)
        or not np.isfinite(candidate_z).all()
        or not candidate_z.flags.c_contiguous
    ):
        raise ValueError(
            "restricted z must be C-order finite float64 with native shape"
        )
    candidate_z_sha = hashlib.sha256(candidate_z.tobytes()).hexdigest()
    if candidate_z_sha != candidate["control_z_sha256"]:
        raise ValueError("restricted control vector hash differs")

    parent_case_path = parent_root / "CASE_MANIFEST.json"
    parent_base_path = parent_root / "BASELINE.json"
    parent_final_path = parent_root / "FINAL.json"
    parent_case = json.loads(parent_case_path.read_text())
    parent_summary = json.loads(parent_base_path.read_text())
    parent_final = json.loads(parent_final_path.read_text())
    if parent_case.get("run_id") != candidate["parent_run_id"]:
        raise ValueError("candidate parent run ID differs from CASE_MANIFEST")
    if (
        parent_final.get("status") != "COMPLETED_NO_ACCEPTABLE_UPDATE"
        or parent_final.get("accepted_trial") is not None
        or parent_summary.get("full_domain") is not True
        or parent_summary.get("processed_columns") != 65988
        or len(parent_summary.get("chunks", [])) != 129
        or parent_summary.get("globalZ") != 381528.0
    ):
        raise ValueError(
            "restricted candidate parent is not the exact completed full-domain case"
        )
    parent_source_differences = _check_parent_source_overlay(parent_case)
    request = parent_case.get("request")
    validate_request(request)
    config = load_case_config(request.get("paths"))
    config["rttov_timeout_seconds"] = float(request.get("rttov_timeout_seconds", 900.0))
    config.pop("rttov_replay_manifest", None)
    config.pop("rttov_replay_sha256", None)
    config["capture_value_state"] = True

    public_manifest, read_public, read_public_npz, public_root = (
        _read_public_parent_bundle(candidate)
    )
    public_receipts = read_public("execution_receipts.json")
    public_trials = read_public("trials/trials.json")
    public_summary = read_public("summary.json")
    public_scope = read_public("scope.json")
    read_public("source_manifest.json")
    public_support = read_public_npz("observation_support.npz")
    public_bt = read_public_npz("channel_bt.npz")
    if (
        public_manifest.get("full_domain_columns") != 65988
        or public_manifest.get("grid") != [282, 234, 39]
        or public_receipts.get("run_id") != parent_case["run_id"]
        or len(public_receipts["baseline"]["chunks"]) != 129
        or public_summary.get("globalZ") != 381528.0
        or public_summary.get("baseline_objective", {}).get("J_total")
        != parent_summary["objective"]["J_total"]
        or public_summary.get("accepted_trial") is not None
        or public_scope.get("fixed_baseline_support") is not True
    ):
        raise ValueError(
            "public parent bundle does not bind the original domain execution"
        )
    public_trial = next((row for row in public_trials if row.get("alpha") == 1.0), None)
    private_trial_path = parent_root / "TRIAL_alpha_1p0.json"
    if public_trial is None or not private_trial_path.is_file():
        raise ValueError("parent alpha=1 trial records are missing")
    private_trial = json.loads(private_trial_path.read_text())
    if (
        private_trial.get("alpha") != 1.0
        or private_trial.get("objective_valid") is not False
        or public_trial.get("support_preserved") is not False
        or public_trial.get("objective_valid") is not False
        or public_trial.get("objective") is not None
        or private_trial.get("controls_sha256") != public_trial.get("controls_sha256")
    ):
        raise ValueError("parent alpha=1 rejected trial identity differs")

    baseline_rows, trial_rows = {}, {}
    public_baseline = {
        row["chunk_index"]: row for row in public_receipts["baseline"]["chunks"]
    }
    public_trial_chunks = {row["chunk_index"]: row for row in public_trial["chunks"]}
    private_trial_chunks = {row["chunk_index"]: row for row in private_trial["chunks"]}
    if (
        set(public_baseline) != set(range(129))
        or set(public_trial_chunks) != set(range(129))
        or set(private_trial_chunks) != set(range(129))
    ):
        raise ValueError(
            "parent baseline or alpha=1 trial does not contain all 129 chunks"
        )
    for base_row in parent_summary["chunks"]:
        index = base_row["chunk_index"]
        baseline_rows[index] = _validate_parent_chunk(
            parent_root, "baseline", base_row, public_baseline[index]
        )
        trial_row = private_trial_chunks[index]
        public_row = public_trial_chunks[index]
        if (
            trial_row["chunk_index"] != index
            or trial_row["artifact_sha256"] != public_row["artifact_sha256"]
            or trial_row["start"] != base_row["start"]
            or trial_row["stop"] != base_row["stop"]
        ):
            raise ValueError(f"parent alpha=1 trial chunk {index} binding differs")
        trial_rows[index] = _validate_parent_chunk(
            parent_root, "TRIAL_alpha_1p0", trial_row, public_row
        )
    invalid_old_blocks = {
        row["chunk_index"]
        for row in private_trial["chunks"]
        if not row["support_preserved"]
    }
    if invalid_old_blocks != set(RESTRICTED_FREEZE_BLOCKS):
        raise ValueError(
            "candidate freeze set differs from original alpha=1 support failures"
        )
    public_mask = public_support["mask"]
    public_weights = public_support["weights"]
    if (
        not np.array_equal(public_support["flat_index"], np.arange(65988))
        or not np.array_equal(public_bt["flat_index"], np.arange(65988))
        or public_mask.shape != (65988, 7)
        or math.fsum(public_weights.ravel().tolist()) != 381528.0
    ):
        raise ValueError("parent public support/index/normalizer differs")
    for row in parent_summary["chunks"]:
        arrays = baseline_rows[row["chunk_index"]]
        sl = slice(row["start"], row["stop"])
        for name in (
            "mask",
            "weights",
            "source_eligible",
            "raw_source_valid",
            "profile_valid",
            "active",
        ):
            if name == "raw_source_valid":
                source_valid = (
                    (arrays["source_dqf"] == 0)
                    & (arrays["source_qc"] == 0)
                    & np.isfinite(arrays["obs_bt"])
                )
                public_values = public_support[name][sl]
            elif name == "active":
                source_valid = arrays[name]
                public_values = public_support[name][:, sl, :]
            else:
                source_valid = arrays[name]
                public_values = public_support[name][sl]
            if not np.array_equal(source_valid, public_values):
                raise ValueError(f"parent private/public fixed support differs: {name}")
    flat, baseline, active, direction = _baseline_direction(parent_summary)
    z = restrict_control_blocks(
        direction, flat, RESTRICTED_FREEZE_BLOCKS, chunk_columns=512
    )
    if not np.array_equal(z.tobytes(), candidate_z.tobytes()):
        raise ValueError(
            "candidate z differs bytewise from original-gradient projection"
        )
    controls_sha = hashlib.sha256(np.ascontiguousarray(z).tobytes()).hexdigest()
    if controls_sha != candidate["control_z_sha256"]:
        raise ValueError("projected control hash differs from candidate manifest")

    screen, expected_by_chunk = _restricted_screen(
        parent_root,
        parent_summary,
        private_trial,
        baseline_rows,
        trial_rows,
        z,
        active,
        set(RESTRICTED_FREEZE_BLOCKS),
    )
    expected_screen = float(candidate["expected_screen_J_total"])
    if (
        screen["cost"] != expected_screen
        or screen["observation_numerator"] / screen["Z"]
        != candidate["expected_screen_J_obs"]
        or screen["regularization_numerator"] / screen["Z"]
        != candidate["expected_screen_J_prior"]
    ):
        raise ValueError(
            "stored candidate screen cost differs from exact saved-array reconstruction"
        )

    torch.set_num_threads(1)
    with _runtime_environment(EXPERIMENT):
        rt_environment = {
            name: value
            for name, value in _child_env().items()
            if name.startswith(
                (
                    "OMP_",
                    "MKL_",
                    "OPENBLAS_",
                    "VECLIB_",
                    "DYLD_",
                    "LD_",
                    "GFORTRAN_",
                    "RTTOV_",
                    "AD_RTTOV_",
                    "KDM6_",
                )
            )
        }
    current_runtime = {
        "python": sys.version,
        "python_executable": sys.executable,
        "torch": torch.__version__,
        "numpy": np.__version__,
        "machine": platform.machine(),
        "platform": platform.platform(),
        "RT_environment_sha256": identity(rt_environment),
        "RT_environment_names": sorted(rt_environment),
        "torch_threads": torch.get_num_threads(),
    }
    parent_runtime = parent_case.get("runtime", {})
    runtime_keys = (
        "python",
        "python_executable",
        "torch",
        "numpy",
        "machine",
        "platform",
        "RT_environment_sha256",
        "RT_environment_names",
        "torch_threads",
    )
    if any(parent_runtime.get(key) != current_runtime[key] for key in runtime_keys):
        raise ValueError(
            "restricted confirmation runtime differs from parent execution"
        )
    source_pins_current = source_pins(config)
    parent_input_paths = [
        parent_case_path,
        parent_base_path,
        parent_final_path,
        private_trial_path,
        candidate_path,
        candidate_npz,
        screen_audit_path,
        superseded_spec,
        public_root / "publication_manifest.json",
    ]
    for name in (
        "execution_receipts.json",
        "trials/trials.json",
        "summary.json",
        "scope.json",
        "source_manifest.json",
        "observation_support.npz",
        "channel_bt.npz",
    ):
        parent_input_paths.append(public_root / name)
    for stage_name, rows_to_pin in (
        ("baseline", parent_summary["chunks"]),
        ("TRIAL_alpha_1p0", private_trial["chunks"]),
    ):
        for row in rows_to_pin:
            chunk_folder = parent_root / stage_name / f"chunk_{row['chunk_index']:05d}"
            parent_input_paths.append(chunk_folder / "receipt.json")
            parent_input_paths.append(Path(row["artifact"]))
    for path in parent_input_paths:
        resolved = Path(path).resolve(strict=True)
        source_pins_current[str(resolved)] = sha(resolved)
    check_pins(source_pins_current)
    run_contract = {
        "experiment_type": "restricted_block_confirmation_v1",
        "parent_run_id": parent_case["run_id"],
        "parent_case_manifest_sha256": sha(parent_case_path),
        "parent_baseline_sha256": sha(parent_base_path),
        "parent_final_sha256": sha(parent_final_path),
        "parent_publication_manifest_sha256": candidate[
            "parent_publication_manifest_sha256"
        ],
        "parent_trial_sha256": sha(private_trial_path),
        "candidate_json_sha256": sha(candidate_path),
        "candidate_control_npz_sha256": candidate["control_npz_sha256"],
        "candidate_control_z_sha256": controls_sha,
        "freeze_blocks_0based": list(RESTRICTED_FREEZE_BLOCKS),
        "selected_alpha": 1.0,
        "expected_screen_J_total": expected_screen,
        "no_renormalization_after_projection": True,
        "parent_source_v3_overlay_differences": parent_source_differences,
        "source_pins": source_pins_current,
        "runtime": current_runtime,
        "case_preparation": config,
        "capture_value_state": True,
        "rttov_mode": "direct only; no K/AD/recovery",
    }
    run_id = identity(run_contract)
    _EXPECTED_FAILURE_RUN_ID = run_id
    root = args.output_root.absolute()
    if root.is_symlink() or any(parent.is_symlink() for parent in root.parents):
        raise ValueError("restricted run output must not traverse symlinks")
    resolved_root = root.resolve()
    if resolved_root == REPO.resolve() or REPO.resolve() in resolved_root.parents:
        raise ValueError(
            "restricted run artifacts must be outside the public source checkout"
        )
    if (
        resolved_root == parent_root
        or resolved_root in parent_root.parents
        or parent_root in resolved_root.parents
    ):
        raise ValueError(
            "restricted run output must not overlap or contain the parent run"
        )
    if (
        resolved_root == candidate_root
        or resolved_root in candidate_root.parents
        or candidate_root in resolved_root.parents
    ):
        raise ValueError(
            "restricted run output must not overlap or contain the candidate input"
        )
    if (
        resolved_root == public_root.resolve()
        or resolved_root in public_root.resolve().parents
        or public_root.resolve() in resolved_root.parents
    ):
        raise ValueError(
            "restricted run output must not overlap or contain the parent publication"
        )
    if root.exists() and not args.resume:
        raise FileExistsError("restricted output root exists; use explicit --resume")
    for path in list(config["paths"].values()) + [
        str(candidate_path),
        str(candidate_npz),
        str(parent_root),
    ]:
        source = Path(path).resolve()
        if (
            resolved_root == source
            or resolved_root in source.parents
            or source in resolved_root.parents
        ):
            raise ValueError("restricted output overlaps a pinned input")
    jobs = _make_restricted_jobs(
        config,
        root,
        run_id,
        parent_summary,
        z,
        baseline_rows,
        set(RESTRICTED_FREEZE_BLOCKS),
        controls_sha,
    )
    if args.preflight_only:
        print(
            json.dumps(
                {
                    "status": "PREFLIGHT_VALID",
                    "run_id": run_id,
                    "parent_run_id": parent_case["run_id"],
                    "control_z_sha256": controls_sha,
                    "screen_objective": expected_screen,
                    "blocks_planned": len(jobs),
                    "processed_columns_planned": sum(job[5]["columns"] for job in jobs),
                    "new_KDM_RTTOV_host_calls": 0,
                    "output_root_created": False,
                }
            ),
            flush=True,
        )
        return 0
    root.mkdir(parents=True, exist_ok=True)
    run_contract["run_id"] = run_id
    write_stage(root / "CASE_MANIFEST.json", run_contract)
    config["run_id"] = run_id
    execution_path = root / "executions" / (uuid.uuid4().hex + ".json")
    publish_json(
        execution_path,
        {
            "workers": args.workers,
            "threads_per_worker": 1,
            "stage": RESTRICTED_STAGE,
            "run_id": run_id,
            "parent_run_id": parent_case["run_id"],
            "control_z_sha256": controls_sha,
            "chunks": list(range(129)),
            "command": sys.argv,
            "started_at_UTC": datetime.now(timezone.utc).isoformat(),
        },
    )
    with _runtime_environment(EXPERIMENT):
        receipts = execute_jobs(jobs, workers=args.workers)
    if [row["chunk_index"] for row in receipts] != list(range(129)):
        raise ValueError("restricted confirmation did not complete all 129 chunks")
    support_valid = all(
        row["support_preserved"] and row["observation_numerator"] is not None
        for row in receipts
    )
    z_total = math.fsum(row["Z_partial"] for row in receipts)
    if z_total != parent_summary["globalZ"]:
        raise ValueError("restricted confirmation changed frozen support normalizer")
    call_totals = {
        key: sum(row["calls"][key] for row in receipts) for key in receipts[0]["calls"]
    }
    if (
        call_totals["KDM_forward"] != 129
        or call_totals["KDM_JVP"] != 0
        or call_totals["KDM_VJP"] != 0
        or call_totals["RTTOV_K"] != 0
        or call_totals["RTTOV_K_replayed"] != 0
        or any(row["calls"]["KDM_forward"] != 1 for row in receipts)
        or any(row.get("RTTOV_receipt", {}).get("mode") != "direct" for row in receipts)
    ):
        raise ValueError(
            "restricted confirmation call ledger is not one value-only full-B call per block"
        )
    if not 0 <= call_totals["RTTOV_direct"] <= 129:
        raise ValueError(
            "restricted confirmation direct-call count is outside the full-block bound"
        )
    expected_direct = sum(
        int(row["RTTOV_receipt"].get("nprofiles", 0) > 0) for row in receipts
    )
    if call_totals["RTTOV_direct"] != expected_direct:
        raise ValueError(
            "restricted confirmation direct RTTOV calls differ from eligible block count"
        )

    mismatched_blocks = []
    lost_supported_observations = 0
    for row in receipts:
        index = row["chunk_index"]
        actual = load_arrays(row)
        base = baseline_rows[index]
        expected = expected_by_chunk[index]
        if not np.array_equal(actual["mask"], base["mask"]) or not np.array_equal(
            actual["weights"], base["weights"]
        ):
            raise ValueError(
                f"restricted confirmation altered frozen baseline support in block {index}"
            )
        m0 = base["mask"]
        if (
            actual["quality"][m0].tobytes() != expected["quality"][m0].tobytes()
            or actual["bt"][m0].tobytes() != expected["bt"][m0].tobytes()
            or not np.array_equal(
                actual["profile_valid"][m0.any(axis=1)],
                expected["profile_valid"][m0.any(axis=1)],
            )
        ):
            mismatched_blocks.append(index)
        lost = m0 & (
            (actual["quality"] != 0)
            | ~np.isfinite(actual["bt"])
            | ~actual["profile_valid"][:, None]
        )
        lost_supported_observations += int(lost.sum())
    actual_objective = None
    cost_result = None
    screen_cost_matches = None
    if support_valid:
        objective = finalize_objective(
            [row["observation_numerator"] for row in receipts],
            z_total,
            z,
            active,
        )
        actual_objective = objective
        cost_result = cost_decreased(
            parent_summary["objective"]["J_total"], objective["cost"]
        )
        screen_cost_matches = objective["cost"] == expected_screen
    decision_status = (
        "REPRODUCTION_MISMATCH"
        if mismatched_blocks or screen_cost_matches is False
        else "RESTRICTED_UPDATE_NOT_ACCEPTED"
        if not support_valid
        else "RESTRICTED_UPDATE_ACCEPTED"
        if cost_result["decreased"]
        else "RESTRICTED_UPDATE_NOT_ACCEPTED"
    )
    check_pins(source_pins_current)
    check_pins(parent_case["source_pins"])
    confirmation = {
        "schema": "kdm6.native_satellite_restricted_confirmation.v1",
        "status": decision_status,
        "run_id": run_id,
        "parent_run_id": parent_case["run_id"],
        "parent_publication_manifest_sha256": candidate[
            "parent_publication_manifest_sha256"
        ],
        "candidate_json_sha256": sha(candidate_path),
        "control_npz_sha256": candidate["control_npz_sha256"],
        "controls_sha256": controls_sha,
        "stage": RESTRICTED_STAGE,
        "freeze_blocks_0based": list(RESTRICTED_FREEZE_BLOCKS),
        "selected_alpha": 1.0,
        "full_domain": True,
        "processed_columns": 65988,
        "blocks": len(receipts),
        "globalZ": z_total,
        "fixed_support_preserved": support_valid,
        "lost_supported_observations": lost_supported_observations,
        "stitched_B_equal_on_baseline_support": not mismatched_blocks,
        "stitched_mismatched_blocks": mismatched_blocks,
        "actual_cost_matches_screen": screen_cost_matches,
        "screen_objective": expected_screen,
        "actual_objective": actual_objective,
        "cost_acceptance": cost_result,
        "call_totals": call_totals,
        "chunks": receipts,
        "completed_at_UTC": datetime.now(timezone.utc).isoformat(),
        "native_host_steps": 0,
        "native_cycles": 0,
        "final_publication_pending": True,
    }
    write_stage(root / "CONFIRMATION.json", confirmation)
    print(
        json.dumps(
            {
                k: confirmation[k]
                for k in (
                    "status",
                    "run_id",
                    "parent_run_id",
                    "processed_columns",
                    "blocks",
                    "globalZ",
                    "fixed_support_preserved",
                    "actual_objective",
                    "cost_acceptance",
                )
            }
        ),
        flush=True,
    )
    return 0


def main(argv=None):
    global _EXPECTED_FAILURE_RUN_ID
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-json", type=Path)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--stage",
        choices=("pilot", "baseline", "all", "restricted-confirmation"),
        default="all",
    )
    parser.add_argument("--parent-run", type=Path)
    parser.add_argument("--candidate-json", type=Path)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--workers", type=int, choices=(1, 2, 3))
    parser.add_argument(
        "--pilot-chunks", help="Optional subset of original pilot IDs, e.g. 0"
    )
    args = parser.parse_args(argv)
    if args.stage == "restricted-confirmation":
        if (
            args.case_json is not None
            or args.parent_run is None
            or args.candidate_json is None
        ):
            parser.error(
                "restricted-confirmation requires --parent-run and --candidate-json, and does not take --case-json"
            )
        if args.pilot_chunks is not None:
            parser.error("restricted-confirmation does not accept --pilot-chunks")
        return run_restricted_confirmation(args)
    if args.preflight_only:
        parser.error("--preflight-only is only valid for restricted-confirmation")
    if args.workers is None:
        args.workers = 1
    if args.case_json is None:
        parser.error("--case-json is required for pilot, baseline, and all stages")
    if args.parent_run is not None or args.candidate_json is not None:
        parser.error(
            "--parent-run/--candidate-json are only valid for restricted-confirmation"
        )
    request = json.loads(args.case_json.read_text())
    validate_request(request)
    from harness.prepare_native_satellite_case import load_case_config
    from harness.run_native_candidate_observation import (
        _runtime_environment,
        EXPERIMENT,
    )
    from oracle.kdm6.obs.rttov_runner import _child_env
    import torch

    torch.set_num_threads(1)
    with _runtime_environment(EXPERIMENT):
        rt_environment = {
            name: value
            for name, value in _child_env().items()
            if name.startswith(
                (
                    "OMP_",
                    "MKL_",
                    "OPENBLAS_",
                    "VECLIB_",
                    "DYLD_",
                    "LD_",
                    "GFORTRAN_",
                    "RTTOV_",
                    "AD_RTTOV_",
                    "KDM6_",
                )
            )
        }
    config = load_case_config(request.get("paths"))
    config["rttov_timeout_seconds"] = float(request.get("rttov_timeout_seconds", 900.0))
    if request.get("rttov_replay_manifest"):
        recovery_path = Path(request["rttov_replay_manifest"]).resolve()
        config["rttov_replay_manifest"] = str(recovery_path)
        config["rttov_replay_sha256"] = sha(recovery_path)
    root = args.output_root.absolute()
    if root.is_symlink() or any(parent.is_symlink() for parent in root.parents):
        raise ValueError("run output must not traverse symlinks")
    if root.resolve() == REPO.resolve() or REPO.resolve() in root.resolve().parents:
        raise ValueError("run artifacts must be outside the public source checkout")
    if root.exists() and not args.resume:
        raise FileExistsError("run root already exists; use explicit --resume")
    for value in config["paths"].values():
        source = Path(value).resolve()
        if (
            root.resolve() == source
            or root.resolve() in source.parents
            or source in root.resolve().parents
        ):
            raise ValueError("run output overlaps a pinned input")
    root.mkdir(parents=True, exist_ok=True)
    pins = source_pins(config)
    for name in pins:
        source = Path(name).resolve()
        if root.resolve() == source or root.resolve() in source.parents:
            raise ValueError("run output overlaps a pinned source/recovery artifact")
    check_pins(pins)
    run_contract = {
        "request": request,
        "source_pins": pins,
        "base_commit": "792e890ea2be5cd4ce874dceca2a45f2c1bba1f8",
        "model_snapshot_time": "2025-07-19_00:00:40",
        "KO_nominal_slot": "202507190000",
        "local_physics_dt_seconds": 20,
        "host_timestep_or_cycle": False,
        "raw_host_number_units_certified": False,
        "optical_number_coordinate": "raw output divided by the identical live post-finish dry density supplied to the cloud bridge",
        "model_quality_contract": "strict zero baseline; preserve frozen support for trials",
        "pixel_UTC_verified": False,
        "runtime": {
            "python": sys.version,
            "python_executable": sys.executable,
            "torch": torch.__version__,
            "numpy": np.__version__,
            "machine": platform.machine(),
            "platform": platform.platform(),
            "RT_environment_sha256": identity(rt_environment),
            "RT_environment_names": sorted(rt_environment),
            "torch_threads": torch.get_num_threads(),
        },
        "case_preparation": config,
    }
    run_id = identity(run_contract)
    _EXPECTED_FAILURE_RUN_ID = run_id
    run_contract["run_id"] = run_id
    write_stage(root / "CASE_MANIFEST.json", run_contract)
    config["run_id"] = run_id
    ordered = list(PILOTS)
    pilot_name = "PILOT.json"
    if args.pilot_chunks is not None:
        if args.stage != "pilot":
            raise ValueError("an explicit pilot subset is only valid in pilot stage")
        ordered = [int(value) for value in args.pilot_chunks.split(",")]
        if (
            not ordered
            or len(set(ordered)) != len(ordered)
            or any(index not in PILOTS for index in ordered)
        ):
            raise ValueError("pilot subset must use distinct original pilot IDs")
        pilot_name = "PILOT_" + "_".join(map(str, sorted(ordered))) + ".json"
    if args.stage != "pilot":
        ordered += [i for i in range(129) if i not in PILOTS]
    publish_json(
        root / "executions" / (uuid.uuid4().hex + ".json"),
        {
            "workers": args.workers,
            "threads_per_worker": 1,
            "stage": args.stage,
            "run_id": run_id,
            "chunks": ordered,
            "command": sys.argv,
            "started_at_UTC": datetime.now(timezone.utc).isoformat(),
        },
    )
    with _runtime_environment(EXPERIMENT):
        receipts = run_baseline(config, root, run_id, ordered, workers=args.workers)
        summary = baseline_summary(receipts, full_domain=args.stage != "pilot")
        write_stage(
            root / (pilot_name if args.stage == "pilot" else "BASELINE.json"), summary
        )
        if args.stage == "pilot":
            check_pins(pins)
            return 0
        if not summary["dot"]["passed"]:
            raise RuntimeError(
                "global JVP/VJP dot check failed; trials are not authorized by the case contract"
            )
        if args.stage == "baseline":
            check_pins(pins)
            return 0
        fd = run_fd(
            config, root, run_id, summary, request.get("fd_epsilons", [1e-3, 3e-4])
        )
        if not fd["passed"]:
            raise RuntimeError(
                "independent directional differences failed; case remains incomplete"
            )
        accepted, trials, reason = run_trials(
            config, root, run_id, summary, workers=args.workers
        )
    check_pins(pins)
    final = {
        "status": "COMPLETED_ACCEPTED"
        if accepted
        else "COMPLETED_NO_ACCEPTABLE_UPDATE",
        "accepted_trial": accepted,
        "trials": trials,
        "reason": reason,
        "processed_columns": summary["processed_columns"],
        "blocks": len(receipts),
        "gradient_verification": {
            "dot": summary["dot"],
            "sparse_FD_passed": fd["passed"],
        },
        "completed_at_UTC": datetime.now(timezone.utc).isoformat(),
        "native_host_steps": 0,
        "native_cycles": 0,
    }
    # A decision is not yet a completed case: the required assembled artifacts
    # and maps must also succeed before publishing the completion marker.
    decision_path = root / "RUN_DECISION.json"
    if decision_path.exists():
        previous = json.loads(decision_path.read_text())
        old_fields = {k: v for k, v in previous.items() if k != "completed_at_UTC"}
        new_fields = {k: v for k, v in final.items() if k != "completed_at_UTC"}
        if old_fields != new_fields:
            raise ValueError("saved run decision differs from recomputed decision")
        final = previous
    else:
        publish_json(decision_path, final)
    from harness.summarize_native_satellite_case import summarize

    summary_receipt_path = root / "SUMMARY_RECEIPT.json"
    if summary_receipt_path.exists():
        summary_receipt = json.loads(summary_receipt_path.read_text())
        if summary_receipt.get("decision_identity") != identity(final):
            raise ValueError("assembled outputs belong to a different decision")
        folder = Path(summary_receipt["directory"])
        if folder.parent.resolve() != root.resolve():
            raise ValueError("assembled outputs escape their owned run directory")
        for name, digest in summary_receipt["files_sha256"].items():
            path = folder / name
            if path.parent.resolve() != folder.resolve() or sha(path) != digest:
                raise ValueError("completed assembled output changed")
    else:
        folder = root / "summary"
        if folder.exists():
            # Preserve a failed partial summary and retry in a new directory.
            folder = root / ("summary_attempt_" + uuid.uuid4().hex)
        summarize(root, folder)
        summary_receipt = {
            "decision_identity": identity(final),
            "directory": str(folder),
            "files_sha256": {
                path.name: sha(path)
                for path in sorted(folder.iterdir())
                if path.is_file()
            },
        }
        publish_json(summary_receipt_path, summary_receipt)
    check_pins(pins)
    write_stage(root / "FINAL.json", final)
    print(json.dumps(final), flush=True)
    return 0


def _owns_failure_output(arguments, case):
    """Preflight is read-only; restricted failures may only enter their own run."""
    if "--preflight-only" in arguments:
        return False
    if not _EXPECTED_FAILURE_RUN_ID or case.get("run_id") != _EXPECTED_FAILURE_RUN_ID:
        return False

    def option(name):
        try:
            return arguments[arguments.index(name) + 1]
        except (ValueError, IndexError):
            return None

    if option("--stage") != "restricted-confirmation":
        return True  # Keep the existing legacy-stage failure contract.
    try:
        return (
            case.get("experiment_type") == "restricted_block_confirmation_v1"
            and case.get("candidate_json_sha256") == sha(Path(option("--candidate-json")))
            and case.get("parent_case_manifest_sha256")
            == sha(Path(option("--parent-run")) / "CASE_MANIFEST.json")
        )
    except (OSError, TypeError, ValueError):
        return False


def guarded_main(argv=None):
    """Preserve failures and their owned partial work without a completion flag."""
    global _EXPECTED_FAILURE_RUN_ID
    _EXPECTED_FAILURE_RUN_ID = None
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        return main(arguments)
    except BaseException as exc:
        if "--output-root" in arguments:
            position = arguments.index("--output-root") + 1
            if position < len(arguments):
                root = Path(arguments[position]).absolute()
                manifest = root / "CASE_MANIFEST.json"
                if manifest.is_file() and not root.is_symlink():
                    try:
                        case = json.loads(manifest.read_text())
                        run_id = case["run_id"]
                        if _owns_failure_output(arguments, case):
                            publish_json(
                                root / "failures" / (uuid.uuid4().hex + ".json"),
                                {
                                    "status": "INCOMPLETE",
                                    "run_id": run_id,
                                    "exception": repr(exc),
                                    "traceback": traceback.format_exc(),
                                    "command": arguments,
                                    "at_UTC": datetime.now(timezone.utc).isoformat(),
                                },
                            )
                    except (OSError, ValueError, KeyError):
                        pass  # Preserve the original execution exception.
        raise


if __name__ == "__main__":
    raise SystemExit(guarded_main())
