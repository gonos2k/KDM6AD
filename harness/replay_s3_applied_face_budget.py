#!/usr/bin/env python3
"""Replay a fixed five-cell QNCLOUD face counterfactual and its rounding ledger."""

import hashlib
import json
import math
import struct
from fractions import Fraction
from pathlib import Path

from replay_native_number import f32
from replay_negative_number_trace import fma32
from replay_number_face_flux import divergence_stores
from s3_face_budget_backoff import (
    Cell, SharedFace, _face_numerator_contribution, _operator_weight,
    _stored, _validate_topology,
)


EVIDENCE = Path(__file__).parent / "evidence/S3_QN_face_neighbors_run1/S3QN_face.stream"
COORDS = ((233, 124, 12), (232, 124, 12), (233, 123, 12),
          (233, 125, 12), (233, 124, 13))
NAMES = ("donor", "west", "south", "north", "upper")
PAIRS = (SharedFace(0, 0, 1, 1), SharedFace(0, 2, 2, 3),
         SharedFace(0, 3, 3, 2), SharedFace(0, 5, 4, 4))


def bits(value):
    return f"{struct.unpack('I', struct.pack('f', value))[0]:08X}"


def word(token):
    if len(token) != 8 or any(c not in "0123456789abcdefABCDEF" for c in token):
        raise ValueError("invalid binary32 word")
    value = struct.unpack("f", struct.pack("I", int(token, 16)))[0]
    if not math.isfinite(value):
        raise ValueError("nonfinite captured operand")
    return value


def numerator(cell, high):
    rk = cell.rk
    adv = divergence_stores(cell.initial_tendency, high, cell.low,
                            cell.rdzw, cell.msftx, cell.rdx, cell.rdy)[-1]
    tendency = f32(f32(adv * rk["msfty"]) + rk["sc_tend"])
    # S3QNRK logs the already-added MUOLD/MUNEW totals, including mu_base.
    old_weight = fma32(rk["c1"], rk["mu_old"], rk["c2"])
    new_weight = fma32(rk["c1"], rk["mu_new"], rk["c2"])
    return fma32(old_weight, rk["old"], f32(rk["dt"] * tendency)), new_weight


def replay(text):
    records = {}
    for line in text.splitlines():
        t = line.split()
        if not t or t[0] not in ("S3QNAX", "S3QNPD", "S3QNRK"):
            raise ValueError("unexpected capture record")
        widths = {"S3QNAX": 22, "S3QNPD": 35, "S3QNRK": 23}
        if len(t) != widths[t[0]]:
            raise ValueError("capture record width differs")
        identity = tuple(map(int, t[1:12]))
        if identity[:8] != (2, 3, 3, 1, 1, 235, 1, 142) or identity[8:] not in COORDS:
            raise ValueError("capture is outside the fixed event roster")
        axis = int(t[12]) if t[0] == "S3QNAX" else 0
        if t[0] == "S3QNAX" and (axis not in (1, 2, 3) or t[13] != "2"):
            raise ValueError("wrong axis or source branch")
        if t[0] == "S3QNPD" and t[12] not in ("0", "1"):
            raise ValueError("wrong limiter activation flag")
        start = 14 if axis else (13 if t[0] == "S3QNPD" else 12)
        values = tuple(map(word, t[start:]))
        key = (t[0], identity[8:], axis)
        if key in records:
            raise ValueError("duplicate capture record")
        records[key] = values
    expected = {(tag, coord, axis) for coord in COORDS
                for tag, axes in (("S3QNAX", (1, 2, 3)), ("S3QNPD", (0,)),
                                  ("S3QNRK", (0,))) for axis in axes}
    if records.keys() != expected:
        raise ValueError("incomplete capture event set")

    cells, before = [], []
    for coord in COORDS:
        x, y, z = (records["S3QNAX", coord, a] for a in (2, 1, 3))
        adv, my, source, tendency, old, dt, c1, c2, mo, mn, after = records["S3QNRK", coord, 0]
        if x[4] != y[4] or z[4] != 1.0:
            raise ValueError("axis metric differs from source contract")
        cell = Cell(tuple(v for a in (x, y, z) for v in a[:2]),
                    tuple(v for a in (x, y, z) for v in a[2:4]),
                    z[6], z[5], x[4], x[5], y[5],
                    dict(old=old, value=old, rk=3, mu_old=mo, mu_new=mn,
                         mu_base=0.0, c1=c1, c2=c2, advect_tend=adv,
                         msfty=my, sc_tend=source, dt=dt, i=coord[0], j=coord[1]))
        prefixes = divergence_stores(cell.initial_tendency, cell.high, cell.low,
                                     cell.rdzw, cell.msftx, cell.rdx, cell.rdy)
        if (tuple(map(bits, prefixes)) != tuple(bits(a[7]) for a in (z, x, y))
                or tuple(bits(a[6]) for a in (x, y)) != tuple(map(bits, prefixes[:2]))
                or bits(adv) != bits(prefixes[-1])
                or bits(tendency) != bits(f32(f32(adv * my) + source))
                or bits(_stored(cell, cell.high)) != bits(after)):
            raise ValueError("captured source-order baseline does not replay")
        cells.append(cell)
        before.append(after)
    _validate_topology(tuple(cells), PAIRS)

    # A prescribed local counterfactual, not a native run or an accepted repair.
    factor = 1.0 - 2.0**-24
    high = [list(c.high) for c in cells]
    paired = {p.donor_slot: p for p in PAIRS}
    for slot in (0, 1, 2, 3, 5):
        high[0][slot] = f32(cells[0].high[slot] * factor)
        if slot in paired:
            p = paired[slot]
            high[p.receiver][p.receiver_slot] = high[0][slot]
    after = [_stored(c, tuple(high[i])) for i, c in enumerate(cells)]
    internal = []
    for p in PAIRS:
        delta = high[0][p.donor_slot] - cells[0].high[p.donor_slot]
        left = _operator_weight(cells[0]) * _face_numerator_contribution(cells[0], p.donor_slot, delta)
        right = _operator_weight(cells[p.receiver]) * _face_numerator_contribution(cells[p.receiver], p.receiver_slot, delta)
        if left + right != 0:
            raise ValueError("internal operator exchange does not pair")
        internal.append(dict(donor_slot=p.donor_slot, receiver=NAMES[p.receiver],
                             donor=float(left), receiver_amount=float(right), residual=0.0))
    external = _operator_weight(cells[0]) * _face_numerator_contribution(
        cells[0], 1, high[0][1] - cells[0].high[1])
    rounded, stored = Fraction(0), Fraction(0)
    for i, cell in enumerate(cells):
        n0, denominator = numerator(cell, cell.high)
        n1, _ = numerator(cell, tuple(high[i]))
        weight = _operator_weight(cell)
        rounded += weight * (Fraction(n1) - Fraction(n0))
        stored += weight * Fraction(denominator) * (Fraction(after[i]) - Fraction(before[i]))
    return dict(scope="fixed_capture_counterfactual", native_candidate_executed=False,
                physical_number_basis_resolved=False, operational_fix_applied=False,
                capture_sha256=hashlib.sha256(text.encode()).hexdigest(), factor_bits=bits(factor),
                cells=[dict(name=name, before=before[i], after=after[i],
                            before_bits=bits(before[i]), after_bits=bits(after[i])) for i, name in enumerate(NAMES)],
                internal_faces=internal, external_xR=float(external),
                rounded_numerator_change=float(rounded), stored_inventory_change=float(stored),
                change_in_divergence_and_RK_rounding=float(rounded - external),
                division_store_rounding=float(stored - rounded),
                all_selected_states_nonnegative=all(v >= 0 for v in after))


if __name__ == "__main__":
    print(json.dumps(replay(EVIDENCE.read_text()), indent=2))
