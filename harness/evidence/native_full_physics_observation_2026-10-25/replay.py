#!/usr/bin/env python3
"""Offline arithmetic replay for the native full-physics baseline packet.

This reader verifies the declared NPZ SHA before opening those exact bytes with
BytesIO. It imports only Python's standard library and NumPy; it does not run
RTTOV, KDM6, host physics, or an optimizer.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
from io import BytesIO
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

REASON_LABELS = (
    "admitted_with_support",
    "direct_RTTOV_model_quality_nonzero",
    "initial_negative_native_number_moment",
    "native_checkpoint_profile_preflight_invalid",
    "rttov_hard_qmin_input_minimum",
    "no_channel_support_after_direct_quality",
    "source_qc_or_observation_invalid",
)


def _sha(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _huber(residual: float) -> float:
    magnitude = abs(residual)
    return 0.5 * residual * residual if magnitude <= 1.0 else magnitude - 0.5


def replay(manifest_path: Path) -> dict[str, Any]:
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    replay_source_sha = _sha(Path(__file__).read_bytes())
    pinned_replay_sha = manifest.get("provenance", {}).get("public_code_sources", {}).get("replay.py")
    if pinned_replay_sha != replay_source_sha:
        raise ValueError("public replay source SHA differs from manifest")
    packet_info = manifest["packet"]
    packet_path = manifest_path.parent / packet_info["file"]

    # Read once, hash those bytes, then parse those same bytes.
    packet_bytes = packet_path.read_bytes()
    packet_sha = _sha(packet_bytes)
    if packet_sha != packet_info["sha256"]:
        raise ValueError(f"packet SHA mismatch: expected {packet_info['sha256']}, got {packet_sha}")
    with np.load(BytesIO(packet_bytes), allow_pickle=False) as archive:
        arrays = {key: np.array(archive[key], copy=True) for key in archive.files}

    required = {
        "flat_index", "i_zero_based", "j_zero_based", "chunk_index", "chunk_local_row",
        "source_owner_id", "source_ko_coverage_all7", "channel_id", "obs_bt_k",
        "baseline_bt_kma_v3_0", "source_dqf", "source_qc_code", "model_quality",
        "profile_valid", "source_valid", "m0_mask", "reason_code", "outer_edge_ring",
    }
    missing = sorted(required - arrays.keys())
    if missing:
        raise ValueError(f"packet is missing required arrays: {missing}")

    flat = arrays["flat_index"]
    obs = arrays["obs_bt_k"]
    bt = arrays["baseline_bt_kma_v3_0"]
    dqf = arrays["source_dqf"]
    qc = arrays["source_qc_code"]
    quality = arrays["model_quality"]
    profile_valid = arrays["profile_valid"].astype(bool)
    source_valid = arrays["source_valid"].astype(bool)
    mask = arrays["m0_mask"].astype(bool)
    reason_code = arrays["reason_code"].astype(np.uint8)
    chunk_index = arrays["chunk_index"].astype(np.int64)

    if flat.shape != (65_988,) or not np.array_equal(flat, np.arange(65_988, dtype=flat.dtype)):
        raise ValueError("flat columns do not cover 0..65,987 exactly once in canonical order")
    if arrays["channel_id"].tolist() != [10, 11, 12, 13, 14, 15, 16]:
        raise ValueError("AMI channel coordinate differs from the packet contract")
    for name, value in (("obs_bt_k", obs), ("baseline_bt_kma_v3_0", bt), ("source_dqf", dqf),
                        ("source_qc_code", qc), ("model_quality", quality), ("m0_mask", mask)):
        if value.shape != (65_988, 7):
            raise ValueError(f"{name} shape is {value.shape}, expected (65988,7)")
    if profile_valid.shape != (65_988,) or reason_code.shape != (65_988,):
        raise ValueError("profile_valid or reason_code is not full domain")
    if not np.array_equal(arrays["i_zero_based"], flat % 234) or not np.array_equal(arrays["j_zero_based"], flat // 234):
        raise ValueError("native i/j coordinates do not match flat=j*234+i")
    if not np.array_equal(chunk_index, flat // 512):
        raise ValueError("chunk index differs from original B512 partition and tail")
    if not np.array_equal(arrays["chunk_local_row"], flat % 512):
        raise ValueError("chunk-local row differs from original schedule")
    owner = arrays["source_owner_id"]
    if owner.shape != flat.shape or np.unique(owner).size != flat.size:
        raise ValueError("source owner IDs are not unique over all native columns")

    source_expected = (dqf == 0) & (qc == 0) & np.isfinite(obs)
    if not np.array_equal(source_valid, source_expected):
        raise ValueError("source_valid does not match source DQF/QC/finite-observation contract")
    mask_expected = profile_valid[:, None] & source_valid & (quality == 0) & np.isfinite(bt)
    if not np.array_equal(mask, mask_expected):
        raise ValueError("M0 differs from profile/source/model-quality/finite-BT contract")
    if not np.isfinite(bt[mask]).all() or not np.isfinite(obs[mask]).all():
        raise ValueError("supported observation/BT values are nonfinite")
    if not bool(arrays["source_ko_coverage_all7"].all()):
        raise ValueError("packet reports missing raw KO coverage despite baseline manifest")
    if int(arrays["source_ko_coverage_all7"].sum()) != manifest["analysis"]["raw_ko_source_coverage_all7"]:
        raise ValueError("mapped raw KO coverage count differs from manifest")
    if int(np.count_nonzero(reason_code == REASON_LABELS.index("rttov_hard_qmin_input_minimum"))) != 1:
        raise ValueError("expected exactly one q_min exclusion in the full domain")
    qmin_flat = 28_195
    if profile_valid[qmin_flat] or mask[qmin_flat].any() or reason_code[qmin_flat] != REASON_LABELS.index("rttov_hard_qmin_input_minimum"):
        raise ValueError("the q_min-invalid chunk55 row is not separately excluded")

    reason_labels = tuple(manifest["reason_codebook"])
    if reason_labels != REASON_LABELS:
        raise ValueError("reason codebook differs from this reader's frozen mapping")
    if np.any(reason_code >= len(reason_labels)):
        raise ValueError("reason code is outside the manifest codebook")
    qmin_reason_id = REASON_LABELS.index("rttov_hard_qmin_input_minimum")
    if np.count_nonzero((~profile_valid) & (reason_code == qmin_reason_id)) != 1:
        raise ValueError("q_min row code is not associated with one invalid profile")
    for row in np.flatnonzero(profile_valid):
        if not source_valid[row].all():
            expected_id = REASON_LABELS.index("source_qc_or_observation_invalid")
        elif np.any(quality[row] != 0):
            expected_id = REASON_LABELS.index("direct_RTTOV_model_quality_nonzero")
        elif not mask[row].any():
            expected_id = REASON_LABELS.index("no_channel_support_after_direct_quality")
        else:
            expected_id = REASON_LABELS.index("admitted_with_support")
        if reason_code[row] != expected_id:
            raise ValueError(f"row {row} reason code does not match its direct support status")
    invalid_reason_codes = set(reason_code[~profile_valid].tolist()) - {
        REASON_LABELS.index("initial_negative_native_number_moment"),
        REASON_LABELS.index("native_checkpoint_profile_preflight_invalid"),
        qmin_reason_id,
    }
    if invalid_reason_codes:
        raise ValueError(f"invalid-profile rows have unexpected reason codes: {sorted(invalid_reason_codes)}")

    # Match the producer's operation order: per chunk, per channel, row-ordered
    # Huber terms; then math.fsum channel partials and global chunk partials.
    chunk_num = []
    chunk_channel_num = []
    chunk_support = []
    for chunk in range(129):
        rows = chunk_index == chunk
        channel_num = []
        channel_support = []
        for channel in range(7):
            selected = rows & mask[:, channel]
            terms = [
                _huber(float(bt[row, channel]) - float(obs[row, channel]))
                for row in np.flatnonzero(selected)
            ]
            channel_num.append(math.fsum(terms))
            channel_support.append(int(np.count_nonzero(selected)))
        chunk_channel_num.append(channel_num)
        chunk_num.append(math.fsum(channel_num))
        chunk_support.append(channel_support)
    huber_num = math.fsum(chunk_num)
    Z = int(mask.sum())
    cost = huber_num / Z
    per_channel_num = [math.fsum(chunk_channel_num[c][k] for c in range(129)) for k in range(7)]
    channel_coverage = mask.sum(axis=0).astype(int).tolist()

    per_channel = []
    for c, channel in enumerate(arrays["channel_id"].tolist()):
        values = []
        for row in np.flatnonzero(mask[:, c]):
            values.append(float(bt[row, c]) - float(obs[row, c]))
        count = len(values)
        per_channel.append(
            {
                "channel_id": int(channel),
                "support_count": count,
                "bias_model_minus_observation_K": math.fsum(values) / count if count else None,
                "MAE_K": math.fsum(abs(x) for x in values) / count if count else None,
                "RMSE_K": math.sqrt(math.fsum(x * x for x in values) / count) if count else None,
                "huber_observation_numerator": per_channel_num[c],
                "supported_abs_residual_max_K": max((abs(x) for x in values), default=None),
            }
        )
    expected = manifest["analysis"]
    if Z != expected["global_support_Z"] or huber_num != expected["global_huber_observation_numerator"] or cost != expected["global_cost"]:
        raise ValueError("recomputed global support/numerator/cost differs from the packet manifest")
    if channel_coverage != [int(x["support_count"]) for x in expected["per_channel"]]:
        raise ValueError("recomputed per-channel support differs from manifest")
    for index, computed in enumerate(per_channel):
        for field in (
            "bias_model_minus_observation_K",
            "MAE_K",
            "RMSE_K",
            "huber_observation_numerator",
            "supported_abs_residual_max_K",
        ):
            if computed[field] != expected["per_channel"][index][field]:
                raise ValueError(f"recomputed channel {computed['channel_id']} {field} differs from manifest")
    edge = arrays["outer_edge_ring"].astype(bool)
    if edge.sum() != 1028 or not np.array_equal(edge, (arrays["i_zero_based"] == 0) | (arrays["i_zero_based"] == 233) | (arrays["j_zero_based"] == 0) | (arrays["j_zero_based"] == 281)):
        raise ValueError("outer one-cell ring mapping differs from 1,028 native columns")
    edge_support = int(mask[edge].sum())
    interior_support = int(mask[~edge].sum())

    computed_reason_counts = {name: int(np.count_nonzero(reason_code == i)) for i, name in enumerate(REASON_LABELS)}
    if computed_reason_counts != manifest["row_reason_counts"]:
        raise ValueError("canonical row reason counts differ from the public manifest")

    observed_requests = manifest["request_ledger"]
    if observed_requests["direct_request_count_including_4_reused_pilots"] != 130 or observed_requests["successful_unique_chunk_results"] != 129:
        raise ValueError("direct-request provenance count differs from frozen run")
    return {
        "status": "PUBLIC_PACKET_ARITHMETIC_REPLAY_PASSED",
        "replay_source_sha256": replay_source_sha,
        "packet_sha256": packet_sha,
        "columns": int(flat.size),
        "unique_source_owner_ids": int(np.unique(owner).size),
        "raw_ko_coverage_all7_columns": int(arrays["source_ko_coverage_all7"].sum()),
        "source_valid_cells_by_channel": source_valid.sum(axis=0).astype(int).tolist(),
        "profile_valid_rows": int(profile_valid.sum()),
        "row_reason_counts": {name: int(np.count_nonzero(reason_code == i)) for i, name in enumerate(REASON_LABELS)},
        "support_Z": Z,
        "channel_support": channel_coverage,
        "huber_observation_numerator": huber_num,
        "global_cost": cost,
        "per_channel": per_channel,
        "per_chunk_support_cells": [int(sum(row)) for row in chunk_support],
        "per_chunk_huber_numerators": chunk_num,
        "edge_interior_support_cells": {"edge": edge_support, "interior": interior_support},
        "direct_requests": observed_requests,
        "scope": "Offline arithmetic only: no RTTOV, KDM, host, cleanup, finish, or optimizer calls.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).with_name("manifest.json"),
        help="packet manifest (defaults to this evidence directory)",
    )
    args = parser.parse_args()
    try:
        result = replay(args.manifest)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
    except Exception as exc:
        print(json.dumps({"status": "PUBLIC_PACKET_ARITHMETIC_REPLAY_FAILED", "error": f"{type(exc).__name__}: {exc}"}, sort_keys=True))
        raise


if __name__ == "__main__":
    main()
