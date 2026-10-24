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
NATIVE_GRID_NX, NATIVE_GRID_NY, NATIVE_LEVELS = 234, 282, 39
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


def _plot_maps(output, arrays, nx, ny, *, comparison_name="Final",
               control_name="Input"):
    import matplotlib.pyplot as plt

    obs = arrays["obs_bt"]
    base, final = arrays["baseline_bt"], arrays["final_bt"]
    mask = arrays["mask"]
    for channel, channel_id in enumerate(CHANNELS):
        selected = mask[:, channel]
        if not selected.any():
            fig, ax = plt.subplots(figsize=(8, 5))
            ax.text(0.5, 0.5, "No fixed-support observations in this channel",
                    ha="center", va="center", transform=ax.transAxes)
            ax.set_title(f"AMI channel {channel_id} ({CHANNEL_NAMES[channel]})")
            fig.savefig(output / f"channel_{channel_id:02d}.png", dpi=150)
            plt.close(fig)
            continue
        bt_values = np.concatenate([field[selected, channel] for field in (obs, base, final)])
        bt_min, bt_max = float(bt_values.min()), float(bt_values.max())
        residual_limit = max(float(np.max(np.abs(field[selected, channel] - obs[selected, channel])))
                             for field in (base, final))
        fields = [
            ("Observed", obs[:, channel]),
            ("Baseline model", base[:, channel]),
            (f"{comparison_name} model", final[:, channel]),
            ("Baseline residual", base[:, channel] - obs[:, channel]),
            (f"{comparison_name} residual", final[:, channel] - obs[:, channel]),
            (f"{comparison_name} − baseline", final[:, channel] - base[:, channel]),
        ]
        fig, axes = plt.subplots(2, 3, figsize=(15, 8), constrained_layout=True)
        for ax, (title, field) in zip(axes.flat, fields):
            grid = field.reshape(ny, nx).copy()
            grid[~mask[:, channel].reshape(ny, nx)] = np.nan
            finite = grid[np.isfinite(grid)]
            difference = title == f"{comparison_name} − baseline"
            residual = "residual" in title.lower()
            limit = float(np.max(np.abs(finite))) if difference and finite.size else residual_limit
            if (difference or residual) and limit == 0.0:
                ax.imshow(grid, origin="lower", cmap="Greys", vmin=0, vmax=1)
                ax.text(0.5, 0.5, "exactly 0 K on fixed support", transform=ax.transAxes,
                        ha="center", va="center")
                image = None
            elif difference or residual:
                image = ax.imshow(
                    grid, origin="lower", cmap="coolwarm", vmin=-limit, vmax=limit
                )
            else:
                image = ax.imshow(grid, origin="lower", cmap="viridis",
                                  vmin=bt_min, vmax=bt_max)
            ax.set_title(title)
            ax.set_xlabel("native i (0-based)")
            ax.set_ylabel("native j (0-based)")
            if image is not None:
                fig.colorbar(image, ax=ax, shrink=0.8, label="K")
        fig.suptitle(f"AMI channel {channel_id} ({CHANNEL_NAMES[channel]}) on frozen baseline support\n"
                     "White means profile/RTTOV exclusion, not missing KO source data")
        fig.savefig(output / f"channel_{channel_id:02d}.png", dpi=150)
        plt.close(fig)

    dtheta = arrays["delta_theta"]
    dqv = arrays["delta_qv"]
    tnorm = np.linalg.norm(dtheta, axis=1).reshape(ny, nx)
    qnorm = np.linalg.norm(dqv, axis=1).reshape(ny, nx)
    reasons, counts = np.unique(arrays["reasons"], return_counts=True)
    fig, axes = plt.subplots(1, 3, figsize=(16, 5), constrained_layout=True)
    for ax, data, title in (
        (axes[0], tnorm, f"{control_name} moist-theta increment L2 over 39 levels (K)"),
        (axes[1], qnorm, f"{control_name} QV increment L2 over 39 levels (kg/kg dry)"),
    ):
        maximum = float(np.max(data))
        image = ax.imshow(data, origin="lower", cmap="magma", vmin=0, vmax=maximum) if maximum else None
        if image is None:
            ax.text(0.5, 0.5, "0 everywhere",
                    transform=ax.transAxes, ha="center", va="center")
            ax.set_xlim(-0.5, nx - 0.5)
            ax.set_ylim(-0.5, ny - 0.5)
        frozen = arrays.get("frozen_control_rows")
        if frozen is not None:
            ax.contour(frozen.reshape(ny, nx), levels=[0.5], colors="cyan", linewidths=0.35)
        ax.set_title(title)
        ax.set_xlabel("native i (0-based)")
        ax.set_ylabel("native j (0-based)")
        if image is not None:
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


def _same_f64_bits(left, right):
    a = np.asarray(left)
    b = np.asarray(right)
    if a.dtype != np.float64 or b.dtype != np.float64:
        return False
    a = np.ascontiguousarray(a)
    b = np.ascontiguousarray(b)
    return a.shape == b.shape and a.tobytes() == b.tobytes()


def _finish_rate_formula(before, clean, config):
    """Independent NumPy replay in native_finish's ordered f64 expressions."""
    before, clean = np.asarray(before), np.asarray(clean)
    if (before.dtype != np.float64 or clean.dtype != np.float64
            or before.shape != clean.shape or before.ndim != 3 or before.shape[0] != 12):
        raise ValueError("before/clean must be matching float64 (12,B,L) states")
    if not np.isfinite(before).all() or not np.isfinite(clean).all():
        raise ValueError("finish inputs must be finite")
    dt = float(config["dt"])
    alpha = float(config["alpha"])
    bound = float(config["mp_tend_lim"]) * dt
    if not all(math.isfinite(x) for x in (dt, alpha, bound)) or dt <= 0 or alpha <= 0 or bound < 0:
        raise ValueError("invalid finish configuration")
    raw_delta_th = clean[0] - before[0]
    m = np.where(raw_delta_th >= bound, bound,
                 np.where(raw_delta_th <= -bound, -bound, raw_delta_th))
    delta_qv = clean[1] - before[1]
    delta_qc = clean[2] - before[2]
    _a = 1.0 + alpha * before[1]
    b = 1.0 + alpha * clean[1]
    mb = m * b
    cross = (alpha * delta_qv) * clean[0]
    n = mb + cross
    return np.stack((n / dt, delta_qv / dt, delta_qc / dt))


def _read_capture_arrays(root, entry, names):
    """Read extra saved arrays after the existing receipt/artifact hash checks."""
    receipt = _verify_receipt(root, entry)
    artifact = _inside(root, entry["artifact"], "artifact")
    payload = artifact.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != _artifact_sha(entry) or digest != receipt.get("artifact_sha256"):
        raise ValueError("captured physics arrays do not match their receipt SHA")
    with np.load(io.BytesIO(payload), allow_pickle=False) as archive:
        missing = sorted(set(names) - set(archive.files))
        if missing:
            raise ValueError(f"confirmation chunk lacks applied capture arrays: {missing}")
        arrays = {name: archive[name].copy() for name in names}
    return arrays, receipt


def _source_pin_record(manifest, suffix):
    pins = manifest.get("source_pins", {})
    matches = [(Path(path).as_posix(), digest) for path, digest in pins.items()
               if Path(path).as_posix().endswith(suffix)]
    authoritative = [entry for entry in matches if "/source_v3/" in entry[0]]
    if len(authoritative) == 1:
        selected = authoritative[0]
    elif not authoritative and len(matches) == 1:
        selected = matches[0]
    elif not authoritative and matches and len({digest for _, digest in matches}) == 1:
        selected = sorted(matches)[0]
    else:
        raise ValueError(f"manifest does not identify one content-authoritative pin for {suffix}")
    return {"path": selected[0], "sha256": selected[1],
            "content_identical_aliases": sorted(path for path, digest in matches if digest == selected[1])}


def _load_restricted_confirmation(parent_root, confirmation_root):
    """Read the parent run plus a restricted run containing CONFIRMATION.json only."""
    parent_case = _json(parent_root / "CASE_MANIFEST.json")
    parent_manifest = _json(parent_root / "BASELINE.json")
    parent_final = _json(parent_root / "FINAL.json")
    candidate_case = _json(confirmation_root / "CASE_MANIFEST.json")
    confirmation = _json(confirmation_root / "CONFIRMATION.json")
    if parent_final.get("status") not in ("COMPLETED_ACCEPTED", "COMPLETED_NO_ACCEPTABLE_UPDATE"):
        raise ValueError("parent run is not a completed full-domain run")
    if parent_manifest.get("full_domain") is not True:
        raise ValueError("parent baseline manifest is not full-domain")
    parent_id, candidate_id = parent_case.get("run_id"), candidate_case.get("run_id")
    if confirmation.get("parent_run_id") != parent_id or confirmation.get("run_id") != candidate_id:
        raise ValueError("confirmation does not bind the saved parent and candidate run IDs")
    control_sha = candidate_case.get("candidate_control_z_sha256")
    if not isinstance(control_sha, str) or not control_sha or confirmation.get("controls_sha256") != control_sha:
        raise ValueError("confirmation control hash differs from CASE_MANIFEST candidate control")
    if confirmation.get("status") not in ("RESTRICTED_UPDATE_ACCEPTED", "RESTRICTED_UPDATE_NOT_ACCEPTED"):
        raise ValueError("confirmation status does not certify a reproduced candidate")
    if not isinstance(confirmation.get("stage"), str) or not confirmation["stage"]:
        raise ValueError("confirmation must name its stage")
    if confirmation.get("fixed_support_preserved") is not True:
        raise ValueError("confirmation does not preserve frozen baseline support")
    if not isinstance(confirmation.get("actual_objective"), dict):
        raise ValueError("confirmation lacks its actual fixed-support objective")
    if float(confirmation.get("globalZ", math.nan)) != float(parent_manifest["globalZ"]):
        raise ValueError("confirmation changes the frozen baseline normalizer")
    chunks = confirmation.get("chunks")
    parent_hashes = {int(e["chunk_index"]): _artifact_sha(e) for e in parent_manifest["chunks"]}
    if (sorted(parent_hashes) != list(range(129)) or not isinstance(chunks, list)
            or len(chunks) != 129 or sorted(e.get("chunk_index") for e in chunks) != list(range(129))):
        raise ValueError("parent and confirmation must bind the same 129 original chunks")
    return parent_case, parent_manifest, parent_final, candidate_case, confirmation, parent_hashes


def _packet_state_by_flat(case_config, chunk_index, expected_flat):
    packet_root = Path(case_config["paths"]["packets"])
    packet_manifest_path = packet_root / "manifest.json"
    packet_manifest_bytes = packet_manifest_path.read_bytes()
    if hashlib.sha256(packet_manifest_bytes).hexdigest() != case_config["packet_manifest_sha256"]:
        raise ValueError("source packet manifest SHA differs from CASE_MANIFEST")
    packet_manifest = json.loads(packet_manifest_bytes)
    entry = packet_manifest["chunks"][chunk_index]
    packet = _inside(packet_root, entry["path"], "source packet")
    digest = hashlib.sha256(packet.read_bytes()).hexdigest()
    if digest != entry["sha256"]:
        raise ValueError("source packet SHA differs from its packet manifest")
    with np.load(packet, allow_pickle=False) as archive:
        state = np.asarray(archive["state"])
        forcing = np.asarray(archive["forcing"])
        flat = np.asarray(archive["flat_indices"])
    levels = int(case_config["grid"]["levels"])
    if (state.dtype != np.float64 or state.shape != (12, len(flat), levels)
            or forcing.dtype != np.float64 or forcing.shape != (4, len(flat), levels)
            or not np.array_equal(flat, expected_flat)):
        raise ValueError("source packet state/flat-index metadata differs from result block")
    return state.copy(), forcing.copy()


def _packet_qc_by_flat(case_config, chunk_index, expected_flat):
    state, _ = _packet_state_by_flat(case_config, chunk_index, expected_flat)
    return state[2].copy(), state[1].copy()


def _weighted_water_summary(before, raw, clean, forcing):
    """Sum per-column DEN*DELZ-integrated changes, without horizontal area weights."""
    water_names = ("QV", "QC", "QR", "QI", "QS", "QG")
    if forcing.shape != (4, before.shape[1], before.shape[2]):
        raise ValueError("applied_forcing must have shape (4,B,L)")
    weights = forcing[0] * forcing[3]
    results = {}
    for name, delta in (
        ("raw_minus_input", raw[1:7] - before[1:7]),
        ("cleanup_minus_raw", clean[1:7] - raw[1:7]),
        ("applied_minus_input", clean[1:7] - before[1:7]),
    ):
        product = delta * weights[None, :, :]
        per_column = np.asarray([
            [math.fsum(map(float, product[s, b])) for b in range(product.shape[1])]
            for s in range(6)
        ])
        results[name] = {
            species: math.fsum(map(float, per_column[row]))
            for row, species in enumerate(water_names)
        }
    return {"weight":"actual applied_forcing[DEN] * applied_forcing[DELZ]",
            "aggregation":"unweighted sum of per-column kg/m2 diagnostics; not regional mass",
            "changes_kg_m2_unweighted_over_columns":results}


def _new_water_column_accumulator(nprofiles):
    species = ("QV", "QC", "QR", "QI", "QS", "QG")
    return {key: np.full((len(species), nprofiles), np.nan, dtype=np.float64) for key in (
        "raw_minus_input_kg_m2", "cleanup_minus_raw_kg_m2", "applied_minus_input_kg_m2"
    )}


def _append_water_column_changes(accumulator, before, raw, clean, forcing, flat_index):
    """Place full-B column integrals at native indices using actual DEN*DELZ."""
    species = ("QV", "QC", "QR", "QI", "QS", "QG")
    weight = forcing[0] * forcing[3]
    flat_index = np.asarray(flat_index)
    if (flat_index.ndim != 1 or flat_index.size != before.shape[1]
            or flat_index.dtype.kind not in "iu" or np.any(flat_index < 0)
            or np.any(flat_index >= accumulator[next(iter(accumulator))].shape[1])
            or np.unique(flat_index).size != flat_index.size):
        raise ValueError("flat_index does not match water accumulator columns")
    for key, delta in (
        ("raw_minus_input_kg_m2", raw[1:7] - before[1:7]),
        ("cleanup_minus_raw_kg_m2", clean[1:7] - raw[1:7]),
        ("applied_minus_input_kg_m2", clean[1:7] - before[1:7]),
    ):
        product = delta * weight[None, :, :]
        for row, name in enumerate(species):
            accumulator[key][row, flat_index] = [
                math.fsum(map(float, product[row, b])) for b in range(product.shape[1])
            ]


def _append_saved_water_columns(accumulator, key, values, flat_index):
    values = np.asarray(values)
    flat_index = np.asarray(flat_index)
    if (values.dtype != np.float64 or values.shape != (6, flat_index.size)
            or flat_index.ndim != 1 or np.any(flat_index < 0)
            or np.any(flat_index >= accumulator[key].shape[1])):
        raise ValueError(f"saved applied water array {key} has invalid shape/indices")
    accumulator[key][:, flat_index] = values


def _sum_water_column_arrays(values):
    if any(not np.isfinite(matrix).all() for matrix in values.values()):
        raise ValueError("per-column applied water export contains unfilled or nonfinite values")
    return {
        key: {species: math.fsum(map(float, matrix[row]))
              for row, species in enumerate(("QV", "QC", "QR", "QI", "QS", "QG"))}
        for key, matrix in values.items()
    }


def _sum_water_columns(values):
    species = ("QV", "QC", "QR", "QI", "QS", "QG")
    result = {}
    for key, matrix in values.items():
        if not np.isfinite(matrix).all():
            raise ValueError(f"per-column water field {key} has unfilled indices")
        result[key] = {name: math.fsum(map(float, matrix[row]))
                       for row, name in enumerate(species)}
    return result


def export_restricted_tendencies(parent_root, confirmation_root, out_dir):
    """Export saved baseline/candidate H/QV/QC rates and applied-state receipts.

    Reads existing receipts only. It does not call KDM or RTTOV. The parent
    rate fields come from its saved ``finish`` arrays; candidate rates come
    from the confirmation's same-forward ``finish`` and captured applied
    state/forcing/raw/clean arrays.
    """
    parent_root = Path(parent_root).resolve(strict=True)
    confirmation_root = Path(confirmation_root).resolve(strict=True)
    out_original = Path(out_dir).absolute()
    if out_original.exists() or out_original.is_symlink():
        raise ValueError("tendency export directory must be new and not a symlink")
    out = out_original.resolve()
    if (out == parent_root or parent_root in out.parents or out == confirmation_root
            or confirmation_root in out.parents or out in parent_root.parents
            or out in confirmation_root.parents):
        raise ValueError("tendency export directory must not overlap an input run")
    nx, ny = NATIVE_GRID_NX, NATIVE_GRID_NY
    nprofiles = nx * ny
    (parent_case, parent_manifest, parent_final, candidate_case,
     confirmation, parent_sha_by_chunk) = _load_restricted_confirmation(parent_root, confirmation_root)
    parent_id = parent_case.get("run_id")
    candidate_id = candidate_case.get("run_id")
    parent = _join_manifest(parent_root, parent_manifest, nx=nx, ny=ny,
                            stage="baseline", run_id=parent_id)
    stage = confirmation.get("stage")
    candidate = _join_manifest(confirmation_root, confirmation, nx=nx, ny=ny,
                               trial=True, stage=stage, run_id=candidate_id,
                               baseline_sha_by_chunk=parent_sha_by_chunk)
    if not np.array_equal(parent["flat_index"], candidate["flat_index"]):
        raise ValueError("parent and confirmation flat-index grids differ")
    for name in ("mask", "weights", "source_eligible", "obs_bt"):
        if not np.array_equal(parent[name], candidate[name], equal_nan=True):
            raise ValueError(f"confirmation changed frozen {name}")
    if (parent["finish"].shape != (5, nprofiles, NATIVE_LEVELS)
            or candidate["finish"].shape != (5, nprofiles, NATIVE_LEVELS)):
        raise ValueError("parent/confirmation finish arrays must cover the native grid")
    confirmation_status = confirmation.get("status")
    if confirmation_status not in ("RESTRICTED_UPDATE_ACCEPTED", "RESTRICTED_UPDATE_NOT_ACCEPTED"):
        raise ValueError(f"confirmation status does not certify a reproduced candidate: {confirmation_status!r}")
    recomputed_candidate_objective = _check_report_objective(
        {"objective": confirmation["actual_objective"]}, candidate["bt"], parent["obs_bt"],
        {"m0": parent["mask"], "weights": parent["weights"]},
        float(parent_manifest["globalZ"]), candidate["z"])
    parent_config = parent_case["case_preparation"]
    candidate_config = candidate_case["case_preparation"]
    cfg = parent_config["finish_configuration"]
    if (cfg != candidate_config["finish_configuration"]
            or parent_config["prep_configuration"] != candidate_config["prep_configuration"]
            or parent_config["zero_out_configuration"] != candidate_config["zero_out_configuration"]
            or parent_config["experiment"] != candidate_config["experiment"]
            or parent_config["grid"] != candidate_config["grid"]
            or parent_config["packet_manifest_sha256"] != candidate_config["packet_manifest_sha256"]):
        raise ValueError("parent and confirmation physics, geometry, or packet configuration differs")
    parent_library = Path(parent_config["paths"]["candidate_library"]).resolve()
    candidate_library = Path(candidate_config["paths"]["candidate_library"]).resolve()
    parent_library_sha = hashlib.sha256(parent_library.read_bytes()).hexdigest()
    candidate_library_sha = hashlib.sha256(candidate_library.read_bytes()).hexdigest()
    if (parent_library != candidate_library or parent_library_sha != candidate_library_sha
            or parent_case.get("source_pins", {}).get(str(parent_library)) != parent_library_sha
            or candidate_case.get("source_pins", {}).get(str(candidate_library)) != candidate_library_sha):
        raise ValueError("parent and confirmation candidate library differ")
    checked_physics_sources = ("harness/native_batch_microphysics.py",
                               "oracle/kdm6/native_finish.py", "oracle/kdm6/native_prep.py")
    source_pin_checks = {}
    for suffix in checked_physics_sources:
        parent_pin = _source_pin_record(parent_case, suffix)
        candidate_pin = _source_pin_record(candidate_case, suffix)
        source_pin_checks[suffix] = {
            "parent": parent_pin, "confirmation": candidate_pin,
            "sha256_matches": parent_pin["sha256"] == candidate_pin["sha256"],
        }
    if not all(value["sha256_matches"] for value in source_pin_checks.values()):
        raise ValueError(f"parent and confirmation physics source pins differ: {source_pin_checks}")
    dt = float(cfg["dt"])
    if dt != 20.0:
        raise ValueError("restricted tendency export expects the fixed 20-second map")
    baseline_rates = np.ascontiguousarray(parent["finish"][1:4])
    candidate_rates = np.ascontiguousarray(candidate["finish"][1:4])
    baseline_qv_error_count = baseline_qc_error_count = 0
    baseline_qv_elements = baseline_qc_elements = 0
    baseline_qv_max_abs = baseline_qc_max_abs = 0.0
    candidate_rate_match = np.ones(3, dtype=np.bool_)
    candidate_rate_max_abs = np.zeros(3, dtype=np.float64)
    candidate_rate_elements = np.zeros(3, dtype=np.int64)
    capture_receipts = []
    water_columns = _new_water_column_accumulator(nprofiles)
    baseline_water_columns = _new_water_column_accumulator(nprofiles)
    baseline_weights = np.full((nprofiles, NATIVE_LEVELS), np.nan, dtype=np.float64)
    candidate_weights = np.full_like(baseline_weights, np.nan)
    finish_theta_before = np.full((nprofiles, NATIVE_LEVELS), np.nan, dtype=np.float64)
    finish_theta_clean = np.full_like(finish_theta_before, np.nan)
    initial_qc_export = np.full_like(finish_theta_before, np.nan)
    baseline_phase = {int(e["chunk_index"]): e for e in parent_manifest["chunks"]}
    candidate_phase = {int(e["chunk_index"]): e for e in confirmation["chunks"]}
    if sorted(baseline_phase) != list(range(129)) or sorted(candidate_phase) != list(range(129)):
        raise ValueError("parent/confirmation must contain exactly 129 full-B chunks")
    cloud_names = ("cloud_qc", "cloud_qr", "cloud_qi", "cloud_qs", "cloud_qg",
                   "cloud_nn", "cloud_nc", "cloud_ni", "cloud_nr", "cloud_bg")
    capture_names = ("applied_before", "applied_forcing", "applied_raw",
                     "applied_clean_replay", "applied_clean_matches_output",
                     "native_after_qv", *cloud_names)
    applied_audit_root = parent_root / "APPLIED_PHYSICS_AUDIT"
    applied_ledger_path = applied_audit_root / "ledger.json"
    applied_ledger = _json(applied_ledger_path)
    if not applied_ledger["phases"][0]["all_replay_bit_gates_passed"]:
        raise ValueError("parent applied-physics replay bit gates did not pass")
    if applied_ledger.get("run_id") != parent_id:
        raise ValueError("parent applied audit belongs to a different run_id")
    audit_phase = applied_ledger["phases"][0]
    parent_baseline_sha = hashlib.sha256((parent_root / "BASELINE.json").read_bytes()).hexdigest()
    if audit_phase.get("manifest_sha256") != parent_baseline_sha:
        raise ValueError("parent applied audit is not bound to this BASELINE.json")
    audit_by_chunk = {int(e["chunk_index"]): e for e in audit_phase["chunks"]}
    if sorted(audit_by_chunk) != list(range(129)):
        raise ValueError("parent applied audit does not bind all 129 chunks")
    packet_root = Path(parent_config["paths"]["packets"])
    packet_manifest_path = packet_root / "manifest.json"
    packet_manifest_sha = hashlib.sha256(packet_manifest_path.read_bytes()).hexdigest()
    if packet_manifest_sha != parent_config["packet_manifest_sha256"]:
        raise ValueError("parent packet manifest SHA differs from CASE_MANIFEST")
    packet_manifest = _json(packet_manifest_path)
    baseline_h_max = []
    for ci in range(129):
        be, ce = baseline_phase[ci], candidate_phase[ci]
        # Baseline QV/QC relation uses saved baseline state/output plus original block QC.
        b_arrays, _ = _read_chunk(parent_root, be, trial=False)
        audit_entry = audit_by_chunk[ci]
        parent_receipt_path = parent_root / "baseline" / f"chunk_{ci:05d}" / "receipt.json"
        parent_receipt_sha = hashlib.sha256(parent_receipt_path.read_bytes()).hexdigest()
        parent_receipt = _json(parent_receipt_path)
        if (audit_entry.get("saved_artifact_sha256") != _artifact_sha(be)
                or audit_entry.get("saved_binding") != be.get("binding")
                or audit_entry.get("saved_receipt_sha256") != parent_receipt_sha
                or audit_entry.get("source_packet_sha256") != packet_manifest["chunks"][ci]["sha256"]
                or parent_receipt.get("binding") != be.get("binding")
                or parent_receipt.get("artifact_sha256") != _artifact_sha(be)
                or Path(parent_receipt.get("artifact", "")).resolve() != Path(be["artifact"]).resolve()):
            raise ValueError(f"parent applied audit chunk {ci} is not bound to baseline receipt and packet")
        audit_npz = _inside(applied_audit_root, audit_entry["replay_npz"], "applied audit NPZ")
        audit_bytes = audit_npz.read_bytes()
        if hashlib.sha256(audit_bytes).hexdigest() != audit_entry["replay_npz_sha256"]:
            raise ValueError(f"parent applied audit NPZ SHA mismatch in chunk {ci}")
        with np.load(io.BytesIO(audit_bytes), allow_pickle=False) as audit_archive:
            audit_keys = ("weights_kg_m2_by_level", "water_raw_minus_input_kg_m2",
                          "water_cleanup_minus_raw_kg_m2", "water_applied_minus_input_kg_m2",
                          "rate_relation_residuals")
            if any(name not in audit_archive.files for name in audit_keys):
                raise ValueError(f"parent applied audit arrays are incomplete in chunk {ci}")
            audit_arrays = {name: np.asarray(audit_archive[name]).copy() for name in audit_keys}
        bflat = b_arrays["flat_index"]
        bcount = int(bflat.size)
        if (audit_arrays["weights_kg_m2_by_level"].shape != (bcount, NATIVE_LEVELS)
                or any(audit_arrays[name].shape != (6, bcount) for name in audit_keys[1:4])
                or audit_arrays["rate_relation_residuals"].shape != (3, bcount, NATIVE_LEVELS)
                or not all(np.isfinite(value).all() for value in audit_arrays.values())):
            raise ValueError(f"parent applied audit array shape/value differs in chunk {ci}")
        baseline_weights[bflat] = audit_arrays["weights_kg_m2_by_level"]
        for key, array_key in zip(
            ("raw_minus_input_kg_m2", "cleanup_minus_raw_kg_m2", "applied_minus_input_kg_m2"),
            audit_keys[1:4],
        ):
            _append_saved_water_columns(baseline_water_columns, key, audit_arrays[array_key], bflat)
        baseline_h_max.append(float(np.max(np.abs(audit_arrays["rate_relation_residuals"][0]))))
        b_extra, _ = _read_capture_arrays(parent_root, be, ("native_after_qv", "cloud_qc"))
        packet_state, _ = _packet_state_by_flat(parent_config, ci, b_arrays["flat_index"])
        initial_qc, packet_qv = packet_state[2], packet_state[1]
        if not _same_f64_bits(packet_qv, b_arrays["qv"]):
            raise ValueError(f"parent baseline QV differs from original packet in chunk {ci}")
        qv_formula = (b_extra["native_after_qv"] - b_arrays["qv"]) / dt
        qc_formula = (b_extra["cloud_qc"] - initial_qc) / dt
        base_finish = b_arrays["finish"]
        baseline_qv_elements += qv_formula.size
        baseline_qc_elements += qc_formula.size
        baseline_qv_max_abs = max(baseline_qv_max_abs, float(np.max(np.abs(qv_formula-base_finish[2]))))
        baseline_qc_max_abs = max(baseline_qc_max_abs, float(np.max(np.abs(qc_formula-base_finish[3]))))
        baseline_qv_error_count += int(np.count_nonzero(np.ascontiguousarray(qv_formula).view(np.uint64)
                                                        != np.ascontiguousarray(base_finish[2]).view(np.uint64)))
        baseline_qc_error_count += int(np.count_nonzero(np.ascontiguousarray(qc_formula).view(np.uint64)
                                                        != np.ascontiguousarray(base_finish[3]).view(np.uint64)))

        c_arrays, _ = _read_chunk(confirmation_root, ce, trial=True)
        cap, receipt = _read_capture_arrays(confirmation_root, ce, capture_names)
        before, forcing = cap["applied_before"], cap["applied_forcing"]
        raw, clean = cap["applied_raw"], cap["applied_clean_replay"]
        bcount = int(c_arrays["flat_index"].size)
        expected_state_shape = (12, bcount, NATIVE_LEVELS)
        if (before.dtype != np.float64 or raw.dtype != np.float64 or clean.dtype != np.float64
                or before.shape != expected_state_shape or raw.shape != expected_state_shape
                or clean.shape != expected_state_shape or forcing.dtype != np.float64
                or forcing.shape != (4, bcount, NATIVE_LEVELS)):
            raise ValueError(f"confirmation applied capture shape/dtype mismatch in chunk {ci}")
        if not all(np.isfinite(x).all() for x in (before, raw, clean, forcing)):
            raise ValueError(f"confirmation applied capture is nonfinite in chunk {ci}")
        if not bool(np.asarray(cap["applied_clean_matches_output"]).item()):
            raise ValueError(f"confirmation cleanup replay flag is false in chunk {ci}")
        actual_cloud = np.stack([cap[name] for name in cloud_names])
        if (not _same_f64_bits(clean[1], cap["native_after_qv"])
                or not _same_f64_bits(clean[2:12], actual_cloud)
                or not _same_f64_bits(raw[8:10], clean[8:10])):
            raise ValueError(f"confirmation cleanup/raw-NC/NI fields differ from saved outputs in chunk {ci}")
        if not np.array_equal(c_arrays["flat_index"], b_arrays["flat_index"]):
            raise ValueError(f"parent/confirmation chunk {ci} flat indices differ")
        if not _same_f64_bits(before[1], c_arrays["qv"]):
            raise ValueError(f"confirmation applied_before QV differs from saved control in chunk {ci}")
        if not _same_f64_bits(before[2], initial_qc):
            raise ValueError(f"confirmation applied_before QC differs from original packet in chunk {ci}")
        if not _same_f64_bits(before[2:12], packet_state[2:12]):
            raise ValueError(f"confirmation changed a non-T/Q KDM state field in chunk {ci}")
        formula = _finish_rate_formula(before, clean, cfg)
        saved_rates = c_arrays["finish"][1:4]
        for ri in range(3):
            candidate_rate_match[ri] &= _same_f64_bits(formula[ri], saved_rates[ri])
            candidate_rate_max_abs[ri] = max(candidate_rate_max_abs[ri],
                                             float(np.max(np.abs(formula[ri]-saved_rates[ri]))))
            candidate_rate_elements[ri] += formula[ri].size
        if not np.all(candidate_rate_match):
            raise ValueError(f"confirmation finish rate differs from ordered independent formula in chunk {ci}")
        capture_receipts.append({"chunk_index":ci,"artifact_sha256":receipt.get("artifact_sha256",_artifact_sha(ce)),
                                 "applied_clean_matches_output":True})
        # Candidate applied-state diagnostic uses its actual DEN*DELZ forcing, product rounded f64 before fsum.
        flat_index = c_arrays["flat_index"]
        candidate_weights[flat_index] = forcing[0] * forcing[3]
        finish_theta_before[flat_index] = before[0]
        finish_theta_clean[flat_index] = clean[0]
        initial_qc_export[flat_index] = initial_qc
        _append_water_column_changes(water_columns,before,raw,clean,forcing,flat_index)

    if baseline_qv_error_count or baseline_qc_error_count:
        raise ValueError("saved baseline QV/QC rates do not match old block qv/rest relation")
    # Baseline H is validated only through the existing applied-audit's recorded relation residuals;
    # no missing baseline raw state is reconstructed here.
    if max(baseline_h_max)!=0.0:
        raise ValueError("baseline applied audit H_RATE record 0 is not exactly zero")
    if not (np.isfinite(finish_theta_before).all() and np.isfinite(finish_theta_clean).all()
            and np.isfinite(initial_qc_export).all()):
        raise ValueError("finish input/candidate theta or packet QC export has incomplete coverage")
    baseline_water_totals = _sum_water_column_arrays(baseline_water_columns)
    candidate_water_totals = _sum_water_column_arrays(water_columns)
    if not np.isfinite(baseline_weights).all() or not np.isfinite(candidate_weights).all():
        raise ValueError("baseline/candidate applied DEN*DELZ arrays have incomplete native coverage")

    rate_names=("H_RATE","QV_RATE","QC_RATE")
    rate_units=("K/s","kg/kg dry air/s","kg/kg dry air/s")
    out.mkdir(parents=True,exist_ok=False)
    flat=parent["flat_index"]
    finish_theta_path=out/"finish_theta_coordinates.npz"
    np.savez_compressed(finish_theta_path,flat_index=flat,before_theta=finish_theta_before,
                        clean_theta=finish_theta_clean)
    initial_qc_path=out/"initial_qc.npz"
    np.savez_compressed(initial_qc_path,flat_index=flat,initial_qc_kgkg=initial_qc_export)
    water_export={"flat_index":flat,"species":np.asarray(("QV","QC","QR","QI","QS","QG")),
                  "baseline_DEN_times_DELZ_kg_m2_by_level":baseline_weights,
                  "candidate_DEN_times_DELZ_kg_m2_by_level":candidate_weights}
    water_delta={}
    for key in baseline_water_columns:
        water_export["baseline_"+key]=baseline_water_columns[key]
        water_export["candidate_"+key]=water_columns[key]
        water_delta[key]=water_columns[key]-baseline_water_columns[key]
        water_export["delta_"+key]=water_delta[key]
    water_path=out/"applied_water_columns.npz"
    np.savez_compressed(water_path,**water_export)
    water_file={"path":str(water_path.resolve()),"sha256":hashlib.sha256(water_path.read_bytes()).hexdigest(),
                "bytes":water_path.stat().st_size,"shape":[nprofiles,NATIVE_LEVELS],
                "delta_shapes":{key:list(value.shape) for key,value in water_delta.items()},
                "weight_shape":list(baseline_weights.shape),"species_order":["QV","QC","QR","QI","QS","QG"]}
    exports={}
    for i,(name,unit) in enumerate(zip(rate_names,rate_units)):
        b=baseline_rates[i]
        c=candidate_rates[i]
        delta=c-b
        path=out/f"{name}_{unit.replace('/','_per_').replace(' ','_')}.npz"
        np.savez_compressed(path,flat_index=flat,baseline=b,candidate=c,delta=delta)
        exports[name]={"path":str(path.resolve()),"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
                       "shape":list(b.shape),"dtype":str(b.dtype),"unit":unit,
                       "field_sha256":{"baseline":hashlib.sha256(np.ascontiguousarray(b).tobytes()).hexdigest(),
                                       "candidate":hashlib.sha256(np.ascontiguousarray(c).tobytes()).hexdigest(),
                                       "delta":hashlib.sha256(np.ascontiguousarray(delta).tobytes()).hexdigest()}}
    rate_audit={
        "baseline":{
            "H_RATE_relation_source":"existing parent APPLIED_PHYSICS_AUDIT rate_relation_residuals row 0; no missing raw state reconstructed",
            "H_RATE_relation_max_abs_residual":max(baseline_h_max),
            "QV_RATE_relation":{"formula":"(saved native_after_qv - parent block QV)/dt",
                                "bitwise_mismatches":baseline_qv_error_count,"elements":baseline_qv_elements,
                                "max_abs_residual":baseline_qv_max_abs},
            "QC_RATE_relation":{"formula":"(saved cloud_qc - parent block state QC)/dt",
                                "bitwise_mismatches":baseline_qc_error_count,"elements":baseline_qc_elements,
                                "max_abs_residual":baseline_qc_max_abs},
        },
        "confirmation":{
            "H_RATE_QV_RATE_QC_RATE_formula_bitwise_match":candidate_rate_match.tolist(),
            "elements_per_rate":candidate_rate_elements.tolist(),
            "max_abs_residual_per_rate":candidate_rate_max_abs.tolist(),
            "applied_clean_output_gates_passed":len(capture_receipts)==129,
            "candidate_formula":"NumPy f64 replay with source operation order: clip, B, N terms, H/QV/QC rates",
        },
    }
    report={"schema":"kdm6.restricted_native_tendency_export.v1",
            "scope":"Saved full-domain parent and confirmation arrays only; no KDM/RTTOV calls.",
            "parent":{"root":str(parent_root),"case_manifest_sha256":hashlib.sha256((parent_root/"CASE_MANIFEST.json").read_bytes()).hexdigest(),
                      "baseline_manifest_sha256":hashlib.sha256((parent_root/"BASELINE.json").read_bytes()).hexdigest(),
                      "applied_audit_ledger_sha256":hashlib.sha256((parent_root/"APPLIED_PHYSICS_AUDIT"/"ledger.json").read_bytes()).hexdigest(),
                      "baseline_qv_relation_bitwise_matches":baseline_qv_error_count==0,
                      "baseline_qc_relation_bitwise_matches":baseline_qc_error_count==0,
                      "baseline_h_relation_source":"parent APPLIED_PHYSICS_AUDIT rate_relation_residuals row 0",
                      "baseline_h_relation_max_abs":max(baseline_h_max)},
            "confirmation":{"root":str(confirmation_root),"status":confirmation_status,
                           "parent_run_id":confirmation["parent_run_id"],"run_id":confirmation["run_id"],
                           "controls_sha256":confirmation["controls_sha256"],
                           "fixed_support_preserved":confirmation["fixed_support_preserved"],
                           "actual_objective":confirmation["actual_objective"],
                           "recomputed_actual_objective":recomputed_candidate_objective,
                           "case_manifest_sha256":hashlib.sha256((confirmation_root/"CASE_MANIFEST.json").read_bytes()).hexdigest(),
                           "confirmation_manifest_sha256":hashlib.sha256((confirmation_root/"CONFIRMATION.json").read_bytes()).hexdigest(),
                           "candidate_library_sha256":candidate_library_sha,
                           "matching_physics_source_pins":source_pin_checks,
                           "finish_formula_matches_saved_bitwise":candidate_rate_match.tolist(),
                           "applied_capture_receipts":capture_receipts},
            "grid":{"nx":nx,"ny":ny,"profiles":nprofiles,"levels":NATIVE_LEVELS,"flat_index_order":"j-major, i-fastest"},
            "finish_crosswalk":{"array_order":["T_NEW_AFTER","H_RATE","QV_RATE","QC_RATE","TH_PHY_M_T0"],
               "H_RATE":{"formula":"N/dt; N=m*(1+alpha*q1)+alpha*(q1-q0)*theta1; m=clip(theta1-theta0, +/- mp_tend_lim*dt)","unit":"K/s","receiver_state":"native_after_thm_pert/T_NEW_AFTER; rate is not reapplied"},
               "QV_RATE":{"formula":"(q1-q0)/dt","unit":"kg/kg dry air/s","receiver_state":"native_after_qv"},
               "QC_RATE":{"formula":"(c1-c0)/dt","unit":"kg/kg dry air/s","receiver_state":"cloud_qc"},
               "dt_seconds":dt,"alpha":cfg["alpha"],"t0_K":cfg["t0"],"mp_tend_lim_K_s":cfg["mp_tend_lim"],
               "TH_coordinate":"absolute dry potential temperature, K",
               "T_NEW_AFTER_coordinate":"moist potential-temperature perturbation relative to t0, K",
               "theta0_q0_c0":"KDM before state rows TH/QV/QC","theta1_q1_c1":"applied_clean_replay rows TH/QV/QC"},
            "exports":exports,
            "finish_inputs":{
                "finish_theta_coordinates":{"path":str(finish_theta_path.resolve()),
                    "sha256":hashlib.sha256(finish_theta_path.read_bytes()).hexdigest(),
                    "bytes":finish_theta_path.stat().st_size,"shape":list(finish_theta_before.shape),
                    "fields":{"before_theta":"prepared KDM TH input, applied_before[0]",
                              "clean_theta":"applied_clean_replay[0], KDM output TH retained by cleanup"}},
                "initial_qc":{"path":str(initial_qc_path.resolve()),
                    "sha256":hashlib.sha256(initial_qc_path.read_bytes()).hexdigest(),
                    "bytes":initial_qc_path.stat().st_size,"shape":list(initial_qc_export.shape),
                    "source":"source packet state row 2, joined by native flat_index; candidate controls alter T/Q only"},
            },
            "exporter_source_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "applied_water_diagnostics":{"baseline_source":"parent pinned applied audit's per-column deltas and actual DEN*DELZ weights",
                "candidate_weight":"captured applied_forcing[DEN]*applied_forcing[DELZ] (f64 product before per-column math.fsum)",
                "aggregation":"unweighted sum of per-column kg/m2 diagnostics; not regional mass",
                "baseline_kg_m2_unweighted_over_columns":baseline_water_totals,
                "candidate_kg_m2_unweighted_over_columns":candidate_water_totals,
                "delta_kg_m2_unweighted_over_columns":_sum_water_column_arrays(water_delta),
                "per_column_export":water_file,
                "precipitation":"not captured; no closed-water-budget claim"},
            "rate_relation_audit":rate_audit,
            "limits":["No baseline KDM replay was made; baseline H relation uses the existing zero-residual applied-audit record.",
                      "No host RK receiver or operational tendency application is certified.",
                      "NC/NI host number units remain uncertified; no number-budget claim."]}
    crosswalk_path=out/"tendency_crosswalk.json"
    with crosswalk_path.open('x') as stream:
        json.dump(report,stream,indent=2,allow_nan=False);stream.write("\n")
    audit_path=out/"rate_relation_audit.json"
    with audit_path.open('x') as stream:
        json.dump(rate_audit,stream,indent=2,allow_nan=False);stream.write("\n")
    return report


def _plot_restricted_tendency_response(output, report):
    """Show named rates and call-weighted water changes on the complete grid."""
    import matplotlib.pyplot as plt

    def row_sum(values):
        return np.asarray([math.fsum(map(float, row)) for row in values])

    with np.load(report["applied_water_diagnostics"]["per_column_export"]["path"],
                 allow_pickle=False) as archive:
        water = {name: archive[name] for name in archive.files}
    weights = [water[name + "_DEN_times_DELZ_kg_m2_by_level"]
               for name in ("baseline", "candidate")]
    rate_columns = {}
    fig, axes = plt.subplots(3, 3, figsize=(15, 12), constrained_layout=True)
    vertical, vertical_axes = plt.subplots(1, 3, figsize=(14, 6), constrained_layout=True)

    def panels(axs, fields, label, unit):
        shared = max(float(np.max(np.abs(v))) for v in fields[:2])
        for i, (ax, values) in enumerate(zip(axs, fields)):
            maximum = shared if i < 2 else float(np.max(np.abs(values)))
            if maximum:
                image = ax.imshow(values.reshape(282, 234), origin="lower", cmap="coolwarm",
                                  vmin=-maximum, vmax=maximum)
                fig.colorbar(image, ax=ax, shrink=0.75, label=unit)
            else:
                ax.text(0.5, 0.5, "exactly 0", transform=ax.transAxes,
                        ha="center", va="center")
                ax.set_xlim(-0.5, 233.5)
                ax.set_ylim(-0.5, 281.5)
            ax.set_title(label + "\n" + ("Baseline", "Candidate", "Candidate − baseline")[i])
            ax.set_xlabel("native i (0-based)")
            ax.set_ylabel("native j (0-based)")

    statistics = {}
    for i, name in enumerate(("H_RATE", "QV_RATE", "QC_RATE")):
        record = report["exports"][name]
        with np.load(record["path"], allow_pickle=False) as archive:
            rates = {key: archive[key] for key in ("baseline", "candidate", "delta")}
        integrated = [row_sum(rates[key] * weight)
                      for key, weight in zip(("baseline", "candidate"), weights)]
        if name == "H_RATE":
            integrated = [value / row_sum(weight) for value, weight in zip(integrated, weights)]
            label, unit = "Moist-theta memory mass mean", "K/s"
        else:
            label, unit = name + " column integral", "kg/m²/s"
        fields = integrated + [integrated[1] - integrated[0]]
        panels(axes[i], fields, label, unit)
        for key, field in zip(("baseline", "candidate", "delta"), fields):
            rate_columns[name + "_" + key] = field
        for key, style in (("baseline", "k-"), ("candidate", "b-"), ("delta", "g--")):
            means = row_sum(rates[key].T) / rates[key].shape[0]
            vertical_axes[i].plot(means, np.arange(1, NATIVE_LEVELS + 1), style, label=key)
        vertical_axes[i].set_title(name)
        vertical_axes[i].set_xlabel(record["unit"] + "; equal column weights")
        vertical_axes[i].set_ylabel("native mass level (1 = bottom)")
        vertical_axes[i].legend()
        statistics[name] = {"max_abs_delta": float(np.max(np.abs(rates["delta"]))),
                            "changed_values": int(np.count_nonzero(rates["delta"])),
                            "unit": record["unit"]}
    fig.suptitle("Actual-call DEN×DELZ diagnostics on all 65,988 columns\n"
                 "Heating memory is not physical-temperature rate; no host/RK consumption claimed")
    fig.savefig(output / "tendency_response.png", dpi=150)
    plt.close(fig)
    vertical.suptitle("Baseline, candidate and response of named rates over native levels")
    vertical.savefig(output / "tendency_vertical_profiles.png", dpi=150)
    plt.close(vertical)
    with (output / "column_rate_response.npz").open("xb") as stream:
        np.savez_compressed(stream, flat_index=water["flat_index"], **rate_columns)

    fig, axes = plt.subplots(3, 3, figsize=(15, 12), constrained_layout=True)
    for row, (key, title) in enumerate((("raw_minus_input_kg_m2", "Raw KDM change"),
                                      ("cleanup_minus_raw_kg_m2", "Outer cleanup change"),
                                      ("applied_minus_input_kg_m2", "Applied change"))):
        fields = [row_sum(water[prefix + "_" + key].T) for prefix in ("baseline", "candidate")]
        panels(axes[row], fields + [fields[1] - fields[0]], title, "kg/m²")
    fig.suptitle("Net sum across six water species relative to each call's own input\n"
                 "Actual DEN×DELZ; no precipitation export or closed/regional water-budget claim")
    fig.savefig(output / "water_phase_changes.png", dpi=150)
    plt.close(fig)
    return statistics


def summarize_restricted_confirmation(parent_root, confirmation_root, output_dir,
                                      *, make_plots=True):
    """Join one reproduced restricted forward and export its state/rate response.

    The original completed experiment is read-only. No model, gradient, or
    RTTOV call occurs here, and only a fresh output directory is permitted.
    """
    from harness.native_satellite_objective import cost_decreased, finalize_objective

    parent_root = Path(parent_root).resolve(strict=True)
    root = Path(confirmation_root).resolve(strict=True)
    original_out = Path(output_dir).absolute()
    out = original_out.resolve()
    if original_out.exists() or original_out.is_symlink():
        raise FileExistsError("restricted summary output must be a new directory")
    for source in (parent_root, root):
        if out == source or out in source.parents or source in out.parents:
            raise ValueError("restricted summary must not overlap an input run")
    parent_case, base_manifest, _, case, confirmation, base_hashes = (
        _load_restricted_confirmation(parent_root, root)
    )
    if confirmation["screen_objective"] != case["expected_screen_J_total"]:
        raise ValueError("confirmation screen cost differs from its pinned candidate contract")
    baseline = _join_manifest(parent_root, base_manifest, nx=234, ny=282,
                              stage="baseline", run_id=parent_case["run_id"])
    candidate = _join_manifest(root, confirmation, nx=234, ny=282, trial=True,
                               stage=confirmation["stage"], run_id=case["run_id"],
                               baseline_sha_by_chunk=base_hashes)
    for name in ("flat_index", "mask", "weights", "obs_bt", "source_eligible", "active"):
        if not np.array_equal(baseline[name], candidate[name]):
            raise ValueError(f"restricted confirmation changes frozen {name}")
    z = candidate["z"]
    control_hash = hashlib.sha256(np.ascontiguousarray(z).tobytes()).hexdigest()
    if control_hash != confirmation["controls_sha256"]:
        raise ValueError("assembled restricted z differs from its manifest hash")
    expected_theta = baseline["theta_m"] + candidate["delta_theta"]
    expected_qv = baseline["qv"] + candidate["delta_qv"]
    if (not _same_f64_bits(candidate["theta_m"], expected_theta)
            or not _same_f64_bits(candidate["qv"], expected_qv)):
        raise ValueError("restricted inputs are not one baseline-relative update")
    frozen_rows = np.isin(baseline["flat_index"] // 512, case["freeze_blocks_0based"])
    if np.any(z[:, frozen_rows]) or np.any(z[~baseline["active"]]):
        raise ValueError("restricted z changes a frozen degree of freedom")
    if np.max(np.abs(z)) > 1.0:
        raise ValueError("restricted normalized control exceeds the declared bound")
    normalizer = math.fsum(map(float, baseline["weights"].ravel()))
    if normalizer != base_manifest["globalZ"] or normalizer != confirmation["globalZ"]:
        raise ValueError("restricted summary changes the global normalizer")

    def recompute(arrays, control):
        numerators = []
        for entry in base_manifest["chunks"]:
            rows = slice(entry["start"], entry["stop"])
            support = {"m0": baseline["mask"][rows], "weights": baseline["weights"][rows]}
            numerators.append(objective_chunk(arrays["bt"][rows], baseline["obs_bt"][rows],
                                               support)["numerator"])
        return finalize_objective(numerators, normalizer, control, baseline["active"])

    base_cost = recompute(baseline, np.zeros_like(z))
    actual = recompute(candidate, z)
    if (base_cost["cost"] != base_manifest["objective"]["J_total"]
            or actual != confirmation["actual_objective"]):
        raise ValueError("receipt-joined objective differs from recorded global costs")
    accepted = confirmation["status"] == "RESTRICTED_UPDATE_ACCEPTED"
    decrease = cost_decreased(base_cost["cost"], actual["cost"])
    if accepted != decrease["decreased"]:
        raise ValueError("restricted acceptance differs from the unchanged cost threshold")
    metrics_base = _channel_metrics(baseline["obs_bt"], baseline["bt"],
                                    baseline["mask"], baseline["weights"])
    metrics_candidate = _channel_metrics(baseline["obs_bt"], candidate["bt"],
                                         baseline["mask"], baseline["weights"])
    out.mkdir(parents=True, exist_ok=False)
    artifacts = {}

    def save(name, **fields):
        path = out / name
        with path.open("xb") as stream:
            np.savez_compressed(stream, **fields)
        if path.stat().st_size > 50 * 1024**2:
            raise ValueError(f"split oversized public array artifact: {name}")
        artifacts[name] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                           "bytes": path.stat().st_size}

    flat = baseline["flat_index"]
    final = candidate if accepted else baseline
    save("channel_comparison.npz", flat_index=flat, observed_bt=baseline["obs_bt"],
         baseline_bt=baseline["bt"], candidate_bt=candidate["bt"], final_bt=final["bt"],
         mask=baseline["mask"], weights=baseline["weights"],
         baseline_quality=baseline["quality"], candidate_quality=candidate["quality"],
         baseline_profile_valid=baseline["profile_valid"],
         candidate_profile_valid=candidate["profile_valid"],
         baseline_reasons=baseline["reasons"], candidate_reasons=candidate["reasons"])
    save("candidate_input_state.npz", flat_index=flat,
         theta_m=candidate["theta_m"], qv=candidate["qv"])
    save("candidate_input_delta.npz", flat_index=flat, frozen_control_rows=frozen_rows,
         delta_theta=candidate["delta_theta"], delta_qv=candidate["delta_qv"])
    for label, input_root, manifest, arrays in (
        ("baseline", parent_root, base_manifest, baseline),
        ("candidate", root, confirmation, candidate),
    ):
        receivers = {"native_after_qv": [], "cloud_qc": []}
        for entry in manifest["chunks"]:
            extra, _ = _read_capture_arrays(input_root, entry, tuple(receivers))
            for name in receivers:
                receivers[name].append(extra[name])
        save(label + "_applied_tq.npz", flat_index=flat, t_new_after=arrays["finish"][0],
             qv_after=np.concatenate(receivers["native_after_qv"]))
        save(label + "_applied_qc.npz", flat_index=flat,
             qc_after=np.concatenate(receivers["cloud_qc"]))
    tendencies = export_restricted_tendencies(parent_root, root, out / "tendencies")
    plot_arrays = {"obs_bt": baseline["obs_bt"], "baseline_bt": baseline["bt"],
                   "final_bt": candidate["bt"], "mask": baseline["mask"],
                   "delta_theta": candidate["delta_theta"],
                   "delta_qv": candidate["delta_qv"],
                   "reasons": baseline["reasons"], "frozen_control_rows": frozen_rows}
    if make_plots:
        _plot_maps(out, plot_arrays, 234, 282, comparison_name="Candidate",
                   control_name="Candidate input")
        tendency_statistics = _plot_restricted_tendency_response(out, tendencies)
    else:
        tendency_statistics = None
    summary = {
        "schema": "kdm6.native_satellite_restricted_summary.v1",
        "status": confirmation["status"], "accepted": accepted,
        "run_id": case["run_id"], "parent_run_id": parent_case["run_id"],
        "globalZ": normalizer, "native_columns": 65988, "original_blocks": 129,
        "freeze_blocks_0based": case["freeze_blocks_0based"],
        "frozen_native_columns": int(frozen_rows.sum()), "controls_sha256": control_hash,
        "baseline_objective": base_cost, "screen_J_total": confirmation["screen_objective"],
        "actual_objective": actual, "cost_acceptance": decrease,
        "percent_total_decrease": 100 * decrease["decrease"] / base_cost["cost"],
        "per_channel": {"baseline": metrics_base, "candidate": metrics_candidate},
        "profile_admission": {
            name: {"valid_profiles": int(arrays["profile_valid"].sum()),
                   "reason_counts": {str(reason): int(count) for reason, count in
                                     zip(*np.unique(arrays["reasons"], return_counts=True))}}
            for name, arrays in (("baseline", baseline), ("candidate", candidate))
        },
        "candidate_input_change": {"max_abs_theta_m_K": float(np.max(np.abs(candidate["delta_theta"]))),
                                    "max_abs_qv_kgkg_dry": float(np.max(np.abs(candidate["delta_qv"])))},
        "accepted_input_delta_artifact": "candidate_input_delta.npz" if accepted else None,
        "applied_tendencies": tendencies, "tendency_response": tendency_statistics,
        "artifacts": artifacts,
        "limits": ["Post-hoc control-space projection; original observation support/weights retained.",
                   "Input control increments, applied microphysics changes and tendency responses are distinct.",
                   "Same scene used for candidate selection and evaluation; no held-out or forecast-skill claim.",
                   "No native host/RK timestep or cycle and no closed water/energy/number budget certified."],
    }
    with (out / "summary.json").open("x") as stream:
        json.dump(summary, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return summary
