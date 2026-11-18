"""Replay captured C5 and the complete ordered conservation limiter.

The caller must first authenticate and validate the packet. This module does not
claim that host AD, raw QNICE units, or process identifiability are established.
"""

from collections import namedtuple
import struct
import torch
from oracle.kdm6.cold import IceAggregationParams, ice_aggregation_torch
from .source_order_limiter import scale_rates_for_conservation_torch


def require(condition, message):
    if not condition:
        raise ValueError(message)


def diagnostic_scalar(value):
    """Extract a value for audit/reporting only; never feed it into the AD map."""
    return float(value.detach()) if isinstance(value, torch.Tensor) else float(value)


def bits(x):
    return struct.pack("<d", diagnostic_scalar(x))


def replay(
    rows,
    *,
    qi=None,
    ni=None,
    check=True,
    audit=None,
    producer_overrides=None,
    complete_override=None,
):
    def number(stage, name):
        row = rows[(stage, name)]
        size = {"f32": 4, "f64": 8, "bool": 1}[row["dtype"]]
        b = int(row["raw_hex"], 16).to_bytes(size, "little")
        return struct.unpack({4: "<f", 8: "<d", 1: "<?"}[size], b)[0]

    def tensor(stage, field):
        return torch.tensor([number(stage, field)], dtype=torch.float64)

    def field(owner, name):
        if owner == "working" and name == "qi" and qi is not None:
            return qi
        if owner == "working" and name == "ni" and ni is not None:
            return ni
        return tensor("limiter_in", owner + "." + name)

    def c5(x):
        return tensor("c5_in", x)

    params = IceAggregationParams(
        *(
            number("c5_in", "params." + f)
            for f in ("deni", "di125", "t_split", "qcrmin")
        )
    )
    dt = number("c5_in", "dtcld")
    if check:
        require(bits(dt) == bits(number("limiter_in", "dtcld")), "timestep mismatch")
        require(
            struct.pack("<f", number("c5_in", "fconst.pi_f32"))
            == struct.pack("<f", 3.1415927410125732),
            "pi mismatch",
        )
        for name in ("qi", "ni"):
            require(
                bits(number("c5_in", "state." + name))
                == bits(number("limiter_in", "working." + name)),
                "working state handoff " + name,
            )
    if audit is not None:
        # All conditions affecting C5, plus limiter floor and phase gates.
        q = diagnostic_scalar((qi if qi is not None else c5("state.qi"))[0])
        n = diagnostic_scalar((ni if ni is not None else c5("state.ni"))[0])
        temp = float(c5("state.t")[0])
        den = float(c5("forcing.dend")[0])
        sup = float(c5("pre.supcol")[0])
        import math

        qi0 = (
            0.4632 * 10 ** (-6.0 + 0.0413 * sup) * den
            if temp > params.t_split
            else 0.2316 * 10 ** (-4.0 - 0.0519 * sup) * den
        )
        alpha = 0.005 * math.exp(-0.025 * sup)
        raw = alpha * (q - qi0)
        # The number cap signature is recorded after the true C5 call below.
        audit["c5_margins"] = {
            "cold": sup,
            "qi_positive": q,
            "ni_positive": n,
            "warm_formula": temp - params.t_split,
            "mass_positive": raw,
            "mass_cap": max(raw, 0.0) - q / dt,
            "ice_mass_floor": q - 1e-15,
            "ice_number_floor": n - number("limiter_in", "ncmin"),
            "cold_limiter": number("limiter_in", "pre2.supcol"),
        }
        audit["branches"] = {
            "cold": sup > 0,
            "qi_positive": q > 0,
            "ni_positive": n > 0,
            "warm_formula": temp > params.t_split,
            "mass_positive": raw > 0,
            "mass_cap": max(raw, 0) > q / dt,
            "cold_limiter": number("limiter_in", "pre2.supcol") >= 0,
            "delta2": number("limiter_in", "working.qr") < 1e-4
            and number("limiter_in", "working.qs") < 1e-4,
            "delta3": number("limiter_in", "working.qr") < 1e-4,
            "ice_mass_floor": q < 1e-15,
            "ice_number_floor": n < number("limiter_in", "ncmin"),
        }
    ps, ns = ice_aggregation_torch(
        qi if qi is not None else c5("state.qi"),
        ni if ni is not None else c5("state.ni"),
        c5("state.t"),
        c5("forcing.dend"),
        c5("pre.supcol"),
        params=params,
        dtcld=dt,
    )
    if audit is not None:
        # Recompute the f32-generated Miaut exactly as in the oracle.
        from oracle.kdm6 import fconst as fc

        d = fc._f32(params.di125)
        mass = fc._f32(
            fc._f32(
                fc._f32(fc._f32(fc.PI) * fc._f32(params.deni))
                * fc._f32(fc._f32(d * d) * d)
            )
            / fc._f32(6.0)
        )
        audit["c5_margins"]["number_cap"] = (
            diagnostic_scalar(ps[0]) * den / mass - n / dt
        )
        audit["branches"]["number_cap"] = audit["c5_margins"]["number_cap"] > 0
        audit["c5_outputs"] = {
            "psaut": diagnostic_scalar(ps[0]),
            "nsaut": diagnostic_scalar(ns[0]),
        }
    if check:
        for name, result in [("psaut", ps), ("nsaut", ns)]:
            require(
                bits(result[0]) == bits(number("c5_out", "agg." + name)),
                "C5 raw bits " + name,
            )
            require(
                bits(result[0]) == bits(number("limiter_in", "cold_out." + name)),
                "C5 handoff " + name,
            )
    owners = {
        "working": "qc qr qs qg qi nc nr ni",
        "warm_out": "praut nraut pracw nracw nccol nrcol prevp",
        "cold_out": "praci piacr psaci pgaci nraci niacr nsaci ngaci paacw_adj naacw piacw niacw pracs psacr_adj nsacr pgacr_adj ngacr pmulcs pmulrs pmulcg pmulrg nmulcs nmulrs nmulcg nmulrg pinud ninud pidep psdep pgdep psaut nsaut psevp pgevp",
        "mf5": "pseml nseml pgeml ngeml",
    }
    structs = []
    for owner, names in owners.items():
        names = names.split()
        typ = namedtuple(owner, names)
        vals = [
            producer_overrides[n]
            if owner == "cold_out"
            and producer_overrides is not None
            and n in producer_overrides
            else ps
            if owner == "cold_out" and n == "psaut"
            else ns
            if owner == "cold_out" and n == "nsaut"
            else field(owner, n)
            for n in names
        ]
        structs.append(typ(*vals))
    floor = (
        tensor("limiter_in", "ncmin")
        if number("limiter_in", "ncmin_present") == 1
        else None
    )
    require(number("limiter_in", "ncmin_present") in (0, 1), "ncmin presence")
    if audit is not None:
        audit["limiter"] = []
    warm, cold, mf = scale_rates_for_conservation_torch(
        *[structs[0], tensor("limiter_in", "pre2.supcol"), *structs[1:]],
        dtcld=dt,
        ncmin_tensor=floor,
        audit=None if audit is None else audit["limiter"],
    )
    if audit is not None:
        audit["limited_outputs"] = {
            name: diagnostic_scalar(getattr(cold, name)[0]) for name in cold._fields
        }
    if check:
        for (stage, name), row in rows.items():
            if stage == "limited":
                fieldname = name.removeprefix("scaled.cold.")
                require(
                    bits(getattr(cold, fieldname)[0]) == bits(number(stage, name)),
                    "limiter raw bits " + fieldname,
                )
    # Exact source order for the selected ice state update; D5 ice amounts zero
    # and C4 complete-sublimation flag are captured by the baseline contract.
    cm = (tensor("limiter_in", "pre2.supcol") >= 0).to(torch.float64)
    r = cold
    qi_inner = (
        r.psaut
        + r.praci
        + r.psaci
        + r.pgaci
        - r.pinud
        - r.pidep
        - r.piacw
        - r.pmulcs
        - r.pmulcg
        - r.pmulrs
        - r.pmulrg
    )
    ni_inner = (
        -r.nraci
        - r.nsaci
        - r.ngaci
        - r.niacr
        + r.ninud
        + r.nmulcs
        + r.nmulcg
        + r.nmulrs
        + r.nmulrg
        - r.nsaut
    )
    complete = (
        complete_override.to(torch.float64)
        if complete_override is not None
        else float(number("c4_out", "depsub.ice_complete_sublim"))
    )
    qout = torch.clamp(
        (structs[0].qi + ((0.0 + 0.0) - 0.0)) + cm * (-qi_inner) * dt, min=0.0
    )
    nout = torch.clamp(
        (structs[0].ni + ((0.0 + 0.0) - 0.0)) * (1.0 - complete) + cm * ni_inner * dt,
        min=0.0,
    )
    if check:
        for name, result in [("qi", qout), ("ni", nout)]:
            require(
                bits(result[0]) == bits(number("state_out", "new_state." + name)),
                "state update raw bits " + name,
            )
    return torch.cat((qout, nout))


def derivative_diagnostics(rows):
    """Check two represented coordinate directions on a branch-stable local map.

    All captured producer rates other than C5 are held fixed. The result says
    nothing about host AD or total end-to-end process attribution. Failure to
    find stable finite differences is returned as inconclusive, not a pass.
    """
    import math

    def value(field):
        row = rows[("limiter_in", "working." + field)]
        return struct.unpack("<d", int(row["raw_hex"], 16).to_bytes(8, "little"))[0]

    base = torch.tensor(
        [value("qi"), value("ni")], dtype=torch.float64, requires_grad=True
    )

    def fn(x, audit=None):
        return replay(rows, qi=x[0:1], ni=x[1:2], check=False, audit=audit)

    # Authenticate the base replay against actual captured outputs first.
    replay(rows)
    base_audit = {}
    y = fn(base, base_audit)
    if not torch.isfinite(y).all() or any(diagnostic_scalar(v) <= 0 for v in y):
        return {
            "status": "inconclusive",
            "reason": "state output clamp at or below zero",
            "audit": base_audit,
        }
    if any(v == 0 for v in base_audit["c5_margins"].values()) or any(
        a["active"] and a["margin"] == 0 for a in base_audit["limiter"]
    ):
        return {
            "status": "inconclusive",
            "reason": "exact branch tie",
            "audit": base_audit,
        }
    signature = (
        base_audit["branches"],
        [(a["group"], a["active"], a["binding"]) for a in base_audit["limiter"]],
    )
    directions = []
    for i, name in enumerate(("qi", "ni")):
        x = diagnostic_scalar(base[i])
        if x == 0:
            return {
                "status": "inconclusive",
                "reason": "zero relative direction",
                "direction": name,
                "audit": base_audit,
            }
        direction = torch.zeros_like(base)
        direction[i] = x
        _, tangent = torch.autograd.functional.jvp(fn, base, direction)
        vjp = torch.stack(
            [
                torch.autograd.grad(y[j], base, retain_graph=True)[0][i] * x
                for j in range(2)
            ]
        )
        if not torch.allclose(tangent, vjp, rtol=1e-10, atol=0.0):
            return {
                "status": "inconclusive",
                "reason": "JVP/VJP disagreement",
                "direction": name,
                "audit": base_audit,
            }
        h = max(abs(x) * 1e-4, math.ulp(x) * 128)
        trials = []
        for shrink in (1.0, 0.5, 0.25):
            plus, minus = base.detach().clone(), base.detach().clone()
            plus[i] = x + h * shrink
            minus[i] = x - h * shrink
            delta = float(plus[i]) - float(minus[i])
            if delta == 0:
                continue
            ap, am = {}, {}
            yp, ym = fn(plus, ap), fn(minus, am)

            def sig(a):
                return (
                    a["branches"],
                    [(v["group"], v["active"], v["binding"]) for v in a["limiter"]],
                )

            def strict(a):
                return all(v != 0 for v in a["c5_margins"].values()) and all(
                    not v["active"] or v["margin"] != 0 for v in a["limiter"]
                )

            stable = (
                sig(ap) == signature == sig(am)
                and strict(ap)
                and strict(am)
                and all(float(v) > 0 for v in yp)
                and all(float(v) > 0 for v in ym)
            )
            fd = (yp - ym) / delta * x
            errors = [
                (abs(float(a) - float(b)), max(abs(float(a)), abs(float(b))))
                for a, b in zip(fd, tangent)
            ]
            # Two rounded endpoint values are subtracted before division.
            # Allow four endpoint ULPs for cancellation; this dominates only
            # when the expected directional signal is near output resolution.
            floors = [
                4.0
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
                    "cancellation_floors": floors,
                    "agrees": agreement,
                    "plus_audit": ap,
                    "minus_audit": am,
                }
            )
        if len(trials) != 3 or not all(t["stable"] and t["agrees"] for t in trials):
            return {
                "status": "inconclusive",
                "reason": "branch change or finite-difference disagreement",
                "direction": name,
                "trials": trials,
                "audit": base_audit,
            }
        directions.append(
            {
                "direction": name,
                "jvp": tangent.tolist(),
                "vjp": vjp.tolist(),
                "trials": trials,
            }
        )
    return {
        "status": "pass",
        "directions": directions,
        "audit": base_audit,
        "scope": "relative working QI/NI directions through local C5 plus ordered limiter and selected state update; other producer rates frozen",
    }
