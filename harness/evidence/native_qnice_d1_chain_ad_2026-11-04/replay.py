#!/usr/bin/env python3
"""Conditional ice-speed → sedimentation → D1 → snap A/B derivative replay."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import struct

import torch


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
D1_PACKET = REPO / "harness/evidence/native_qnice_d1_ad_2026-11-03"
SPEED_PACKET = REPO / "harness/evidence/native_qnice_ice_speed_ad_2026-11-03"
D1_SOURCE_SHA = "3189153439220e8409345215fce00d2a145aee292f74224838d4602869e610ae"
SPEED_SOURCE_SHA = "628de86460cfaa2aaa4760d00632e651d8efbf903c312cf636d4bceb44839f28"
D1_RESULT_SHA = "9c016291e06edc2c0572b02b0e2a4bbaaaeee2badfdc27e0d1b92d995aa08330"
SPEED_RESULT_SHA = "b7175f04ff8e141041154851b61f3fc32ee9921993e90f7df063e79f7f5d4cfd"
SAVED_SHA = "7be5905393872125c5ada6d823e466d44c2b732164e157be18b4fd9c19ba6de2"
K = 39
L15, L16, L22, L23 = (K - level for level in (15, 16, 22, 23))
OUTPUTS = (
    "D1_QC15",
    "D1_QI15",
    "D1_NC15",
    "D1_NI15",
    "D1_T15",
    "C3_NI15",
    "C3_NI16",
    "C3_NI22",
    "C3_NI23",
)
SEEDS = ("relative_qi16", "relative_qi23", "relative_qi16_qi23")


def need(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError(why)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_module(path: Path, expected: str, name: str):
    need(sha(path.read_bytes()) == expected, "pinned parent source: " + name)
    spec = importlib.util.spec_from_file_location(name, path)
    need(spec is not None and spec.loader is not None, "parent import: " + name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def word(value: float) -> str:
    return format(int.from_bytes(struct.pack("<d", value), "little"), "x")


def load():
    d1 = load_module(D1_PACKET / "replay.py", D1_SOURCE_SHA, "native_d1_ad_parent")
    speed = load_module(
        SPEED_PACKET / "replay.py", SPEED_SOURCE_SHA, "native_speed_parent"
    )
    raw = d1.pinned(d1.CAPTURE_NAME)
    need(sha(raw) == d1.PINS[d1.CAPTURE_NAME], "D1 capture SHA-256")
    d1_result = d1.replay(capture_override=raw, capture_sha=sha(raw))
    saved_d1_raw = (D1_PACKET / "results.json").read_bytes()
    need(sha(saved_d1_raw) == D1_RESULT_SHA, "saved D1 result SHA-256")
    saved_d1 = json.loads(saved_d1_raw)
    for name in (
        "call",
        "new_rows",
        "parent_rows_raw_bit_equal",
        "d1_stores",
        "no_splice_chain",
    ):
        need(saved_d1[name] == d1_result[name], "D1 baseline/source contract: " + name)
    d1_parent, p39, old = d1.load_parent()
    fields = d1.parse_capture(raw, old, p39)
    source = speed.source_attribution()
    need(source, "speed source attribution")
    saved_speed_raw = (SPEED_PACKET / "results.json").read_bytes()
    need(sha(saved_speed_raw) == SPEED_RESULT_SHA, "saved speed result SHA-256")
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
    op["den"] = speed.tensor(rows, "runtime_entry_pre_clamp", "den")
    need(
        all(
            v.dtype == torch.float64 and v.shape == (K,) for v in (q0, n0, *op.values())
        ),
        "f64 39-level operands",
    )
    need(
        torch.all(op["mstep"] == 1).item()
        and torch.all(op["gate"] == 1).item()
        and torch.all(op["dtcld"] == 20).item(),
        "one active ice substep",
    )

    def captured(stage: str, name: str) -> torch.Tensor:
        return torch.tensor(
            [d1.get(fields, stage, name, k) for k in range(K)], dtype=torch.float64
        )

    stage = "c3_pre_mf_d1"
    fixed = {
        name: captured(stage, name)
        for name in (
            "qc_before",
            "nc_before",
            "t_before",
            "cpm_safe",
            "psmlt_capped",
            "pgmlt_capped",
            "pinuc_qi",
            "pfrzdtc_qi",
            "ninuc",
            "nfrzdtc",
        )
    }
    fixed["hom_mask"] = torch.tensor(
        [
            bool(
                int(
                    fields[("c3_pre_homogeneous_freeze", "freeze_mask", k)]["raw_hex"],
                    16,
                )
            )
            for k in range(K)
        ]
    )
    fixed["d2"] = {
        name: captured("c3_pre_mf_d2_d3_d4", name)
        for name in (
            "pinuc_qi",
            "pimlt_qi",
            "pfrzdtc_qi",
            "ninuc",
            "pimlt_ni",
            "nfrzdtc",
        )
    }
    need(
        not bool(torch.any(fixed["hom_mask"])),
        "homogeneous mask fixed false in this call",
    )
    need(
        all(
            torch.all(fixed[name] == 0).item()
            for name in ("pinuc_qi", "pfrzdtc_qi", "ninuc", "nfrzdtc")
        ),
        "zero D1 freeze terms",
    )
    return d1, speed, fields, q0, n0, op, fixed, source


def chain(
    q: torch.Tensor,
    n: torch.Tensor,
    speed,
    op: dict,
    fixed: dict,
    params,
    *,
    dynamic: bool,
    diagnostic: bool = False,
) -> tuple:
    if dynamic:
        wq, wn, producer = speed.ice_speeds(
            q, n, op["den"], op["dend"], op["delz_safe"], params
        )
    else:
        wq, wn, producer = op["work1_qi"], op["workn_qi"], {}
    qsed, nsed, qout, nout, qtry, ntry = speed.transport(q, n, wq, wn, op)
    d1_active = (fixed["t_before"] > 273.15) & (qsed > 0.0)
    mqi = torch.where(d1_active, qsed, torch.zeros_like(qsed))
    mni = torch.where(d1_active, nsed, torch.zeros_like(nsed))
    qc1 = fixed["qc_before"] - fixed["pinuc_qi"] + mqi
    qc_d1 = qc1 - fixed["pfrzdtc_qi"]
    qi1 = qsed + fixed["pinuc_qi"] - mqi
    qi_d1 = qi1 + fixed["pfrzdtc_qi"]
    nc1 = fixed["nc_before"] - fixed["ninuc"] + mni
    nc_d1 = nc1 - fixed["nfrzdtc"]
    ni1 = nsed + fixed["ninuc"] - mni
    ni_d1 = ni1 + fixed["nfrzdtc"]
    coef = 350000.0 / fixed["cpm_safe"]
    t_d1 = (
        (fixed["t_before"] + coef * fixed["psmlt_capped"])
        + coef * fixed["pgmlt_capped"]
    ) - coef * mqi
    mask = fixed["hom_mask"].to(torch.float64)
    q_hom = qi_d1 + qc_d1 * mask
    n_hom = ni_d1 + nc_d1 * mask
    a_diag, b_diag = {}, {}
    na = speed.snap(q_hom, n_hom, op["dend"], a_diag if diagnostic else None)
    d2 = fixed["d2"]
    qd2 = (q_hom + d2["pinuc_qi"] - d2["pimlt_qi"]) + d2["pfrzdtc_qi"]
    nd2 = (na + d2["ninuc"] - d2["pimlt_ni"]) + d2["nfrzdtc"]
    nb = speed.snap(qd2, nd2, op["dend"], b_diag if diagnostic else None)
    selected = torch.stack(
        (
            qc_d1[L15],
            qi_d1[L15],
            nc_d1[L15],
            ni_d1[L15],
            t_d1[L15],
            nb[L15],
            nb[L16],
            nb[L22],
            nb[L23],
        )
    )
    parts = {
        "wq": wq,
        "wn": wn,
        "producer": producer,
        "qsed": qsed,
        "nsed": nsed,
        "qout": qout,
        "nout": nout,
        "qtry": qtry,
        "ntry": ntry,
        "d1_active": d1_active,
        "mqi": mqi,
        "mni": mni,
        "qc_d1": qc_d1,
        "qi_d1": qi_d1,
        "nc_d1": nc_d1,
        "ni_d1": ni_d1,
        "t_d1": t_d1,
        "q_hom": q_hom,
        "n_hom": n_hom,
        "na": na,
        "qd2": qd2,
        "nd2": nd2,
        "nb": nb,
        "a_diag": a_diag,
        "b_diag": b_diag,
    }
    return selected, parts


def raw_baseline(d1, fields: dict, fixed_parts: dict, baseline: torch.Tensor) -> dict:
    checks = (
        ("qsed", "c3_pre_mf_d1", "qi_before"),
        ("nsed", "c3_pre_mf_d1", "ni_before"),
        ("mqi", "c3_pre_mf_d1", "pimlt_qi"),
        ("mni", "c3_pre_mf_d1", "pimlt_ni"),
        ("qc_d1", "c3_pre_mf_d1", "qc_after_store2"),
        ("qi_d1", "c3_pre_mf_d1", "qi_after_store2"),
        ("nc_d1", "c3_pre_mf_d1", "nc_after_store2"),
        ("ni_d1", "c3_pre_mf_d1", "ni_after_store2"),
        ("t_d1", "c3_pre_mf_d1", "t_after_d1"),
        ("q_hom", "c3_pre_snap_a", "qi"),
        ("na", "c3_pre_snap_a", "ni_after"),
        ("qd2", "c3_pre_snap_b", "qi"),
        ("nb", "c3_input", "ni"),
    )
    for part, stage, name in checks:
        for k in range(K):
            need(
                word(fixed_parts[part][k].item())
                == fields[(stage, name, k)]["raw_hex"],
                "fixed-speed no-splice raw bits: " + part,
            )
    need(
        word(baseline[0].item())
        == fields[("c3_pre_mf_d1", "qc_after_store2", L15)]["raw_hex"],
        "selected QC baseline",
    )
    return {
        "checked_fields": [part for part, _, _ in checks],
        "raw_bit_matches_per_field": K,
        "hardcoded_qi15_splice": False,
    }


def cap_winner(attempt: torch.Tensor, reservoir: torch.Tensor) -> str:
    if bool(attempt < reservoir):
        return "raw"
    if bool(attempt == reservoir):
        return "tie"
    return "reservoir"


def signature(parts: dict, q: torch.Tensor, n: torch.Tensor) -> tuple:
    prod, a, b = parts["producer"], parts["a_diag"], parts["b_diag"]
    out = []
    for k in (L15, L16, L22, L23):
        out.append(
            (
                bool(prod["ice_mask"][k]),
                bool(prod["qden_floor"][k]),
                bool(prod["ratio_floor"][k]),
                bool(prod["rslope_lower"][k]),
                bool(prod["rslope_upper"][k]),
                bool(prod["vt_i_zero"][k]),
                cap_winner(parts["qtry"][k], q[k]),
                cap_winner(parts["ntry"][k], n[k]),
                bool(parts["d1_active"][k]),
                bool(a["active"][k]),
                bool(a["too_small"][k]),
                bool(a["too_large"][k]),
                bool(b["active"][k]),
                bool(b["too_small"][k]),
                bool(b["too_large"][k]),
            )
        )
    return tuple(out)


def seed(q0: torch.Tensor, name: str) -> torch.Tensor:
    tangent = torch.zeros_like(q0)
    if name in ("relative_qi16", "relative_qi16_qi23"):
        tangent[L16] = q0[L16]
    if name in ("relative_qi23", "relative_qi16_qi23"):
        tangent[L23] = q0[L23]
    return tangent


def analytic(q0: torch.Tensor, n0: torch.Tensor, op: dict, fixed: dict) -> dict:
    """Sparse source-order expectations on the audited open caps and snap branches."""
    zero = [0.0] * len(OUTPUTS)
    q16 = zero.copy()
    fall_rate16 = (
        ((op["dend"][L16].item() * q0[L16].item()) * op["work1_qi"][L16].item())
        / op["mstep"][L16].item()
    ) * op["gate"][L16].item()
    out16 = (fall_rate16 * op["dtcld"][L16].item()) / op["dend_safe"][L16].item()
    arrived = (out16 * (op["dend_safe"][L16].item() * op["delz"][L16].item())) / (
        op["dend_safe"][L15].item() * op["delz_safe"][L15].item()
    )
    q16[0] = arrived
    q16[4] = -(350000.0 / fixed["cpm_safe"][L15].item()) * arrived
    kept16 = q0[L16].item() - out16
    q16[6] = (op["dend"][L16].item() * (9080.0**3) / 1570.79638671875) * kept16
    q23 = zero.copy()
    alpha = 0.3333333432674408
    out23 = (
        alpha * n0[L23].item() * op["workn_qi"][L23].item() * op["dtcld"][L23].item()
    )
    q23[7] = out23 * op["delz_safe"][L23].item() / op["delz_safe"][L22].item()
    q23[8] = -out23
    return {
        "relative_qi16": q16,
        "relative_qi23": q23,
        "relative_qi16_qi23": [a + b for a, b in zip(q16, q23, strict=True)],
    }


def replay() -> dict:
    d1, speed, fields, q0, n0, op, fixed, source = load()
    params = speed.default_slope_params()
    fixed_out, fixed_parts = chain(
        q0, n0, speed, op, fixed, params, dynamic=False, diagnostic=True
    )
    fixed_check = raw_baseline(d1, fields, fixed_parts, fixed_out)
    dynamic_out, base_parts = chain(
        q0, n0, speed, op, fixed, params, dynamic=True, diagnostic=True
    )
    speed_relative = {}
    for k in (L16, L23):
        for name, got in (
            ("work1_qi", base_parts["wq"]),
            ("workn_qi", base_parts["wn"]),
        ):
            recorded = op[name][k].item()
            relative = abs(got[k].item() - recorded) / max(abs(recorded), 1e-30)
            need(relative <= 1e-12, "active speed baseline")
            speed_relative[f"{39 - k}:{name}"] = relative
    max_c3 = max(
        abs(base_parts["nb"][k].item() - fixed_parts["nb"][k].item()) for k in range(K)
    )
    need(max_c3 <= 1e-8, "dynamic-speed C3 baseline difference")
    need(
        abs(base_parts["qsed"][L15].item() - fixed_parts["qsed"][L15].item())
        <= 1e-12 * fixed_parts["qsed"][L15].item(),
        "dynamic D1-input QI15",
    )
    base_sig = signature(base_parts, q0, n0)
    need(
        q0[L15].item() == 0.0 and base_sig[0][6] == "tie", "native15 zero-departure tie"
    )
    need(
        bool(base_parts["d1_active"][L15])
        and not bool(base_parts["a_diag"]["active"][L15]),
        "native15 D1/snap-A gates",
    )
    need(
        bool(base_parts["producer"]["rslope_lower"][L16])
        and bool(base_parts["a_diag"]["too_small"][L16])
        and bool(base_parts["b_diag"]["active"][L16])
        and not bool(base_parts["b_diag"]["too_small"][L16]),
        "native16 slope/snap branches",
    )
    expected = analytic(q0, n0, op, fixed)
    weights = torch.tensor(
        (2.0, -3.0, 5.0, 7.0, 11.0, 13.0, 17.0, 19.0, 23.0), dtype=torch.float64
    )

    def map_output(q: torch.Tensor) -> torch.Tensor:
        return chain(q, n0, speed, op, fixed, params, dynamic=True)[0]

    _, pullback = torch.func.vjp(map_output, q0)
    adjoint = pullback(weights)[0]
    directions = {}
    for name in SEEDS:
        tangent = seed(q0, name)
        _, jvp = torch.func.jvp(map_output, (q0,), (tangent,))
        target = torch.tensor(expected[name], dtype=torch.float64)
        need(
            torch.allclose(jvp, target, atol=1e-20, rtol=1e-11),
            "analytic full-chain JVP: " + name,
        )
        dot_vjp = torch.dot(adjoint, tangent).item()
        dot_jvp = torch.dot(weights, jvp).item()
        need(
            abs(dot_vjp - dot_jvp) <= 2e-12 * max(1.0, abs(dot_jvp)),
            "VJP transpose: " + name,
        )
        endpoints = {}
        for h in (1e-3, 1e-4, 1e-5):
            plus = q0.clone()
            minus = q0.clone()
            gaps = {}
            for level, k in ((16, L16), (23, L23)):
                if tangent[k].item() == 0:
                    continue
                plus[k] = q0[k] * (1.0 + h)
                minus[k] = q0[k] * (1.0 - h)
                gaps[str(level)] = (plus[k].item() - minus[k].item()) / q0[k].item()
            ref_gap = gaps["16"] if "16" in gaps else gaps["23"]
            p_out, p_parts = chain(
                plus, n0, speed, op, fixed, params, dynamic=True, diagnostic=True
            )
            m_out, m_parts = chain(
                minus, n0, speed, op, fixed, params, dynamic=True, diagnostic=True
            )
            need(
                signature(p_parts, plus, n0) == base_sig
                and signature(m_parts, minus, n0) == base_sig,
                "branch-preserving endpoints: " + name,
            )
            need(
                bool(p_parts["d1_active"][L15])
                and bool(m_parts["d1_active"][L15])
                and p_parts["qi_d1"][L15].item() == 0.0
                and m_parts["qi_d1"][L15].item() == 0.0,
                "D1 complete-melt endpoints",
            )
            fd = (p_out - m_out) / ref_gap
            represented_expected = (
                torch.tensor(expected["relative_qi16"], dtype=torch.float64)
                if "16" in gaps
                else torch.zeros_like(jvp)
            )
            if "23" in gaps:
                represented_expected = represented_expected + (
                    gaps["23"] / ref_gap
                ) * torch.tensor(expected["relative_qi23"], dtype=torch.float64)
            normalized = torch.max(
                torch.abs(fd - represented_expected)
                / torch.maximum(torch.ones_like(jvp), torch.abs(jvp))
            ).item()
            bound = 0.25 * h * h + (3e-8 if h == 1e-5 else 0.0)
            need(normalized <= bound, "represented-gap full-chain FD: " + name)
            if "16" in gaps:
                for i in (0, 4):
                    limit = 2.0 * math.ulp(dynamic_out[i].item()) / ref_gap + 1e-23
                    need(
                        abs(fd[i].item() - represented_expected[i].item()) <= limit,
                        "D1 QC/T FD resolution: " + name,
                    )
            endpoints[str(h)] = {
                "represented_input_gaps": gaps,
                "output_difference": (p_out - m_out).tolist(),
                "output_ulp": [math.ulp(x) for x in dynamic_out.tolist()],
                "fd": fd.tolist(),
                "fd_minus_jvp": (fd - jvp).tolist(),
                "max_normalized_fd_residual": normalized,
                "acceptance_bound": bound,
            }
        directions[name] = {
            "jvp": jvp.tolist(),
            "analytic": expected[name],
            "weighted_vjp_contraction": dot_vjp,
            "weighted_jvp_contraction": dot_jvp,
            "finite_differences": endpoints,
        }

    def speed_q16(x: torch.Tensor) -> torch.Tensor:
        return speed.ice_speeds(x, n0, op["den"], op["dend"], op["delz_safe"], params)[
            0
        ][L16]

    _, w16_jvp = torch.func.jvp(speed_q16, (q0,), (seed(q0, "relative_qi16"),))
    need(w16_jvp.item() == 0.0, "native16 slope-clamped speed derivative")
    result = {
        "schema": "kdm6.native_d1_speed_chain_conditional_ad.v1",
        "source_attribution": source,
        "parent_d1_result_sha256": D1_RESULT_SHA,
        "parent_speed_result_sha256": SPEED_RESULT_SHA,
        "baseline_fixed_speed": fixed_check,
        "baseline_dynamic_speed_max_c3_ni_abs": max_c3,
        "baseline_selected_speed_relative_difference": speed_relative,
        "baseline_selected_outputs": dynamic_out.tolist(),
        "output_order": list(OUTPUTS),
        "input_directions": directions,
        "native16_relative_speed_jvp": w16_jvp.item(),
        "branch_signature_selected_15_16_22_23": base_sig,
        "fixed_operands": [
            "DEN/DEND",
            "DELZ",
            "dtcld/mstep/gate",
            "D1 entry T/QC/NC",
            "D1 cpm_safe/psmlt_capped/pgmlt_capped",
            "homogeneous mask",
            "D2-D4 applied QI/NI amounts",
            "other hydrometeors and batch schedule",
        ],
        "native_full_process_derivative_certified": False,
        "scientific_status": "INCONCLUSIVE",
        "physical_unit_status": "INCONCLUSIVE",
    }
    saved_raw = (HERE / "results.json").read_bytes()
    need(sha(saved_raw) == SAVED_SHA, "saved conditional chain result SHA-256")
    saved = json.loads(saved_raw)
    for key in (
        "schema",
        "parent_d1_result_sha256",
        "parent_speed_result_sha256",
        "baseline_fixed_speed",
        "output_order",
        "fixed_operands",
        "native_full_process_derivative_certified",
        "scientific_status",
        "physical_unit_status",
    ):
        need(saved[key] == result[key], "stable conditional chain result: " + key)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = replay()
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print("NATIVE_QNICE_D1_SPEED_CHAIN_AD_REPLAY_PASSED")
        print(
            json.dumps(
                {
                    "schema": result["schema"],
                    "baseline_fixed_speed": result["baseline_fixed_speed"],
                    "scientific_status": result["scientific_status"],
                },
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
