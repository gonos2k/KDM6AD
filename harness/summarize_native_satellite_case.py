"""Validate and summarize a completed native-grid satellite objective run.

The reader joins only receipt-pinned chunk artifacts and requires exact
coverage of ``0..nx*ny-1``. It computes diagnostics on the frozen baseline
mask and never fetches external observations or model data.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
from pathlib import Path

import numpy as np

from harness.native_satellite_objective import objective_chunk


CHANNELS = (10, 11, 12, 13, 14, 15, 16)
CHANNEL_NAMES = ("wv073", "ir087", "ir096", "ir105", "ir112", "ir123", "ir133")
BASELINE_KEYS = (
    "flat_index",
    "obs_bt",
    "bt",
    "quality",
    "mask",
    "weights",
    "source_eligible",
    "profile_valid",
    "reasons",
    "theta_m",
    "qv",
    "grad_theta_numerator",
    "grad_qv_numerator",
    "active",
    "direction_theta",
    "direction_qv",
    "bt_jvp",
    "finish",
)
TRIAL_KEYS = ("delta_theta", "delta_qv", "z")


def _json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read valid JSON: {path}") from exc


def _inside(root, value, label):
    path = Path(value)
    resolved = (path if path.is_absolute() else root / path).resolve()
    if resolved == root or root not in resolved.parents:
        raise ValueError(f"{label} escapes the run root")
    return resolved


def _verify_receipt(root, entry):
    if "receipt" in entry:
        receipt_path = _inside(root, entry["receipt"], "receipt")
        receipt = _json(receipt_path)
    else:
        # The runner embeds the exact receipt object in its stage JSON.
        receipt = entry
        if not isinstance(receipt.get("binding"), str) or not receipt["binding"]:
            raise ValueError("inline chunk receipt lacks a run binding")
    for key in ("chunk_index", "start", "stop"):
        if key in receipt and receipt[key] != entry.get(key):
            raise ValueError(f"chunk receipt {key} differs from manifest")
    return receipt


def _read_chunk(root, entry, *, trial=False):
    receipt = _verify_receipt(root, entry)
    sha_key = "sha256" if "sha256" in entry else "artifact_sha256"
    if "artifact" not in entry or sha_key not in entry:
        raise ValueError("chunk entry lacks artifact path or SHA-256")
    artifact = _inside(root, entry["artifact"], "artifact")
    if not artifact.is_file():
        raise ValueError(f"chunk artifact is missing: {entry['artifact']}")
    artifact_bytes = artifact.read_bytes()
    actual_sha = hashlib.sha256(artifact_bytes).hexdigest()
    if actual_sha != entry[sha_key]:
        raise ValueError(f"chunk artifact changed while reading: {entry['artifact']}")
    with np.load(io.BytesIO(artifact_bytes), allow_pickle=False) as archive:
        required = (
            set(BASELINE_KEYS)
            if not trial
            else {
                "flat_index",
                "obs_bt",
                "bt",
                "quality",
                "mask",
                "weights",
                "source_eligible",
                "profile_valid",
                "reasons",
                "theta_m",
                "qv",
                "active",
                "finish",
                *TRIAL_KEYS,
            }
        )
        missing = sorted(required - set(archive.files))
        if missing:
            raise ValueError(f"chunk artifact lacks required arrays: {missing}")
        arrays = {name: archive[name].copy() for name in required}
    return arrays, receipt


def _as_mask(value, shape, name):
    array = np.asarray(value)
    if array.shape != shape:
        raise ValueError(f"{name} must have shape {shape}")
    if array.dtype == np.bool_:
        return array
    if (
        array.dtype.kind not in "fiu"
        or not np.isfinite(array).all()
        or not np.isin(array, (0, 1)).all()
    ):
        raise ValueError(f"{name} must contain only boolean/0/1 values")
    return array.astype(np.bool_)


def _validate_chunk_arrays(arrays, entry, *, trial=False):
    start, stop = entry.get("start"), entry.get("stop")
    if type(start) is not int or type(stop) is not int or start < 0 or stop <= start:
        raise ValueError("chunk start/stop must define a nonempty integer interval")
    flat = arrays["flat_index"]
    if (
        flat.ndim != 1
        or flat.dtype.kind not in "iu"
        or not np.array_equal(flat, np.arange(start, stop, dtype=flat.dtype))
    ):
        raise ValueError("chunk flat_index does not match its declared [start, stop)")
    b = stop - start
    if (
        arrays["obs_bt"].shape != (b, len(CHANNELS))
        or arrays["obs_bt"].dtype != np.float64
    ):
        raise ValueError("obs_bt must be binary64 with shape (chunk, 7)")
    for name in ("bt", "quality", "mask", "weights"):
        if arrays[name].shape != (b, len(CHANNELS)):
            raise ValueError(f"{name} must have shape (chunk, 7)")
    if arrays["bt"].dtype != np.float64 or arrays["weights"].dtype != np.float64:
        raise TypeError("bt and weights must be binary64")
    if arrays["quality"].dtype.kind not in "iu":
        raise TypeError("quality must be an integer status array")
    mask = _as_mask(arrays["mask"], (b, len(CHANNELS)), "mask")
    source_eligible = _as_mask(
        arrays["source_eligible"], (b, len(CHANNELS)), "source_eligible"
    )
    profile_valid = _as_mask(arrays["profile_valid"], (b,), "profile_valid")
    if not trial and np.any(source_eligible & ~profile_valid[:, None]):
        raise ValueError("source_eligible includes an invalid native profile")
    weights = arrays["weights"]
    if not np.isfinite(weights).all() or np.any(weights < 0.0):
        raise ValueError("weights must be finite and nonnegative")
    if np.any(weights[~mask] != 0.0) or np.any(weights[mask] <= 0.0):
        raise ValueError("weights must be positive on mask and zero off mask")
    if not trial and np.any(mask & (arrays["quality"] != 0)):
        raise ValueError("mask includes a baseline model-quality failure")
    if not trial and not np.array_equal(
        mask, source_eligible & (arrays["quality"] == 0)
    ):
        raise ValueError(
            "baseline mask differs from source eligibility and zero model quality"
        )
    reasons = arrays["reasons"]
    if reasons.shape != (b,) or reasons.dtype.kind not in "US":
        raise ValueError("reasons must be a non-object string vector per profile")
    state_names = ("theta_m", "qv")
    baseline_only = (
        "grad_theta_numerator",
        "grad_qv_numerator",
        "direction_theta",
        "direction_qv",
        "bt_jvp",
    )
    for name in state_names + (() if trial else baseline_only):
        if (
            arrays[name].ndim != 2
            or arrays[name].shape[0] != b
            or arrays[name].dtype != np.float64
        ):
            raise ValueError(f"{name} must be binary64 with shape (chunk, levels)")
        if not np.isfinite(arrays[name]).all():
            raise ValueError(f"{name} must be finite")
    levels = arrays["theta_m"].shape[1]
    if any(
        arrays[name].shape != (b, levels)
        for name in state_names + (() if trial else baseline_only[:4])
    ):
        raise ValueError(
            "native state, gradients and directions must share (chunk, levels)"
        )
    active = arrays["active"]
    if active.shape != (2, b, levels):
        raise ValueError("active must have shape (2, chunk, levels)")
    active = _as_mask(active, (2, b, levels), "active")
    admitted = mask.any(axis=1)
    expected_active_t = np.broadcast_to(admitted[:, None], (b, levels))
    expected_active_qv = expected_active_t & (arrays["qv"] > 0.0)
    if not trial:
        if not np.array_equal(active[0], expected_active_t):
            raise ValueError(
                "T controls must be active at every level of admitted columns"
            )
        if not np.array_equal(active[1], expected_active_qv):
            raise ValueError(
                "QV controls must be active only where admitted baseline QV is positive"
            )
        if (
            arrays["bt_jvp"].shape != (b, len(CHANNELS))
            or arrays["bt_jvp"].dtype != np.float64
        ):
            raise ValueError("bt_jvp must be binary64 with shape (chunk, 7)")
    if arrays["finish"].shape != (5, b, levels) or arrays["finish"].dtype != np.float64:
        raise ValueError("finish must be binary64 with shape (5, chunk, levels)")
    if not np.isfinite(arrays["finish"]).all():
        raise ValueError("finish must be finite")
    if not trial and not np.isfinite(arrays["bt_jvp"]).all():
        raise ValueError("bt_jvp must be finite")
    if not trial:
        for name in ("obs_bt", "bt"):
            if not np.isfinite(arrays[name][mask]).all():
                raise ValueError(f"{name} must be finite on frozen support")
    if trial:
        for name in ("delta_theta", "delta_qv"):
            if (
                arrays[name].shape != (b, levels)
                or arrays[name].dtype != np.float64
                or not np.isfinite(arrays[name]).all()
            ):
                raise ValueError(
                    f"{name} must be finite binary64 with shape (chunk, levels)"
                )
        if (
            arrays["z"].shape != (2, b, levels)
            or arrays["z"].dtype != np.float64
            or not np.isfinite(arrays["z"]).all()
        ):
            raise ValueError("z must be finite binary64 with shape (2, chunk, levels)")
        if np.any(arrays["z"][~active] != 0.0):
            raise ValueError("trial z is nonzero in frozen control degrees")
        if not np.array_equal(arrays["mask"], mask):
            raise ValueError("trial must preserve the frozen baseline mask")
    return mask


def _artifact_sha(entry):
    return entry.get("sha256", entry.get("artifact_sha256"))


def _verify_inline_binding(entry, *, run_id, stage, baseline_sha, controls_sha):
    if "receipt" in entry:
        return
    payload = {
        "run_id": run_id,
        "stage": stage,
        "chunk": entry["chunk_index"],
        "baseline_sha": baseline_sha,
        "controls_sha": controls_sha,
    }
    expected = hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, allow_nan=False, separators=(",", ":")
        ).encode()
    ).hexdigest()
    if entry.get("binding") != expected:
        raise ValueError(
            "chunk receipt binding differs from run/stage/baseline/control identity"
        )


def _join_manifest(
    root,
    manifest,
    *,
    nx,
    ny,
    trial=False,
    stage=None,
    run_id=None,
    baseline_sha_by_chunk=None,
):
    entries = manifest.get("chunks")
    if not isinstance(entries, list) or not entries:
        raise ValueError("manifest chunks must be a nonempty list")
    expected_total = nx * ny
    seen_chunk_indices = set()
    seen_flat = []
    pieces = []
    intervals = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("each chunk manifest entry must be an object")
        ci = entry.get("chunk_index")
        if type(ci) is not int or ci < 0 or ci in seen_chunk_indices:
            raise ValueError("chunk_index must be a unique nonnegative integer")
        seen_chunk_indices.add(ci)
        if "receipt" not in entry:
            if not run_id or not stage:
                raise ValueError(
                    "inline chunk receipts require CASE_MANIFEST run_id and stage"
                )
            baseline_sha = None if not trial else baseline_sha_by_chunk.get(ci)
            if trial and baseline_sha is None:
                raise ValueError("trial receipt has no matching baseline chunk SHA")
            controls_sha = None if not trial else manifest.get("controls_sha256")
            _verify_inline_binding(
                entry,
                run_id=run_id,
                stage=stage,
                baseline_sha=baseline_sha,
                controls_sha=controls_sha,
            )
        arrays, _receipt = _read_chunk(root, entry, trial=trial)
        if "receipt" not in entry:
            artifact = _inside(root, entry["artifact"], "artifact")
            expected_chunk_dir = root / stage / f"chunk_{ci:05d}"
            if artifact.parent.parent != expected_chunk_dir.resolve():
                raise ValueError(
                    "inline chunk artifact is outside its bound stage/chunk directory"
                )
        mask = _validate_chunk_arrays(arrays, entry, trial=trial)
        expected_z = math.fsum(float(x) for x in arrays["weights"].ravel())
        if "Z_partial" in _receipt:
            saved_partial = float(_receipt["Z_partial"])
            if not math.isfinite(saved_partial) or abs(
                saved_partial - expected_z
            ) > 1e-12 * max(1.0, abs(expected_z)):
                raise ValueError("chunk receipt Z_partial differs from frozen weights")
        if "observation_numerator" in _receipt:
            saved_numerator = _receipt["observation_numerator"]
            if saved_numerator is not None:
                local_support = {"m0": mask, "weights": arrays["weights"]}
                try:
                    reconstructed = objective_chunk(
                        arrays["bt"], arrays["obs_bt"], local_support
                    )["numerator"]
                except ValueError:
                    raise ValueError(
                        "chunk receipt has a numerator for invalid support BT"
                    )
                saved_numerator = float(saved_numerator)
                if not math.isfinite(saved_numerator) or abs(
                    saved_numerator - reconstructed
                ) > 1e-12 * max(1.0, abs(reconstructed)):
                    raise ValueError(
                        "chunk receipt observation numerator differs from artifact"
                    )
        if trial and "support_preserved" in _receipt:
            local_lost = mask & (arrays["quality"] != 0)
            local_nonfinite = mask & ~np.isfinite(arrays["bt"])
            actual_preserved = not local_lost.any() and not local_nonfinite.any()
            if bool(_receipt["support_preserved"]) != actual_preserved:
                raise ValueError(
                    "chunk receipt support status differs from quality/BT artifact"
                )
        start, stop = entry["start"], entry["stop"]
        if stop > expected_total:
            raise ValueError("chunk range exceeds expected native grid")
        intervals.append((start, stop, ci))
        seen_flat.append(arrays["flat_index"])
        arrays["mask"] = mask
        pieces.append((start, ci, arrays))
    intervals.sort()
    cursor = 0
    for start, stop, _ci in intervals:
        if start != cursor:
            raise ValueError("chunk ranges contain a gap or overlap")
        cursor = stop
    if cursor != expected_total:
        raise ValueError(
            f"chunk ranges cover {cursor} profiles; expected {expected_total}"
        )
    flat = np.concatenate(seen_flat)
    if flat.size != expected_total or not np.array_equal(
        np.sort(flat), np.arange(expected_total)
    ):
        raise ValueError(
            "flat_index contains missing or duplicate native grid positions"
        )
    pieces.sort(key=lambda item: item[0])
    names = set(pieces[0][2])
    if any(set(arrays) != names for _, _, arrays in pieces):
        raise ValueError("chunk artifact key sets differ")
    excluded = {"active", "finish"} | (set(TRIAL_KEYS) if trial else set())
    joined = {
        name: np.concatenate([arrays[name] for _, _, arrays in pieces], axis=0)
        for name in names
        if name not in excluded
    }
    # These fields place the profile dimension on axis 1 or axis 0, respectively.
    joined["active"] = np.concatenate(
        [arrays["active"] for _, _, arrays in pieces], axis=1
    )
    joined["finish"] = np.concatenate(
        [arrays["finish"] for _, _, arrays in pieces], axis=1
    )
    if trial:
        # Preserve baseline and extra trial keys with the same profile-first layout.
        for name in TRIAL_KEYS:
            if name == "z":
                joined[name] = np.concatenate(
                    [arrays[name] for _, _, arrays in pieces], axis=1
                )
            else:
                joined[name] = np.concatenate(
                    [arrays[name] for _, _, arrays in pieces], axis=0
                )
    order = np.argsort(joined["flat_index"])
    for name, value in list(joined.items()):
        axis = 1 if name in ("active", "finish", "z") else 0
        joined[name] = np.take(value, order, axis=axis)
    return joined


def _weighted_quantile(values, weights, quantile):
    order = np.argsort(values, kind="mergesort")
    v, w = values[order], weights[order]
    total = math.fsum(float(x) for x in w)
    cutoff = quantile * total
    index = int(np.searchsorted(np.cumsum(w), cutoff, side="left"))
    return float(v[min(index, len(v) - 1)])


def _channel_metrics(observed, predicted, mask, weights):
    result = []
    for channel in range(len(CHANNELS)):
        keep = mask[:, channel]
        w = weights[keep, channel]
        obs = observed[keep, channel]
        pred = predicted[keep, channel]
        total = math.fsum(float(x) for x in w)
        if not keep.any() or total <= 0.0:
            result.append(
                {
                    "channel": CHANNELS[channel],
                    "name": CHANNEL_NAMES[channel],
                    "matched_count": 0,
                    "weight_sum": 0.0,
                    "observed_mean": None,
                    "model_mean": None,
                    "bias": None,
                    "mae": None,
                    "rmse": None,
                    "abs_residual_median": None,
                    "abs_residual_p95": None,
                    "huber_mean": None,
                }
            )
            continue
        residual = pred - obs
        abs_residual = np.abs(residual)
        huber = np.where(abs_residual <= 1.0, 0.5 * residual**2, abs_residual - 0.5)
        result.append(
            {
                "channel": CHANNELS[channel],
                "name": CHANNEL_NAMES[channel],
                "matched_count": int(keep.sum()),
                "weight_sum": total,
                "observed_mean": math.fsum(float(a * b) for a, b in zip(obs, w))
                / total,
                "model_mean": math.fsum(float(a * b) for a, b in zip(pred, w)) / total,
                "bias": math.fsum(float(a * b) for a, b in zip(residual, w)) / total,
                "mae": math.fsum(float(a * b) for a, b in zip(abs_residual, w)) / total,
                "rmse": math.sqrt(
                    math.fsum(float(a * a * b) for a, b in zip(residual, w)) / total
                ),
                "abs_residual_median": _weighted_quantile(abs_residual, w, 0.5),
                "abs_residual_p95": _weighted_quantile(abs_residual, w, 0.95),
                "huber_mean": math.fsum(float(a * b) for a, b in zip(huber, w)) / total,
            }
        )
    return result


def _check_report_objective(manifest, predicted, observed, support, normalizer, z=None):
    obj = manifest.get("objective")
    if not isinstance(obj, dict):
        raise ValueError("run manifest lacks objective mapping")
    part = objective_chunk(predicted, observed, support)
    denominator = float(normalizer)
    if not math.isfinite(denominator) or denominator <= 0.0:
        raise ValueError("objective normalizer must be positive and finite")
    obs_value = part["numerator"] / denominator
    background = 0.0
    if z is not None:
        background = 0.5 * math.fsum(float(x * x) for x in z.ravel()) / denominator
    expected = {
        "J_observation": obs_value,
        "J_background": background,
        "J_total": obs_value + background,
    }
    if "J_observation" in obj:
        checks = expected
        required = ("J_observation", "J_background", "J_total")
    else:
        checks = {
            "observation_numerator": part["numerator"],
            "regularization_numerator": background * denominator,
            "numerator": (obs_value + background) * denominator,
            "Z": denominator,
            "cost": obs_value + background,
        }
        required = tuple(checks)
    missing = sorted(set(required) - set(obj))
    if missing:
        raise ValueError(f"manifest objective lacks fields: {missing}")
    for name, value in checks.items():
        if name in obj:
            saved = float(obj[name])
            if not math.isfinite(saved) or abs(saved - value) > 1.0e-12 * max(
                1.0, abs(value)
            ):
                raise ValueError(
                    f"manifest {name} differs from reconstructed objective"
                )
    return expected


def _plot_maps(output, arrays, nx, ny):
    import matplotlib.pyplot as plt

    obs = arrays["obs_bt"]
    base, final = arrays["baseline_bt"], arrays["final_bt"]
    mask = arrays["mask"]
    for channel, channel_id in enumerate(CHANNELS):
        fields = [
            ("Observed", obs[:, channel]),
            ("Baseline model", base[:, channel]),
            ("Final model", final[:, channel]),
            ("Baseline residual", base[:, channel] - obs[:, channel]),
            ("Final residual", final[:, channel] - obs[:, channel]),
            ("Final − baseline", final[:, channel] - base[:, channel]),
        ]
        fig, axes = plt.subplots(2, 3, figsize=(15, 8), constrained_layout=True)
        for ax, (title, field) in zip(axes.flat, fields):
            grid = field.reshape(ny, nx).copy()
            grid[~mask[:, channel].reshape(ny, nx)] = np.nan
            finite = grid[np.isfinite(grid)]
            if (
                "residual" in title.lower()
                or "baseline" in title.lower()
                and "model" not in title.lower()
                or "final −" in title
            ):
                limit = float(np.max(np.abs(finite))) if finite.size else 1.0
                limit = max(limit, 1e-12)
                image = ax.imshow(
                    grid, origin="lower", cmap="coolwarm", vmin=-limit, vmax=limit
                )
            else:
                image = ax.imshow(grid, origin="lower", cmap="viridis")
            ax.set_title(title)
            ax.set_xlabel("native i (0-based)")
            ax.set_ylabel("native j (0-based)")
            fig.colorbar(image, ax=ax, shrink=0.8)
        fig.suptitle(f"AMI channel {channel_id} ({CHANNEL_NAMES[channel]})")
        fig.savefig(output / f"channel_{channel_id:02d}.png", dpi=150)
        plt.close(fig)

    dtheta = arrays["delta_theta"]
    dqv = arrays["delta_qv"]
    tnorm = np.linalg.norm(dtheta, axis=1).reshape(ny, nx)
    qnorm = np.linalg.norm(dqv, axis=1).reshape(ny, nx)
    reasons, counts = np.unique(arrays["reasons"], return_counts=True)
    fig, axes = plt.subplots(1, 3, figsize=(16, 5), constrained_layout=True)
    for ax, data, title in (
        (axes[0], tnorm, "T control increment L2"),
        (axes[1], qnorm, "QV control increment L2"),
    ):
        image = ax.imshow(data, origin="lower", cmap="magma")
        ax.set_title(title)
        ax.set_xlabel("native i (0-based)")
        ax.set_ylabel("native j (0-based)")
        fig.colorbar(image, ax=ax, shrink=0.8)
    axes[2].bar(np.arange(len(reasons)), counts)
    axes[2].set_xticks(np.arange(len(reasons)), reasons, rotation=70, ha="right")
    axes[2].set_title("Baseline exclusion / status reasons")
    axes[2].set_ylabel("profile count")
    fig.savefig(output / "control_updates_and_reasons.png", dpi=150)
    plt.close(fig)


def summarize(run_root, output_dir, *, nx=234, ny=282, make_plots=True):
    """Validate full-grid baseline/final chunks and create summary artifacts."""
    root = Path(run_root).resolve(strict=True)
    out_original = Path(output_dir).absolute()
    if out_original.exists() or out_original.is_symlink():
        raise ValueError("summary output directory must be new and not a symlink")
    out = out_original.resolve()
    if out == root or out in root.parents:
        raise ValueError("summary output must be a new directory at or below run root")
    if type(nx) is not int or type(ny) is not int or nx <= 0 or ny <= 0:
        raise ValueError("nx and ny must be positive integers")
    baseline_manifest = _json(root / "BASELINE.json")
    decision_path = root / "RUN_DECISION.json"
    final_manifest = _json(
        decision_path if decision_path.is_file() else root / "FINAL.json"
    )
    status = final_manifest.get("status", final_manifest.get("desired_status"))
    if status == "INCOMPLETE":
        raise ValueError("cannot summarize an incomplete native satellite run")
    if status not in ("COMPLETED_ACCEPTED", "COMPLETED_NO_ACCEPTABLE_UPDATE"):
        raise ValueError(f"unknown final run status {status!r}")
    try:
        saved_z = float(baseline_manifest["globalZ"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("baseline globalZ must be a numeric positive value") from exc
    if not math.isfinite(saved_z) or saved_z <= 0.0:
        raise ValueError("baseline globalZ must be finite and positive")
    case_path = root / "CASE_MANIFEST.json"
    case_manifest = _json(case_path) if case_path.is_file() else None
    inline_receipts = any(
        "receipt" not in entry for entry in baseline_manifest.get("chunks", [])
    )
    if inline_receipts and not case_manifest:
        raise ValueError("inline runner receipts require CASE_MANIFEST.json")
    run_id = None if case_manifest is None else case_manifest.get("run_id")
    if inline_receipts and (not isinstance(run_id, str) or not run_id):
        raise ValueError(
            "CASE_MANIFEST.json lacks run_id for inline receipt validation"
        )
    baseline_sha_by_chunk = {
        entry.get("chunk_index"): _artifact_sha(entry)
        for entry in baseline_manifest.get("chunks", [])
    }
    baseline = _join_manifest(
        root, baseline_manifest, nx=nx, ny=ny, stage="baseline", run_id=run_id
    )

    accepted_ref = final_manifest.get("accepted_trial")
    if status == "COMPLETED_ACCEPTED" and not accepted_ref:
        raise ValueError("accepted final status requires accepted_trial")
    if status == "COMPLETED_NO_ACCEPTABLE_UPDATE" and accepted_ref is not None:
        raise ValueError("no-acceptable-update status must not name an accepted trial")
    trial_manifests = {}
    declared_trials = final_manifest.get("trials", [])
    if declared_trials and not isinstance(declared_trials, list):
        raise ValueError("final trial list must be a list of manifest names")
    trial_names = set(str(name) for name in declared_trials)
    trial_names.update(path.name for path in root.glob("TRIAL_alpha_*.json"))
    for name in sorted(trial_names):
        trial_path = _inside(root, name, "trial manifest")
        if not trial_path.is_file():
            if name in declared_trials:
                raise ValueError(f"declared trial manifest is missing: {name}")
            continue
        trial_manifests[trial_path.name] = _json(trial_path)
    accepted_name = None
    if accepted_ref is not None:
        accepted_path = _inside(root, accepted_ref, "accepted_trial")
        if accepted_path.suffix != ".json" or not accepted_path.is_file():
            raise ValueError("accepted_trial must name a saved trial JSON manifest")
        accepted_name = accepted_path.name
        if accepted_name not in trial_manifests:
            trial_manifests[accepted_name] = _json(accepted_path)

    baseline_quality = baseline["quality"]
    baseline_mask = baseline["mask"]
    baseline_weights = baseline["weights"]
    baseline_observed = baseline["obs_bt"]
    baseline_bt = baseline["bt"]
    computed_z = math.fsum(float(value) for value in baseline_weights.ravel())
    if not math.isfinite(saved_z) or abs(saved_z - computed_z) > 1e-12 * max(
        1.0, abs(saved_z)
    ):
        raise ValueError("baseline globalZ differs from summed frozen weights")
    baseline_support = {"m0": baseline_mask, "weights": baseline_weights}
    baseline_objective = _check_report_objective(
        baseline_manifest, baseline_bt, baseline_observed, baseline_support, saved_z
    )
    dot = baseline_manifest.get("dot")
    if not isinstance(dot, dict) or not all(
        key in dot for key in ("lhs", "rhs", "relative_error")
    ):
        raise ValueError("baseline manifest lacks its global JVP/VJP dot result")
    dot_lhs, dot_rhs, dot_error = (
        float(dot[key]) for key in ("lhs", "rhs", "relative_error")
    )
    if not all(math.isfinite(value) for value in (dot_lhs, dot_rhs, dot_error)):
        raise ValueError("baseline dot result must be finite")
    recomputed_dot_error = abs(dot_lhs - dot_rhs) / max(
        abs(dot_lhs), abs(dot_rhs), 1e-12
    )
    if abs(recomputed_dot_error - dot_error) > 1e-12 * max(1.0, abs(dot_error)):
        raise ValueError("baseline dot relative error differs from lhs/rhs")
    if dot.get("passed") is False:
        raise ValueError("baseline global JVP/VJP dot gate did not pass")

    trial_outputs = {}
    trial_summaries = {}
    for name, manifest in trial_manifests.items():
        trial_z = float(manifest.get("globalZ", saved_z))
        if not math.isfinite(trial_z) or trial_z != saved_z:
            raise ValueError(f"{name} changes the frozen baseline globalZ")
        stage_name = name.removesuffix(".json")
        trial = _join_manifest(
            root,
            manifest,
            nx=nx,
            ny=ny,
            trial=True,
            stage=stage_name,
            run_id=run_id,
            baseline_sha_by_chunk=baseline_sha_by_chunk,
        )
        if not np.array_equal(trial["flat_index"], baseline["flat_index"]):
            raise ValueError(f"{name} grid indices differ from baseline")
        if not np.array_equal(trial["mask"], baseline_mask):
            raise ValueError(f"{name} does not preserve frozen baseline mask")
        if not np.array_equal(trial["weights"], baseline_weights):
            raise ValueError(f"{name} does not preserve frozen baseline weights")
        if not np.array_equal(trial["source_eligible"], baseline["source_eligible"]):
            raise ValueError(f"{name} changes pre-RT source eligibility")
        if not np.array_equal(trial["obs_bt"], baseline_observed, equal_nan=True):
            raise ValueError(f"{name} observations differ from baseline")
        if not np.array_equal(trial["active"], baseline["active"]):
            raise ValueError(f"{name} changes the frozen baseline active-control mask")
        # New quality-zero channels remain outside m0. A candidate that loses
        # baseline support is summarized as rejected; it is never used as final.
        newly_quality_zero_outside_m0 = 0
        support_preserved = True
        support_errors = []
        for entry in manifest["chunks"]:
            arrays, _ = _read_chunk(root, entry, trial=True)
            _validate_chunk_arrays(arrays, entry, trial=True)
            s = slice(entry["start"], entry["stop"])
            lost = baseline_mask[s] & (arrays["quality"] != 0)
            nonfinite = baseline_mask[s] & ~np.isfinite(arrays["bt"])
            lost_profile = baseline_mask[s].any(axis=1) & ~arrays["profile_valid"]
            if lost.any():
                support_preserved = False
                support_errors.append(f"lost_quality:{int(lost.sum())}")
            if nonfinite.any():
                support_preserved = False
                support_errors.append(f"nonfinite_bt:{int(nonfinite.sum())}")
            if lost_profile.any():
                support_preserved = False
                support_errors.append(f"profile_invalid:{int(lost_profile.sum())}")
            newly_quality_zero_outside_m0 += int(
                ((arrays["quality"] == 0) & ~baseline_mask[s]).sum()
            )
            support_errors.extend(
                str(entry[key]) for key in ("support_error",) if entry.get(key)
            )
        objective_valid = bool(manifest.get("objective_valid", support_preserved))
        objective = manifest.get("objective")
        if objective_valid and not support_preserved:
            raise ValueError(
                f"{name} claims a valid objective after losing baseline support"
            )
        if name == accepted_name and not objective_valid:
            raise ValueError("accepted trial is marked objective-invalid")
        result_objective = None
        if objective_valid:
            trial_support = {"m0": baseline_mask, "weights": baseline_weights}
            result_objective = _check_report_objective(
                manifest,
                trial["bt"],
                baseline_observed,
                trial_support,
                saved_z,
                trial["z"],
            )
        elif objective is not None:
            raise ValueError(
                f"{name} carries an objective despite objective_valid=false"
            )
        trial_outputs[name] = trial
        trial_summaries[name] = {
            "status": manifest.get("status", "UNSPECIFIED"),
            "objective_valid": objective_valid,
            "support_preserved": support_preserved,
            "support_errors": support_errors,
            "profile_valid_count": int(trial["profile_valid"].sum()),
            "objective_recomputed": result_objective,
            "quality_zero_outside_m0_ignored": int(newly_quality_zero_outside_m0),
            "coverage_profiles": int(trial["flat_index"].size),
        }
    if accepted_name is not None and accepted_name not in trial_outputs:
        raise ValueError("accepted trial has no complete artifacts")

    if accepted_name is None:
        final_bt = baseline_bt.copy()
        final_quality = baseline_quality.copy()
        delta_theta = np.zeros_like(baseline["theta_m"])
        delta_qv = np.zeros_like(baseline["qv"])
        final_objective = baseline_objective
        final_profile_valid = baseline["profile_valid"]
    else:
        final_trial = trial_outputs[accepted_name]
        final_bt = final_trial["bt"]
        final_quality = final_trial["quality"]
        delta_theta = final_trial["delta_theta"]
        delta_qv = final_trial["delta_qv"]
        final_objective = trial_summaries[accepted_name]["objective_recomputed"]
        final_profile_valid = final_trial["profile_valid"]

    baseline_metrics = _channel_metrics(
        baseline_observed, baseline_bt, baseline_mask, baseline_weights
    )
    final_metrics = _channel_metrics(
        baseline_observed, final_bt, baseline_mask, baseline_weights
    )
    metrics = []
    for first, last in zip(baseline_metrics, final_metrics):
        metrics.append(
            {
                "channel": first["channel"],
                "name": first["name"],
                "matched_count": first["matched_count"],
                "weight_sum": first["weight_sum"],
                "observed_mean": first["observed_mean"],
                "baseline": {
                    k: v
                    for k, v in first.items()
                    if k
                    not in (
                        "channel",
                        "name",
                        "matched_count",
                        "weight_sum",
                        "observed_mean",
                    )
                },
                "final": {
                    k: v
                    for k, v in last.items()
                    if k
                    not in (
                        "channel",
                        "name",
                        "matched_count",
                        "weight_sum",
                        "observed_mean",
                    )
                },
            }
        )

    active = baseline["active"].astype(np.bool_)
    grad_t = baseline["grad_theta_numerator"] / saved_z
    grad_q = baseline["grad_qv_numerator"] / saved_z
    gradient_summary = {}
    for name, grad, act in (("theta_m", grad_t, active[0]), ("qv", grad_q, active[1])):
        values = grad[act]
        gradient_summary[name] = {
            "active_count": int(act.sum()),
            "l2_norm": float(np.linalg.norm(values)),
            "max_abs": float(np.max(np.abs(values))) if values.size else 0.0,
            "min": float(np.min(values)) if values.size else None,
            "max": float(np.max(values)) if values.size else None,
            "per_level_active_min": [
                float(np.min(grad[act[:, k], k])) if act[:, k].any() else None
                for k in range(grad.shape[1])
            ],
            "per_level_active_max": [
                float(np.max(grad[act[:, k], k])) if act[:, k].any() else None
                for k in range(grad.shape[1])
            ],
        }
    theta_norm = np.linalg.norm(delta_theta, axis=1)
    qv_norm = np.linalg.norm(delta_qv, axis=1)
    reason_values, reason_counts = np.unique(baseline["reasons"], return_counts=True)
    reasons = {
        str(value): int(count) for value, count in zip(reason_values, reason_counts)
    }

    summary = {
        "schema": "kdm6.native_satellite_case_summary.v1",
        "status": status,
        "accepted_trial": accepted_name,
        "grid": {
            "nx": nx,
            "ny": ny,
            "profiles": nx * ny,
            "flat_index_order": "j-major, i-fastest; flat=(j-1)*nx+(i-1)",
        },
        "globalZ": saved_z,
        "baseline_objective": baseline_objective,
        "final_objective": final_objective,
        "trials": trial_summaries,
        "per_channel": metrics,
        "gradient": {
            "normalization": "reported gradients are dJ/dnative-state after one global division by Z",
            "fields": gradient_summary,
        },
        "control_increment": {
            "theta_m_l2_min": float(np.min(theta_norm)),
            "theta_m_l2_max": float(np.max(theta_norm)),
            "qv_l2_min": float(np.min(qv_norm)),
            "qv_l2_max": float(np.max(qv_norm)),
            "theta_m_level_max_abs": np.max(np.abs(delta_theta), axis=0).tolist(),
            "qv_level_max_abs": np.max(np.abs(delta_qv), axis=0).tolist(),
        },
        "baseline_exclusion_reasons": reasons,
        "source_coverage": {
            "profile_valid_count": int(baseline["profile_valid"].sum()),
            "final_profile_valid_count": int(final_profile_valid.sum()),
            "source_eligible_observations": int(baseline["source_eligible"].sum()),
            "baseline_model_quality_supported": int(baseline_mask.sum()),
            "source_eligible_per_channel": baseline["source_eligible"]
            .sum(axis=0)
            .tolist(),
            "baseline_supported_per_channel": baseline_mask.sum(axis=0).tolist(),
        },
        "limits": [
            "Metrics use the frozen baseline observation mask and owner weights.",
            "Newly quality-valid trial entries are ignored and do not enter the objective.",
            "This summarizes saved run artifacts; it does not run KDM, RTTOV, host dynamics, or assimilation.",
        ],
    }
    summary["dot"] = {
        **dot,
        "recomputed_relative_error": recomputed_dot_error,
    }

    output_arrays = {
        "flat_index": baseline["flat_index"],
        "native_i_1based": baseline["flat_index"] % nx + 1,
        "native_j_1based": baseline["flat_index"] // nx + 1,
        "obs_bt": baseline_observed,
        "baseline_bt": baseline_bt,
        "final_bt": final_bt,
        "baseline_quality": baseline_quality,
        "final_quality": final_quality,
        "mask": baseline_mask,
        "weights": baseline_weights,
        "source_eligible": baseline["source_eligible"],
        "profile_valid": baseline["profile_valid"],
        "final_profile_valid": final_profile_valid,
        "reasons": baseline["reasons"],
        "theta_m": baseline["theta_m"],
        "qv": baseline["qv"],
        "grad_theta_numerator": baseline["grad_theta_numerator"],
        "grad_qv_numerator": baseline["grad_qv_numerator"],
        "grad_theta_cost": grad_t,
        "grad_qv_cost": grad_q,
        "active": active,
        "direction_theta": baseline["direction_theta"],
        "direction_qv": baseline["direction_qv"],
        "bt_jvp": baseline["bt_jvp"],
        "finish": baseline["finish"],
        "delta_theta": delta_theta,
        "delta_qv": delta_qv,
    }
    # All inputs and artifacts are validated before reserving the output path.
    out.mkdir(parents=True, exist_ok=False)
    np.savez_compressed(out / "assembled.npz", **output_arrays)
    if make_plots:
        _plot_maps(out, output_arrays, nx, ny)
    summary["artifacts"] = {
        "assembled_npz": "assembled.npz",
        "channel_plots": [f"channel_{c:02d}.png" for c in CHANNELS]
        if make_plots
        else [],
        "control_plot": "control_updates_and_reasons.png" if make_plots else None,
    }
    with (out / "summary.json").open("x") as stream:
        json.dump(summary, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return summary
