#!/usr/bin/env python3
"""Conditional native D1 QV→heat-capacity→temperature derivative replay."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import struct
import sys

import torch


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from oracle.kdm6.thermo import compute_cpm, default_thermo_params  # noqa: E402


PARENT = REPO / "harness/evidence/native_qnice_d1_chain_ad_2026-11-04"
THERMO_SNAPSHOT = (
    REPO
    / "harness/evidence/native_qnice_ice_speed_ad_2026-11-03/source_snapshots/oracle_thermo.py.txt"
)
PARENT_SOURCE_SHA = "6d29a147f3ae64c056c2733fe880421e304ef017727240a28770fde0fcc200e2"
PARENT_RESULT_SHA = "7be5905393872125c5ada6d823e466d44c2b732164e157be18b4fd9c19ba6de2"
THERMO_SHA = "5278c14c6d87178af5ee963eef59d3297b923fa374412fd854c01e43ffb1b5cd"
SAVED_SHA = "fecd3cba739d3ac53082d32d66dda09244f157b80458f2ff3d8f56ccdf31574e"
L15 = 39 - 15


def need(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError(why)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def word(value: float) -> str:
    return format(int.from_bytes(struct.pack("<d", value), "little"), "x")


def load_parent():
    source = PARENT / "replay.py"
    need(sha(source.read_bytes()) == PARENT_SOURCE_SHA, "parent chain source SHA-256")
    saved_raw = (PARENT / "results.json").read_bytes()
    need(sha(saved_raw) == PARENT_RESULT_SHA, "parent chain result SHA-256")
    spec = importlib.util.spec_from_file_location(
        "native_d1_speed_chain_parent", source
    )
    need(spec is not None and spec.loader is not None, "parent chain import")
    parent = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parent)
    fresh = parent.replay()
    saved = json.loads(saved_raw)
    for name in (
        "schema",
        "baseline_fixed_speed",
        "output_order",
        "fixed_operands",
        "native_full_process_derivative_certified",
        "scientific_status",
    ):
        need(fresh[name] == saved[name], "parent chain stable result: " + name)
    need(
        sha(THERMO_SNAPSHOT.read_bytes()) == THERMO_SHA
        and sha((REPO / "oracle/kdm6/thermo.py").read_bytes()) == THERMO_SHA,
        "executed oracle thermo source",
    )
    return parent, saved


def verify_qv_handoff(fields: dict) -> int:
    for k in range(39):
        need(
            fields[("runtime_entry_pre_clamp", "qv", k)]["raw_hex"]
            == fields[("c3_pre_mf_d1", "qv_before", k)]["raw_hex"],
            "runtime-to-D1 QV raw handoff",
        )
    return 39


def baseline():
    parent, saved = load_parent()
    d1, speed, fields, q0, n0, op, fixed, source = parent.load()
    params = speed.default_slope_params()
    thermo = default_thermo_params()
    need(
        thermo.cpd == 1004.5 and thermo.cpv == 1846.4 and thermo.qmin == 1e-15,
        "cpm source constants",
    )
    qv0 = torch.tensor(
        [d1.get(fields, "c3_pre_mf_d1", "qv_before", k) for k in range(39)],
        dtype=torch.float64,
    )
    verify_qv_handoff(fields)
    cpm = compute_cpm(qv0, params=thermo)
    safe = torch.clamp(cpm, min=1e-9)
    for k in range(39):
        need(
            word(cpm[k].item()) == fields[("c3_pre_mf_d1", "pre_cpm", k)]["raw_hex"],
            "QV→pre.cpm raw bits",
        )
        need(
            word(safe[k].item()) == fields[("c3_pre_mf_d1", "cpm_safe", k)]["raw_hex"],
            "pre.cpm→cpm_safe raw bits",
        )
    reconstructed = dict(fixed, cpm_safe=safe)
    fixed_out, fixed_parts = parent.chain(
        q0, n0, speed, op, reconstructed, params, dynamic=False, diagnostic=True
    )
    parent.raw_baseline(d1, fields, fixed_parts, fixed_out)
    dynamic_out, dynamic_parts = parent.chain(
        q0, n0, speed, op, reconstructed, params, dynamic=True, diagnostic=True
    )
    original_out, original_parts = parent.chain(
        q0, n0, speed, op, fixed, params, dynamic=True, diagnostic=True
    )
    need(
        torch.equal(dynamic_out, original_out),
        "new cpm producer leaves baseline outputs unchanged",
    )
    need(
        parent.signature(dynamic_parts, q0, n0)
        == parent.signature(original_parts, q0, n0),
        "baseline branch signature",
    )
    need(
        saved["baseline_fixed_speed"]["raw_bit_matches_per_field"] == 39,
        "parent baseline field inventory",
    )
    return (
        parent,
        d1,
        speed,
        fields,
        q0,
        n0,
        op,
        fixed,
        params,
        thermo,
        qv0,
        cpm,
        dynamic_out,
    )


def replay() -> dict:
    (
        parent,
        d1,
        speed,
        fields,
        q0,
        n0,
        op,
        fixed,
        params,
        thermo,
        qv0,
        cpm0,
        baseline_out,
    ) = baseline()

    def make_fixed(qv: torch.Tensor) -> dict:
        return dict(
            fixed, cpm_safe=torch.clamp(compute_cpm(qv, params=thermo), min=1e-9)
        )

    def output(qv: torch.Tensor) -> torch.Tensor:
        return parent.chain(q0, n0, speed, op, make_fixed(qv), params, dynamic=True)[0]

    tangent = torch.zeros_like(qv0)
    tangent[L15] = qv0[L15]
    _, jvp = torch.func.jvp(output, (qv0,), (tangent,))
    _, cpm_jvp = torch.func.jvp(
        lambda qv: compute_cpm(qv, params=thermo)[L15], (qv0,), (tangent,)
    )
    qv15 = qv0[L15].item()
    cp15 = cpm0[L15].item()
    melt = d1.get(fields, "c3_pre_mf_d1", "pimlt_qi", L15)
    need(
        melt > 0
        and d1.get(fields, "c3_pre_mf_d1", "psmlt_capped", L15) == 0
        and d1.get(fields, "c3_pre_mf_d1", "pgmlt_capped", L15) == 0,
        "isolated level15 ice-melt heat term",
    )
    dcpm = (thermo.cpv - thermo.cpd) * qv15
    expected_t = 350000.0 * melt * dcpm / (cp15 * cp15)
    expected = torch.zeros_like(jvp)
    expected[4] = expected_t
    need(abs(cpm_jvp.item() - dcpm) <= 1e-13 * abs(dcpm), "independent cpm JVP")
    need(
        torch.allclose(jvp, expected, rtol=1e-12, atol=1e-23),
        "independent QV→cpm→T JVP",
    )
    weights = torch.tensor(
        (2.0, -3.0, 5.0, 7.0, 11.0, 13.0, 17.0, 19.0, 23.0), dtype=torch.float64
    )
    _, pullback = torch.func.vjp(output, qv0)
    cotangent = pullback(weights)[0]
    weighted_vjp = torch.dot(cotangent, tangent).item()
    weighted_jvp = torch.dot(weights, jvp).item()
    need(
        abs(weighted_vjp - weighted_jvp) <= max(1e-21, 1e-12 * abs(weighted_jvp)),
        "QV weighted VJP transpose",
    )
    base_sig = parent.signature(
        parent.chain(
            q0, n0, speed, op, make_fixed(qv0), params, dynamic=True, diagnostic=True
        )[1],
        q0,
        n0,
    )
    need(
        qv15 > thermo.qmin and cp15 > 1e-9 and base_sig[0][8],
        "baseline QV/cpm floor and D1 melt gate",
    )
    finite_differences = {}
    for h in (0.25, 0.1, 0.05, 0.01):
        plus = qv0.clone()
        minus = qv0.clone()
        plus[L15] = qv0[L15] * (1.0 + h)
        minus[L15] = qv0[L15] * (1.0 - h)
        represented_gap = (plus[L15].item() - minus[L15].item()) / qv15
        need(
            plus[L15].item() > thermo.qmin and minus[L15].item() > thermo.qmin,
            "QV finite-difference floor",
        )
        high, high_parts = parent.chain(
            q0, n0, speed, op, make_fixed(plus), params, dynamic=True, diagnostic=True
        )
        low, low_parts = parent.chain(
            q0, n0, speed, op, make_fixed(minus), params, dynamic=True, diagnostic=True
        )
        need(
            parent.signature(high_parts, q0, n0) == base_sig
            and parent.signature(low_parts, q0, n0) == base_sig,
            "QV endpoint branch signature",
        )
        change = high - low
        fd = change / represented_gap
        need(
            all(fd[i].item() == 0.0 for i in range(len(fd)) if i != 4),
            "QV direction changes only selected D1 temperature",
        )
        ratio = dcpm / cp15
        curvature = 4.0 * abs(expected_t) * (ratio * h) ** 2
        resolution = 2.0 * math.ulp(baseline_out[4].item()) / represented_gap
        need(
            abs(fd[4].item() - expected_t) <= curvature + resolution,
            "QV represented-gap T difference",
        )
        finite_differences[str(h)] = {
            "represented_relative_input_gap": represented_gap,
            "output_difference": change.tolist(),
            "output_ulp": [math.ulp(x) for x in baseline_out.tolist()],
            "temperature_signal_ulps": abs(change[4].item())
            / math.ulp(baseline_out[4].item()),
            "fd": fd.tolist(),
            "fd_minus_jvp": (fd - jvp).tolist(),
            "temperature_acceptance_bound": curvature + resolution,
        }
    next_qv = torch.tensor(math.nextafter(qv15, math.inf), dtype=torch.float64)
    next_cpm = compute_cpm(next_qv, params=thermo)
    need(word(next_cpm.item()) == word(cp15), "adjacent QV cpm rounding collision")
    result = {
        "schema": "kdm6.native_d1_qv_cpm_conditional_ad.v1",
        "parent_chain_result_sha256": PARENT_RESULT_SHA,
        "baseline_runtime_to_D1_qv_raw_bit_matches": 39,
        "baseline_cpm_raw_bit_matches": 39,
        "baseline_cpm_safe_raw_bit_matches": 39,
        "baseline_no_splice_raw_bit_matches_per_field": 39,
        "baseline_outputs": baseline_out.tolist(),
        "output_order": list(parent.OUTPUTS),
        "direction": "relative_D1_input_QV15",
        "qv15": qv15,
        "cpm15": cp15,
        "cpm_relative_jvp": cpm_jvp.item(),
        "independent_cpm_relative_jvp": dcpm,
        "jvp": jvp.tolist(),
        "independent_jvp": expected.tolist(),
        "weighted_vjp_contraction": weighted_vjp,
        "weighted_jvp_contraction": weighted_jvp,
        "finite_differences": finite_differences,
        "adjacent_qv_has_same_rounded_cpm": True,
        "fixed_operands": [
            "sedimentation entry QI/NI and ice-speed source inputs",
            "density, depth, timing and one-substep gates",
            "D1 entry T/QC/NC and ice-melt amount",
            "D1 capped snow/graupel amounts and other rates",
            "homogeneous mask and D2-D4 applied amounts",
        ],
        "native_full_process_derivative_certified": False,
        "scientific_status": "INCONCLUSIVE",
        "physical_unit_status": "INCONCLUSIVE",
    }
    saved_raw = (HERE / "results.json").read_bytes()
    need(sha(saved_raw) == SAVED_SHA, "saved QV→cpm result SHA-256")
    saved = json.loads(saved_raw)
    for name in (
        "schema",
        "parent_chain_result_sha256",
        "baseline_runtime_to_D1_qv_raw_bit_matches",
        "baseline_cpm_raw_bit_matches",
        "baseline_cpm_safe_raw_bit_matches",
        "baseline_no_splice_raw_bit_matches_per_field",
        "output_order",
        "direction",
        "fixed_operands",
        "native_full_process_derivative_certified",
        "scientific_status",
        "physical_unit_status",
    ):
        need(saved[name] == result[name], "stable QV→cpm result: " + name)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = replay()
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print("NATIVE_QNICE_D1_CPM_AD_REPLAY_PASSED")
        print(
            json.dumps(
                {
                    "schema": result["schema"],
                    "jvp_T15": result["jvp"][4],
                    "scientific_status": result["scientific_status"],
                },
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
