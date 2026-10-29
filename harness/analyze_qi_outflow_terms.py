"""Decompose the stored RK3 QI lower-owner FLUX_OUT into its six faces.

All exact quantities interpret saved f32 words as rationals. They are a
numerical diagnostic, not a physical ice-mass budget or a compiled-operation
trace. The original FLUX_OUT word and each pre-limiter face are kept distinct.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import itertools
import json
import math
from pathlib import Path
import struct

import numpy as np

from harness.analyze_qi_face_producer import read_trace as read_parent_face
from harness.g33_s15_probe import fma32


PACKET = Path(__file__).resolve().parent / "evidence/native_qi_outflow_terms_2026-10-30"
PARENT = Path(__file__).resolve().parent / "evidence/native_qi_face_producer_2026-10-30"
OWNER = (2, 32, 168)  # source and TSV use (i,k,j)
FACES = ("FX_WEST", "FX_EAST", "FY_SOUTH", "FY_NORTH", "FZ_BOTTOM", "FZ_TOP")
INPUTS = ("DT", "MSFTX", "MSFTY", "RDX", "RDY", "RDZW", "FIELD_OLD",
          "C1", "C2", "MU_OLD", "MUB", "PH_LOW", "FLUX_OUT")
META = ("VERT_ORDER", "HORZ_ORDER", "KTS", "KTF", "I_START", "I_END",
        "J_START", "J_END")
VERT = ("ROM", "RDZW", "RDZW_PREV", "C1", "C2", "MUT", "FIELD_M2",
        "FIELD_M1", "FIELD_P0", "FIELD_P1", "OLD_M1", "OLD_P0")


def f32(raw: str) -> float:
    return struct.unpack(">f", bytes.fromhex(raw))[0]


def fraction(raw: str) -> Fraction:
    return Fraction.from_float(f32(raw))


def word(value: np.float32) -> str:
    return f"{int(np.float32(value).view(np.uint32)):08X}"


def read_trace(path: Path) -> dict[tuple[str, int, int, int, str], tuple[str, str]]:
    lines = path.read_text(encoding="ascii").splitlines()
    if lines[:3] != [
        "# KDM6AD_QI_OUTFLOW_TERMS_V1",
        "# BASE_ADVECT_SHA256 cb8882c7e7dd3646ed1b2793b6735b9326580dbd06c7652930d5da40e274c898",
        "# VAL step rk stage i k j field dtype raw_word_hex",
    ]:
        raise ValueError("QI outflow trace header differs")
    expected = {(stage, *OWNER, field): "f32"
                for stage in ("PRE", "LOW", "VISIT") for field in FACES}
    expected.update({("INPUT", *OWNER, field): "f32" for field in INPUTS})
    expected.update({("META", *OWNER, field): "i32" for field in META})
    expected.update({("VERT", 2, level, 168, field): "f32"
                     for level in (32, 33) for field in VERT})
    rows: dict[tuple[str, int, int, int, str], tuple[str, str]] = {}
    for line in lines[3:]:
        parts = line.split()
        if len(parts) != 10 or parts[:3] != ["VAL", "3", "3"]:
            raise ValueError("QI outflow trace row/step differs")
        _, _, _, stage, i, k, j, field, dtype, raw = parts
        if len(raw) != 8 or any(ch not in "0123456789ABCDEF" for ch in raw):
            raise ValueError("QI outflow raw word differs")
        if dtype == "f32" and not math.isfinite(f32(raw)):
            raise ValueError("QI outflow f32 is nonfinite")
        key = (stage, int(i), int(k), int(j), field)
        if key in rows:
            raise ValueError("duplicate QI outflow record")
        rows[key] = dtype, raw
    if {key: value[0] for key, value in rows.items()} != expected:
        raise ValueError("QI outflow record inventory differs")
    return rows


def raw(rows: dict, stage: str, field: str, coord: tuple[int, int, int] = OWNER) -> str:
    return rows[(stage, *coord, field)][1]


def exact_terms(rows: dict) -> dict[str, Fraction]:
    face = {name: fraction(raw(rows, "PRE", name)) for name in FACES}
    dt = fraction(raw(rows, "INPUT", "DT"))
    mx = fraction(raw(rows, "INPUT", "MSFTX"))
    my = fraction(raw(rows, "INPUT", "MSFTY"))
    rdx = fraction(raw(rows, "INPUT", "RDX"))
    rdy = fraction(raw(rows, "INPUT", "RDY"))
    rdzw = fraction(raw(rows, "INPUT", "RDZW"))
    zero = Fraction(0)
    return {
        "FX_WEST": dt * mx * my * rdx * -min(zero, face["FX_WEST"]),
        "FX_EAST": dt * mx * my * rdx * max(zero, face["FX_EAST"]),
        "FY_SOUTH": dt * mx * my * rdy * -min(zero, face["FY_SOUTH"]),
        "FY_NORTH": dt * mx * my * rdy * max(zero, face["FY_NORTH"]),
        "FZ_BOTTOM": dt * my * rdzw * -max(zero, face["FZ_BOTTOM"]),
        "FZ_TOP": dt * my * rdzw * min(zero, face["FZ_TOP"]),
    }


def separate_f32_outflow(rows: dict) -> str:
    """A source-grouped, separate-operation candidate; not compiler identity."""
    def f(name: str) -> np.float32:
        return np.float32(f32(raw(rows, "PRE", name)))

    def inp(name: str) -> np.float32:
        return np.float32(f32(raw(rows, "INPUT", name)))

    z = np.float32(0)
    with np.errstate(under="ignore", invalid="raise", over="raise"):
        x = np.float32(np.maximum(z, f("FX_EAST")) - np.minimum(z, f("FX_WEST")))
        y = np.float32(np.maximum(z, f("FY_NORTH")) - np.minimum(z, f("FY_SOUTH")))
        v = np.float32(np.minimum(z, f("FZ_TOP")) - np.maximum(z, f("FZ_BOTTOM")))
        xy = np.float32(np.float32(inp("RDX") * x) + np.float32(inp("RDY") * y))
        horizontal = np.float32(np.float32(inp("MSFTX") * inp("MSFTY")) * xy)
        vertical = np.float32(np.float32(inp("MSFTY") * inp("RDZW")) * v)
        result = np.float32(inp("DT") * np.float32(horizontal + vertical))
    return word(result)


def separate_f32_available(rows: dict) -> str:
    """Replay the source-grouped low-order availability from saved operands."""
    def f(name: str) -> np.float32:
        return np.float32(f32(raw(rows, "LOW", name)))

    def inp(name: str) -> np.float32:
        return np.float32(f32(raw(rows, "INPUT", name)))

    with np.errstate(under="ignore", invalid="raise", over="raise"):
        mass = np.float32(np.float32(np.float32(inp("C1") * inp("MUB")) + inp("C2")) +
                          np.float32(inp("C1") * inp("MU_OLD")))
        x = np.float32(inp("RDX") * np.float32(f("FX_EAST") - f("FX_WEST")))
        y = np.float32(inp("RDY") * np.float32(f("FY_NORTH") - f("FY_SOUTH")))
        z = np.float32(np.float32(inp("MSFTY") * inp("RDZW")) *
                       np.float32(f("FZ_TOP") - f("FZ_BOTTOM")))
        horizontal = np.float32(np.float32(inp("MSFTX") * inp("MSFTY")) *
                                np.float32(x + y))
        result = np.float32(np.float32(mass * inp("FIELD_OLD")) -
                            np.float32(inp("DT") * np.float32(horizontal + z)))
    return word(result)


def vertical_source_compatible(rows: dict, level: int, face: str) -> dict:
    """Check saved vertical PRE/LOW against bounded separate/FMA candidates.

    Enumerate both possible SIGN(1,time_step) values because the integer
    argument was not recorded. The positive saved ROM gives SIGN(1.,-vel)=-1.
    Matching candidates do not identify compiled instructions.
    """
    def get(field: str) -> np.float32:
        return np.float32(f32(raw(rows, "VERT", field, (2, level, 168))))

    def rnd(value: float) -> float:
        return float(np.float32(value))

    q2, q1, q0, qp = (float(get(field)) for field in
                       ("FIELD_M2", "FIELD_M1", "FIELD_P0", "FIELD_P1"))
    vel = float(get("ROM"))
    if vel <= 0:
        raise ValueError("QI vertical producer velocity sign differs")
    c7, c1 = rnd(7 / 12), rnd(1 / 12)
    dz = np.float32(np.float32(2) / np.float32(get("RDZW") + get("RDZW_PREV")))
    mass = np.float32(get("C1") * get("MUT") + get("C2"))
    mu = np.float32(np.float32(0.5) * np.float32(mass + mass))
    dt = np.float32(f32(raw(rows, "INPUT", "DT")))
    with np.errstate(under="ignore"):
        cr = np.float32(np.float32(np.float32(get("ROM") * dt) / dz) / mu)
        up = np.float32(
            np.float32(np.float32(np.float32(0.5) *
                                  np.minimum(np.float32(1), np.float32(cr + abs(cr)))) *
                       get("OLD_M1")) +
            np.float32(np.float32(np.float32(0.5) *
                                  np.maximum(np.float32(-1), np.float32(cr - abs(cr)))) *
                       get("OLD_P0")))
        low = np.float32(np.float32(mu * np.float32(dz / dt)) * up)
    if word(low) != raw(rows, "LOW", face):
        raise ValueError(f"QI vertical low-order face does not replay: k={level}")
    matching = []
    for time_sign, f4_fma, slope_fma, combine_fma in itertools.product(
            (-1, 1), (False, True), (False, True), (False, True)):
        q01, qp2 = rnd(q0 + q1), rnd(qp + q2)
        first = rnd(c7 * q01)
        flux4 = (fma32(-c1, qp2, first) if f4_fma else
                 rnd(first - rnd(c1 * qp2)))
        diff1, diff2 = rnd(qp - q2), rnd(q0 - q1)
        slope = (fma32(-3.0, diff2, diff1) if slope_fma else
                 rnd(diff1 - rnd(3.0 * diff2)))
        signed_c1 = rnd(-time_sign * c1)
        flux3 = (fma32(signed_c1, slope, flux4) if combine_fma else
                 rnd(flux4 + rnd(signed_c1 * slope)))
        with np.errstate(under="ignore"):
            post = np.float32(np.float32(vel * flux3) - low)
        if word(post) == raw(rows, "PRE", face):
            matching.append({"time_step_sign": time_sign,
                             "flux4_fma": f4_fma, "slope_fma": slope_fma,
                             "flux3_combine_fma": combine_fma})
    if not matching:
        raise ValueError(f"QI vertical high-order face has no compatible mode: k={level}")
    return {"low_order_word": word(low), "matching_mode_count": len(matching),
            "matching_modes": matching}


def analyze_case(rows: dict, parent: dict) -> dict:
    if (int(raw(rows, "META", "VERT_ORDER"), 16) != 3 or
            int(raw(rows, "META", "KTS"), 16) + 2 > 32 or
            int(raw(rows, "META", "KTF"), 16) - 1 < 33 or
            not (int(raw(rows, "META", "I_START"), 16) <= 2 <= int(raw(rows, "META", "I_END"), 16)) or
            not (int(raw(rows, "META", "J_START"), 16) <= 168 <= int(raw(rows, "META", "J_END"), 16))):
        raise ValueError("QI owner or vertical producer was outside recorded loops")
    for field, parent_name in (("PH_LOW", "PH_LOW"), ("FLUX_OUT", "FLUX_OUT")):
        if raw(rows, "INPUT", field) != parent[("OWNER", *OWNER, parent_name)][1]:
            raise ValueError(f"QI owner {field} differs from parent trace")
    for field in ("DT", "MSFTX", "MSFTY", "RDX", "RDY"):
        if raw(rows, "INPUT", field) != parent[("INPUT", 2, 33, 168, field)][1]:
            raise ValueError(f"QI outflow {field} differs from donor trace")
    for vertical_field, donor_field in (("FIELD_P0", "FIELD"),
                                        ("OLD_P0", "FIELD_OLD"),
                                        ("C1", "C1H"), ("C2", "C2H")):
        if raw(rows, "VERT", vertical_field, (2, 33, 168)) != parent[
                ("INPUT", 2, 33, 168, donor_field)][1]:
            raise ValueError(f"QI k33 {vertical_field} differs from donor input")
    for field in ("VERT_ORDER", "HORZ_ORDER"):
        if raw(rows, "META", field) != parent[("META", 2, 33, 168, field)][1]:
            raise ValueError(f"QI outflow {field} differs from donor trace")
    for field, parent_field in (("I_START", "LIM_I_START"), ("I_END", "LIM_I_END"),
                                ("J_START", "LIM_J_START"), ("J_END", "LIM_J_END")):
        if raw(rows, "META", field) != parent[("META", 2, 33, 168, parent_field)][1]:
            raise ValueError(f"QI outflow {field} differs from limiter bounds")
    if raw(rows, "PRE", "FZ_TOP") != parent[("PRE", 2, 33, 168, "FZ_BOTTOM")][1]:
        raise ValueError("shared QI top face differs from donor bottom face")
    if raw(rows, "LOW", "FZ_TOP") != parent[("LOW", 2, 33, 168, "FZ_BOTTOM")][1]:
        raise ValueError("shared low-order vertical face differs from donor")
    overlaps = (
        ("INPUT", "RDZW", 32, "VERT", "RDZW", 32),
        ("INPUT", "C1", 32, "VERT", "C1", 32),
        ("INPUT", "C2", 32, "VERT", "C2", 32),
        ("INPUT", "FIELD_OLD", 32, "VERT", "OLD_P0", 32),
        ("VERT", "RDZW", 32, "VERT", "RDZW_PREV", 33),
        ("VERT", "FIELD_M1", 32, "VERT", "FIELD_M2", 33),
        ("VERT", "FIELD_P0", 32, "VERT", "FIELD_M1", 33),
        ("VERT", "FIELD_P1", 32, "VERT", "FIELD_P0", 33),
        ("VERT", "OLD_P0", 32, "VERT", "OLD_M1", 33),
        ("VERT", "MUT", 32, "VERT", "MUT", 33),
    )
    for left_stage, left_field, left_k, right_stage, right_field, right_k in overlaps:
        if raw(rows, left_stage, left_field, (2, left_k, 168)) != raw(
                rows, right_stage, right_field, (2, right_k, 168)):
            raise ValueError("QI outflow overlapping source inputs differ")
    available_candidate = separate_f32_available(rows)
    if available_candidate != raw(rows, "INPUT", "PH_LOW"):
        raise ValueError("saved QI PH_LOW differs from source-grouped f32 replay")
    terms = exact_terms(rows)
    total = sum(terms.values(), Fraction(0))
    stored = fraction(raw(rows, "INPUT", "FLUX_OUT"))
    candidate = separate_f32_outflow(rows)
    if candidate != raw(rows, "INPUT", "FLUX_OUT"):
        raise ValueError("saved QI FLUX_OUT differs from source-grouped f32 replay")
    return {
        "pre_faces": {name: raw(rows, "PRE", name) for name in FACES},
        "visit_faces": {name: raw(rows, "VISIT", name) for name in FACES},
        "low_faces": {name: raw(rows, "LOW", name) for name in FACES},
        "pre_visit_same_bits": all(raw(rows, "PRE", name) == raw(rows, "VISIT", name)
                                   for name in FACES),
        "exact_term_float": {name: float(value) for name, value in terms.items()},
        "exact_total_float": float(total),
        "recorded_FLUX_OUT_word": raw(rows, "INPUT", "FLUX_OUT"),
        "recorded_FLUX_OUT_float": float(stored),
        "saved_exact_minus_recorded_float": float(total - stored),
        "separate_f32_available_word": available_candidate,
        "separate_f32_candidate_word": candidate,
        "vertical_producer_inputs": {
            str(level): {name: raw(rows, "VERT", name, (2, level, 168)) for name in VERT}
            for level in (32, 33)
        },
        "vertical_source_compatible": {
            "32": vertical_source_compatible(rows, 32, "FZ_BOTTOM"),
            "33": vertical_source_compatible(rows, 33, "FZ_TOP"),
        },
    }


def analyze(packet: Path = PACKET) -> dict:
    cases = {}
    rows_by_case = {}
    for case in ("control", "alpha025"):
        rows = read_trace(packet / "data" / case / "qi_outflow.tsv")
        parent = read_parent_face(PARENT / "data" / case / "qi_face.tsv")
        rows_by_case[case] = rows
        cases[case] = analyze_case(rows, parent)
    control, alpha = rows_by_case["control"], rows_by_case["alpha025"]
    terms_c, terms_a = exact_terms(control), exact_terms(alpha)
    return {
        "schema": "kdm6.native_qi_outflow_terms.v1",
        "record_count_per_case": len(control),
        "owner_ikj": list(OWNER),
        "cases": cases,
        "changed_pre_faces": [name for name in FACES if raw(control, "PRE", name) != raw(alpha, "PRE", name)],
        "exact_term_delta_alpha_minus_control_float": {
            name: float(terms_a[name] - terms_c[name]) for name in FACES
        },
        "exact_total_delta_alpha_minus_control_float": float(sum(terms_a.values(), Fraction(0)) -
                                                               sum(terms_c.values(), Fraction(0))),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, default=PACKET)
    args = parser.parse_args()
    print(json.dumps(analyze(args.packet), indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
