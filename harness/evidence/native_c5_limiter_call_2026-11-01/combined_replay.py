"""Conditional C3/C4/C5 -> limiter -> ice state map on captured operands.

All non-selected producer rates and precomputed auxiliaries remain frozen.
Diagnostic scalar extraction is value-only and never feeds the model graph.
"""

import math
import struct
import torch
from oracle.kdm6 import fconst as fc
from oracle.kdm6.cold import (
    default_dep_sub_params,
    default_ice_nucleation_params,
    dep_sub_torch,
    ice_nucleation_torch,
)
from .replay import replay, bits, require, diagnostic_scalar


def read(rows, stage, field):
    row = rows[(stage, field)]
    size = {"f32": 4, "f64": 8, "bool": 1}[row["dtype"]]
    return struct.unpack(
        {4: "<f", 8: "<d", 1: "<?"}[size],
        int(row["raw_hex"], 16).to_bytes(size, "little"),
    )[0]


def combined(rows, qi, ni, *, check=False, audit=None, ice_aux=None):
    def t(stage, field):
        return torch.tensor([read(rows, stage, field)], dtype=torch.float64)

    def v(stage, field):
        return read(rows, stage, field)

    dt = v("c5_in", "dtcld")
    p = default_ice_nucleation_params()
    dp = default_dep_sub_params()
    c3 = ice_nucleation_torch(
        *(t("c3_in", x) for x in ("pre.supcol", "pre.supsat", "pre.rh_ice", "prevp")),
        ni,
        t("c3_in", "forcing.dend"),
        params=p,
        dtcld=dt,
    )
    args = [qi] + [t("c4_in", x) for x in ("state.qs", "state.qg")]
    args += [t("c3_in", x) for x in ("pre.rh_ice", "pre.supcol", "pre.supsat", "prevp")]
    n0i = t("c4_in", "n0i") if ice_aux is None else ice_aux[0]
    rslope2_i = t("c4_in", "s.rslope2_i") if ice_aux is None else ice_aux[1]
    args += [c3.pinud, c3.ifsat, n0i]
    args += [
        rslope2_i if x == "s.rslope2_i" else t("c4_in", x)
        for x in (
            "n0so",
            "n0go",
            "s.n0sfac_field",
            "work1_ice",
            "pre.work2",
            "pre.precg2",
            "s.rslope_s",
            "s.rslope2_s",
            "s.rslopeb_s",
            "s.rslopemu_s",
            "s.rslope_g",
            "s.rslope2_g",
            "s.rslopeb_g",
            "s.rslopemu_g",
            "s.rslope2_i",
            "s.rslopemu_i",
        )
    ]
    c4 = dep_sub_torch(*args, params=dp, dtcld=dt)
    rates = {
        "pinud": c3.pinud,
        "ninud": c3.ninud,
        "pidep": c4.pidep,
        "psdep": c4.psdep,
        "pgdep": c4.pgdep,
    }
    if check:
        for name, obj, stage in (
            ("pinud", c3, "c3_out"),
            ("ninud", c3, "c3_out"),
            ("pidep", c4, "c4_out"),
            ("psdep", c4, "c4_out"),
            ("pgdep", c4, "c4_out"),
        ):
            prefix = "icenuc." if stage == "c3_out" else "depsub."
            require(
                bits(getattr(obj, name)[0]) == bits(v(stage, prefix + name)),
                "combined producer raw bits " + name,
            )
            require(
                bits(getattr(obj, name)[0])
                == bits(v("limiter_in", "cold_out." + name)),
                "combined prelimit handoff " + name,
            )
        for obj, stage, prefix, names in (
            (c3, "c3_out", "icenuc.", ("ifsat",)),
            (c4, "c4_out", "depsub.", ("ifsat", "ice_complete_sublim")),
        ):
            for name in names:
                require(
                    bool(getattr(obj, name)[0]) == v(stage, prefix + name),
                    "combined branch " + name,
                )
        require(
            bits(qi[0]) == bits(v("c4_in", "state.qi"))
            and bits(ni[0]) == bits(v("c3_in", "state.ni")),
            "combined working handoff",
        )
    if audit is not None:
        audit["producers"] = producer_audit(rows, qi, ni, c3, c4, p, dp, dt)
    return replay(
        rows,
        qi=qi,
        ni=ni,
        check=check,
        audit=audit,
        producer_overrides=rates,
        complete_override=c4.ice_complete_sublim,
    )


def producer_audit(rows, qi, ni, c3, c4, p, dp, dt):
    """Value-only source-order branch margins for each active C3/C4 arm."""

    def v(stage, field):
        return read(rows, stage, field)

    q = diagnostic_scalar(qi[0])
    n = diagnostic_scalar(ni[0])
    sup = v("c3_in", "pre.supcol")
    sat = v("c3_in", "pre.supsat")
    rh = v("c3_in", "pre.rh_ice")
    prev = v("c3_in", "prevp")
    den = v("c3_in", "forcing.dend")
    sd = sat / dt
    nidraw = (p.cooper_a * math.exp(p.cooper_b * sup)) * p.cooper_unit
    nid = min(max(nidraw, 0.0), p.nid_max)
    rn = fc._f32(p.rinud)
    mass = fc._f32(
        fc._f32(fc._f32(fc._f32(4.0 / 3.0) * fc._f32(fc.PI)) * fc._f32(p.deni))
        * fc._f32(fc._f32(rn * rn) * rn)
    )
    c3caps = [(nid - n) / dt / max(den, 1e-9) * mass, 0.5 * sd, sd - prev]
    outer = (sup > p.supcol_threshold and sat > 0) or rh > p.rh_ice_threshold
    active = outer and nid > n
    strict = []

    def margin(name, value, needed=True):
        if needed:
            strict.append((name, value))

    for name, val in [
        ("c3_supcol", sup - p.supcol_threshold),
        ("c3_sat", sat),
        ("c3_rh", rh - p.rh_ice_threshold),
        ("c3_nid_low", nidraw),
        ("c3_nid_high", nidraw - p.nid_max),
        ("c3_inner", nid - n),
        ("c3_den_floor", den - 1e-9),
    ]:
        margin(name, val)
    if active:
        for i in range(3):
            for j in range(i):
                margin("c3_cap_%d_%d" % (i, j), c3caps[i] - c3caps[j])
    pin = diagnostic_scalar(c3.pinud[0])
    ice = diagnostic_scalar(c4.pidep[0])
    snow = diagnostic_scalar(c4.psdep[0])
    graupel = diagnostic_scalar(c4.pgdep[0])
    r1 = max(v("c4_in", "work1_ice"), dp.qcrmin)
    margin("c4_work1_floor", v("c4_in", "work1_ice") - dp.qcrmin)
    ice_raw = (
        4
        * v("c4_in", "n0i")
        * dp.g2pmi
        * v("c4_in", "s.rslopemu_i")
        * v("c4_in", "s.rslope2_i")
        * (rh - 1)
        / r1
    )
    slope_s = v("c4_in", "s.rslope_s")
    slope_g = v("c4_in", "s.rslope_g")
    smul = slope_s * v("c4_in", "s.rslopeb_s")
    gmul = slope_g * v("c4_in", "s.rslopeb_g")
    margin("c4_snow_sqrt_floor", smul - dp.qcrmin)
    margin("c4_graupel_sqrt_floor", gmul - dp.qcrmin)
    cs = (
        v("c4_in", "s.rslope2_s")
        * math.sqrt(max(smul, dp.qcrmin))
        * v("c4_in", "s.rslopemu_s")
    )
    cg = (
        v("c4_in", "s.rslope2_g")
        * math.sqrt(max(gmul, dp.qcrmin))
        * v("c4_in", "s.rslopemu_g")
    )
    sr = (
        (rh - 1)
        * v("c4_in", "s.n0sfac_field")
        * (
            dp.precs1
            * v("c4_in", "n0so")
            * v("c4_in", "s.rslope2_s")
            * v("c4_in", "s.rslopemu_s")
            + dp.precs2 * v("c4_in", "n0so") * v("c4_in", "pre.work2") * cs
        )
        / r1
    )
    gr = (
        (rh - 1)
        * (
            dp.precg1
            * v("c4_in", "n0go")
            * v("c4_in", "s.rslope2_g")
            * v("c4_in", "s.rslopemu_g")
            + v("c4_in", "pre.precg2")
            * v("c4_in", "n0go")
            * v("c4_in", "pre.work2")
            * cg
        )
        / r1
    )
    cold = sup > 0
    ifsat = bool(c3.ifsat[0])
    phases = []
    for name, res, raw, supply, amount in [
        ("ice", q, ice_raw, sd - prev - pin, ice),
        ("snow", v("c4_in", "state.qs"), sr, sd - prev - pin - ice, snow),
        ("graupel", v("c4_in", "state.qg"), gr, sd - prev - pin - ice - snow, graupel),
    ]:
        entered = cold and res > 0 and not ifsat
        margin("c4_" + name + "_reservoir", res)
        margin("c4_" + name + "_raw_sign", raw, entered)
        caps = (
            [raw, 0.5 * sd, supply] if raw >= 0 else [raw, -res / dt, 0.5 * sd, supply]
        )
        if entered:
            for i in range(len(caps)):
                for j in range(i):
                    margin("c4_" + name + "_cap_%d_%d" % (i, j), caps[i] - caps[j])
        chosen = max(caps) if raw < 0 else min(caps)
        winner = caps.index(chosen)
        running = (
            prev
            + pin
            + ice
            + (snow if name != "ice" else 0)
            + (graupel if name == "graupel" else 0)
        )
        # For ice the cumulative rate contains ice; snow adds snow; graupel adds both.
        sm = abs(running) - abs(sd)
        margin("c4_" + name + "_saturation", sm, entered)
        ifsat = ifsat or (entered and sm >= 0)
        if name == "ice":
            margin("c4_complete_sublimation", raw + q / dt, entered and raw < 0)
        phases.append((name, entered, raw < 0, winner if entered else None, ifsat))
    margin("c4_cold", sup)
    c3_sat = abs(prev + pin) - abs(sd)
    margin("c3_saturation", c3_sat, outer)
    return {
        "margins": dict(strict),
        # Explicitly frozen input words; never perturbed by the QI/NI map.
        "frozen_species_bits": {
            species: rows[("c4_in", "state." + species)]["raw_hex"]
            for species in ("qs", "qg")
        },
        "signature": {
            "c3_outer": outer,
            "c3_inner": nid > n,
            "c3_cap": c3caps.index(min(c3caps)) if active else None,
            "c3_ifsat": bool(c3.ifsat[0]),
            "c4_phases": phases,
            "c4_ifsat": bool(c4.ifsat[0]),
            "complete_sublim": bool(c4.ice_complete_sublim[0]),
        },
    }


def combined_diagnostics(rows):
    """Run only on strictly untied producer/limiter branches; otherwise inconclusive."""
    base = torch.tensor(
        [
            read(rows, "limiter_in", "working.qi"),
            read(rows, "limiter_in", "working.ni"),
        ],
        dtype=torch.float64,
        requires_grad=True,
    )

    def f(x, audit=None):
        return combined(rows, x[0:1], x[1:2], audit=audit)

    # Raw value gate precedes any AD claim.
    combined(rows, base[0:1], base[1:2], check=True)
    initial = {}
    y = f(base, initial)

    def ties(a):
        # QS/QG are fixed packet operands. At exactly zero their inactive
        # C4 gates are tied, but cannot change in either tested direction.
        excluded = {"c4_snow_reservoir": "qs", "c4_graupel_reservoir": "qg"}
        frozen = a["producers"]["frozen_species_bits"]
        out = [
            "producer/" + k
            for k, v in a["producers"]["margins"].items()
            if v == 0 and not (k in excluded and int(frozen[excluded[k]], 16) == 0)
        ]
        out += ["c5/" + k for k, v in a["c5_margins"].items() if v == 0]
        out += [
            "limiter/" + v["group"]
            for v in a["limiter"]
            if v["active"] and v["margin"] == 0
        ]
        return out

    def sig(a):
        return (
            a["producers"]["signature"],
            a["branches"],
            [(v["group"], v["active"], v["binding"]) for v in a["limiter"]],
        )

    tied = ties(initial)
    if tied:
        return {
            "status": "inconclusive",
            "reason": "exact branch tie",
            "ties": tied,
            "audit": initial,
        }
    if any(diagnostic_scalar(x) <= 0 for x in y):
        return {"status": "inconclusive", "reason": "output clamp", "audit": initial}
    baseline_sig = sig(initial)
    frozen_bits = initial["producers"]["frozen_species_bits"]
    require(
        all(int(v, 16) == 0 for v in frozen_bits.values()),
        "frozen QS/QG zero-gate contract",
    )
    directions = []
    for i, name in enumerate(("qi", "ni")):
        x = diagnostic_scalar(base[i])
        if x == 0:
            return {
                "status": "inconclusive",
                "reason": "zero relative direction",
                "direction": name,
                "audit": initial,
            }
        direction = torch.zeros_like(base)
        direction[i] = x
        _, jvp = torch.autograd.functional.jvp(f, base, direction)
        vjp = torch.stack(
            [
                torch.autograd.grad(y[j], base, retain_graph=True)[0][i] * x
                for j in range(2)
            ]
        )
        # Near-zero output directions can lose a few ULPs when large
        # state-update tangent terms cancel. Use an output-scale rounding
        # allowance only when both directional values are within that floor.
        transpose_errors = []
        for value, forward, reverse in zip(y, jvp, vjp):
            a = diagnostic_scalar(forward)
            b = diagnostic_scalar(reverse)
            floor = 16.0 * math.ulp(diagnostic_scalar(value))
            scale = max(abs(a), abs(b))
            bound = floor if scale <= floor else 1e-10 * scale
            transpose_errors.append((abs(a - b), bound, floor))
        if any(err > bound for err, bound, _ in transpose_errors):
            return {
                "status": "inconclusive",
                "reason": "JVP/VJP mismatch",
                "direction": name,
                "audit": initial,
            }
        trials = []
        for factor in (1.0, 0.5, 0.25):
            h = max(abs(x) * 1e-4, math.ulp(x) * 128) * factor
            plus = base.detach().clone()
            minus = base.detach().clone()
            plus[i] = x + h
            minus[i] = x - h
            delta = diagnostic_scalar(plus[i]) - diagnostic_scalar(minus[i])
            if not delta:
                return {
                    "status": "inconclusive",
                    "reason": "unrepresented perturbation",
                    "direction": name,
                    "audit": initial,
                }
            ap = {}
            am = {}
            yp = f(plus, ap)
            ym = f(minus, am)
            stable = (
                sig(ap) == baseline_sig == sig(am)
                and not ties(ap)
                and not ties(am)
                and ap["producers"]["frozen_species_bits"] == frozen_bits
                and am["producers"]["frozen_species_bits"] == frozen_bits
                and all(diagnostic_scalar(v) > 0 for v in yp)
                and all(diagnostic_scalar(v) > 0 for v in ym)
            )
            fd = (yp - ym) / delta * x
            errors = [
                (
                    abs(diagnostic_scalar(a) - diagnostic_scalar(b)),
                    max(abs(diagnostic_scalar(a)), abs(diagnostic_scalar(b))),
                )
                for a, b in zip(fd, jvp)
            ]
            floors = [
                4
                * (math.ulp(diagnostic_scalar(a)) + math.ulp(diagnostic_scalar(b)))
                * abs(x / delta)
                for a, b in zip(yp, ym)
            ]
            bounds = [
                floor if scale <= floor else 1e-8 * scale
                for (_, scale), floor in zip(errors, floors)
            ]
            agreement = all(err <= bound for (err, _), bound in zip(errors, bounds))
            trials.append(
                {
                    "represented_delta": delta,
                    "stable": stable,
                    "fd": fd.tolist(),
                    "absolute_errors": [e for e, _ in errors],
                    "bounds": bounds,
                    "plus_audit": ap,
                    "minus_audit": am,
                }
            )
            if not stable or not agreement:
                return {
                    "status": "inconclusive",
                    "reason": "branch change or FD disagreement",
                    "direction": name,
                    "trials": trials,
                    "audit": initial,
                }
        directions.append(
            {
                "direction": name,
                "jvp": jvp.tolist(),
                "vjp": vjp.tolist(),
                "transpose_errors_bounds_floors": transpose_errors,
                "trials": trials,
            }
        )
    return {
        "status": "pass",
        "directions": directions,
        "audit": initial,
        "scope": "conditional combined producer map; precomputed auxiliaries and other producers frozen",
        "frozen_zero_gate_exclusions": ["C4 QS", "C4 QG"],
    }


def main():
    """Authenticate the native packet before running the optional combined map."""
    import argparse
    import json
    from pathlib import Path
    from .verify_packet import verify

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    try:
        raw = args.packet.read_bytes()
        verify(raw, args.sha256)
        packet = json.loads(raw)
        cells = {
            k: {
                (row["stage"], row["field"]): row
                for row in packet["selected_rows"]
                if row["k_zero"] == k
            }
            for k in ("20", "22")
        }
        print(
            json.dumps(
                {k: combined_diagnostics(rows) for k, rows in cells.items()},
                indent=2,
                allow_nan=False,
            )
        )
    except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as exc:
        parser.exit(1, "INVALID: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
