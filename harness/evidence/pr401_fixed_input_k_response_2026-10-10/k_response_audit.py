#!/usr/bin/env python3
"""Audit the saved center runK Jacobian against declared input directions.

This is a metadata/input/output replay helper. It does not launch RTTOV or a
model, read observation pixels, or modify the saved case. It uses the oracle's
production RTTOV ASCII parser and AMI BT/K coordinate transform.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "oracle"))

from kdm6.obs._rttov_reference.rttov_ascii import parse_rttov_ascii_blocks  # noqa: E402
from kdm6.obs.ami_bt_coordinate import (  # noqa: E402
    BT_REPLAY_ATOL_K,
    read_ami_filters,
    read_kma_calibration,
    transform_rttov_to_kma,
)
from kdm6.obs.gk2a_l1b import AMI_CHANNELS  # noqa: E402
from kdm6.obs.rttov_runner import (  # noqa: E402
    parse_rttov_profiles_k,
    parse_rttov_radiance,
)


RESULT = ROOT / "harness/evidence/pr399_vertical_neighbor_2026-10-10/NEIGHBOR_RESULT_attempt2.json"
POSTRUN = ROOT / "harness/evidence/pr399_vertical_neighbor_2026-10-10/NEIGHBOR_POSTRUN_AUDIT_attempt2.json"
FIXED = ROOT / "harness/evidence/pr400_input_compatibility_2026-10-10/FIXED_INPUTS.json"
REF_DIR = Path(
    "/Users/yhlee/AD-RTTOV/external/rttov14/src/"
    "rttov_test/tests.1.gfortran-openmp/ami/cloud/in/profiles/001/atm"
)
PRIVATE_ROOT = Path(
    "/Users/yhlee/KDM6AD-k/host/research_evidence/"
    "pr401_fixed_input_k_response_20261010"
)
PRIVATE_NPZ = PRIVATE_ROOT / "center_86_48_rttov_k_response_v2.npz"
PLAN_PATH = ROOT / "harness/evidence/pr401_fixed_input_k_response_2026-10-10/DIRECTION_PLAN.md"
SOURCE_CONTRACT_RECEIPT = ROOT / "graphify-out/pr401-root/source_contracts.json"
PRODUCTION_SOURCE_CONTRACTS = {
    "rttov_runner": ROOT / "oracle/kdm6/obs/rttov_runner.py",
    "rttov_ascii_parser": ROOT / "oracle/kdm6/obs/_rttov_reference/rttov_ascii.py",
    "ami_bt_coordinate": ROOT / "oracle/kdm6/obs/ami_bt_coordinate.py",
    "rttov_case_writer": ROOT / "oracle/kdm6/obs/rttov_case_writer.py",
    "model_profile_builder": ROOT / "oracle/kdm6/obs/model_profile_builder.py",
    "ami_channel_map": ROOT / "oracle/kdm6/obs/gk2a_l1b.py",
    "k_response_tests": ROOT / "harness/evidence/pr401_fixed_input_k_response_2026-10-10/test_k_response_audit.py",
    "rttov_types_fortran": Path("/Users/yhlee/AD-RTTOV/external/rttov14/src/src/main/rttov_types.F90"),
    "rttov_convert_profile_units_fortran": Path("/Users/yhlee/AD-RTTOV/external/rttov14/src/src/main/rttov_convert_profile_units.F90"),
    "rttov_k_fortran": Path("/Users/yhlee/AD-RTTOV/external/rttov14/src/src/main/rttov_k.F90"),
    "rttov_convert_profile_units_k_fortran": Path("/Users/yhlee/AD-RTTOV/external/rttov14/src/src/main/rttov_convert_profile_units_k.F90"),
    "rttov_test_semantics": Path("/Users/yhlee/AD-RTTOV/external/rttov14/src/rttov_test/rttov_test.pl"),
    "rttov_example_k_semantics": Path("/Users/yhlee/AD-RTTOV/external/rttov14/src/src/test/example_k.F90"),
}
CHANNEL_IDS = tuple(range(10, 17))
CHANNEL_NAMES = tuple(AMI_CHANNELS[c - 1].lower() for c in CHANNEL_IDS)
PLANNED_DIRECTIONS = (
    "skin_T_plus_1K", "reference_o3_plus_1pct", "reference_co2_plus_1pct",
    "near_surface_Q2_plus_1pct", "upper_reference_T_plus_1K",
    "upper_reference_Q_plus_1pct",
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def source_contract_bindings() -> dict:
    """Verify the root's source contract receipt and hash local unit/K sources."""
    if not SOURCE_CONTRACT_RECEIPT.is_file():
        raise FileNotFoundError(f"source contract receipt is missing: {SOURCE_CONTRACT_RECEIPT}")
    receipt = json.loads(SOURCE_CONTRACT_RECEIPT.read_text())
    receipt_files = receipt.get("files")
    if not isinstance(receipt_files, dict) or not receipt_files:
        raise ValueError("source contract receipt has no file hash map")
    bound = {}
    for raw_path, expected in receipt_files.items():
        path = Path(raw_path)
        if not path.is_absolute():
            path = ROOT / path
        actual = sha256(path)
        if actual != expected:
            raise ValueError(f"source contract receipt hash mismatch: {path}")
        bound[raw_path] = {"path": str(path), "sha256": actual,
                           "hash_verified_against": str(SOURCE_CONTRACT_RECEIPT)}
    for name, path in PRODUCTION_SOURCE_CONTRACTS.items():
        if not Path(path).is_file():
            raise FileNotFoundError(f"production source contract missing: {path}")
        bound[name] = {"path": str(path), "sha256": sha256(Path(path))}
    return {
        "receipt_path": str(SOURCE_CONTRACT_RECEIPT),
        "receipt_sha256": sha256(SOURCE_CONTRACT_RECEIPT),
        "receipt_scope": receipt.get("scope"),
        "key_paths": receipt.get("key_paths", []),
        "files": bound,
    }


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def parse_assignments(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    pattern = re.compile(r"^\s*([\w%()]+)\s*=\s*([^!\n]+?)\s*$")
    for line in Path(path).read_text().splitlines():
        match = pattern.match(line)
        if match:
            out[match.group(1).casefold()] = match.group(2).strip().rstrip(",")
    return out


def parse_gas_units(text: str, label: str) -> int:
    match = re.search(r"(?im)^\s*gas_units\s*=\s*(\d+)\s*$", text)
    if match is None or int(match.group(1)) != 2:
        raise ValueError(f"{label} must declare gas_units=2 (ppmv over moist air)")
    return int(match.group(1))


def validate_run_contract(
    channel_values: list[int], channel_names: tuple[str, ...],
    gas_units_text: str, settings: dict[str, str],
) -> int:
    """Validate saved channel order and the executed AD/ppmv input contract."""
    if tuple(channel_values) != CHANNEL_IDS:
        raise ValueError("executed channels.txt is not ordered 10..16")
    if tuple(channel_names) != CHANNEL_NAMES:
        raise ValueError("saved result channel names do not match AMI 10..16 order")
    if settings.get("defn%opts%config%adk_bt", "").casefold() != ".true.":
        raise ValueError("saved RTTOV namelist does not enable adk_bt")
    if settings.get("defn%run_gas_units") != "2":
        raise ValueError("saved RTTOV namelist does not use run_gas_units=2")
    if (settings.get("defn%do_direct", "").casefold() != ".true."
            or settings.get("defn%do_k", "").casefold() != ".true."):
        raise ValueError("saved RTTOV namelist is not a direct+K run")
    if settings.get("defn%opts%rt_all%use_q2m", "").casefold() != ".true.":
        raise ValueError("saved RTTOV namelist does not enable use_q2m")
    return parse_gas_units(gas_units_text, "active gas_units.txt")


def build_log_pressure_interpolation_matrix(
    source_pressure_hpa: np.ndarray, query_pressure_hpa: np.ndarray
) -> np.ndarray:
    """Build rows reproducing numpy.interp(log(query), log(source), values).

    Out-of-range queries hold the first/last source value, exactly the endpoint
    policy used by the saved profile builder.
    """
    source = np.asarray(source_pressure_hpa, dtype=np.float64)
    query = np.asarray(query_pressure_hpa, dtype=np.float64)
    if source.ndim != 1 or query.ndim != 1 or source.size < 2 or query.size == 0:
        raise ValueError("pressure vectors must be nonempty one-dimensional arrays")
    if not np.isfinite(source).all() or not np.isfinite(query).all():
        raise ValueError("pressure vectors must be finite")
    if not (source > 0.0).all() or not (query > 0.0).all():
        raise ValueError("pressure vectors must be positive")
    if not (np.diff(source) > 0.0).all():
        raise ValueError("source pressure must be strictly increasing")

    xs = np.log(source)
    xq = np.log(query)
    matrix = np.zeros((query.size, source.size), dtype=np.float64)
    for row, x in enumerate(xq):
        if x <= xs[0]:
            matrix[row, 0] = 1.0
        elif x >= xs[-1]:
            matrix[row, -1] = 1.0
        else:
            lo = int(np.searchsorted(xs, x, side="right") - 1)
            weight_hi = (x - xs[lo]) / (xs[lo + 1] - xs[lo])
            matrix[row, lo] = 1.0 - weight_hi
            matrix[row, lo + 1] = weight_hi
    return matrix


def contract_reference_k(
    k_active: np.ndarray, interpolation: np.ndarray, beta_reference: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return active delta, direct K·P·beta, and equivalent (K·P)·beta."""
    k = np.asarray(k_active, dtype=np.float64)
    p = np.asarray(interpolation, dtype=np.float64)
    beta = np.asarray(beta_reference, dtype=np.float64)
    if k.ndim != 2 or p.ndim != 2 or beta.ndim != 1:
        raise ValueError("expected K[channel,active], P[active,reference], beta[reference]")
    if k.shape[1] != p.shape[0] or p.shape[1] != beta.size:
        raise ValueError("K/P/beta dimensions do not align")
    if not np.isfinite(k).all() or not np.isfinite(p).all() or not np.isfinite(beta).all():
        raise ValueError("K/P/beta must be finite")
    active_delta = p @ beta
    contracted_active = k @ active_delta
    contracted_source = (k @ p) @ beta
    if not np.allclose(contracted_active, contracted_source, rtol=0.0, atol=2e-12):
        raise ValueError("K·(P beta) does not match (K P)·beta")
    return active_delta, contracted_active, contracted_source


def contract_held_endpoint_k(
    k_active: np.ndarray, interpolation: np.ndarray,
    beta_reference: np.ndarray, held_rows: np.ndarray, endpoint_index: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Sum active sensitivities sharing one held source endpoint and contract it."""
    k = np.asarray(k_active, dtype=np.float64)
    p = np.asarray(interpolation, dtype=np.float64)
    beta = np.asarray(beta_reference, dtype=np.float64)
    held = np.asarray(held_rows, dtype=np.int64)
    if k.ndim != 2 or p.ndim != 2 or beta.ndim != 1:
        raise ValueError("expected K[channel,active], P[active,reference], beta[reference]")
    if k.shape[1] != p.shape[0] or p.shape[1] != beta.size:
        raise ValueError("K/P/beta dimensions do not align")
    if endpoint_index < 0 or endpoint_index >= beta.size or held.ndim != 1 or not held.size:
        raise ValueError("held endpoint index/rows are invalid")
    if np.any((held < 0) | (held >= k.shape[1])):
        raise ValueError("held active row is out of range")
    expected = np.zeros(held.size, dtype=np.float64)
    expected[:] = 1.0
    if not np.array_equal(p[held, endpoint_index], expected):
        raise ValueError("held rows do not map fully to the selected source endpoint")
    other = np.delete(p[held], endpoint_index, axis=1)
    if np.any(other != 0.0):
        raise ValueError("held rows mix other source levels into the endpoint")
    aggregate = np.sum(k[:, held], axis=1)
    contribution = aggregate * beta[endpoint_index]
    # Contract only the fully held rows here. Other active rows can have a
    # partial weight on this same reference endpoint and are reported separately.
    equivalent = (k[:, held] @ p[held, :])[:, endpoint_index] * beta[endpoint_index]
    if not np.allclose(contribution, equivalent, rtol=0.0, atol=2e-12):
        raise ValueError("summed held-level K does not match source endpoint contraction")
    return aggregate, contribution


def huber_loss_and_slope(
    model_bt: np.ndarray,
    observed_bt: np.ndarray,
    sigma: np.ndarray,
    bias: np.ndarray,
    support: np.ndarray,
    delta: float,
) -> tuple[float, np.ndarray, np.ndarray]:
    """Huber J and its channelwise first derivative with respect to model BT."""
    m, y, s, b, mask = (np.asarray(a, dtype=np.float64) for a in
                         (model_bt, observed_bt, sigma, bias, support))
    if any(a.ndim != 1 for a in (m, y, s, b, mask)) or not (
        m.shape == y.shape == s.shape == b.shape == mask.shape
    ):
        raise ValueError("Huber inputs must be aligned channel vectors")
    if not np.isfinite(np.concatenate((m, y, s, b, mask))).all():
        raise ValueError("Huber inputs must be finite")
    if not (s > 0.0).all() or not (mask >= 0.0).all() or delta <= 0.0:
        raise ValueError("Huber sigma/support/delta outside allowed range")
    residual = (m - y - b) / s
    absolute = np.abs(residual)
    loss = np.where(absolute <= delta, 0.5 * residual**2,
                    delta * (absolute - 0.5 * delta))
    slope = mask * np.clip(residual, -delta, delta) / s
    return float(np.sum(mask * loss)), residual, slope


def load_center_inputs() -> dict:
    result = json.loads(RESULT.read_text())
    postrun = json.loads(POSTRUN.read_text())
    fixed = json.loads(FIXED.read_text())
    require(result.get("status") == "ALL_NINE_ROWS_RETURNED", "PR399 result incomplete")
    center_rows = [r for r in result["results"] if int(r["j"]) == 86 and int(r["i"]) == 48]
    require(len(center_rows) == 1, "PR399 result must contain one center row")
    row = center_rows[0]
    require(row["case_role"] == "REUSED_PR398_V2_CENTRAL_H", "center H role changed")
    require(row["case_id"] == "frame1_fixed_AMI_candidate_pixel_center", "unexpected center case")
    require(row["native_time_label"] == "2025-07-19_05:56:00", "unexpected center time")
    require(row["channels_1based"] == list(CHANNEL_IDS), "result channel order changed")
    require(tuple(row["channel_names"]) == CHANNEL_NAMES, "result channel names/order changed")
    require(row["all_seven_rad_quality_zero"], "saved center quality gate failed")
    require(not row["automatic_retry"], "center record indicates automatic retry")

    fixed_row = next(
        c for c in fixed["profile_contract"]["per_cell"]
        if c["cell_j_i"] == [86, 48]
    )
    case_dir = Path(row["case_output_dir"])
    require(case_dir.is_dir(), f"preserved center case is missing: {case_dir}")
    profiles_k_path = case_dir / "out/k/profiles_k.txt"
    radiance_path = case_dir / "out/k/radiance.txt"
    require(sha256(profiles_k_path) == fixed_row["profiles_k"]["sha256"],
            "center profiles_k differs from final fixed-input receipt")
    require(postrun["center_is_exactly_reused_pr398_H"],
            "postrun receipt no longer binds reused center H")

    input_dir = case_dir / "in/profiles/001"
    atm_dir = input_dir / "atm"
    active = {name: np.loadtxt(atm_dir / f"{name}.txt", dtype=np.float64)
              for name in ("p", "p_half", "t", "q", "o3", "co2")}
    for name, record in fixed_row["active_profiles"].items():
        require(sha256(atm_dir / name) == record["sha256"],
                f"center active profile hash changed: {name}")

    ref_half = np.loadtxt(REF_DIR / "p_half.txt", dtype=np.float64)
    p_half_for_full = ref_half.copy()
    p_half_for_full[0] = max(p_half_for_full[0], 1.0e-12)
    ref_pressure = 0.5 * (p_half_for_full[:-1] + p_half_for_full[1:])
    reference = {name: np.loadtxt(REF_DIR / f"{name}.txt", dtype=np.float64)
                 for name in ("t", "q", "o3", "co2")}
    reference_gas_units_path = REF_DIR.parent / "gas_units.txt"
    reference_gas_units = parse_gas_units(
        reference_gas_units_path.read_text(), "reference fixture gas_units.txt"
    )
    fixed_ref_hashes = fixed["source_hashes"]["reference_files"]
    for name in ("p_half", "t", "q", "o3", "co2"):
        require(sha256(REF_DIR / f"{name}.txt") == fixed_ref_hashes[name],
                f"reference {name} changed since fixed-input receipt")

    channel_file = [int(v) for v in (case_dir / "in/channels.txt").read_text().split()]
    settings = parse_assignments(case_dir / "out/rttov_test.txt")
    gas_units_text = (input_dir / "gas_units.txt").read_text()
    gas_units = validate_run_contract(
        channel_file, tuple(row["channel_names"]), gas_units_text, settings
    )

    q2_text = (input_dir / "sfc/01/near_surface.txt").read_text()
    skin_text = (input_dir / "sfc/01/skin.txt").read_text()
    q2_match = re.search(r"(?im)^\s*s0%q2m\s*=\s*([+-]?[0-9.eEdD]+)", q2_text)
    skin_match = re.search(r"(?im)^\s*k0%t\s*=\s*([+-]?[0-9.eEdD]+)", skin_text)
    require(q2_match is not None and skin_match is not None,
            "saved skin or near-surface file lacks target input field")
    q2_ppmv = float(q2_match.group(1).replace("D", "E").replace("d", "e"))
    skin_t_k = float(skin_match.group(1).replace("D", "E").replace("d", "e"))

    result_fixed = result["fixed_observation"]
    return {
        "result": result,
        "postrun": postrun,
        "fixed": fixed,
        "row": row,
        "fixed_row": fixed_row,
        "case_dir": case_dir,
        "profiles_k_path": profiles_k_path,
        "radiance_path": radiance_path,
        "active": active,
        "reference": reference,
        "reference_pressure": ref_pressure,
        "reference_half_pressure": ref_half,
        "reference_dir": REF_DIR,
        "reference_gas_units_path": reference_gas_units_path,
        "settings": settings,
        "gas_units": gas_units,
        "reference_gas_units": reference_gas_units,
        "q2_ppmv": q2_ppmv,
        "skin_t_k": skin_t_k,
        "fixed_observation": result_fixed,
    }


def audit_center(output_dir: Path, private_npz: Path) -> dict:
    if not PLAN_PATH.is_file():
        raise FileNotFoundError(f"frozen direction plan is missing: {PLAN_PATH}")
    plan_text = PLAN_PATH.read_text()
    missing_directions = [name for name in PLANNED_DIRECTIONS if name not in plan_text]
    if missing_directions:
        raise ValueError(f"direction plan does not predeclare {missing_directions}")
    direction_plan_hash = sha256(PLAN_PATH)
    source_contracts = source_contract_bindings()
    src = load_center_inputs()
    row = src["row"]
    case_dir = src["case_dir"]
    channel_ids = np.asarray(CHANNEL_IDS, dtype=np.int64)
    channel_names = np.asarray(CHANNEL_NAMES, dtype="U8")

    rad = parse_rttov_radiance(src["radiance_path"], nchannels=len(CHANNEL_IDS))
    k_raw_list, nprofiles_k = parse_rttov_profiles_k(
        src["profiles_k_path"], nchannels=len(CHANNEL_IDS)
    )
    blocks = parse_rttov_ascii_blocks(src["radiance_path"])
    require(nprofiles_k == 1 and rad["nprofiles"] == 1,
            "preserved center runK must contain exactly one profile")
    require("RADIANCE%TOTAL" in blocks, "same-run RADIANCE%TOTAL block is missing")
    total_flat = np.asarray(blocks["RADIANCE%TOTAL"], dtype=np.float64)
    require(total_flat.size == len(CHANNEL_IDS), "same-run total radiance channel count changed")
    total = total_flat.reshape(1, len(CHANNEL_IDS))
    bt_native = np.asarray(rad["bt"], dtype=np.float64)
    rad_quality = np.asarray(rad["rad_quality"], dtype=np.float64)
    require(np.array_equal(rad_quality, np.asarray(row["rad_quality"], dtype=np.float64)),
            "same-run production-parser quality differs from saved center result")
    k_raw = {name: np.asarray(value, dtype=np.float64) for name, value in k_raw_list.items()}

    coefficient_path = Path(
        row["rttov_assets"]["fixture_source"]["ami_coefficient"]["path"]
    )
    coefficient_hash = sha256(coefficient_path)
    require(coefficient_hash == row["rttov_assets"]["coefficient_sha256"],
            "actual coefficient file differs from the saved center asset hash")
    require(coefficient_hash == src["fixed"]["source_hashes"]["RTTOV_coefficient"]["sha256"],
            "actual coefficient differs from PR400 fixed-input receipt")

    filters = read_ami_filters(coefficient_path)
    calibration = read_kma_calibration()
    bt_kma, k_kma, d_bt_kma_d_bt_rttov = transform_rttov_to_kma(
        bt_native, total, k_raw, channel_ids.tolist(), filters, calibration
    )
    prior_bt_kma = np.asarray(row["BT_K"], dtype=np.float64)
    prior_bt_error = np.abs(bt_kma - prior_bt_kma)
    require(np.max(prior_bt_error) <= BT_REPLAY_ATOL_K,
            "converted center BT differs from the prior receipt beyond production tolerance")

    obs = src["fixed_observation"]
    obs_bt = np.asarray(obs["BT_K"], dtype=np.float64)
    sigma_raw = np.asarray(obs["sigma_K"], dtype=np.float64)
    bias_raw = np.asarray(obs["bias_K"], dtype=np.float64)
    support = np.asarray(obs["frozen_support"], dtype=np.float64)
    huber_delta = float(obs["huber_delta_K"])
    require(obs_bt.shape == bt_kma.shape,
            "fixed observation BT shape does not match the center")
    if sigma_raw.size == 1:
        sigma = np.full_like(bt_kma, float(sigma_raw.reshape(-1)[0]))
    elif sigma_raw.shape == bt_kma.shape:
        sigma = sigma_raw
    else:
        raise ValueError("fixed observation sigma shape is not broadcastable by contract")
    if bias_raw.size == 1:
        bias = np.full_like(bt_kma, float(bias_raw.reshape(-1)[0]))
    elif bias_raw.shape == bt_kma.shape:
        bias = bias_raw
    else:
        raise ValueError("fixed observation bias shape is not broadcastable by contract")
    require(support.shape == bt_kma.shape, "fixed support shape does not match center")
    require(np.all(support == 1.0) and np.all(rad_quality == 0.0),
            "center fixed-support or rad-quality contract changed")
    jo, residual, huber_slope = huber_loss_and_slope(
        bt_kma[0], obs_bt[0], sigma[0], bias[0], support[0], huber_delta
    )
    require(abs(jo - float(row["Jo_huber_K_units"])) <= 2e-12,
            "recomputed center Huber cost does not match prior center result")

    active = src["active"]
    reference = src["reference"]
    p_active = active["p"]
    p_ref = src["reference_pressure"]
    require(p_active.shape == (66,) and active["p_half"].shape == (67,),
            "center profile must have 66 layers and 67 interfaces")
    require(all(active[n].shape == (66,) for n in ("t", "q", "o3", "co2")),
            "active T/Q/O3/CO2 profile length changed")
    require(p_ref.shape == (69,) and all(reference[n].shape == (69,)
                                         for n in ("o3", "co2", "q", "t")),
            "reference profile must have 69 layers")
    p_matrix = build_log_pressure_interpolation_matrix(p_ref, p_active)
    for gas in ("o3", "co2"):
        reconstructed = p_matrix @ reference[gas]
        if not np.allclose(reconstructed, active[gas], rtol=0.0, atol=2e-13):
            err = float(np.max(np.abs(reconstructed - active[gas])))
            raise ValueError(f"{gas} interpolation matrix fails active profile replay ({err})")
    require(src["gas_units"] == 2, "active input gas units must remain 2 (ppmv moist)")

    n_upper = int(src["fixed_row"]["reference_layers"])
    n_native = int(src["fixed_row"]["native_layers"])
    require(n_upper == 27 and n_native == 39 and n_upper + n_native == 66,
            "fixed center profile composition changed from 27+39 layers")
    held_rows = np.flatnonzero(p_active > p_ref[-1])
    require(held_rows.size == 6, "expected six high-pressure endpoint-held gas levels")
    require(np.all(p_matrix[held_rows, -1] == 1.0),
            "endpoint-held rows must map wholly to the final reference level")
    require(np.all(p_matrix[held_rows, :-1] == 0.0),
            "endpoint-held rows must not include any other reference level")
    partial_endpoint_rows = np.flatnonzero(
        (p_matrix[:, -1] > 0.0) & (p_matrix[:, -1] < 1.0)
    )

    directions = []
    def add_direct(name, field, delta, description, units, affected_levels, category):
        vec = np.asarray(delta, dtype=np.float64)
        kval = k_kma[field][0]
        require(vec.shape == (kval.shape[1],),
                f"{name} input perturbation length does not match {field} K")
        delta_bt = kval @ vec
        directions.append({
            "name": name, "field": field, "description": description,
            "input_units": units, "affected_levels": int(affected_levels),
            "category": category, "delta_input": vec,
            "delta_bt_kma_k": delta_bt,
        })

    add_direct("skin_T_plus_1K", "SKIN(1)%T", np.array([1.0]),
               "+1 K in the saved skin-temperature scalar", "K", 1, "surface")
    directions[-1]["declared_perturbation"] = {
        "kind": "absolute", "value": 1.0, "units": "K"
    }

    for gas, field in (("o3", "O3"), ("co2", "CO2")):
        beta = 0.01 * reference[gas]
        active_delta, delta_bt, delta_bt_equiv = contract_reference_k(
            k_kma[field][0], p_matrix, beta
        )
        require(np.allclose(p_matrix @ beta, active_delta, rtol=0.0, atol=1e-14),
                f"{gas} source perturbation projection changed")
        directions.append({
            "name": f"reference_{gas}_plus_1pct", "field": field,
            "description": f"+1% of the 69-level reference {gas.upper()} profile, projected to active levels",
            "input_units": "ppmv_moist_reference", "active_units": "ppmv_moist_gas_units_2",
            "affected_levels": int(np.count_nonzero(active_delta)),
            "category": "reference_gas",
            "declared_perturbation": {
                "kind": "relative", "fraction": 0.01,
                "units": "of the 69-level reference profile",
            },
            "reference_profile_min_ppmv": float(np.min(reference[gas])),
            "reference_profile_max_ppmv": float(np.max(reference[gas])),
            "beta_reference": beta,
            "delta_input": active_delta,
            "delta_bt_kma_k": delta_bt,
            "delta_bt_source_contracted_k": delta_bt_equiv,
        })

    q2_delta = np.array([0.01 * src["q2_ppmv"]], dtype=np.float64)
    add_direct(
        "near_surface_Q2_plus_1pct", "NEAR_SURFACE(1)%Q2M", q2_delta,
        "+1% of the actual saved RTTOV near-surface Q2 value",
        "ppmv_moist", 1, "near_surface",
    )
    directions[-1]["declared_perturbation"] = {
        "kind": "relative", "fraction": 0.01,
        "reference_value_ppmv_moist": float(src["q2_ppmv"]),
        "actual_delta_ppmv_moist": float(q2_delta[0]),
    }

    upper_t_delta = np.zeros(66, dtype=np.float64)
    upper_t_delta[:n_upper] = 1.0
    add_direct(
        "upper_reference_T_plus_1K", "T", upper_t_delta,
        "+1 K on 27 upper fixture-reference T levels; all 39 native levels held fixed",
        "K", n_upper, "upper_reference",
    )
    directions[-1]["declared_perturbation"] = {
        "kind": "absolute", "value": 1.0,
        "units": "K on upper 27 active levels",
    }

    upper_q_delta = np.zeros(66, dtype=np.float64)
    upper_q_delta[:n_upper] = 0.01 * active["q"][:n_upper]
    add_direct(
        "upper_reference_Q_plus_1pct", "Q", upper_q_delta,
        "+1% on 27 upper fixture-reference Q levels; all 39 native levels held fixed",
        "ppmv_moist_gas_units_2", n_upper, "upper_reference",
    )
    directions[-1]["declared_perturbation"] = {
        "kind": "relative", "fraction": 0.01,
        "units": "of upper 27 active Q values in ppmv moist",
        "active_Q_min_ppmv_moist": float(np.min(active["q"][:n_upper])),
        "active_Q_max_ppmv_moist": float(np.max(active["q"][:n_upper])),
    }
    if tuple(d["name"] for d in directions) != PLANNED_DIRECTIONS:
        raise ValueError("executed direction list differs from frozen direction plan")

    direction_matrix = np.vstack([d["delta_bt_kma_k"] for d in directions])
    direction_jo = direction_matrix * huber_slope[None, :]
    for d, row_delta_jo in zip(directions, direction_jo):
        d["delta_jo_linear_by_channel"] = row_delta_jo
        d["delta_jo_linear_channels_10_to_15"] = float(np.sum(row_delta_jo[:6]))
        d["delta_jo_linear_channel_16_ir133"] = float(row_delta_jo[6])
        d["delta_jo_linear_total_seven_channels"] = float(np.sum(row_delta_jo))

    endpoint_details = {}
    for gas, field in (("o3", "O3"), ("co2", "CO2")):
        k_active = k_kma[field][0]
        beta = 0.01 * reference[gas]
        endpoint_sensitivity, endpoint_contribution = contract_held_endpoint_k(
            k_active, p_matrix, beta, held_rows, int(reference[gas].size - 1)
        )
        partial_weight = p_matrix[partial_endpoint_rows, -1]
        partial_sensitivity = np.sum(
            k_active[:, partial_endpoint_rows] * partial_weight[None, :], axis=1
        )
        partial_contribution = partial_sensitivity * beta[-1]
        source_endpoint_sensitivity = (k_active @ p_matrix)[:, -1]
        source_equiv = source_endpoint_sensitivity * beta[-1]
        if not np.allclose(endpoint_contribution + partial_contribution,
                            source_equiv, rtol=0.0, atol=2e-12):
            raise ValueError(f"{gas} held + partial endpoint terms do not reproduce source column")
        endpoint_details[gas.upper()] = {
            "held_active_level_indices_0based": held_rows.tolist(),
            "partially_weighted_active_level_indices_0based": partial_endpoint_rows.tolist(),
            "partially_weighted_endpoint_weights": partial_weight.tolist(),
            "partially_weighted_active_pressures_hpa": p_active[partial_endpoint_rows].tolist(),
            "shared_reference_endpoint_index_0based": int(reference[gas].size - 1),
            "active_kma_sensitivity_sum_K_per_ppmv": endpoint_sensitivity.tolist(),
            "one_percent_endpoint_contribution_delta_bt_k": endpoint_contribution.tolist(),
            "partial_endpoint_sensitivity_K_per_ppmv": partial_sensitivity.tolist(),
            "partial_endpoint_contribution_delta_bt_k": partial_contribution.tolist(),
            "total_last_reference_level_contribution_delta_bt_k": source_equiv.tolist(),
            "source_contracted_check_delta_bt_k": source_equiv.tolist(),
            "interpretation": "Six active levels hold one source endpoint; two additional levels use fractional endpoint weights. All endpoint effects come from one correlated source perturbation, not eight independent profile errors.",
        }

    active_input_hashes = {
        name: sha256(case_dir / "in/profiles/001/atm" / f"{name}.txt")
        for name in ("p", "p_half", "t", "q", "o3", "co2")
    }
    surface_hashes = {
        "skin": sha256(case_dir / "in/profiles/001/sfc/01/skin.txt"),
        "near_surface": sha256(case_dir / "in/profiles/001/sfc/01/near_surface.txt"),
        "gas_units": sha256(case_dir / "in/profiles/001/gas_units.txt"),
        "channels": sha256(case_dir / "in/channels.txt"),
        "namelist": sha256(case_dir / "out/rttov_test.txt"),
    }
    source_hashes = {
        "audit_source": sha256(Path(__file__).resolve()),
        "neighbor_result": sha256(RESULT),
        "neighbor_postrun": sha256(POSTRUN),
        "fixed_inputs_receipt": sha256(FIXED),
        "profiles_k": sha256(src["profiles_k_path"]),
        "same_run_radiance": sha256(src["radiance_path"]),
        "rttov_coefficient": coefficient_hash,
        "rttov_executable": row["rttov_assets"]["executable_sha256"],
        "reference_files": {
            n: sha256(REF_DIR / f"{n}.txt") for n in ("p_half", "t", "q", "o3", "co2")
        },
        "reference_gas_units_path": str(src["reference_gas_units_path"]),
        "reference_gas_units_sha256": sha256(src["reference_gas_units_path"]),
        "active_profile_files": active_input_hashes,
        "surface_and_contract_files": surface_hashes,
        "production_source_contracts": source_contracts,
        "direction_plan": {"path": str(PLAN_PATH), "sha256": direction_plan_hash},
    }

    private_npz.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(private_npz.parent, 0o700)
    if private_npz.exists():
        raise FileExistsError(f"refusing to overwrite preserved private NPZ: {private_npz}")
    arrays: dict[str, np.ndarray] = {
        "channel_ids_1based": channel_ids,
        "channel_names": channel_names,
        "rttov_native_bt_k": bt_native,
        "rttov_total_radiance": total,
        "rttov_rad_quality": rad_quality,
        "kma_bt_k": bt_kma,
        "prior_receipt_bt_kma_bt_k": prior_bt_kma,
        "observation_bt_kma_k": obs_bt,
        "observation_sigma_k": sigma,
        "observation_bias_k": bias,
        "frozen_support": support,
        "baseline_residual_k": residual,
        "huber_slope_djo_dbt": huber_slope,
        "d_bt_kma_d_bt_rttov": d_bt_kma_d_bt_rttov,
        "active_p_hpa": active["p"],
        "active_p_half_hpa": active["p_half"],
        "active_t_k": active["t"],
        "active_q_ppmv_moist": active["q"],
        "active_o3_ppmv_moist": active["o3"],
        "active_co2_ppmv_moist": active["co2"],
        "active_gas_units": np.asarray(src["gas_units"], dtype=np.int64),
        "reference_pressure_hpa": p_ref,
        "reference_o3_ppmv_moist": reference["o3"],
        "reference_co2_ppmv_moist": reference["co2"],
        "reference_gas_units": np.asarray(src["reference_gas_units"], dtype=np.int64),
        "log_pressure_interpolation_matrix": p_matrix,
        "held_active_level_indices_0based": held_rows.astype(np.int64),
        "direction_delta_bt_kma_k": direction_matrix,
        "direction_delta_jo_linear_by_channel": direction_jo,
        "direction_names": np.asarray([d["name"] for d in directions], dtype="U48"),
        "direction_names_units": np.asarray([d["input_units"] for d in directions], dtype="U48"),
        "direction_plan_sha256": np.asarray(direction_plan_hash),
    }
    for name, value in k_raw.items():
        safe = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").upper()
        arrays[f"k_rttov__{safe}"] = value
        arrays[f"k_kma__{safe}"] = k_kma[name]
    for d in directions:
        safe = re.sub(r"[^A-Za-z0-9]+", "_", d["name"]).strip("_")
        if "beta_reference" in d:
            arrays[f"beta_reference__{safe}"] = d["beta_reference"]
        arrays[f"delta_input__{safe}"] = d["delta_input"]

    with private_npz.open("xb") as stream:
        np.savez_compressed(stream, **arrays)
    os.chmod(private_npz, 0o600)
    npz_hash = sha256(private_npz)

    direction_rows = []
    for d, delta_j in zip(directions, direction_jo):
        for c, channel_id in enumerate(CHANNEL_IDS):
            direction_rows.append({
                "direction": d["name"],
                "category": d["category"],
                "description": d["description"],
                "declared_perturbation": json.dumps(d["declared_perturbation"], sort_keys=True),
                "input_units": d["input_units"],
                "affected_levels": d["affected_levels"],
                "active_input_delta_min": float(np.min(d["delta_input"])),
                "active_input_delta_max": float(np.max(d["delta_input"])),
                "active_input_delta_nonzero_levels": int(np.count_nonzero(d["delta_input"])),
                "channel_id_1based": channel_id,
                "channel_name": CHANNEL_NAMES[c],
                "delta_bt_kma_k": float(d["delta_bt_kma_k"][c]),
                "huber_slope_djo_dbt": float(huber_slope[c]),
                "delta_jo_linear": float(delta_j[c]),
                "delta_jo_units": "dimensionless",
                "term_group": "channels_10_to_15" if c < 6 else "channel_16_ir133",
            })

    channel_rows = []
    for c, channel_id in enumerate(CHANNEL_IDS):
        channel_rows.append({
            "channel_id_1based": channel_id,
            "channel_name": CHANNEL_NAMES[c],
            "rttov_native_bt_k": float(bt_native[0, c]),
            "rttov_total_radiance": float(total[0, c]),
            "kma_bt_k": float(bt_kma[0, c]),
            "prior_receipt_bt_kma_bt_k": float(prior_bt_kma[0, c]),
            "bt_abs_diff_from_prior_k": float(prior_bt_error[0, c]),
            "observation_bt_kma_k": float(obs_bt[0, c]),
            "baseline_residual_k": float(residual[c]),
            "huber_slope_djo_dbt": float(huber_slope[c]),
            "k_coordinate_scale_dbt_kma_dbt_rttov": float(d_bt_kma_d_bt_rttov[0, c]),
            "rad_quality": float(rad_quality[0, c]),
        })

    report_path = output_dir / "REPORT.md"
    json_path = output_dir / "K_RESPONSE.json"
    direction_csv = output_dir / "K_RESPONSE_DIRECTIONS.csv"
    channel_csv = output_dir / "K_RESPONSE_CHANNELS.csv"
    output_dir.mkdir(parents=True, exist_ok=True)
    for path in (report_path, json_path, direction_csv, channel_csv):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite existing audit artifact: {path}")

    def write_csv(path: Path, rows: list[dict]) -> None:
        with path.open("x", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    write_csv(direction_csv, direction_rows)
    write_csv(channel_csv, channel_rows)

    direction_json = []
    for d in directions:
        record = {
            k: v for k, v in d.items()
            if k not in {"delta_input", "beta_reference", "delta_bt_kma_k", "delta_jo_linear_by_channel"}
        }
        record = {k: (v.tolist() if isinstance(v, np.ndarray) else v)
                  for k, v in record.items()}
        active_delta = np.asarray(d["delta_input"], dtype=np.float64)
        record["active_input_delta_summary"] = {
            "n_levels": int(active_delta.size),
            "nonzero_levels": int(np.count_nonzero(active_delta)),
            "min": float(np.min(active_delta)),
            "max": float(np.max(active_delta)),
            "units": d["input_units"],
        }
        if "beta_reference" in d:
            beta = np.asarray(d["beta_reference"], dtype=np.float64)
            record["reference_beta_summary"] = {
                "n_levels": int(beta.size),
                "min": float(np.min(beta)),
                "max": float(np.max(beta)),
                "units": d["input_units"],
            }
        direction_json.append(record | {
            "delta_bt_kma_k_by_channel": d["delta_bt_kma_k"].tolist(),
            "delta_jo_linear_by_channel": d["delta_jo_linear_by_channel"].tolist(),
        })
    payload = {
        "schema": "pr401_center_fixed_input_k_response_v1",
        "status": "SAVED_CENTER_K_RESPONSE_REPLAYED; EXPLORATORY_LINEAR_DIRECTIONS_ONLY",
        "scope": {
            "center_cell_j_i": [86, 48],
            "native_time": row["native_time_label"],
            "center_role": "preserved PR398 direct-H center with existing direct RTTOV runK K output",
            "channels_1based": list(CHANNEL_IDS),
            "channel_names": list(CHANNEL_NAMES),
            "calls": {"RTTOV_H": 0, "RTTOV_K": 0, "M": 0, "Model_H": 0,
                      "native_run": 0, "preprocessing": 0, "optimizer": 0,
                      "external_acquisition": 0},
            "analysis_acceptance": False,
            "production_changes": False,
            "observation_pixels_read": False,
            "input_errors_estimated": False,
            "direction_sizes_are_exploratory": True,
        },
        "provenance": {
            "result_path": str(RESULT),
            "result_sha256": sha256(RESULT),
            "postrun_audit_sha256": sha256(POSTRUN),
            "fixed_inputs_sha256": sha256(FIXED),
            "case_output_dir": str(case_dir),
            "case_role": row["case_role"],
            "rttov_radiance_path": str(src["radiance_path"]),
            "rttov_radiance_sha256": source_hashes["same_run_radiance"],
            "rttov_profiles_k_path": str(src["profiles_k_path"]),
            "rttov_profiles_k_sha256": source_hashes["profiles_k"],
            "same_run_contract": "RADIANCE%TOTAL, RADIANCE%BT, RADIANCE%QUALITY and PROFILES_K were parsed from the saved out/k runK products in this same center case.",
            "active_profile_hashes": active_input_hashes,
            "surface_contract_hashes": surface_hashes,
            "reference_dir": str(REF_DIR),
            "reference_file_hashes": source_hashes["reference_files"],
            "coefficient_path": str(coefficient_path),
            "coefficient_sha256": coefficient_hash,
            "coefficient_matches_pr399_center_asset": coefficient_hash == row["rttov_assets"]["coefficient_sha256"],
            "audit_source_path": str(Path(__file__).resolve()),
            "audit_source_sha256": source_hashes["audit_source"],
            "direction_plan_path": str(PLAN_PATH),
            "direction_plan_sha256": direction_plan_hash,
            "source_contract_receipt_path": str(SOURCE_CONTRACT_RECEIPT),
            "source_contract_receipt_sha256": source_contracts["receipt_sha256"],
        },
        "source_contracts": source_contracts,
        "run_contract": {
            "channels_file_order_matches": True,
            "channels_file": list(CHANNEL_IDS),
            "rttov_result_order_matches": row["channels_1based"],
            "channel_names_match": list(CHANNEL_NAMES),
            "adk_bt": True,
            "use_q2m": True,
            "gas_units_file": src["gas_units"],
            "reference_gas_units_file": src["reference_gas_units"],
            "reference_gas_units_file_path": str(src["reference_gas_units_path"]),
            "reference_gas_units_file_sha256": sha256(src["reference_gas_units_path"]),
            "run_gas_units": int(src["settings"]["defn%run_gas_units"]),
            "rttov_quality_all_zero": True,
            "frozen_support_all_one": True,
            "prior_bt_abs_max_diff_k": float(np.max(prior_bt_error)),
            "prior_bt_replay_atol_k": float(BT_REPLAY_ATOL_K),
            "baseline_huber_jo_recomputed": jo,
            "baseline_huber_jo_saved": float(row["Jo_huber_K_units"]),
            "baseline_huber_jo_units": "dimensionless (Huber applied to residual/sigma; sigma is in K)",
            "baseline_huber_saved_receipt_key": "Jo_huber_K_units (legacy field name; numeric objective is dimensionless)",
        },
        "profile_and_reference": {
            "active_layer_count": 66,
            "active_interface_count": 67,
            "reference_layer_count": 69,
            "upper_fixture_layer_count": n_upper,
            "native_layer_count": n_native,
            "active_layer_pressure_hpa": active["p"].tolist(),
            "reference_layer_pressure_hpa": p_ref.tolist(),
            "log_pressure_interpolation_matrix_shape": list(p_matrix.shape),
            "matrix_orientation": "P[active_layer, reference_layer]; active_delta=P@beta_reference",
            "np_interp_reproduction_max_abs": {
                gas.upper(): float(np.max(np.abs(p_matrix @ reference[gas] - active[gas])))
                for gas in ("o3", "co2")
            },
            "endpoint_policy": "linear interpolation in log pressure with constant endpoint hold, matching saved numpy.interp source path",
            "held_high_pressure_layer_indices_0based": held_rows.tolist(),
            "held_high_pressure_layer_count": int(held_rows.size),
            "partial_last_endpoint_layer_indices_0based": partial_endpoint_rows.tolist(),
            "partial_last_endpoint_weights": p_matrix[partial_endpoint_rows, -1].tolist(),
            "endpoint_sensitivity": endpoint_details,
        },
        "coordinate_transform": {
            "method": "oracle.kdm6.obs.ami_bt_coordinate.transform_rttov_to_kma",
            "native_bt_source": "RADIANCE%BT from same out/k/radiance.txt as RADIANCE%TOTAL",
            "total_radiance_source": "RADIANCE%TOTAL from same out/k/radiance.txt",
            "all_parsed_k_fields_transformed": sorted(k_raw),
            "coordinate_scale_d_bt_kma_d_bt_rttov": d_bt_kma_d_bt_rttov[0].tolist(),
            "per_channel": channel_rows,
        },
        "directions": direction_json,
        "summary": {
            "baseline_jo_huber_dimensionless": jo,
            "baseline_residual_and_sigma_units": "K",
            "huber_loss_units": "dimensionless; loss is applied to (model_BT - observation_BT - bias) / sigma",
            "six_channel_terms_10_to_15_by_direction": {
                d["name"]: d["delta_jo_linear_channels_10_to_15"] for d in directions
            },
            "ir133_channel_16_term_by_direction": {
                d["name"]: d["delta_jo_linear_channel_16_ir133"] for d in directions
            },
            "total_seven_channel_linear_delta_jo_by_direction": {
                d["name"]: d["delta_jo_linear_total_seven_channels"] for d in directions
            },
            "cost_interpretation": "First-order delta-Jo of the dimensionless Huber loss at the existing center; the six-channel subtotal and IR133 term are descriptive splits of the unchanged seven-channel support, not ablation results.",
        },
        "k_field_summary": {
            name: {
                "levels_per_channel": int(value.shape[-1]),
                "channels": int(value.shape[1]),
                "elements": int(value.size),
                "positive": int(np.count_nonzero(value > 0.0)),
                "negative": int(np.count_nonzero(value < 0.0)),
                "zero": int(np.count_nonzero(value == 0.0)),
                "min": float(np.min(value)),
                "max": float(np.max(value)),
                "rttov_sha256": sha256(src["profiles_k_path"]),
            }
            for name, value in k_raw.items()
        },
        "private_npz": {
            "path": str(private_npz),
            "sha256": npz_hash,
            "mode_octal": oct(private_npz.stat().st_mode & 0o777),
            "directory_mode_octal": oct(private_npz.parent.stat().st_mode & 0o777),
            "arrays": sorted(arrays),
        },
        "output_files": {
            direction_csv.name: sha256(direction_csv),
            channel_csv.name: sha256(channel_csv),
        },
        "limitations": [
            "Saved center K is the direct RTTOV observation-operator derivative at the PR398-reused center, not a KDM6AD Model_H/JVP/VJP or final accepted analysis.",
            "The scalar/unit directions are exploratory response scales, not observation/input-error estimates, physically approved perturbation ranges, or corrective fits.",
            "O3/CO2 endpoint terms are correlated because six active levels use one held reference endpoint.",
            "No changed input was passed through RTTOV; delta-BT and delta-Jo are first-order K contractions only.",
        ],
    }

    with json_path.open("x") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
    report = render_report(payload, directions)
    with report_path.open("x") as stream:
        stream.write(report)
    print(json.dumps({"status": payload["status"], "output": str(json_path),
                      "json_sha256": sha256(json_path), "private_npz_sha256": npz_hash,
                      "baseline_jo": jo, "prior_bt_max_diff_k": float(np.max(prior_bt_error))},
                     sort_keys=True))
    return payload


def render_report(payload: dict, directions: list[dict]) -> str:
    lines = [
        "# PR401 saved center RTTOV K response audit",
        "",
        "## Scope and replay",
        "",
        "This is a metadata and saved-output replay of the existing PR398 center direct-H/runK case at `(j=86,i=48)`, `2025-07-19_05:56:00`, with seven channels 10–16. It made no new RTTOV, H, K, M, Model_H, native, preprocessing, optimizer, acquisition, or observation-pixel calls. The center is the previously reused direct-H center, not a final accepted analysis.",
        "",
        "The production parser recovered `RADIANCE%TOTAL`, native `RADIANCE%BT`, quality, and every `PROFILES_K` field from the same `out/k` outputs. Saved `channels.txt` is exactly `10 11 12 13 14 15 16`; the output profile count is one; `adk_bt=.TRUE.`, `use_q2m=.TRUE.`, active and reference fixture `gas_units=2`, and `run_gas_units=2`. All seven quality flags are zero and support is all one. Applying the existing `transform_rttov_to_kma` to the same-run radiance/native BT scales every K field; converted center BT agrees with the prior receipt within the production `3e-6 K` replay tolerance.",
        "",
        f"Recomputed dimensionless normalized Huber objective is `{payload['run_contract']['baseline_huber_jo_recomputed']:.12f}` versus saved `{payload['run_contract']['baseline_huber_jo_saved']:.12f}` (the saved receipt field is named `Jo_huber_K_units`). Residuals and sigma are in K with `sigma=1 K`. Maximum converted BT difference from the saved center is `{payload['run_contract']['prior_bt_abs_max_diff_k']:.3g} K`.",
        "",
        "## Input directions and linear response",
        "",
        "| Direction | Declared input perturbation | Approximate dimensionless delta-Jo, channels 10–15 | Channel 16 IR133 term | All seven channels |",
        "|---|---|---:|---:|---:|",
    ]
    for d in directions:
        lines.append(
            f"| {d['name']} | `{json.dumps(d['declared_perturbation'], sort_keys=True)}` | "
            f"{d['delta_jo_linear_channels_10_to_15']:.8g} | "
            f"{d['delta_jo_linear_channel_16_ir133']:.8g} | "
            f"{d['delta_jo_linear_total_seven_channels']:.8g} |"
        )
    lines += [
        "",
        "Directions are: skin temperature +1 K; source O3 +1%; source CO2 +1%; saved near-surface Q2 +1% in its actual RTTOV ppmv units; upper 27-layer T +1 K with the 39 native T levels fixed; and upper 27-layer Q +1% in active ppmv with the native suffix fixed. The actual Q2 value and 1% delta are explicit in the table and CSV. `K_RESPONSE_DIRECTIONS.csv` lists declared scales, units, affected levels, and channelwise BT/Jo responses; exact per-level input delta vectors, reference beta vectors, P and K arrays are preserved in the private NPZ. Baseline channel order and residuals are in `K_RESPONSE_CHANNELS.csv`.",
        "",
        "These are unit/example perturbations, not estimated input errors or corrective fits. `delta-Jo` is the first-order derivative of the unchanged Huber objective at the saved center, not a cost from a perturbed forward run. The channel 10–15 subtotal and channel 16 term only describe the seven-channel result; no channel was removed or ablated.",
        "",
        "## Log-pressure interpolation and endpoint correlation",
        "",
        "The audit builds `P[active layer,reference layer]` on log pressure from the saved 69-level fixture to the 66-level active profile. `P @ beta_reference` reproduces the active O3 and CO2 files, and `(K_z @ P) @ beta_reference` agrees with `K_z @ (P @ beta_reference)` within the recorded contraction tolerance.",
        "",
        f"Exactly {payload['profile_and_reference']['held_high_pressure_layer_count']} high-pressure active levels `{payload['profile_and_reference']['held_high_pressure_layer_indices_0based']}` fully hold the final reference O3/CO2 value. Two additional active levels `{payload['profile_and_reference']['partial_last_endpoint_layer_indices_0based']}` have fractional final-endpoint weights `{payload['profile_and_reference']['partial_last_endpoint_weights']}`. The audit separates held and partial K contributions, then confirms their sum matches the last source-reference-level contraction. All of these terms arise from one correlated source endpoint, not eight independent errors. Per-channel endpoint sensitivity and contribution are in `K_RESPONSE.json`.",
        "",
        "## Limits and preserved evidence",
        "",
        "The stored NPZ preserves native and KMA-coordinate matrices, active and reference profiles, the interpolation matrix, all input directions, and response/cost contractions. Its canonical copy is mode `0600` in a mode `0700` directory. Source, receipt, case output, coefficient, reference profile, active profile and surface hashes are recorded in `K_RESPONSE.json`.",
        "",
        "This establishes a local direct observation-operator response for one saved center. It does not establish KDM6AD Model_H, model-composed derivatives, an accepted analysis, valid physical error ranges, or input error. No H/M/model rerun or parameter fitting was performed.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path,
                        default=ROOT / "harness/evidence/pr401_fixed_input_k_response_2026-10-10/final_v2")
    parser.add_argument("--private-npz", type=Path, default=PRIVATE_NPZ)
    args = parser.parse_args()
    audit_center(args.output_dir, args.private_npz)


if __name__ == "__main__":
    main()
