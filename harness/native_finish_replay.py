"""Independent value replay of the sampled arm64/GFortran theta_m finish map.

This diagnostic profile follows the emitted FMADD/FDIV sequence, not a change
to host arithmetic. It is not a derivative, water/number budget, or certification
of other compiler configurations. FMA expectations use exact rational products
and sums followed by binary32 round-to-nearest/even, independently of libm fmaf.
"""
from __future__ import annotations

from fractions import Fraction
from typing import Mapping

import numpy as np


def _fraction(value) -> Fraction:
    return Fraction.from_float(float(np.float32(value)))


def _bits(value) -> int:
    return int(np.asarray([value], dtype=np.float32).view(np.uint32)[0])


def _round_f32(value: Fraction) -> np.float32:
    if value == 0:
        return np.float32(0)
    # Correct overflow midpoint for nearest/even, before a float64 approximation.
    if abs(value) >= Fraction(2**128 - 2**103):
        return np.float32(np.inf if value > 0 else -np.inf)
    with np.errstate(over="ignore", under="ignore"):
        approximate = np.float32(float(value))
        if not np.isfinite(approximate):
            approximate = np.float32(np.finfo(np.float32).max * (1 if value > 0 else -1))
        candidates = (approximate, np.nextafter(approximate, np.float32(-np.inf)),
                      np.nextafter(approximate, np.float32(np.inf)))
    finite = [x for x in candidates if np.isfinite(x)]
    return min(finite, key=lambda x: (abs(_fraction(x) - value), _bits(x) & 1))


def fma_f32_exact(a, b, c) -> np.float32:
    """One correctly rounded fused binary32 product-plus-sum, finite inputs."""
    a, b, c = (np.float32(x) for x in (a, b, c))
    if not all(np.isfinite(x) for x in (a, b, c)):
        raise ValueError("finite f32 operands required")
    value = _fraction(a) * _fraction(b) + _fraction(c)
    if value == 0:
        negative_product = bool(np.signbit(a) ^ np.signbit(b))
        if (a == 0 or b == 0) and c == 0 and negative_product and np.signbit(c):
            return np.float32(-0.0)
        return np.float32(0.0)
    return _round_f32(value)


def replay_arm64_theta_m_finish(pre: Mapping[str, float]) -> dict[str, np.float32]:
    """Replay use_theta_m=1/no_mp_heating=0 from captured pre-finish values.

    Runtime alpha and limiter are inputs. MP_RAW/QVTEN/MP_CLIPPED are derived
    independently rather than borrowed from their captured diagnostics.
    The emitted profile is pinned by the native evidence's object disassembly.
    """
    names = ("dt", "H_PRE", "QV_PRE", "TH_PLUS", "QV_PLUS", "T0", "ALPHA", "MP_TEND_LIM")
    v = {name: np.float32(pre[name]) for name in names}
    if not all(np.isfinite(x) for x in v.values()) or v["dt"] <= 0 or v["MP_TEND_LIM"] < 0:
        raise ValueError("finite finish inputs, positive dt and nonnegative limiter required")
    f = np.float32
    raw = f(v["TH_PLUS"] - v["H_PRE"])
    delta_q = f(v["QV_PLUS"] - v["QV_PRE"])
    maximum = f(v["MP_TEND_LIM"] * v["dt"])
    applied = f(max(f(-maximum), min(maximum, raw)))
    old_factor = fma_f32_exact(v["QV_PRE"], v["ALPHA"], f(1))
    new_factor = fma_f32_exact(v["QV_PLUS"], v["ALPHA"], f(1))
    term_b = f(new_factor * applied)
    scaled_q = f(delta_q * v["ALPHA"])
    base_plus_b = fma_f32_exact(v["H_PRE"], old_factor, term_b)
    heating_numerator = fma_f32_exact(scaled_q, v["TH_PLUS"], term_b)
    full_after = fma_f32_exact(scaled_q, v["TH_PLUS"], base_plus_b)
    perturbation = f(full_after - v["T0"])
    return {
        "MP_RAW": raw, "MP_CLIPPED": applied, "QVTEN": delta_q,
        "T_NEW_AFTER": perturbation,
        "H_RATE": f(heating_numerator / v["dt"]),
        "QV_RATE": f(delta_q / v["dt"]),
        "TH_PHY_M_T0": f(f(f(perturbation + v["T0"]) / new_factor) - v["T0"]),
    }
