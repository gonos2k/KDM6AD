#!/usr/bin/env python3
"""Backend-neutral LADDER FIDELITY replay for a normalized G3.3-M run.

The comparator asks "where do the two backends first differ". That question is only
meaningful if each backend's dumped ladder actually IS its arithmetic. Nothing
proved that for the Fortran leg: its offline replay re-derived only the final
clamped update, so a commonly-wrong instrumentation shadow — the SAME wrong
expression emitted by both Fortran variants — would show up as a shared-mechanism
first divergence and could read as PASS.

This module re-derives every rung of the ladder from the operands the producer
itself dumped, for BOTH variants and BOTH backends, and requires bit equality. It
consumes the normalized run (not container payloads), so one implementation covers
all four legs.

Every relation below was verified bit-exactly against real evidence before being
made a gate — the legacy ladder against the committed Fortran sample, the
conservative ladder against the C++ conservative leg.

The decisive one is FALK `falk_f32 == shadow_falk_f32`: the actual value the
transport used against the instrumentation's independent recomputation of it.
"""
from __future__ import annotations

import struct
from collections import Counter

import numpy as np

_F32 = lambda b: np.float32(struct.unpack(">f", struct.pack(">I", b & 0xFFFFFFFF))[0])
_F64 = lambda b: np.float64(struct.unpack(">d", struct.pack(">Q", b))[0])
_B32 = lambda v: struct.unpack(">I", struct.pack(">f", np.float32(v)))[0]
_B64 = lambda v: struct.unpack(">Q", struct.pack(">d", np.float64(v)))[0]

#: water density, a module PARAMETER of the reference (module_mp_wsm6r.F:51). A leg
#: reporting anything else is a different build or corrupt evidence; either must stop
#: a verdict, so the closed world pins it rather than reading it from the leg.
_DENR_BITS = _B32(np.float32(1000.0))


#: which bottom-cell falls feed each accumulator (F:1461-1463). "rain" is the sum of
#: all four and is dumped as bottom_fall_total, so it is replayed as its own rung.
_PRECIP = {"rain": ("bottom_fall_total",),
           "snow": ("bottom_fall_qs", "bottom_fall_qi"),
           "graupel": ("bottom_fall_qg",)}


#: EXACT coverage contract. A count assertion ("more than 300 relations") cannot tell
#: a full ladder from one whose INFLOW family vanished, so the decision path requires
#: the relation NAMES to match exactly. Both committed fixtures produce these same
#: sets -- a 1-loop mstep=1 run and a 3-loop run with mstep heterogeneous across BOTH
#: columns and loops -- so a leg missing a family is a producer defect, not a fixture
#: property, and must read as INVALID_EVIDENCE rather than a thinner check.
_COMMON = {
    "FALK.mul_dend_q", "FALK.mul_work1", "FALK.mul_workn", "FALK.div_mstep",
    "FALK.falk_precast", "FALK.shadow_falk_f32", "FALK.actual==shadow",
    "OUTFLOW.mul_dt", "OUTFLOW.outflow_pre_cap", "OUTFLOW.dq_out", "OUTFLOW.dn_out",
    "INFLOW.mul_delz_src", "INFLOW.inflow_final",
    "FALLACC.fall_increment", "FALLACC.fall_after",
    "UPDATE.q_minus_out", "UPDATE.n_minus_out",
    "UPDATE.q_plus_in_preclamp", "UPDATE.n_plus_in_preclamp",
    "UPDATE.q_post", "UPDATE.n_post",
    "OUTFLOW.source_reservoir(state)", "FALLACC.fall_before(carry)",
    "INFLOW.delz_raw_src(state)", "INFLOW.delz_safe_dst(state)",
    "INFLOW.dend_safe_dst(state)",
    "SURFACE.bottom_fall_qr(carry)", "SURFACE.delz_bottom(state)",
    "SURFACE.bottom_fall_total", "SURFACE.surface_denr",
    "OUTPUT.rain_precip_cumulative", "OUTPUT.snow_precip_cumulative",
    "OUTPUT.graupel_precip_cumulative",
}
#: Emitted only by a producer that distinguishes a RAW metric from its floored SAFE
#: value. The reference Fortran has no floor, so its absence there is structural, not
#: a coverage hole; the C++ bundle layer independently REQUIRES dend_raw/delz_raw, so
#: a C++ leg cannot drop them to dodge these.
OPTIONAL_RELATIONS = frozenset({"METRIC.dend_safe==dend_raw",
                                "METRIC.delz_safe==delz_raw"}
                               | {f"OUTPUT.{p}_increment(actual)"
                                  for p in ("rain", "snow", "graupel")})
RELATION_COVERAGE = {
    "legacy": frozenset(_COMMON | {
        "INFLOW.div_delz_dst", "INFLOW.mul_dt", "INFLOW.inflow_pre_cap",
        "INFLOW.stored_falk_prev(carry)", "INFLOW.stored_falk_nr_prev(carry)",
        "INFLOW.source_reservoir(state)",
        # legacy TOP cells have no capped OUTFLOW op, so the raw depletion is the rung
        "UPDATE.q_minus_out(raw depletion)", "UPDATE.n_minus_out(raw depletion)",
    }),
    "conservative": frozenset(_COMMON | {
        "INFLOW.src_metric", "INFLOW.dst_metric", "INFLOW.mul_src",
        "INFLOW.prev_out(carry)", "INFLOW.prev_out_nr(carry)",
        "FALLACC.mul_dend_safe", "FALLACC.dq_out(carry)", "FALLACC.dn_out(carry)",
        "INFLOW.dend_safe_src(state)",
    }),
}


def surface_increment(operands: dict, dtcld_bits: int, family: str):
    """One loop's precipitation increment for one family, from that loop's surface
    operands (module_mp_kdm6.F:1461-1479). Returns f32 bits."""
    q = lambda nm: _F32(operands[nm])
    fs = q(_PRECIP[family][0])           # rain's first source IS bottom_fall_total
    for nm in _PRECIP[family][1:]:
        fs = np.float32(fs + q(nm))
    if not fs > 0:                       # the source's own guard
        return _B32(np.float32(0.0))
    scaled = np.float32(np.float32(np.float32(fs * q("delz_bottom"))
                                   / q("surface_denr")) * _F32(dtcld_bits))
    return _B32(np.float32(scaled * np.float32(1000.0)))


def expected_surface_increments(run: dict) -> dict:
    """(family, loop, col) -> the increment that loop's own operands imply."""
    srf, dts = {}, {}
    for s in run["stages"]:
        if s["stage"] == "surface":
            srf.setdefault((s["loop"], s["col"]), {})[s["field"]] = int(s["bits"])
        elif s["field"] == "dtcld":
            dts[(s["loop"], s["col"])] = int(s["bits"])
    return {(fam, loop, col): surface_increment(f, dts[(loop, col)], fam)
            for (loop, col), f in srf.items() for fam in _PRECIP}


#: Checked by validate_gate_semantics._check_branch (4-state branch authority from
#: the raw operands), not by an arithmetic rung — so the replay does not read them.
_EXEMPT_FIELDS = frozenset({"cap_active", "inflow_cap_active", "clamp_active"})


class _Tracked(dict):
    """A record whose reads are logged. Comparing relation NAMES alone cannot see a
    replay that skips one cell — the name still appears from every other cell. This
    turns coverage into a per-value property: every dumped field must be read by some
    relation, at every cell, or the run is not fully replayed."""
    __slots__ = ("seen",)

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.seen: set = set()

    def __getitem__(self, key):
        self.seen.add(key)
        return super().__getitem__(key)


class FidelityError(Exception):
    """A dumped rung does not equal a recomputation from its own operands."""


def _need(mapping, key, what):
    if key not in mapping:
        raise FidelityError(f"{what}: missing operand {key!r}")
    return mapping[key]


def replay_report(run: dict) -> Counter:
    """Per-relation counts. Lets a caller assert WHICH relations were checked, not
    just how many: a producer that silently stops emitting an op family would other-
    wise shrink coverage without failing anything."""
    try:
        return _replay(run)
    except FidelityError:
        raise
    except (KeyError, TypeError, ValueError, IndexError) as e:
        raise FidelityError(f"ladder cannot be replayed: {e!r}") from None


def replay_run(run: dict) -> int:
    """Re-derive every ladder rung; raise FidelityError on the first mismatch.
    Returns the number of relations checked (0 means nothing was proven).

    Fail-closed: a missing or wrongly-typed operand is a FidelityError too, not a
    crash — evidence whose variant label disagrees with its own arithmetic (a legacy
    ladder labelled conservative, say) lacks the operands the other variant's
    relations need, and that must READ as a fidelity failure."""
    report = replay_report(run)
    want = RELATION_COVERAGE[run["algorithm"]]
    got = set(report) - OPTIONAL_RELATIONS
    if got != want:
        raise FidelityError(
            f"{run['algorithm']} coverage mismatch: missing "
            f"{sorted(want - got)}, unexpected {sorted(got - want)}")
    return sum(report.values())


def _replay(run: dict) -> Counter:
    cons = run["algorithm"] == "conservative"
    ops: dict = {}
    stg: dict = {}
    srf: dict = {}      # (loop, col) -> surface operands
    fin: dict = {}      # col        -> whole-step accumulators
    dts: dict = {}      # (loop, col) -> dtcld
    incs: dict = run.get("surface_increments", {})   # producer's own per-loop values
    for o in run["ops"]:
        ops.setdefault((o["loop"], o["chain"], o["n"], o["col"], o["k"],
                        o["species"], o["op_id"]), _Tracked())[o["field"]] = int(o["bits"])
    for s in run["stages"]:
        stg[(s["loop"], s["chain"], s["n"], s["col"], s["k"], s["field"])] = int(s["bits"])
        if s["stage"] == "surface":
            srf.setdefault((s["loop"], s["col"]), _Tracked())[s["field"]] = int(s["bits"])
        elif s["stage"] == "final_output":
            fin.setdefault(s["col"], _Tracked())[s["field"]] = int(s["bits"])
        elif s["field"] == "dtcld":
            dts[(s["loop"], s["col"])] = int(s["bits"])
    kbot = max((k for (_l, _c, _n, _co, k, _f) in stg), default=-1)   # bottom cell
    counts: Counter = Counter()

    def eq(name, got, want, where):
        counts[name] += 1
        if got != want:
            raise FidelityError(f"{name} at {where}: dumped {want:#x} != replay {got:#x}")

    # The ladder divides by dend_safe/delz_safe and treats them as the producer's own
    # operands. That holds only while the metric floor is inert, so prove it here
    # rather than inherit it: a floored metric silently changes the divisor.
    for (loop, chain, n, col, k, fld), raw in sorted(run.get("raw_metrics", {}).items()):
        safe, w = fld.replace("_raw", "_safe"), f"loop{loop}/n{n}/col{col}/k{k}"
        eq(f"METRIC.{safe}=={fld}", _need(stg, (loop, chain, n, col, k, safe), w),
           raw, w)

    for key, f in ops.items():
        loop, chain, n, col, k, sp, op = key
        where = f"loop{loop}/{chain}/n{n}/col{col}/k{k}/{sp}/{op}"
        fam = op.split("_", 1)[1]
        sub = lambda name, kk=k: _need(stg, (loop, chain, n, col, kk, name), where)
        dt = _F32(sub("dtcld", -1))
        dend = _F32(sub("dend_safe"))

        if fam == "FALK":
            if sp == "qr":
                # mul_dend_q was previously TRUSTED as the chain's input. Recompute it
                # from the state: the metric floor is barred on a valid fixture, so
                # dend_safe == dend_raw and this is the producer's own operand.
                base = np.float32(_F32(sub("dend_safe")) * _F32(sub("qr")))
                eq("FALK.mul_dend_q", _B32(base), f["mul_dend_q"], where)
                w, first = _F64(sub("work1_qr")), "mul_work1"
            else:
                base, w, first = _F32(sub("nr")), _F64(sub("workn_qr")), "mul_workn"
            s2 = np.float64(base) * w
            eq("FALK." + first, _B64(s2), f[first], where)
            s3 = s2 / np.float64(sub("mstep", -1))
            eq("FALK.div_mstep", _B64(s3), f["div_mstep"], where)
            s4 = s3 * np.float64(sub("gate", -1))
            eq("FALK.falk_precast", _B64(s4), f["falk_precast"], where)
            eq("FALK.shadow_falk_f32", _B32(np.float32(s4)), f["shadow_falk_f32"], where)
            # THE fidelity claim: the value the transport actually used equals the
            # instrumentation's independent recomputation of it.
            eq("FALK.actual==shadow", f["shadow_falk_f32"], f["falk_f32"], where)

        elif fam == "OUTFLOW":
            falk = _F32(_need(ops, (loop, chain, n, col, k, sp, f"{sp.upper()}_FALK"),
                              where)["falk_f32"])
            if sp == "qr":
                o1 = np.float32(falk * dt)
                eq("OUTFLOW.mul_dt", _B32(o1), f["mul_dt"], where)
                o2 = np.float32(o1 / dend)
            else:
                o2 = np.float32(falk * dt)
            eq("OUTFLOW.outflow_pre_cap", _B32(o2), f["outflow_pre_cap"], where)
            # Pin the cap operand to the state it must BE. Without this a lifted
            # reservoir is inert whenever the cap is inactive, so corrupt evidence
            # could hide a cap that should have bound and still replay clean.
            upd = _need(ops, (loop, chain, n, col, k, sp, f"{sp.upper()}_UPDATE"), where)
            eq("OUTFLOW.source_reservoir(state)",
               _need(upd, "q_before" if sp == "qr" else "n_before", where),
               f["source_reservoir"], where)
            res = _F32(f["source_reservoir"])
            out = "dq_out" if sp == "qr" else "dn_out"
            eq(f"OUTFLOW.{out}", _B32(min(o2, res)), f[out], where)

        elif fam == "FALLACC":
            falk_k = (loop, chain, n, col, k, sp, f"{sp.upper()}_FALK")
            out_k = (loop, chain, n, col, k, sp, f"{sp.upper()}_OUTFLOW")
            if cons:
                moved_name = "dq_out" if sp == "qr" else "dn_out"
                if out_k in ops:      # the carried outflow must BE the outflow
                    eq(f"FALLACC.{moved_name}(carry)", ops[out_k][moved_name],
                       f[moved_name], where)
                moved = _F32(f[moved_name])
                if "mul_dend_safe" in f:                 # conservative qr: mass rate
                    m = np.float32(moved * dend)
                    eq("FALLACC.mul_dend_safe", _B32(m), f["mul_dend_safe"], where)
                else:                                    # conservative nr: number rate
                    m = moved
                eq("FALLACC.fall_increment", _B32(np.float32(m / dt)),
                   f["fall_increment"], where)
            else:
                # legacy accumulates the raw falk itself
                eq("FALLACC.fall_increment", _need(ops, falk_k, where)["falk_f32"],
                   f["fall_increment"], where)
            # the accumulator's own carry: 0 at the first substep, else what the
            # previous substep left. Unpinned, a fall_before could absorb a wrong
            # increment and still land on the right fall_after.
            prev = ops.get((loop, chain, n - 1, col, k, sp, f"{sp.upper()}_FALLACC"))
            eq("FALLACC.fall_before(carry)",
               0 if n == 1 else _need(prev or {}, "fall_after", where),
               f["fall_before"], where)
            eq("FALLACC.fall_after",
               _B32(_F32(f["fall_before"]) + _F32(f["fall_increment"])),
               f["fall_after"], where)

        elif fam == "INFLOW":
            # Op-level copies of the cell state. delz_raw_src is compared against the
            # SAFE metric because the floor is proved inert (METRIC.* above), so the
            # two are the same value and one relation covers every leg.
            for opnd, fld, kk in (("delz_raw_src", "delz_safe", k - 1),
                                  ("delz_safe_dst", "delz_safe", k),
                                  ("dend_safe_dst", "dend_safe", k),
                                  ("dend_safe_src", "dend_safe", k - 1)):
                if opnd in f:
                    eq(f"INFLOW.{opnd}(state)",
                       _need(stg, (loop, chain, n, col, kk, fld), where), f[opnd], where)
            if cons:
                above_out = (loop, chain, n, col, k - 1, sp, f"{sp.upper()}_OUTFLOW")
                pv = "prev_out" if sp == "qr" else "prev_out_nr"
                if pv in f and above_out in ops:      # carried from the cell above
                    eq(f"INFLOW.{pv}(carry)",
                       ops[above_out]["dq_out" if sp == "qr" else "dn_out"], f[pv], where)
                if "src_metric" in f:                    # conservative qr: rho*dz
                    sm = np.float32(_F32(f["dend_safe_src"]) * _F32(f["delz_raw_src"]))
                    eq("INFLOW.src_metric", _B32(sm), f["src_metric"], where)
                    dm = np.float32(_F32(f["dend_safe_dst"]) * _F32(f["delz_safe_dst"]))
                    eq("INFLOW.dst_metric", _B32(dm), f["dst_metric"], where)
                    ms = np.float32(_F32(f["prev_out"]) * _F32(f["src_metric"]))
                    eq("INFLOW.mul_src", _B32(ms), f["mul_src"], where)
                    eq("INFLOW.inflow_final",
                       _B32(np.float32(ms / _F32(f["dst_metric"]))), f["inflow_final"], where)
                else:                                    # conservative nr: dz only
                    mv = np.float32(_F32(f["prev_out_nr"]) * _F32(f["delz_raw_src"]))
                    eq("INFLOW.mul_delz_src", _B32(mv), f["mul_delz_src"], where)
                    eq("INFLOW.inflow_final",
                       _B32(np.float32(mv / _F32(f["delz_safe_dst"]))), f["inflow_final"], where)
            else:
                above = _need(ops, (loop, chain, n, col, k - 1, sp, f"{sp.upper()}_FALK"),
                              where)["falk_f32"]
                if "stored_falk_prev" in f or "stored_falk_nr_prev" in f:
                    nm = "stored_falk_prev" if "stored_falk_prev" in f else "stored_falk_nr_prev"
                    eq(f"INFLOW.{nm}(carry)", above, f[nm], where)
                prev = _F32(above)
                i1 = np.float32(prev * _F32(sub("delz_safe", k - 1)))
                eq("INFLOW.mul_delz_src", _B32(i1), f["mul_delz_src"], where)
                i2 = np.float32(i1 / _F32(sub("delz_safe")))
                eq("INFLOW.div_delz_dst", _B32(i2), f["div_delz_dst"], where)
                if sp == "qr":
                    i3 = np.float32(i2 * dt)
                    eq("INFLOW.mul_dt", _B32(i3), f["mul_dt"], where)
                    i4 = np.float32(i3 / dend)
                else:
                    i4 = np.float32(i2 * dt)
                eq("INFLOW.inflow_pre_cap", _B32(i4), f["inflow_pre_cap"], where)
                above_upd = _need(ops, (loop, chain, n, col, k - 1, sp,
                                        f"{sp.upper()}_UPDATE"), where)
                eq("INFLOW.source_reservoir(state)",
                   _need(above_upd, "q_post" if sp == "qr" else "n_post", where),
                   f["source_reservoir"], where)
                eq("INFLOW.inflow_final",
                   _B32(min(i4, _F32(f["source_reservoir"]))), f["inflow_final"], where)

        elif fam == "UPDATE":
            before = "q_before" if sp == "qr" else "n_before"
            minus = "q_minus_out" if sp == "qr" else "n_minus_out"
            plus = "q_plus_in_preclamp" if sp == "qr" else "n_plus_in_preclamp"
            post = "q_post" if sp == "qr" else "n_post"
            outk = (loop, chain, n, col, k, sp, f"{sp.upper()}_OUTFLOW")
            if outk in ops:
                moved = _F32(ops[outk]["dq_out" if sp == "qr" else "dn_out"])
                eq(f"UPDATE.{minus}", _B32(_F32(f[before]) - moved), f[minus], where)
            else:
                # legacy TOP: no capped OUTFLOW op, so the RAW depletion is the rung
                falk = _F32(_need(ops, (loop, chain, n, col, k, sp, f"{sp.upper()}_FALK"),
                                  where)["falk_f32"])
                cand = (np.float32(np.float32(falk * dt) / dend) if sp == "qr"
                        else np.float32(falk * dt))
                eq(f"UPDATE.{minus}(raw depletion)",
                   _B32(_F32(f[before]) - cand), f[minus], where)
            last = minus
            if plus in f:
                infk = (loop, chain, n, col, k, sp, f"{sp.upper()}_INFLOW")
                gained = _F32(_need(ops, infk, where)["inflow_final"])
                eq(f"UPDATE.{plus}", _B32(_F32(f[minus]) + gained), f[plus], where)
                last = plus
            if cons:                       # conservative does NOT clamp
                eq(f"UPDATE.{post}", f[last], f[post], where)
            else:
                eq(f"UPDATE.{post}",
                   _B32(max(_F32(f[last]), np.float32(0.0))), f[post], where)

    # ---- surface conversion and the whole-step accumulation --------------------
    # module_mp_kdm6.F:1461-1479. fallsum is the bottom-cell fall of all four
    # species; each accumulator adds  fallsum*delz/denr*dtcld*1000  and ONLY when
    # its own fallsum is positive, so the guard is part of the arithmetic.
    for col in sorted(fin):
        acc = {p: np.float32(0.0) for p in _PRECIP}
        for loop in sorted(lp for (lp, c) in srf if c == col):
            f, where = srf[(loop, col)], f"loop{loop}/col{col}/surface"
            q = lambda nm: _F32(_need(f, nm, where))
            # Tie the surface operands back to the transport ladder. Without this a
            # perturbed operand can be absorbed below the ULP of the accumulated sum
            # and replay clean, so the link -- not the sum -- is what pins them.
            nmax = max((n for (lp, _ch, n, c, _k, _sp, op) in ops
                        if lp == loop and c == col and op == "QR_FALLACC"), default=None)
            if nmax is not None:
                eq("SURFACE.bottom_fall_qr(carry)",
                   _need(_need(ops, (loop, "main", nmax, col, kbot, "qr", "QR_FALLACC"),
                               where), "fall_after", where),
                   f["bottom_fall_qr"], where)
            eq("SURFACE.delz_bottom(state)",
               _need(stg, (loop, "main", 1, col, kbot, "delz_safe"), where),
               f["delz_bottom"], where)
            total = q("bottom_fall_qr")
            for nm in ("bottom_fall_qs", "bottom_fall_qg", "bottom_fall_qi"):
                total = np.float32(total + q(nm))
            eq("SURFACE.bottom_fall_total", _B32(total), f["bottom_fall_total"], where)
            eq("SURFACE.surface_denr", _DENR_BITS, f["surface_denr"], where)
            for p in _PRECIP:
                inc_bits = surface_increment(f, _need(dts, (loop, col), where), p)
                # If the producer emitted THIS loop's increment, gate it HERE. Folding
                # first and comparing only the total is blind twice over: loop 1 high
                # by eps and loop 2 low by eps cancel, and on this very fixture a
                # 1-ULP error in ANY loop leaves the f32 total bit-identical.
                actual = incs.get((p, loop, col))
                if actual is not None:
                    eq(f"OUTPUT.{p}_increment(actual)", inc_bits, actual, where)
                    inc_bits = actual
                acc[p] = np.float32(_F32(inc_bits) + acc[p])
        # the RETURNED whole-step output must be the fold of those same increments
        for p in _PRECIP:                        # sum_L, not the last loop's value
            eq(f"OUTPUT.{p}_precip_cumulative", _B32(acc[p]),
               _need(fin[col], f"{p}_precip_cumulative", f"col{col}/final_output"),
               f"col{col}")

    # Per-VALUE coverage: every dumped field, at every cell, was read by some relation.
    unchecked = sorted({f"{key[-1]}.{fld}" if isinstance(key, tuple) else f"surface.{fld}"
                        for group in (ops, srf, fin)
                        for key, rec in group.items()
                        for fld in rec
                        if fld not in rec.seen and fld not in _EXEMPT_FIELDS})
    if unchecked:
        raise FidelityError(f"dumped values never checked by any relation: {unchecked}")
    return counts
