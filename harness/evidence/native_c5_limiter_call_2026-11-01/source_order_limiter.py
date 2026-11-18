"""Offline transcription of the executed C++ conservation limiter.

Derived from the public torch oracle, with five source-order expressions
matching the instrumented C++ overlay; raw-bit replay validates this map.
"""

import torch
from oracle.kdm6 import constants as c


def scale_rates_for_conservation_torch(
    state,
    supcol: torch.Tensor,
    warm,
    cold,
    mf,
    *,
    dtcld: float,
    ncmin_tensor=None,  # per-cell ncmin floor for cloud/ice NUMBER budgets (1:1 fix #18)
    budget_trace=None,  # optional SensitivityTrace; diagnostics only
    diagnostic_step: int = 0,
    audit=None,  # value-only branch instrumentation, never modifies the AD map
):
    """F1d2 — Fortran group conservation budgets (module_mp_kdm6.F :2460-2597
    cold-arm + :2657-2728 warm-arm). 14 budgets: value=max(floor,reservoir);
    source=Σ(signed sinks)·dtcld; if source>value scale every listed sink by
    factor=value/source. Bounds the SUM of competing sinks on one species — the
    tier the per-rate caps cannot provide (its absence caused the 806× staged-ice
    over-production). Runs AFTER melt_freeze (D5 read UNSCALED cold rates, as
    Fortran does) and BEFORE state_update; supcol gates cold(pass1)/warm(pass2)
    exactly as state_update's cold_mask=(supcol>=0).

    Mirrors C++ scale_rates_for_conservation 1:1. Each `source` is the LITERAL
    Fortran arithmetic on the corresponding rate tensors (the port carries
    Fortran's signs ⇒ identical arithmetic). Rates are scaled IN ORDER,
    sequentially (a rate re-read by a later budget sees its already-scaled
    value). factor=value/max(source,value) is an exact no-op (=1) where
    source≤value (the common case ⇒ existing tests unchanged). pgaut/pgacs ≡ 0
    (dropped, not invented); paacw/naacw appear ×2 in source but scaled once.
    For extreme binding sources, normalize numerator and denominator by the
    same power of two before division: forming a tiny factor first can lose
    its reverse derivative. Ordinary-source arithmetic is unchanged. Active
    nonfinite sums/amounts are rejected by value-only checks; these checks
    do not replace or detach any tensors used by the differentiable map.
    Returns scaled (warm, cold, mf).
    """
    dtype = state.qc.dtype
    cold_gate = (
        supcol >= 0
    )  # Fortran F:2456 `t.le.t0c` ⇔ supcol>=0; == state_update cold_mask
    warm_gate = (
        supcol < 0
    )  # complement (warm arm, Fortran t>t0c); supcol==0 stays on the cold arm.
    delta2 = ((state.qr < 1.0e-4) & (state.qs < 1.0e-4)).to(dtype)
    delta3 = (state.qr < 1.0e-4).to(dtype)
    one_m_d2 = 1.0 - delta2
    one_m_d3 = 1.0 - delta3
    EPS = 1.0e-15  # Fortran qmin (matches C++ constants::EPS)

    # Mutable working copies keyed by rate name (names are unique across the
    # three structs). Sequential mutation needs mutable state — NamedTuples are
    # immutable, so we mutate this dict and _replace at the end.
    W = ("praut", "pracw", "prevp", "nraut", "nccol", "nracw", "nrcol")
    C = (
        "paacw_adj",
        "piacw",
        "pmulcs",
        "pmulcg",
        "psaut",
        "pinud",
        "pidep",
        "praci",
        "psaci",
        "pgaci",
        "pmulrs",
        "pmulrg",
        "piacr",
        "psacr_adj",
        "pgacr_adj",
        "psdep",
        "pracs",
        "pgdep",
        "naacw",
        "niacw",
        "nraci",
        "nsaci",
        "ngaci",
        "niacr",
        "nsaut",
        "ninud",
        "nmulcs",
        "nmulcg",
        "nmulrs",
        "nmulrg",
        "nsacr",
        "ngacr",
        "psevp",
        "pgevp",
    )
    M = ("pseml", "pgeml", "nseml", "ngeml")
    r = {nm: getattr(warm, nm) for nm in W}
    r.update({nm: getattr(cold, nm) for nm in C})
    r.update({nm: getattr(mf, nm) for nm in M})

    def scale_group(value, source_sum, gate, names):
        source = source_sum * dtcld
        for label, amount in (("source sum", source_sum), ("source amount", source)):
            if not bool(torch.isfinite(amount[gate]).all()):
                raise ValueError(f"conservation {label} must be finite for {names}")
        # Inactive groups are identities, including when their unused sum is
        # NaN. Mask operands before division so saved intermediates cannot
        # contaminate an otherwise finite output's backward pass.
        source = torch.where(gate, source, torch.zeros_like(source))
        value = torch.where(gate, value, torch.ones_like(value))
        denominator = torch.maximum(source, value)
        if audit is not None:
            # Single-cell replay only. Float conversion is diagnostic-only and
            # does not replace any operand in the differentiable computation.
            a = float(source[0].detach())
            b = float(value[0].detach())
            active = bool(gate[0].detach())
            audit.append(
                {
                    "group": "/".join(names),
                    "active": active,
                    "source": a,
                    "reservoir": b,
                    "margin": a - b,
                    "binding": active and a > b,
                    "factor": b / max(a, b) if active else 1.0,
                }
            )
        if budget_trace is not None and "pidep" in names:
            # Record the pre-limit ice budget once; the branch mask is the
            # actual source>reservoir decision used by both arithmetic paths.
            budget_trace.record_stage(
                "ice_mass_budget",
                diagnostic_step,
                dtcld,
                None,
                None,
                branch=gate & (source > value),
                operands={"source": source, "value": value},
                metadata={"kind": "conservation_limiter", "rate_names": list(names)},
            )
        # This is an arithmetic choice, not an extra physical cap. Above
        # sqrt(max), reciprocal differentiation can lose B/S**2 although the
        # requested controlled derivative is representable. Keep the original
        # expression (including its tie derivative) for ordinary sources.
        large = gate & (source > value) & (source > torch.finfo(dtype).max ** 0.5)
        if not bool(large.any()):
            factor = torch.where(gate, value / denominator, torch.ones_like(value))
            for nm in names:
                r[nm] = r[nm] * factor
            return

        ordinary_denominator = torch.where(large, torch.ones_like(source), denominator)
        factor = torch.where(gate, value / ordinary_denominator, torch.ones_like(value))
        large_denominator = torch.where(large, source, torch.ones_like(source))
        # The exponent is a value-only arithmetic choice. Multiplication by
        # its power of two keeps the full rate/source AD paths; differentiable
        # ldexp is avoided because its backward can lose subnormal factors.
        exponent = torch.frexp(large_denominator)[1]
        reciprocal_scale = torch.exp2(-exponent.to(dtype))
        normalized_source = large_denominator * reciprocal_scale
        for nm in names:
            rate = r[nm]
            ordinary_rate = torch.where(large, torch.zeros_like(rate), rate)
            large_rate = torch.where(large, rate, torch.zeros_like(rate))
            normalized_rate = large_rate * reciprocal_scale
            ratio = normalized_rate / normalized_source
            # A subnormal normalized numerator can lose significant bits even
            # when the final result is ordinary. Normalize rate*budget instead.
            # If that product would overflow, normalize the (then necessarily
            # large) budget first. Mask operands before evaluating either form.
            small = large & (normalized_rate.abs() < torch.finfo(dtype).tiny)
            product_safe = value <= torch.finfo(dtype).max / rate.abs().clamp(min=1)
            product_rate = torch.where(
                small & product_safe, large_rate, torch.zeros_like(rate)
            )
            budget_first_rate = torch.where(
                small & ~product_safe, large_rate, torch.zeros_like(rate)
            )
            small_numerator = (
                product_rate * value
            ) * reciprocal_scale + budget_first_rate * (value * reciprocal_scale)
            limited = torch.where(
                small, small_numerator / normalized_source, ratio * value
            )
            r[nm] = torch.where(large, limited, ordinary_rate * factor)

    def limit(reservoir, floor, source_sum, gate, names):
        scale_group(torch.clamp(reservoir, min=floor), source_sum, gate, names)

    def limit_ncmin(reservoir, source_sum, gate, names):
        # Per-cell ncmin floor (xland-derived) for cloud/ice NUMBER budgets — Fortran
        # F:2554/2568/2706 max(ncmin,nci), ncmin=10/100, NOT hardcoded 0.01. 1:1 fix #18.
        value = (
            torch.maximum(reservoir, ncmin_tensor)
            if ncmin_tensor is not None
            else torch.clamp(reservoir, min=c.NCMIN)
        )
        scale_group(value, source_sum, gate, names)

    # ── PASS 1: cold arm (t<=t0c), gate=cold_gate ──────────────────────────
    limit(
        state.qc,
        EPS,  # cloud mass :2460
        r["praut"]
        + r["pracw"]
        + r["paacw_adj"]
        + r["paacw_adj"]
        + r["piacw"]
        + r["pmulcs"]
        + r["pmulcg"],
        cold_gate,
        ("praut", "pracw", "paacw_adj", "piacw", "pmulcs", "pmulcg"),
    )
    limit(
        state.qi,
        EPS,  # ice mass :2475
        r["psaut"]
        - r["pinud"]
        - r["pidep"]
        + r["praci"]
        + r["psaci"]
        + r["pgaci"]
        - r["pmulcs"]
        - r["pmulrs"]
        - r["pmulcg"]
        - r["pmulrg"]
        - r["piacw"],
        cold_gate,
        (
            "psaut",
            "pinud",
            "pidep",
            "praci",
            "psaci",
            "pgaci",
            "piacw",
            "pmulcs",
            "pmulrs",
            "pmulcg",
            "pmulrg",
        ),
    )
    limit(
        state.qr,
        EPS,  # rain mass :2495
        -r["praut"]
        - r["prevp"]
        - r["pracw"]
        + r["piacr"]
        + r["psacr_adj"]
        + r["pgacr_adj"]
        + r["pmulrs"]
        + r["pmulrg"],
        cold_gate,
        (
            "praut",
            "prevp",
            "pracw",
            "piacr",
            "psacr_adj",
            "pgacr_adj",
            "pmulrs",
            "pmulrg",
        ),
    )
    limit(
        state.qs,
        EPS,  # snow mass :2512 (pgaut,pgacs≡0)
        -(
            r["psdep"]
            + r["psaut"]
            + r["paacw_adj"]
            + r["piacr"] * delta3
            + r["praci"] * delta3
            - r["pracs"] * one_m_d2
            + r["psacr_adj"] * delta2
            + r["psaci"]
        ),
        cold_gate,
        (
            "psdep",
            "psaut",
            "paacw_adj",
            "piacr",
            "praci",
            "psaci",
            "pracs",
            "psacr_adj",
        ),
    )
    limit(
        state.qg,
        EPS,  # graupel mass :2533 (pgaut,pgacs≡0)
        -(
            r["pgdep"]
            + r["piacr"] * one_m_d3
            + r["praci"] * one_m_d3
            + r["psacr_adj"] * one_m_d2
            + r["pracs"] * one_m_d2
            + r["pgaci"]
            + r["paacw_adj"]
            + r["pgacr_adj"]
        ),
        cold_gate,
        (
            "pgdep",
            "piacr",
            "praci",
            "psacr_adj",
            "pracs",
            "paacw_adj",
            "pgaci",
            "pgacr_adj",
        ),
    )
    limit_ncmin(
        state.nc,  # cloud number :2554
        r["nraut"] + r["nccol"] + r["nracw"] + r["niacw"] + r["naacw"] + r["naacw"],
        cold_gate,
        ("nraut", "nccol", "nracw", "naacw", "niacw"),
    )
    limit_ncmin(
        state.ni,  # ice number :2568
        r["nraci"]
        + r["nsaci"]
        + r["ngaci"]
        + r["niacr"]
        + r["nsaut"]
        - r["nmulcs"]
        - r["nmulcg"]
        - r["nmulrs"]
        - r["nmulrg"]
        - r["ninud"],
        cold_gate,
        (
            "nraci",
            "nsaci",
            "ngaci",
            "niacr",
            "nsaut",
            "ninud",
            "nmulcs",
            "nmulcg",
            "nmulrs",
            "nmulrg",
        ),
    )
    limit(
        state.nr,
        c.NRMIN,  # rain number :2587
        -r["nraut"] + r["nraci"] + r["nrcol"] + r["niacr"] + r["nsacr"] + r["ngacr"],
        cold_gate,
        ("nraci", "nraut", "nrcol", "niacr", "nsacr", "ngacr"),
    )

    # ── PASS 2: warm arm (t>t0c), gate=warm_gate ───────────────────────────
    limit(
        state.qc,
        EPS,  # cloud mass :2657
        r["praut"] + r["pracw"] + r["paacw_adj"] + r["paacw_adj"],
        warm_gate,
        ("praut", "pracw", "paacw_adj"),
    )
    limit(
        state.qr,
        EPS,  # rain mass :2669
        -r["paacw_adj"]
        - r["praut"]
        + r["pseml"]
        + r["pgeml"]
        - r["pracw"]
        - r["paacw_adj"]
        - r["prevp"],
        warm_gate,
        ("praut", "prevp", "pracw", "paacw_adj", "pseml", "pgeml"),
    )
    limit(
        state.qs,
        c.QCRMIN,  # snow mass :2684 (pgacs≡0)
        -r["pseml"] - r["psevp"],
        warm_gate,
        ("psevp", "pseml"),
    )
    limit(
        state.qg,
        c.QCRMIN,  # graupel mass :2695 (pgacs≡0)
        -(r["pgevp"] + r["pgeml"]),
        warm_gate,
        ("pgevp", "pgeml"),
    )
    limit_ncmin(
        state.nc,  # cloud number :2706
        r["nraut"] + r["nccol"] + r["nracw"] + r["naacw"] + r["naacw"],
        warm_gate,
        ("nraut", "nccol", "nracw", "naacw"),
    )
    limit(
        state.nr,
        c.NRMIN,  # rain number :2719
        -r["nraut"] + r["nrcol"] - r["nseml"] - r["ngeml"],
        warm_gate,
        ("nraut", "nrcol", "nseml", "ngeml"),
    )

    warm2 = warm._replace(**{nm: r[nm] for nm in W})
    cold2 = cold._replace(**{nm: r[nm] for nm in C})
    mf2 = mf._replace(**{nm: r[nm] for nm in M})
    return warm2, cold2, mf2
