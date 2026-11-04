#!/usr/bin/env python3
"""Pinned native QI applied-interface and active D1 same-call replay."""

from __future__ import annotations

import argparse
import csv
from fractions import Fraction
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
import struct


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
P39 = REPO / "harness/evidence/native_qnice_39_applied_2026-11-03"
PD1_QI = REPO / "harness/evidence/native_qnice_d1_qi_2026-11-03"
PD1_AD = REPO / "harness/evidence/native_qnice_d1_ad_2026-11-03"
P39_SOURCE_SHA = "83932565067bf6433aebc090974e9c21338c019403e6f4d3779c327b4ab12968"
PD1_QI_SOURCE_SHA = "e3bc6dc8c41bcf4e267d42908baee7c97c22b80e808c3e17d88f03a03e7ff81d"
PD1_AD_SOURCE_SHA = "3189153439220e8409345215fce00d2a145aee292f74224838d4602869e610ae"
CAPTURE = "raw/native_qnice_applied_23158_runtime2.csv"
ORDER_SHA = "e57358a01352be28ebc938105b986f1c8b0cf776153b249da230a3c55e1361f6"
PINS = {
    "raw/build_receipt.json": "0f7c611d84af9671b00c259249ed378da49d9bacd1329f31d34695d47f3ae1d0",
    CAPTURE: "a6dd4d18025b5d5b3223b1f382dbc0b7ec1c3b21cfb7c6f01a6892e529a40bec",
    "raw/off_live_session.json": "954e82f261a3b8fa066cc290ee282d96c24d0fc25ed4b2c0657a670f09da3971",
    "raw/off_run_result.json": "2a8f492f064936da73e33884ffd2d5edb74d2e10d25147b7c0051050bfef7f1a",
    "raw/on_live_session.json": "c314a074deea927fd2f046b742b02ca76044d69f371569cc930b2af94c7a56db",
    "raw/on_run_result.json": "db974cce9a820290f890aa939b086540e73909e872457573c81f2e3145a865e6",
    "executed_cpp/sedimentation_conservative.cpp": "3091bd0cd6ac267037e1feeaec3c6cf0c5fb17654ff6f16f06d920958b6c357d",
    "producer/qi_capture_block.txt": "dd8b6feefd1ca59522151f1f694c01ea1bc843360d65b4e88e233c0fd0fc58fd",
    "producer/run.py.txt": "b746dc04bb46a1e3b16a3422651e0f371645598c66cc1d88003c54cfe7a0b48c",
    "results.json": "a308abf09c52d871f67148530ef866a6c6963bd65fad94f0f3f2f14bb2817312",
}
QI_FIELDS = {
    "qi_before",
    "falk_stored_qi",
    "out_attempt_qi",
    "applied_out_qi",
    "applied_in_qi",
    "fall_qi_before",
    "qi_after",
    "fall_qi_after",
    "departure_cap_active_qi",
    "departure_tie_active_qi",
    "state_roundoff_residual_qi",
    "realized_delta_qi",
    "previous_actual_out_qi",
}
K = 39
SED = "ice_sedimentation_conservative_n1"


def need(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError(why)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def pinned(name: str) -> bytes:
    raw = (HERE / name).read_bytes()
    need(sha(raw) == PINS[name], "packet SHA-256: " + name)
    return raw


def module(path: Path, expected: str, name: str):
    need(sha(path.read_bytes()) == expected, "parent source SHA-256: " + name)
    spec = importlib.util.spec_from_file_location(name, path)
    need(spec is not None and spec.loader is not None, "parent import: " + name)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def f64(raw_hex: str) -> float:
    out = struct.unpack("<d", int(raw_hex, 16).to_bytes(8, "little"))[0]
    need(math.isfinite(out), "nonfinite captured f64")
    return out


def word(value: float) -> str:
    return format(int.from_bytes(struct.pack("<d", value), "little"), "x")


def load_capture(raw: bytes, p39, d1_qi, d1_ad) -> dict:
    need(len(raw) <= 2 << 20 and raw.endswith(b"\n"), "native capture bound/newline")
    lines = raw.decode("ascii").splitlines()
    need(
        len(lines) == 4489
        and lines[0] == p39.NATIVE_HEADER
        and lines[1] == p39.NATIVE_META[0]
        and lines[2]
        == "# selected_runtime_call=2; first_one_step_call=2; selected_B_zero=27945; K=39; max_rows=7000; max_bytes=2097152"
        and lines[-1] == "# native_rows=4485,status=complete",
        "native capture header/footer",
    )
    reader = csv.DictReader(io.StringIO("\n".join([lines[0], *lines[3:-1]])))
    need(reader.fieldnames == p39.NATIVE_HEADER.split(","), "native capture columns")
    fields = {}
    stages = []
    order = []
    expected = {
        stage: set(names)
        | set(d1_qi.ADDED.get(stage, ()))
        | (d1_ad.NEW_FIELDS if stage == "c3_pre_mf_d1" else set())
        | (QI_FIELDS if stage == SED else set())
        for stage, names in p39.STAGES.items()
    }
    for row in reader:
        need(
            set(row) == set(reader.fieldnames) and None not in row.values(),
            "native row shape",
        )
        need(
            (
                row["one_step_call"],
                row["runtime_call"],
                row["b_zero"],
                row["B"],
                row["K"],
            )
            == ("2", "2", "27945", "32248", "39"),
            "native call/tile identity",
        )
        try:
            k = int(row["k_zero"])
            bits = int(row["raw_hex"], 16)
        except ValueError as exc:
            raise ValueError("native index/raw word") from exc
        need(0 <= k < K and row["k_zero"] == str(k), "native level index")
        stage, name = row["stage"], row["field"]
        need(stage in expected and name in expected[stage], "native stage/field")
        need(row["substep"] == ("1" if stage == SED else "0"), "native substep")
        dtype = "bool" if (stage, name) in p39.BOOL_FIELDS else "f64"
        need(
            row["dtype"] == dtype
            and row["raw_hex"] == format(bits, "x")
            and bits < (2 if dtype == "bool" else 1 << 64),
            "native dtype/raw word",
        )
        if dtype == "f64":
            f64(row["raw_hex"])
        key = (stage, name, k)
        need(key not in fields, "native duplicate field")
        fields[key] = row
        if not stages or stages[-1] != stage:
            stages.append(stage)
        order.append(
            "|".join(
                row[c]
                for c in (
                    "one_step_call",
                    "runtime_call",
                    "substep",
                    "b_zero",
                    "k_zero",
                    "stage",
                    "field",
                    "dtype",
                )
            )
        )
    need(
        len(fields) == 4485 and stages == list(p39.STAGES), "native row/stage inventory"
    )
    need(
        sha(("\n".join(order) + "\n").encode()) == ORDER_SHA,
        "native row order signature",
    )
    for k in range(K):
        for stage, names in expected.items():
            need(
                {name for s, name, j in fields if s == stage and j == k} == names,
                "complete native 39-level inventory: " + stage,
            )
    return fields


def get(fields: dict, stage: str, name: str, k: int) -> float:
    return f64(fields[(stage, name, k)]["raw_hex"])


def equal(fields: dict, left: tuple, right: tuple) -> None:
    need(
        fields[left]["dtype"] == fields[right]["dtype"]
        and fields[left]["raw_hex"] == fields[right]["raw_hex"],
        "raw-bit handoff: " + str((left, right)),
    )


def check(fields: dict, stage: str, name: str, k: int, value: float, why: str) -> None:
    need(fields[(stage, name, k)]["raw_hex"] == word(value), why)


def provenance(p39, d1_ad) -> dict:
    parent_result = d1_ad.replay()
    need(
        parent_result["scientific_status"] == "INCONCLUSIVE",
        "verified D1 parent replay",
    )
    receipt = json.loads(pinned("raw/build_receipt.json"))
    need(
        receipt["schema"] == "kdm6.native_qi_applied_d1_active_cpp_build.v1",
        "build schema",
    )
    c = receipt["candidate"]
    need(
        c
        == {
            "native_ij_1based": [203, 149],
            "target_native_level_1based": 16,
            "donor_native_level_1based": 17,
            "B": 32248,
            "b_zero": 27945,
            "runtime_call": 2,
            "one_step_call": 2,
            "tile_bounds": [2, 233, 143, 281],
        },
        "candidate identity",
    )
    need(c["b_zero"] == (203 - 2) * 139 + (149 - 143), "native tile flattening")
    need(
        receipt["only_source_change_vs_parent"]
        == ["src/sedimentation_conservative.cpp"],
        "capture-only source scope",
    )
    old = (P39 / "executed_cpp/sedimentation_conservative.cpp").read_bytes()
    need(
        sha(old) == p39.PINS["executed_cpp/sedimentation_conservative.cpp"],
        "parent sedimentation source",
    )
    new = pinned("executed_cpp/sedimentation_conservative.cpp")
    block = pinned("producer/qi_capture_block.txt")
    need(
        new.count(block) == 1 and new.replace(block, b"", 1) == old,
        "selected QI capture-only source overlay",
    )
    need(
        sha(new) == receipt["source_sha256"]["sedimentation_conservative.cpp"],
        "executed sedimentation source hash",
    )
    d1_receipt = json.loads(d1_ad.pinned("raw/build_receipt.json"))
    for name in ("coordinator.cpp", "runtime.cpp", "melt_freeze.cpp"):
        need(
            receipt["source_sha256"][name] == d1_receipt["source_sha256"][name],
            "unchanged D1 C++ source: " + name,
        )
    need(
        receipt["parent_d1_dso_sha256"] == d1_receipt["new_dso_sha256"]
        and receipt["parent_executable_sha256"]
        == d1_receipt["executable_sha256"]
        == receipt["new_executable_sha256"],
        "build parent executable/DSO",
    )
    need("-ffp-contract=off" in receipt["cxx_flags"], "C++ FP contraction disabled")
    pinned("producer/run.py.txt")
    need(
        receipt["producer_runner_sha256"] == PINS["producer/run.py.txt"]
        and receipt["source_overlay_block_sha256"]
        == PINS["producer/qi_capture_block.txt"],
        "producer source pins",
    )
    for mode in ("off", "on"):
        run = json.loads(pinned(f"raw/{mode}_run_result.json"))
        session_raw = pinned(f"raw/{mode}_live_session.json")
        session = json.loads(session_raw)
        need(
            run["schema"] == "kdm6.native_qi_d1_active_run.v1" and run["mode"] == mode,
            "run schema/mode",
        )
        need(run["session_record_sha256"] == sha(session_raw), "run/session hash")
        need(
            run["source_sha256"] == receipt["source_sha256"]
            and all(
                run["object_sha256"][name] == receipt["object_sha256"][name]
                for name in run["object_sha256"]
            ),
            "source/object build pins",
        )
        need(
            run["executable_sha256"]
            == session["executable_sha256"]
            == receipt["new_executable_sha256"],
            "executed host binary",
        )
        need(
            run["dso_sha256"]
            == session["library_candidate_sha256"]
            == receipt["new_dso_sha256"],
            "executed DSO hash",
        )
        need(
            run["origin_sha256"]
            == "7a353f1fa4f6636864ac169c9ee8d16869d1f38c8e998762c19659404cbb9c8e"
            and run["startup_sha256"]
            == "0c4836a2a44531c98d38d3ded15cab5048679b1139f3e4fd96fb62eff84bfad3",
            "same native input",
        )
        need(
            run["endpoint_sha256"]
            == "225d2cabe8a466304c06ba1a04638b84c8456b8477326b6852c9217360440070",
            "off/on/prior full endpoint identity",
        )
        need(
            session["status"] == "complete"
            and session["execution"]["experiment_valid"] is True,
            "completed host run",
        )
        need(
            any(
                "/native_qi_d1_active_20261104/host_bundle/libtorch/install/lib/libkdm6_c.2.0.0.dylib"
                in line
                for line in session["loaded_library_lines"]
            ),
            "loaded isolated DSO",
        )
        if mode == "off":
            need(run["captures"] == {}, "capture-off inventory")
        else:
            need(
                run["captures"]
                == {"native_qnice_applied_23158_runtime2.csv": PINS[CAPTURE]},
                "capture-on inventory/hash",
            )
    return {
        "executable_sha256": receipt["new_executable_sha256"],
        "dso_sha256": receipt["new_dso_sha256"],
        "endpoint_sha256": "225d2cabe8a466304c06ba1a04638b84c8456b8477326b6852c9217360440070",
        "capture_sha256": PINS[CAPTURE],
    }


def sed_replay(fields: dict) -> dict:
    prev_out = 0.0
    prev_den = 0.0
    prev_dz = 0.0
    before = after = attributed = Fraction(0)
    interfaces = []
    out_levels = []
    capped = []
    for k in range(K):
        q = get(fields, SED, "qi_before", k)
        d, ds, dz, zs = (
            get(fields, SED, name, k)
            for name in ("dend", "dend_safe", "delz", "delz_safe")
        )
        work, mstep, gate, dt = (
            get(fields, SED, name, k) for name in ("work1_qi", "mstep", "gate", "dtcld")
        )
        need(
            d > 0
            and ds > 0
            and dz > 0
            and zs > 0
            and dt > 0
            and mstep >= 1
            and gate in (0.0, 1.0),
            "positive geometry/time and active gate domain",
        )
        falk = (((d * q) * work) / mstep) * gate
        attempt = (falk * dt) / ds
        out = min(attempt, q)
        incoming = 0.0 if k == 0 else (prev_out * (prev_den * prev_dz)) / (ds * zs)
        qnew = q - out if k == 0 else (q - out) + incoming
        fall = get(fields, SED, "fall_qi_before", k) + (out * ds) / dt
        for name, value in (
            ("falk_stored_qi", falk),
            ("out_attempt_qi", attempt),
            ("applied_out_qi", out),
            ("applied_in_qi", incoming),
            ("qi_after", qnew),
            ("fall_qi_after", fall),
            ("departure_cap_active_qi", float(attempt > q)),
            ("departure_tie_active_qi", float(attempt == q)),
            ("state_roundoff_residual_qi", 0.0),
            ("realized_delta_qi", qnew - q),
            ("previous_actual_out_qi", prev_out),
        ):
            check(fields, SED, name, k, value, "source-order QI sedimentation: " + name)
        equal(fields, (SED, "qi_after", k), ("runtime_post_sed_entry", "qi", k))
        equal(
            fields,
            ("runtime_post_sed_entry", "qi", k),
            ("c3_pre_mf_d1", "qi_before", k),
        )
        if k == 0:
            equal(fields, ("runtime_entry_post_clamp", "qi", k), (SED, "qi_before", k))
        else:
            equal(fields, ("runtime_entry_post_clamp", "qi", k), (SED, "qi_before", k))
        weight = Fraction.from_float(ds) * Fraction.from_float(zs)
        before += Fraction.from_float(q) * weight
        after += Fraction.from_float(qnew) * weight
        attributed += (
            Fraction.from_float(incoming) - Fraction.from_float(out)
        ) * weight
        if k > 0:
            upper = (
                Fraction.from_float(prev_out)
                * Fraction.from_float(prev_den)
                * Fraction.from_float(prev_dz)
            )
            lower = Fraction.from_float(incoming) * weight
            interfaces.append(float(lower - upper))
        if out != 0.0:
            out_levels.append(K - k)
        if attempt > q:
            capped.append(K - k)
        prev_out, prev_den, prev_dz = out, ds, dz
    return {
        "raw_bit_replayed_levels": K,
        "nonzero_actual_departure_native_levels": sorted(out_levels),
        "capped_departure_native_levels": sorted(capped),
        "mass_coordinate_before": float(before),
        "mass_coordinate_after": float(after),
        "mass_coordinate_change": float(after - before),
        "attributed_applied_change": float(attributed),
        "arithmetic_closure_residual": float((after - before) - attributed),
        "max_abs_interface_mass_difference": max(map(abs, interfaces), default=0.0),
        "bottom_actual_departure_mass": float(
            Fraction.from_float(prev_out)
            * Fraction.from_float(prev_den)
            * Fraction.from_float(prev_dz)
        ),
    }


def d1_replay(fields: dict) -> dict:
    stage = "c3_pre_mf_d1"
    snow = []
    graupel = []
    ice = []
    for k in range(K):
        equal(fields, ("runtime_entry_pre_clamp", "qv", k), (stage, "qv_before", k))
        q, n, qc, nc, t, qv = (
            get(fields, stage, name, k)
            for name in (
                "qi_before",
                "ni_before",
                "qc_before",
                "nc_before",
                "t_before",
                "qv_before",
            )
        )
        active = t > 273.15 and q > 0.0
        melt_q = q if active else 0.0
        melt_n = n if active else 0.0
        qsafe = max(qv, 1e-15)
        cpm = 1004.5 * (1.0 - qsafe) + qsafe * 1846.4
        cpm_safe = max(cpm, 1e-9)
        for name, value in (
            ("pimlt_qi", melt_q),
            ("pimlt_ni", melt_n),
            ("pre_cpm", cpm),
            ("cpm_safe", cpm_safe),
        ):
            check(fields, stage, name, k, value, "D1 producer: " + name)
        pin, pfrz, nin, nfrz = (
            get(fields, stage, name, k)
            for name in ("pinuc_qi", "pfrzdtc_qi", "ninuc", "nfrzdtc")
        )
        qc1 = qc - pin + melt_q
        qc2 = qc1 - pfrz
        qi1 = q + pin - melt_q
        qi2 = qi1 + pfrz
        nc1 = nc - nin + melt_n
        nc2 = nc1 - nfrz
        ni1 = n + nin - melt_n
        ni2 = ni1 + nfrz
        coef = 350000.0 / cpm_safe
        ps, pg = (
            get(fields, stage, name, k) for name in ("psmlt_capped", "pgmlt_capped")
        )
        td1 = ((t + coef * ps) + coef * pg) - coef * melt_q
        for name, value in (
            ("qc_after_store1", qc1),
            ("qc_after_store2", qc2),
            ("qi_after_store1", qi1),
            ("qi_after_store2", qi2),
            ("nc_after_store1", nc1),
            ("nc_after_store2", nc2),
            ("ni_after_store1", ni1),
            ("ni_after_store2", ni2),
            ("t_after_melt", td1),
            ("t_after_d1", td1),
        ):
            check(fields, stage, name, k, value, "D1 source-order state: " + name)
        if ps != 0:
            snow.append(K - k)
        if pg != 0:
            graupel.append(K - k)
        if melt_q != 0:
            ice.append(K - k)
    need(
        16 in snow and 16 in graupel and 16 in ice,
        "candidate must have active snow/graupel/ice D1 amounts",
    )
    top = K - 16
    return {
        "raw_bit_replayed_levels": K,
        "nonzero_snow_melt_native_levels": sorted(snow),
        "nonzero_graupel_melt_native_levels": sorted(graupel),
        "nonzero_ice_melt_native_levels": sorted(ice),
        "level16": {
            name: get(fields, stage, name, top)
            for name in (
                "t_before",
                "t_after_d1",
                "qi_before",
                "pimlt_qi",
                "psmlt_capped",
                "pgmlt_capped",
                "qc_before",
                "qc_after_store2",
                "cpm_safe",
                "ni_before",
            )
        },
    }


def replay(
    *, capture_override: bytes | None = None, capture_sha: str | None = None
) -> dict:
    p39 = module(P39 / "replay.py", P39_SOURCE_SHA, "p39_native_ni_parent")
    d1_qi = module(PD1_QI / "replay.py", PD1_QI_SOURCE_SHA, "d1_qi_parent")
    d1_ad = module(PD1_AD / "replay.py", PD1_AD_SOURCE_SHA, "d1_ad_parent")
    provenance_data = provenance(p39, d1_ad)
    raw = pinned(CAPTURE) if capture_override is None else capture_override
    if capture_override is not None:
        need(capture_sha is not None and sha(raw) == capture_sha, "override SHA-256")
    fields = load_capture(raw, p39, d1_qi, d1_ad)
    sed = sed_replay(fields)
    d1 = d1_replay(fields)
    k16, k17 = K - 16, K - 17
    need(
        fields[(SED, "applied_out_qi", k17)]["raw_hex"]
        == fields[(SED, "previous_actual_out_qi", k16)]["raw_hex"],
        "native17→16 actual QI departure handoff",
    )
    result = {
        "schema": "kdm6.native_qi_applied_d1_active_same_call.v1",
        "call": {
            "native_ij_1based": [203, 149],
            "runtime_call": 2,
            "one_step_call": 2,
            "b_zero": 27945,
            "B": 32248,
            "K": 39,
            "ice_substep": 1,
        },
        "capture_rows": len(fields),
        "runtime_to_d1_qv_raw_bit_matches": K,
        "source_and_run": provenance_data,
        "sedimentation": sed,
        "d1": d1,
        "native17_actual_out_qi": get(fields, SED, "applied_out_qi", k17),
        "native16_actual_in_qi": get(fields, SED, "applied_in_qi", k16),
        "native16_post_sed_qi": get(fields, SED, "qi_after", k16),
        "native16_D1_applied_snow_melt": get(
            fields, "c3_pre_mf_d1", "psmlt_capped", k16
        ),
        "native16_D1_applied_graupel_melt": get(
            fields, "c3_pre_mf_d1", "pgmlt_capped", k16
        ),
        "native16_D1_applied_ice_melt": get(fields, "c3_pre_mf_d1", "pimlt_qi", k16),
        "scientific_status": "INCONCLUSIVE",
        "physical_unit_status": "INCONCLUSIVE",
    }
    if capture_override is None:
        need(json.loads(pinned("results.json")) == result, "saved applied-QI/D1 result")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = replay()
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print("NATIVE_QI_APPLIED_D1_ACTIVE_REPLAY_PASSED")
        print(
            json.dumps(
                {
                    "schema": result["schema"],
                    "native16_actual_in_qi": result["native16_actual_in_qi"],
                    "scientific_status": result["scientific_status"],
                },
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
