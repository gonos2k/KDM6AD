"""Conditional fixed-operand sedimentation → snap A/B → C3 NI replay."""

from __future__ import annotations

import csv
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

from oracle.kdm6 import constants as c  # noqa: E402 - direct CLI repository root
from oracle.kdm6 import fconst as fc  # noqa: E402 - direct CLI repository root
from oracle.kdm6.coordinator import _limit_number_for_lamda  # noqa: E402


PARENT = REPO / "harness/evidence/native_qnice_39_applied_2026-11-03"
CAPTURE = PARENT / "raw/native_qnice_applied_30339_runtime2.csv"
PARENT_ANALYSIS = PARENT / "raw/initial_analysis.json"
CPP_CONSERVATIVE = PARENT / "executed_cpp/sedimentation_conservative.cpp"
CPP_COORDINATOR = PARENT / "executed_cpp/coordinator.cpp"
CAPTURE_SHA256 = "27b89eb5b38b88174f55188be7d724cd74df8e6577c034a044581c78b3dff3bf"
CAPTURE_PARENT_LINK_SHA256 = (
    "27b89eb5b38b88174f55188be7d724cd74df8e6577c034a044581c78b3dff3bf"
)
PARENT_ANALYSIS_SHA256 = (
    "39f351dd4d52d1fbfaf6a9636290c5fc8d7efab7006322dc0ad81ce85138d6b7"
)
CPP_CONSERVATIVE_SHA256 = (
    "5af3a1d5a95624c0cc9a0c71ba411c0777c97426ab721ad9771a3d0b202489f7"
)
CPP_COORDINATOR_SHA256 = (
    "a67570b2b4a0fcc3f359392616c5ba146669afac1206fc095d27b43a5214dd00"
)
SNAP_A_RESULT = REPO / "harness/evidence/native_qnice_snap_a_ad_2026-11-03/results.json"
SNAP_A_RESULT_SHA256 = (
    "606cc9919e0748d5df4a04723c403ebccf72815333c20672ae7c3eb3ef42e284"
)
ORACLE_SNAPSHOT_PINS = {
    "oracle_coordinator.py.txt": "05981b7a19c8d4fe262cb8080b14ddf3b4eb5c027b58604803b2e0b80764a0bd",
    "oracle_constants.py.txt": "aa489872c2b00d1160e158b9390ebe7bdcbbe4b31a468673cf22615f137f1b62",
    "oracle_fconst.py.txt": "c6529c9a543ad8ed0a33524114f30f5665cd9a7b6983b32a917cc39debd377f2",
}
LIVE_ORACLE_PATHS = {
    "oracle_coordinator.py.txt": REPO / "oracle/kdm6/coordinator.py",
    "oracle_constants.py.txt": REPO / "oracle/kdm6/constants.py",
    "oracle_fconst.py.txt": REPO / "oracle/kdm6/fconst.py",
}
SAVED_RESULT = HERE / "results.json"
SAVED_RESULT_SHA256 = "94da704cfa0d91b6b1ecd9db7a22e311a3c3dda48044c35574c69af2b5efe555"
K = 39
S = "ice_sedimentation_conservative_n1"
H_VALUES = (1.0e-3, 1.0e-4, 1.0e-5)
TARGET_NATIVE = (20, 21, 22, 23)
TARGET_TOP = tuple(K - level for level in TARGET_NATIVE)
QI_UNRESOLVED_NATIVE = 15
QI_UNRESOLVED_TOP = K - QI_UNRESOLVED_NATIVE
PIDNI = 1570.79638671875

REQUIRED = {
    "runtime_entry_post_clamp": {"qi"},
    S: {
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
        "dtcld",
        "applied_out_ni",
        "applied_in_ni",
        "out_attempt_ni",
        "falk_stored_ni",
    },
    "runtime_post_sed_entry": {"ni"},
    "c3_pre_mf_d1": {
        "ni_before",
        "ni_after_store1",
        "ni_after_store2",
        "ninuc",
        "pimlt_ni",
        "nfrzdtc",
    },
    "c3_pre_homogeneous_freeze": {
        "ni_before",
        "ni_after",
        "freeze_mask",
        "nc_freeze_source",
    },
    "c3_pre_snap_a": {
        "qi",
        "ni_before",
        "ni_after",
        "dend",
        "lambda_raw",
        "gate_qi_ge_1e14",
        "gate_ni_ge_zero",
    },
    "c3_pre_mf_d2_d3_d4": {
        "ni_before",
        "ni_after_store1",
        "ni_after_store2",
        "ninuc",
        "pimlt_ni",
        "nfrzdtc",
    },
    "c3_pre_snap_b": {
        "qi",
        "ni_before",
        "ni_after",
        "dend",
        "lambda_raw",
        "gate_qi_ge_1e14",
        "gate_ni_ge_zero",
    },
    "c3_input": {"qi", "ni", "dend"},
}


def need(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def pinned(path: Path, expected: str) -> bytes:
    raw = path.read_bytes()
    need(
        hashlib.sha256(raw).hexdigest() == expected,
        "pinned parent source/data: " + path.name,
    )
    return raw


def oracle_sources() -> dict:
    snapshot_dir = (
        REPO / "harness/evidence/native_qnice_snap_a_ad_2026-11-03/source_snapshots"
    )
    for name, expected in ORACLE_SNAPSHOT_PINS.items():
        pinned(snapshot_dir / name, expected)
    current = {
        name: hashlib.sha256(path.read_bytes()).hexdigest()
        for name, path in LIVE_ORACLE_PATHS.items()
    }
    return {
        "archived_sha256": ORACLE_SNAPSHOT_PINS.copy(),
        "current_checkout_sha256": current,
        "current_checkout_equal_to_archived": {
            name: current[name] == expected
            for name, expected in ORACLE_SNAPSHOT_PINS.items()
        },
        "oracle_under_test": "current checkout oracle.kdm6.coordinator._limit_number_for_lamda",
    }


def bits(value: float) -> str:
    return format(struct.unpack("<Q", struct.pack("<d", value))[0], "x")


def value(word: str) -> float:
    integer = int(word, 16)
    need(0 <= integer < (1 << 64), "f64 word width")
    result = struct.unpack("<d", integer.to_bytes(8, "little"))[0]
    need(math.isfinite(result), "finite f64 word")
    return result


def load_capture() -> tuple[dict, dict]:
    raw = pinned(CAPTURE, CAPTURE_SHA256)
    pinned(CPP_CONSERVATIVE, CPP_CONSERVATIVE_SHA256)
    pinned(CPP_COORDINATOR, CPP_COORDINATOR_SHA256)
    parent = json.loads(pinned(PARENT_ANALYSIS, PARENT_ANALYSIS_SHA256))
    local = json.loads(pinned(SNAP_A_RESULT, SNAP_A_RESULT_SHA256))
    need(
        local["changed_native_levels_1based"] == [25, 20, 19, 18, 17, 16]
        and local["parent_capture_sha256"] == CAPTURE_PARENT_LINK_SHA256
        and parent["host_to_runtime_den_qv_ni_words_equal"] == 117,
        "parent result chain",
    )
    lines = raw.decode("ascii").splitlines()
    need(
        len(lines) == 2773 and lines[-1] == "# native_rows=2769,status=complete",
        "complete parent native CSV",
    )
    reader = csv.DictReader(line for line in lines if not line.startswith("#"))
    need(
        reader.fieldnames
        == "one_step_call,runtime_call,substep,b_zero,k_zero,B,K,stage,field,dtype,raw_hex".split(
            ","
        ),
        "parent CSV columns",
    )
    records = {}
    for row in reader:
        stage, field = row["stage"], row["field"]
        if stage not in REQUIRED or field not in REQUIRED[stage]:
            continue
        need(
            (
                row["one_step_call"],
                row["runtime_call"],
                row["b_zero"],
                row["B"],
                row["K"],
            )
            == ("2", "2", "22617", "32248", "39"),
            "same-call stage identity",
        )
        k = int(row["k_zero"])
        need(0 <= k < K and row["dtype"] in ("f64", "bool"), "stage K/dtype")
        key = (stage, field, k)
        need(key not in records, "duplicate stage field K")
        records[key] = row["raw_hex"]
    need(
        all(
            (stage, field, k) in records
            for stage, fields in REQUIRED.items()
            for field in fields
            for k in range(K)
        ),
        "required 39-level stage inventory",
    )
    return records, parent


def get(records: dict, stage: str, field: str, k: int) -> float:
    return value(records[(stage, field, k)])


def vector(records: dict, stage: str, field: str) -> torch.Tensor:
    return torch.tensor(
        [get(records, stage, field, k) for k in range(K)], dtype=torch.float64
    )


def snap(
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
        q_thresh=1.0e-14,
        n_thresh=0.0,
        diagnostic=diagnostic,
    )


def transport(q: torch.Tensor, n: torch.Tensor, operands: dict) -> tuple:
    """Executed conservative source order with fixed captured speed and grid."""
    d, ds, z, zs = (
        operands[name] for name in ("dend", "dend_safe", "delz", "delz_safe")
    )
    wq, wn, m, gate, dt = (
        operands[name] for name in ("work1_qi", "workn_qi", "mstep", "gate", "dtcld")
    )
    qout, nout, qafter, nafter = [], [], [], []
    q_attempt, n_attempt = [], []
    for k in range(K):
        falk_q = (d[k] * q[k] * wq[k] / m[k] * gate[k]).to(q.dtype)
        falk_n = (n[k] * wn[k] / m[k] * gate[k]).to(n.dtype)
        q_candidate = falk_q * dt[k] / ds[k]
        n_candidate = falk_n * dt[k]
        qo = torch.minimum(q_candidate, q[k])
        no = torch.minimum(n_candidate, n[k])
        qi = (
            torch.zeros_like(qo)
            if k == 0
            else qout[-1] * (ds[k - 1] * z[k - 1]) / (ds[k] * zs[k])
        )
        ni = torch.zeros_like(no) if k == 0 else nout[-1] * z[k - 1] / zs[k]
        qafter.append(q[k] - qo if k == 0 else q[k] - qo + qi)
        nafter.append(n[k] - no if k == 0 else n[k] - no + ni)
        qout.append(qo)
        nout.append(no)
        q_attempt.append(q_candidate)
        n_attempt.append(n_candidate)
    return tuple(
        torch.stack(x) for x in (qafter, nafter, qout, nout, q_attempt, n_attempt)
    )


def composite(
    q: torch.Tensor,
    n: torch.Tensor,
    operands: dict,
    frozen_q15: torch.Tensor,
    *,
    diagnostic: bool = False,
) -> tuple:
    q_sed, n_sed, qout, nout, qattempt, nattempt = transport(q, n, operands)
    # The observed native level 15 QI differs after sedimentation; this
    # unreachable, unperturbed cell is a fixed captured boundary in this map.
    q_a = torch.stack(
        [frozen_q15 if k == QI_UNRESOLVED_TOP else q_sed[k] for k in range(K)]
    )
    a_diag, b_diag = {}, {}
    n_a = snap(q_a, n_sed, operands["dend"], a_diag if diagnostic else None)
    # D1/homogeneous/D2-D4 NI rates and masks are held at their captured zero
    # values. Their producer derivatives are not represented here.
    n_b = snap(q_a, n_a, operands["dend"], b_diag if diagnostic else None)
    return n_b, (q_sed, n_sed, q_a, n_a, qout, nout, qattempt, nattempt, a_diag, b_diag)


def cap_winner(attempt: torch.Tensor, reservoir: torch.Tensor) -> str:
    if bool(attempt < reservoir):
        return "raw"
    if bool(attempt == reservoir):
        return "tie"
    return "reservoir"


def selected_signature(
    transport_parts: tuple,
    q_entry: torch.Tensor,
    n_entry: torch.Tensor,
    den: torch.Tensor,
    support: tuple[int, ...],
) -> tuple:
    q_sed, n_sed, q_a, n_a, qout, nout, qattempt, nattempt, a, b = transport_parts
    return tuple(
        (
            cap_winner(qattempt[k], q_entry[k]),
            cap_winner(nattempt[k], n_entry[k]),
            bool(a["active"][k]),
            bool(a["too_small"][k]),
            bool(a["too_large"][k]),
            bool(q_a[k] * den[k] <= 1.0e-30),
            bool(fc.PIDNI * n_sed[k] / a["qden"][k] <= 1.0e-30),
            bool(b["active"][k]),
            bool(b["too_small"][k]),
            bool(b["too_large"][k]),
            bool(q_a[k] * den[k] <= 1.0e-30),
            bool(fc.PIDNI * n_a[k] / b["qden"][k] <= 1.0e-30),
            bool(q_a[k] >= 1.0e-14),
            bool(n_sed[k] >= 0.0),
        )
        for k in support
    )


def strict_causal_support(
    parts: tuple, q_entry: torch.Tensor, n_entry: torch.Tensor, den: torch.Tensor
) -> float:
    """Value-only audit of moving branches; native-20 NI entry tie stays fixed."""
    _, n_sed, q_a, _, _, _, q_attempt, n_attempt, a, b = parts
    margins = []
    for level in TARGET_NATIVE:
        k = K - level
        need(
            q_a[k].item() > 1.0e-14
            and n_sed[k].item() > 0.0
            and q_a[k].item() * den[k].item() > 1.0e-30,
            "strict active snap inputs on causal support",
        )
        need(
            cap_winner(q_attempt[k], q_entry[k]) == "raw",
            "strict open QI departure cap on causal support",
        )
        if level == 20:
            need(
                n_entry[k].item() == 0.0
                and cap_winner(n_attempt[k], n_entry[k]) == "tie",
                "fixed zero native-20 NI entry tie",
            )
            need(
                bool(a["too_small"][k]) and a["lamda"][k].item() < c.LAMDAIMIN,
                "strict snap-A lower branch at native 20",
            )
        else:
            need(
                cap_winner(n_attempt[k], n_entry[k]) == "raw"
                and c.LAMDAIMIN < a["lamda"][k].item() < c.LAMDAIMAX,
                "strict open NI cap and snap-A interior",
            )
        need(
            bool(a["active"][k])
            and bool(b["active"][k])
            and c.LAMDAIMIN < b["lamda"][k].item() < c.LAMDAIMAX,
            "strict snap-B interior",
        )
        margins.append(b["lamda"][k].item() - c.LAMDAIMIN)
    return min(margins)


def replay() -> dict:
    need(
        CAPTURE_SHA256 == CAPTURE_PARENT_LINK_SHA256,
        "parent capture independent digest link",
    )
    source_attribution = oracle_sources()
    records, parent = load_capture()
    need(
        fc.PIDNI == PIDNI and c.DMI == 3.0 and c.LAMDAIMIN == 9080.0,
        "f32-derived snap coefficient",
    )
    q0 = vector(records, "runtime_entry_post_clamp", "qi")
    n0 = vector(records, S, "ni_before")
    operands = {
        name: vector(records, S, name)
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
    need(
        all(
            torch.equal(operands[name], operands[safe])
            for name, safe in (("dend", "dend_safe"), ("delz", "delz_safe"))
        )
        and torch.all(operands["mstep"] == 1).item()
        and torch.all(operands["gate"] == 1).item()
        and torch.all(operands["dtcld"] == 20).item(),
        "fixed schedule and inactive geometry floors",
    )
    for stage in ("c3_pre_mf_d1", "c3_pre_mf_d2_d3_d4"):
        for field in ("ninuc", "pimlt_ni", "nfrzdtc"):
            need(
                all(records[(stage, field, k)] == "0" for k in range(K)),
                "captured zero NI rate: " + stage + "/" + field,
            )
    need(
        all(
            records[("c3_pre_homogeneous_freeze", "freeze_mask", k)] == "0"
            for k in range(K)
        ),
        "captured inactive homogeneous mask",
    )
    observed_a_q = vector(records, "c3_pre_snap_a", "qi")
    frozen_q15 = observed_a_q[QI_UNRESOLVED_TOP].detach()
    baseline, parts = composite(q0, n0, operands, frozen_q15, diagnostic=True)
    q_sed, n_sed, q_a, n_a, qout, nout, qattempt, nattempt, a, b = parts
    q_disagree = [
        K - k
        for k in range(K)
        if bits(q_sed[k].item()) != records[("c3_pre_snap_a", "qi", k)]
    ]
    need(
        q_disagree == [QI_UNRESOLVED_NATIVE] and frozen_q15.item() == 0.0,
        "one explicit unresolved post-sed QI level",
    )
    for k in range(K):
        for computed, stage, field in (
            (n_sed[k], S, "ni_after"),
            (n_sed[k], "runtime_post_sed_entry", "ni"),
            (n_sed[k], "c3_pre_mf_d1", "ni_before"),
            (n_sed[k], "c3_pre_mf_d1", "ni_after_store1"),
            (n_sed[k], "c3_pre_mf_d1", "ni_after_store2"),
            (n_sed[k], "c3_pre_homogeneous_freeze", "ni_before"),
            (n_sed[k], "c3_pre_homogeneous_freeze", "ni_after"),
            (n_sed[k], "c3_pre_snap_a", "ni_before"),
            (q_a[k], "c3_pre_snap_a", "qi"),
            (q_a[k], "c3_pre_snap_b", "qi"),
            (n_a[k], "c3_pre_snap_a", "ni_after"),
            (n_a[k], "c3_pre_mf_d2_d3_d4", "ni_before"),
            (n_a[k], "c3_pre_mf_d2_d3_d4", "ni_after_store1"),
            (n_a[k], "c3_pre_mf_d2_d3_d4", "ni_after_store2"),
            (n_a[k], "c3_pre_snap_b", "ni_before"),
            (baseline[k], "c3_pre_snap_b", "ni_after"),
            (baseline[k], "c3_input", "ni"),
        ):
            need(
                bits(computed.item()) == records[(stage, field, k)],
                "conditional baseline raw-word handoff: " + stage + "/" + field,
            )
        need(
            bits(q_a[k].item()) == records[("c3_input", "qi", k)],
            "fixed QI middle-stage baseline",
        )
        for stage in ("c3_pre_snap_a", "c3_pre_snap_b", "c3_input"):
            need(
                bits(operands["dend"][k].item()) == records[(stage, "dend", k)],
                "shared snap/C3 density handoff",
            )
        for stage, diag, n_input in (
            ("c3_pre_snap_a", a, n_sed),
            ("c3_pre_snap_b", b, n_a),
        ):
            captured_lambda = get(records, stage, "lambda_raw", k)
            gate_q = bool(int(records[(stage, "gate_qi_ge_1e14", k)], 16))
            gate_n = bool(int(records[(stage, "gate_ni_ge_zero", k)], 16))
            captured_active = gate_q and gate_n
            captured_low = captured_active and captured_lambda <= c.LAMDAIMIN
            captured_high = (
                captured_active and not captured_low and captured_lambda >= c.LAMDAIMAX
            )
            need(
                math.isclose(diag["lamda"][k].item(), captured_lambda, rel_tol=1e-12)
                and gate_q == bool(q_a[k] >= 1e-14)
                and gate_n == bool(n_input[k] >= 0.0)
                and (captured_active, captured_low, captured_high)
                == (
                    bool(diag["active"][k]),
                    bool(diag["too_small"][k]),
                    bool(diag["too_large"][k]),
                ),
                "captured snap gate/lambda inferred winner",
            )
    need(
        parent["pre_c3_ni_changes"]["snap_a"]["changed_native_levels_1based"]
        == [25, 20, 19, 18, 17, 16],
        "parent snap A change inventory",
    )
    support = TARGET_TOP
    baseline_signature = selected_signature(parts, q0, n0, operands["dend"], support)
    # Full-column zero ties stay frozen. Only the four-level causal support
    # carries derivative claims; snap B level 20 is close to the lower bound.
    baseline_b_margin = strict_causal_support(parts, q0, n0, operands["dend"])
    targets = baseline[list(TARGET_TOP)].detach()
    seeds = {}
    for label, field, level in (
        ("relative_q21", "q", 21),
        ("relative_ni21", "n", 21),
        ("relative_ni23", "n", 23),
    ):
        dq, dn = torch.zeros_like(q0), torch.zeros_like(n0)
        k = K - level
        if field == "q":
            dq[k] = q0[k]
        else:
            dn[k] = n0[k]
        seeds[label] = (dq, dn)
    q21, n21, n23 = q0[K - 21].item(), n0[K - 21].item(), n0[K - 23].item()
    z21, z20, z23, z22 = (operands["delz"][K - j].item() for j in (21, 20, 23, 22))
    alpha_q21 = operands["work1_qi"][K - 21].item() * 20.0
    alpha_n21 = operands["workn_qi"][K - 21].item() * 20.0
    alpha_n23 = operands["workn_qi"][K - 23].item() * 20.0
    coefficient = math.pow(c.LAMDAIMIN, c.DMI) / PIDNI
    analytic = {
        "relative_q21": (
            coefficient * q21 * alpha_q21 * operands["dend"][K - 21].item() * z21 / z20,
            0.0,
            0.0,
            0.0,
        ),
        "relative_ni21": (0.0, n21 * (1 - alpha_n21), 0.0, 0.0),
        "relative_ni23": (0.0, 0.0, n23 * alpha_n23 * z23 / z22, n23 * (1 - alpha_n23)),
    }

    def fn(q: torch.Tensor, n: torch.Tensor) -> torch.Tensor:
        return composite(q, n, operands, frozen_q15)[0][list(TARGET_TOP)]

    directions = {}
    for label, seed in seeds.items():
        jvp = torch.autograd.functional.jvp(fn, (q0, n0), seed)[1]
        need(
            all(
                math.isclose(
                    jvp[i].item(), analytic[label][i], rel_tol=1e-12, abs_tol=1e-11
                )
                for i in range(4)
            ),
            "independent sparse-chain derivative",
        )
        fd_records = []
        k = K - (21 if label != "relative_ni23" else 23)
        active = 0 if label == "relative_q21" else 1
        for h in H_VALUES:
            plus = (q0 + h * seed[0], n0 + h * seed[1])
            minus = (q0 - h * seed[0], n0 - h * seed[1])
            _, pplus = composite(*plus, operands, frozen_q15, diagnostic=True)
            _, pminus = composite(*minus, operands, frozen_q15, diagnostic=True)
            need(
                selected_signature(pplus, *plus, operands["dend"], support)
                == baseline_signature
                and selected_signature(pminus, *minus, operands["dend"], support)
                == baseline_signature,
                "conditional four-level branch signature",
            )
            margin_plus = strict_causal_support(pplus, *plus, operands["dend"])
            margin_minus = strict_causal_support(pminus, *minus, operands["dend"])
            xp, xm = plus[active][k].item(), minus[active][k].item()
            gap = xp - xm
            need(gap != 0.0, "represented input gap")
            yp, ym = fn(*plus).detach(), fn(*minus).detach()
            fd = seed[active][k] * (yp - ym) / gap
            scaled = torch.max(
                torch.abs(fd - jvp) / torch.clamp(torch.abs(jvp), min=1.0)
            ).item()
            need(scaled < 1.0e-9, "represented-spacing FD and JVP")
            fd_records.append(
                {
                    "h": h,
                    "input_plus": xp,
                    "input_minus": xm,
                    "actual_gap": gap,
                    "output_plus": yp.tolist(),
                    "output_minus": ym.tolist(),
                    "fd": fd.tolist(),
                    "max_scaled_fd_minus_jvp": scaled,
                    "branch_signature_plus": selected_signature(
                        pplus, *plus, operands["dend"], support
                    ),
                    "branch_signature_minus": selected_signature(
                        pminus, *minus, operands["dend"], support
                    ),
                    "snap_b_min_lambda_margin": min(margin_plus, margin_minus),
                }
            )
        directions[label] = {
            "seed_input_value": seed[active][k].item(),
            "jvp": jvp.tolist(),
            "analytic": analytic[label],
            "finite_differences": fd_records,
        }
    cotangent = torch.tensor((0.7, -0.4, 0.9, -0.2), dtype=torch.float64)
    q_leaf, n_leaf = q0.clone().requires_grad_(True), n0.clone().requires_grad_(True)
    vjp_q, vjp_n = torch.autograd.grad(
        fn(q_leaf, n_leaf), (q_leaf, n_leaf), grad_outputs=cotangent
    )
    analytic_vjp = {
        "q21": cotangent[0].item() * analytic["relative_q21"][0] / q21,
        "ni21": cotangent[1].item() * (1 - alpha_n21),
        "ni23": (
            cotangent[2].item() * alpha_n23 * z23 / z22
            + cotangent[3].item() * (1 - alpha_n23)
        ),
    }
    need(
        math.isclose(vjp_q[K - 21].item(), analytic_vjp["q21"], rel_tol=1e-12)
        and math.isclose(vjp_n[K - 21].item(), analytic_vjp["ni21"], rel_tol=1e-12)
        and math.isclose(vjp_n[K - 23].item(), analytic_vjp["ni23"], rel_tol=1e-12),
        "independent sparse-chain weighted VJP",
    )
    transpose = {}
    for label, (dq, dn) in seeds.items():
        left = torch.dot(
            torch.autograd.functional.jvp(fn, (q0, n0), (dq, dn))[1], cotangent
        ).item()
        right = (torch.dot(dq, vjp_q) + torch.dot(dn, vjp_n)).item()
        need(
            math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-10),
            "selected weighted JVP/VJP transpose",
        )
        transpose[label] = {"jvp_dot_weight": left, "seed_dot_vjp": right}
    result = {
        "schema": "kdm6.native_qnice_sed_snap_chain_conditional.v1",
        "scientific_status": "INCONCLUSIVE",
        "physical_unit_status": "INCONCLUSIVE",
        "parent_capture_sha256": CAPTURE_SHA256,
        "source_attribution": source_attribution,
        "target_native_levels_1based": list(TARGET_NATIVE),
        "unresolved_qi_native_level_1based": QI_UNRESOLVED_NATIVE,
        "unresolved_qi_sed_output": q_sed[QI_UNRESOLVED_TOP].item(),
        "unresolved_qi_snap_a_input": frozen_q15.item(),
        "baseline_target_c3_ni": targets.tolist(),
        "baseline_39_ni_stage_words_equal": True,
        "reconstructed_qi_equals_snap_a_input_in_38_layers": True,
        "middle_ni_rates_and_homogeneous_mask_frozen_at_zero": True,
        "work1_workn_geometry_and_schedule_frozen": True,
        "baseline_support_branch_signature": baseline_signature,
        "snap_b_level20_lambda_margin": b["lamda"][K - 20].item() - c.LAMDAIMIN,
        "baseline_causal_support_min_snap_b_margin": baseline_b_margin,
        "directions": directions,
        "cotangent": cotangent.tolist(),
        "selected_vjp_q21": vjp_q[K - 21].item(),
        "selected_vjp_ni21": vjp_n[K - 21].item(),
        "selected_vjp_ni23": vjp_n[K - 23].item(),
        "analytic_selected_vjp": analytic_vjp,
        "transpose_checks": transpose,
        "native_full_process_derivative_certified": False,
    }
    saved = json.loads(pinned(SAVED_RESULT, SAVED_RESULT_SHA256))
    for key in (
        "schema",
        "scientific_status",
        "physical_unit_status",
        "parent_capture_sha256",
        "target_native_levels_1based",
        "unresolved_qi_native_level_1based",
        "unresolved_qi_snap_a_input",
        "baseline_target_c3_ni",
        "baseline_39_ni_stage_words_equal",
        "reconstructed_qi_equals_snap_a_input_in_38_layers",
        "middle_ni_rates_and_homogeneous_mask_frozen_at_zero",
        "work1_workn_geometry_and_schedule_frozen",
        "native_full_process_derivative_certified",
    ):
        need(result[key] == saved[key], "saved conditional-chain reference: " + key)
    need(
        math.isclose(
            result["unresolved_qi_sed_output"],
            saved["unresolved_qi_sed_output"],
            rel_tol=1e-12,
        ),
        "saved unresolved QI numerical value",
    )
    need(
        result["source_attribution"]["archived_sha256"]
        == saved["source_attribution"]["archived_sha256"]
        and result["source_attribution"]["oracle_under_test"]
        == saved["source_attribution"]["oracle_under_test"],
        "saved archived oracle source identities",
    )
    for name in directions:
        need(
            all(
                math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)
                for a, b in zip(
                    result["directions"][name]["analytic"],
                    saved["directions"][name]["analytic"],
                )
            ),
            "saved sparse analytic direction: " + name,
        )
    return result


if __name__ == "__main__":
    print(json.dumps(replay(), indent=2, sort_keys=True))
    print("NATIVE_QNICE_SED_SNAP_CHAIN_REPLAY_PASSED")
