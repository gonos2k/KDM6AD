#!/usr/bin/env python3
"""Offline per-species accounting of saved post-microphysics endpoint changes.

Reads only the already saved actual-QR B512 comparison arrays. It makes no
KDM, WRF, RTTOV, or optimizer calls, and it does not attribute net endpoint
changes to named internal processes.
"""

from __future__ import annotations

import argparse
from io import BytesIO
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EVIDENCE_ROOT = ROOT / "harness/evidence/actual_qr_transport_2026-10-24"
DEFAULT_OUTPUT = (
    ROOT
    / "harness/evidence/saved_candidate_attribution_2026-10-24/post_micro_attribution.json"
)
CHUNKS = (34, 40)
BATCH = 512
LEVELS = 39
GLOBAL_SUBSTEPS = 5
NX = 234
SPECIES = ("QV", "QC", "QR", "QI", "QS", "QG")
GROUPS = {"vapor": (0,), "liquid": (1, 2), "ice": (3, 4, 5)}
HOT_COUNT = 5


class AttributionError(ValueError):
    """Saved stage arrays, orientation, or provenance pins are invalid."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _f64(name: str, value: np.ndarray, shape: tuple[int, ...]) -> np.ndarray:
    if not isinstance(value, np.ndarray) or value.dtype != np.float64:
        raise AttributionError(f"{name} must be a float64 ndarray")
    if value.shape != shape:
        raise AttributionError(f"{name} must have shape {shape}, got {value.shape}")
    if not np.isfinite(value).all():
        raise AttributionError(f"{name} contains nonfinite values")
    return value


def _same_bits(left: np.ndarray, right: np.ndarray) -> bool:
    a = np.ascontiguousarray(left, dtype=np.float64)
    b = np.ascontiguousarray(right, dtype=np.float64)
    return a.shape == b.shape and a.tobytes() == b.tobytes()


def distribution(values: np.ndarray) -> dict:
    """Unweighted column distribution; quantiles select sorted ranks."""
    data = np.asarray(values, dtype=np.float64).reshape(-1)
    if not data.size or not np.isfinite(data).all():
        raise AttributionError("statistics require finite nonempty values")
    ordered = np.sort(data, kind="stable")
    return {
        "count": int(data.size),
        "min": float(ordered[0]),
        "max": float(ordered[-1]),
        "unweighted_column_mean": math.fsum(float(x) for x in data) / data.size,
        "rank_p01": float(ordered[int(0.01 * (data.size - 1))]),
        "rank_p50": float(ordered[int(0.50 * (data.size - 1))]),
        "rank_p99": float(ordered[int(0.99 * (data.size - 1))]),
    }


def rounded_post_micro_products(
    water_stages_bottomfirst: np.ndarray,
    rho_topfirst_steps: np.ndarray,
    dz_topfirst_steps: np.ndarray,
) -> dict:
    """Return post_sed→post_micro rounded products and fsum reductions.

    Water stages use ``(stage,species,column,bottom_level)`` order. The QR
    trace carries ``(global_step,column,top_level)`` geometry, so the first
    trace measure is explicitly reversed into bottom-first WRF state order.
    Net total change is one flat fsum of the already-rounded species×level
    products in species-major, level-major order. Species, group and layer
    subtotals are reported independently; their additional reductions may
    differ by a small, bounded binary64 arithmetic remainder.
    """
    stages = np.asarray(water_stages_bottomfirst)
    if (
        not isinstance(water_stages_bottomfirst, np.ndarray)
        or stages.dtype != np.float64
        or stages.ndim != 4
        or stages.shape[0:2] != (3, len(SPECIES))
        or stages.shape[2] <= 0
        or stages.shape[3] <= 0
    ):
        raise AttributionError(
            "water_stages_bottomfirst must be float64 shape (3,6,B,L), B,L > 0"
        )
    batch, levels = stages.shape[2:]
    if not np.isfinite(stages).all():
        raise AttributionError("water_stages_bottomfirst contains nonfinite values")
    rho_steps = _f64(
        "rho_topfirst_steps", rho_topfirst_steps, (GLOBAL_SUBSTEPS, batch, levels)
    )
    dz_steps = _f64(
        "dz_topfirst_steps", dz_topfirst_steps, (GLOBAL_SUBSTEPS, batch, levels)
    )
    if not _same_bits(rho_steps, np.broadcast_to(rho_steps[:1], rho_steps.shape)):
        raise AttributionError("rho changes across global substeps")
    if not _same_bits(dz_steps, np.broadcast_to(dz_steps[:1], dz_steps.shape)):
        raise AttributionError("dz changes across global substeps")
    if np.any(rho_steps <= 0.0) or np.any(dz_steps <= 0.0):
        raise AttributionError("rho and dz must be strictly positive")

    rho_bottomfirst = rho_steps[0, :, ::-1].copy()
    dz_bottomfirst = dz_steps[0, :, ::-1].copy()
    measure = rho_bottomfirst * dz_bottomfirst
    # Keep the subtraction and multiplication as explicit rounded binary64
    # NumPy operations; only the reductions use math.fsum.
    state_delta = stages[2] - stages[1]
    products = state_delta * measure[None, :, :]
    species_delta = np.asarray(
        [
            [
                math.fsum(
                    float(products[field, column, level]) for level in range(levels)
                )
                for column in range(batch)
            ]
            for field in range(len(SPECIES))
        ],
        dtype=np.float64,
    )
    # Accepted candidate-analyzer contract: one flat fsum of all rounded
    # species×level terms per column, field-major then bottomfirst-level-major.
    net_total = np.asarray(
        [
            math.fsum(
                float(products[field, column, level])
                for field in range(len(SPECIES))
                for level in range(levels)
            )
            for column in range(batch)
        ],
        dtype=np.float64,
    )
    layer_net = np.asarray(
        [
            [
                math.fsum(
                    float(products[field, column, level])
                    for field in range(len(SPECIES))
                )
                for level in range(levels)
            ]
            for column in range(batch)
        ],
        dtype=np.float64,
    )
    layer_gross = np.asarray(
        [
            [
                math.fsum(
                    abs(float(products[field, column, level]))
                    for field in range(len(SPECIES))
                )
                for level in range(levels)
            ]
            for column in range(batch)
        ],
        dtype=np.float64,
    )

    group_delta = {
        group: np.asarray(
            [
                math.fsum(
                    float(species_delta[field, column]) for field in field_indices
                )
                for column in range(batch)
            ],
            dtype=np.float64,
        )
        for group, field_indices in GROUPS.items()
    }
    group_layer = {
        group: np.asarray(
            [
                [
                    math.fsum(
                        float(products[field, column, level]) for field in field_indices
                    )
                    for level in range(levels)
                ]
                for column in range(batch)
            ],
            dtype=np.float64,
        )
        for group, field_indices in GROUPS.items()
    }
    gross_species = np.asarray(
        [
            math.fsum(abs(float(species_delta[field, column])) for field in range(6))
            for column in range(batch)
        ],
        dtype=np.float64,
    )
    gross_groups = np.asarray(
        [
            math.fsum(abs(float(group_delta[group][column])) for group in GROUPS)
            for column in range(batch)
        ],
        dtype=np.float64,
    )
    gross_layer_products = np.asarray(
        [
            math.fsum(
                abs(float(products[field, column, level]))
                for field in range(len(SPECIES))
                for level in range(levels)
            )
            for column in range(batch)
        ],
        dtype=np.float64,
    )
    net_over_gross_species = np.divide(
        np.abs(net_total),
        gross_species,
        out=np.zeros_like(net_total),
        where=gross_species > 0,
    )
    net_over_gross_groups = np.divide(
        np.abs(net_total),
        gross_groups,
        out=np.zeros_like(net_total),
        where=gross_groups > 0,
    )
    net_over_gross_layer = np.divide(
        np.abs(net_total),
        gross_layer_products,
        out=np.zeros_like(net_total),
        where=gross_layer_products > 0,
    )

    species_hierarchical_total = np.asarray(
        [
            math.fsum(float(species_delta[field, column]) for field in range(6))
            for column in range(batch)
        ],
        dtype=np.float64,
    )
    group_hierarchical_total = np.asarray(
        [
            math.fsum(float(group_delta[group][column]) for group in GROUPS)
            for column in range(batch)
        ],
        dtype=np.float64,
    )
    layer_hierarchical_total = np.asarray(
        [
            math.fsum(float(layer_net[column, level]) for level in range(levels))
            for column in range(batch)
        ],
        dtype=np.float64,
    )
    abs_products = np.asarray(
        [
            math.fsum(
                abs(float(products[field, column, level]))
                for field in range(len(SPECIES))
                for level in range(levels)
            )
            for column in range(batch)
        ],
        dtype=np.float64,
    )
    eps = np.finfo(np.float64).eps
    # Arithmetic-only envelope for the extra subtotal reductions. This is not
    # a physical conservation threshold and is never used to classify closure.
    regrouping_bound = 8.0 * eps * np.maximum(abs_products, np.finfo(np.float64).tiny)
    species_remainder = net_total - species_hierarchical_total
    group_remainder = net_total - group_hierarchical_total
    layer_remainder = net_total - layer_hierarchical_total
    if any(
        np.any(np.abs(remainder) > regrouping_bound)
        for remainder in (species_remainder, group_remainder, layer_remainder)
    ):
        raise AttributionError(
            "subtotal regrouping remainder exceeds arithmetic envelope"
        )

    return {
        "weights_bottomfirst": measure,
        "state_delta_bottomfirst": state_delta,
        "rounded_products_bottomfirst": products,
        "species_delta_kg_m2": species_delta,
        "net_total_kg_m2": net_total,
        "group_delta_kg_m2": group_delta,
        "group_layer_delta_kg_m2": group_layer,
        "layer_net_kg_m2": layer_net,
        "layer_gross_abs_species_kg_m2": layer_gross,
        "gross_abs_species_delta_kg_m2": gross_species,
        "gross_abs_group_delta_kg_m2": gross_groups,
        "gross_abs_layer_products_kg_m2": gross_layer_products,
        "net_over_gross_species": net_over_gross_species,
        "net_over_gross_groups": net_over_gross_groups,
        "net_over_gross_layer": net_over_gross_layer,
        "species_regrouping_remainder_kg_m2": species_remainder,
        "group_regrouping_remainder_kg_m2": group_remainder,
        "layer_regrouping_remainder_kg_m2": layer_remainder,
        "regrouping_arithmetic_bound_kg_m2": regrouping_bound,
        "absolute_rounded_products_sum_kg_m2": abs_products,
    }


def _index_record(chunk: int, local: int) -> dict:
    flat = chunk * BATCH + local
    return {
        "chunk": int(chunk),
        "local_column": int(local),
        "flat_index": int(flat),
        "i_1based": int(flat % NX + 1),
        "j_1based": int(flat // NX + 1),
    }


def _column_record(column: int, chunk: int, values: dict) -> dict:
    species = values["species_delta_kg_m2"]
    groups = values["group_delta_kg_m2"]
    net = float(values["net_total_kg_m2"][column])
    gross_species = float(values["gross_abs_species_delta_kg_m2"][column])
    gross_layer = float(values["gross_abs_layer_products_kg_m2"][column])
    top_species = sorted(
        range(len(SPECIES)),
        key=lambda field: (-abs(float(species[field, column])), field),
    )[:3]
    layer_gross = values["layer_gross_abs_species_kg_m2"][column]
    layer_net = values["layer_net_kg_m2"][column]
    dominant_exchange = sorted(
        range(LEVELS), key=lambda level: (-float(layer_gross[level]), level)
    )[:5]
    dominant_net = sorted(
        range(LEVELS), key=lambda level: (-abs(float(layer_net[level])), level)
    )[:5]

    def layer_details(level: int) -> dict:
        return {
            "level_bottom0": int(level),
            "level_top0": int(LEVELS - 1 - level),
            "net_layer_change_kg_m2": float(layer_net[level]),
            "gross_abs_species_change_kg_m2": float(layer_gross[level]),
            "species_rounded_products_kg_m2": {
                SPECIES[field]: float(
                    values["rounded_products_bottomfirst"][field, column, level]
                )
                for field in range(len(SPECIES))
            },
            "group_rounded_products_kg_m2": {
                group: float(values["group_layer_delta_kg_m2"][group][column, level])
                for group in GROUPS
            },
        }

    return {
        **_index_record(chunk, column),
        "species_net_inventory_change_kg_m2": {
            SPECIES[field]: float(species[field, column])
            for field in range(len(SPECIES))
        },
        "group_net_inventory_change_kg_m2": {
            group: float(groups[group][column]) for group in GROUPS
        },
        "joint_flat_fsum_net_kg_m2": net,
        "gross_abs_species_increment_sum_kg_m2": gross_species,
        "gross_abs_layer_species_product_sum_kg_m2": gross_layer,
        "cancelled_species_increment_magnitude_kg_m2": gross_species - abs(net),
        "cancelled_layer_product_magnitude_kg_m2": gross_layer - abs(net),
        "net_over_gross_species_fraction": float(
            values["net_over_gross_species"][column]
        ),
        "net_over_gross_group_fraction": float(values["net_over_gross_groups"][column]),
        "net_over_gross_layer_product_fraction": float(
            values["net_over_gross_layer"][column]
        ),
        "top_species_by_abs_net_increment": [SPECIES[field] for field in top_species],
        "dominant_levels_by_gross_exchange": [
            layer_details(level) for level in dominant_exchange
        ],
        "dominant_levels_by_abs_net": [layer_details(level) for level in dominant_net],
    }


def _case_summary(chunk: int, arrays: dict, values: dict, source_info: dict) -> dict:
    stages = arrays["water_stages_bottomfirst"]
    negative = {
        stage_name: {
            SPECIES[field]: int(np.count_nonzero(stages[stage_index, field] < 0.0))
            for field in range(len(SPECIES))
        }
        for stage_index, stage_name in enumerate(("pre_sed", "post_sed", "post_micro"))
    }
    hot_exchange = sorted(
        range(BATCH),
        key=lambda col: (-float(values["gross_abs_layer_products_kg_m2"][col]), col),
    )[:HOT_COUNT]
    hot_net = sorted(
        range(BATCH), key=lambda col: (-abs(float(values["net_total_kg_m2"][col])), col)
    )[:HOT_COUNT]
    cleanup = arrays["actual_cleanup"]
    return {
        "chunk": int(chunk),
        "B": BATCH,
        "L": LEVELS,
        "stage_transition": "post_sed to post_micro",
        "species_order": list(SPECIES),
        "state_orientation": "bottomfirst; source rho/dz trace is topfirst and explicitly reversed",
        "rho_dz_measure_bottomfirst_kg_m2": "rho_dry_kg_m3 * delz_m from the actual request trace, fixed over five substeps",
        "source": source_info,
        "stored_micro_total_change_bitwise_matches_joint_fsum": True,
        "net_six_species_inventory_change_kg_m2": distribution(
            values["net_total_kg_m2"]
        ),
        "species_net_inventory_change_kg_m2": {
            SPECIES[field]: distribution(values["species_delta_kg_m2"][field])
            for field in range(len(SPECIES))
        },
        "vapor_liquid_ice_group_net_inventory_change_kg_m2": {
            group: distribution(delta)
            for group, delta in values["group_delta_kg_m2"].items()
        },
        "gross_abs_species_increment_sum_kg_m2": distribution(
            values["gross_abs_species_delta_kg_m2"]
        ),
        "gross_abs_layer_species_product_sum_kg_m2": distribution(
            values["gross_abs_layer_products_kg_m2"]
        ),
        "gross_abs_vapor_liquid_ice_group_increment_sum_kg_m2": distribution(
            values["gross_abs_group_delta_kg_m2"]
        ),
        "net_over_gross_species_fraction": distribution(
            values["net_over_gross_species"]
        ),
        "net_over_gross_group_fraction": distribution(values["net_over_gross_groups"]),
        "net_over_gross_layer_product_fraction": distribution(
            values["net_over_gross_layer"]
        ),
        "rounded_reduction_remainders_kg_m2": {
            "species_subtotals_then_fsum_minus_joint_flat_fsum": distribution(
                values["species_regrouping_remainder_kg_m2"]
            ),
            "vapor_liquid_ice_subtotals_then_fsum_minus_joint_flat_fsum": distribution(
                values["group_regrouping_remainder_kg_m2"]
            ),
            "layer_subtotals_then_fsum_minus_joint_flat_fsum": distribution(
                values["layer_regrouping_remainder_kg_m2"]
            ),
            "arithmetic_only_bound": distribution(
                values["regrouping_arithmetic_bound_kg_m2"]
            ),
            "max_abs_species_remainder": float(
                np.max(np.abs(values["species_regrouping_remainder_kg_m2"]))
            ),
            "max_abs_group_remainder": float(
                np.max(np.abs(values["group_regrouping_remainder_kg_m2"]))
            ),
            "max_abs_layer_remainder": float(
                np.max(np.abs(values["layer_regrouping_remainder_kg_m2"]))
            ),
            "note": "Rounded products are identical; per-species/group/layer subtotal reductions can differ from the joint flat fsum by bounded binary64 arithmetic. This is not a physical conservation tolerance.",
        },
        "hot_columns_by_gross_layer_species_increment": [
            _column_record(column, chunk, values) for column in hot_exchange
        ],
        "largest_abs_net_columns": [
            _column_record(column, chunk, values) for column in hot_net
        ],
        "selected_qr_witness_post_micro_attribution": _column_record(
            int(source_info["selected_witness"]["local_column"]), chunk, values
        ),
        "negative_state_counts_by_stage": negative,
        "offline_uniform_cleanup_separate": {
            "included_in_post_micro_transition": False,
            "source_field": "actual_cleanup",
            "unweighted_column_change_kg_m2": distribution(cleanup),
            "note": "This saved offline cleanup diagnostic is separate; it is not added to post_sed→post_micro changes.",
        },
        "physical_water_budget_closed": False,
        "interpretation_limits": [
            "These are endpoint state-inventory increments at fixed request rho*dz, not causal process rates or named-process attribution.",
            "QV/liquid/ice cancellation is an arithmetic summary of opposing species increments, not proof of a particular phase-transfer mechanism.",
            "No closed physical water budget, RK/area-weighted total, native-host step, RTTOV cost, or forecast metric is computed here.",
        ],
    }


def analyze(
    evidence_root: Path = EVIDENCE_ROOT,
    output: Path = DEFAULT_OUTPUT,
    manifest_path: Path | None = None,
    comparison_path: Path | None = None,
) -> dict:
    """Validate two saved chunk archives and write a new offline summary."""
    evidence_root = Path(evidence_root)
    output = Path(output)
    manifest_path = (
        Path(manifest_path)
        if manifest_path is not None
        else evidence_root / "manifest.json"
    )
    comparison_path = (
        Path(comparison_path)
        if comparison_path is not None
        else evidence_root / "block_comparison.json"
    )
    if output.exists() or output.is_symlink():
        raise AttributionError(f"output must be a new file: {output}")
    manifest_bytes = manifest_path.read_bytes()
    comparison_bytes = comparison_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    comparison = json.loads(comparison_bytes)
    if comparison.get("schema") != "kdm6.actual_qr_comparison.v1":
        raise AttributionError("candidate comparison schema differs")
    if comparison.get("model_calls_added") != 0:
        raise AttributionError("saved comparison claims additional model calls")
    if tuple(row.get("chunk") for row in comparison.get("cases", ())) != CHUNKS:
        raise AttributionError(
            "comparison cases must cover the two frozen chunks in order"
        )
    manifest_artifacts = manifest.get("artifact_sha256", {})
    comparison_rel = (
        "harness/evidence/actual_qr_transport_2026-10-24/block_comparison.json"
    )
    if manifest_artifacts.get(comparison_rel) != sha256_bytes(comparison_bytes):
        raise AttributionError("block comparison differs from pinned artifact hash")
    manifest_hash = sha256_bytes(manifest_bytes)
    comparison_hash = sha256_bytes(comparison_bytes)
    producer_hash = sha256_file(Path(__file__))
    cases = {}
    input_hashes = {
        str(manifest_path): manifest_hash,
        str(comparison_path): comparison_hash,
    }
    for row in comparison["cases"]:
        chunk = int(row["chunk"])
        if (row.get("B"), row.get("L"), row.get("global_steps")) != (
            BATCH,
            LEVELS,
            GLOBAL_SUBSTEPS,
        ):
            raise AttributionError(f"chunk {chunk} dimensions/global steps differ")
        archive_path = evidence_root / f"chunk{chunk:03d}.npz"
        archive_bytes = archive_path.read_bytes()
        archive_hash = sha256_bytes(archive_bytes)
        if archive_hash != row.get("array_sha256"):
            raise AttributionError(
                f"chunk {chunk} archive hash differs from comparison"
            )
        expected_rel = (
            f"harness/evidence/actual_qr_transport_2026-10-24/chunk{chunk:03d}.npz"
        )
        if manifest_artifacts.get(expected_rel) != archive_hash:
            raise AttributionError(
                f"chunk {chunk} archive differs from pinned manifest"
            )
        with np.load(BytesIO(archive_bytes), allow_pickle=False) as source:
            arrays = {name: source[name].copy() for name in source.files}
        required = {
            "water_stages_bottomfirst",
            "rho",
            "dz",
            "micro_total_change",
            "actual_cleanup",
            "actual_state_in",
            "actual_state_out",
            "q_after",
            "mstep",
            "gate",
            "n",
            "k_top0",
            "column",
        }
        if not required.issubset(arrays):
            raise AttributionError(f"chunk {chunk} is missing required arrays")
        stages = _f64(
            "water_stages_bottomfirst",
            arrays["water_stages_bottomfirst"],
            (3, 6, BATCH, LEVELS),
        )
        rho = _f64("rho", arrays["rho"], (GLOBAL_SUBSTEPS, BATCH, LEVELS))
        dz = _f64("dz", arrays["dz"], (GLOBAL_SUBSTEPS, BATCH, LEVELS))
        _f64("micro_total_change", arrays["micro_total_change"], (BATCH,))
        _f64("actual_cleanup", arrays["actual_cleanup"], (BATCH,))
        state_in = _f64(
            "actual_state_in", arrays["actual_state_in"], (12, BATCH, LEVELS)
        )
        state_out = _f64(
            "actual_state_out", arrays["actual_state_out"], (12, BATCH, LEVELS)
        )
        q_after = _f64("q_after", arrays["q_after"], (GLOBAL_SUBSTEPS, BATCH, LEVELS))
        if not _same_bits(stages[0], state_in[1:7]):
            raise AttributionError(
                f"chunk {chunk} pre_sed stage differs from K request water state"
            )
        if not _same_bits(stages[2], state_out[1:7]):
            raise AttributionError(
                f"chunk {chunk} post_micro stage differs from K response water state"
            )
        if not _same_bits(stages[1, 2], q_after[-1, :, ::-1]):
            raise AttributionError(
                f"chunk {chunk} post_sed QR differs from actual QR trace endpoint"
            )
        if not _same_bits(rho, np.broadcast_to(rho[:1], rho.shape)):
            raise AttributionError(f"chunk {chunk} rho varies across substeps")
        if not _same_bits(dz, np.broadcast_to(dz[:1], dz.shape)):
            raise AttributionError(f"chunk {chunk} dz varies across substeps")
        if not np.array_equal(
            arrays["n"],
            np.broadcast_to(
                np.arange(1, GLOBAL_SUBSTEPS + 1)[:, None, None], arrays["n"].shape
            ),
        ):
            raise AttributionError(f"chunk {chunk} global trace substeps/order differ")
        if not np.array_equal(
            arrays["k_top0"],
            np.broadcast_to(np.arange(LEVELS)[None, None, :], arrays["k_top0"].shape),
        ):
            raise AttributionError(f"chunk {chunk} trace level order differs")
        if not np.array_equal(
            arrays["column"],
            np.broadcast_to(np.arange(BATCH)[None, :, None], arrays["column"].shape),
        ):
            raise AttributionError(f"chunk {chunk} trace column order differs")
        values = rounded_post_micro_products(stages, rho, dz)
        if not _same_bits(values["net_total_kg_m2"], arrays["micro_total_change"]):
            raise AttributionError(
                f"chunk {chunk} joint fsum differs from stored micro_total_change"
            )
        target_local = 254 if chunk == 34 else 8
        if int(row.get("local_steps_at_witness", -1)) != int(
            arrays["mstep"][0, target_local, 0]
        ):
            raise AttributionError(
                f"chunk {chunk} local witness mstep differs from saved comparison"
            )
        info = {
            "archive": archive_path.name,
            "archive_sha256": archive_hash,
            "comparison_source_sha256": row.get("source_sha256"),
            "selected_witness": _index_record(chunk, target_local),
            "selected_witness_mstep": int(row["local_steps_at_witness"]),
            "source_measure_orientation_check": "topfirst trace rho/dz was bitwise constant across five steps and reversed to bottomfirst state levels",
            "endpoint_checks": {
                "pre_sed_matches_candidate_request_water_bits": True,
                "post_micro_matches_candidate_response_water_bits": True,
                "post_sed_QR_matches_candidate_trace_endpoint_bits": True,
            },
        }
        cases[str(chunk)] = _case_summary(chunk, arrays, values, info)
        input_hashes[str(archive_path)] = archive_hash
    result = {
        "schema": "kdm6.saved_candidate_post_micro_attribution.v1",
        "source_main": "3f3899b474e51d814988a5ac24fbf22cb2c42bba",
        "producer_sha256": producer_hash,
        "source_hashes": input_hashes,
        "model_calls_added": 0,
        "native_host_steps": 0,
        "RTTOV_calls": 0,
        "whole_domain_repeats": 0,
        "measure_contract": "Rounded binary64 (post_micro-post_sed)*rho_dry*DELZ products; joint net is one fsum in species-major/level-major order; all spatial summaries are unweighted column statistics.",
        "species_order": list(SPECIES),
        "grouping": {
            name: [SPECIES[index] for index in indices]
            for name, indices in GROUPS.items()
        },
        "cases": cases,
        "overall_limits": [
            "Endpoint species increments are net stage changes, not causal named-process rates.",
            "QV/liquid/ice cancellation is a diagnostic reduction of species endpoints, not proof of a particular phase-transfer mechanism.",
            "Post-sed→post-micro accounting excludes the separately reported offline host-cleanup reference and does not certify a closed physical water budget.",
            "No cell-area weighting, RK transport, native-host step, RTTOV observation cost, or forecast metric is computed here.",
        ],
    }
    if sha256_file(Path(__file__)) != producer_hash:
        raise AttributionError("producer source changed during analysis")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, default=EVIDENCE_ROOT)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--comparison", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    result = analyze(args.evidence_root, args.output, args.manifest, args.comparison)
    print(
        json.dumps({"cases": list(result["cases"]), "model_calls_added": 0}, indent=2)
    )


if __name__ == "__main__":
    main()
