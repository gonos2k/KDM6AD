"""Small conservative remap check on a declared common overlap.

This validates a supplied linear remap P; it does not create a production
remapper or change the native KDM model grid. Source/destination coverage
fractions and the destination normalization are explicit.
"""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Real

import numpy as np


@dataclass(frozen=True)
class OverlapRemap:
    source_measure: np.ndarray
    destination_measure: np.ndarray
    source_fraction: np.ndarray
    destination_fraction: np.ndarray
    matrix: np.ndarray  # [destination, source]
    normalization: str  # "covered_area" or "destination_area"


@dataclass(frozen=True)
class RemapAudit:
    column_residual: np.ndarray
    constant_residual: np.ndarray
    overlap_measure_residual: float


def _f64_array(value, name: str, rank: int) -> np.ndarray:
    # Require callers to perform any f32/other-basis conversion explicitly.
    # In particular, np.asarray would drop missing-data masks or coerce bool.
    if (np.ma.isMaskedArray(value) or not isinstance(value, np.ndarray)
            or value.dtype != np.float64 or value.ndim != rank
            or not value.size or not np.isfinite(value).all()):
        raise ValueError(f"{name} must be a nonempty finite unmasked float64 array")
    return value


def check_overlap_remap(spec: OverlapRemap, *, atol: float = 0.0,
                        rtol: float = 1e-12) -> RemapAudit:
    """Check w_dst^T P = w_src^T on overlap and declared constant behavior.

    `covered_area`: destination values are normalized by covered area;
      weighted integral uses w_dst*f_dst and rows sum to one where covered.
    `destination_area`: uncovered area contributes zero to the full-cell
      value; integral uses w_dst and rows sum to f_dst.
    """
    # atol has the source/destination measure unit; rtol is dimensionless.
    # A positive *default* absolute tolerance would swallow tiny-overlap
    # conservation errors even when they are order-one relative to coverage.
    if (isinstance(atol, bool) or isinstance(rtol, bool)
            or not isinstance(atol, Real) or not isinstance(rtol, Real)
            or not np.isfinite(atol) or not np.isfinite(rtol)
            or atol < 0 or rtol < 0):
        raise ValueError("finite nonnegative real remap tolerances required")
    ws = _f64_array(spec.source_measure, "source measure", 1)
    wd = _f64_array(spec.destination_measure, "destination measure", 1)
    fs = _f64_array(spec.source_fraction, "source overlap fraction", 1)
    fd = _f64_array(spec.destination_fraction, "destination overlap fraction", 1)
    p = _f64_array(spec.matrix, "remap matrix", 2)
    if (fs.shape != ws.shape or fd.shape != wd.shape
            or p.shape != (wd.size, ws.size)):
        raise ValueError("source/destination measures, fractions and matrix shapes differ")
    if (np.any(ws <= 0) or np.any(wd <= 0)
            or np.any((fs < 0) | (fs > 1))
            or np.any((fd < 0) | (fd > 1)) or np.any(p < 0)):
        raise ValueError("positive measures, fractions in [0,1], nonnegative P required")
    if spec.normalization not in ("covered_area", "destination_area"):
        raise ValueError("declare covered_area or destination_area normalization")
    if np.any(p[fd == 0] != 0) or np.any(p[:, fs == 0] != 0):
        raise ValueError("masked source/destination cells must not carry remap weights")
    with np.errstate(under="ignore", over="ignore", invalid="ignore"):
        source_weight = ws * fs
        covered_destination_weight = wd * fd
    if (np.any((fs > 0) & (source_weight == 0))
            or np.any((fd > 0) & (covered_destination_weight == 0))):
        raise ValueError("positive overlap measure underflowed to zero")
    destination_weight = (covered_destination_weight
                          if spec.normalization == "covered_area" else wd)
    with np.errstate(over="ignore", invalid="ignore"):
        mapped_weight = destination_weight @ p
        column_residual = mapped_weight - source_weight
        expected_constant = np.where(fd > 0, 1., 0.) if spec.normalization == "covered_area" else fd
        mapped_constant = p @ np.ones(ws.size)
        constant_residual = mapped_constant - expected_constant
        source_overlap = float(np.sum(source_weight))
        destination_overlap = float(np.sum(covered_destination_weight))
        overlap_residual = source_overlap - destination_overlap
    if (not np.isfinite(column_residual).all()
            or not np.isfinite(constant_residual).all()
            or not np.isfinite(overlap_residual)):
        raise ValueError("remap budget overflowed")
    with np.errstate(over="ignore", invalid="ignore"):
        column_tol = atol + rtol * np.maximum(np.abs(mapped_weight), np.abs(source_weight))
        constant_tol = rtol * np.maximum(np.abs(mapped_constant), np.abs(expected_constant))
        overlap_tol = atol + rtol * max(abs(source_overlap), abs(destination_overlap))
    if (not np.isfinite(column_tol).all() or not np.isfinite(constant_tol).all()
            or not np.isfinite(overlap_tol)):
        raise ValueError("remap tolerance calculation overflowed")
    if (np.any(np.abs(column_residual) > column_tol)
            or np.any(np.abs(constant_residual) > constant_tol)
            or abs(overlap_residual) > overlap_tol):
        raise ValueError("remap does not conserve overlap or declared constant field")
    return RemapAudit(np.array(column_residual, copy=True),
                      np.array(constant_residual, copy=True), overlap_residual)


def remap_and_integrate(spec: OverlapRemap, source_values: np.ndarray) -> tuple[np.ndarray, float, float]:
    """Apply an already-checked P and report source/destination overlap totals."""
    check_overlap_remap(spec)
    x = _f64_array(source_values, "source values", 1)
    if x.shape != spec.source_measure.shape:
        raise ValueError("source value shape differs from source cells")
    y = spec.matrix @ x
    wd = (spec.destination_measure * spec.destination_fraction
          if spec.normalization == "covered_area" else spec.destination_measure)
    source_total = float((spec.source_measure * spec.source_fraction) @ x)
    destination_total = float(wd @ y)
    if not np.isfinite(y).all() or not np.isfinite(source_total) or not np.isfinite(destination_total):
        raise ValueError("remapped values or totals overflowed")
    return y, source_total, destination_total
