"""Replay selected C-arm guard and source-ordered mass/volume/heat events."""
from __future__ import annotations

import math
from collections import Counter
from typing import Any, Iterable

from replay_progb_validity import PROGB_CALL_CONTEXTS

from s10_progb_zero_qg_guard import (
    brs_volume_stage1,
    brs_volume_stage2,
    brs_volume_stage3,
    f32,
    guarded_rate_over_density,
    heat_stage1,
    heat_stage2,
    qg_mass_stage1,
    qg_mass_stage2,
    qg_mass_stage3,
    xlwork2_stage2,
    xlwork2_stage3,
)

GUARD_CONSUMER_STAGE = {1418: 1, 2824: 2, 2915: 3, 2916: 3}
EVENT_WIDTHS = {
    "S10MELTGATE": (8, 3),
    "S10PHASE": (8, 3),
    "S10ZG": (9, 3),
    "S10MASS": (8, None),
    "S10VOLUME": (8, None),
    "S10HEAT": (8, None),
}


def _parse(lines: Iterable[str], tag: str,
           int_width: int, real_width: int | None = None) -> list[dict[str, Any]]:
    out = []
    for line_no, line in enumerate(lines, 1):
        fields = line.split()
        if not fields or fields[0] != tag:
            continue
        if len(fields) < int_width + 1:
            raise ValueError(f"line {line_no}: {tag} is truncated")
        try:
            ints = tuple(int(x, 10) for x in fields[1:1 + int_width])
            reals = tuple(float(x) for x in fields[1 + int_width:])
        except ValueError as exc:
            raise ValueError(f"line {line_no}: malformed {tag} event") from exc
        if real_width is not None and len(reals) != real_width:
            raise ValueError(f"line {line_no}: {tag} has {len(reals)} reals, expected {real_width}")
        if not all(math.isfinite(x) for x in reals):
            raise ValueError(f"line {line_no}: {tag} contains a non-finite operand")
        out.append({"ints": ints, "reals": reals, "line": line_no})
    return out


def _unique(rows: list[dict[str, Any]], key_width: int, tag: str) -> dict[tuple[int, ...], dict[str, Any]]:
    result: dict[tuple[int, ...], dict[str, Any]] = {}
    for row in rows:
        key = row["ints"][:key_width]
        if key in result:
            raise ValueError(f"duplicate {tag} key {key}")
        result[key] = row
    return result


def _eq32(actual: float, expected: float, where: str) -> None:
    if f32(actual) != f32(expected):
        raise ValueError(f"{where}: source-order f32 mismatch: actual={actual!r} expected={expected!r}")


def _replay_event_rows(lines: list[str], *,
                      expected_gate_keys: set[tuple[int, ...]] | None = None) -> dict[str, Any]:
    parsed = {tag: _parse(lines, tag, *widths) for tag, widths in EVENT_WIDTHS.items()}
    if any(not parsed[tag] for tag in EVENT_WIDTHS):
        raise ValueError("C-arm event stream is missing one of S10ZG/MASS/VOLUME/HEAT")
    expected_keys = expected_gate_keys or {
        (*context, i, k)
        for context in PROGB_CALL_CONTEXTS
        for i in (113, 115)
        for k in range(1, 40)
    }
    melt_gates = _unique(parsed["S10MELTGATE"], 7, "S10MELTGATE")
    phase_gates = _unique(parsed["S10PHASE"], 7, "S10PHASE")
    if set(melt_gates) != expected_keys or set(phase_gates) != expected_keys:
        raise ValueError("independent melt/phase gate census differs from fixed call×i×k schedule")
    stage1_expected: set[tuple[int, ...]] = set()
    stage2_expected: set[tuple[int, ...]] = set()
    stage3_expected: set[tuple[int, ...]] = set()
    for key in expected_keys:
        melt, phase = melt_gates[key], phase_gates[key]
        melt_flag, phase_flag = melt["ints"][7], phase["ints"][7]
        qg_gate, temp_gate, t0c = melt["reals"]
        supcol = phase["reals"][0]
        if melt_flag != int(temp_gate > t0c):
            raise ValueError(f"melt gate bit disagrees with source operand at {key}")
        if phase_flag != int(supcol < 0.0):
            raise ValueError(f"cold/warm gate bit disagrees with source operand at {key}")
        if melt_flag == 1 and qg_gate > 0.0:
            stage1_expected.add((*key, 1))
        if phase_flag == 1:
            stage2_expected.add((*key, 2))
        else:
            stage3_expected.add((*key, 3))
    zgs = parsed["S10ZG"]
    mass_rows = _unique(parsed["S10MASS"], 8, "S10MASS")
    volume_rows = _unique(parsed["S10VOLUME"], 8, "S10VOLUME")
    heat_rows = _unique(parsed["S10HEAT"], 8, "S10HEAT")

    guard_by_key: dict[tuple[int, ...], dict[int, dict[str, Any]]] = {}
    action_counts: Counter[str] = Counter()
    for row in zgs:
        ints, values = row["ints"], row["reals"]
        call_key = ints[:7]
        consumer, action = ints[7:9]
        if consumer not in GUARD_CONSUMER_STAGE:
            raise ValueError(f"unknown C-arm rhox consumer {consumer}")
        stage = GUARD_CONSUMER_STAGE[consumer]
        if stage not in (1, 2, 3):
            raise ValueError(f"invalid stage for consumer {consumer}")
        qg, rate, rhox = values
        expected_action, expected_contribution = guarded_rate_over_density(qg, rate, rhox)
        if action != expected_action:
            raise ValueError(f"S10ZG guard action mismatch at {call_key}/{consumer}")
        if action == 0 and (qg != 0.0 or rate != 0.0 or expected_contribution != 0.0):
            raise ValueError(f"S10ZG bypass suppressed a nonzero process at {call_key}/{consumer}")
        if action == 1 and rhox <= 0.0:
            raise ValueError(f"S10ZG executed an invalid density division at {call_key}/{consumer}")
        key = (*call_key, stage)
        sites = guard_by_key.setdefault(key, {})
        if consumer in sites:
            raise ValueError(f"duplicate S10ZG consumer {consumer} at {call_key}")
        sites[consumer] = row
        action_counts[str(action)] += 1

    if set(mass_rows) != set(volume_rows) or set(mass_rows) != set(heat_rows):
        raise ValueError("S10MASS/S10VOLUME/S10HEAT selected call-stage keys differ")
    if set(mass_rows) != set(guard_by_key):
        raise ValueError("C guard and budget call-stage key universes differ")
    expected_budget_keys = stage1_expected | stage2_expected | stage3_expected
    if set(mass_rows) != expected_budget_keys:
        raise ValueError("budget key universe differs from independent source branch gates")

    for key, mass_row in mass_rows.items():
        _, _, _, _, _, _, _, stage = key
        m = mass_row["reals"]
        v = volume_rows[key]["reals"]
        h = heat_rows[key]["reals"]
        guards = guard_by_key[key]
        if stage == 1:
            if set(guards) != {1418} or len(m) != 5 or len(v) != 6 or len(h) != 7:
                raise ValueError(f"stage-1 event schema/census error at {key}")
            qg_before, pgmlt, qg_after, qr_before, qr_after = m
            _eq32(qg_after, qg_mass_stage1(qg_before, pgmlt), f"stage-1 qg at {key}")
            _eq32(qr_after, f32(qr_before - pgmlt), f"stage-1 qr at {key}")
            z = guards[1418]["reals"]
            qg_use, rate, rho = z
            _eq32(qg_use, qg_after, f"stage-1 guarded qg at {key}")
            _eq32(rate, pgmlt, f"stage-1 guarded rate at {key}")
            guard_event = next(row for row in zgs if row["ints"][:7] == key[:7]
                               and row["ints"][7] == 1418)
            _eq32(rho, guard_event["reals"][2], f"stage-1 guard rhox at {key}")
            qgv, pgv, rhov, vol, brs_before, brs_after = v
            _, expected_quotient = guarded_rate_over_density(qg_use, rate, rho)
            for a, e, label in ((qgv, qg_after, "qg"), (pgv, pgmlt, "rate"),
                                (rhov, rho, "rhox"),
                                (vol, expected_quotient, "quotient")):
                _eq32(a, e, f"stage-1 volume {label} at {key}")
            _eq32(brs_after, brs_volume_stage1(brs_before, expected_quotient),
                  f"stage-1 brs at {key}")
            qgh, pgheat, qg_heat_after, xlf, cpm, temp_before, temp_after = h
            _eq32(qgh, qg_before, f"stage-1 heat qg before at {key}")
            _eq32(pgheat, pgmlt, f"stage-1 latent rate at {key}")
            _eq32(qg_heat_after, qg_after, f"stage-1 heat qg after at {key}")
            _eq32(temp_after, heat_stage1(temp_before, xlf=xlf, cpm=cpm, pgmlt=pgmlt),
                  f"stage-1 heat store at {key}")
        elif stage == 2:
            if set(guards) != {2824} or len(m) != 15 or len(v) != 14 or len(h) != 22:
                raise ValueError(f"stage-2 event schema/census error at {key}")
            (qg_before, pgdep, pgaut, piacr, delta3, praci, psacr, delta2,
             pracs, pgaci, paacw, pgacr, pgacs, dtcld, qg_after) = m
            expected_qg = qg_mass_stage2(
                qg_before, pgdep=pgdep, pgaut=pgaut, piacr=piacr, delta3=delta3,
                praci=praci, psacr=psacr, delta2=delta2, pracs=pracs,
                pgaci=pgaci, paacw=paacw, pgacr=pgacr, pgacs=pgacs, dtcld=dtcld)
            _eq32(qg_after, expected_qg, f"stage-2 qg source order at {key}")
            (qg_use, brs_before, pgdep_v, rho, quotient, biacr, braci, bsacr,
             bracs, bgaci, baacw, bgacr, vol_dt, brs_after) = v
            guard_event = next(row for row in zgs if row["ints"][:7] == key[:7]
                               and row["ints"][7] == 2824)
            zg_qg, zg_rate, zg_rhox = guard_event["reals"]
            _eq32(zg_qg, qg_after, f"stage-2 ZG qg operand at {key}")
            _eq32(zg_rate, pgdep, f"stage-2 ZG rate operand at {key}")
            _eq32(zg_rhox, rho, f"stage-2 ZG rhox at {key}")
            _, expected_quotient = guarded_rate_over_density(zg_qg, zg_rate, zg_rhox)
            for a, e, label in ((qg_use, qg_after, "qg"), (pgdep_v, pgdep, "rate"),
                                (rho, zg_rhox, "rhox"),
                                (quotient, expected_quotient, "quotient")):
                _eq32(a, e, f"stage-2 volume {label} at {key}")
            _eq32(vol_dt, dtcld, f"stage-2 volume dt at {key}")
            _eq32(brs_after, brs_volume_stage2(
                brs_before, pgdep_volume=quotient,
                other_rates=(biacr, braci, bsacr, bracs, bgaci, baacw, bgacr),
                dtcld=dtcld), f"stage-2 brs source order at {key}")
            (psdep, heat_pgdep, pidep, pinud, prevp, heat_piacr, heat_paacw,
             pmulcs, pmulcg, pmulrs, pmulrg, piacw, heat_pgacr, psacr_h,
             xls, xl, xlf, xlwork, heat_dt, cpm, temp_before, temp_after) = h
            _eq32(heat_pgdep, pgdep, f"stage-2 heat pgdep at {key}")
            _eq32(heat_piacr, piacr, f"stage-2 heat piacr at {key}")
            _eq32(heat_paacw, paacw, f"stage-2 heat paacw at {key}")
            _eq32(heat_pgacr, pgacr, f"stage-2 heat pgacr at {key}")
            _eq32(heat_dt, dtcld, f"stage-2 heat dt at {key}")
            expected_xlwork = xlwork2_stage2(
                xls=xls, xl=xl, xlf=xlf, psdep=psdep, pgdep=pgdep,
                pidep=pidep, pinud=pinud, prevp=prevp, piacr=piacr,
                paacw=paacw, pmulcs=pmulcs, pmulcg=pmulcg,
                pmulrs=pmulrs, pmulrg=pmulrg, piacw=piacw,
                pgacr=pgacr, psacr=psacr_h)
            _eq32(xlwork, expected_xlwork, f"stage-2 xlwork2 at {key}")
            _eq32(temp_after, heat_stage2(temp_before, xlwork2=xlwork,
                                          cpm=cpm, dtcld=dtcld),
                  f"stage-2 heat store at {key}")
        else:
            if set(guards) != {2915, 2916} or len(m) != 6 or len(v) != 11 or len(h) != 12:
                raise ValueError(f"stage-3 event schema/census error at {key}")
            qg_before, pgacs, pgevp, pgeml, dtcld, qg_after = m
            _eq32(qg_after, qg_mass_stage3(qg_before, pgacs=pgacs,
                                           pgevp=pgevp, pgeml=pgeml,
                                           dtcld=dtcld), f"stage-3 qg at {key}")
            (qg_use, qg_after_volume, pgevp_v, rho_e, bgevp,
             pgeml_v, rho_m, bgeml, vol_dt, brs_before, brs_after) = v
            event_e = next(row for row in zgs if row["ints"][:7] == key[:7]
                           and row["ints"][7] == 2915)
            event_m = next(row for row in zgs if row["ints"][:7] == key[:7]
                           and row["ints"][7] == 2916)
            for event, rate, consumer in ((event_e, pgevp, 2915), (event_m, pgeml, 2916)):
                _eq32(event["reals"][0], qg_before, f"stage-3 ZG {consumer} qg at {key}")
                _eq32(event["reals"][1], rate, f"stage-3 ZG {consumer} rate at {key}")
            z_e = (event_e["reals"][0], event_e["reals"][1], event_e["reals"][2],
                   guarded_rate_over_density(*event_e["reals"])[1])
            z_m = (event_m["reals"][0], event_m["reals"][1], event_m["reals"][2],
                   guarded_rate_over_density(*event_m["reals"])[1])
            for a, e, label in ((qg_use, qg_before, "qg before divisions"),
                                (qg_after_volume, qg_after, "qg after mass update"),
                                (pgevp_v, pgevp, "pgevp"),
                                (rho_e, z_e[2], "pgevp rhox"), (bgevp, z_e[3], "bgevp"),
                                (pgeml_v, pgeml, "pgeml"), (rho_m, z_m[2], "pgeml rhox"),
                                (bgeml, z_m[3], "bgeml"), (vol_dt, dtcld, "dt")):
                _eq32(a, e, f"stage-3 volume {label} at {key}")
            _eq32(brs_after, brs_volume_stage3(brs_before, bgevp=bgevp,
                                               bgeml=bgeml, dtcld=dtcld),
                  f"stage-3 brs at {key}")
            prevp, psevp, heat_pgevp, pseml, heat_pgeml, xl, xlf, xlwork, heat_dt, cpm, temp_before, temp_after = h
            _eq32(heat_pgevp, pgevp, f"stage-3 heat pgevp at {key}")
            _eq32(heat_pgeml, pgeml, f"stage-3 heat pgeml at {key}")
            _eq32(heat_dt, dtcld, f"stage-3 heat dt at {key}")
            expected_xlwork = xlwork2_stage3(xl=xl, xlf=xlf, prevp=prevp,
                psevp=psevp, pgevp=pgevp, pseml=pseml, pgeml=pgeml)
            _eq32(xlwork, expected_xlwork, f"stage-3 xlwork2 at {key}")
            _eq32(temp_after, heat_stage2(temp_before, xlwork2=xlwork,
                                          cpm=cpm, dtcld=dtcld),
                  f"stage-3 heat store at {key}")

    return {
        "schema": "s10-czeroqg-ledger-replay-v1",
        "policy_approved": False,
        "guard_action_counts": dict(action_counts),
        "guard_rows": len(zgs),
        "mass_volume_heat_call_stages": len(mass_rows),
        "source_ordered_f32_budgets_passed": True,
        "nonzero_rate_suppressed": False,
        "positive_trace_policy": "B midpoint, unapproved",
        "physical_policy": "OPEN",
    }


def replay_events(lines: list[str]) -> dict[str, Any]:
    """Production default uses the fixed S10 call context×column×level universe."""
    return _replay_event_rows(lines)
