"""Binary32 source-order helpers for the experimental S10 C-arm ledger."""
from __future__ import annotations

import math
import struct
from typing import Iterable


def f32(value: float) -> float:
    return struct.unpack(">f", struct.pack(">f", float(value)))[0]


def add32(left: float, right: float) -> float:
    return f32(f32(left) + f32(right))


def sub32(left: float, right: float) -> float:
    return f32(f32(left) - f32(right))


def mul32(left: float, right: float) -> float:
    return f32(f32(left) * f32(right))


def div32(left: float, right: float) -> float:
    return f32(f32(left) / f32(right))


def finite32(*values: float) -> bool:
    return all(math.isfinite(f32(value)) for value in values)


def guarded_rate_over_density(qg: float, rate: float,
                              rhox: float) -> tuple[int, float]:
    """Skip only the exact-zero qg and same-rate 0/0 denominator case."""
    qg32, rate32, rho32 = f32(qg), f32(rate), f32(rhox)
    if not finite32(qg32, rate32, rho32):
        raise ValueError("non-finite qg/rate/rhox in C guard input")
    if qg32 == 0.0 and rate32 == 0.0:
        return 0, f32(0.0)
    if rho32 <= 0.0:
        raise ZeroDivisionError("nonzero C guard arm requires finite positive rhox")
    return 1, div32(rate32, rho32)


def sum32(terms: Iterable[float]) -> float:
    values = iter(terms)
    first = next(values, None)
    if first is None:
        return f32(0.0)
    total = f32(first)
    for term in values:
        total = add32(total, term)
    return total


def qg_mass_stage1(before: float, pgmlt: float) -> float:
    return add32(before, pgmlt)


def qg_mass_stage2(before: float, *, pgdep: float, pgaut: float,
                   piacr: float, delta3: float, praci: float,
                   psacr: float, delta2: float, pracs: float,
                   pgaci: float, paacw: float, pgacr: float,
                   pgacs: float, dtcld: float) -> float:
    """Replay the canonical generation update's left-to-right f32 order."""
    rate = add32(pgdep, pgaut)
    rate = add32(rate, mul32(piacr, sub32(1.0, delta3)))
    rate = add32(rate, mul32(praci, sub32(1.0, delta3)))
    rate = add32(rate, mul32(psacr, sub32(1.0, delta2)))
    rate = add32(rate, mul32(pracs, sub32(1.0, delta2)))
    rate = add32(rate, pgaci)
    rate = add32(rate, paacw)
    rate = add32(rate, pgacr)
    rate = add32(rate, pgacs)
    return max(add32(before, mul32(rate, dtcld)), f32(0.0))


def qg_mass_stage3(before: float, *, pgacs: float, pgevp: float,
                   pgeml: float, dtcld: float) -> float:
    rate = add32(add32(pgacs, pgevp), pgeml)
    return max(add32(before, mul32(rate, dtcld)), f32(0.0))


def brs_volume_stage1(before: float, quotient: float) -> float:
    return add32(before, quotient)


def brs_volume_stage2(before: float, *, pgdep_volume: float,
                      other_rates: Iterable[float], dtcld: float) -> float:
    source = f32(pgdep_volume)
    for rate in other_rates:
        source = add32(source, rate)
    return max(add32(before, mul32(source, dtcld)), f32(0.0))


def brs_volume_stage3(before: float, *, bgevp: float, bgeml: float,
                      dtcld: float) -> float:
    source = add32(bgevp, bgeml)
    return max(add32(before, mul32(source, dtcld)), f32(0.0))


def heat_stage1(before: float, *, xlf: float, cpm: float,
                pgmlt: float) -> float:
    tendency = div32(xlf, cpm)
    return add32(before, mul32(tendency, pgmlt))


def xlwork2_stage2(*, xls: float, xl: float, xlf: float,
                   psdep: float, pgdep: float, pidep: float, pinud: float,
                   prevp: float, piacr: float, paacw: float,
                   pmulcs: float, pmulcg: float, pmulrs: float,
                   pmulrg: float, piacw: float, pgacr: float,
                   psacr: float) -> float:
    first = sum32((psdep, pgdep, pidep, pinud))
    last = sum32((piacr, paacw, pmulcs, pmulcg, pmulrs,
                  pmulrg, piacw, paacw, pgacr, psacr))
    result = mul32(-f32(xls), first)
    result = sub32(result, mul32(xl, prevp))
    return sub32(result, mul32(xlf, last))


def xlwork2_stage3(*, xl: float, xlf: float, prevp: float,
                   psevp: float, pgevp: float, pseml: float,
                   pgeml: float) -> float:
    first = sum32((prevp, psevp, pgevp))
    second = add32(pseml, pgeml)
    result = mul32(-f32(xl), first)
    return sub32(result, mul32(xlf, second))


def heat_stage2(before: float, *, xlwork2: float, cpm: float,
                dtcld: float) -> float:
    tendency = div32(xlwork2, cpm)
    return sub32(before, mul32(tendency, dtcld))


def heat_stage3(before: float, *, xlwork2: float, cpm: float,
                dtcld: float) -> float:
    return heat_stage2(before, xlwork2=xlwork2, cpm=cpm, dtcld=dtcld)
