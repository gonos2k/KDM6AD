#!/usr/bin/env python3
"""Compare selected, possibly differently indexed, WRF NetCDF history frames.

The comparison is exact: numeric fields are compared by their raw element bits
and character fields byte-for-byte.  A matching NaN/Inf payload is reported as
raw-bit equal but is never considered a finite scientific pass.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np


_NUMERIC_KINDS = {"f", "i", "u"}
_CHAR_KINDS = {"S", "U"}
_SUPPORTED_ITEMSIZE = {1, 2, 4, 8}


def _dim_size(dimension: Any) -> int:
    size = getattr(dimension, "size", None)
    return int(size if size is not None else len(dimension))


def _dataset_dimensions(dataset: Any) -> dict[str, int]:
    dimensions = getattr(dataset, "dimensions", None)
    if dimensions is None:
        raise TypeError("dataset must expose a dimensions mapping")
    return {str(name): _dim_size(dim) for name, dim in dimensions.items()}


def _read_frame(variable: Any, frame: int) -> np.ndarray:
    dims = tuple(variable.dimensions)
    if "Time" not in dims:
        selected = variable[...]
    else:
        axis = dims.index("Time")
        index = [slice(None)] * len(dims)
        index[axis] = frame
        selected = variable[tuple(index)]
    if np.ma.isMaskedArray(selected):
        mask = np.ma.getmaskarray(selected)
        if np.any(mask):
            raise ValueError("selected frame contains masked values")
        selected = selected.data
    return np.asarray(selected)


def _field_shape_without_time(variable: Any) -> tuple[int, ...]:
    dims = tuple(variable.dimensions)
    shape = tuple(int(n) for n in variable.shape)
    return tuple(n for dim, n in zip(dims, shape) if dim != "Time")


def _decoded_char_frame(value: np.ndarray) -> str:
    flat = value.reshape(-1)
    if value.dtype.kind == "S":
        raw = b"".join(bytes(item) for item in flat.tolist())
        return raw.decode("ascii", errors="strict").rstrip("\x00 ")
    if value.dtype.kind == "U":
        return "".join(str(item) for item in flat.tolist()).rstrip("\x00 ")
    raise TypeError(f"Times must use a character dtype, got {value.dtype}")


def _raw_numeric_view(value: np.ndarray) -> np.ndarray:
    dtype = np.dtype(value.dtype)
    if dtype.kind not in _NUMERIC_KINDS or dtype.itemsize not in _SUPPORTED_ITEMSIZE:
        raise TypeError(f"unsupported numeric dtype {dtype}")
    contiguous = np.ascontiguousarray(value)
    return contiguous.view(np.dtype(f"u{dtype.itemsize}")).reshape(value.shape)


def _finite_counts(value: np.ndarray) -> tuple[int, int, int]:
    if value.dtype.kind != "f":
        return int(value.size), 0, 0
    finite = np.isfinite(value)
    nan = np.isnan(value)
    inf = np.isinf(value)
    return int(np.count_nonzero(finite)), int(np.count_nonzero(nan)), int(np.count_nonzero(inf))


def _declared_missing_values(variable: Any) -> np.ndarray:
    """Return only explicitly declared _FillValue/missing_value sentinels."""
    sentinels: list[np.ndarray] = []
    for name in ("_FillValue", "missing_value"):
        attrs = getattr(variable, "attrs", None)
        if isinstance(attrs, dict) and name in attrs:
            raw = attrs[name]
        elif hasattr(variable, "ncattrs") and name in variable.ncattrs():
            raw = variable.getncattr(name)
        elif hasattr(variable, name):
            raw = getattr(variable, name)
        else:
            continue
        values = np.asarray(raw)
        if values.dtype.kind in _NUMERIC_KINDS:
            sentinels.append(values.reshape(-1))
    if not sentinels:
        return np.asarray([], dtype=np.float64)
    return np.concatenate(sentinels)


def _declared_missing_mask(value: np.ndarray, sentinels: np.ndarray) -> np.ndarray:
    mask = np.zeros(value.shape, dtype=bool)
    for sentinel in sentinels:
        try:
            if np.issubdtype(sentinels.dtype, np.floating) and np.isnan(sentinel):
                mask |= np.isnan(value)
            else:
                mask |= value == sentinel
        except (TypeError, ValueError):
            continue
    return mask


def _max_abs_difference(a: np.ndarray, b: np.ndarray) -> float | str | None:
    if a.size == 0:
        return None
    with np.errstate(over="ignore", invalid="ignore"):
        delta = np.abs(a.astype(np.float64) - b.astype(np.float64))
    if np.isinf(delta).any():
        return "Infinity"
    finite_delta = delta[np.isfinite(delta)]
    if finite_delta.size == 0:
        return None
    return float(finite_delta.max())


def compare_frames(
    reference_dataset: Any,
    candidate_dataset: Any,
    reference_frame: int,
    candidate_frame: int,
    expected_time: str,
) -> dict[str, Any]:
    """Compare all variables at two explicit frames and return a JSON report.

    ``reference_dataset`` and ``candidate_dataset`` need only provide the small
    Dataset/Variable interface used here, so tests can use in-memory fakes.
    Time may have different lengths across the datasets; all other dimensions,
    field schemas, and the selected ``Times`` values must agree exactly.
    """
    if not isinstance(reference_frame, int) or not isinstance(candidate_frame, int):
        raise TypeError("frame indices must be integers")
    if reference_frame < 0 or candidate_frame < 0:
        raise ValueError("frame indices must be non-negative")
    if not isinstance(expected_time, str) or not expected_time:
        raise ValueError("expected_time must be a non-empty string")

    ref_dims = _dataset_dimensions(reference_dataset)
    cand_dims = _dataset_dimensions(candidate_dataset)
    ref_vars = reference_dataset.variables
    cand_vars = candidate_dataset.variables
    errors: list[str] = []

    if "Time" not in ref_dims or "Time" not in cand_dims:
        errors.append("both datasets must have a Time dimension")
    else:
        if reference_frame >= ref_dims["Time"]:
            errors.append(f"reference frame {reference_frame} out of range ({ref_dims['Time']})")
        if candidate_frame >= cand_dims["Time"]:
            errors.append(f"candidate frame {candidate_frame} out of range ({cand_dims['Time']})")

    if set(ref_dims) != set(cand_dims):
        errors.append(
            "dataset dimension inventory differs: "
            f"reference-only={sorted(set(ref_dims) - set(cand_dims))}, "
            f"candidate-only={sorted(set(cand_dims) - set(ref_dims))}"
        )
    for name in sorted(set(ref_dims) & set(cand_dims)):
        if name != "Time" and ref_dims[name] != cand_dims[name]:
            errors.append(f"dimension {name} size differs: {ref_dims[name]} vs {cand_dims[name]}")

    ref_names, cand_names = set(ref_vars), set(cand_vars)
    missing = sorted(ref_names - cand_names)
    extra = sorted(cand_names - ref_names)
    if missing:
        errors.append(f"candidate missing variables: {missing}")
    if extra:
        errors.append(f"candidate has extra variables: {extra}")

    field_reports: dict[str, dict[str, Any]] = {}
    total_numeric_elements = 0
    total_element_mismatches = 0
    all_numeric_finite = True
    times_values: dict[str, str] = {}

    for name in sorted(ref_names & cand_names):
        va, vb = ref_vars[name], cand_vars[name]
        dims_a, dims_b = tuple(va.dimensions), tuple(vb.dimensions)
        dtype_a, dtype_b = np.dtype(va.dtype), np.dtype(vb.dtype)
        item: dict[str, Any] = {
            "dimensions": list(dims_a),
            "reference_shape": [int(n) for n in va.shape],
            "candidate_shape": [int(n) for n in vb.shape],
            "reference_dtype": str(dtype_a),
            "candidate_dtype": str(dtype_b),
            "raw_bitwise_equal": False,
            "mismatch_count": 0,
            "first_mismatch_index": None,
            "max_abs_difference": None,
            "finite": None,
        }
        field_reports[name] = item

        if dims_a != dims_b:
            errors.append(f"{name}: dimension-name mismatch {dims_a} vs {dims_b}")
            continue
        if _field_shape_without_time(va) != _field_shape_without_time(vb):
            errors.append(f"{name}: non-Time shape mismatch {va.shape} vs {vb.shape}")
            continue
        if dtype_a.kind not in _NUMERIC_KINDS | _CHAR_KINDS:
            raise TypeError(f"{name}: unsupported dtype {dtype_a}")
        if dtype_b.kind not in _NUMERIC_KINDS | _CHAR_KINDS:
            raise TypeError(f"{name}: unsupported dtype {dtype_b}")
        if dtype_a.kind != dtype_b.kind:
            errors.append(f"{name}: dtype-kind mismatch {dtype_a.kind} vs {dtype_b.kind}")
            continue
        if dtype_a.kind not in _NUMERIC_KINDS and dtype_a != dtype_b:
            errors.append(f"{name}: character dtype mismatch {dtype_a} vs {dtype_b}")
            continue
        if dtype_a.kind in _NUMERIC_KINDS:
            if dtype_a.itemsize not in _SUPPORTED_ITEMSIZE or dtype_b.itemsize not in _SUPPORTED_ITEMSIZE:
                raise TypeError(f"{name}: unsupported numeric dtype {dtype_a} or {dtype_b}")

        try:
            xa = _read_frame(va, reference_frame)
            xb = _read_frame(vb, candidate_frame)
        except IndexError as exc:
            errors.append(f"{name}: selected frame is unavailable: {exc}")
            continue
        if xa.shape != xb.shape:
            errors.append(f"{name}: selected-frame shape mismatch {xa.shape} vs {xb.shape}")
            continue
        if xa.dtype != xb.dtype:
            errors.append(f"{name}: selected-frame dtype mismatch {xa.dtype} vs {xb.dtype}")
            continue

        if dtype_a.kind in _NUMERIC_KINDS:
            total_numeric_elements += int(xa.size)
            finite_a, nan_a, inf_a = _finite_counts(xa)
            finite_b, nan_b, inf_b = _finite_counts(xb)
            item["finite"] = finite_a == xa.size and finite_b == xb.size
            item["reference_nonfinite"] = {"nan": nan_a, "inf": inf_a}
            item["candidate_nonfinite"] = {"nan": nan_b, "inf": inf_b}
            if not item["finite"]:
                all_numeric_finite = False
            missing_a = int(np.count_nonzero(_declared_missing_mask(xa, _declared_missing_values(va))))
            missing_b = int(np.count_nonzero(_declared_missing_mask(xb, _declared_missing_values(vb))))
            item["declared_missing_count"] = {"reference": missing_a, "candidate": missing_b}
            item["complete_values"] = missing_a == 0 and missing_b == 0
            ua, ub = _raw_numeric_view(xa), _raw_numeric_view(xb)
            different = ua != ub
            mismatch_count = int(np.count_nonzero(different))
            item["mismatch_count"] = mismatch_count
            item["raw_bitwise_equal"] = mismatch_count == 0
            total_element_mismatches += mismatch_count
            if mismatch_count:
                first = tuple(int(i) for i in np.argwhere(different)[0])
                item["first_mismatch_index"] = list(first)
                item["max_abs_difference"] = _max_abs_difference(xa, xb)
            if xa.size == 0:
                errors.append(f"{name}: empty numeric field provides no comparison evidence")
        else:
            char_different = xa != xb
            char_mismatch_count = int(np.count_nonzero(char_different))
            item["raw_bitwise_equal"] = char_mismatch_count == 0
            item["mismatch_count"] = char_mismatch_count
            item["complete_values"] = True
            if char_mismatch_count:
                item["first_mismatch_index"] = [
                    int(i) for i in np.argwhere(char_different)[0]
                ]
            if not item["raw_bitwise_equal"]:
                errors.append(f"{name}: character data differ")
            if name == "Times":
                if "Time" not in dims_a:
                    errors.append("Times variable must include the Time dimension")
                else:
                    time_a = _decoded_char_frame(xa)
                    time_b = _decoded_char_frame(xb)
                    times_values = {"reference": time_a, "candidate": time_b}
                    if time_a != expected_time or time_b != expected_time:
                        errors.append(
                            f"Times mismatch: expected {expected_time!r}, "
                            f"reference={time_a!r}, candidate={time_b!r}"
                        )

    if "Times" not in ref_names or "Times" not in cand_names:
        errors.append("both datasets must contain a Times variable")

    raw_equal = (
        not missing
        and not extra
        and all(item["raw_bitwise_equal"] for item in field_reports.values())
        and all("mismatch" not in error.lower() and "differ" not in error.lower()
                for error in errors)
    )
    return {
        "schema": "kdm6ad.native_replay_compare.v1",
        "expected_time": expected_time,
        "reference_frame": reference_frame,
        "candidate_frame": candidate_frame,
        "reference_time_dimension": ref_dims.get("Time"),
        "candidate_time_dimension": cand_dims.get("Time"),
        "times_values": times_values,
        "variable_count_reference": len(ref_names),
        "variable_count_candidate": len(cand_names),
        "missing_variables": missing,
        "extra_variables": extra,
        "numeric_elements_compared": total_numeric_elements,
        "numeric_element_mismatches": total_element_mismatches,
        "raw_bitwise_equal": bool(raw_equal),
        "finite": bool(all_numeric_finite),
        "complete_values": bool(
            all(item.get("complete_values", True) for item in field_reports.values())
        ),
        "passed": bool(
            raw_equal
            and all_numeric_finite
            and all(item.get("complete_values", True) for item in field_reports.values())
            and total_numeric_elements > 0
            and not errors
        ),
        "errors": errors,
        "variables": field_reports,
    }


def _cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", required=True, help="baseline NetCDF file")
    parser.add_argument("--candidate", required=True, help="restart-continuation NetCDF file")
    parser.add_argument("--reference-frame", required=True, type=int, help="0-based baseline frame")
    parser.add_argument("--candidate-frame", required=True, type=int, help="0-based candidate frame")
    parser.add_argument("--expected-time", required=True, help="expected WRF timestamp, e.g. YYYY-MM-DD_HH:MM:SS")
    parser.add_argument("--output", required=True, help="path to write the JSON comparison report")
    args = parser.parse_args()

    try:
        import netCDF4 as nc  # Optional dependency: CLI-only.
    except ImportError as exc:
        parser.error(f"netCDF4 is required for file input: {exc}")

    try:
        with nc.Dataset(args.reference, "r") as reference, nc.Dataset(args.candidate, "r") as candidate:
            reference.set_auto_maskandscale(False)
            candidate.set_auto_maskandscale(False)
            report = compare_frames(
                reference, candidate, args.reference_frame, args.candidate_frame, args.expected_time
            )
    except (OSError, RuntimeError, ValueError, TypeError) as exc:
        report = {
            "schema": "kdm6ad.native_replay_compare.v1",
            "passed": False,
            "raw_bitwise_equal": False,
            "finite": False,
            "errors": [f"comparison failed: {exc}"],
        }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({k: report.get(k) for k in (
        "passed", "raw_bitwise_equal", "finite", "numeric_elements_compared",
        "numeric_element_mismatches", "errors",
    )}, indent=2, sort_keys=True))
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(_cli())
