"""Decompose saved native-observation profile-K tangent contributions.

This offline reader uses saved result JSON only. It does not load a library,
call KDM/RTTOV, or reconstruct cfrac. Each K*tangent product is rounded to
binary64 before its profile-level reduction with ``math.fsum``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np


DEFAULT_CANDIDATE = Path(
    "harness/evidence/actual_qr_transport_2026-10-24/observation_result.json"
)
DEFAULT_REFERENCE = Path(
    "harness/evidence/norm_actual_observation_2026-10-24/native13188_cost.json"
)
DEFAULT_REFERENCE_PREPARED = Path(
    "harness/evidence/norm_actual_observation_2026-10-24/prepared.json"
)
REFERENCE_EXECUTION_MANIFEST = Path(
    "harness/evidence/norm_actual_observation_2026-10-24/manifest.json"
)
REFERENCE_CONTROLLER_SNAPSHOT = Path(
    "harness/evidence/norm_actual_observation_2026-10-24/execution_sources/final_coupling.py.txt"
)
CHANNELS = (10, 11, 12, 13, 14, 15, 16)
DIRECTIONS = ("theta_m", "qv", "mixed")
PROFILE_COMPONENTS = (
    "T",
    "Q",
    "P",
    "P_HALF",
    "HYDRO6",
    "HYDRO_DEFF6",
    "HYDRO7",
    "HYDRO_DEFF7",
)
GROUP_COMPONENTS = {
    "temperature": ("T",),
    "water_vapour": ("Q",),
    "pressure_center": ("P",),
    "pressure_half": ("P_HALF",),
    "direct_pressure_K_total": ("P", "P_HALF"),
    "liquid_mass_HYDRO6": ("HYDRO6",),
    "liquid_size_DEFF6": ("HYDRO_DEFF6",),
    "liquid_total": ("HYDRO6", "HYDRO_DEFF6"),
    "ice_mass_HYDRO7": ("HYDRO7",),
    "ice_size_DEFF7": ("HYDRO_DEFF7",),
    "ice_total": ("HYDRO7", "HYDRO_DEFF7"),
}
ARITHMETIC_ENVELOPE_ULPS = 2048


class AttributionError(ValueError):
    """A saved result does not satisfy the profile-attribution contract."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _finite_array(value, name, *, ndim=None):
    array = np.asarray(value, dtype=np.float64)
    if not array.size or (ndim is not None and array.ndim != ndim):
        raise AttributionError(f"{name} must be a nonempty rank-{ndim} array")
    if not np.isfinite(array).all():
        raise AttributionError(f"{name} must be finite")
    return array


def _require_keys(mapping, required, name):
    if not isinstance(mapping, dict):
        raise AttributionError(f"{name} must be a mapping")
    missing = sorted(set(required) - set(mapping))
    if missing:
        raise AttributionError(f"{name} is missing required keys: {missing}")


def _huber_cost_seed(bt, observation, mask, *, sigma=1.0, delta=1.0):
    residual = (bt - observation) / sigma
    return mask * (np.clip(residual, -delta, delta) / sigma)


def _validate_result(result, label):
    _require_keys(
        result,
        (
            "profile",
            "profile_K",
            "cost_BT_seed",
            "direction_checks",
            "BT_KMA",
            "cost",
            "observation_BT_KMA",
            "quality",
            "mask",
            "geometry",
            "surface",
        ),
        label,
    )
    _require_keys(result["profile"], PROFILE_COMPONENTS, f"{label}.profile")
    _require_keys(result["profile_K"], PROFILE_COMPONENTS, f"{label}.profile_K")
    _require_keys(result["direction_checks"], DIRECTIONS, f"{label}.direction_checks")
    profile = {
        key: _finite_array(result["profile"][key], f"{label}.profile.{key}", ndim=1)
        for key in PROFILE_COMPONENTS
    }
    levels = profile["T"].size
    if any(
        profile[key].size != levels
        for key in (
            "Q",
            "P",
            "HYDRO6",
            "HYDRO_DEFF6",
            "HYDRO7",
            "HYDRO_DEFF7",
        )
    ):
        raise AttributionError(f"{label} layer profiles do not share one layer grid")
    if profile["P_HALF"].size != levels + 1:
        raise AttributionError(f"{label}.profile.P_HALF must have L+1 interfaces")

    cost_seed = _finite_array(result["cost_BT_seed"], f"{label}.cost_BT_seed")
    stored_bt = _finite_array(result["BT_KMA"], f"{label}.BT_KMA")
    if cost_seed.shape != (1, len(CHANNELS)) or stored_bt.shape != cost_seed.shape:
        raise AttributionError(
            f"{label} BT and cost seed must be shape (1,{len(CHANNELS)})"
        )
    observation = _finite_array(
        result["observation_BT_KMA"], f"{label}.observation_BT_KMA"
    )
    quality = _finite_array(result["quality"], f"{label}.quality")
    mask = _finite_array(result["mask"], f"{label}.mask")
    if (
        observation.shape != cost_seed.shape
        or quality.shape != cost_seed.shape
        or mask.shape != cost_seed.shape
    ):
        raise AttributionError(
            f"{label} observed BT/quality/mask grids differ from channel cost seed"
        )
    if not isinstance(result["geometry"], dict) or not isinstance(
        result["surface"], dict
    ):
        raise AttributionError(
            f"{label} geometry and surface metadata must be mappings"
        )
    expected_seed = _huber_cost_seed(stored_bt, observation, mask)
    if (
        expected_seed.shape != cost_seed.shape
        or expected_seed.tobytes() != cost_seed.tobytes()
    ):
        raise AttributionError(
            f"{label} cost_BT_seed differs from its own saved BT/observation/mask Huber contract"
        )
    native_levels = result.get("experiment", {}).get("levels", result.get("L", 39))
    if type(native_levels) is not int or native_levels <= 0:
        raise AttributionError(f"{label} native level metadata is invalid")

    kernels = {}
    for key in PROFILE_COMPONENTS:
        kernel = _finite_array(
            result["profile_K"][key], f"{label}.profile_K.{key}", ndim=3
        )
        expected = (1, len(CHANNELS), profile[key].size)
        if kernel.shape != expected:
            raise AttributionError(
                f"{label}.profile_K.{key} must have shape {expected}; got {kernel.shape}"
            )
        kernels[key] = kernel[0]

    directions = {}
    for name in DIRECTIONS:
        item = result["direction_checks"][name]
        _require_keys(
            item,
            (
                "profile_tangent",
                "BT_JVP",
                "cost_directional_derivative",
                "dot_lhs",
                "dot_rhs",
            ),
            f"{label}.direction_checks.{name}",
        )
        _require_keys(
            item["profile_tangent"],
            PROFILE_COMPONENTS,
            f"{label}.direction_checks.{name}.profile_tangent",
        )
        tangents = {}
        for key in PROFILE_COMPONENTS:
            tangent = _finite_array(
                item["profile_tangent"][key],
                f"{label}.{name}.profile_tangent.{key}",
                ndim=1,
            )
            if tangent.shape != profile[key].shape:
                raise AttributionError(f"{label}.{name} tangent grid differs for {key}")
            tangents[key] = tangent
        bt_jvp = _finite_array(item["BT_JVP"], f"{label}.{name}.BT_JVP")
        if bt_jvp.shape != cost_seed.shape:
            raise AttributionError(f"{label}.{name}.BT_JVP shape differs from channels")
        scalars = {}
        for key in ("cost_directional_derivative", "dot_lhs", "dot_rhs"):
            value = float(item[key])
            if not math.isfinite(value):
                raise AttributionError(f"{label}.{name}.{key} must be finite")
            scalars[key] = value
        direction_x = None
        if "direction_x" in item:
            direction_x = _finite_array(
                item["direction_x"], f"{label}.{name}.direction_x", ndim=1
            )
            if direction_x.shape != (3 * native_levels + 2,):
                raise AttributionError(
                    f"{label}.{name}.direction_x shape differs from native control vector"
                )
        rest_direction = None
        if "rest_direction" in item:
            rest_direction = _finite_array(
                item["rest_direction"], f"{label}.{name}.rest_direction", ndim=2
            )
            if rest_direction.shape != (10, native_levels):
                raise AttributionError(
                    f"{label}.{name}.rest_direction shape differs from rest controls"
                )
        directions[name] = {
            "tangents": tangents,
            "stored_bt_jvp": bt_jvp.reshape(-1),
            "direction_x": direction_x,
            "rest_direction": rest_direction,
            **scalars,
        }
    cost = float(result["cost"])
    if not math.isfinite(cost):
        raise AttributionError(f"{label}.cost must be finite")
    return {
        "levels": levels,
        "profile": profile,
        "kernels": kernels,
        "cost_seed": cost_seed.reshape(-1),
        "cost_seed_expected": expected_seed.reshape(-1),
        "cost_seed_matches_own_huber": True,
        "observation_bt": observation.reshape(-1),
        "quality": quality.reshape(-1),
        "mask": mask.reshape(-1),
        "geometry": result["geometry"],
        "surface": result["surface"],
        "stored_bt": stored_bt.reshape(-1),
        "cost": cost,
        "directions": directions,
    }


def _rounded_products(kernel, tangent):
    """Materialize rounded binary64 products before any accurate summation."""
    return [float(np.float64(k) * np.float64(d)) for k, d in zip(kernel, tangent)]


def _sum_fields_by_channel(field_values, keys):
    channels = len(CHANNELS)
    return np.fromiter(
        (
            math.fsum(float(field_values[key][channel]) for key in keys)
            for channel in range(channels)
        ),
        dtype=np.float64,
        count=channels,
    )


def decompose_direction(result, direction, *, label="result"):
    """Compute eight component contributions and liquid/ice aggregates."""
    validated = _validate_result(result, label)
    if direction not in validated["directions"]:
        raise AttributionError(f"{label} lacks direction {direction!r}")
    item = validated["directions"][direction]
    field_bt = {}
    abs_product_terms = [[] for _ in CHANNELS]
    for key in PROFILE_COMPONENTS:
        values = np.empty(len(CHANNELS), dtype=np.float64)
        for channel in range(len(CHANNELS)):
            products = _rounded_products(
                validated["kernels"][key][channel], item["tangents"][key]
            )
            values[channel] = math.fsum(products)
            abs_product_terms[channel].extend(abs(value) for value in products)
        field_bt[key] = values

    abs_products = np.fromiter(
        (math.fsum(terms) for terms in abs_product_terms),
        dtype=np.float64,
        count=len(CHANNELS),
    )

    group_bt = {
        group: _sum_fields_by_channel(field_bt, keys)
        for group, keys in GROUP_COMPONENTS.items()
    }
    reconstructed_bt = _sum_fields_by_channel(field_bt, PROFILE_COMPONENTS)
    bt_gate = (
        ARITHMETIC_ENVELOPE_ULPS
        * np.finfo(np.float64).eps
        * np.maximum(1.0, abs_products)
    )
    bt_error = np.abs(reconstructed_bt - item["stored_bt_jvp"])

    seed = validated["cost_seed"]
    field_cost = {
        key: np.fromiter(
            (
                float(np.float64(seed[c]) * np.float64(field_bt[key][c]))
                for c in range(len(CHANNELS))
            ),
            dtype=np.float64,
            count=len(CHANNELS),
        )
        for key in PROFILE_COMPONENTS
    }
    group_cost = {
        group: _sum_fields_by_channel(field_cost, keys)
        for group, keys in GROUP_COMPONENTS.items()
    }
    cost_by_channel = _sum_fields_by_channel(field_cost, PROFILE_COMPONENTS)
    reconstructed_cost = math.fsum(float(value) for value in cost_by_channel)
    abs_cost_products = math.fsum(
        abs(float(np.float64(seed[channel]) * np.float64(field_bt[key][channel])))
        for channel in range(len(CHANNELS))
        for key in PROFILE_COMPONENTS
    )
    cost_gate = (
        ARITHMETIC_ENVELOPE_ULPS
        * np.finfo(np.float64).eps
        * max(1.0, abs_cost_products)
    )
    stored_dots = {
        "cost_directional_derivative": item["cost_directional_derivative"],
        "dot_lhs": item["dot_lhs"],
        "dot_rhs": item["dot_rhs"],
    }
    cost_errors = {
        key: abs(reconstructed_cost - value) for key, value in stored_dots.items()
    }
    checks = {
        "bt_matches_stored_by_channel": bool(np.all(bt_error <= bt_gate)),
        "cost_matches_stored_dot": all(
            value <= cost_gate for value in cost_errors.values()
        ),
    }
    return {
        "direction": direction,
        "channels": list(CHANNELS),
        "profile_layers": validated["levels"],
        "profile_component_bt_jvp_by_channel_K": {
            key: value.tolist() for key, value in field_bt.items()
        },
        "profile_group_bt_jvp_by_channel_K": {
            key: value.tolist() for key, value in group_bt.items()
        },
        "reconstructed_bt_jvp_by_channel_K": reconstructed_bt.tolist(),
        "stored_bt_jvp_by_channel_K": item["stored_bt_jvp"].tolist(),
        "cost_seed_by_channel": seed.tolist(),
        "profile_component_cost_by_channel": {
            key: value.tolist() for key, value in field_cost.items()
        },
        "profile_group_cost_by_channel": {
            key: value.tolist() for key, value in group_cost.items()
        },
        "cost_contribution_by_channel": cost_by_channel.tolist(),
        "reconstructed_cost_derivative": reconstructed_cost,
        "stored_cost_derivatives": stored_dots,
        "arithmetic_envelope": {
            "rule": "rounded binary64 K*tangent and seed*contribution products, then math.fsum",
            "ulps_multiplier": ARITHMETIC_ENVELOPE_ULPS,
            "unit_roundoff": float(np.finfo(np.float64).eps),
            "bt_gate_by_channel_K": bt_gate.tolist(),
            "bt_abs_error_by_channel_K": bt_error.tolist(),
            "cost_gate": cost_gate,
            "cost_abs_error_by_stored_dot": cost_errors,
            **checks,
        },
    }


def _validate_target(candidate, reference):
    target = candidate.get("target", {})
    if (
        target.get("i_1based"),
        target.get("j_1based"),
        target.get("flat_index0"),
        target.get("batch_index0"),
        target.get("row_in_batch0"),
    ) != (131, 88, 20488, 40, 8):
        raise AttributionError(
            "candidate is not the admitted native (131,88), chunk40,row8 target"
        )
    if (
        reference.get("i"),
        reference.get("j"),
        reference.get("flat_index"),
        reference.get("chunk"),
        reference.get("local_row"),
        reference.get("B"),
        reference.get("L"),
    ) != (131, 88, 20488, 40, 8, 512, 39):
        raise AttributionError(
            "reference does not match the same native target and B512 block"
        )
    experiment = candidate.get("experiment", {})
    if (
        experiment.get("factorial_mode") != "norm_actual"
        or experiment.get("qr_transport") != "actual_departure"
        or experiment.get("batch_columns") != 512
        or experiment.get("levels") != 39
    ):
        raise AttributionError(
            "candidate mode/QR-transport metadata differs from expected actual candidate"
        )


def _json_equal(left, right):
    left_text = json.dumps(left, sort_keys=True, allow_nan=False, separators=(",", ":"))
    right_text = json.dumps(
        right, sort_keys=True, allow_nan=False, separators=(",", ":")
    )
    return left_text == right_text


def _validate_comparison_contract(candidate_valid, reference_valid):
    for key in ("observation_bt", "quality", "mask"):
        current = candidate_valid[key]
        prior = reference_valid[key]
        if current.shape != prior.shape or current.tobytes() != prior.tobytes():
            raise AttributionError(f"candidate/reference {key} arrays differ")
    for key in ("geometry", "surface"):
        if not _json_equal(candidate_valid[key], reference_valid[key]):
            raise AttributionError(f"candidate/reference {key} metadata differ")
    direction_equal = {}
    for name in DIRECTIONS:
        current = candidate_valid["directions"][name]
        prior = reference_valid["directions"][name]
        if current["direction_x"] is None or prior["direction_x"] is None:
            raise AttributionError(
                f"{name} direction_x must be serialized in both results"
            )
        if current["direction_x"].tobytes() != prior["direction_x"].tobytes():
            raise AttributionError(
                f"candidate/reference {name} input directions differ"
            )
        rest = current["rest_direction"]
        if rest is None or np.any(rest != 0.0):
            raise AttributionError(
                f"candidate {name} rest_direction must be serialized as zero"
            )
        prior_rest = prior["rest_direction"]
        if prior_rest is not None and rest.tobytes() != prior_rest.tobytes():
            raise AttributionError(f"candidate/reference {name} rest directions differ")
        direction_equal[name] = True
    return {
        "observation_bt_bit_equal": True,
        "quality_bit_equal": True,
        "mask_bit_equal": True,
        "geometry_json_equal": True,
        "surface_json_equal": True,
        "direction_x_bit_equal_by_direction": direction_equal,
        "candidate_rest_direction_zero_by_direction": True,
        "reference_rest_direction_serialized_by_direction": {
            name: reference_valid["directions"][name]["rest_direction"] is not None
            for name in DIRECTIONS
        },
    }


def _reference_rest_source_contract(prepared_data):
    source_hashes = prepared_data.get("source_sha256", {})
    matches = [
        (path, digest)
        for path, digest in source_hashes.items()
        if path.endswith("/v4_final/pilot.py")
    ]
    if len(matches) != 1:
        raise AttributionError(
            "reference prepared metadata must pin its v4_final/pilot.py"
        )
    archived_path, expected_hash = matches[0]
    repo_root = Path(__file__).resolve().parents[1]
    manifest_path = repo_root / REFERENCE_EXECUTION_MANIFEST
    controller_path = repo_root / REFERENCE_CONTROLLER_SNAPSHOT
    try:
        manifest = json.loads(manifest_path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise AttributionError(
            "public reference execution manifest is unavailable"
        ) from exc
    if manifest.get("final_controller_sha256") != expected_hash:
        raise AttributionError(
            "public manifest controller hash differs from prepared source pin"
        )
    if (
        not controller_path.is_file()
        or sha256_bytes(controller_path.read_bytes()) != expected_hash
    ):
        raise AttributionError(
            "public archived reference controller does not match its saved pin"
        )
    source_text = controller_path.read_text()
    if (
        "dr=np.zeros_like(rest)" not in source_text
        and "dr = np.zeros_like(rest)" not in source_text
    ):
        raise AttributionError(
            "pinned reference controller does not establish a zero rest direction"
        )
    return {
        "path": str(REFERENCE_CONTROLLER_SNAPSHOT),
        "archived_execution_path": archived_path,
        "sha256": expected_hash,
        "verified_statement": "dr=np.zeros_like(rest)",
        "saved_reference_rest_direction_array": False,
    }


def analyze(candidate_path, reference_path, output_path, *, reference_prepared=None):
    candidate_path = Path(candidate_path)
    reference_path = Path(reference_path)
    output_path = Path(output_path)
    if output_path.exists() or output_path.is_symlink():
        raise FileExistsError(f"output must be a new file: {output_path}")
    if output_path.resolve() in (candidate_path.resolve(), reference_path.resolve()):
        raise ValueError("output must not overwrite an input result")
    candidate_bytes, reference_bytes = (
        candidate_path.read_bytes(),
        reference_path.read_bytes(),
    )
    candidate, reference = json.loads(candidate_bytes), json.loads(reference_bytes)
    _validate_target(candidate, reference)
    candidate_valid = _validate_result(candidate, "candidate")
    reference_valid = _validate_result(reference, "reference")
    if candidate_valid["levels"] != reference_valid["levels"]:
        raise AttributionError("candidate/reference RTTOV profile grids differ")
    comparison_contract = _validate_comparison_contract(
        candidate_valid, reference_valid
    )

    reference_prepared_data = None
    reference_prepared_digest = None
    if reference_prepared is not None:
        ref_prepared_path = Path(reference_prepared)
        prepared_bytes = ref_prepared_path.read_bytes()
        reference_prepared_data = json.loads(prepared_bytes)
        reference_prepared_digest = sha256_bytes(prepared_bytes)
        _require_keys(
            reference_prepared_data,
            ("source_sha256", "native_targets"),
            "reference prepared metadata",
        )
        if (
            reference_prepared_data.get("mode") != "norm_actual"
            or reference_prepared_data.get("B") != 512
            or reference_prepared_data.get("L") != 39
            or [131, 88] not in reference_prepared_data.get("native_targets", [])
        ):
            raise AttributionError(
                "reference prepared metadata does not admit norm_actual B512/L39 target (131,88)"
            )
        reference_rest_contract = _reference_rest_source_contract(
            reference_prepared_data
        )
    else:
        reference_rest_contract = None

    directions = {}
    arithmetic_checks_passed = True
    for name in DIRECTIONS:
        current = decompose_direction(candidate, name, label="candidate")
        prior = decompose_direction(reference, name, label="reference")
        current_checks = current["arithmetic_envelope"]
        prior_checks = prior["arithmetic_envelope"]
        if not (
            current_checks["bt_matches_stored_by_channel"]
            and current_checks["cost_matches_stored_dot"]
            and prior_checks["bt_matches_stored_by_channel"]
            and prior_checks["cost_matches_stored_dot"]
        ):
            arithmetic_checks_passed = False
        component_delta = {
            key: [
                float(a - b)
                for a, b in zip(
                    current["profile_component_bt_jvp_by_channel_K"][key],
                    prior["profile_component_bt_jvp_by_channel_K"][key],
                )
            ]
            for key in PROFILE_COMPONENTS
        }
        group_delta = {
            key: [
                float(a - b)
                for a, b in zip(
                    current["profile_group_bt_jvp_by_channel_K"][key],
                    prior["profile_group_bt_jvp_by_channel_K"][key],
                )
            ]
            for key in GROUP_COMPONENTS
        }
        directions[name] = {
            "candidate": current,
            "reference": prior,
            "candidate_minus_reference_profile_component_bt_jvp_by_channel_K": component_delta,
            "candidate_minus_reference_profile_group_bt_jvp_by_channel_K": group_delta,
            "candidate_minus_reference_cost_derivative": float(
                current["reconstructed_cost_derivative"]
                - prior["reconstructed_cost_derivative"]
            ),
        }

    result = {
        "schema": "kdm6.saved_profile_k_directional_contribution_analysis.v1",
        "candidate_source": {
            "path": str(candidate_path.resolve()),
            "sha256": sha256_bytes(candidate_bytes),
            "library": candidate.get("library", {}),
            "source_sha256": candidate.get("source_sha256", {}),
        },
        "reference_source": {
            "path": str(reference_path.resolve()),
            "sha256": sha256_bytes(reference_bytes),
            "prepared_metadata_path": (
                str(Path(reference_prepared).resolve())
                if reference_prepared is not None
                else None
            ),
            "prepared_metadata_sha256": reference_prepared_digest,
            "source_sha256": (
                reference_prepared_data.get("source_sha256", {})
                if reference_prepared_data is not None
                else {}
            ),
            "mode": (
                reference_prepared_data.get("mode")
                if reference_prepared_data is not None
                else "norm_actual"
            ),
            "qr_transport": "not recorded in the earlier norm_actual result; do not treat this as a paired actual-QR experiment",
        },
        "target": candidate["target"],
        "channels": list(CHANNELS),
        "profile_grid": {
            "layer_count": candidate_valid["levels"],
            "layer_fields": [
                "T",
                "Q",
                "P",
                "HYDRO6",
                "HYDRO_DEFF6",
                "HYDRO7",
                "HYDRO_DEFF7",
            ],
            "interface_field": "P_HALF",
            "profile_order": "the saved RTTOV/K profile order; no reordering or interpolation",
        },
        "component_units": {
            "T": "K",
            "Q": "ppmv moist air",
            "P": "hPa layer-center pressure",
            "P_HALF": "hPa interface pressure",
            "HYDRO6": "g m-3 liquid cloud content",
            "HYDRO_DEFF6": "micrometers liquid effective diameter",
            "HYDRO7": "g m-3 ice cloud content",
            "HYDRO_DEFF7": "micrometers ice effective diameter",
            "BT_contribution": "K per channel",
            "cost_contribution": "saved Huber-cost units per channel",
        },
        "method": "For each channel and saved direction, form every binary64 K[field,channel,level]*profile_tangent[field,level] product, reduce levels by math.fsum, then multiply by the saved channel cost_BT_seed and fsum across channels. Report all eight fields and liquid/ice aggregates; mass and size terms remain separate.",
        "interpretation": "These are an algebraic split of the validated stored profile-space JVP. P/P_HALF contributions are the direct pressure-K terms only; pressure-mediated Exner/temperature and moving-grid Q/cloud effects remain in their respective profile-field terms. Groups are not independent native controls or per-field finite-difference certificates.",
        "arithmetic_envelope": {
            "ulps_multiplier": ARITHMETIC_ENVELOPE_ULPS,
            "unit_roundoff": float(np.finfo(np.float64).eps),
            "bt_and_dot_totals_match_saved_results": arithmetic_checks_passed,
        },
        "candidate_reference_baseline_comparison": {
            "candidate_cost": candidate_valid["cost"],
            "reference_cost": reference_valid["cost"],
            "candidate_minus_reference_cost": float(
                candidate_valid["cost"] - reference_valid["cost"]
            ),
            "cost_seed_bit_equal": bool(
                candidate_valid["cost_seed"].tobytes()
                == reference_valid["cost_seed"].tobytes()
            ),
            "max_abs_BT_K_delta": float(
                np.max(
                    np.abs(candidate_valid["stored_bt"] - reference_valid["stored_bt"])
                )
            ),
            "interpretation": "near-roundoff baseline difference is not a fit-gain claim",
        },
        "input_comparison_contract": comparison_contract,
        "reference_rest_direction_contract": reference_rest_contract,
        "directions": directions,
        "limits": [
            "K×tangent terms decompose saved profile-coordinate first-order products, not KDM state rows or named physical processes.",
            "CFRAC is a non-differentiable RTTOV passthrough and has no stored profile_K; the old result also omitted old endpoint CFRAC, so no old/new CFRAC comparison is certified.",
            "The prior norm_actual result predates the actual QR-transport selector; candidate/reference contribution differences are not a paired single-formula perturbation attribution.",
            (
                "The prior result did not serialize rest_direction; its pinned controller source establishes zero rest input, while the candidate result serializes and passes an explicit zero array."
                if reference_rest_contract is not None
                else "The prior rest_direction is not serialized and no prepared source contract was supplied; reference rest equality is unverified."
            ),
            "No new KDM, RTTOV, host/RK, HVP, unrestricted-gradient or forecast-skill evidence is produced by this reader.",
        ],
    }
    if not arithmetic_checks_passed:
        raise AttributionError(
            "decomposed BT/dot totals exceed the declared arithmetic envelope"
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-result", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--reference-result", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument(
        "--reference-prepared", type=Path, default=DEFAULT_REFERENCE_PREPARED
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = analyze(
        args.candidate_result,
        args.reference_result,
        args.output,
        reference_prepared=args.reference_prepared,
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "directions": list(result["directions"]),
                "arithmetic_checks_passed": result["arithmetic_envelope"][
                    "bt_and_dot_totals_match_saved_results"
                ],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
