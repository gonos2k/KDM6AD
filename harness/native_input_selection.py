"""Predeclare native spatial holdouts from input properties, not test outcomes."""

from __future__ import annotations

import numpy as np

CATEGORIES = ("clear", "warm_liquid", "mixed_column", "ice", "rain")


def select_columns(
    qc, qr, qi, qs, qg, temperature, *, margin=2, excluded=((153, 144),)
):
    """Return one unique median-ordered native column per predeclared class.

    Arrays are native (K,J,I); indices returned are Fortran one-based. Classes
    can overlap and are column classifications, not proof of active processes
    or colocated mixed phase. No number initialization or observation is used.
    """
    inputs = (qc, qr, qi, qs, qg, temperature)
    if any(
        np.ma.isMaskedArray(x) and bool(np.ma.getmaskarray(x).any()) for x in inputs
    ):
        raise ValueError("masked native input is not a classified physical state")
    arrays = [np.asarray(x, dtype=float) for x in inputs]
    shape = arrays[0].shape
    if len(shape) != 3 or any(x.shape != shape for x in arrays):
        raise ValueError("matching native (K,J,I) arrays required")
    if not all(np.isfinite(x).all() for x in arrays) or any(
        (x < 0).any() for x in arrays[:5]
    ):
        raise ValueError("finite state and nonnegative condensate required")
    if type(margin) is not int or margin < 1 or min(shape[1:]) <= 2 * margin:
        raise ValueError("nonempty physical interior with positive margin required")
    qc, qr, qi, qs, qg, t = arrays
    masks = {
        "clear": np.max(qc + qr + qi + qs + qg, axis=0) < 1e-12,
        "warm_liquid": np.any((qc > 1e-5) & (t > 273.15), axis=0),
        "mixed_column": np.any((qc > 1e-5) & (t < 273.15), axis=0)
        & np.any(qi + qs > 1e-6, axis=0),
        "ice": np.any((qi + qs > 1e-5) & (t < 253.15), axis=0),
        "rain": np.any(qr > 1e-5, axis=0),
    }
    used = set(excluded)
    out = []
    for category in CATEGORIES:
        mask = masks[category].copy()
        mask[:margin] = False
        mask[-margin:] = False
        mask[:, :margin] = False
        mask[:, -margin:] = False
        coordinates = [(int(j) + 1, int(i) + 1) for j, i in np.argwhere(mask)]
        candidates = [p for p in coordinates if p not in used]
        point = candidates[len(candidates) // 2] if candidates else None
        if point is not None:
            used.add(point)
        out.append(
            dict(
                category=category,
                candidate_count=len(coordinates),
                eligible_count=len(candidates),
                selected=None if point is None else dict(j=point[0], i=point[1]),
            )
        )
    return out
