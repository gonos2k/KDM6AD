#!/usr/bin/env python3
"""Same-call native D1 mass/number/temperature replay and conditional AD."""

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

import torch


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
PARENT = REPO / "harness/evidence/native_qnice_d1_qi_2026-11-03"
SPEED = REPO / "harness/evidence/native_qnice_ice_speed_ad_2026-11-03"
CAPTURE_NAME = "raw/native_qnice_applied_57032_runtime2.csv"
PARENT_REPLAY_SHA = "e3bc6dc8c41bcf4e267d42908baee7c97c22b80e808c3e17d88f03a03e7ff81d"
SPEED_REPLAY_SHA = "628de86460cfaa2aaa4760d00632e651d8efbf903c312cf636d4bceb44839f28"
SPEED_THERMO_SHA = "f4c887ba754244f781a27cd94dc42341e7559be7680947f74ea27d06507dbe4b"
ORDER_SHA = "4c1d8d59e9227d10e9d3f69f7f8cfb3674749c8853605e662242f220b68c0130"
PINS = {
    "raw/build_receipt.json": "54fcb88c3482070bde43bb6220b5a009f27a3a5dcc749fa90824f8eae27bc13c",
    "raw/host_qnice_pre_call.csv": "3ca8411ccc0368eef4c08df8a682cfd3aca7b10c944edce7b8dd959ffc9c9c75",
    CAPTURE_NAME: "6ef59ed078387583323a4b173910c03a2d117acffc91b45f47165c585a7e6efe",
    "raw/off_live_session.json": "6d2bf4f77f378d554810be3b0a76cd1c66f883f7dc5fe7c2b45aa26d9f201900",
    "raw/off_run_result.json": "3ffb86e0093ddc55c3f3078aad01e7760480133d43b38babc03dd05b9604d700",
    "raw/on_live_session.json": "4f9d3a7ea6cd293e16909e1cfc429dca640d41c975d556ec076bf381a91d5cb9",
    "raw/on_run_result.json": "63329e15fd5d2eebb7521fb6b771809c0da071d94cef790dd9b9fe3eb07bb94b",
    "producer/d1_extra_capture_block.txt": "4088c4369cccf4403b1c41e194fe644cfd18dad0e4f695a7d1b6e087eb94778d",
    "executed_headers/constants.h.txt": "f9e41a49e36414f9247f1a645051ba78b4dc7847bdc084669e4a96516a2a3f74",
    "executed_headers/melt_freeze.h.txt": "a8e562d644ea7aa88a8221f4ef30aea5b48cdd80a7173f3d71cf8c5678808292",
    "executed_headers/ops.h.txt": "4a11cca456b9a0095917e96c4fea1ec7347e4c0050416925d837bbdc002d8b5d",
    "executed_cpp/ops.cpp.txt": "0c0cb13fc97c66888424121453537af953165746d9e9bdc6e21fa69dccbe9014",
    "results.json": "9c016291e06edc2c0572b02b0e2a4bbaaaeee2badfdc27e0d1b92d995aa08330",
}
NEW_FIELDS = {
    "qc_before",
    "nc_before",
    "qv_before",
    "pre_cpm",
    "cpm_safe",
    "psmlt_capped",
    "pgmlt_capped",
    "qc_after_store1",
    "qc_after_store2",
    "nc_after_store1",
    "nc_after_store2",
    "t_after_melt",
    "t_after_d1",
}
L15 = 39 - 15
OUTPUTS = ("QC", "QI", "NC", "NI", "T")


def need(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def pinned(name: str) -> bytes:
    raw = (HERE / name).read_bytes()
    need(sha(raw) == PINS[name], "pinned D1 AD packet: " + name)
    return raw


def load_module(path: Path, expected: str, name: str):
    need(sha(path.read_bytes()) == expected, "parent replay source: " + name)
    spec = importlib.util.spec_from_file_location(name, path)
    need(spec is not None and spec.loader is not None, "import: " + name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def f64(raw_hex: str) -> float:
    out = struct.unpack("<d", int(raw_hex, 16).to_bytes(8, "little"))[0]
    need(math.isfinite(out), "nonfinite captured f64")
    return out


def word(value: float) -> str:
    return format(int.from_bytes(struct.pack("<d", value), "little"), "x")


def load_parent():
    parent = load_module(PARENT / "replay.py", PARENT_REPLAY_SHA, "native_d1_parent")
    parent.replay()  # Verify the complete prior packet, its source and its saved result.
    p39 = parent.parent_module()
    p39raw = (p39.PACKET / "raw/native_qnice_applied_30339_runtime2.csv").read_bytes()
    need(
        sha(p39raw) == p39.PINS["raw/native_qnice_applied_30339_runtime2.csv"],
        "39-level parent capture",
    )
    old39 = p39.load_native(p39raw)
    old = parent.parse_capture(parent.pinned(parent.RAW_NAME), old39, p39)
    return parent, p39, old


def parse_capture(raw: bytes, old: dict, p39) -> dict:
    need(len(raw) <= 2 << 20 and raw.endswith(b"\n"), "D1 AD capture bound")
    lines = raw.decode("ascii").splitlines()
    need(
        len(lines) == 3982
        and lines[0] == p39.NATIVE_HEADER
        and lines[1] == p39.NATIVE_META[0]
        and lines[2]
        == "# selected_runtime_call=2; first_one_step_call=2; selected_B_zero=22617; K=39; max_rows=7000; max_bytes=2097152"
        and lines[-1] == "# native_rows=3978,status=complete",
        "D1 AD header/footer",
    )
    reader = csv.DictReader(io.StringIO("\n".join([lines[0], *lines[3:-1]])))
    need(reader.fieldnames == p39.NATIVE_HEADER.split(","), "D1 AD columns")
    rows = list(reader)
    need(len(rows) == 3978, "D1 AD row count")
    fields = {}
    stages = []
    ordered = []
    expected = set(old) | {
        ("c3_pre_mf_d1", field, k) for k in range(39) for field in NEW_FIELDS
    }
    for row in rows:
        need(
            set(row) == set(reader.fieldnames) and None not in row.values(),
            "D1 AD row shape",
        )
        need(
            (
                row["one_step_call"],
                row["runtime_call"],
                row["b_zero"],
                row["B"],
                row["K"],
            )
            == ("2", "2", "22617", "32248", "39"),
            "D1 AD same-call tile identity",
        )
        try:
            k = int(row["k_zero"])
            bits = int(row["raw_hex"], 16)
        except ValueError as exc:
            raise ValueError("D1 AD integer/hex field") from exc
        need(0 <= k < 39 and row["k_zero"] == str(k), "D1 AD level identity")
        key = (row["stage"], row["field"], k)
        need(key in expected and key not in fields, "D1 AD field/duplicate")
        need(
            row["substep"] == ("1" if row["stage"] == p39.STAGE else "0"),
            "D1 AD substep",
        )
        dtype = "bool" if (row["stage"], row["field"]) in p39.BOOL_FIELDS else "f64"
        need(row["dtype"] == dtype, "D1 AD dtype")
        need(
            row["raw_hex"] == format(bits, "x")
            and bits < (2 if dtype == "bool" else 1 << 64),
            "D1 AD raw word",
        )
        if dtype == "f64":
            f64(row["raw_hex"])
        fields[key] = row
        if not stages or stages[-1] != row["stage"]:
            stages.append(row["stage"])
        ordered.append(
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
        set(fields) == expected and stages == list(p39.STAGES),
        "D1 AD stage/level inventory",
    )
    need(sha(("\n".join(ordered) + "\n").encode()) == ORDER_SHA, "D1 AD row order")
    for key, prior in old.items():
        current = fields[key]
        need(
            (current["dtype"], current["raw_hex"])
            == (prior["dtype"], prior["raw_hex"]),
            "D1 parent raw bits",
        )
    return fields


def get(fields: dict, stage: str, field: str, k: int) -> float:
    return f64(fields[(stage, field, k)]["raw_hex"])


def check_word(
    fields: dict, stage: str, field: str, k: int, value: float, reason: str
) -> None:
    need(fields[(stage, field, k)]["raw_hex"] == word(value), reason)


def provenance(parent, receipt: dict) -> None:
    need(receipt["schema"] == "kdm6.native_d1_ad_cpp_build.v1", "D1 AD build schema")
    parent_receipt_raw = parent.pinned("raw/build_receipt.json")
    need(
        sha(parent_receipt_raw) == receipt["parent_build_receipt_sha256"],
        "D1 build parent",
    )
    need(
        receipt["only_source_changes_vs_parent"] == ["src/coordinator.cpp"],
        "D1 AD source change inventory",
    )
    block = pinned("producer/d1_extra_capture_block.txt")
    need(sha(block) == receipt["capture_block_sha256"], "D1 capture source block")
    previous = parent.pinned("executed_cpp/coordinator.cpp")
    anchor = b"    out.t   = (t_d3 + fr_coef * mf.pfrzdtr).to(dtype);                             // D4 freeze heat (F:1591, f32 rate)\n"
    need(previous.count(anchor) == 1, "D1 capture overlay anchor")
    executed = previous.replace(anchor, anchor + block, 1)
    need(
        sha(executed) == receipt["source_sha256"]["coordinator.cpp"],
        "D1 capture-only source reconstruction",
    )
    for name in ("runtime.cpp", "melt_freeze.cpp"):
        need(
            receipt["source_sha256"][name] == parent.PINS["executed_cpp/" + name],
            "unchanged D1 source: " + name,
        )
    for name in ("constants.h.txt", "melt_freeze.h.txt", "ops.h.txt"):
        relative = "executed_headers/" + name
        need(
            receipt["source_headers_sha256"][name] == PINS[relative],
            "D1 build header: " + name,
        )
        pinned(relative)
    need(
        b"inline constexpr double DEFAULT_XLF = 3.50e5;"
        in pinned("executed_headers/melt_freeze.h.txt")
        and b"inline constexpr double QCRMIN = 1.0e-9;"
        in pinned("executed_headers/constants.h.txt")
        and b"inline constexpr double EPS        = 1.0e-15;"
        in pinned("executed_headers/constants.h.txt"),
        "D1 captured thermal/floor constants",
    )
    thermo = (SPEED / "source_snapshots/build_tree_thermo.cpp.txt").read_bytes()
    ops = pinned("executed_cpp/ops.cpp.txt")
    need(
        sha(thermo)
        == SPEED_THERMO_SHA
        == receipt["producer_source_sha256"]["thermo.cpp"]
        and sha(ops) == receipt["producer_source_sha256"]["ops.cpp"],
        "D1 QV-to-cpm producer sources",
    )
    need(
        b"const double cpd = 1004.5;" in thermo
        and b"const double cpv = 1846.4;" in thermo
        and b"auto q_safe = torch::clamp(q, /*min=*/p.qmin);" in thermo
        and b"return ops::fma_acc(ab, q_safe, cpv_t);" in thermo
        and b"if (value == 1.0)  return acc + t1 * t2;" in ops,
        "D1 QV-to-cpm source formula",
    )
    need(
        b"const torch::Tensor& t2, double value = 1.0);"
        in pinned("executed_headers/ops.h.txt"),
        "D1 accumulator default argument",
    )
    need(
        receipt["executable_sha256"]
        == json.loads(parent_receipt_raw)["new_executable_sha256"],
        "same host executable",
    )
    need(
        receipt["parent_dso_sha256"]
        == json.loads(parent_receipt_raw)["new_dso_sha256"],
        "D1 parent DSO",
    )
    need("-ffp-contract=off" in receipt["cxx_flags"], "D1 build FP contraction")
    for mode in ("off", "on"):
        run = json.loads(pinned(f"raw/{mode}_run_result.json"))
        session_raw = pinned(f"raw/{mode}_live_session.json")
        session = json.loads(session_raw)
        need(
            run["mode"] == mode and run["schema"] == "kdm6.native_d1_qi_capture_run.v1",
            "D1 run schema/mode",
        )
        need(run["session_record_sha256"] == sha(session_raw), "D1 run/session link")
        need(run["source_sha256"] == receipt["source_sha256"], "D1 run source")
        need(
            all(
                run["object_sha256"][name] == receipt["object_sha256"][name]
                for name in run["object_sha256"]
            ),
            "D1 run objects",
        )
        need(
            run["executable_sha256"]
            == session["executable_sha256"]
            == receipt["executable_sha256"],
            "D1 host executable",
        )
        need(
            run["dso_sha256"]
            == session["library_candidate_sha256"]
            == receipt["new_dso_sha256"],
            "D1 loaded DSO hash",
        )
        need(
            run["endpoint_sha256"]
            == "225d2cabe8a466304c06ba1a04638b84c8456b8477326b6852c9217360440070",
            "D1 off/on/prior endpoint",
        )
        need(
            run["origin_sha256"]
            == "7a353f1fa4f6636864ac169c9ee8d16869d1f38c8e998762c19659404cbb9c8e",
            "D1 origin",
        )
        need(
            session["status"] == "complete"
            and session["execution"]["experiment_valid"] is True,
            "D1 host execution",
        )
        need(
            any(
                "/native_qnice_d1_ad_20261103/host_bundle/libtorch/install/lib/libkdm6_c.2.0.0.dylib"
                in s
                for s in session["loaded_library_lines"]
            ),
            "D1 loaded isolated DSO",
        )
        if mode == "off":
            need(run["captures"] == {}, "D1 off capture")
        else:
            need(
                run["captures"]
                == {
                    "host_qnice_pre_call.csv": PINS["raw/host_qnice_pre_call.csv"],
                    "native_qnice_applied_57032_runtime2.csv": PINS[CAPTURE_NAME],
                },
                "D1 on capture hashes",
            )
    new_host = pinned("raw/host_qnice_pre_call.csv").decode().splitlines()
    old_host = parent.pinned("raw/host_qnice_pre_call.csv").decode().splitlines()
    need(
        new_host[0].split("capture_id=")[0] == old_host[0].split("capture_id=")[0]
        and new_host[1:] == old_host[1:],
        "D1 host input rows",
    )


def replay_d1_stores(fields: dict) -> dict:
    stage = "c3_pre_mf_d1"
    melted = []
    for k in range(39):
        q = get(fields, stage, "qi_before", k)
        n = get(fields, stage, "ni_before", k)
        qc = get(fields, stage, "qc_before", k)
        nc = get(fields, stage, "nc_before", k)
        t = get(fields, stage, "t_before", k)
        active = t > 273.15 and q > 0.0
        mqi = q if active else 0.0
        mni = n if active else 0.0
        check_word(fields, stage, "pimlt_qi", k, mqi, "D1 QI producer")
        check_word(fields, stage, "pimlt_ni", k, mni, "D1 NI producer")
        qv_safe = max(get(fields, stage, "qv_before", k), 1e-15)
        produced_cpm = 1004.5 * (1.0 - qv_safe) + qv_safe * 1846.4
        check_word(fields, stage, "pre_cpm", k, produced_cpm, "D1 QV-to-cpm producer")
        cpm = max(get(fields, stage, "pre_cpm", k), 1e-9)
        check_word(fields, stage, "cpm_safe", k, cpm, "D1 cpm clamp")
        for name in ("pinuc_qi", "pfrzdtc_qi", "ninuc", "nfrzdtc"):
            need(get(fields, stage, name, k) == 0.0, "D1 frozen freeze terms")
        qc1 = (qc - get(fields, stage, "pinuc_qi", k)) + mqi
        qc2 = qc1 - get(fields, stage, "pfrzdtc_qi", k)
        nc1 = (nc - get(fields, stage, "ninuc", k)) + mni
        nc2 = nc1 - get(fields, stage, "nfrzdtc", k)
        coef = 350000.0 / cpm
        td1 = (
            (t + coef * get(fields, stage, "psmlt_capped", k))
            + coef * get(fields, stage, "pgmlt_capped", k)
        ) - coef * mqi
        for name, value in (
            ("qc_after_store1", qc1),
            ("qc_after_store2", qc2),
            ("nc_after_store1", nc1),
            ("nc_after_store2", nc2),
            ("t_after_melt", td1),
            ("t_after_d1", td1),
        ):
            check_word(fields, stage, name, k, value, "D1 source-order " + name)
        check_word(
            fields,
            "c3_pre_homogeneous_freeze",
            "qc_freeze_source",
            k,
            qc2,
            "D1 QC handoff",
        )
        if active:
            melted.append(39 - k)
    need(melted == [15], "observed active D1 ice melt")
    return {
        "melted_native_levels": melted,
        "level15": {
            name: get(fields, stage, name, L15)
            for name in (
                "qi_before",
                "ni_before",
                "qc_before",
                "nc_before",
                "t_before",
                "pimlt_qi",
                "pimlt_ni",
                "cpm_safe",
                "psmlt_capped",
                "pgmlt_capped",
                "qi_after_store2",
                "ni_after_store2",
                "qc_after_store2",
                "nc_after_store2",
                "t_after_d1",
            )
        },
    }


def local_d1_map(fields: dict):
    """Only the instantaneous ice-melt producer varies; other D1 operands are fixed."""
    stage = "c3_pre_mf_d1"

    def scalar(name: str) -> torch.Tensor:
        return torch.tensor(get(fields, stage, name, L15), dtype=torch.float64)

    q0, n0 = scalar("qi_before"), scalar("ni_before")
    qc, nc, t = scalar("qc_before"), scalar("nc_before"), scalar("t_before")
    cpm, ps, pg = scalar("cpm_safe"), scalar("psmlt_capped"), scalar("pgmlt_capped")
    coef = 350000.0 / cpm

    def fn(q: torch.Tensor, n: torch.Tensor) -> torch.Tensor:
        active = (t > 273.15) & (q > 0.0)
        mq = torch.where(active, q, torch.zeros_like(q))
        mn = torch.where(active, n, torch.zeros_like(n))
        qc_out = qc + mq
        qi_out = q - mq
        nc_out = nc + mn
        ni_out = n - mn
        t_out = ((t + coef * ps) + coef * pg) - coef * mq
        return torch.stack((qc_out, qi_out, nc_out, ni_out, t_out))

    return fn, q0, n0, coef


def derivatives(fields: dict) -> dict:
    fn, q0, n0, coef = local_d1_map(fields)
    base = fn(q0, n0)
    for i, name in enumerate(
        (
            "qc_after_store2",
            "qi_after_store2",
            "nc_after_store2",
            "ni_after_store2",
            "t_after_d1",
        )
    ):
        check_word(
            fields, "c3_pre_mf_d1", name, L15, base[i].item(), "D1 AD baseline " + name
        )
    need(
        q0.item() > 0
        and n0.item() == 0
        and get(fields, "c3_pre_mf_d1", "t_before", L15) > 273.15,
        "D1 branch baseline",
    )
    zero = torch.zeros_like(q0)
    _, j_q = torch.func.jvp(fn, (q0, n0), (q0, zero))
    _, j_n = torch.func.jvp(fn, (q0, n0), (zero, torch.ones_like(n0)))
    expected_q = torch.stack((q0, zero, zero, zero, -coef * q0))
    expected_n = torch.stack((zero, zero, torch.ones_like(n0), zero, zero))
    need(torch.allclose(j_q, expected_q, rtol=1e-13, atol=1e-24), "D1 QI relative JVP")
    need(torch.allclose(j_n, expected_n, rtol=1e-13, atol=1e-24), "D1 NI positive JVP")
    weights = torch.tensor((2.0, -3.0, 5.0, 7.0, 11.0), dtype=torch.float64)
    _, pullback = torch.func.vjp(fn, q0, n0)
    vq, vn = pullback(weights)
    need(
        torch.allclose(vq * q0, torch.dot(weights, expected_q), rtol=1e-13, atol=1e-20),
        "D1 QI weighted VJP",
    )
    need(
        torch.allclose(vn, torch.dot(weights, expected_n), rtol=1e-13, atol=1e-20),
        "D1 NI weighted VJP",
    )
    fd_q = {}
    for h in (0.1, 0.01, 0.001):
        minus, plus = q0 * (1.0 - h), q0 * (1.0 + h)
        need(minus.item() > 0 and plus.item() > 0, "D1 QI FD branch")
        low, high = fn(minus, n0), fn(plus, n0)
        represented = (plus.item() - minus.item()) / q0.item()
        fd = (high - low) / represented
        bounds = [2.0 * math.ulp(base[i].item()) / represented for i in range(5)]
        for i in range(5):
            need(
                abs(fd[i].item() - expected_q[i].item()) <= bounds[i] + 1e-24,
                "D1 QI represented-gap FD: " + OUTPUTS[i],
            )
        fd_q[str(h)] = {
            "represented_relative_gap": represented,
            "output_difference": (high - low).tolist(),
            "output_ulp": [math.ulp(x) for x in base.tolist()],
            "fd": fd.tolist(),
            "fd_minus_jvp": (fd - expected_q).tolist(),
        }
    fd_n = {}
    for h in (1.0, 0.1, 0.01):
        high = fn(q0, torch.tensor(h, dtype=torch.float64))
        fd = (high - base) / h
        need(
            torch.allclose(fd, expected_n, rtol=1e-12, atol=1e-12),
            "D1 NI positive one-sided FD",
        )
        fd_n[str(h)] = fd.tolist()
    return {
        "output_order": OUTPUTS,
        "qi_relative_jvp": j_q.tolist(),
        "qi_relative_analytic": expected_q.tolist(),
        "ni_positive_absolute_jvp": j_n.tolist(),
        "ni_positive_absolute_analytic": expected_n.tolist(),
        "weighted_vjp": [vq.item(), vn.item()],
        "qi_relative_finite_differences": fd_q,
        "ni_positive_one_sided_finite_differences": fd_n,
        "ni_zero_gate_boundary": True,
    }


def no_splice_chain(fields: dict, speed) -> dict:
    rows, _ = speed.load()
    q0 = speed.tensor(rows, "runtime_entry_post_clamp", "qi")
    n0 = speed.tensor(rows, speed.S, "ni_before")
    op = {
        name: speed.tensor(rows, speed.S, name)
        for name in (
            "dend",
            "dend_safe",
            "delz",
            "delz_safe",
            "work1_qi",
            "workn_qi",
            "mstep",
            "gate",
            "dtcld",
        )
    }
    qsed, nsed, *_ = speed.transport(q0, n0, op["work1_qi"], op["workn_qi"], op)
    t = torch.tensor(
        [get(fields, "c3_pre_mf_d1", "t_before", k) for k in range(39)],
        dtype=torch.float64,
    )
    zero = torch.zeros_like(qsed)
    active = (t > 273.15) & (qsed > 0.0)
    qd1 = qsed - torch.where(active, qsed, zero)
    nd1 = nsed - torch.where(active, nsed, torch.zeros_like(nsed))
    a = speed.snap(qd1, nd1, op["dend"])

    def rates(field: str) -> torch.Tensor:
        return torch.tensor(
            [get(fields, "c3_pre_mf_d2_d3_d4", field, k) for k in range(39)],
            dtype=torch.float64,
        )

    qd2 = (qd1 + rates("pinuc_qi") - rates("pimlt_qi")) + rates("pfrzdtc_qi")
    nd2 = (a + rates("ninuc") - rates("pimlt_ni")) + rates("nfrzdtc")
    b = speed.snap(qd2, nd2, op["dend"])
    for k in range(39):
        for value, stage, name in (
            (qsed[k], "c3_pre_mf_d1", "qi_before"),
            (nsed[k], "c3_pre_mf_d1", "ni_before"),
            (qd1[k], "c3_pre_mf_d1", "qi_after_store2"),
            (nd1[k], "c3_pre_mf_d1", "ni_after_store2"),
            (a[k], "c3_pre_snap_a", "ni_after"),
            (qd2[k], "c3_pre_snap_b", "qi"),
            (b[k], "c3_input", "ni"),
        ):
            check_word(
                fields,
                stage,
                name,
                k,
                value.item(),
                "no-splice chain " + stage + "/" + name,
            )
    return {"fixed_speed_c3_ni_raw_bit_matches": 39, "hardcoded_qi15_splice": False}


def replay(
    *, capture_override: bytes | None = None, capture_sha: str | None = None
) -> dict:
    parent, p39, old = load_parent()
    speed = load_module(
        SPEED / "replay.py", SPEED_REPLAY_SHA, "native_ice_speed_parent"
    )
    receipt = json.loads(pinned("raw/build_receipt.json"))
    provenance(parent, receipt)
    raw = pinned(CAPTURE_NAME) if capture_override is None else capture_override
    if capture_override is not None:
        need(capture_sha is not None and sha(raw) == capture_sha, "override SHA-256")
    fields = parse_capture(raw, old, p39)
    result = {
        "schema": "kdm6.native_d1_ad_conditional.v1",
        "call": {
            "runtime_call": 2,
            "one_step_call": 2,
            "b_zero": 22617,
            "native_ij_1based": [164, 242],
            "levels": 39,
        },
        "new_rows": len(fields) - len(old),
        "parent_rows_raw_bit_equal": len(old),
        "off_on_endpoint_sha256": "225d2cabe8a466304c06ba1a04638b84c8456b8477326b6852c9217360440070",
        "d1_stores": replay_d1_stores(fields),
        "conditional_derivatives": derivatives(fields),
        "no_splice_chain": no_splice_chain(fields, speed),
        "scientific_status": "INCONCLUSIVE",
        "physical_unit_status": "INCONCLUSIVE",
    }
    if capture_override is None:
        saved = json.loads(pinned("results.json"))
        for stable in (
            "call",
            "new_rows",
            "parent_rows_raw_bit_equal",
            "off_on_endpoint_sha256",
            "d1_stores",
            "no_splice_chain",
            "scientific_status",
            "physical_unit_status",
        ):
            need(saved[stable] == result[stable], "saved D1 stable result: " + stable)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = replay()
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print("NATIVE_QNICE_D1_CONDITIONAL_AD_REPLAY_PASSED")
        print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
