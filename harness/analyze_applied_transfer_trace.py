"""Offline accounting for selected saved KDM applied-transfer trace cells.

Reads a long-form TSV emitted by the private trace harness. It does not run a
model or reconstruct uncaptured process rates. Endpoint changes, limiter-scaled
rates, nominal signed pair transfers, and threshold cleanup remain separate.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np


EXPECTED_COLUMNS = (
    (34, 281, 17),
    (34, 281, 18),
    (40, 250, 17),
)
HEADER = (
    "call",
    "stage",
    "group",
    "chunk",
    "column",
    "level_bottom0",
    "dt",
    "field",
    "value",
)
WATER_FIELDS = ("qv", "qc", "qr", "qi", "qs", "qg")
RATE_FIELDS = ("psdep", "pgdep", "psevp", "pgevp")
SNAPSHOT_STAGES = (
    "micro_entry",
    "pre_limits",
    "post_limits",
    "state_update_raw",
    "post_state_update",
    "post_reclass_ice",
    "post_reclass_rain",
    "post_satadj",
    "post_threshold",
    "micro_exit",
)
LIMITER_STAGES = ("limiter_before", "limiter_after")
LIMITER_GROUPS = tuple(str(value) for value in range(1, 15))
LIMITER_FIELDS = frozenset((*RATE_FIELDS, "value", "source", "factor", "gate"))
LIMITER_BUDGETS = {
    "1": ("cold_mass_qc", "mass mixing ratio kg/kg"),
    "2": ("cold_mass_qi", "mass mixing ratio kg/kg"),
    "3": ("cold_mass_qr", "mass mixing ratio kg/kg"),
    "4": ("cold_mass_qs", "mass mixing ratio kg/kg"),
    "5": ("cold_mass_qg", "mass mixing ratio kg/kg"),
    "6": ("cold_number_nc", "number-state coordinate; physical basis unverified"),
    "7": ("cold_number_ni", "number-state coordinate; physical basis unverified"),
    "8": ("cold_number_nr", "number-state coordinate; physical basis unverified"),
    "9": ("warm_mass_qc", "mass mixing ratio kg/kg"),
    "10": ("warm_mass_qr", "mass mixing ratio kg/kg"),
    "11": ("warm_mass_qs", "mass mixing ratio kg/kg"),
    "12": ("warm_mass_qg", "mass mixing ratio kg/kg"),
    "13": ("warm_number_nc", "number-state coordinate; physical basis unverified"),
    "14": ("warm_number_nr", "number-state coordinate; physical basis unverified"),
}
TRANSFER_ENDPOINTS = {
    "psdep": ("qv", "qs", "cold_mask"),
    "pgdep": ("qv", "qg", "cold_mask"),
    "psevp": ("qv", "qs", "warm_mask"),
    "pgevp": ("qv", "qg", "warm_mask"),
}
REFERENCE_MANIFEST = Path(
    "harness/evidence/actual_qr_transport_2026-10-24/manifest.json"
)
REFERENCE_NPZ_HASHES = {
    "chunk034.npz": "8e0341ab5a296332d176ddd6b9d773210f1d4a066c91081c4aa4e181ce3adf8d",
    "chunk040.npz": "eaf3bb7c001ae8b03ab7d5864c0ee2e3e24c50b9e79ecd47c17303c64ccc16c8",
}


class TraceError(ValueError):
    """Malformed or incomplete saved trace."""


def _value(text, key):
    normalized = text.strip().lower()
    if normalized in ("true", "false"):
        return normalized == "true"
    try:
        number = float(text)
    except ValueError as exc:
        raise TraceError(f"{key} must be numeric or boolean") from exc
    if not math.isfinite(number):
        raise TraceError(f"{key} must be finite")
    return number


def parse_trace(data: bytes):
    """Parse unique call/stage/group/cell/field rows from the fixed TSV schema."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TraceError("trace must be UTF-8 TSV") from exc
    reader = csv.DictReader(text.splitlines(), delimiter="\t")
    if tuple(reader.fieldnames or ()) != HEADER:
        raise TraceError(f"trace header must be exactly {HEADER}")
    cells = {}
    for line, row in enumerate(reader, start=2):
        try:
            call = int(row["call"])
            stage = row["stage"].strip()
            group = row["group"].strip()
            chunk = int(row["chunk"])
            column = int(row["column"])
            level = int(row["level_bottom0"])
            dt = float(row["dt"])
            field = row["field"].strip()
            value = _value(row["value"], f"line {line} value")
        except TraceError:
            raise
        except (TypeError, ValueError) as exc:
            raise TraceError(f"invalid row metadata at line {line}") from exc
        if not stage or not field or not math.isfinite(dt) or dt <= 0.0:
            raise TraceError(f"invalid stage/field/dt at line {line}")
        if call < 1:
            raise TraceError(
                f"call index must be a positive subcycle ordinal at line {line}"
            )
        if stage not in SNAPSHOT_STAGES and stage not in LIMITER_STAGES:
            raise TraceError(f"unknown v1 stage {stage!r} at line {line}")
        if stage in SNAPSHOT_STAGES and group != "0":
            raise TraceError(f"non-limiter stage {stage!r} must use group 0")
        if stage in LIMITER_STAGES and group not in LIMITER_GROUPS:
            raise TraceError(f"limiter stage {stage!r} requires group 1..14")
        target = (chunk, column, level)
        key = (call, stage, group, target)
        fields = cells.setdefault(key, {})
        if field in fields:
            raise TraceError(f"duplicate field {field!r} at line {line}")
        fields[field] = value
        row_dt = cells.setdefault((call, "__dt__", "", target), {})
        prior_dt = row_dt.setdefault("dt", dt)
        if prior_dt != dt:
            raise TraceError(f"dt changed within call {call} target {target}")
    if not cells:
        raise TraceError("trace contains no data rows")
    return cells


def _one_stage(cells, call, stage, target, *, group="0"):
    key = (call, stage, group, target)
    try:
        return cells[key]
    except KeyError as exc:
        raise TraceError(
            f"missing stage {stage!r}, group {group!r}, call={call}, target={target}"
        ) from exc


def _water_total(snapshot):
    missing = set(WATER_FIELDS) - set(snapshot)
    if missing:
        raise TraceError(f"water snapshot missing fields {sorted(missing)}")
    return math.fsum(float(snapshot[field]) for field in WATER_FIELDS)


def _stage_change(before, after):
    deltas = {
        field: float(after[field]) - float(before[field]) for field in WATER_FIELDS
    }
    before_total = _water_total(before)
    after_total = _water_total(after)
    delta_from_fields = math.fsum(deltas[field] for field in WATER_FIELDS)
    inventory_subtraction = after_total - before_total
    return {
        "field_delta_kg_kg": deltas,
        "water_total_delta_kg_kg": delta_from_fields,
        "water_total_delta_from_inventory_subtraction_kg_kg": inventory_subtraction,
        "water_total_delta_cancellation_remainder_kg_kg": inventory_subtraction
        - delta_from_fields,
        "water_total_before_kg_kg": before_total,
        "water_total_after_kg_kg": after_total,
    }


def _weighted_stage_change(before, after, weight):
    result = _stage_change(before, after)
    result["water_total_before_kg_m2_local_level"] = (
        result["water_total_before_kg_kg"] * weight
    )
    result["water_total_after_kg_m2_local_level"] = (
        result["water_total_after_kg_kg"] * weight
    )
    result["water_total_delta_kg_m2_local_level"] = math.fsum(
        float(weight) * float(result["field_delta_kg_kg"][field])
        for field in WATER_FIELDS
    )
    result["water_total_delta_from_inventory_subtraction_kg_m2_local_level"] = (
        result["water_total_delta_from_inventory_subtraction_kg_kg"] * weight
    )
    result["water_total_delta_cancellation_remainder_kg_m2_local_level"] = (
        result["water_total_delta_from_inventory_subtraction_kg_m2_local_level"]
        - result["water_total_delta_kg_m2_local_level"]
    )
    result["fixed_entry_dry_mass_weight_kg_m2"] = weight
    return result


def _transfer_ledger(raw_stage, dt):
    masks = {}
    for mask_name in ("cold_mask", "warm_mask"):
        if mask_name not in raw_stage:
            raise TraceError(f"state_update_raw missing {mask_name}")
        masks[mask_name] = float(raw_stage[mask_name])
        if masks[mask_name] not in (0.0, 1.0):
            raise TraceError(f"state_update_raw {mask_name} must be 0 or 1")
    if masks["cold_mask"] + masks["warm_mask"] != 1.0:
        raise TraceError("cold_mask and warm_mask must select exactly one branch")
    transfers = {}
    for name, (donor, receiver, mask_name) in TRANSFER_ENDPOINTS.items():
        if name not in raw_stage:
            raise TraceError(f"state_update_raw missing transfer rate {name}")
        signed_amount = float(raw_stage[name]) * masks[mask_name] * dt
        transfers[name] = {
            "selected_signed_rate_kg_kg_s": float(raw_stage[name]) * masks[mask_name],
            "nominal_signed_amount_kg_kg": signed_amount,
            "nominal_signed_endpoint_changes_kg_kg": {
                donor: -signed_amount,
                receiver: signed_amount,
            },
            "convention": "nominal signed rate*dt; not an isolated contribution to the rounded aggregate state update",
        }
    return transfers


def _limiter_ledger(cells, call, target):
    groups_by_stage = {
        stage: {
            group
            for row_call, row_stage, group, row_target in cells
            if row_call == call and row_stage == stage and row_target == target
        }
        for stage in LIMITER_STAGES
    }
    if any(groups != set(LIMITER_GROUPS) for groups in groups_by_stage.values()):
        raise TraceError(
            f"call {call} target {target} must contain limiter groups 1..14 both before and after"
        )
    details = []
    for group in LIMITER_GROUPS:
        pre = _one_stage(cells, call, "limiter_before", target, group=group)
        post = _one_stage(cells, call, "limiter_after", target, group=group)
        if set(pre) != LIMITER_FIELDS or set(post) != LIMITER_FIELDS:
            raise TraceError(
                f"limiter group {group} must have exact fields {sorted(LIMITER_FIELDS)}"
            )
        budget_name, coordinate = LIMITER_BUDGETS[group]
        details.append(
            {
                "group": group,
                "budget_name": budget_name,
                "coordinate": coordinate,
                "fields_before": pre,
                "fields_after": post,
                "captured_rate_field_delta": {
                    name: float(post[name]) - float(pre[name]) for name in RATE_FIELDS
                },
            }
        )
    return {
        "limiter_groups": details,
        "rate_names": list(RATE_FIELDS),
        "group_mapping": LIMITER_BUDGETS,
    }


def compare_reference_npz(data, npz_paths):
    """Bit-compare trace entry/exit state to the pinned earlier public NPZs."""
    if not npz_paths:
        return None
    if len(npz_paths) != 2:
        raise TraceError("supply exactly the chunk034 and chunk040 reference NPZs")
    repo_root = Path(__file__).resolve().parents[1]
    manifest_path = repo_root / REFERENCE_MANIFEST
    try:
        manifest = json.loads(manifest_path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise TraceError("pinned reference NPZ manifest is unavailable") from exc
    pinned = manifest.get("artifact_sha256", {})
    npz_by_chunk = {}
    for value in npz_paths:
        path = Path(value)
        name = path.name
        if name not in REFERENCE_NPZ_HASHES or name in npz_by_chunk:
            raise TraceError(
                "reference NPZ paths must be unique chunk034.npz/chunk040.npz"
            )
        expected = REFERENCE_NPZ_HASHES[name]
        relative = str(Path("harness/evidence/actual_qr_transport_2026-10-24") / name)
        if pinned.get(relative) != expected:
            raise TraceError(f"public manifest hash does not match pinned {name}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise TraceError(
                f"reference {name} does not match its pinned artifact hash"
            )
        npz_by_chunk[int(name[5:8])] = path
    if set(npz_by_chunk) != {34, 40}:
        raise TraceError("reference NPZ inputs must cover chunks 34 and 40")

    cells = {}
    for source in data if isinstance(data, (list, tuple)) else [data]:
        for key, fields in parse_trace(source).items():
            existing = cells.setdefault(key, {})
            overlap = set(existing) & set(fields)
            if overlap:
                raise TraceError("duplicate trace target while checking reference NPZ")
            existing.update(fields)
    by_call = sorted(
        {call for call, stage, group, target in cells if stage != "__dt__"}
    )
    results = []
    for call in by_call:
        for chunk, column, level in EXPECTED_COLUMNS:
            path = npz_by_chunk[chunk]
            with np.load(path, allow_pickle=False) as archive:
                if "water_stages_bottomfirst" not in archive:
                    raise TraceError(f"{path.name} lacks water_stages_bottomfirst")
                water = np.asarray(archive["water_stages_bottomfirst"])
                if water.shape != (3, 6, 512, 39) or water.dtype != np.float64:
                    raise TraceError(
                        f"{path.name} water stage array shape/dtype differs"
                    )
                top_level = 38 - level
                for field_index, field in enumerate(WATER_FIELDS):
                    for stage_name, npz_stage in (
                        ("micro_entry", 1),
                        ("micro_exit", 2),
                    ):
                        trace_value = np.float64(
                            _one_stage(cells, call, stage_name, (chunk, column, level))[
                                field
                            ]
                        )
                        expected_value = np.float64(
                            water[npz_stage, field_index, column, level]
                        )
                        if trace_value.tobytes() != expected_value.tobytes():
                            raise TraceError(
                                f"{path.name} {stage_name}.{field} differs bitwise at column={column}, level={level}"
                            )
                if "rho" not in archive or "dz" not in archive:
                    raise TraceError(f"{path.name} lacks rho/dz arrays")
                for trace_field, archive_name in (("rho", "rho"), ("delz", "dz")):
                    values = np.asarray(archive[archive_name])
                    if values.shape != (5, 512, 39) or values.dtype != np.float64:
                        raise TraceError(
                            f"{path.name} {archive_name} array shape/dtype differs"
                        )
                    actual = np.float64(
                        _one_stage(cells, call, "micro_entry", (chunk, column, level))[
                            trace_field
                        ]
                    )
                    expected = np.float64(values[0, column, top_level])
                    if actual.tobytes() != expected.tobytes():
                        raise TraceError(
                            f"{path.name} {trace_field} differs bitwise at column={column}, level={level}"
                        )
            results.append(
                {
                    "call_index": call,
                    "chunk": chunk,
                    "column": column,
                    "level_bottom0": level,
                    "water_entry_exit_bitwise_equal": True,
                    "rho_delz_entry_bitwise_equal": True,
                    "reference_npz": str(path),
                    "reference_npz_sha256": REFERENCE_NPZ_HASHES[path.name],
                    "level_mapping": "water_stages_bottomfirst directly; rho/dz topfirst index=38-level_bottom0",
                }
            )
    return {
        "manifest_path": str(REFERENCE_MANIFEST),
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "manifest_artifact_hash_pins_verified": True,
        "comparisons": results,
    }


def analyze_trace(
    data: bytes | list[bytes] | tuple[bytes, ...], *, reference_npz_paths=None
):
    """Create a per-call endpoint and nominal pair-transfer ledger.

    A sequence of trace byte strings joins independently traced chunks; each
    input has the fixed TSV header and disjoint target cells.
    """
    sources = list(data) if isinstance(data, (list, tuple)) else [data]
    if not sources:
        raise TraceError("at least one trace is required")
    cells = {}
    source_by_call_target = {}
    for source in sources:
        source_hash = hashlib.sha256(source).hexdigest()
        for key, fields in parse_trace(source).items():
            existing = cells.setdefault(key, {})
            overlap = set(existing) & set(fields)
            if overlap:
                raise TraceError(
                    f"duplicate trace rows while merging inputs: {sorted(overlap)}"
                )
            existing.update(fields)
            call, stage, group, target = key
            if stage != "__dt__":
                source_key = (call, target)
                prior_hash = source_by_call_target.setdefault(source_key, source_hash)
                if prior_hash != source_hash:
                    raise TraceError(
                        "one call/target appears in multiple trace sources"
                    )
    source_hashes = [hashlib.sha256(source).hexdigest() for source in sources]
    available_targets = {
        target for call, stage, group, target in cells if stage != "__dt__"
    }
    if available_targets != set(EXPECTED_COLUMNS):
        raise TraceError(
            f"trace targets must be exactly {EXPECTED_COLUMNS}; got {sorted(available_targets)}"
        )
    calls = sorted({call for call, stage, group, target in cells if stage != "__dt__"})
    report_calls = []
    for call in calls:
        call_dts = {
            float(cells[(call, "__dt__", "", target)]["dt"])
            for target in EXPECTED_COLUMNS
        }
        if len(call_dts) != 1:
            raise TraceError(f"dt differs across targets in call {call}")
        target_reports = []
        for target in EXPECTED_COLUMNS:
            snapshots = {
                stage: _one_stage(cells, call, stage, target)
                for stage in SNAPSHOT_STAGES
            }
            dt = float(cells[(call, "__dt__", "", target)]["dt"])
            entry = snapshots["micro_entry"]
            rho, delz = float(entry.get("rho", 0.0)), float(entry.get("delz", 0.0))
            if (
                not math.isfinite(rho)
                or not math.isfinite(delz)
                or rho <= 0
                or delz <= 0
            ):
                raise TraceError("micro_entry rho and delz must be positive")
            weight = rho * delz
            if (
                "dt" in snapshots["micro_entry"]
                and float(snapshots["micro_entry"]["dt"]) != dt
            ):
                raise TraceError("micro_entry dt differs from call dt")
            transitions = []
            for prior_stage, next_stage in zip(SNAPSHOT_STAGES, SNAPSHOT_STAGES[1:]):
                prior, next_value = snapshots[prior_stage], snapshots[next_stage]
                transitions.append(
                    {
                        "from_stage": prior_stage,
                        "to_stage": next_stage,
                        **_weighted_stage_change(prior, next_value, weight),
                    }
                )
            pre_rates = snapshots["pre_limits"]
            post_rates = snapshots["post_limits"]
            if not set(RATE_FIELDS).issubset(pre_rates) or not set(
                RATE_FIELDS
            ).issubset(post_rates):
                raise TraceError(
                    "pre_limits and post_limits must contain all four selected rate fields"
                )
            rate_comparison = {
                name: {
                    "post_process_local_cap_pre_group_limiter": float(pre_rates[name]),
                    "post_group_limiter": float(post_rates[name]),
                    "group_limiter_delta": float(post_rates[name])
                    - float(pre_rates[name]),
                }
                for name in RATE_FIELDS
            }
            raw_stage = snapshots["state_update_raw"]
            transfers = _transfer_ledger(raw_stage, dt)
            sum_residuals = {}
            update_terms = {
                "qv": ("dqv_sum", None),
                "qc": ("dqc_rate_sum", "dqc_amount"),
                "qr": ("dqr_rate_sum", "dqr_amount"),
                "qi": ("dqi_rate_sum", "dqi_amount"),
                "qs": ("dqs_sum", None),
                "qg": ("dqg_rate_sum", "dqg_amount"),
            }
            post_state = snapshots["post_state_update"]
            for field, (rate_field, amount_field) in update_terms.items():
                if rate_field not in raw_stage:
                    raise TraceError(f"state_update_raw missing {rate_field}")
                before_field = f"{field}_before"
                if before_field not in raw_stage:
                    raise TraceError(f"state_update_raw missing {before_field}")
                rate_amount = float(raw_stage[rate_field]) * dt
                inline_amount = 0.0
                if amount_field is not None:
                    if amount_field not in raw_stage:
                        raise TraceError(f"state_update_raw missing {amount_field}")
                    inline_amount = float(raw_stage[amount_field])
                    amount = inline_amount + rate_amount
                    expected = (
                        float(raw_stage[before_field]) + inline_amount
                    ) + rate_amount
                    source_order = (
                        f"({field}_before + {amount_field}) + {rate_field}*dt"
                    )
                else:
                    amount = rate_amount
                    expected = float(raw_stage[before_field]) + rate_amount
                    source_order = f"{field}_before + {rate_field}*dt"
                raw_state = float(raw_stage[field])
                clamped_state = float(post_state[field])
                sum_residuals[field] = {
                    "state_update_input": float(raw_stage[before_field]),
                    "inline_amount": inline_amount,
                    "rate_sum_times_dt": rate_amount,
                    "nominal_rate_sum_times_dt_plus_amount": amount,
                    "source_order": source_order,
                    "expected_unclamped_state": expected,
                    "traced_raw_state": raw_state,
                    "raw_state_minus_nominal_reconstruction": raw_state - expected,
                    "actual_raw_state_delta": raw_state
                    - float(raw_stage[before_field]),
                    "actual_postclamp_state": clamped_state,
                    "actual_postclamp_state_delta": clamped_state
                    - float(raw_stage[before_field]),
                    "postclamp_minus_raw_state": clamped_state - raw_state,
                    "note": "aggregate comparison only; rounding residual is not assigned to individual process rates",
                }
            target_reports.append(
                {
                    "call_index": call,
                    "trace_source_sha256": source_by_call_target[(call, target)],
                    "chunk": target[0],
                    "column": target[1],
                    "level_bottom0": target[2],
                    "dtcld_seconds": dt,
                    "fixed_entry_dry_mass_weight_kg_m2": weight,
                    "stages": {
                        stage: {
                            field: value
                            for field, value in snapshot.items()
                            if field in WATER_FIELDS or field == "t"
                        }
                        for stage, snapshot in snapshots.items()
                    },
                    "stage_water_changes": transitions,
                    "rate_fields_before_after_group_limiters": rate_comparison,
                    "limiter_groups": _limiter_ledger(cells, call, target),
                    "signed_pair_transfer_nominals": transfers,
                    "aggregate_state_update_reconstruction": sum_residuals,
                }
            )
        report_calls.append(
            {
                "call_index": call,
                "call_index_semantics": "one-based trace-enabled coordinator invocation ordinal local to this source process; merged chunks share ordinals, not a KDM execution or model-step count",
                "targets": target_reports,
            }
        )

    cleanup_observations = []
    for call_block in report_calls:
        for target in call_block["targets"]:
            cleanup = next(
                item
                for item in target["stage_water_changes"]
                if item["from_stage"] == "post_satadj"
                and item["to_stage"] == "post_threshold"
            )
            qg_before = float(target["stages"]["post_satadj"]["qg"])
            qg_after = float(target["stages"]["post_threshold"]["qg"])
            before_cleanup = target["stages"]["post_satadj"]
            after_cleanup = target["stages"]["post_threshold"]
            for field in WATER_FIELDS:
                before_value = before_cleanup[field]
                threshold = 1.0e-15 if field in ("qc", "qi") else 1.0e-9
                expected = (
                    before_value if field == "qv" or before_value > threshold else 0.0
                )
                if after_cleanup[field] != expected:
                    raise TraceError(f"captured threshold cleanup differs for {field}")
            if after_cleanup["t"] != before_cleanup["t"]:
                raise TraceError("threshold cleanup changed temperature")
            cleanup_observations.append(
                {
                    "call_index": call_block["call_index"],
                    "chunk": target["chunk"],
                    "column": target["column"],
                    "level_bottom0": target["level_bottom0"],
                    "qg_before_threshold_cleanup_kg_kg": qg_before,
                    "qg_after_threshold_cleanup_kg_kg": qg_after,
                    "qg_before_is_nonnegative_and_at_or_below_qcrmin": bool(
                        0.0 <= qg_before <= 1.0e-9
                    ),
                    "qg_signed_cleanup_delta_kg_kg": qg_after - qg_before,
                    "water_total_delta_kg_kg": cleanup["water_total_delta_kg_kg"],
                    "water_total_delta_kg_m2_local_level": cleanup[
                        "water_total_delta_kg_m2_local_level"
                    ],
                    "changed_water_fields": [
                        field
                        for field, delta in cleanup["field_delta_kg_kg"].items()
                        if delta != 0.0
                    ],
                }
            )

    report = {
        "schema": "kdm6.applied_transfer_trace_analysis.v1",
        "source_trace_sha256": source_hashes[0] if len(source_hashes) == 1 else None,
        "source_traces_sha256": source_hashes,
        "source_trace_bytes": [len(source) for source in sources],
        "target_contract": {
            "chunk_column_level_bottom0": [list(value) for value in EXPECTED_COLUMNS],
            "batch_columns": 512,
            "vertical_levels": 39,
        },
        "rate_semantics": {
            "call_index": "one-based trace-enabled coordinator invocation ordinal local to its source process; matching ordinals from separate chunk trace files do not imply a shared KDM execution or model-step count",
            "dtcld_seconds": "dtcld seconds for that microphysics subcycle, not the parent window length",
            "pre_limits": "process outputs after their local process caps and before the separate group conservation limiter",
            "post_limits": "rates after group conservation limiting; not uncapped phase-rate attempts",
            "pair_amount": "signed selected branch rate multiplied by dt in this analyzer; nominal pair transfer, not an isolated rounded state contribution",
        },
        "cleanup_thresholds": {
            "cloud_water_ice_qmin_with_paired_number_cleanup": 1.0e-15,
            "precipitating_qcrmin": 1.0e-9,
        },
        "calls": report_calls,
        "observed_threshold_cleanup_boundary": {
            "rule": "post_threshold applies the saved qcrmin=1e-9 cutoff; these rows report the observed post_satadj to post_threshold delta",
            "targets": cleanup_observations,
        },
        "interpretation_limits": [
            "micro_entry to pre_limits is an aggregate endpoint change and does not attribute inline D1-D4 or homogeneous processes individually",
            "the state update uses aggregate source-order sums; its floating-point residual is not distributed among process rates",
            "stage changes are saved endpoint differences, not a conservation proof or forecast attribution",
            "the saved endpoints locate the water loss at threshold cleanup, but do not explain why qg entered that boundary below qcrmin",
            "this analyzer performs no model, KDM, RTTOV, or build operation",
        ],
    }
    report["reference_npz_bitwise_crosscheck"] = compare_reference_npz(
        sources, reference_npz_paths or []
    )
    return report


def run(input_paths, output_path, *, reference_npz_paths=None):
    if not isinstance(input_paths, (list, tuple)):
        input_paths = [input_paths]
    input_paths = [Path(path) for path in input_paths]
    output_path = Path(output_path)
    if output_path.exists() or output_path.is_symlink():
        raise FileExistsError(f"output must be new: {output_path}")
    forbidden = {path.resolve() for path in input_paths} | {Path(__file__).resolve()}
    if output_path.resolve() in forbidden:
        raise ValueError("output must not overwrite trace or analyzer source")
    sources = [path.read_bytes() for path in input_paths]
    report = analyze_trace(sources, reference_npz_paths=reference_npz_paths)
    report["source_trace_paths"] = [str(path.resolve()) for path in input_paths]
    report["analysis_source"] = {
        "path": str(Path(__file__).resolve()),
        "sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, action="append")
    parser.add_argument("--reference-npz", type=Path, action="append")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = run(args.input, args.output, reference_npz_paths=args.reference_npz)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "calls": len(report["calls"]),
                "targets": len(report["target_contract"]["chunk_column_level_bottom0"]),
                "input_sha256": report["source_traces_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
