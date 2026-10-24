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
    config, block, workspace, *, record, baseline=None, delta=None, z=None
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
    theta_np, qv_np = block["theta_m"].copy(), block["qv"].copy()
    if delta is not None:
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-json", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--stage", choices=("pilot", "baseline", "all"), default="all")
    parser.add_argument("--workers", type=int, choices=(1, 2, 3), default=1)
    parser.add_argument(
        "--pilot-chunks", help="Optional subset of original pilot IDs, e.g. 0"
    )
    args = parser.parse_args(argv)
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


def guarded_main(argv=None):
    """Preserve failures and their owned partial work without a completion flag."""
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
                        run_id = json.loads(manifest.read_text())["run_id"]
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
