"""Fixed-baseline provenance receipt for native KDM number coordinates.

The historical KDM kernel consumes number concentrations in its volume
coordinate. This module records a research coordinate ``N_dry = N_volume /
rho_dry`` once at the saved baseline, without asserting that the archived host
payload originally used that basis. It has no Torch dependency and never
reinterprets perturbed/trial values.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Mapping

import numpy as np

from harness.native_number_boundary import (
    ADMISSION_SCHEMA,
    NUMBER_FIELDS,
    NUMBER_ROWS,
    NUMBER_UNITS,
    NumberBasisAdmission,
)


SCHEMA = "kdm6.native_dry_number_input.v1"
ORIGIN = "derived_kernel_volume_coordinate"
FIELD_UNITS = {name: NUMBER_UNITS for name in NUMBER_FIELDS}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_BINDING_HASHES = ("trace", "namelist", "checkpoint")
_BINDING_VALUES = ("step", "i", "j", "levels", "base_native_X_sha256")

_FIELD_MAP = {
    "NN": {"state_row": 7, "registry_field": "QNCCN", "kernel_units": "number_per_m3", "dry_units": FIELD_UNITS["NN"]},
    "NC": {"state_row": 8, "registry_field": "QNCLOUD", "kernel_units": "number_per_m3", "dry_units": FIELD_UNITS["NC"]},
    "NI": {"state_row": 9, "registry_field": "QNICE", "kernel_units": "number_per_m3", "dry_units": FIELD_UNITS["NI"]},
    "NR": {"state_row": 10, "registry_field": "QNRAIN", "kernel_units": "number_per_m3", "dry_units": FIELD_UNITS["NR"]},
}
_CONVERSION = "N_dry = N_kernel_volume / rho_native_dry"
_RHO_SOURCE = {
    "forcing_row": 0,
    "field": "DEN",
    "units": "kg_dry_air_per_m3",
    "meaning": "saved native dry density supplied by the prep operator",
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _array_sha256(value: np.ndarray) -> str:
    return _sha256_bytes(np.ascontiguousarray(value, dtype="<f8").tobytes())


def _canonical_json(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _content_digest(receipt: Mapping) -> str:
    body = dict(receipt)
    body.pop("receipt_content_sha256", None)
    return _sha256_bytes(_canonical_json(body))


def _validate_bindings(bindings: Mapping, levels: int) -> dict:
    if not isinstance(bindings, Mapping):
        raise TypeError("source_bindings must be a mapping")
    missing = [key for key in (*_BINDING_HASHES, *_BINDING_VALUES) if key not in bindings]
    if missing:
        raise ValueError(f"source_bindings missing required values: {', '.join(missing)}")
    out = dict(bindings)
    for key in _BINDING_HASHES:
        if not isinstance(out[key], str) or not _SHA256.fullmatch(out[key]):
            raise ValueError(f"source_bindings[{key!r}] must be lowercase 64-hex SHA-256")
    if not isinstance(out["base_native_X_sha256"], str) or not _SHA256.fullmatch(out["base_native_X_sha256"]):
        raise ValueError("base_native_X_sha256 must be lowercase 64-hex SHA-256")
    for key in ("step", "i", "j", "levels"):
        value = out[key]
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"source_bindings[{key!r}] must be a positive integer")
    if out["levels"] != levels:
        raise ValueError("source_bindings levels do not match the arrays")
    # Ensure caller metadata is JSON-stable before embedding it in the receipt.
    try:
        json.dumps(out, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise TypeError("source_bindings must contain JSON-compatible finite values") from exc
    return out


def _check_arrays(volume_state, forcing):
    if not isinstance(volume_state, np.ndarray) or volume_state.dtype != np.float64:
        raise TypeError("volume_state must be a float64 ndarray")
    if volume_state.ndim != 2 or volume_state.shape[0] != 12 or volume_state.shape[1] <= 0:
        raise ValueError("volume_state must have shape (12, L), L > 0")
    levels = volume_state.shape[1]
    if not isinstance(forcing, np.ndarray) or forcing.dtype != np.float64:
        raise TypeError("forcing must be a float64 ndarray")
    if forcing.shape != (4, levels):
        raise ValueError(f"forcing must have shape (4, {levels})")
    if not np.isfinite(volume_state).all() or not np.isfinite(forcing).all():
        raise ValueError("volume_state and forcing must be finite")
    # K's state preserves TH at row 0. The first forcing row is native dry DEN.
    rho = forcing[0]
    if np.any(rho <= 0.0):
        raise ValueError("forcing row 0 native dry DEN must be positive")
    if np.any(volume_state[list(NUMBER_ROWS)] < 0.0):
        raise ValueError("kernel volume number operands NN/NC/NI/NR must be nonnegative")
    return levels, rho


def _dry_state(volume_state, rho):
    result = np.ascontiguousarray(volume_state.copy())
    result[list(NUMBER_ROWS)] /= rho[None, :]
    if not np.isfinite(result).all():
        raise ValueError("volume-to-dry number conversion produced nonfinite values")
    return result


def _ulp_distance_nonnegative(a, b):
    # All admitted number operands are nonnegative finite binary64 values, so
    # their unsigned IEEE-754 encodings have the same order as numeric values.
    ai = np.ascontiguousarray(a, dtype=np.float64).view(np.uint64)
    bi = np.ascontiguousarray(b, dtype=np.float64).view(np.uint64)
    return np.abs(ai.astype(object) - bi.astype(object))


def _roundtrip_metrics(volume_state, dry_state, rho):
    back = dry_state[list(NUMBER_ROWS)] * rho[None, :]
    original = volume_state[list(NUMBER_ROWS)]
    metrics = {}
    for offset, name in enumerate(NUMBER_FIELDS):
        errors = _ulp_distance_nonnegative(back[offset], original[offset])
        max_ulp = int(max(errors.flat))
        max_abs = float(np.max(np.abs(back[offset] - original[offset])))
        metrics[name] = {"max_abs": max_abs, "max_ulp": max_ulp}
        if max_ulp > 2:
            raise ValueError(f"{name} dry-number conversion roundtrip exceeds 2 ULP ({max_ulp})")
    return metrics


def make_kernel_coordinate_receipt(
    volume_state: np.ndarray,
    forcing: np.ndarray,
    *,
    source_id: str,
    source_sha256: str,
    source_bindings: Mapping[str, object],
) -> dict:
    """Create a reproducible, fixed-base ``N_volume/rho_dry`` receipt.

    ``volume_state`` is the unchanged verifier 12-row K state (TH, QV, QC,
    QR, QI, QS, QG, NN, NC, NI, NR, BG). Rows 7--10 are the kernel's volume
    operands NN/NC/NI/NR. The first row of the unchanged four-row K forcing
    is native dry DEN (kg dry air m-3) and supplies rho. Registry's BG/QIB
    volume-per-mass row is row 11 and is never converted.
    """
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError("source_id is required")
    if not isinstance(source_sha256, str) or not _SHA256.fullmatch(source_sha256):
        raise ValueError("source_sha256 must be lowercase 64-hex SHA-256")
    levels, rho = _check_arrays(volume_state, forcing)
    bindings = _validate_bindings(source_bindings, levels)
    if source_sha256 != bindings["trace"]:
        raise ValueError("derived-coordinate source_sha256 must identify the pinned trace")
    dry = _dry_state(volume_state, rho)
    roundtrip = _roundtrip_metrics(volume_state, dry, rho)
    receipt = {
        "schema": SCHEMA,
        "origin": ORIGIN,
        "source_id": source_id,
        "source_sha256": source_sha256,
        "source_basis": "kernel_volume_operand",
        "original_host_payload_basis": "unknown_not_migrated",
        "original_host_basis_certified": False,
        "field_map": copy.deepcopy(_FIELD_MAP),
        "conversion": _CONVERSION,
        "rho_source": copy.deepcopy(_RHO_SOURCE),
        "source_bindings": bindings,
        "levels": levels,
        "base_volume_state_sha256": _array_sha256(volume_state),
        "base_forcing_sha256": _array_sha256(forcing),
        "base_rho_native_dry": rho.tolist(),
        "base_volume_state": volume_state.tolist(),
        "base_forcing": forcing.tolist(),
        "base_dry_state": dry.tolist(),
        "roundtrip_volume_coordinate": roundtrip,
        "roundtrip_limit_ulp": 2,
    }
    receipt["receipt_content_sha256"] = _content_digest(receipt)
    return receipt


def apply_receipt(
    receipt: Mapping,
    volume_state: np.ndarray,
    forcing: np.ndarray,
    source_bindings: Mapping[str, object],
    receipt_sha256: str,
) -> tuple[np.ndarray, NumberBasisAdmission]:
    """Validate and apply a receipt only to its exact saved baseline arrays."""
    if not isinstance(receipt, Mapping):
        raise TypeError("receipt must be a mapping")
    if receipt.get("schema") != SCHEMA or receipt.get("origin") != ORIGIN:
        raise ValueError("unsupported number-coordinate receipt schema or origin")
    if receipt.get("source_basis") != "kernel_volume_operand":
        raise ValueError("receipt source basis is not a kernel volume operand")
    if receipt.get("field_map") != _FIELD_MAP:
        raise ValueError("receipt NN/NC/NI/NR field map or units are invalid")
    if receipt.get("conversion") != _CONVERSION or receipt.get("rho_source") != _RHO_SOURCE:
        raise ValueError("receipt density source or conversion contract is invalid")
    if receipt.get("roundtrip_limit_ulp") != 2:
        raise ValueError("receipt roundtrip ULP limit must be exactly 2")
    if receipt.get("original_host_payload_basis") != "unknown_not_migrated" or receipt.get("original_host_basis_certified") is not False:
        raise ValueError("receipt must not claim the original host payload basis is certified")
    if not isinstance(receipt_sha256, str) or not _SHA256.fullmatch(receipt_sha256):
        raise ValueError("receipt_sha256 must be lowercase 64-hex SHA-256")
    source_id, source_sha256 = receipt.get("source_id"), receipt.get("source_sha256")
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError("receipt source_id is required")
    if not isinstance(source_sha256, str) or not _SHA256.fullmatch(source_sha256):
        raise ValueError("receipt source_sha256 must be lowercase 64-hex SHA-256")
    if receipt.get("receipt_content_sha256") != _content_digest(receipt):
        raise ValueError("receipt content digest mismatch")

    levels, rho = _check_arrays(volume_state, forcing)
    bindings = _validate_bindings(source_bindings, levels)
    if source_sha256 != bindings["trace"]:
        raise ValueError("receipt source_sha256 does not identify the pinned trace")
    if receipt.get("source_bindings") != bindings:
        raise ValueError("receipt source bindings differ from the caller's pinned inputs")
    if receipt.get("levels") != levels:
        raise ValueError("receipt levels do not match the arrays")
    if receipt.get("base_volume_state_sha256") != _array_sha256(volume_state):
        raise ValueError("volume_state does not match the receipt's fixed baseline")
    if receipt.get("base_forcing_sha256") != _array_sha256(forcing):
        raise ValueError("forcing does not match the receipt's fixed baseline")
    if receipt.get("base_volume_state") != volume_state.tolist() or receipt.get("base_forcing") != forcing.tolist():
        raise ValueError("receipt baseline arrays do not match exactly")
    if receipt.get("base_rho_native_dry") != rho.tolist():
        raise ValueError("receipt native dry density does not match exactly")

    dry = _dry_state(volume_state, rho)
    roundtrip = _roundtrip_metrics(volume_state, dry, rho)
    if receipt.get("roundtrip_volume_coordinate") != roundtrip:
        raise ValueError("receipt roundtrip metrics differ from the fixed baseline recomputation")
    if receipt.get("base_dry_state") != dry.tolist():
        raise ValueError("receipt fixed dry-number coordinate differs from recomputation")
    admission = NumberBasisAdmission(
        ADMISSION_SCHEMA, ORIGIN, source_id, source_sha256, receipt_sha256, FIELD_UNITS
    )
    return dry, admission
