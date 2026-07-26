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

import numpy as np

_F32 = lambda b: np.float32(struct.unpack(">f", struct.pack(">I", b & 0xFFFFFFFF))[0])
_F64 = lambda b: np.float64(struct.unpack(">d", struct.pack(">Q", b))[0])
_B32 = lambda v: struct.unpack(">I", struct.pack(">f", np.float32(v)))[0]
_B64 = lambda v: struct.unpack(">Q", struct.pack(">d", np.float64(v)))[0]


class FidelityError(Exception):
    """A dumped rung does not equal a recomputation from its own operands."""


def _need(mapping, key, what):
    if key not in mapping:
        raise FidelityError(f"{what}: missing operand {key!r}")
    return mapping[key]


def replay_run(run: dict) -> int:
    """Re-derive every ladder rung; raise FidelityError on the first mismatch.
    Returns the number of relations checked (0 means nothing was proven).

    Fail-closed: a missing or wrongly-typed operand is a FidelityError too, not a
    crash — evidence whose variant label disagrees with its own arithmetic (a legacy
    ladder labelled conservative, say) lacks the operands the other variant's
    relations need, and that must READ as a fidelity failure."""
    try:
        return _replay(run)
    except FidelityError:
        raise
    except (KeyError, TypeError, ValueError, IndexError) as e:
        raise FidelityError(f"ladder cannot be replayed: {e!r}") from None


def _replay(run: dict) -> int:
    cons = run["algorithm"] == "conservative"
    ops: dict = {}
    stg: dict = {}
    for o in run["ops"]:
        ops.setdefault((o["loop"], o["chain"], o["n"], o["col"], o["k"],
                        o["species"], o["op_id"]), {})[o["field"]] = int(o["bits"])
    for s in run["stages"]:
        stg[(s["loop"], s["chain"], s["n"], s["col"], s["k"], s["field"])] = int(s["bits"])
    checked = 0

    def eq(name, got, want, where):
        nonlocal checked
        checked += 1
        if got != want:
            raise FidelityError(f"{name} at {where}: dumped {want:#x} != replay {got:#x}")

    for key, f in ops.items():
        loop, chain, n, col, k, sp, op = key
        where = f"loop{loop}/{chain}/n{n}/col{col}/k{k}/{sp}/{op}"
        fam = op.split("_", 1)[1]
        sub = lambda name, kk=k: _need(stg, (loop, chain, n, col, kk, name), where)
        dt = _F32(sub("dtcld", -1))
        dend = _F32(sub("dend_safe"))

        if fam == "FALK":
            if sp == "qr":
                base, w, first = _F32(f["mul_dend_q"]), _F64(sub("work1_qr")), "mul_work1"
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
            res = _F32(f["source_reservoir"])
            out = "dq_out" if sp == "qr" else "dn_out"
            eq(f"OUTFLOW.{out}", _B32(min(o2, res)), f[out], where)

        elif fam == "FALLACC":
            if cons:
                moved = _F32(f["dq_out" if sp == "qr" else "dn_out"])
                if "mul_dend_safe" in f:                 # conservative qr: mass rate
                    m = np.float32(moved * dend)
                    eq("FALLACC.mul_dend_safe", _B32(m), f["mul_dend_safe"], where)
                else:                                    # conservative nr: number rate
                    m = moved
                eq("FALLACC.fall_increment", _B32(np.float32(m / dt)),
                   f["fall_increment"], where)
            eq("FALLACC.fall_after",
               _B32(_F32(f["fall_before"]) + _F32(f["fall_increment"])),
               f["fall_after"], where)

        elif fam == "INFLOW":
            if cons:
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
                prev = _F32(_need(ops, (loop, chain, n, col, k - 1, sp, f"{sp.upper()}_FALK"),
                                  where)["falk_f32"])
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
    return checked
