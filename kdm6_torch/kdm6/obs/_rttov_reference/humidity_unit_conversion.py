#!/usr/bin/env python3
"""Humidity unit conversions needed by the KDM6AD -> RTTOV14 Q bridge.

RTTOV14 can read profile water vapour in multiple `gas_units` conventions. The
GK2A AMI ami/501 fixture used in AD-RTTOV has `gas_units=2`, i.e. ppmv over
moist air. KDM6-style microphysics variables are commonly kg/kg mass mixing
ratios, so bridge code must make this conversion explicit instead of relabeling
qv as RTTOV Q.
"""

from __future__ import annotations

import math

DRY_AIR_MOLAR_MASS_KG_PER_MOL = 28.9647e-3
WATER_VAPOR_MOLAR_MASS_KG_PER_MOL = 18.01528e-3


def _validate_nonnegative_finite(value: float, name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be finite and non-negative")
    return value


def kgkg_mixing_ratio_to_ppmv_moist(mixing_ratio_kgkg_dry_air: float) -> float:
    """Convert water-vapour mass mixing ratio kg/kg dry air to ppmv moist air.

    Let w be kg water vapour per kg dry air. The water-vapour mole fraction over
    moist air is:

        x_v = (w / M_v) / (1 / M_d + w / M_v)

    RTTOV gas_units=2 stores `x_v * 1e6`.
    """
    w = _validate_nonnegative_finite(mixing_ratio_kgkg_dry_air, "mixing_ratio_kgkg_dry_air")
    numerator = w / WATER_VAPOR_MOLAR_MASS_KG_PER_MOL
    denominator = (1.0 / DRY_AIR_MOLAR_MASS_KG_PER_MOL) + numerator
    return 1.0e6 * numerator / denominator


def kgkg_specific_humidity_to_ppmv_moist(specific_humidity_kgkg_moist_air: float) -> float:
    """Convert specific humidity kg/kg moist air to ppmv moist air."""
    q = _validate_nonnegative_finite(specific_humidity_kgkg_moist_air, "specific_humidity_kgkg_moist_air")
    if q >= 1.0:
        raise ValueError("specific_humidity_kgkg_moist_air must be less than 1")
    return kgkg_mixing_ratio_to_ppmv_moist(q / (1.0 - q))


def ppmv_moist_to_kgkg_mixing_ratio(ppmv_moist: float) -> float:
    """Convert ppmv over moist air to kg/kg dry-air mass mixing ratio."""
    ppmv = _validate_nonnegative_finite(ppmv_moist, "ppmv_moist")
    if ppmv >= 1.0e6:
        raise ValueError("ppmv_moist must be less than 1000000")
    x_v = ppmv / 1.0e6
    return (x_v * WATER_VAPOR_MOLAR_MASS_KG_PER_MOL) / ((1.0 - x_v) * DRY_AIR_MOLAR_MASS_KG_PER_MOL)


def ppmv_moist_to_kgkg_specific_humidity(ppmv_moist: float) -> float:
    """Convert ppmv over moist air to specific humidity kg/kg moist air."""
    w = ppmv_moist_to_kgkg_mixing_ratio(ppmv_moist)
    return w / (1.0 + w)
