#!/usr/bin/env python3
"""Pinned offline replay of one native 39-level QNICE applied capture."""

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
import re
import struct
import sys


STAGE = "ice_sedimentation_conservative_n1"
K = 39
PACKET = Path(__file__).resolve().parent
REPO = PACKET.parents[2]
PINS = {
    "raw/host_qnice_pre_call.csv": "4bc95ebe84551eb360b97975b71cc7af21429fff5143b28fbb808e29b702f5ca",
    "raw/native_qnice_applied_30339_runtime2.csv": "27b89eb5b38b88174f55188be7d724cd74df8e6577c034a044581c78b3dff3bf",
    "raw/off_run_result.json": "6f88fd042c11fa5951d8a59258833efcd7766293d86cea5b194512b4a9bde316",
    "raw/on_run_result.json": "7e140a84dd2bb18807830f6540011ac0655baa3666a8181ff00912c4ed7e8611",
    "raw/off_live_session.json": "f9de9620a3e7d164dbe37b8ec8498f8f987abe0a23b405e02cbad05770d82aac",
    "raw/on_live_session.json": "23e7859253a718fccd1c4c184feb5882cae81d540fba932fa480dd7a0db834bb",
    "raw/cpp_build_receipt.json": "c8aa9e5b2e7bd6634d1ab91dc131dd7b37f0e147d638de6201529c6130bd3cd4",
    "raw/cpp_attempt2_receipt.json": "047520449cc58654bb004c3e529ad986da5073d000c305cd917c941dd16ec951",
    "raw/cpp_attempt1_receipt.json": "d6c660f0bcfdb6bf3913c8498f8cb00af47b95e26673cecce7a6a54ec792a780",
    "raw/host_build_receipt.json": "62e807021aa842c30b49c3122d850542e948bda70e028c68665f9b425dbe029f",
    "raw/host_retry_receipt.json": "be85f2dee2d40ebd658c5088cb9302ffb37d630be9346769be957e7b57864aa4",
    "raw/initial_analysis.json": "39f351dd4d52d1fbfaf6a9636290c5fc8d7efab7006322dc0ad81ce85138d6b7",
    "raw/historical_c5_compare.txt": "9d585300e23994523dfaed180098e2a337725c60f873775dc754c6d05a22828a",
    "raw/historical_c5_compare_receipt.json": "70e27348d03db7daeb3b617eff42c490e3197c2b1fd9ef6e64c62d53a7aad33a",
    "producer/run_host.py.txt": "561f6c07d2ae65153eff7efc97ca593ac1057d44dda26379c18c2fa7c8c56607",
    "producer/verify_pair.py.txt": "9de8b427b087e113fefb74bbad71cdc7ce70badf6cd5c04886809f65f88acbd3",
    "producer/strict_bitwise_nc.py.txt": "e073e1a7146b28498eff78a2673cc7302059d407cd6f89b15d71907db0dd9177",
    "executed_cpp/coordinator.cpp": "a67570b2b4a0fcc3f359392616c5ba146669afac1206fc095d27b43a5214dd00",
    "executed_cpp/coordinator.h": "7afb3fe12379f8aefd2472101ec54328f5d236aa3b2b91f91779e5c18056831c",
    "executed_cpp/runtime.cpp": "c253cbcaeab1655194b32f46b42262a20a0b7a459e0f34f22c9f53d8ab6367dd",
    "executed_cpp/sedimentation.cpp": "3f9344a2b1a3c314835d2436cb47204c7a9a06b3c0b3a242c965f89d1ebcd14c",
    "executed_cpp/sedimentation_conservative.cpp": "5af3a1d5a95624c0cc9a0c71ba411c0777c97426ab721ad9771a3d0b202489f7",
    "executed_cpp/kdm6_c_api.cpp": "8c3f4a96dc7078eea8b19806d70c0ec6477debbc2cead04eec32403c26efe049",
}
ROW_ORDER_SHA256 = "63adeb20086517a25a4f518ffd9caa539d610ad0e195d20e0e742724e3bd84c1"
NATIVE_HEADER = (
    "one_step_call,runtime_call,substep,b_zero,k_zero,B,K,stage,field,dtype,raw_hex"
)
NATIVE_META = (
    "# schema=kdm6.ice_number_applied.native.v1; capture_scope=raw_native_values; "
    "vertical_order=sedimentation_top_first; native_k_1based=K-k_zero; "
    "call_identity=runtime_call+one_step_call",
    "# selected_runtime_call=2; first_one_step_call=2; selected_B_zero=22617; "
    "K=39; max_rows=5000; max_bytes=1048576",
)
HOST_HEADER = (
    "CAPTURE 3 0 1 2 164 242 39  6.6666668653488159E-001 "
    "2 233 143 281 1 40 1 40 "
    "capture_id=/Users/yhlee/KDM6AD-k/host/research_evidence/"
    "native_qnice_39_20261102/runs/on_final/capture/host_qnice_pre_call.csv"
)
HOST_SCHEMA = (
    "CAPTURE_SCHEMA step rank domain_id tile i j levels model_time_minutes "
    "its ite jts jte kds kde k_start k_end capture_id"
)
HOST_ROW_SCHEMA = (
    "ROW_SCHEMA step rank domain_id tile i j k AL ALB RHO QV QNICE; "
    "words=raw_f32_hex; model_time_units=minutes_since_start; "
    "phase=after_moist_physics_prep_before_microphysics_driver; scheme=mp137"
)
STAGES = {
    "runtime_entry_pre_clamp": "ni qi qv den dend".split(),
    "runtime_entry_post_clamp": "ni qi".split(),
    STAGE: "dtcld workn_vt_over_delz ni_before work1_qi workn_qi dend dend_safe delz delz_safe mstep gate falk_stored_ni out_attempt_ni applied_out_ni in_attempt_ni applied_in_ni fall_ni_before ni_after fall_ni_after falk_candidate_pre_store_ni departure_cap_active departure_tie_active state_roundoff_residual_ni realized_delta_ni previous_actual_out_ni".split(),
    "runtime_post_sed_entry": ["ni"],
    "c3_pre_mf_d1": "ni_before ninuc pimlt_ni nfrzdtc ni_after_store1 ni_after_store2".split(),
    "c3_pre_homogeneous_freeze": "ni_before nc_freeze_source freeze_mask ni_after".split(),
    "c3_pre_snap_a": "ni_before qi dend gate_qi_ge_1e14 gate_ni_ge_zero ni_after lambda_raw lambda_clamped".split(),
    "c3_pre_mf_d2_d3_d4": "ni_before ninuc pimlt_ni nfrzdtc ni_after_store1 ni_after_store2".split(),
    "c3_pre_snap_b": "ni_before qi dend gate_qi_ge_1e14 gate_ni_ge_zero ni_after lambda_raw lambda_clamped".split(),
    "c3_input": "qi ni dend".split(),
    "final_dsd_number_rewrite": "ni_before ni_snapped_candidate ni_after".split(),
}
BOOL_FIELDS = {
    ("c3_pre_homogeneous_freeze", "freeze_mask"),
    ("c3_pre_snap_a", "gate_qi_ge_1e14"),
    ("c3_pre_snap_a", "gate_ni_ge_zero"),
    ("c3_pre_snap_b", "gate_qi_ge_1e14"),
    ("c3_pre_snap_b", "gate_ni_ge_zero"),
}
EXPECTED_FIELDS = {
    "dtcld",
    "workn_vt_over_delz",
    "ni_before",
    "ni_after",
    "work1_qi",
    "workn_qi",
    "dend",
    "dend_safe",
    "delz",
    "delz_safe",
    "mstep",
    "gate",
    "falk_candidate_pre_store_ni",
    "falk_stored_ni",
    "out_attempt_ni",
    "applied_out_ni",
    "in_attempt_ni",
    "applied_in_ni",
    "fall_ni_before",
    "fall_ni_after",
    "previous_actual_out_ni",
    "departure_cap_active",
    "departure_tie_active",
    "state_roundoff_residual_ni",
    "realized_delta_ni",
}


def need(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def word(x: float, dtype: str = "f64") -> str:
    fmt, integer = ("<d", "<Q") if dtype == "f64" else ("<f", "<I")
    return format(struct.unpack(integer, struct.pack(fmt, x))[0], "x")


def value(raw: str, dtype: str) -> float:
    need(
        dtype in ("f32", "f64") and raw and len(raw) <= (8 if dtype == "f32" else 16),
        "word dtype/length",
    )
    fmt, integer = ("<d", "<Q") if dtype == "f64" else ("<f", "<I")
    bits = int(raw, 16)
    x = struct.unpack(fmt, struct.pack(integer, bits))[0]
    need(math.isfinite(x), "nonfinite word")
    return x


def f32(x: float) -> float:
    return struct.unpack("<f", struct.pack("<f", x))[0]


def load_native(raw: bytes) -> dict:
    need(len(raw) <= 1 << 20 and raw.endswith(b"\n"), "native file bound/newline")
    lines = raw.decode("ascii").splitlines()
    need(
        len(lines) == 2773
        and lines[0] == NATIVE_HEADER
        and tuple(lines[1:3]) == NATIVE_META
        and lines[-1] == "# native_rows=2769,status=complete",
        "native header/footer",
    )
    reader = csv.DictReader(io.StringIO("\n".join([lines[0], *lines[3:-1]])))
    need(reader.fieldnames == NATIVE_HEADER.split(","), "native CSV columns")
    rows = list(reader)
    need(len(rows) == 2769, "native row inventory")
    seen = set()
    fields = {}
    stages = []
    order = []
    for r in rows:
        need(
            set(r) == set(reader.fieldnames)
            and None not in r
            and None not in r.values(),
            "native row column inventory",
        )
        need(
            r["one_step_call"] == "2"
            and r["runtime_call"] == "2"
            and r["b_zero"] == "22617"
            and r["B"] == "32248"
            and r["K"] == "39",
            "native call/tile identity",
        )
        k = int(r["k_zero"])
        need(0 <= k < K, "native K range")
        need(
            r["stage"] in STAGES and r["field"] in STAGES[r["stage"]],
            "native stage/field inventory",
        )
        dtype = "bool" if (r["stage"], r["field"]) in BOOL_FIELDS else "f64"
        need(
            r["dtype"] == dtype and re.fullmatch("[0-9a-f]+", r["raw_hex"]) is not None,
            "native dtype/raw word",
        )
        bits = int(r["raw_hex"], 16)
        need(bits < (2 if dtype == "bool" else 1 << 64), "native word size")
        if dtype == "f64":
            value(r["raw_hex"], dtype)
        key = (r["stage"], r["field"], k)
        need(key not in seen, "native duplicate stage/field/K")
        seen.add(key)
        if r["stage"] == STAGE:
            need(r["substep"] == "1", "ice substep")
        else:
            need(r["substep"] == "0", "non-ice substep")
        fields[key] = r
        if not stages or stages[-1] != r["stage"]:
            stages.append(r["stage"])
        order.append(
            "|".join(
                r[name]
                for name in (
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
    need(stages == list(STAGES), "native stage order")
    need(
        hashlib.sha256(("\n".join(order) + "\n").encode()).hexdigest()
        == ROW_ORDER_SHA256,
        "native row order signature",
    )
    for k in range(K):
        for stage, expected in STAGES.items():
            need(
                {field for s, field, j in fields if s == stage and j == k}
                == set(expected),
                "native complete stage/level inventory: " + stage,
            )
    return fields


def get(fields: dict, stage: str, field: str, k: int) -> float:
    r = fields[(stage, field, k)]
    return (
        value(r["raw_hex"], r["dtype"])
        if r["dtype"] != "bool"
        else float(int(r["raw_hex"], 16))
    )


def same_word(fields: dict, left: tuple, right: tuple) -> None:
    need(
        fields[left]["dtype"] == fields[right]["dtype"]
        and fields[left]["raw_hex"] == fields[right]["raw_hex"],
        "raw-word handoff: " + str((left, right)),
    )


def load_host(raw: bytes) -> dict:
    need(len(raw) < 8192 and raw.endswith(b"\n"), "host trace bound/newline")
    lines = raw.decode("ascii").splitlines()
    need(
        len(lines) == 43
        and lines[0] == HOST_HEADER
        and lines[1] == HOST_SCHEMA
        and lines[2] == HOST_ROW_SCHEMA
        and lines[-1] == "END_CAPTURE 3 0 1 2 164 242 39 rows=39 completeness=complete",
        "host trace schema/footer",
    )
    rows = {}
    for expected_k, line in enumerate(lines[3:-1], 1):
        x = line.split()
        need(
            len(x) == 13 and x[:7] == ["ROW", "3", "0", "1", "2", "164", "242"],
            "host row identity",
        )
        native_k = int(x[7])
        need(native_k == expected_k and native_k not in rows, "host K/order inventory")
        words = dict(zip(("AL", "ALB", "RHO", "QV", "QNICE"), x[8:]))
        need(
            all(
                re.fullmatch("[0-9A-F]{8}", item) is not None for item in words.values()
            ),
            "host f32 words",
        )
        for item in words.values():
            value(item, "f32")
        rows[native_k] = words
    need(set(rows) == set(range(1, 40)), "host complete native levels")
    return rows


def analyze(host_raw: bytes, native_raw: bytes) -> dict:
    host = load_host(host_raw)
    r = load_native(native_raw)
    f = Fraction.from_float
    before, after, dz, out, incoming = [], [], [], [], []
    cap_count = gate_count = dz_floor_count = 0
    for k in range(K):
        native_k = K - k
        h = host[native_k]
        al, alb, rho = (value(h[name], "f32") for name in ("AL", "ALB", "RHO"))
        need(
            word(f32(1.0 / f32(al + alb)), "f32").zfill(8).upper() == h["RHO"],
            "host density source-order raw word",
        )
        for host_field, runtime_field in (
            ("RHO", "den"),
            ("QV", "qv"),
            ("QNICE", "ni"),
        ):
            expected = value(h[host_field], "f32")
            need(
                word(expected)
                == r[("runtime_entry_pre_clamp", runtime_field, k)]["raw_hex"],
                "host-to-runtime f32 widening: " + host_field,
            )
        same_word(r, ("runtime_entry_post_clamp", "ni", k), (STAGE, "ni_before", k))
        same_word(r, (STAGE, "ni_after", k), ("runtime_post_sed_entry", "ni", k))
        ni = get(r, STAGE, "ni_before", k)
        ni_after = get(r, STAGE, "ni_after", k)
        w = get(r, STAGE, "workn_qi", k)
        m = get(r, STAGE, "mstep", k)
        gate = get(r, STAGE, "gate", k)
        dt = get(r, STAGE, "dtcld", k)
        raw_dz = get(r, STAGE, "delz", k)
        safe_dz = get(r, STAGE, "delz_safe", k)
        need(
            dt == 20.0
            and m == 1.0
            and gate == 1.0
            and get(r, STAGE, "workn_vt_over_delz", k) == 1.0,
            "timestep/gate/normalization",
        )
        need(
            raw_dz > 1.0e-9
            and get(r, STAGE, "dend", k) > 1.0e-9
            and r[(STAGE, "delz", k)]["raw_hex"]
            == r[(STAGE, "delz_safe", k)]["raw_hex"]
            and r[(STAGE, "dend", k)]["raw_hex"]
            == r[(STAGE, "dend_safe", k)]["raw_hex"],
            "inactive density/depth floors",
        )
        gate_count += gate == 1.0
        dz_floor_count += raw_dz != safe_dz
        candidate = ni * w / m * gate
        need(
            word(candidate) == r[(STAGE, "falk_candidate_pre_store_ni", k)]["raw_hex"],
            "falk pre-store word",
        )
        need(
            word(candidate) == r[(STAGE, "falk_stored_ni", k)]["raw_hex"],
            "falk stored word",
        )
        attempt = candidate * dt
        actual = min(attempt, ni)
        need(
            word(attempt) == r[(STAGE, "out_attempt_ni", k)]["raw_hex"]
            and word(actual) == r[(STAGE, "applied_out_ni", k)]["raw_hex"],
            "actual departure source order",
        )
        cap_count += attempt > ni
        need(
            get(r, STAGE, "departure_cap_active", k) == float(attempt > ni)
            and get(r, STAGE, "departure_tie_active", k) == float(attempt == ni),
            "departure branch flags",
        )
        prev = 0.0 if k == 0 else out[-1]
        inc = 0.0 if k == 0 else prev * dz[-1] / safe_dz
        need(
            word(prev) == r[(STAGE, "previous_actual_out_ni", k)]["raw_hex"]
            and word(inc) == r[(STAGE, "applied_in_ni", k)]["raw_hex"]
            and word(inc) == r[(STAGE, "in_attempt_ni", k)]["raw_hex"],
            "actual arrival source order",
        )
        expected_after = ni - actual if k == 0 else ni - actual + inc
        need(
            word(expected_after) == r[(STAGE, "ni_after", k)]["raw_hex"],
            "NI update source-order raw bits",
        )
        need(
            word(ni_after - expected_after)
            == r[(STAGE, "state_roundoff_residual_ni", k)]["raw_hex"],
            "recorded state arithmetic residual",
        )
        fall_before = get(r, STAGE, "fall_ni_before", k)
        fall_after = fall_before + actual / dt
        need(
            word(fall_after) == r[(STAGE, "fall_ni_after", k)]["raw_hex"],
            "fall accumulator source-order raw bits",
        )
        need(
            word(ni_after - ni) == r[(STAGE, "realized_delta_ni", k)]["raw_hex"],
            "realized delta word",
        )
        before.append(ni)
        after.append(ni_after)
        dz.append(raw_dz)
        out.append(actual)
        incoming.append(inc)
    handoffs = [
        (("runtime_post_sed_entry", "ni"), ("c3_pre_mf_d1", "ni_before")),
        (
            ("c3_pre_mf_d1", "ni_after_store2"),
            ("c3_pre_homogeneous_freeze", "ni_before"),
        ),
        (("c3_pre_homogeneous_freeze", "ni_after"), ("c3_pre_snap_a", "ni_before")),
        (("c3_pre_snap_a", "ni_after"), ("c3_pre_mf_d2_d3_d4", "ni_before")),
        (("c3_pre_mf_d2_d3_d4", "ni_after_store2"), ("c3_pre_snap_b", "ni_before")),
        (("c3_pre_snap_b", "ni_after"), ("c3_input", "ni")),
    ]
    for left, right in handoffs:
        for k in range(K):
            same_word(r, (left[0], left[1], k), (right[0], right[1], k))
    rewrite_stages = (
        ("d1_melt", "c3_pre_mf_d1", "ni_before", "ni_after_store2"),
        ("homogeneous_freeze", "c3_pre_homogeneous_freeze", "ni_before", "ni_after"),
        ("snap_a", "c3_pre_snap_a", "ni_before", "ni_after"),
        ("d2_d3_d4", "c3_pre_mf_d2_d3_d4", "ni_before", "ni_after_store2"),
        ("snap_b", "c3_pre_snap_b", "ni_before", "ni_after"),
    )
    pre_c3_changes = {}
    for label, stage, first, last in rewrite_stages:
        changed = [
            K - k
            for k in range(K)
            if r[(stage, first, k)]["raw_hex"] != r[(stage, last, k)]["raw_hex"]
        ]
        weighted = sum(
            (
                f(dz[k]) * (f(get(r, stage, last, k)) - f(get(r, stage, first, k)))
                for k in range(K)
            ),
            Fraction(),
        )
        pre_c3_changes[label] = {
            "changed_native_levels_1based": changed,
            "weighted_ni_dz_change": float(weighted),
        }
    change = sum(
        (f(dz[k]) * (f(after[k]) - f(before[k])) for k in range(K)), Fraction()
    )
    interface = [
        f(dz[k]) * f(out[k]) - f(dz[k + 1]) * f(incoming[k + 1]) for k in range(K - 1)
    ]
    bottom = f(dz[-1]) * f(out[-1])
    attributed_loss = bottom + sum(interface, Fraction())
    residual = -change - attributed_loss
    selected = {}
    for native_k in (21, 23):
        k = K - native_k
        selected[str(native_k)] = {
            "top_first_k_zero": k,
            "ni_before": before[k],
            "applied_out_ni": out[k],
            "applied_in_ni": incoming[k],
            "ni_after": after[k],
            "realized_delta_ni": after[k] - before[k],
            "delz": dz[k],
        }
    return {
        "schema": "kdm6.native_qnice_39_private_replay.v1",
        "host_sha256": hashlib.sha256(host_raw).hexdigest(),
        "native_sha256": hashlib.sha256(native_raw).hexdigest(),
        "levels": K,
        "ice_substeps": 1,
        "host_density_f32_words_equal": K,
        "host_to_runtime_den_qv_ni_words_equal": 3 * K,
        "sedimentation_state_and_fall_raw_words_equal": True,
        "pre_c3_stage_handoffs_raw_words_equal": 6 * K,
        "pre_c3_ni_changes": pre_c3_changes,
        "gate_active_levels": gate_count,
        "departure_cap_active_levels": cap_count,
        "delz_floor_active_levels": dz_floor_count,
        "selected_levels": selected,
        "numerical_coordinate": "NI * raw DELZ; QNICE physical basis unresolved",
        "column_change_ni_dz": float(change),
        "bottom_out_ni_dz": float(bottom),
        "interface_difference_ni_dz": [float(x) for x in interface],
        "interface_difference_max_abs_ni_dz": float(max(map(abs, interface))),
        "attributed_loss_ni_dz": float(attributed_loss),
        "arithmetic_closure_residual_ni_dz": float(residual),
        "physical_conservation_certified": False,
    }


def pinned_inputs() -> dict[str, bytes]:
    """Read every published artifact once, then check immutable code pins."""
    data = {}
    for relative, expected in PINS.items():
        raw = (PACKET / relative).read_bytes()
        need(
            hashlib.sha256(raw).hexdigest() == expected,
            "published artifact SHA-256: " + relative,
        )
        data[relative] = raw
    return data


def verify_attestations(data: dict[str, bytes]) -> dict:
    """Check the recorded source/build/run chain; private binaries stay private."""
    cpp1 = json.loads(data["raw/cpp_attempt1_receipt.json"])
    cpp2 = json.loads(data["raw/cpp_attempt2_receipt.json"])
    cpp4 = json.loads(data["raw/cpp_build_receipt.json"])
    host_retry = json.loads(data["raw/host_retry_receipt.json"])
    host5 = json.loads(data["raw/host_build_receipt.json"])
    off = json.loads(data["raw/off_run_result.json"])
    on = json.loads(data["raw/on_run_result.json"])
    historical_compare = json.loads(data["raw/historical_c5_compare_receipt.json"])
    sessions = [
        json.loads(data[f"raw/{mode}_live_session.json"]) for mode in ("off", "on")
    ]
    need(
        cpp1["schema"] == "kdm6.native_qnice_39_cpp_build.v1"
        and cpp2["schema"] == "kdm6.native_qnice_39_cpp_build_attempt2.v1"
        and cpp4["schema"] == "kdm6.native_qnice_39_cpp_build_attempt4.v1"
        and host_retry["schema"] == "kdm6ad.native_qnice_host_retry_pr457_v3.v1"
        and host5["schema"] == "kdm6ad.native_qnice_attempt5_host_bundle.v1",
        "build receipt schema lineage",
    )
    need(
        cpp2["attempt1_receipt_sha256"] == PINS["raw/cpp_attempt1_receipt.json"]
        and cpp4["attempt2_receipt_sha256"] == PINS["raw/cpp_attempt2_receipt.json"]
        and host5["cpp_attempt4_receipt"]["sha256"]
        == PINS["raw/cpp_build_receipt.json"]
        and host5["fp64_retry_lineage"]["receipt_sha256"]
        == PINS["raw/host_retry_receipt.json"]
        and host5["fp64_retry_lineage"]["retry_archive_sha256"]
        == host_retry["historical_archive"]["retry_archive_sha256"],
        "receipt parent chain",
    )
    need(
        set(cpp4["archive_member_changes_vs_attempt2"])
        == {"coordinator.cpp.o", "runtime.cpp.o"}
        and set(cpp2["archive_member_changes_vs_attempt1"])
        == {"sedimentation_conservative.cpp.o"}
        and cpp4["verification"]["call2_single_loop"]["header_first_one_step_call"] == 2
        and cpp4["verification"]["two_calls_two_outer_subcycles"][
            "all_legacy_streams_byte_identical_to_attempt2"
        ]
        is True
        and cpp4["verification"]["direct_conservative_cap_smoke"][
            "binary64_source_order_replay_all39"
        ]
        is True
        and host5["executable"]["imports_native_fp64_value"] is True
        and host5["executable"]["imports_f32_step_wrapper"] is False
        and host5["loader_resolution"]["first_rpath_resolves_to_attempt5_prefix"]
        is True,
        "executed build/branch contract",
    )
    for relative, hashes in cpp4["source_changes_vs_attempt2"].items():
        name = Path(relative).name
        need(
            PINS[f"executed_cpp/{name}"] == hashes["attempt4"],
            "executed C++ identity source: " + name,
        )
    need(
        PINS["executed_cpp/sedimentation_conservative.cpp"]
        == cpp2["attempt2_source_file_sha256"]["src/sedimentation_conservative.cpp"]
        and PINS["executed_cpp/sedimentation.cpp"]
        == cpp1["instrumented_source_sha256"]["src/sedimentation.cpp"],
        "executed sedimentation source lineage",
    )
    exe_sha = host5["executable"]["sha256"]
    dso_sha = host5["dso"]["attempt5_sha256"]
    need(
        exe_sha == host_retry["retry_executable"]["sha256"]
        and dso_sha == cpp4["dso_sha256"] == host5["dso"]["build_sha256"],
        "host executable/DSO receipt values",
    )
    common = (
        "worktree_commit",
        "historical_plan_sha256",
        "source_sha256",
        "cpp_receipt_sha256",
        "host_receipt_sha256",
        "executable_sha256",
        "dso_sha256",
        "origin_sha256",
        "startup_sha256",
        "endpoint_sha256",
        "private_runner_sha256",
    )
    need(
        off["schema"] == on["schema"] == "kdm6.native_qnice_39_same_call_run.v1"
        and off["mode"] == "off_final"
        and on["mode"] == "on_final"
        and all(off[key] == on[key] for key in common)
        and off["worktree_commit"] == "3fda6cbcda751a6ea2475213b4237a86ec21f0b6"
        and off["cpp_receipt_sha256"] == PINS["raw/cpp_build_receipt.json"]
        and off["host_receipt_sha256"] == PINS["raw/host_build_receipt.json"]
        and off["executable_sha256"] == exe_sha
        and off["dso_sha256"] == dso_sha
        and off["private_runner_sha256"] == PINS["producer/run_host.py.txt"]
        and off["historical_c5_endpoint_match"] is False
        and on["historical_c5_endpoint_match"] is False
        and off["endpoint_sha256"]
        == "225d2cabe8a466304c06ba1a04638b84c8456b8477326b6852c9217360440070",
        "same-build off/on receipt identity",
    )
    need(
        off["capture_files"] == {}
        and set(on["capture_files"])
        == {
            "cpp_scalar_30339_2.csv",
            "host_qnice_pre_call.csv",
            "native_qnice_applied_30339_runtime2.csv",
        }
        and on["capture_files"]["host_qnice_pre_call.csv"]
        == PINS["raw/host_qnice_pre_call.csv"]
        and on["capture_files"]["native_qnice_applied_30339_runtime2.csv"]
        == PINS["raw/native_qnice_applied_30339_runtime2.csv"]
        and on["capture_files"]["cpp_scalar_30339_2.csv"]
        == "fd2a239a480a728aebdbde2d2a3a982a949f4349eec2df4f094081f2211a58a5",
        "capture file inventory/digest",
    )
    scan = data["raw/historical_c5_compare.txt"].decode("utf-8")
    need(
        historical_compare["schema"]
        == "kdm6.native_qnice_39_historical_endpoint_comparison.v1"
        and historical_compare["comparison_tool"] == "harness/strict_bitwise_nc.py"
        and historical_compare["comparison_tool_sha256"]
        == PINS["producer/strict_bitwise_nc.py.txt"]
        and historical_compare["historical_c5_endpoint_sha256"]
        == off["historical_c5_endpoint_sha256"]
        and historical_compare["new_off_endpoint_sha256"] == off["endpoint_sha256"]
        and historical_compare["stdout_sha256"] == PINS["raw/historical_c5_compare.txt"]
        and historical_compare["exit_code"] == 1
        and historical_compare["common_variables"] == 652
        and historical_compare["bitwise_matching_variables"] == 650
        and historical_compare["differing_variables"] == {"QNCLOUD": 15, "RE_CLOUD": 1}
        and "VARIABLES: 652 common, 650 BITWISE-MATCH, 2 DIFFER" in scan
        and "QNCLOUD                DIVERGES 15/2573532 cells" in scan
        and "RE_CLOUD               DIVERGES 1/2573532 cells" in scan
        and scan.endswith("RESULT: FAIL\n"),
        "pinned historical endpoint scan receipt",
    )
    for mode, run, session in zip(("off", "on"), (off, on), sessions):
        need(
            run["session_record_sha256"] == PINS[f"raw/{mode}_live_session.json"]
            and session["status"] == "complete"
            and session["initial_time"] == "2025-07-19_00:00:40"
            and session["initial_itimestep"] == session["startup_itimestep"] == 2
            and session["dt_seconds"] == 20
            and session["steps"] == len(session["controls"]) == 1
            and session["control_family"] == "ANALYSIS_TQ"
            and session["execution"]
            == {
                "experiment_valid": True,
                "invalid_reasons": [],
                "requested_proc_grid": "1x1",
                "actual_proc_grid": "1x1",
                "active_input_identity_complete": True,
                "exit_code": 0,
                "model_completed": True,
            }
            and session["executable_sha256"] == exe_sha
            and session["library_candidate_sha256"] == dso_sha
            and session["startup_sha256"] == run["startup_sha256"]
            and session["controls"][0]["output_checkpoint_sha256"]
            == run["endpoint_sha256"]
            and session["controls"][0]["output_time"] == "2025-07-19_00:01:00"
            and session["controls"][0]["output_itimestep"] == 3
            and session["startup_origin_comparison"]["numeric_element_mismatches"] == 1
            and len(session["loaded_library_lines"]) == 1
            and session["loaded_library_lines"][0].endswith(
                "> " + host5["loader_resolution"]["expected_runtime_dso_realpath"]
            ),
            "completed run/dynamic-loader attestation: " + mode,
        )
    return {"off": off, "on": on, "cpp": cpp4, "host": host5}


def verify_prior_scalar(raws: dict[str, bytes], fields: dict, host: dict) -> None:
    """Join the exact old selected packet to this run's identical scalar hash."""
    prior_dir = REPO / "harness/evidence/native_c5_limiter_call_2026-11-01"
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    module = importlib.import_module(
        "harness.evidence.native_c5_limiter_call_2026-11-01.verify_packet"
    )
    prior_raw = (prior_dir / "selected_packet.json").read_bytes()
    need(
        hashlib.sha256(prior_raw).hexdigest() == module.PACKET_SHA256,
        "historical selected C5 packet SHA-256",
    )
    module.verify(prior_raw, module.PACKET_SHA256)
    packet = json.loads(prior_raw)
    need(
        any(
            f["sha256"] == raws["on"]["capture_files"]["cpp_scalar_30339_2.csv"]
            and f["identity"] == ["2", "2", "1", "32248", "39"]
            for f in packet["capture_files"]
        ),
        "identical legacy scalar capture file",
    )
    selected = packet["selected_rows"]
    for model_k in (20, 22):
        top_k = 38 - model_k
        native_k = model_k + 1
        rows = {
            (r["stage"], r["field"]): r for r in selected if r["k_zero"] == str(model_k)
        }
        for stage, field, expected in (
            ("abi_ingress", "ni", host[native_k]["QNICE"].lower()),
            ("c3_in", "state.ni", fields[("c3_input", "ni", top_k)]["raw_hex"]),
        ):
            row = rows[(stage, field)]
            need(
                (
                    row["one_step_call"],
                    row["runtime_call"],
                    row["substep"],
                    row["b_zero"],
                    row["B"],
                    row["K"],
                )
                == ("2", "2", "1", "22617", "32248", "39")
                and row["raw_hex"] == expected,
                "same-call scalar/host/C3 raw-word join",
            )


def replay() -> dict:
    data = pinned_inputs()
    attested = verify_attestations(data)
    host_raw = data["raw/host_qnice_pre_call.csv"]
    native_raw = data["raw/native_qnice_applied_30339_runtime2.csv"]
    host = load_host(host_raw)
    fields = load_native(native_raw)
    verify_prior_scalar({"on": attested["on"]}, fields, host)
    result = analyze(host_raw, native_raw)
    need(
        result == json.loads(data["raw/initial_analysis.json"]),
        "saved numerical analysis equality",
    )
    result["schema"] = "kdm6.native_qnice_39_applied_public_replay.v1"
    result["native_same_call_scalar_join"] = True
    result["attested_off_on_endpoint_hashes_equal"] = True
    result["private_executable_and_dso_bytes_redistributed"] = False
    result["historical_c5_endpoint_equal"] = False
    result["physical_unit_status"] = "INCONCLUSIVE"
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(json.dumps(replay(), indent=2, sort_keys=True))
    print("NATIVE_QNICE_39_APPLIED_REPLAY_PASSED")
