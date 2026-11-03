"""Pinned, conditional replay and local AD for native ice-number snap A."""

from __future__ import annotations

import csv
from fractions import Fraction
import hashlib
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

from oracle.kdm6 import constants as c  # noqa: E402 - repo path for direct CLI
from oracle.kdm6 import fconst as fc  # noqa: E402 - repo path for direct CLI
from oracle.kdm6.coordinator import _limit_number_for_lamda  # noqa: E402


PARENT = REPO / "harness/evidence/native_qnice_39_applied_2026-11-03"
CAPTURE = PARENT / "raw/native_qnice_applied_30339_runtime2.csv"
PARENT_RESULT = PARENT / "raw/initial_analysis.json"
EXECUTED_COORDINATOR = PARENT / "executed_cpp/coordinator.cpp"
SAVED_RESULTS = HERE / "results.json"
CAPTURE_SHA256 = "27b89eb5b38b88174f55188be7d724cd74df8e6577c034a044581c78b3dff3bf"
PARENT_RESULT_SHA256 = (
    "39f351dd4d52d1fbfaf6a9636290c5fc8d7efab7006322dc0ad81ce85138d6b7"
)
EXECUTED_COORDINATOR_SHA256 = (
    "a67570b2b4a0fcc3f359392616c5ba146669afac1206fc095d27b43a5214dd00"
)
SAVED_RESULTS_SHA256 = (
    "606cc9919e0748d5df4a04723c403ebccf72815333c20672ae7c3eb3ef42e284"
)
SOURCE_SNAPSHOT_PINS = {
    "cpp_fconst.h.txt": "0bd277fe788a0b334441c9295fdcef8d0cb8f8eefd9ce5d98172b4cef63aba1d",
    "oracle_constants.py.txt": "aa489872c2b00d1160e158b9390ebe7bdcbbe4b31a468673cf22615f137f1b62",
    "oracle_coordinator.py.txt": "05981b7a19c8d4fe262cb8080b14ddf3b4eb5c027b58604803b2e0b80764a0bd",
    "oracle_fconst.py.txt": "c6529c9a543ad8ed0a33524114f30f5665cd9a7b6983b32a917cc39debd377f2",
}
LIVE_SOURCE_PATHS = {
    "oracle_coordinator.py.txt": REPO / "oracle/kdm6/coordinator.py",
    "oracle_fconst.py.txt": REPO / "oracle/kdm6/fconst.py",
    "oracle_constants.py.txt": REPO / "oracle/kdm6/constants.py",
    "cpp_fconst.h.txt": REPO / "libtorch/include/kdm6/fconst.h",
}
PIDNI_F32_BITS = "44c4597c"
PIDNI = 1570.79638671875
INV_DMI_F32 = 0.3333333432674408
Q_GATE = 1.0e-14
EPS = 1.0e-30
LEVELS = (25, 20, 19, 18, 17, 16)
STAGE = "c3_pre_snap_a"
FIELDS = (
    "qi",
    "ni_before",
    "dend",
    "ni_after",
    "lambda_raw",
    "lambda_clamped",
    "gate_qi_ge_1e14",
    "gate_ni_ge_zero",
)
H_VALUES = (1.0e-3, 1.0e-4, 1.0e-5)


def need(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def raw_word(value: float, dtype: str = "f64") -> str:
    fmt = "<d" if dtype == "f64" else "<f"
    integer = "<Q" if dtype == "f64" else "<I"
    return format(struct.unpack(integer, struct.pack(fmt, value))[0], "x")


def decoded_word(word: str, dtype: str) -> float:
    size = 8 if dtype == "f64" else 4
    bits = int(word, 16)
    need(0 <= bits < 1 << (8 * size), "raw word width")
    value = struct.unpack(
        "<d" if dtype == "f64" else "<f", bits.to_bytes(size, "little")
    )[0]
    need(math.isfinite(value), "finite raw word")
    return value


def pinned_bytes(path: Path, expected: str) -> bytes:
    raw = path.read_bytes()
    need(
        hashlib.sha256(raw).hexdigest() == expected,
        "parent source/result SHA-256: " + path.name,
    )
    return raw


def source_constants() -> None:
    need(
        raw_word(fc.PIDNI, "f32") == PIDNI_F32_BITS
        and fc.PIDNI == PIDNI
        and c.DMI == 3.0
        and c.LAMDAIMIN == 9080.0
        and c.LAMDAIMAX == 1.82e6
        and decoded_word(raw_word(1.0 / 3.0, "f32"), "f32") == INV_DMI_F32,
        "f32-derived source constants",
    )


def source_snapshots() -> dict:
    for name, expected in SOURCE_SNAPSHOT_PINS.items():
        pinned_bytes(HERE / "source_snapshots" / name, expected)
    live = {
        name: hashlib.sha256(path.read_bytes()).hexdigest()
        for name, path in LIVE_SOURCE_PATHS.items()
    }
    return {
        "archived_sha256": SOURCE_SNAPSHOT_PINS.copy(),
        "current_checkout_sha256": live,
        "current_checkout_equal_to_archived": {
            name: live[name] == expected
            for name, expected in SOURCE_SNAPSHOT_PINS.items()
        },
    }


def parent_rows() -> tuple[dict[int, dict], dict[int, float], dict]:
    """Read the exact parent CSV bytes and extract the eight snap-A fields."""
    raw = pinned_bytes(CAPTURE, CAPTURE_SHA256)
    parent_result = json.loads(pinned_bytes(PARENT_RESULT, PARENT_RESULT_SHA256))
    pinned_bytes(EXECUTED_COORDINATOR, EXECUTED_COORDINATOR_SHA256)
    lines = raw.decode("ascii").splitlines()
    need(
        len(lines) == 2773 and lines[-1] == "# native_rows=2769,status=complete",
        "parent complete capture",
    )
    reader = csv.DictReader(line for line in lines if not line.startswith("#"))
    need(
        reader.fieldnames
        == "one_step_call,runtime_call,substep,b_zero,k_zero,B,K,stage,field,dtype,raw_hex".split(
            ","
        ),
        "parent CSV columns",
    )
    selected: dict[int, dict] = {k: {} for k in range(39)}
    dz: dict[int, float] = {}
    for row in reader:
        if row["stage"] == STAGE:
            need(
                (
                    row["one_step_call"],
                    row["runtime_call"],
                    row["substep"],
                    row["b_zero"],
                    row["B"],
                    row["K"],
                )
                == ("2", "2", "0", "22617", "32248", "39"),
                "snap A call identity",
            )
            k = int(row["k_zero"])
            need(
                0 <= k < 39
                and row["field"] in FIELDS
                and row["field"] not in selected[k],
                "snap A field/level inventory",
            )
            expected_type = "bool" if row["field"].startswith("gate_") else "f64"
            need(row["dtype"] == expected_type, "snap A field dtype")
            selected[k][row["field"]] = row["raw_hex"]
        if (
            row["stage"] == "ice_sedimentation_conservative_n1"
            and row["field"] == "delz"
        ):
            k = int(row["k_zero"])
            need(k not in dz and row["dtype"] == "f64", "DELZ inventory")
            dz[k] = decoded_word(row["raw_hex"], "f64")
    need(
        all(set(rows) == set(FIELDS) for rows in selected.values())
        and set(dz) == set(range(39)),
        "complete 39-level snap A/DELZ records",
    )
    return selected, dz, parent_result


def scalar_branch(q: float, n: float, den: float) -> dict:
    """Independent scalar rendition of the executed C++ source order."""
    active = q >= Q_GATE and n >= 0.0
    qden_raw = q * den
    qden = max(qden_raw, EPS)
    ratio_raw = PIDNI * n / qden
    ratio = max(ratio_raw, EPS)
    lamda = math.exp(math.log(ratio) * INV_DMI_F32)
    low = active and lamda <= c.LAMDAIMIN
    high = active and lamda >= c.LAMDAIMAX and not low
    output = (
        den * q * math.pow(c.LAMDAIMIN, c.DMI) / PIDNI
        if low
        else den * q * math.pow(c.LAMDAIMAX, c.DMI) / PIDNI
        if high
        else n
    )
    return {
        "active": active,
        "low": low,
        "high": high,
        "qden_raw": qden_raw,
        "ratio_raw": ratio_raw,
        "qden_floor": qden_raw <= EPS,
        "ratio_floor": ratio_raw <= EPS,
        "lambda_raw": lamda,
        "lambda_clamped": max(c.LAMDAIMIN, min(lamda, c.LAMDAIMAX)),
        "output": output,
        "q_gate_margin": q - Q_GATE,
        "n_gate_margin": n,
        "lambda_low_margin": c.LAMDAIMIN - lamda,
        "lambda_high_margin": c.LAMDAIMAX - lamda,
    }


def strict_low_branch(q: float, n: float, den: float, *, ni_interior: bool) -> bool:
    branch = scalar_branch(q, n, den)
    return (
        branch["active"]
        and branch["low"]
        and not branch["high"]
        and q > Q_GATE
        and n >= 0.0
        and (not ni_interior or n > 0.0)
        and branch["lambda_raw"] < c.LAMDAIMIN
        and branch["qden_raw"] > EPS
        and branch["ratio_raw"] != EPS
    )


def torch_map(
    q: torch.Tensor, n: torch.Tensor, den: torch.Tensor, diagnostic: dict | None = None
) -> torch.Tensor:
    return _limit_number_for_lamda(
        q,
        n,
        den,
        pidn=fc.PIDNI,
        dm=c.DMI,
        lamda_min=c.LAMDAIMIN,
        lamda_max=c.LAMDAIMAX,
        q_thresh=Q_GATE,
        n_thresh=0.0,
        diagnostic=diagnostic,
    )


def branch_signature(
    q: torch.Tensor, n: torch.Tensor, den: torch.Tensor
) -> tuple[tuple[bool, ...], ...]:
    return tuple(
        tuple(
            scalar_branch(q[i].item(), n[i].item(), den[i].item())[key]
            for key in ("active", "low", "high", "qden_floor", "ratio_floor")
        )
        for i in range(len(q))
    )


def replay() -> dict:
    source_constants()
    sources = source_snapshots()
    rows, dz, parent_result = parent_rows()
    q_all = torch.tensor(
        [decoded_word(rows[k]["qi"], "f64") for k in range(39)], dtype=torch.float64
    )
    n_all = torch.tensor(
        [decoded_word(rows[k]["ni_before"], "f64") for k in range(39)],
        dtype=torch.float64,
    )
    d_all = torch.tensor(
        [decoded_word(rows[k]["dend"], "f64") for k in range(39)], dtype=torch.float64
    )
    diagnostic: dict = {}
    oracle_out = torch_map(q_all, n_all, d_all, diagnostic)
    selected = []
    changed = []
    weighted_delta = Fraction()
    lambda_raw_bit_matches = 0
    lambda_max_relative_difference = 0.0
    for k in range(39):
        raw = rows[k]
        q, n, den = (x[k].item() for x in (q_all, n_all, d_all))
        independent = scalar_branch(q, n, den)
        need(
            raw_word(independent["output"]) == raw["ni_after"]
            and raw_word(oracle_out[k].item()) == raw["ni_after"],
            "source-order scalar and oracle NI raw bits",
        )
        need(
            int(raw["gate_qi_ge_1e14"], 16) == int(q >= Q_GATE)
            and int(raw["gate_ni_ge_zero"], 16) == int(n >= 0.0),
            "captured source gates",
        )
        captured_lambda = decoded_word(raw["lambda_raw"], "f64")
        captured_active = bool(int(raw["gate_qi_ge_1e14"], 16)) and bool(
            int(raw["gate_ni_ge_zero"], 16)
        )
        captured_low = captured_active and captured_lambda <= c.LAMDAIMIN
        captured_high = (
            captured_active and not captured_low and captured_lambda >= c.LAMDAIMAX
        )
        need(
            (captured_active, captured_low, captured_high)
            == (independent["active"], independent["low"], independent["high"])
            and raw_word(max(c.LAMDAIMIN, min(captured_lambda, c.LAMDAIMAX)))
            == raw["lambda_clamped"],
            "captured-gate/lambda inferred branch",
        )
        for field, value in (
            ("lambda_raw", independent["lambda_raw"]),
            ("lambda_clamped", independent["lambda_clamped"]),
        ):
            captured = decoded_word(raw[field], "f64")
            if field == "lambda_raw":
                lambda_raw_bit_matches += raw_word(value) == raw[field]
                lambda_max_relative_difference = max(
                    lambda_max_relative_difference,
                    abs(value - captured) / abs(captured),
                )
            need(
                math.isclose(value, captured, rel_tol=1.0e-12, abs_tol=0.0),
                "independent lambda branch value",
            )
        need(
            bool(diagnostic["active"][k]) == independent["active"]
            and bool(diagnostic["too_small"][k]) == independent["low"]
            and bool(diagnostic["too_large"][k]) == independent["high"],
            "oracle/scalar branch selection",
        )
        before = n
        after = decoded_word(raw["ni_after"], "f64")
        if raw_word(before) != raw["ni_after"]:
            changed.append(39 - k)
        weighted_delta += Fraction.from_float(dz[k]) * (
            Fraction.from_float(after) - Fraction.from_float(before)
        )
        if 39 - k in LEVELS:
            selected.append(
                {
                    "native_level_1based": 39 - k,
                    "q": q,
                    "ni_before": n,
                    "dend": den,
                    "ni_after": after,
                    "lambda_raw": decoded_word(raw["lambda_raw"], "f64"),
                    "q_gate_margin": independent["q_gate_margin"],
                    "n_gate_margin": independent["n_gate_margin"],
                    "lambda_low_margin": c.LAMDAIMIN - captured_lambda,
                    "ratio_floor_active": independent["ratio_floor"],
                    "ni_two_sided_branch_interior": n > 0.0,
                }
            )
    need(
        changed == list(LEVELS)
        and float(weighted_delta)
        == parent_result["pre_c3_ni_changes"]["snap_a"]["weighted_ni_dz_change"],
        "six-level applied rewrite and parent weighted delta",
    )

    indices = [39 - j for j in LEVELS]
    q = q_all[indices].detach()
    n = n_all[indices].detach()
    d = d_all[indices].detach()
    baseline_signature = branch_signature(q, n, d)
    need(
        all(
            sig[0]
            and sig[1]
            and not sig[2]
            and not sig[3]
            and strict_low_branch(
                q[i].item(), n[i].item(), d[i].item(), ni_interior=i == 1
            )
            for i, sig in enumerate(baseline_signature)
        ),
        "six strict low-snap branches",
    )
    need(
        all(n[i].item() == 0.0 for i in (0, 2, 3, 4, 5)) and n[1].item() > 0.0,
        "NI gate boundary classification",
    )
    zero = torch.zeros_like(q)
    ni20 = zero.clone()
    ni20[1] = n[1]
    directions = {
        "relative_q": (q, zero, zero),
        "relative_dend": (zero, zero, d),
        "relative_ni_level20": (zero, ni20, zero),
    }
    baseline = torch_map(q, n, d).detach()
    derivative = {}
    for name, seed in directions.items():
        jvp = torch.autograd.functional.jvp(torch_map, (q, n, d), seed)[1]
        if name == "relative_ni_level20":
            need(torch.count_nonzero(jvp).item() == 0, "strict-interior NI direct JVP")
        else:
            need(
                torch.allclose(jvp, baseline, atol=0.0, rtol=1.0e-13),
                "independent low-snap relative derivative",
            )
        fd_records = []
        for h in H_VALUES:
            plus = tuple(x + h * v for x, v in zip((q, n, d), seed))
            minus = tuple(x - h * v for x, v in zip((q, n, d), seed))
            need(
                branch_signature(*plus) == baseline_signature
                and branch_signature(*minus) == baseline_signature,
                "represented finite-difference endpoints retain branch",
            )
            for endpoint in (plus, minus):
                need(
                    all(
                        strict_low_branch(
                            endpoint[0][i].item(),
                            endpoint[1][i].item(),
                            endpoint[2][i].item(),
                            ni_interior=i == 1,
                        )
                        for i in range(len(q))
                    ),
                    "represented endpoints retain strict branch margins",
                )
            y_plus, y_minus = torch_map(*plus).detach(), torch_map(*minus).detach()
            active_index = (
                0 if name == "relative_q" else 2 if name == "relative_dend" else 1
            )
            gap = plus[active_index] - minus[active_index]
            need(
                all(
                    gap[i].item() != 0.0
                    for i in range(len(q))
                    if seed[active_index][i].item() != 0.0
                ),
                "represented nonzero input interval",
            )
            actual = torch.where(
                seed[active_index] != 0,
                seed[active_index]
                * (y_plus - y_minus)
                / torch.where(gap != 0, gap, torch.ones_like(gap)),
                torch.zeros_like(gap),
            )
            max_error = torch.max(torch.abs(actual - jvp)).item()
            max_relative = torch.max(
                torch.abs(actual - jvp) / torch.clamp(torch.abs(jvp), min=1.0)
            ).item()
            need(
                max_error <= 5.0e-9 and max_relative <= 1.0e-10,
                "represented-input finite difference vs JVP",
            )
            fd_records.append(
                {
                    "h": h,
                    "max_abs_fd_minus_jvp": max_error,
                    "max_scaled_fd_minus_jvp": max_relative,
                    "input_plus": plus[active_index].tolist(),
                    "input_minus": minus[active_index].tolist(),
                    "actual_input_gap": gap.tolist(),
                    "output_plus": y_plus.tolist(),
                    "output_minus": y_minus.tolist(),
                    "actual_spacing_fd": actual.tolist(),
                    "branch_signature_plus": branch_signature(*plus),
                    "branch_signature_minus": branch_signature(*minus),
                    "min_output_signal_ulps": min(
                        abs(y_plus[i].item() - y_minus[i].item())
                        / math.ulp(baseline[i].item())
                        for i in range(6)
                        if seed[active_index][i].item() != 0.0
                    ),
                }
            )
        derivative[name] = {"jvp": jvp.tolist(), "finite_differences": fd_records}

    cotangent = torch.tensor((0.5, -0.3, 1.1, -0.7, 0.25, 0.9), dtype=torch.float64)
    q_leaf, n_leaf, d_leaf = (x.detach().requires_grad_(True) for x in (q, n, d))
    vjp = torch.autograd.grad(
        torch_map(q_leaf, n_leaf, d_leaf),
        (q_leaf, n_leaf, d_leaf),
        grad_outputs=cotangent,
    )
    coefficient = math.pow(c.LAMDAIMIN, c.DMI) / PIDNI
    analytic_q = cotangent * d * coefficient
    analytic_d = cotangent * q * coefficient
    need(
        torch.allclose(vjp[0], analytic_q, atol=1.0e-9, rtol=1.0e-12)
        and torch.allclose(vjp[2], analytic_d, atol=1.0e-15, rtol=1.0e-12)
        and vjp[1][1].item() == 0.0,
        "VJP and independent low-snap coefficient",
    )
    joint_seed = (q, ni20, -0.4 * d)
    joint_jvp = torch.autograd.functional.jvp(torch_map, (q, n, d), joint_seed)[1]
    dot_jvp = torch.dot(joint_jvp, cotangent).item()
    dot_vjp = sum(torch.dot(a, b).item() for a, b in zip(joint_seed, vjp))
    need(
        math.isclose(dot_jvp, dot_vjp, rel_tol=1.0e-12, abs_tol=1.0e-12),
        "JVP/VJP transpose identity",
    )
    result = {
        "schema": "kdm6.native_qnice_snap_a_local_ad.v1",
        "scientific_status": "INCONCLUSIVE",
        "physical_unit_status": "INCONCLUSIVE",
        "parent_capture_sha256": CAPTURE_SHA256,
        "source_attribution": sources,
        "oracle_under_test": "current checkout oracle.kdm6.coordinator._limit_number_for_lamda",
        "source_constants": {
            "pidni_f32_bits": PIDNI_F32_BITS,
            "pidni_widened_f64": PIDNI,
            "inverse_dmi_f32_widened_f64": INV_DMI_F32,
            "lambda_min": c.LAMDAIMIN,
            "lambda_max": c.LAMDAIMAX,
            "q_gate": Q_GATE,
        },
        "baseline_39_outputs_raw_bits_equal": True,
        "baseline_39_gates_and_branch_winners_equal": True,
        "lambda_raw_bit_matches_on_this_platform": lambda_raw_bit_matches,
        "lambda_raw_max_relative_difference": lambda_max_relative_difference,
        "changed_native_levels_1based": changed,
        "observed_weighted_ni_dz_delta": float(weighted_delta),
        "selected_levels": selected,
        "relative_directions": derivative,
        "branch_signature_baseline": baseline_signature,
        "ni_gate_boundary_levels_1based": [25, 19, 18, 17, 16],
        "cotangent": cotangent.tolist(),
        "vjp_q": vjp[0].tolist(),
        "vjp_ni_level20": vjp[1][1].item(),
        "vjp_dend": vjp[2].tolist(),
        "joint_jvp_dot_cotangent": dot_jvp,
        "joint_seed_dot_vjp": dot_vjp,
        "zero_ni_levels_two_sided_ni_derivative_claimed": False,
        "full_host_or_rttov_derivative_certified": False,
    }
    saved = json.loads(pinned_bytes(SAVED_RESULTS, SAVED_RESULTS_SHA256))
    for key in (
        "schema",
        "scientific_status",
        "physical_unit_status",
        "parent_capture_sha256",
        "oracle_under_test",
        "source_constants",
        "changed_native_levels_1based",
        "observed_weighted_ni_dz_delta",
        "selected_levels",
        "ni_gate_boundary_levels_1based",
        "zero_ni_levels_two_sided_ni_derivative_claimed",
        "full_host_or_rttov_derivative_certified",
    ):
        need(result[key] == saved[key], "saved snap-A reference: " + key)
    need(
        result["source_attribution"]["archived_sha256"]
        == saved["source_attribution"]["archived_sha256"],
        "saved archived source identities",
    )
    return result


if __name__ == "__main__":
    print(json.dumps(replay(), indent=2, sort_keys=True))
    print("NATIVE_QNICE_SNAP_A_LOCAL_AD_REPLAY_PASSED")
