"""Replay the applied RK3 QI face contribution at donor (2,168,33).

The packet records one donor's six faces and limiter decisions around the
actual Z→X→Y update. It locates the positive subnormal tendency, while leaving
the upstream flux stencil and a physical QI/NI correction open.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from harness.analyze_qi_donor_transient import read_trace as read_parent_donor


PACKET = Path(__file__).resolve().parent / "evidence/native_qi_face_producer_2026-10-30"
PARENT = Path(__file__).resolve().parent / "evidence/native_qi_donor_transient_2026-10-30"
QNC_PARENT = Path(__file__).resolve().parent / "evidence/native_qnc_live_guard_2026-10-30"
DONOR = (2, 33, 168)  # source and trace use (i,k,j)
OWNERS = ((2, 33, 168), (1, 33, 168), (3, 33, 168),
          (2, 33, 167), (2, 33, 169), (2, 32, 168), (2, 34, 168))
FACES = ("FX_WEST", "FX_EAST", "FY_SOUTH", "FY_NORTH", "FZ_BOTTOM", "FZ_TOP")
INPUT_FIELDS = ("FIELD", "FIELD_OLD", "C1H", "C2H", "MU_OLD", "MU_BASE",
                "MSFTX", "MSFTY", "RDX", "RDY", "RDZW", "DT", "EPS")
META_INT = ("HORZ_ORDER", "VERT_ORDER", "IDS", "IDE", "JDS", "JDE",
            "ITS", "ITE", "JTS", "JTE", "LIM_I_START", "LIM_I_END",
            "LIM_J_START", "LIM_J_END")
META_BOOL = ("DEGRADE_XS", "DEGRADE_XE", "DEGRADE_YS", "DEGRADE_YE", "TENDEC")
TEND_STAGES = ("TEND_START", "AFTER_Z", "AFTER_X", "AFTER_Y")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def f32(word: str) -> np.float32:
    return np.asarray([int(word, 16)], dtype=np.uint32).view(np.float32)[0]


def word(value: np.float32) -> str:
    return f"{int(np.float32(value).view(np.uint32)):08X}"


def fraction(raw: str) -> Fraction:
    return Fraction.from_float(float(f32(raw)))


def read_trace(path: Path) -> dict[tuple[str, int, int, int, str], tuple[str, str]]:
    lines = path.read_text(encoding="ascii").splitlines()
    if lines[:3] != [
        "# KDM6AD_QI_FACE_PRODUCER_V1",
        "# BASE_ADVECT_SHA256 2655e8e0f0e2d19db77fdee583f926ebd371c236c00dd1d580dd5283afed714b",
        "# VAL step rk stage i k j field dtype raw_word_hex",
    ]:
        raise ValueError("QI face trace header differs")
    rows = {}
    for line in lines[3:]:
        parts = line.split()
        if len(parts) != 10 or parts[0:3] != ["VAL", "3", "3"]:
            raise ValueError("QI face trace row/step differs")
        _, _, _, stage, i, k, j, field, dtype, raw = parts
        if (len(raw) != 8 or any(ch not in "0123456789ABCDEF" for ch in raw) or
                dtype not in ("f32", "i32", "bool")):
            raise ValueError("QI face trace raw word/type differs")
        if dtype == "f32" and not math.isfinite(float(f32(raw))):
            raise ValueError("QI face trace has nonfinite value")
        if dtype == "bool" and raw not in ("00000000", "00000001"):
            raise ValueError("QI face trace Boolean differs")
        key = (stage, int(i), int(k), int(j), field)
        if key in rows:
            raise ValueError("duplicate QI face trace record")
        rows[key] = (dtype, raw)
    expected = {}
    for stage in ("PRE", "LOW", "POST"):
        expected.update({(stage, *DONOR, field): "f32" for field in FACES})
    expected.update({("INPUT", *DONOR, field): "f32" for field in INPUT_FIELDS})
    expected.update({("META", *DONOR, field): "i32" for field in META_INT})
    expected.update({("META", *DONOR, field): "bool" for field in META_BOOL})
    for owner in OWNERS:
        expected[("OWNER", *owner, "SEEN")] = "bool"
        if owner != (1, 33, 168):
            for name, dtype in (("HIT", "bool"), ("SCALE", "f32"),
                                ("PH_LOW", "f32"), ("FLUX_OUT", "f32")):
                expected[("OWNER", *owner, name)] = dtype
    expected.update({(stage, *DONOR, "ADVECT_TEND"): "f32" for stage in TEND_STAGES})
    if len(expected) != 85 or {key: value[0] for key, value in rows.items()} != expected:
        raise ValueError("QI face trace stage/field/owner inventory differs")
    return rows


def _raw(rows: dict, stage: str, field: str, coord: tuple[int, int, int] = DONOR) -> str:
    return rows[(stage, *coord, field)][1]


def _replay_tendency(rows: dict) -> tuple[dict[str, str], Fraction]:
    def face(stage: str, name: str) -> np.float32:
        return f32(_raw(rows, stage, name))

    value = f32(_raw(rows, "TEND_START", "ADVECT_TEND"))
    if word(value) != "00000000":
        raise ValueError("QI RK3 tendency did not start at +0")
    with np.errstate(under="ignore"):
        for axis, upper, lower, metric in (
            ("Z", "FZ_TOP", "FZ_BOTTOM", "RDZW"),
            ("X", "FX_EAST", "FX_WEST", "RDX"),
            ("Y", "FY_NORTH", "FY_SOUTH", "RDY"),
        ):
            delta = np.float32(np.float32(np.float32(face("POST", upper) -
                                                   face("POST", lower)) +
                                       face("LOW", upper)) - face("LOW", lower))
            inner = np.float32(f32(_raw(rows, "INPUT", metric)) * delta)
            if axis == "Z":
                value = np.float32(value - inner)
            else:
                value = np.float32(value - np.float32(f32(_raw(rows, "INPUT", "MSFTX")) * inner))
            if word(value) != _raw(rows, f"AFTER_{axis}", "ADVECT_TEND"):
                raise ValueError(f"QI {axis} tendency does not replay from applied faces")
    z_exact = -fraction(_raw(rows, "INPUT", "RDZW")) * (
        fraction(_raw(rows, "POST", "FZ_TOP")) -
        fraction(_raw(rows, "POST", "FZ_BOTTOM")) +
        fraction(_raw(rows, "LOW", "FZ_TOP")) -
        fraction(_raw(rows, "LOW", "FZ_BOTTOM")))
    return {stage: _raw(rows, stage, "ADVECT_TEND") for stage in TEND_STAGES}, z_exact


def _verify_owners(rows: dict) -> None:
    i_start = int(_raw(rows, "META", "LIM_I_START"), 16)
    i_end = int(_raw(rows, "META", "LIM_I_END"), 16)
    j_start = int(_raw(rows, "META", "LIM_J_START"), 16)
    j_end = int(_raw(rows, "META", "LIM_J_END"), 16)
    if (i_start != 2 or i_end < 3 or j_start > 167 or j_end < 169 or
            _raw(rows, "META", "DEGRADE_XS") != "00000001" or
            _raw(rows, "META", "IDS") != "00000001" or
            _raw(rows, "META", "ITS") != "00000001"):
        raise ValueError("QI limiter bounds do not explain executed owners")
    if _raw(rows, "OWNER", "SEEN", (1, 33, 168)) != "00000000":
        raise ValueError("west boundary limiter owner unexpectedly executed")
    eps = f32(_raw(rows, "INPUT", "EPS"))
    for owner in OWNERS:
        if owner == (1, 33, 168):
            continue
        if _raw(rows, "OWNER", "SEEN", owner) != "00000001":
            raise ValueError(f"limiter owner omitted: {owner}")
        available = f32(_raw(rows, "OWNER", "PH_LOW", owner))
        flux_out = f32(_raw(rows, "OWNER", "FLUX_OUT", owner))
        hit = available < flux_out
        if _raw(rows, "OWNER", "HIT", owner) != ("00000001" if hit else "00000000"):
            raise ValueError(f"limiter branch disagrees with operands: {owner}")
        with np.errstate(under="ignore"):
            scale = (np.float32(max(np.float32(0), np.float32(available /
                      np.float32(flux_out + eps)))) if hit else np.float32(1))
        if word(scale) != _raw(rows, "OWNER", "SCALE", owner):
            raise ValueError(f"limiter scale disagrees with operands: {owner}")


def _verify_applied_faces(rows: dict) -> None:
    # A signed nonzero PRE word has one outgoing owner under the host's
    # direction tests. Zero, including -0, is not scaled by either cell.
    owner_by_face = (
        ("FX_WEST", (1, 33, 168), -1),
        ("FX_EAST", (3, 33, 168), +1),
        ("FY_SOUTH", (2, 33, 167), -1),
        ("FY_NORTH", (2, 33, 169), +1),
        ("FZ_BOTTOM", (2, 32, 168), +1),
        ("FZ_TOP", (2, 34, 168), -1),
    )
    for name, neighbor, donor_sign in owner_by_face:
        pre_word = _raw(rows, "PRE", name)
        pre = f32(pre_word)
        owner = None
        if pre != 0:
            owner = DONOR if (pre > 0) == (donor_sign > 0) else neighbor
        expected = pre_word
        if (owner is not None and
                _raw(rows, "OWNER", "SEEN", owner) == "00000001" and
                _raw(rows, "OWNER", "HIT", owner) == "00000001"):
            with np.errstate(under="ignore"):
                expected = word(np.float32(pre * f32(_raw(rows, "OWNER", "SCALE", owner))))
        if _raw(rows, "POST", name) != expected:
            raise ValueError(f"applied QI face differs from owner-scale result: {name}")


def analyze(packet: Path = PACKET) -> dict:
    execution = json.loads((packet / "execution_summary.json").read_text())
    parent_execution = json.loads((PARENT / "execution_summary.json").read_text())
    if (execution["parent_manifest_sha256"] != sha(PARENT / "manifest.json") or
            execution["parent_analysis_sha256"] != sha(PARENT / "analysis.json") or
            execution["base_executable_sha256"] != parent_execution["executable_sha256"] or
            execution["dso_sha256"] != parent_execution["dso_sha256"] or
            execution["changed_archive_members"] != ["module_advect_em.o", "solve_em.o"] or
            execution["host_steps_completed"] != 4 or execution["RTTOV_calls"] != 0):
        raise ValueError("QI face execution lineage differs")
    rows_by_case = {}
    for case in ("control", "alpha025"):
        run = execution["runs"][case]
        if (run["off"]["checkpoint_sha256"] != run["on"]["checkpoint_sha256"] or
                run["off"]["applied_ack_sha256"] != run["on"]["applied_ack_sha256"]):
            raise ValueError(f"QI face trace on/off changed checkpoint/ACK: {case}")
        for mode in ("off", "on"):
            if (run[mode]["checkpoint_sha256"] !=
                    parent_execution["runs"][case][mode]["checkpoint_sha256"] or
                    run[mode]["applied_ack_sha256"] !=
                    parent_execution["runs"][case][mode]["applied_ack_sha256"]):
                raise ValueError(f"QI face trace changed parent endpoint: {case}/{mode}")
        path = packet / "data" / case / "qi_face.tsv"
        if sha(path) != run["on"]["trace_sha256"]["qi_face"]:
            raise ValueError(f"QI face data/receipt hash differs: {case}")
        if run["on"]["trace_sha256"]["qi_donor"] != sha(PARENT / "data" / case / "qi_donor.tsv"):
            raise ValueError(f"QI donor parent trace changed: {case}")
        for name, fname in (("qnc_candidate_faces", "faces.tsv"), ("rk_writer", "rk_writer.tsv")):
            if run["on"]["trace_sha256"][name] != sha(QNC_PARENT / "data" / case / fname):
                raise ValueError(f"QNC parent trace changed: {case}/{name}")
        rows = read_trace(path)
        _verify_owners(rows)
        _verify_applied_faces(rows)
        stages, z_exact = _replay_tendency(rows)
        donor = read_parent_donor(PARENT / "data" / case / "qi_donor.tsv")
        if stages["AFTER_Y"] != donor[(3, "QI_RK_BEFORE", 2, "ADVECT_TEND")]:
            raise ValueError(f"QI face tendency does not reach RK input: {case}")
        if _raw(rows, "META", "TENDEC") != "00000000":
            raise ValueError("QI tendency split unexpectedly active")
        rows_by_case[case] = (rows, stages, z_exact)

    control, control_stages, control_exact = rows_by_case["control"]
    alpha, alpha_stages, alpha_exact = rows_by_case["alpha025"]
    for stage in ("PRE", "LOW", "INPUT", "META"):
        keys = [key for key in control if key[0] == stage]
        if any(control[key] != alpha[key] for key in keys):
            raise ValueError(f"QI donor {stage} differs before limiter")
    if (_raw(control, "PRE", "FZ_BOTTOM") != "80000060" or
            _raw(alpha, "PRE", "FZ_BOTTOM") != "80000060" or
            _raw(control, "LOW", "FZ_BOTTOM") != "80000000" or
            _raw(alpha, "LOW", "FZ_BOTTOM") != "80000000" or
            _raw(control, "POST", "FZ_BOTTOM") != "80000000" or
            _raw(alpha, "POST", "FZ_BOTTOM") != "80000060"):
        raise ValueError("QI bottom correction face branch differs")
    for name in FACES:
        if name != "FZ_BOTTOM" and _raw(control, "POST", name) != _raw(alpha, "POST", name):
            raise ValueError("additional QI post-limiter face changed")
    below = (2, 32, 168)
    if (_raw(control, "OWNER", "HIT", below) != "00000001" or
            _raw(alpha, "OWNER", "HIT", below) != "00000000" or
            _raw(control, "OWNER", "SCALE", below) != "22B0552B" or
            _raw(alpha, "OWNER", "SCALE", below) != "3F800000" or
            _raw(control, "OWNER", "PH_LOW", below) !=
            _raw(alpha, "OWNER", "PH_LOW", below)):
        raise ValueError("QI lower-neighbor limiter branch differs")
    with np.errstate(under="ignore"):
        predicted_control_face = np.float32(f32(_raw(control, "PRE", "FZ_BOTTOM")) *
                                            f32(_raw(control, "OWNER", "SCALE", below)))
    if word(predicted_control_face) != _raw(control, "POST", "FZ_BOTTOM"):
        raise ValueError("QI control lower face is not rounded owner scale product")
    if alpha_exact / Fraction(1, 2**149) != Fraction(17635905, 2048) or control_exact != 0:
        raise ValueError("QI exact vertical face contribution differs")
    if (control_stages != {"TEND_START": "00000000", "AFTER_Z": "00000000",
                           "AFTER_X": "00000000", "AFTER_Y": "00000000"} or
            alpha_stages != {"TEND_START": "00000000", "AFTER_Z": "000021A3",
                             "AFTER_X": "000021A3", "AFTER_Y": "000021A3"}):
        raise ValueError("QI directional tendency sequence differs")
    return {
        "schema": "kdm6.native_qi_face_producer.v1",
        "trace_records_per_case": 85,
        "host_steps_completed": 4,
        "trace_off_on_and_parent_checkpoints_equal": True,
        "same_PRE_LOW_and_donor_inputs": True,
        "changed_applied_face": {
            "face": "FZ_BOTTOM at donor (i,k,j)=(2,33,168)",
            "PRE_word_both": "80000060",
            "LOW_word_both": "80000000",
            "POST_control_word": "80000000",
            "POST_alpha025_word": "80000060",
        },
        "lower_owner_limiter": {
            "coord_ikj": [2, 32, 168],
            "control_HIT": True, "control_SCALE_word": "22B0552B",
            "alpha025_HIT": False, "alpha025_SCALE_word": "3F800000",
            "PH_LOW_word_both": _raw(control, "OWNER", "PH_LOW", below),
            "control_FLUX_OUT_word": _raw(control, "OWNER", "FLUX_OUT", below),
            "alpha025_FLUX_OUT_word": _raw(alpha, "OWNER", "FLUX_OUT", below),
            "west_boundary_owner_executed": False,
        },
        "directional_tendency": {"control": control_stages, "alpha025": alpha_stages},
        "alpha025_exact_Z_increment_in_subnormal_ULP": str(alpha_exact / Fraction(1, 2**149)),
        "alpha025_exact_Z_increment_in_subnormal_ULP_approximately": float(
            alpha_exact / Fraction(1, 2**149)),
        "limits": {
            "lower_owner_FLUX_OUT_six_face_decomposition_captured": False,
            "upstream_high_order_vertical_flux_stencil_captured": False,
            "physical_QI_NI_budget_certified": False,
            "whole_M0_supported": False,
            "whole_M0_RTTOV_cost_defined": False,
            "accepted_analysis": False,
        },
        "replay_model_calls": {"host": 0, "KDM6": 0, "RTTOV": 0, "optimizer": 0},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, default=PACKET)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise FileExistsError(args.output)
    result = analyze(args.packet)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": "QI_FACE_PRODUCER_ANALYZED",
                      "alpha_Z_word": result["directional_tendency"]["alpha025"]["AFTER_Z"]},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
