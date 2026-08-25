#!/usr/bin/env python3
"""One way to take numbers out of a netCDF variable, with the census attached.

netCDF4 returns a `MaskedArray` whether or not anything is masked, and every
reader here does `np.asarray(var[i], dtype="float64")`, which DROPS the mask.
Where a mask is set that silently turns fill values into ordinary numbers and
feeds them to a median.

MEASURED, before writing this: on `wrfinput_d01`, seven load-bearing variables
(`T`, `QVAPOR`, `QNRAIN`, `P`, `PH`, `MU`, `XLAND`) return `MaskedArray` with
**0 masked cells and no `_FillValue` declared**. So the hazard is latent, not
live, and no published number is affected. What it needs is therefore a GUARD
rather than a rewrite of five modules: if a file ever does declare a fill value,
this says so instead of ingesting it.
"""
from __future__ import annotations


def read_numeric(var, index=None, *, allow_masked: bool = False) -> dict:
    """`var[index]` as float64, with what was dropped counted.

    Masked cells become NaN so they cannot pass as data, and the counts come
    back with the array so a statistic can state its own denominator. With
    `allow_masked=False` (the default) a mask is refused outright: nothing in
    this campaign reads a file that has one, so one appearing is news.
    """
    import numpy as np
    raw = np.ma.asarray(var[...] if index is None else var[index])
    masked = np.ma.getmaskarray(raw)
    if masked.any() and not allow_masked:
        raise ValueError(
            f"{getattr(var, 'name', 'variable')}: {int(masked.sum())} of "
            f"{masked.size} cells are masked. Every reader in this harness "
            f"drops the mask, so those fill values would enter the statistics "
            f"as data. Pass allow_masked=True once you have decided what they "
            f"mean here.")
    data = np.asarray(raw.filled(np.nan), dtype="float64")
    finite = np.isfinite(data)
    return {"data": data,
            "masked": masked,
            "total_count": int(data.size),
            "masked_count": int(masked.sum()),
            "finite_count": int(finite.sum()),
            "nonfinite_count": int((~finite).sum())}
