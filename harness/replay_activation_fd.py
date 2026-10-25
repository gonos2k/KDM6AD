"""Offline replay of the saved block22 activation-direction FD campaign.

The reader never loads KDM/RTTOV code or executes a model. It validates the
manifest-bound files, independently reconstructs finite-difference arithmetic,
and keeps the joint 33-category decision separate from the component checks.
"""

from __future__ import annotations

import argparse
from io import BytesIO
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from harness.verify_localized_ice_ad import ATOL as NATIVE_ATOL
from harness.verify_localized_ice_ad import FIELDS as NATIVE_FIELDS
from harness.verify_localized_ice_ad import RTOL as NATIVE_RTOL
from harness.verify_localized_ice_ad import SCALES as NATIVE_SCALES


SCHEMA = "kdm6.block22_activation_fd_inputs.v1"
BATCH, LEVELS, TARGET_ROW, TARGET_FLAT = 512, 39, 368, 11632
CHANNELS = (10, 11, 12, 13, 14, 15, 16)
PROFILE_FIELDS = (
    "T", "Q", "P", "P_HALF", "HYDRO6", "HYDRO7", "HYDRO_DEFF6", "HYDRO_DEFF7"
)
PROFILE_LENGTHS = {name: (67 if name == "P_HALF" else 66) for name in PROFILE_FIELDS}
BASELINE_PROFILE_FIELDS = PROFILE_FIELDS + ("CFRAC",)
PROFILE_K_KEYS = {
    "T": "K_T",
    "Q": "K_Q",
    "P": "K_P",
    "P_HALF": "K_P_HALF",
    "HYDRO6": "K_HYDRO6",
    "HYDRO7": "K_HYDRO7",
    "HYDRO_DEFF6": "K_HYDRO_DEFF6",
    "HYDRO_DEFF7": "K_HYDRO_DEFF7",
}
REQUIRED_ROLES = {
    "ad_control", "ad_off", "ad_on", "input_bundle", "accepted_z_block22",
    "profile_jvp", "baseline_K", "huber_seed", "native_summary",
    "observation_result", "cost_vjp", "activation_trace", "observer_receipt",
    "fd_trace", "plan", "objective_inputs",
}
EPSILON_SIGNS = {(1.0e-2, 1), (1.0e-2, -1), (1.0e-3, 1), (1.0e-3, -1),
                 (1.0e-4, 1), (1.0e-4, -1), (1.0e-5, 1), (1.0e-5, -1),
                 (1.0e-6, 1), (1.0e-6, -1)}


class ReplayError(ValueError):
    """Malformed, incomplete, or inconsistent saved FD packet."""


def same_bits(left, right) -> bool:
    a = np.asarray(left)
    b = np.asarray(right)
    return a.shape == b.shape and a.dtype == b.dtype and a.tobytes(order="C") == b.tobytes(order="C")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _finite_numeric_array(value, name: str) -> np.ndarray:
    array = np.asarray(value)
    if array.dtype.hasobject:
        raise ReplayError(f"{name} contains an object array")
    if array.dtype.kind in "fiu b".replace(" ", ""):
        if not np.isfinite(array).all():
            raise ReplayError(f"{name} contains nonfinite values")
    elif array.dtype.kind not in "SU":
        raise ReplayError(f"{name} has unsupported dtype {array.dtype}")
    return array


def _json_finite(value, where="json"):
    if isinstance(value, dict):
        for key, child in value.items():
            _json_finite(child, f"{where}.{key}")
    elif isinstance(value, list):
        for i, child in enumerate(value):
            _json_finite(child, f"{where}[{i}]")
    elif isinstance(value, float) and not math.isfinite(value):
        raise ReplayError(f"{where} contains a nonfinite JSON number")


def _read_json(raw: bytes, name: str) -> dict:
    try:
        value = json.loads(raw, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ReplayError(f"{name} is not finite UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ReplayError(f"{name} must be a JSON object")
    _json_finite(value, name)
    return value


def _descriptor(root: Path, entry: dict, label: str) -> tuple[Path, bytes]:
    if not isinstance(entry, dict) or set(("file", "sha256", "bytes")) - set(entry):
        raise ReplayError(f"{label} must contain file, sha256, and bytes")
    relative = Path(entry["file"])
    if relative.is_absolute():
        raise ReplayError(f"{label} path must be relative to the pack")
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise ReplayError(f"{label} escapes the manifest pack root") from exc
    if path.is_symlink() or not path.is_file():
        raise ReplayError(f"{label} is missing or is not a regular file")
    raw = path.read_bytes()
    if type(entry["bytes"]) is not int or len(raw) != entry["bytes"]:
        raise ReplayError(f"{label} byte count differs from manifest")
    if not isinstance(entry["sha256"], str) or sha256(raw) != entry["sha256"]:
        raise ReplayError(f"{label} SHA-256 differs from manifest")
    return path, raw


def _load_npz(raw: bytes, label: str) -> dict[str, np.ndarray]:
    try:
        archive = np.load(BytesIO(raw), allow_pickle=False)
        arrays = {name: _finite_numeric_array(archive[name], f"{label}.{name}") for name in archive.files}
    except (OSError, ValueError, KeyError) as exc:
        if isinstance(exc, ReplayError):
            raise
        raise ReplayError(f"{label} is not a valid non-pickle NPZ") from exc
    finally:
        try:
            archive.close()
        except UnboundLocalError:
            pass
    return arrays


def _load_inputs(manifest_path: Path):
    manifest_path = Path(manifest_path)
    raw_manifest = manifest_path.read_bytes()
    manifest = _read_json(raw_manifest, "manifest")
    if manifest.get("schema") != SCHEMA:
        raise ReplayError("manifest schema mismatch")
    root = manifest_path.resolve().parent
    roles = manifest.get("roles")
    if not isinstance(roles, dict) or set(roles) != REQUIRED_ROLES:
        missing = sorted(REQUIRED_ROLES - set(roles or {}))
        extra = sorted(set(roles or {}) - REQUIRED_ROLES)
        raise ReplayError(f"manifest role set mismatch; missing={missing}, extra={extra}")

    role_meta, role_data = {}, {}
    for role, descriptor in roles.items():
        path, raw = _descriptor(root, descriptor, f"role:{role}")
        role_meta[role] = {"file": descriptor["file"], "sha256": sha256(raw), "bytes": len(raw)}
        if role in {"huber_seed", "plan", "native_summary", "observation_result", "observer_receipt"}:
            role_data[role] = _read_json(raw, f"role:{role}")
        elif role in {"activation_trace", "fd_trace"}:
            if not raw.startswith(b"call\tstage\trow0\tlevel_bottom0\tdt_s\tfield\tkind\tvalue\n"):
                raise ReplayError(f"role:{role} TSV header mismatch")
            role_data[role] = raw
        elif role in REQUIRED_ROLES:
            role_data[role] = _load_npz(raw, f"role:{role}")

    control_zero_history = manifest.get("control_zero_history")
    control_zero_summary = None
    if control_zero_history is not None:
        if manifest.get("original_accepted_z_file_sha256") != control_zero_history.get("accepted_run_control_npz_sha256"):
            raise ReplayError("accepted-run control NPZ hash differs from lineage metadata")
        if control_zero_history.get("numeric_equal") is not True:
            raise ReplayError("control lineage does not assert numeric equality of accepted and AD direction recipes")
        accepted_z = np.asarray(role_data["accepted_z_block22"].get("z"))
        if accepted_z.shape != (2, BATCH, LEVELS) or accepted_z.dtype != np.float64:
            raise ReplayError("accepted-run/public z role must contain float64 z[2,512,39]")
        zero_sign_differences = control_zero_history.get("signed_zero_bit_differences_per_component")
        if zero_sign_differences != [8619, 8619]:
            raise ReplayError("accepted-vs-AD zero-sign difference metadata differs from reviewed lineage")
        control_zero_summary = {
            "accepted_z_role_file": roles["accepted_z_block22"]["file"],
            "accepted_z_role_sha256": role_meta["accepted_z_block22"]["sha256"],
            "accepted_run_control_npz_sha256": control_zero_history["accepted_run_control_npz_sha256"],
            "accepted_run_control_array_sha256": control_zero_history["accepted_run_control_array_sha256"],
            "recorded_AD_direction_recipe": control_zero_history["recorded_AD_direction_recipe"],
            "numeric_equal": bool(control_zero_history["numeric_equal"]),
            "signed_zero_bit_differences_per_component": zero_sign_differences,
            "scope": control_zero_history.get("scope", ""),
        }

    endpoint_entries = manifest.get("endpoints")
    if not isinstance(endpoint_entries, list) or len(endpoint_entries) != 10:
        raise ReplayError("manifest must contain exactly ten centered-FD endpoints")
    endpoints, endpoint_meta = {}, {}
    for index, item in enumerate(endpoint_entries):
        if not isinstance(item, dict) or not {"epsilon", "sign", "native", "observation"} <= set(item):
            raise ReplayError(f"endpoint {index} metadata is incomplete")
        try:
            epsilon = float(item["epsilon"])
            sign = int(item["sign"])
        except (TypeError, ValueError) as exc:
            raise ReplayError(f"endpoint {index} epsilon/sign is invalid") from exc
        if not math.isfinite(epsilon) or sign not in (-1, 1):
            raise ReplayError(f"endpoint {index} epsilon/sign is invalid")
        key = (epsilon, sign)
        if key in endpoints:
            raise ReplayError(f"duplicate endpoint epsilon/sign {key}")
        native_path, native_raw = _descriptor(root, item["native"], f"endpoint:{key}:native")
        obs_path, obs_raw = _descriptor(root, item["observation"], f"endpoint:{key}:observation")
        endpoints[key] = {
            "native": _load_npz(native_raw, f"endpoint:{key}:native"),
            "observation": _load_npz(obs_raw, f"endpoint:{key}:observation"),
        }
        endpoint_meta[key] = {
            "native": {"file": item["native"]["file"], "sha256": sha256(native_raw), "bytes": len(native_raw)},
            "observation": {"file": item["observation"]["file"], "sha256": sha256(obs_raw), "bytes": len(obs_raw)},
        }
    if set(endpoints) != EPSILON_SIGNS:
        raise ReplayError("endpoint set differs from the required five epsilon pairs")
    return manifest_path, manifest, raw_manifest, role_data, role_meta, endpoints, endpoint_meta, control_zero_summary


def _required(mapping: dict, name: str, label: str):
    if name not in mapping:
        raise ReplayError(f"{label} missing exact field {name}")
    return mapping[name]


def _baseline_ad(ad: dict, name: str) -> np.ndarray:
    key = f"baseline__{name}"
    if key not in ad:
        raise ReplayError(f"ad_control missing {key}")
    return _finite_numeric_array(ad[key], key)


def _accepted_z(z_archive: dict) -> tuple[np.ndarray, np.ndarray]:
    z = np.asarray(z_archive.get("z"))
    if z.shape != (2, BATCH, LEVELS) or z.dtype != np.float64:
        raise ReplayError("accepted_z_block22.z must be float64[2,512,39]")
    return z[0], z[1]


def _profile_array(mapping: dict, name: str, role: str) -> np.ndarray:
    key = f"profile_{name}"
    if key not in mapping:
        raise ReplayError(f"{role} missing exact field {key}")
    return _finite_numeric_array(mapping[key], f"{role}.{key}")


def _profile_jvp_arrays(mapping: dict) -> dict[str, np.ndarray]:
    out = {}
    for name, length in PROFILE_LENGTHS.items():
        key = f"JVP_{name}"
        if key not in mapping:
            raise ReplayError(f"profile_jvp missing exact field {key}")
        value = mapping[key]
        array = _finite_numeric_array(value, f"profile_jvp.{name}")
        if array.shape == (length,):
            array = array.reshape(1, length)
        if array.shape != (1, length) or array.dtype != np.float64:
            raise ReplayError(f"profile JVP {name} must be float64[1,{length}]")
        out[name] = array
    return out


def _endpoint_bt(mapping: dict, label: str) -> np.ndarray:
    if "bt" not in mapping:
        raise ReplayError(f"{label} missing exact field bt")
    value = np.asarray(mapping["bt"])
    if value.dtype != np.float64:
        raise ReplayError(f"{label} bt must be float64")
    if value.shape == (1, len(CHANNELS)):
        value = value[0]
    if value.shape != (len(CHANNELS),) or not np.isfinite(value).all():
        raise ReplayError(f"{label} BT must be finite float64[7]")
    return value


def coordinate_ratios(fd, tangent, atol: float, rtol: float) -> dict:
    """Per-coordinate ratio check; deliberately does not use a field max-norm denominator."""
    a = np.asarray(fd, dtype=np.float64)
    b = np.asarray(tangent, dtype=np.float64)
    if a.shape != b.shape or not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ReplayError("coordinate ratio operands must be same-shape finite arrays")
    denominator = float(atol) + float(rtol) * np.maximum(np.abs(a), np.abs(b))
    ratios = np.divide(np.abs(a - b), denominator, out=np.zeros_like(a), where=denominator > 0.0)
    worst = np.unravel_index(int(np.argmax(ratios)), ratios.shape)
    return {
        "coordinate_count": int(ratios.size),
        "passing_coordinates": int(np.count_nonzero(ratios <= 1.0)),
        "max_coordinate_ratio": float(np.max(ratios, initial=0.0)),
        "worst_coordinate": [int(i) for i in worst],
        "passed": bool(np.all(ratios <= 1.0)),
    }


def _native_ratio_summary(fd17, tangent17, row: int) -> dict:
    # Match the established native verifier's scaled state/finish statistic:
    # scale fields first, then take one level maximum per output field.
    scales = np.asarray(NATIVE_SCALES, dtype=np.float64).reshape(17, 1, 1)
    atols = np.asarray(NATIVE_ATOL, dtype=np.float64).reshape(17)
    rtols = np.asarray(NATIVE_RTOL, dtype=np.float64).reshape(17)
    fd_values = np.asarray(fd17, dtype=np.float64)
    jvp_values = np.asarray(tangent17, dtype=np.float64)
    # Preserve the existing verifier's operation order: subtract first, then
    # scale the difference; scale each signal separately for the denominator.
    err_scaled = np.abs((fd_values - jvp_values) / scales)
    signal_scaled = np.maximum(np.abs(fd_values / scales), np.abs(jvp_values / scales))
    result = {}
    for label, selection in (("target_row", (slice(None), row, slice(None))), ("fullB", (slice(None), slice(None), slice(None)))):
        err = err_scaled[selection]
        signal = signal_scaled[selection]
        max_err = np.max(err, axis=1) if label == "target_row" else np.max(err, axis=(1, 2))
        max_signal = np.max(signal, axis=1) if label == "target_row" else np.max(signal, axis=(1, 2))
        ratios = max_err / (atols + rtols * max_signal)
        result[label] = {
            "ratio_by_output": ratios.tolist(),
            "pass_by_output": (ratios <= 1.0).tolist(),
            "pass_all_17": bool(np.all(ratios <= 1.0)),
            "max_ratio": float(np.max(ratios)),
        }
    result["output_fields"] = list(NATIVE_FIELDS)
    return result


def _huber_numerator(bt, obs, weights, mask, *, sigma, delta, bias) -> float:
    residual = (np.asarray(bt, dtype=np.float64) - np.asarray(obs, dtype=np.float64) - float(bias)) / float(sigma)
    weights = np.asarray(weights, dtype=np.float64)
    mask = np.asarray(mask, dtype=np.bool_)
    if residual.shape != (7,) or weights.shape != (7,) or mask.shape != (7,):
        raise ReplayError("Huber BT, weights, and mask must have seven channels")
    terms = []
    for r, w, keep in zip(residual, weights, mask):
        if not keep or w == 0.0:
            continue
        magnitude = abs(float(r))
        loss = 0.5 * magnitude * magnitude if magnitude <= delta else delta * (magnitude - 0.5 * delta)
        terms.append(float(w) * loss)
    return math.fsum(terms)


def replay(manifest_path) -> dict:
    """Recompute all saved finite-difference arithmetic from a verified pack."""
    path, manifest, raw_manifest, roles, role_meta, endpoints, endpoint_meta, control_zero_summary = _load_inputs(Path(manifest_path))
    if control_zero_summary is None:
        raise ReplayError("manifest lacks required historical control-zero provenance")
    plan = roles["plan"]
    if plan.get("schema") != "kdm6.block22_activation_experiment_plan.v2":
        raise ReplayError("plan role must be experiment plan v2")
    if plan.get("batch", {}).get("B") != BATCH or plan.get("batch", {}).get("L") != LEVELS or plan.get("batch", {}).get("target_row0") != TARGET_ROW:
        raise ReplayError("experiment plan target/block shape differs from block22")
    local_fd = plan.get("local_FD", {})
    epsilons = [float(x) for x in local_fd.get("epsilons", [])]
    if set((eps, sign) for eps in epsilons for sign in (1, -1)) != EPSILON_SIGNS:
        raise ReplayError("plan epsilon set differs from the ten saved centered endpoints")
    profile_atol = float(local_fd.get("profile_coordinate_atol", 1.0e-8))
    profile_rtol = float(local_fd.get("profile_coordinate_rtol", 3.0e-5))
    bt_atol = float(local_fd.get("BT_cost_atol", 1.0e-8))
    bt_rtol = float(local_fd.get("BT_cost_rtol", 3.0e-5))
    observer_receipt = roles["observer_receipt"]
    if (
        observer_receipt.get("schema") != "kdm6.block22_activation_observer.v1"
        or observer_receipt.get("trace_env") != "KDM6_BLOCK22_ACTIVATION_TRACE"
        or (observer_receipt.get("B"), observer_receipt.get("L"), observer_receipt.get("row0")) != (BATCH, LEVELS, TARGET_ROW)
    ):
        raise ReplayError("observer receipt does not bind the block22 B512/L39 target")

    ad_control, ad_off, ad_on = (roles[name] for name in ("ad_control", "ad_off", "ad_on"))
    if len(ad_control) != 98 or set(ad_control) != set(ad_off) or set(ad_control) != set(ad_on):
        raise ReplayError("three AD mode NPZs must contain the same original 98 array names")
    if any(value.dtype != np.float64 for archive in (ad_control, ad_off, ad_on) for value in archive.values()):
        raise ReplayError("all original AD products must be float64 arrays")
    mode_equal = {}
    for name in sorted(ad_control):
        values = (ad_control[name], ad_off[name], ad_on[name])
        if len({(x.shape, x.dtype.str) for x in values}) != 1:
            raise ReplayError(f"AD mode array metadata differs for {name}")
        mode_equal[name] = bool(same_bits(values[0], values[1]) and same_bits(values[0], values[2]))
    if not all(mode_equal.values()):
        raise ReplayError("AD control/off/on products are not bitwise identical")

    ztheta, zqv = _accepted_z(roles["accepted_z_block22"])
    if ztheta.shape != (BATCH, LEVELS) or zqv.shape != (BATCH, LEVELS) or ztheta.dtype != np.float64 or zqv.dtype != np.float64:
        raise ReplayError("accepted direction z components must be float64 B512x39")
    theta0 = _baseline_ad(ad_control, "theta_m_input")
    qv0 = _baseline_ad(ad_control, "qv_input")
    dtheta = _baseline_ad(ad_control, "direction_theta_m")
    dqv = _baseline_ad(ad_control, "direction_qv")
    if theta0.shape != (BATCH, LEVELS) or qv0.shape != (BATCH, LEVELS) or dtheta.shape != (BATCH, LEVELS) or dqv.shape != (BATCH, LEVELS):
        raise ReplayError("AD baseline inputs/direction are not full B512x39")
    proposal_theta = 0.2 * ztheta
    proposal_qv = 0.02 * qv0 * zqv
    direction_match = {
        "AD_theta_bitwise_matches_parent_alpha025_delta_over_0p25": False,
        "AD_qv_bitwise_matches_parent_alpha025_delta_over_0p25": False,
        "accepted_proposal_numeric_matches_AD_direction": bool(np.array_equal(proposal_theta, dtheta) and np.array_equal(proposal_qv, dqv)),
        "accepted_proposal_bitwise_matches_AD_direction": bool(same_bits(proposal_theta, dtheta) and same_bits(proposal_qv, dqv)),
        "theta_m_numeric_equal": bool(np.array_equal(proposal_theta, dtheta)),
        "qv_numeric_equal": bool(np.array_equal(proposal_qv, dqv)),
        "theta_m_bitwise_equal": same_bits(proposal_theta, dtheta),
        "qv_bitwise_equal": same_bits(proposal_qv, dqv),
        "theta_m_signed_zero_sign_mismatches": int(np.count_nonzero((proposal_theta == dtheta) & (np.signbit(proposal_theta) != np.signbit(dtheta)))),
        "qv_signed_zero_sign_mismatches": int(np.count_nonzero((proposal_qv == dqv) & (np.signbit(proposal_qv) != np.signbit(dqv)))),
        "theta_m_max_abs_difference": float(np.max(np.abs(proposal_theta - dtheta))),
        "qv_max_abs_difference": float(np.max(np.abs(proposal_qv - dqv))),
        "interpretation": "The accepted-run z encoding is authoritative. Numeric equality with the AD alpha025/0.25 direction is required; its historical signed-zero differences are retained below, not treated as input-direction error.",
    }
    if not direction_match["theta_m_numeric_equal"] or not direction_match["qv_numeric_equal"]:
        raise ReplayError("accepted 0.2z/.02*qv*z proposal differs from recorded AD direction")
    if direction_match["theta_m_signed_zero_sign_mismatches"] != control_zero_summary["signed_zero_bit_differences_per_component"][0] or direction_match["qv_signed_zero_sign_mismatches"] != control_zero_summary["signed_zero_bit_differences_per_component"][1]:
        raise ReplayError("accepted/public-to-AD direction signed-zero differences differ from control history")

    input_bundle = roles["input_bundle"]
    for key in ("block__theta_m", "block__qv", "block__mu", "block__ph", "block__rest", "block__geometry__phb", "parent_alpha025__z", "parent_alpha025__delta_theta", "parent_alpha025__delta_qv"):
        if key not in input_bundle:
            raise ReplayError(f"input_bundle missing exact field {key}")
    input_shapes = {
        "block__theta_m": (BATCH, LEVELS), "block__qv": (BATCH, LEVELS),
        "block__mu": (BATCH,), "block__ph": (BATCH, LEVELS + 1),
        "block__rest": (10, BATCH, LEVELS),
        "block__geometry__phb": (BATCH, LEVELS + 1),
        "parent_alpha025__z": (2, BATCH, LEVELS),
        "parent_alpha025__delta_theta": (BATCH, LEVELS),
        "parent_alpha025__delta_qv": (BATCH, LEVELS),
    }
    for key, shape in input_shapes.items():
        value = np.asarray(input_bundle[key])
        if value.shape != shape or value.dtype != np.float64 or not np.isfinite(value).all():
            raise ReplayError(f"input_bundle.{key} must be finite float64{shape}")
    scaled_accepted_z = 0.25 * roles["accepted_z_block22"]["z"]
    if not np.array_equal(input_bundle["parent_alpha025__z"], scaled_accepted_z):
        raise ReplayError("actual full-step z differs from alpha.25 input bundle z")
    alpha25_z_sign_mismatches = [
        int(np.count_nonzero(
            (input_bundle["parent_alpha025__z"][i] == scaled_accepted_z[i])
            & (np.signbit(input_bundle["parent_alpha025__z"][i]) != np.signbit(scaled_accepted_z[i]))
        ))
        for i in range(2)
    ]
    direction_match["accepted_z_vs_alpha025_bundle_signed_zero_sign_mismatches"] = alpha25_z_sign_mismatches
    direction_match["accepted_z_vs_alpha025_bundle_signed_zero_sign_mismatches"] = alpha25_z_sign_mismatches
    if not same_bits(input_bundle["block__theta_m"], theta0) or not same_bits(input_bundle["block__qv"], qv0):
        raise ReplayError("AD baseline controls differ from source-bound input bundle")
    direction_theta_from_saved_alpha = input_bundle["parent_alpha025__delta_theta"] / 0.25
    direction_qv_from_saved_alpha = input_bundle["parent_alpha025__delta_qv"] / 0.25
    direction_match["AD_theta_bitwise_matches_parent_alpha025_delta_over_0p25"] = same_bits(dtheta, direction_theta_from_saved_alpha)
    direction_match["AD_qv_bitwise_matches_parent_alpha025_delta_over_0p25"] = same_bits(dqv, direction_qv_from_saved_alpha)
    direction_match["actual_parent_recipe_byte_equal"] = bool(
        direction_match["AD_theta_bitwise_matches_parent_alpha025_delta_over_0p25"]
        and direction_match["AD_qv_bitwise_matches_parent_alpha025_delta_over_0p25"]
    )
    direction_match["accepted_proposal_numeric_equal"] = direction_match["accepted_proposal_numeric_matches_AD_direction"]
    direction_match["accepted_proposal_byte_equal"] = direction_match["accepted_proposal_bitwise_matches_AD_direction"]
    if not direction_match["AD_theta_bitwise_matches_parent_alpha025_delta_over_0p25"] or not direction_match["AD_qv_bitwise_matches_parent_alpha025_delta_over_0p25"]:
        raise ReplayError("AD direction is not byte-identical to accepted parent alpha025 delta divided by 0.25")

    cost_vjp = roles["cost_vjp"]
    common_inputs = {
        "theta_m_input": input_bundle["block__theta_m"],
        "qv_input": input_bundle["block__qv"],
        "mu_total": input_bundle["block__mu"],
        "ph": input_bundle["block__ph"],
        "rest": input_bundle["block__rest"],
        "direction_theta_m": dtheta,
        "direction_qv": dqv,
    }
    for name, expected in common_inputs.items():
        if name not in cost_vjp or not same_bits(cost_vjp[name], expected):
            raise ReplayError(f"cost_vjp.{name} differs from source-bound common inputs/AD direction")
    raw_input = _required(cost_vjp, "abi_abi_state_input", "cost_vjp")
    if raw_input.shape != (12, BATCH, LEVELS) or not same_bits(raw_input[2:], input_bundle["block__rest"]):
        raise ReplayError("cost_vjp raw ABI rest does not match source-bound input bundle")
    common_phi = input_bundle["block__ph"] + input_bundle["block__geometry__phb"]
    baseline_phi = _required(cost_vjp, "primal_native_after_phi_interfaces", "cost_vjp")
    if common_phi.shape != (BATCH, LEVELS + 1) or not same_bits(common_phi, baseline_phi):
        raise ReplayError("source-bound PH+PHB differs from baseline native phi interfaces")

    baseline_k = roles["baseline_K"]
    if any(value.dtype != np.float64 for key, value in baseline_k.items() if key not in {"quality", "parent_support_mask"}):
        raise ReplayError("baseline_K profile/K arrays must be float64")
    baseline_quality = np.asarray(_required(baseline_k, "quality", "baseline_K"))
    baseline_support = np.asarray(_required(baseline_k, "parent_support_mask", "baseline_K"))
    if baseline_quality.shape != (7,) or baseline_quality.dtype != np.int32:
        raise ReplayError("baseline K quality must be int32[7]")
    if baseline_support.shape != (7,) or baseline_support.dtype != np.bool_:
        raise ReplayError("baseline K support mask must be bool[7]")
    for name, expected_len in PROFILE_LENGTHS.items():
        profile = _profile_array(baseline_k, name, "baseline_K")
        key = PROFILE_K_KEYS[name]
        k = np.asarray(_required(baseline_k, key, "baseline_K"))
        if profile.shape != (1, expected_len) or profile.dtype != np.float64:
            raise ReplayError(f"baseline profile {name} has wrong shape/dtype")
        if k.shape != (1, 7, expected_len) or k.dtype != np.float64:
            raise ReplayError(f"baseline K field {key} has wrong shape/dtype")
    profile_cfrac = _profile_array(baseline_k, "CFRAC", "baseline_K")
    if profile_cfrac.shape != (1, 66) or profile_cfrac.dtype != np.float64:
        raise ReplayError("baseline CFRAC must be float64[1,66]")
    baseline_bt = _endpoint_bt(baseline_k, "baseline_K")

    profile_jvp = _profile_jvp_arrays(roles["profile_jvp"])
    bt_jvp = np.zeros(7, dtype=np.float64)
    for field in PROFILE_FIELDS:
        k = np.asarray(baseline_k[PROFILE_K_KEYS[field]], dtype=np.float64)[0]
        dp = profile_jvp[field][0]
        for channel in range(7):
            bt_jvp[channel] += math.fsum(float(k[channel, level] * dp[level]) for level in range(PROFILE_LENGTHS[field]))

    seed = roles["huber_seed"]
    seed_bt = np.asarray(seed.get("baseline_bt_kma_v3_0"), dtype=np.float64)
    cotangent = np.asarray(seed.get("baseline_target_bt_cotangent_numerator"), dtype=np.float64)
    if seed_bt.shape != (7,) or cotangent.shape != (7,) or not same_bits(seed_bt, baseline_bt):
        raise ReplayError("saved baseline BT/cotangent seed differs from baseline K role")
    if not np.array_equal(cotangent, np.ones(7, dtype=np.float64)):
        raise ReplayError("expected the saved all-seven +1 Huber numerator cotangent")
    seed_bt_jvp = np.asarray(seed.get("actual_candidate_direction_baseline_BT_JVP_K"), dtype=np.float64)
    if seed_bt_jvp.shape != (7,) or not np.allclose(bt_jvp, seed_bt_jvp, rtol=1e-13, atol=1e-13):
        raise ReplayError("fresh K times saved profile JVP differs from Huber seed BT JVP")
    huber_jvp = math.fsum(float(a * b) for a, b in zip(cotangent, bt_jvp))
    expected_huber_jvp = float(seed["target_cost_directional_numerator_from_Huber_seed"])

    observation_result = roles["observation_result"]
    objective_inputs = roles["objective_inputs"]
    obs_bt = np.asarray(_required(objective_inputs, "obs_bt", "objective_inputs"))
    support = np.asarray(_required(objective_inputs, "mask", "objective_inputs"))
    weights = np.asarray(_required(objective_inputs, "weights", "objective_inputs"))
    if obs_bt.shape != (7,) or obs_bt.dtype != np.float64 or not np.isfinite(obs_bt).all():
        raise ReplayError("objective_inputs.obs_bt must be finite float64[7]")
    if support.shape != (7,) or support.dtype != np.bool_:
        raise ReplayError("objective_inputs.mask must be bool[7]")
    if weights.shape != (7,) or weights.dtype != np.float64 or not np.isfinite(weights).all():
        raise ReplayError("objective_inputs.weights must be finite float64[7]")
    if set(objective_inputs) != {"obs_bt", "mask", "weights", "sigma", "huber_delta", "global_Z"}:
        raise ReplayError("objective_inputs NPZ key set differs from fixed v1 schema")

    def objective_scalar(name):
        value = np.asarray(_required(objective_inputs, name, "objective_inputs"))
        if value.size != 1 or value.dtype != np.float64 or not np.isfinite(value).all():
            raise ReplayError(f"objective_inputs.{name} must be a finite float64 scalar")
        return float(value.reshape(-1)[0])

    sigma = objective_scalar("sigma")
    delta = objective_scalar("huber_delta")
    global_z = objective_scalar("global_Z")
    bias = float(seed["objective_constants"]["bias"])
    if (sigma, delta) != (float(seed["objective_constants"]["sigma"]), float(seed["objective_constants"]["huber_delta"])):
        raise ReplayError("objective input sigma/delta differs from Huber seed")
    if not same_bits(weights, np.asarray(seed.get("target_support", {}).get("weights"), dtype=np.float64)):
        raise ReplayError("objective input weights differ from Huber seed")
    if global_z != float(seed["global_Z_from_parent_v4"]):
        raise ReplayError("objective input global_Z differs from Huber seed")
    if not same_bits(support, baseline_support):
        raise ReplayError("objective input fixed mask differs from baseline K support")
    if not bool(seed["target_support"]["all_seven_baseline_m0"]) or not support.all():
        raise ReplayError("this replay expects the admitted all-seven target support")
    baseline_huber = _huber_numerator(baseline_bt, obs_bt, weights, support, sigma=sigma, delta=delta, bias=bias)
    if not math.isclose(baseline_huber, float(seed["target_baseline_huber_numerator"]), rel_tol=1e-13, abs_tol=1e-13):
        raise ReplayError("recomputed baseline Huber numerator differs from saved seed")

    observation_results = observation_result.get("epsilon_results")
    if not isinstance(observation_results, list):
        raise ReplayError("observation_result JSON lacks epsilon_results for arithmetic replay")
    obs_by_eps = {float(item["epsilon"]): item for item in observation_results}
    native_summary = roles["native_summary"]
    native_by_eps = {float(item["epsilon"]): item for item in native_summary.get("per_epsilon", [])}
    if set(obs_by_eps) != set(epsilons) or set(native_by_eps) != set(epsilons):
        raise ReplayError("native/observation summaries do not cover all planned epsilons")

    raw_jvp = _baseline_ad(ad_control, "abi_raw_state_jvp")
    finish_jvp = _baseline_ad(ad_control, "tangent_finish")
    if raw_jvp.shape != (12, BATCH, LEVELS) or finish_jvp.shape != (5, BATCH, LEVELS):
        raise ReplayError("AD native JVP arrays have incorrect 12/5-field full-B shapes")
    endpoint_replay = []
    arithmetic_matches = []
    fixed_geometry_checks = []
    base_forcing = np.asarray(_required(cost_vjp, "abi_abi_forcing_input", "cost_vjp"), dtype=np.float64)
    base_rho = np.asarray(_required(cost_vjp, "primal_rho_d", "cost_vjp"), dtype=np.float64)
    for epsilon in sorted(epsilons, reverse=True):
        plus = endpoints[(epsilon, 1)]
        minus = endpoints[(epsilon, -1)]
        plus_native, minus_native = plus["native"], minus["native"]
        plus_obs, minus_obs = plus["observation"], minus["observation"]
        raw_plus = np.asarray(_required(plus_native, "abi_raw_state_output", "native+"), dtype=np.float64)
        raw_minus = np.asarray(_required(minus_native, "abi_raw_state_output", "native-"), dtype=np.float64)
        finish_plus = np.asarray(_required(plus_native, "finish", "native+"), dtype=np.float64)
        finish_minus = np.asarray(_required(minus_native, "finish", "native-"), dtype=np.float64)
        if raw_plus.shape != raw_jvp.shape or raw_minus.shape != raw_jvp.shape or finish_plus.shape != finish_jvp.shape or finish_minus.shape != finish_jvp.shape:
            raise ReplayError(f"native endpoint 12/5 arrays have wrong shape at epsilon {epsilon}")
        for endpoint_arrays in (plus_native, minus_native):
            for key, shape in (
                ("theta_m_input", (BATCH, LEVELS)), ("qv_input", (BATCH, LEVELS)),
                ("abi_state_input", (12, BATCH, LEVELS)), ("abi_forcing_input", (4, BATCH, LEVELS)),
                ("abi_raw_state_output", (12, BATCH, LEVELS)), ("finish", (5, BATCH, LEVELS)),
                ("rho_d", (BATCH, LEVELS)), ("native_phi_interfaces", (BATCH, LEVELS + 1)),
            ):
                value = np.asarray(_required(endpoint_arrays, key, "native endpoint"))
                if value.shape != shape or value.dtype != np.float64 or not np.isfinite(value).all():
                    raise ReplayError(f"native endpoint {key} must be finite float64{shape}")
        for endpoint_obs in (plus_obs, minus_obs):
            q = np.asarray(_required(endpoint_obs, "quality", "observation endpoint"))
            if q.shape != (7,) or q.dtype != np.int32:
                raise ReplayError("observation endpoint quality must be int32[7]")
            for name in BASELINE_PROFILE_FIELDS:
                value = np.asarray(_profile_array(endpoint_obs, name, "observation endpoint"))
                expected_len = 67 if name == "P_HALF" else 66
                if value.shape != (1, expected_len) or value.dtype != np.float64:
                    raise ReplayError(f"observation endpoint profile_{name} shape/dtype mismatch")
        pair_fixed_checks = []
        for endpoint, obs_endpoint in ((plus_native, plus_obs), (minus_native, minus_obs)):
            sign = 1 if endpoint is plus_native else -1
            theta_input = np.asarray(_required(endpoint, "theta_m_input", "native endpoint"))
            qv_input = np.asarray(_required(endpoint, "qv_input", "native endpoint"))
            theta_step = epsilon * proposal_theta
            qv_step = epsilon * proposal_qv
            theta_step_ad = epsilon * dtheta
            qv_step_ad = epsilon * dqv
            expected_theta = theta0 + theta_step if sign > 0 else theta0 - theta_step
            expected_qv = qv0 + qv_step if sign > 0 else qv0 - qv_step
            expected_theta_ad = theta0 + theta_step_ad if sign > 0 else theta0 - theta_step_ad
            expected_qv_ad = qv0 + qv_step_ad if sign > 0 else qv0 - qv_step_ad
            accepted_inputs_match = same_bits(theta_input, expected_theta) and same_bits(qv_input, expected_qv)
            ad_recipe_inputs_match = same_bits(theta_input, expected_theta_ad) and same_bits(qv_input, expected_qv_ad)
            if not accepted_inputs_match:
                raise ReplayError(f"native theta endpoint differs from actual direction at epsilon {epsilon}")
            if not ad_recipe_inputs_match:
                raise ReplayError(f"native endpoint inputs are not bitwise identical under the AD direction recipe at epsilon {epsilon}")
            abi_state = np.asarray(_required(endpoint, "abi_state_input", "native endpoint"), dtype=np.float64)
            if abi_state.shape != (12, BATCH, LEVELS) or not same_bits(abi_state[2:], input_bundle["block__rest"]):
                raise ReplayError(f"native endpoint changes held rest state at epsilon {epsilon}")
            endpoint_phi = np.asarray(_required(endpoint, "native_phi_interfaces", "native endpoint"), dtype=np.float64)
            if endpoint_phi.shape != common_phi.shape or not same_bits(endpoint_phi, common_phi):
                raise ReplayError(f"native endpoint PH+PHB geometry differs at epsilon {epsilon}")
            endpoint_forcing = np.asarray(_required(endpoint, "abi_forcing_input", "native endpoint"), dtype=np.float64)
            endpoint_rho = np.asarray(_required(endpoint, "rho_d", "native endpoint"), dtype=np.float64)
            if endpoint_forcing.shape != (4, BATCH, LEVELS) or endpoint_rho.shape != (BATCH, LEVELS):
                raise ReplayError(f"native endpoint forcing/rho shape differs at epsilon {epsilon}")
            endpoint_baseline_quality = np.asarray(_required(endpoint, "baseline_quality", "native endpoint"))
            baseline_mask = np.asarray(_required(endpoint, "baseline_mask", "native endpoint"))
            if endpoint_baseline_quality.shape != (BATCH, 7) or not same_bits(endpoint_baseline_quality[TARGET_ROW], baseline_k["quality"]):
                raise ReplayError(f"native endpoint baseline quality differs at epsilon {epsilon}")
            if baseline_mask.shape != (BATCH, 7) or not same_bits(baseline_mask[TARGET_ROW], support):
                raise ReplayError(f"native endpoint fixed target support differs at epsilon {epsilon}")
            obs_quality = np.asarray(_required(obs_endpoint, "quality", "observation endpoint"))
            if obs_quality.shape != (7,) or not same_bits(obs_quality, baseline_k["quality"]):
                raise ReplayError(f"observation endpoint target quality differs at epsilon {epsilon}")
            pair_fixed_checks.append({
                "rest_rows2_11_bitwise_match_common_input": True,
                "native_control_inputs_match_accepted_z_bitwise": accepted_inputs_match,
                "native_control_inputs_match_AD_recipe_bitwise": ad_recipe_inputs_match,
                "native_phi_interfaces_bitwise_match_PH_plus_PHB": True,
                "PH_and_MU_scope": "source-bound common input bundle; not separately endpoint-captured",
                "DEN_forcing_matches_baseline": same_bits(endpoint_forcing[0], base_forcing[0]),
                "DELZ_forcing_matches_baseline": same_bits(endpoint_forcing[3], base_forcing[3]),
                "rho_d_matches_baseline": same_bits(endpoint_rho, base_rho),
            })
        fixed_geometry_checks.append({"epsilon": epsilon, "plus": pair_fixed_checks[0], "minus": pair_fixed_checks[1]})
        fd_raw = (raw_plus - raw_minus) / (2.0 * epsilon)
        fd_finish = (finish_plus - finish_minus) / (2.0 * epsilon)
        fd17 = np.concatenate((fd_raw, fd_finish), axis=0)
        jvp17 = np.concatenate((raw_jvp, finish_jvp), axis=0)
        native_ratio = _native_ratio_summary(fd17, jvp17, TARGET_ROW)

        profile_results = {}
        cfrac_changes = {}
        for field in PROFILE_FIELDS:
            p_plus = _profile_array(plus_obs, field, f"endpoint+ observation at {epsilon}")
            p_minus = _profile_array(minus_obs, field, f"endpoint- observation at {epsilon}")
            if p_plus.shape != (1, PROFILE_LENGTHS[field]) or p_minus.shape != p_plus.shape:
                raise ReplayError(f"observation profile {field} has wrong target shape")
            fd_profile = (p_plus - p_minus) / (2.0 * epsilon)
            profile_results[field] = coordinate_ratios(fd_profile, profile_jvp[field], profile_atol, profile_rtol)
        cfrac_base = _profile_array(baseline_k, "CFRAC", "baseline_K")
        cfrac_plus = _profile_array(plus_obs, "CFRAC", f"endpoint+ observation at {epsilon}")
        cfrac_minus = _profile_array(minus_obs, "CFRAC", f"endpoint- observation at {epsilon}")
        if cfrac_plus.shape != cfrac_base.shape or cfrac_minus.shape != cfrac_base.shape:
            raise ReplayError("CFRAC endpoint/baseline shapes differ")
        cfrac_changes = {
            "plus_changed_coordinates": int(np.count_nonzero(cfrac_plus != cfrac_base)),
            "minus_changed_coordinates": int(np.count_nonzero(cfrac_minus != cfrac_base)),
            "central_fd_nonzero_coordinates": int(np.count_nonzero((cfrac_plus - cfrac_minus) != 0.0)),
            "plus_max_abs_change": float(np.max(np.abs(cfrac_plus - cfrac_base), initial=0.0)),
            "minus_max_abs_change": float(np.max(np.abs(cfrac_minus - cfrac_base), initial=0.0)),
        }
        profile8_pass = all(item["passed"] for item in profile_results.values())

        bt_plus, bt_minus = _endpoint_bt(plus_obs, f"epsilon{epsilon} plus observation"), _endpoint_bt(minus_obs, f"epsilon{epsilon} minus observation")
        bt_fd = (bt_plus - bt_minus) / (2.0 * epsilon)
        bt_ratios = coordinate_ratios(bt_fd, bt_jvp, bt_atol, bt_rtol)
        cost_plus = _huber_numerator(bt_plus, obs_bt, weights, support, sigma=sigma, delta=delta, bias=bias)
        cost_minus = _huber_numerator(bt_minus, obs_bt, weights, support, sigma=sigma, delta=delta, bias=bias)
        cost_fd = (cost_plus - cost_minus) / (2.0 * epsilon)
        cost_ratio = coordinate_ratios(np.asarray([cost_fd]), np.asarray([huber_jvp]), bt_atol, bt_rtol)
        bt_cost8_pass = bool(bt_ratios["passed"] and cost_ratio["passed"])
        native17_pass = bool(native_ratio["target_row"]["pass_all_17"])
        joint = bool(native17_pass and profile8_pass and bt_cost8_pass)

        recorded_native = native_by_eps[epsilon]
        native_record_match = (
            np.allclose(native_ratio["target_row"]["ratio_by_output"], recorded_native.get("target_ratio_by_output"), rtol=1e-12, atol=1e-14)
            and bool(native_ratio["target_row"]["pass_all_17"]) == bool(recorded_native.get("target_pass_all_17_outputs"))
        )
        recorded_obs = obs_by_eps[epsilon]
        direct_calls = observation_result.get("calls", {})
        plus_tag = f"eps_{epsilon:.0e}_plus"
        minus_tag = f"eps_{epsilon:.0e}_minus"
        if plus_tag not in direct_calls or minus_tag not in direct_calls:
            raise ReplayError(f"observation_result lacks direct-call records for epsilon {epsilon}")
        recorded_plus, recorded_minus = direct_calls[plus_tag], direct_calls[minus_tag]
        support_record_match = all(
            item.get("fixed_support_mask_matches_baseline") is True
            and item.get("quality_matches_baseline_support") is True
            and item.get("target_quality") == baseline_quality.tolist()
            for item in (recorded_plus, recorded_minus)
        )
        obs_record_match = (
            np.allclose(bt_fd, np.asarray(recorded_obs.get("BT_FD_K"), dtype=np.float64), rtol=1e-12, atol=1e-12)
            and math.isclose(cost_fd, float(recorded_obs.get("target_cost_huber_numerator_fd")), rel_tol=1e-12, abs_tol=1e-10)
            and np.array_equal(bt_plus, np.asarray(recorded_plus["bt_kma_v3_0"], dtype=np.float64))
            and np.array_equal(bt_minus, np.asarray(recorded_minus["bt_kma_v3_0"], dtype=np.float64))
        )
        profile_record_matches = {}
        recorded_profiles = recorded_obs.get("profile_by_field", {})
        for field, metrics in profile_results.items():
            saved = recorded_profiles.get(field, {})
            profile_record_matches[field] = bool(
                saved.get("coordinate_count") == metrics["coordinate_count"]
                and saved.get("passed") == metrics["passed"]
                and math.isclose(
                    float(saved.get("max_coordinate_tolerance_ratio", math.nan)),
                    metrics["max_coordinate_ratio"],
                    rel_tol=1e-12,
                    abs_tol=1e-14,
                )
            )
        saved_cfrac = recorded_obs.get("CFRAC_changed_coordinates", {})
        cfrac_record_match = (
            saved_cfrac.get("plus_vs_baseline") == cfrac_changes["plus_changed_coordinates"]
            and saved_cfrac.get("minus_vs_baseline") == cfrac_changes["minus_changed_coordinates"]
        )
        arithmetic_matches.append(
            bool(
                native_record_match and obs_record_match and support_record_match
                and all(profile_record_matches.values()) and cfrac_record_match
            )
        )
        endpoint_replay.append({
            "epsilon": epsilon,
            "fixed_geometry_and_support_checks": fixed_geometry_checks[-1],
            "native17": native_ratio,
            "profile8": profile_results,
            "profile8_pass": profile8_pass,
            "CFRAC_zero_change_check": cfrac_changes,
            "BT_FD_K": bt_fd.tolist(),
            "BT_JVP_K": bt_jvp.tolist(),
            "BT7_tolerance": bt_ratios,
            "target_cost_huber_numerator_plus": cost_plus,
            "target_cost_huber_numerator_minus": cost_minus,
            "target_cost_huber_numerator_FD": cost_fd,
            "target_cost_huber_numerator_JVP": huber_jvp,
            "cost_tolerance": cost_ratio,
            "BTcost8_pass": bt_cost8_pass,
            "native17_pass_target": native17_pass,
            "joint33_pass": joint,
            "recorded_native_summary_matches": bool(native_record_match),
            "recorded_observation_result_matches": bool(obs_record_match),
            "recorded_fixed_support_quality_matches": bool(support_record_match),
            "recorded_profile_coordinate_results_match": profile_record_matches,
            "recorded_CFRAC_change_counts_match": bool(cfrac_record_match),
        })
    joint_any = any(item["joint33_pass"] for item in endpoint_replay)

    vjp_gradient_t = np.asarray(_required(cost_vjp, "gradient_theta_m", "cost_vjp"), dtype=np.float64)
    vjp_gradient_q = np.asarray(_required(cost_vjp, "gradient_qv", "cost_vjp"), dtype=np.float64)
    vjp_direction_t = np.asarray(_required(cost_vjp, "direction_theta_m", "cost_vjp"), dtype=np.float64)
    vjp_direction_q = np.asarray(_required(cost_vjp, "direction_qv", "cost_vjp"), dtype=np.float64)
    if any(x.shape != (BATCH, LEVELS) for x in (vjp_gradient_t, vjp_gradient_q, vjp_direction_t, vjp_direction_q)):
        raise ReplayError("cost VJP full-B gradient/direction shapes are invalid")
    fullb_vjp_dot = math.fsum([float(x) for x in (vjp_gradient_t * vjp_direction_t).ravel()]) + math.fsum([float(x) for x in (vjp_gradient_q * vjp_direction_q).ravel()])
    abi_dot = None
    abi_keys = ("abi_abi_raw_state_cotangent", "abi_abi_raw_state_jvp", "abi_abi_state_vjp", "abi_abi_state_direction", "abi_abi_forcing_vjp", "abi_abi_forcing_direction")
    if all(name in cost_vjp for name in abi_keys):
        abi_lhs = math.fsum(float(x) for x in (cost_vjp[abi_keys[0]] * cost_vjp[abi_keys[1]]).ravel())
        abi_rhs = math.fsum(float(x) for x in (cost_vjp[abi_keys[2]] * cost_vjp[abi_keys[3]]).ravel()) + math.fsum(float(x) for x in (cost_vjp[abi_keys[4]] * cost_vjp[abi_keys[5]]).ravel())
        abi_dot = {"lhs": abi_lhs, "rhs": abi_rhs, "abs_error": abs(abi_lhs - abi_rhs)}

    recorded_arithmetic_match = bool(all(arithmetic_matches))
    return {
        "schema": "kdm6.block22_activation_fd_replay.v1",
        "manifest_name": path.name,
        "manifest_sha256": sha256(raw_manifest),
        "control_zero_history": control_zero_summary,
        "pack_files": {"roles": role_meta, "endpoints": [
            {"epsilon": eps, "sign": sign, **endpoint_meta[(eps, sign)]}
            for eps, sign in sorted(endpoint_meta, key=lambda pair: (-pair[0], -pair[1]))
        ]},
        "mode_noninterference": {
            "array_count": len(mode_equal),
            "all_98_arrays_bitwise_equal_across_control_off_on": bool(all(mode_equal.values())),
            "failed_arrays": [name for name, equal in mode_equal.items() if not equal],
        },
        "accepted_fullB_direction": direction_match,
        "K_times_profile_JVP": {
            "BT_JVP_K": bt_jvp.tolist(),
            "Huber_seed_directional_numerator": huber_jvp,
            "saved_seed_directional_numerator": expected_huber_jvp,
            "matches_saved_seed": bool(math.isclose(huber_jvp, expected_huber_jvp, rel_tol=1e-13, abs_tol=1e-11)),
        },
        "cost_VJP_dots": {"fullB_gradient_dot_actual_direction": fullb_vjp_dot, "ABI_raw_dot": abi_dot},
        "per_epsilon": endpoint_replay,
        "common_fixed_input_scope": {
            "input_bundle_role_sha256": role_meta["input_bundle"]["sha256"],
            "PH_and_MU": "fixed source-bound common inputs; not separately saved in each endpoint NPZ",
            "rest": "raw ABI state rows 2:12 checked bitwise at every endpoint",
            "effective_phi_interfaces": "endpoint native_phi_interfaces checked bitwise against source PH+PHB",
        },
        "replay_matches_recorded_arithmetic": recorded_arithmetic_match,
        "experiment_joint33pass": bool(joint_any),
        "joint33_contract": {
            "components": ["native17 target row", "profile8 per-coordinate", "BT7+Huber-cost"],
            "same_epsilon_required": True,
            "profile_coordinatewise_test": True,
            "no_field_maxnorm_substitution_for_profile": True,
        },
        "new_model_calls": {"KDM6": 0, "RTTOV": 0, "host": 0},
        "interpretation_limits": [
            "This is an offline replay of already saved endpoint arithmetic; it executes no model.",
            "Native number coordinates and their units remain conditional; no physical number-unit or whole-budget certification is made.",
            "A passing native/BT subset with a failing profile coordinate still means the joint 33-category experiment fails.",
            "Saved RTTOV endpoint BTs are direct-value observations; no endpoint K is differentiated or rerun here.",
        ],
    }


def _write_new_json(path: Path, report: dict) -> None:
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"output path must be new: {path}")
    encoded = (json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    with path.open("xb") as stream:
        stream.write(encoded)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    # Do not even open the manifest if output would overwrite an artifact.
    if args.output.exists() or args.output.is_symlink():
        raise FileExistsError(f"output path must be new: {args.output}")
    report = replay(args.manifest)
    _write_new_json(args.output, report)
    print(json.dumps({"output": args.output.name, "experiment_joint33pass": report["experiment_joint33pass"], "replay_matches_recorded_arithmetic": report["replay_matches_recorded_arithmetic"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
