#!/usr/bin/env python3
"""Pinned, source-order QI replay for the same native call before snap A."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
import struct


PACKET = Path(__file__).resolve().parent
REPO = PACKET.parents[2]
PARENT = REPO / "harness/evidence/native_qnice_39_applied_2026-11-03"
RAW_NAME = "raw/native_qnice_applied_38424_runtime2.csv"
PINS = {
    "raw/build_receipt.json": "3c51e5f03a2ca4099fa2bad6f783a99095c41f6cbce833d44e01ea333f4b5a73",
    "raw/host_qnice_pre_call.csv": "a503ad36f34102db0eaf782f43bca52bf6f647883f4ecc8b7a42d5c0bf933ace",
    RAW_NAME: "f9acaa8138b3f4b4634fc7b06ffa7da7bd4ad4dfd0872762bcb4ff1dd198e760",
    "raw/off_live_session.json": "0978a98d1c1c89ec85d5a55e2089d4c45a33bbe3174aa4238387c2385de13b7d",
    "raw/off_run_result.json": "2850c9e38abf52e278d8c6e9cb6613b892368d040151fc7f27ceef6e71cd4299",
    "raw/on_live_session.json": "2891702f52c97b114855053ad9167fbf272428cdc2398bec0892740cab1a6a55",
    "raw/on_run_result.json": "bed03bb1c9694ef9d17428d98ffca558b1697417f964a316ca6ac412de8a0826",
    "executed_cpp/coordinator.cpp": "8663f8de6616111e0fb228efa0af01b4793ab544901074ec31f2c556640053b4",
    "executed_cpp/melt_freeze.cpp": "049e3327a277f0342d80767ea5bb48b0f56fa7e1fbdd412b4f508db976d9d4da",
    "executed_cpp/runtime.cpp": "5fd679246a5bac02bec7d0ed784a43cad7d4a6cfbb190387bb7103b152e23a59",
    "producer/run.py.txt": "c3a5aefabf4804b92caa002786e733dd89f95370ac1fc9a2ca86395a7cde36a4",
    "results.json": "dff583b5d9bbaa2dd0e4921bc5909b45517166b10b6b745f99d46606ec17a92d",
}
PARENT_REPLAY_SHA = "83932565067bf6433aebc090974e9c21338c019403e6f4d3779c327b4ab12968"
ORDER_SHA = "3bda0060e10d67279e22f6a4c5ee3776013f66f93019150d47fab749802e6240"
ADDED = {
    "runtime_post_sed_entry": ["qi"],
    "c3_pre_mf_d1": [
        "qi_before",
        "t_before",
        "pinuc_qi",
        "pimlt_qi",
        "pfrzdtc_qi",
        "qi_after_store1",
        "qi_after_store2",
    ],
    "c3_pre_homogeneous_freeze": ["qi_before", "qc_freeze_source", "qi_after"],
    "c3_pre_mf_d2_d3_d4": [
        "qi_before",
        "t_before",
        "pinuc_qi",
        "pimlt_qi",
        "pfrzdtc_qi",
        "qi_after_store1",
        "qi_after_store2",
    ],
}


def need(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError(why)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def pinned(relative: str) -> bytes:
    raw = (PACKET / relative).read_bytes()
    need(digest(raw) == PINS[relative], "packet SHA-256: " + relative)
    return raw


def parent_module():
    path = PARENT / "replay.py"
    need(digest(path.read_bytes()) == PARENT_REPLAY_SHA, "parent replay SHA-256")
    spec = importlib.util.spec_from_file_location("native_qnice_39_parent", path)
    need(spec is not None and spec.loader is not None, "parent replay import")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def f64(raw_hex: str) -> float:
    value = struct.unpack("<d", int(raw_hex, 16).to_bytes(8, "little"))[0]
    need(math.isfinite(value), "nonfinite QI operand")
    return value


def word(value: float) -> str:
    return format(int.from_bytes(struct.pack("<d", value), "little"), "x")


def parse_capture(raw: bytes, old: dict, parent) -> dict:
    need(len(raw) <= 2 << 20 and raw.endswith(b"\n"), "capture bound/newline")
    lines = raw.decode("ascii").splitlines()
    need(
        len(lines) == 3475
        and lines[0] == parent.NATIVE_HEADER
        and lines[1] == parent.NATIVE_META[0]
        and lines[2]
        == "# selected_runtime_call=2; first_one_step_call=2; selected_B_zero=22617; K=39; max_rows=7000; max_bytes=2097152"
        and lines[-1] == "# native_rows=3471,status=complete",
        "capture header/footer",
    )
    reader = csv.DictReader(io.StringIO("\n".join([lines[0], *lines[3:-1]])))
    need(reader.fieldnames == parent.NATIVE_HEADER.split(","), "capture columns")
    rows = list(reader)
    need(len(rows) == 3471, "capture row count")
    fields = {}
    stages = []
    order = []
    expected = {
        s: set(names) | set(ADDED.get(s, ())) for s, names in parent.STAGES.items()
    }
    for r in rows:
        need(
            set(r) == set(reader.fieldnames) and None not in r.values(),
            "capture row shape",
        )
        need(
            (r["one_step_call"], r["runtime_call"], r["b_zero"], r["B"], r["K"])
            == ("2", "2", "22617", "32248", "39"),
            "same-call tile identity",
        )
        try:
            k = int(r["k_zero"])
        except ValueError as exc:
            raise ValueError("capture k_zero") from exc
        need(0 <= k < 39 and r["k_zero"] == str(k), "capture level")
        stage, name = r["stage"], r["field"]
        need(stage in expected and name in expected[stage], "capture stage inventory")
        need(r["substep"] == ("1" if stage == parent.STAGE else "0"), "capture substep")
        dtype = "bool" if (stage, name) in parent.BOOL_FIELDS else "f64"
        need(r["dtype"] == dtype, "capture dtype")
        try:
            n = int(r["raw_hex"], 16)
        except ValueError as exc:
            raise ValueError("capture raw hex") from exc
        need(
            r["raw_hex"] == format(n, "x") and n < (2 if dtype == "bool" else 1 << 64),
            "capture raw word",
        )
        if dtype == "f64":
            need(math.isfinite(f64(r["raw_hex"])), "capture finite word")
        key = (stage, name, k)
        need(key not in fields, "capture duplicate")
        fields[key] = r
        if not stages or stages[-1] != stage:
            stages.append(stage)
        order.append(
            "|".join(
                r[c]
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
    need(stages == list(parent.STAGES), "capture stage order")
    need(digest(("\n".join(order) + "\n").encode()) == ORDER_SHA, "capture row order")
    for k in range(39):
        for stage, names in expected.items():
            need(
                {name for s, name, j in fields if s == stage and j == k} == names,
                "capture complete stage/level",
            )
    need(set(old).issubset(fields), "parent record inventory")
    for key, row in old.items():
        new = fields[key]
        need(
            (new["dtype"], new["raw_hex"]) == (row["dtype"], row["raw_hex"]),
            "parent record raw bits",
        )
    return fields


def source_provenance(receipt: dict, parent) -> None:
    need(receipt["schema"] == "kdm6.native_d1_qi_cpp_build.v1", "build schema")
    need(
        receipt["only_source_changes_vs_parent_attempt4"]
        == ["src/coordinator.cpp", "src/runtime.cpp"],
        "source change inventory",
    )
    for name in ("coordinator.cpp", "runtime.cpp", "melt_freeze.cpp"):
        need(
            receipt["source_snapshots_sha256"][name] == PINS["executed_cpp/" + name],
            "source receipt",
        )
    old_co_path = PARENT / "executed_cpp/coordinator.cpp"
    need(
        digest(old_co_path.read_bytes()) == parent.PINS["executed_cpp/coordinator.cpp"],
        "parent coordinator source",
    )
    old_co = old_co_path.read_text()
    new_co = pinned("executed_cpp/coordinator.cpp").decode()
    qi_rows = "".join(
        f'    capture_native_tensor(checkpoint.c_str(), "{name}", {value});\n'
        for name, value in (
            ("qi_before", "s.qi"),
            ("t_before", "s.t"),
            ("pinuc_qi", "mf.pinuc"),
            ("pimlt_qi", "mf.pimlt_qi"),
            ("pfrzdtc_qi", "mf.pfrzdtc"),
            ("qi_after_store1", "qi1"),
            ("qi_after_store2", "out.qi"),
        )
    )
    hom_rows = (
        '    capture_native_tensor("c3_pre_homogeneous_freeze", "qi_before", state.qi);\n'
        '    capture_native_tensor("c3_pre_homogeneous_freeze", "qc_freeze_source", state.qc);\n'
        '    capture_native_tensor("c3_pre_homogeneous_freeze", "qi_after", out.qi);\n'
    )
    for line in hom_rows.splitlines(keepends=True):
        need(new_co.count(line) == 1, "homogeneous capture source")
        new_co = new_co.replace(line, "", 1)
    need(new_co.count(qi_rows) == 1, "D1 capture source")
    need(new_co.replace(qi_rows, "", 1) == old_co, "coordinator capture-only overlay")
    old_rt_path = PARENT / "executed_cpp/runtime.cpp"
    need(
        digest(old_rt_path.read_bytes()) == parent.PINS["executed_cpp/runtime.cpp"],
        "parent runtime source",
    )
    old_rt = old_rt_path.read_text()
    new_rt = pinned("executed_cpp/runtime.cpp").decode()
    qi_rt = (
        '        capture_native_tensor("runtime_post_sed_entry", "qi", cur.qi, true);\n'
    )
    need(
        new_rt.count(qi_rt) == 1 and new_rt.replace(qi_rt, "", 1) == old_rt,
        "runtime capture-only overlay",
    )
    pinned("executed_cpp/melt_freeze.cpp")
    need(
        receipt["new_executable_sha256"]
        == receipt["parent_39_applied_executable_sha256"],
        "host executable reused",
    )


def run_provenance(receipt: dict, parent, parent_raw: bytes) -> dict:
    off = json.loads(pinned("raw/off_run_result.json"))
    on = json.loads(pinned("raw/on_run_result.json"))
    sessions = (
        json.loads(pinned("raw/off_live_session.json")),
        json.loads(pinned("raw/on_live_session.json")),
    )
    for run, session in zip((off, on), sessions, strict=True):
        need(run["schema"] == "kdm6.native_d1_qi_capture_run.v1", "run schema")
        need(
            run["endpoint_sha256"]
            == "225d2cabe8a466304c06ba1a04638b84c8456b8477326b6852c9217360440070",
            "endpoint identity",
        )
        need(
            run["origin_sha256"]
            == "7a353f1fa4f6636864ac169c9ee8d16869d1f38c8e998762c19659404cbb9c8e",
            "origin identity",
        )
        need(
            run["executable_sha256"]
            == receipt["new_executable_sha256"]
            == session["executable_sha256"],
            "run executable",
        )
        need(
            run["dso_sha256"]
            == receipt["new_dso_sha256"]
            == session["library_candidate_sha256"],
            "run DSO",
        )
        need(run["source_sha256"] == receipt["source_snapshots_sha256"], "run source")
        need(
            all(
                run["object_sha256"][name] == receipt["object_sha256"][name]
                for name in run["object_sha256"]
            ),
            "run objects",
        )
        need(
            run["session_record_sha256"]
            == digest(
                (PACKET / ("raw/" + run["mode"] + "_live_session.json")).read_bytes()
            ),
            "run session",
        )
        need(
            session["status"] == "complete"
            and session["execution"]["experiment_valid"] is True,
            "run completed",
        )
        need(
            any(
                "/native_qnice_d1_20261103/host_bundle/libtorch/install/lib/libkdm6_c.2.0.0.dylib"
                in line
                for line in session["loaded_library_lines"]
            ),
            "loaded isolated DSO",
        )
    need(
        off["mode"] == "off" and on["mode"] == "on" and off["captures"] == {},
        "paired modes",
    )
    need(
        on["captures"]
        == {
            "host_qnice_pre_call.csv": PINS["raw/host_qnice_pre_call.csv"],
            "native_qnice_applied_38424_runtime2.csv": PINS[RAW_NAME],
        },
        "capture hashes",
    )
    new_host = pinned("raw/host_qnice_pre_call.csv").decode().splitlines()
    old_host = parent_raw.decode().splitlines()
    need(
        new_host[0].split("capture_id=")[0] == old_host[0].split("capture_id=")[0]
        and new_host[1:] == old_host[1:],
        "host input words unchanged",
    )
    return {"off_on_endpoint_sha256": off["endpoint_sha256"], "shared_host_rows": 39}


def same(fields: dict, a: tuple, b: tuple) -> None:
    need(
        fields[a]["dtype"] == fields[b]["dtype"]
        and fields[a]["raw_hex"] == fields[b]["raw_hex"],
        "QI handoff: " + str((a, b)),
    )


def get(fields: dict, stage: str, name: str, k: int) -> float:
    return f64(fields[(stage, name, k)]["raw_hex"])


def replay(
    *, capture_override: bytes | None = None, capture_sha: str | None = None
) -> dict:
    parent = parent_module()
    parent_raw = (PARENT / "raw/native_qnice_applied_30339_runtime2.csv").read_bytes()
    need(
        digest(parent_raw)
        == parent.PINS["raw/native_qnice_applied_30339_runtime2.csv"],
        "parent capture SHA-256",
    )
    old = parent.load_native(parent_raw)
    parent_host = (PARENT / "raw/host_qnice_pre_call.csv").read_bytes()
    need(
        digest(parent_host) == parent.PINS["raw/host_qnice_pre_call.csv"],
        "parent host SHA-256",
    )
    receipt = json.loads(pinned("raw/build_receipt.json"))
    source_provenance(receipt, parent)
    provenance = run_provenance(receipt, parent, parent_host)
    pinned("producer/run.py.txt")
    raw = pinned(RAW_NAME) if capture_override is None else capture_override
    if capture_override is not None:
        need(capture_sha is not None and digest(raw) == capture_sha, "override SHA-256")
    fields = parse_capture(raw, old, parent)
    melted = []
    homogeneous = []
    for k in range(39):
        native = 39 - k
        sed = ("runtime_post_sed_entry", "qi", k)
        d1 = ("c3_pre_mf_d1", "qi_before", k)
        same(fields, sed, d1)
        q = get(fields, *d1)
        t = get(fields, "c3_pre_mf_d1", "t_before", k)
        expected_melt = q if t > 273.15 and q > 0.0 else 0.0
        need(
            fields[("c3_pre_mf_d1", "pimlt_qi", k)]["raw_hex"] == word(expected_melt),
            "D1 melt producer raw bits",
        )
        for name in ("pinuc_qi", "pfrzdtc_qi"):
            need(get(fields, "c3_pre_mf_d1", name, k) == 0.0, "D1 zero freeze term")
        store1 = (q + get(fields, "c3_pre_mf_d1", "pinuc_qi", k)) - expected_melt
        store2 = store1 + get(fields, "c3_pre_mf_d1", "pfrzdtc_qi", k)
        need(
            fields[("c3_pre_mf_d1", "qi_after_store1", k)]["raw_hex"] == word(store1),
            "D1 QI store1 raw bits",
        )
        need(
            fields[("c3_pre_mf_d1", "qi_after_store2", k)]["raw_hex"] == word(store2),
            "D1 QI store2 raw bits",
        )
        same(
            fields,
            ("c3_pre_mf_d1", "qi_after_store2", k),
            ("c3_pre_homogeneous_freeze", "qi_before", k),
        )
        mask = int(
            fields[("c3_pre_homogeneous_freeze", "freeze_mask", k)]["raw_hex"], 16
        )
        hom = store2 + get(
            fields, "c3_pre_homogeneous_freeze", "qc_freeze_source", k
        ) * float(mask)
        need(
            fields[("c3_pre_homogeneous_freeze", "qi_after", k)]["raw_hex"]
            == word(hom),
            "homogeneous QI raw bits",
        )
        same(
            fields,
            ("c3_pre_homogeneous_freeze", "qi_after", k),
            ("c3_pre_snap_a", "qi", k),
        )
        same(fields, ("c3_pre_snap_a", "qi", k), ("c3_pre_mf_d2_d3_d4", "qi_before", k))
        d2_q = get(fields, "c3_pre_mf_d2_d3_d4", "qi_before", k)
        d2_store1 = (d2_q + get(fields, "c3_pre_mf_d2_d3_d4", "pinuc_qi", k)) - get(
            fields, "c3_pre_mf_d2_d3_d4", "pimlt_qi", k
        )
        d2_store2 = d2_store1 + get(fields, "c3_pre_mf_d2_d3_d4", "pfrzdtc_qi", k)
        need(
            fields[("c3_pre_mf_d2_d3_d4", "qi_after_store1", k)]["raw_hex"]
            == word(d2_store1),
            "D2-D4 QI store1 raw bits",
        )
        need(
            fields[("c3_pre_mf_d2_d3_d4", "qi_after_store2", k)]["raw_hex"]
            == word(d2_store2),
            "D2-D4 QI store2 raw bits",
        )
        same(
            fields,
            ("c3_pre_mf_d2_d3_d4", "qi_after_store2", k),
            ("c3_pre_snap_b", "qi", k),
        )
        same(fields, ("c3_pre_snap_b", "qi", k), ("c3_input", "qi", k))
        if expected_melt > 0:
            melted.append(native)
        if mask:
            homogeneous.append(native)
    k15 = 39 - 15
    result = {
        "schema": "kdm6.native_d1_qi_same_call_replay.v1",
        "call": {
            "runtime_call": 2,
            "one_step_call": 2,
            "b_zero": 22617,
            "native_ij_1based": [164, 242],
            "levels": 39,
        },
        "parent_rows_raw_bit_equal": len(old),
        "new_rows": len(fields) - len(old),
        "d1_melt_native_levels": sorted(melted),
        "homogeneous_freeze_native_levels": sorted(homogeneous),
        "level15": {
            "post_sed_qi": get(fields, "runtime_post_sed_entry", "qi", k15),
            "d1_temperature_K": get(fields, "c3_pre_mf_d1", "t_before", k15),
            "d1_applied_pimlt_qi": get(fields, "c3_pre_mf_d1", "pimlt_qi", k15),
            "d1_first_store_qi": get(fields, "c3_pre_mf_d1", "qi_after_store1", k15),
            "d1_output_qi": get(fields, "c3_pre_mf_d1", "qi_after_store2", k15),
            "homogeneous_freeze_mask": int(
                fields[("c3_pre_homogeneous_freeze", "freeze_mask", k15)]["raw_hex"], 16
            ),
            "snap_a_input_qi": get(fields, "c3_pre_snap_a", "qi", k15),
        },
        **provenance,
        "scientific_status": "INCONCLUSIVE",
        "physical_unit_status": "INCONCLUSIVE",
    }
    if capture_override is None:
        need(json.loads(pinned("results.json")) == result, "saved result consistency")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = replay()
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print("NATIVE_QNICE_D1_QI_REPLAY_PASSED")
        print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
