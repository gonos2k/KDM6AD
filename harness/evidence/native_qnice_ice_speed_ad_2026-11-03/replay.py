"""Conditional ice-speed producer AD at the recorded native 39-level call."""

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
from oracle.kdm6.slope import default_slope_params, slope_kdm6_torch  # noqa: E402
from oracle.kdm6.thermo import compute_denfac, default_thermo_params  # noqa: E402


PARENT = REPO / "harness/evidence/native_qnice_39_applied_2026-11-03"
CAPTURE = PARENT / "raw/native_qnice_applied_30339_runtime2.csv"
CPP_BUILD_RECEIPT = PARENT / "raw/cpp_build_receipt.json"
CHAIN_RESULT = (
    REPO / "harness/evidence/native_qnice_sed_snap_chain_2026-11-03/results.json"
)
CAPTURE_SHA256 = "27b89eb5b38b88174f55188be7d724cd74df8e6577c034a044581c78b3dff3bf"
CPP_BUILD_RECEIPT_SHA256 = (
    "c8aa9e5b2e7bd6634d1ab91dc131dd7b37f0e147d638de6201529c6130bd3cd4"
)
CHAIN_RESULT_SHA256 = "94da704cfa0d91b6b1ecd9db7a22e311a3c3dda48044c35574c69af2b5efe555"
SAVED_RESULT = HERE / "results.json"
SAVED_RESULT_SHA256 = "b7175f04ff8e141041154851b61f3fc32ee9921993e90f7df063e79f7f5d4cfd"
SOURCE_PINS = {
    "build_tree_slope.cpp.txt": "202f7b197ae9f12df9cbca18d92ea0920123b54c4d2b8dbd357aa89e5fc246ec",
    "build_tree_thermo.cpp.txt": "f4c887ba754244f781a27cd94dc42341e7559be7680947f74ea27d06507dbe4b",
    "oracle_slope.py.txt": "5121761c97390eb0348ad3ed1c2b8aec6ad697b839826fdcac1cd6437978e823",
    "oracle_thermo.py.txt": "5278c14c6d87178af5ee963eef59d3297b923fa374412fd854c01e43ffb1b5cd",
}
LIVE_SOURCES = {
    "oracle_slope.py.txt": REPO / "oracle/kdm6/slope.py",
    "oracle_thermo.py.txt": REPO / "oracle/kdm6/thermo.py",
}
K = 39
S = "ice_sedimentation_conservative_n1"
TARGET_NATIVE = (20, 21, 22, 23)
TARGET_TOP = tuple(K - level for level in TARGET_NATIVE)
QI_UNRESOLVED_TOP = K - 15
H_VALUES = (1.0e-3, 1.0e-4, 1.0e-5)
INV_DMI_F32 = 0.3333333432674408

FIELDS = {
    "runtime_entry_pre_clamp": {"den", "dend"},
    "runtime_entry_post_clamp": {"qi", "ni"},
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
    },
    "c3_pre_snap_a": {"qi", "ni_before", "ni_after"},
    "c3_pre_snap_b": {"qi", "ni_before", "ni_after"},
    "c3_input": {"ni", "qi"},
}


def need(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def pinned(path: Path, expected: str) -> bytes:
    raw = path.read_bytes()
    need(hashlib.sha256(raw).hexdigest() == expected, "pinned input: " + path.name)
    return raw


def word(value: float) -> str:
    return format(struct.unpack("<Q", struct.pack("<d", value))[0], "x")


def unword(raw: str) -> float:
    bits = int(raw, 16)
    need(0 <= bits < 1 << 64, "binary64 width")
    value = struct.unpack("<d", bits.to_bytes(8, "little"))[0]
    need(math.isfinite(value), "finite binary64")
    return value


def load() -> tuple[dict, dict]:
    raw = pinned(CAPTURE, CAPTURE_SHA256)
    saved = json.loads(pinned(CHAIN_RESULT, CHAIN_RESULT_SHA256))
    need(
        saved["parent_capture_sha256"] == CAPTURE_SHA256
        and saved["target_native_levels_1based"] == list(TARGET_NATIVE)
        and saved["unresolved_qi_native_level_1based"] == 15
        and saved["native_full_process_derivative_certified"] is False,
        "conditional parent result identity",
    )
    lines = raw.decode("ascii").splitlines()
    need(
        len(lines) == 2773 and lines[-1] == "# native_rows=2769,status=complete",
        "complete native capture",
    )
    reader = csv.DictReader(line for line in lines if not line.startswith("#"))
    need(
        reader.fieldnames
        == "one_step_call,runtime_call,substep,b_zero,k_zero,B,K,stage,field,dtype,raw_hex".split(
            ","
        ),
        "native capture columns",
    )
    rows = {}
    for row in reader:
        stage, field = row["stage"], row["field"]
        if stage not in FIELDS or field not in FIELDS[stage]:
            continue
        need(
            (
                row["one_step_call"],
                row["runtime_call"],
                row["b_zero"],
                row["B"],
                row["K"],
                row["dtype"],
            )
            == ("2", "2", "22617", "32248", "39", "f64"),
            "speed producer call/dtype",
        )
        k = int(row["k_zero"])
        need(0 <= k < K and (stage, field, k) not in rows, "speed field unique level")
        rows[(stage, field, k)] = row["raw_hex"]
    need(
        all(
            (s, f, k) in rows
            for s, fields in FIELDS.items()
            for f in fields
            for k in range(K)
        ),
        "complete speed/chain field inventory",
    )
    return rows, saved


def get(rows: dict, stage: str, field: str, k: int) -> float:
    return unword(rows[(stage, field, k)])


def tensor(rows: dict, stage: str, field: str) -> torch.Tensor:
    return torch.tensor(
        [get(rows, stage, field, k) for k in range(K)], dtype=torch.float64
    )


def source_attribution() -> dict:
    for name, expected in SOURCE_PINS.items():
        pinned(HERE / "source_snapshots" / name, expected)
    build = json.loads(pinned(CPP_BUILD_RECEIPT, CPP_BUILD_RECEIPT_SHA256))
    need(
        build["schema"] == "kdm6.native_qnice_39_cpp_build_attempt4.v1"
        and build["archive_member_sha256"]["slope.cpp.o"]
        == "73db886d78ebda37595dd6b6ba4fa4472c49a4451bcb567b0519f98ef203039a"
        and build["archive_member_sha256"]["thermo.cpp.o"]
        == "8ba776f3d65f222848524eff7e53e4d39d20b925525540a60bfe85ed142735f0",
        "executed slope/thermo object lineage",
    )
    live = {
        name: hashlib.sha256(path.read_bytes()).hexdigest()
        for name, path in LIVE_SOURCES.items()
    }
    return {
        "archived_source_sha256": SOURCE_PINS.copy(),
        "current_oracle_sha256": live,
        "current_oracle_matches_archive": {
            name: live[name] == SOURCE_PINS[name] for name in live
        },
        "oracle_under_test": "current checkout slope_kdm6_torch and compute_denfac",
        "cpp_build_receipt_sha256": CPP_BUILD_RECEIPT_SHA256,
        "linked_slope_object_sha256": build["archive_member_sha256"]["slope.cpp.o"],
        "linked_thermo_object_sha256": build["archive_member_sha256"]["thermo.cpp.o"],
        "source_to_object_provenance": "private build-tree candidate plus linked-object attestation; exact source-to-object compilation not independently reproduced",
    }


def ice_speeds(
    q: torch.Tensor,
    n: torch.Tensor,
    den: torch.Tensor,
    dend: torch.Tensor,
    dz: torch.Tensor,
    params,
) -> tuple[torch.Tensor, torch.Tensor, dict]:
    """Use the actual public slope/thermo producers for their ice outputs."""
    denfac = compute_denfac(den, params=default_thermo_params())
    zeros = torch.zeros_like(q)
    ones = torch.ones_like(q)
    slope = slope_kdm6_torch(
        zeros,
        zeros,
        zeros,
        q,
        zeros,
        n,
        dend,
        denfac,
        torch.full_like(q, 250.0),
        zeros,
        zeros,
        ones,
        zeros,
        params,
    )
    wq = slope.vt_i / dz
    wn = slope.vtn_i / dz
    # Diagnostic-only branch signature, never reused in the differentiable map.
    qden_raw = q * dend
    ratio_raw = params.pidni * n / torch.clamp(qden_raw, min=1e-30)
    lamda = torch.exp(torch.log(torch.clamp(ratio_raw, min=1e-30)) * INV_DMI_F32)
    return (
        wq,
        wn,
        {
            "lambda_raw": lamda,
            "qden_floor": qden_raw <= 1e-30,
            "ratio_floor": ratio_raw <= 1e-30,
            "ice_mask": q <= 1e-15,
            "vt_i_zero": q <= 0.0,
            "rslope_lower": lamda <= c.LAMDAIMIN,
            "rslope_upper": lamda >= c.LAMDAIMAX,
            "rslope_i": slope.rslope_i,
        },
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
        q_thresh=1e-14,
        n_thresh=0.0,
        diagnostic=diagnostic,
    )


def transport(
    q: torch.Tensor, n: torch.Tensor, wq: torch.Tensor, wn: torch.Tensor, op: dict
) -> tuple:
    d, ds, z, zs, m, gate, dt = (
        op[name]
        for name in ("dend", "dend_safe", "delz", "delz_safe", "mstep", "gate", "dtcld")
    )
    qout, nout, qa, na, qattempt, nattempt = [], [], [], [], [], []
    for k in range(K):
        fq = (d[k] * q[k] * wq[k] / m[k] * gate[k]).to(q.dtype)
        fn = (n[k] * wn[k] / m[k] * gate[k]).to(n.dtype)
        qtry = fq * dt[k] / ds[k]
        ntry = fn * dt[k]
        qo = torch.minimum(qtry, q[k])
        no = torch.minimum(ntry, n[k])
        qi = (
            torch.zeros_like(qo)
            if k == 0
            else qout[-1] * (ds[k - 1] * z[k - 1]) / (ds[k] * zs[k])
        )
        ni = torch.zeros_like(no) if k == 0 else nout[-1] * z[k - 1] / zs[k]
        qa.append(q[k] - qo if k == 0 else q[k] - qo + qi)
        na.append(n[k] - no if k == 0 else n[k] - no + ni)
        qout.append(qo)
        nout.append(no)
        qattempt.append(qtry)
        nattempt.append(ntry)
    return tuple(torch.stack(x) for x in (qa, na, qout, nout, qattempt, nattempt))


def chain(
    q: torch.Tensor,
    n: torch.Tensor,
    op: dict,
    params,
    frozen_q15: torch.Tensor,
    *,
    dynamic: bool,
    diagnostics: bool = False,
) -> tuple:
    if dynamic:
        wq, wn, producer = ice_speeds(
            q, n, op["den"], op["dend"], op["delz_safe"], params
        )
    else:
        wq, wn = op["work1_qi"], op["workn_qi"]
        producer = {}
    qsed, nsed, qout, nout, qattempt, nattempt = transport(q, n, wq, wn, op)
    qsnap = torch.stack(
        [frozen_q15 if k == QI_UNRESOLVED_TOP else qsed[k] for k in range(K)]
    )
    a, b = {}, {}
    na = snap(qsnap, nsed, op["dend"], a if diagnostics else None)
    nb = snap(qsnap, na, op["dend"], b if diagnostics else None)
    return nb, (
        qsed,
        nsed,
        qsnap,
        na,
        qout,
        nout,
        qattempt,
        nattempt,
        wq,
        wn,
        producer,
        a,
        b,
    )


def cap_winner(attempt: torch.Tensor, reservoir: torch.Tensor) -> str:
    if bool(attempt < reservoir):
        return "raw"
    if bool(attempt == reservoir):
        return "tie"
    return "reservoir"


def support_signature(
    parts: tuple, q: torch.Tensor, n: torch.Tensor, op: dict
) -> tuple:
    """Value-only branch audit on the four causally affected native levels."""
    _, nsed, qsnap, na, _, _, qattempt, nattempt, wq, wn, producer, a, b = parts
    d = op["dend"]
    return tuple(
        (
            bool(producer["ice_mask"][k]),
            bool(producer["qden_floor"][k]),
            bool(producer["ratio_floor"][k]),
            bool(producer["rslope_lower"][k]),
            bool(producer["rslope_upper"][k]),
            bool(producer["vt_i_zero"][k]),
            cap_winner(qattempt[k], q[k]),
            cap_winner(nattempt[k], n[k]),
            bool(a["active"][k]),
            bool(a["too_small"][k]),
            bool(a["too_large"][k]),
            bool(b["active"][k]),
            bool(b["too_small"][k]),
            bool(b["too_large"][k]),
            bool(qsnap[k] >= 1e-14),
            bool(nsed[k] >= 0.0),
            bool(qsnap[k] * d[k] <= 1e-30),
            bool(fc.PIDNI * nsed[k] / a["qden"][k] <= 1e-30),
            bool(fc.PIDNI * na[k] / b["qden"][k] <= 1e-30),
        )
        for k in TARGET_TOP
    )


def strict_support(parts: tuple, q: torch.Tensor, n: torch.Tensor, op: dict) -> dict:
    """Check moving branch margins; the native-20 NI-entry tie is fixed."""
    _, nsed, qsnap, _, _, _, qattempt, nattempt, wq, wn, producer, a, b = parts
    margins = {}
    for level in TARGET_NATIVE:
        k = K - level
        lam = producer["lambda_raw"][k].item()
        need(
            q[k].item() > 1e-15
            and qsnap[k].item() > 1e-14
            and not bool(producer["qden_floor"][k])
            and bool(a["active"][k])
            and bool(b["active"][k])
            and cap_winner(qattempt[k], q[k]) == "raw"
            and wq[k].item() > 0
            and wn[k].item() > 0,
            "strict moving ice-speed and QI cap support",
        )
        if level in (20, 21):
            need(
                bool(producer["rslope_lower"][k]) and lam < c.LAMDAIMIN,
                "strict low-clipped speed producer",
            )
        else:
            need(
                not bool(producer["rslope_lower"][k])
                and not bool(producer["rslope_upper"][k])
                and c.LAMDAIMIN < lam < c.LAMDAIMAX,
                "strict interior speed producer",
            )
        if level == 20:
            need(
                n[k].item() == 0.0 and cap_winner(nattempt[k], n[k]) == "tie",
                "fixed native-20 zero NI entry tie",
            )
            need(
                bool(a["too_small"][k]) and a["lamda"][k].item() < c.LAMDAIMIN,
                "strict snap A low branch at native 20",
            )
        else:
            need(
                cap_winner(nattempt[k], n[k]) == "raw"
                and not bool(a["too_small"][k])
                and c.LAMDAIMIN < a["lamda"][k].item() < c.LAMDAIMAX,
                "strict NI cap and snap A interior",
            )
        need(
            not bool(b["too_small"][k])
            and c.LAMDAIMIN < b["lamda"][k].item() < c.LAMDAIMAX,
            "strict snap B interior",
        )
        margins[str(level)] = {
            "speed_lambda_low_gap": lam - c.LAMDAIMIN,
            "speed_lambda_high_gap": c.LAMDAIMAX - lam,
            "snap_b_low_gap": b["lamda"][k].item() - c.LAMDAIMIN,
            "qi_cap_gap": q[k].item() - qattempt[k].item(),
            "ni_cap_gap": n[k].item() - nattempt[k].item(),
        }
    local_step = math.floor(
        max(torch.max(wq).item(), torch.max(wn).item()) * 20.0 + 1.0
    )
    need(local_step == 1, "selected-column mstep branch")
    return margins


def replay() -> dict:
    rows, conditional_parent = load()
    sources = source_attribution()
    params = default_slope_params()
    need(
        params.pidni == 1570.79638671875
        and params.pvti == 10840.0
        and params.pvtin == 2710.0
        and c.DMI == 3.0
        and c.BVTI == 1.0
        and fc._f32(1.0 / 3.0) == INV_DMI_F32,
        "f32-derived ice-speed source constants",
    )
    q0 = tensor(rows, "runtime_entry_post_clamp", "qi")
    n0 = tensor(rows, S, "ni_before")
    op = {
        name: tensor(rows, S, name)
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
    op["den"] = tensor(rows, "runtime_entry_pre_clamp", "den")
    need(
        torch.equal(op["den"], op["dend"])
        and torch.equal(op["dend"], op["dend_safe"])
        and torch.equal(op["delz"], op["delz_safe"])
        and torch.all(op["mstep"] == 1).item()
        and torch.all(op["gate"] == 1).item()
        and torch.all(op["dtcld"] == 20).item(),
        "captured density/floor/schedule operands",
    )
    frozen_q15 = tensor(rows, "c3_pre_snap_a", "qi")[QI_UNRESOLVED_TOP].detach()
    computed_q, computed_n, producer = ice_speeds(
        q0, n0, op["den"], op["dend"], op["delz_safe"], params
    )
    baseline_speed_word_matches = {}
    baseline_speed_max_rel = {}
    support_speed_max_rel = {}
    for field, got in (("work1_qi", computed_q), ("workn_qi", computed_n)):
        expected = op[field]
        count = sum(word(got[k].item()) == rows[(S, field, k)] for k in range(K))
        max_rel = torch.max(
            torch.abs(got - expected) / torch.clamp(torch.abs(expected), min=1e-30)
        ).item()
        support_rel = max(
            abs(got[k].item() - expected[k].item())
            / max(abs(expected[k].item()), 1e-30)
            for k in TARGET_TOP
        )
        need(
            max_rel <= 2e-6 and support_rel <= 1e-12,
            "39-level and selected active speed producer baseline",
        )
        baseline_speed_word_matches[field] = count
        baseline_speed_max_rel[field] = max_rel
        support_speed_max_rel[field] = support_rel
    fixed, fixed_parts = chain(
        q0, n0, op, params, frozen_q15, dynamic=False, diagnostics=True
    )
    dynamic, dynamic_parts = chain(
        q0, n0, op, params, frozen_q15, dynamic=True, diagnostics=True
    )
    need(
        all(word(fixed[k].item()) == rows[("c3_input", "ni", k)] for k in range(K)),
        "fixed-speed baseline C3 raw words",
    )
    dynamic_max_abs = max(abs(dynamic[k].item() - fixed[k].item()) for k in range(K))
    need(dynamic_max_abs <= 1e-8, "recomputed-speed baseline C3 numerical agreement")
    q_sed = fixed_parts[0]
    q_disagree = [
        K - k
        for k in range(K)
        if word(q_sed[k].item()) != rows[("c3_pre_snap_a", "qi", k)]
    ]
    need(
        q_disagree == [15]
        and frozen_q15.item() == 0.0
        and conditional_parent["unresolved_qi_native_level_1based"] == 15,
        "same explicit native-15 QI splice",
    )
    base_signature = support_signature(dynamic_parts, q0, n0, op)
    base_margins = strict_support(dynamic_parts, q0, n0, op)
    baseline_ice_speed_lambda = {
        str(level): producer["lambda_raw"][K - level].item() for level in TARGET_NATIVE
    }
    seeds = {}
    for label, field, level in (
        ("relative_q21", "q", 21),
        ("relative_ni21", "n", 21),
        ("relative_q23", "q", 23),
        ("relative_ni23", "n", 23),
    ):
        dq, dn = torch.zeros_like(q0), torch.zeros_like(n0)
        k = K - level
        if field == "q":
            dq[k] = q0[k]
        else:
            dn[k] = n0[k]
        seeds[label] = (dq, dn)
    z23, z22 = op["delz"][K - 23].item(), op["delz"][K - 22].item()
    n23 = n0[K - 23].item()
    beta = n23 * op["workn_qi"][K - 23].item() * 20.0
    fixed_ni23 = (0.0, 0.0, beta * z23 / z22, n23 - beta)
    a = INV_DMI_F32
    analytic_dynamic = {
        "relative_q21": (1.0429468145871474, 0.0, 0.0, 0.0),
        "relative_ni21": (0.0, 0.1358895005804943, 0.0, 0.0),
        "relative_q23": (0.0, 0.0, a * beta * z23 / z22, -a * beta),
        "relative_ni23": (0.0, 0.0, (1 - a) * beta * z23 / z22, n23 - (1 - a) * beta),
    }
    analytic_fixed = {
        "relative_q21": analytic_dynamic["relative_q21"],
        "relative_ni21": analytic_dynamic["relative_ni21"],
        "relative_q23": (0.0, 0.0, 0.0, 0.0),
        "relative_ni23": fixed_ni23,
    }

    def final(q: torch.Tensor, n: torch.Tensor, *, dynamic_speed: bool) -> torch.Tensor:
        return chain(q, n, op, params, frozen_q15, dynamic=dynamic_speed)[0][
            list(TARGET_TOP)
        ]

    directions = {}
    for label, seed in seeds.items():

        def dyn_fn(q: torch.Tensor, n: torch.Tensor) -> torch.Tensor:
            return final(q, n, dynamic_speed=True)

        def fixed_fn(q: torch.Tensor, n: torch.Tensor) -> torch.Tensor:
            return final(q, n, dynamic_speed=False)

        j_dynamic = torch.autograd.functional.jvp(dyn_fn, (q0, n0), seed)[1]
        j_fixed = torch.autograd.functional.jvp(fixed_fn, (q0, n0), seed)[1]
        for computed, expected in (
            (j_dynamic, analytic_dynamic[label]),
            (j_fixed, analytic_fixed[label]),
        ):
            need(
                all(
                    math.isclose(
                        computed[i].item(), expected[i], rel_tol=1e-12, abs_tol=1e-10
                    )
                    for i in range(4)
                ),
                "independent fixed/dynamic sparse JVP",
            )
        level = 23 if "23" in label else 21
        k = K - level
        speed_seed = torch.autograd.functional.jvp(
            lambda q, n: ice_speeds(
                q, n, op["den"], op["dend"], op["delz_safe"], params
            )[:2],
            (q0, n0),
            seed,
        )[1]
        speed_sign = (
            a if label == "relative_q23" else -a if label == "relative_ni23" else 0.0
        )
        speed_expected = [
            speed_sign * op[name][k].item() for name in ("work1_qi", "workn_qi")
        ]
        need(
            all(
                math.isclose(
                    speed_seed[i][k].item(),
                    speed_expected[i],
                    rel_tol=1e-12,
                    abs_tol=1e-13,
                )
                for i in range(2)
            ),
            "independent ice-speed producer JVP",
        )
        fd = []
        active = 0 if "relative_q" in label else 1
        for h in H_VALUES:
            plus = (q0 + h * seed[0], n0 + h * seed[1])
            minus = (q0 - h * seed[0], n0 - h * seed[1])
            _, pplus = chain(
                *plus, op, params, frozen_q15, dynamic=True, diagnostics=True
            )
            _, pminus = chain(
                *minus, op, params, frozen_q15, dynamic=True, diagnostics=True
            )
            need(
                support_signature(pplus, *plus, op) == base_signature
                and support_signature(pminus, *minus, op) == base_signature,
                "dynamic-speed endpoint branch signature",
            )
            margin_plus = strict_support(pplus, *plus, op)
            margin_minus = strict_support(pminus, *minus, op)
            need(
                word(pplus[0][QI_UNRESOLVED_TOP].item())
                == word(q_sed[QI_UNRESOLVED_TOP].item())
                and word(pminus[0][QI_UNRESOLVED_TOP].item())
                == word(q_sed[QI_UNRESOLVED_TOP].item()),
                "unresolved QI level excluded from selected seed support",
            )
            xp, xm = plus[active][k].item(), minus[active][k].item()
            gap = xp - xm
            need(gap != 0.0, "represented producer input gap")
            yplus, yminus = dyn_fn(*plus).detach(), dyn_fn(*minus).detach()
            secant = seed[active][k] * (yplus - yminus) / gap
            scaled = torch.max(
                torch.abs(secant - j_dynamic)
                / torch.clamp(torch.abs(j_dynamic), min=1.0)
            ).item()
            # The interior producer follows x**a or x**(1-a). Its centered
            # truncation is <=~0.1852*h*h relative to the local derivative;
            # at the smallest h, output/producer rounding can dominate.
            bound = 0.25 * h * h + (3.0e-8 if h == 1.0e-5 else 0.0)
            need(
                scaled < bound,
                f"represented dynamic-speed FD/JVP {label} h={h}: {scaled}",
            )
            speed_plus = ice_speeds(
                *plus, op["den"], op["dend"], op["delz_safe"], params
            )[:2]
            speed_minus = ice_speeds(
                *minus, op["den"], op["dend"], op["delz_safe"], params
            )[:2]
            speed_fd = [
                seed[active][k].item()
                * (speed_plus[i][k].item() - speed_minus[i][k].item())
                / gap
                for i in range(2)
            ]
            speed_error = max(
                abs(speed_fd[i] - speed_seed[i][k].item())
                / max(1.0e-9, abs(speed_seed[i][k].item()))
                for i in range(2)
            )
            # Speed itself follows q**a or n**(-a). The latter has a
            # centered-secant coefficient ~0.5185*h*h, larger than the
            # final number-flux curvature after multiplication by n.
            speed_bound = 0.6 * h * h + (3.0e-8 if h == 1.0e-5 else 0.0)
            need(
                speed_error < speed_bound,
                f"represented ice-speed producer FD/JVP {label} h={h}: {speed_error}",
            )
            signal_ulps = [
                abs(yplus[i].item() - yminus[i].item())
                / math.ulp(fixed[list(TARGET_TOP)][i].item())
                for i in range(4)
            ]
            fd.append(
                {
                    "h": h,
                    "input_plus": xp,
                    "input_minus": xm,
                    "actual_gap": gap,
                    "output_plus": yplus.tolist(),
                    "output_minus": yminus.tolist(),
                    "fd": secant.tolist(),
                    "max_scaled_fd_minus_jvp": scaled,
                    "acceptance_scaled_bound": bound,
                    "output_signal_ulps": signal_ulps,
                    "speed_plus_at_source": [speed_plus[i][k].item() for i in range(2)],
                    "speed_minus_at_source": [
                        speed_minus[i][k].item() for i in range(2)
                    ],
                    "speed_fd_at_source": speed_fd,
                    "speed_max_relative_fd_minus_jvp": speed_error,
                    "speed_acceptance_scaled_bound": speed_bound,
                    "branch_signature_plus": support_signature(pplus, *plus, op),
                    "branch_signature_minus": support_signature(pminus, *minus, op),
                    "speed_lambda23_plus": pplus[10]["lambda_raw"][K - 23].item(),
                    "speed_lambda23_minus": pminus[10]["lambda_raw"][K - 23].item(),
                    "snap_b_min_margin": min(
                        min(x[str(level)]["snap_b_low_gap"] for level in TARGET_NATIVE)
                        for x in (margin_plus, margin_minus)
                    ),
                }
            )
        directions[label] = {
            "seed_value": seed[active][k].item(),
            "speed_jvp_at_source": [speed_seed[i][k].item() for i in range(2)],
            "speed_analytic_at_source": speed_expected,
            "fixed_speed_jvp": j_fixed.tolist(),
            "dynamic_speed_jvp": j_dynamic.tolist(),
            "producer_path_delta": (j_dynamic - j_fixed).tolist(),
            "analytic_dynamic": analytic_dynamic[label],
            "finite_differences": fd,
        }
    cotangent = torch.tensor((0.4, -0.6, 0.7, -0.3), dtype=torch.float64)
    q_leaf, n_leaf = q0.clone().requires_grad_(True), n0.clone().requires_grad_(True)
    vjp_q, vjp_n = torch.autograd.grad(
        final(q_leaf, n_leaf, dynamic_speed=True),
        (q_leaf, n_leaf),
        grad_outputs=cotangent,
    )
    analytic_vjp = {}
    for label, (dq, dn) in seeds.items():
        level = 23 if "23" in label else 21
        k = K - level
        active_seed = dq[k].item() if "relative_q" in label else dn[k].item()
        analytic_vjp[label] = (
            sum(cotangent[i].item() * analytic_dynamic[label][i] for i in range(4))
            / active_seed
        )
        actual = vjp_q[k].item() if "relative_q" in label else vjp_n[k].item()
        need(
            math.isclose(actual, analytic_vjp[label], rel_tol=1e-12, abs_tol=1e-9),
            "independent weighted speed-producer VJP",
        )
    transpose = {}
    for label, (dq, dn) in seeds.items():
        j = directions[label]["dynamic_speed_jvp"]
        lhs = torch.dot(torch.tensor(j, dtype=torch.float64), cotangent).item()
        rhs = (torch.dot(dq, vjp_q) + torch.dot(dn, vjp_n)).item()
        need(
            math.isclose(lhs, rhs, rel_tol=1e-12, abs_tol=1e-10),
            "weighted dynamic JVP/VJP transpose",
        )
        transpose[label] = {"jvp_dot_weight": lhs, "seed_dot_vjp": rhs}
    result = {
        "schema": "kdm6.native_qnice_ice_speed_producer_ad.v1",
        "scientific_status": "INCONCLUSIVE",
        "physical_unit_status": "INCONCLUSIVE",
        "parent_capture_sha256": CAPTURE_SHA256,
        "source_attribution": sources,
        "baseline_speed_raw_bit_matches": baseline_speed_word_matches,
        "baseline_speed_max_relative_difference": baseline_speed_max_rel,
        "selected_active_speed_max_relative_difference": support_speed_max_rel,
        "baseline_dynamic_minus_fixed_c3_max_abs": dynamic_max_abs,
        "target_native_levels_1based": list(TARGET_NATIVE),
        "baseline_target_c3_ni": fixed[list(TARGET_TOP)].tolist(),
        "unresolved_qi_native_level_1based": 15,
        "unresolved_qi_sed_output": q_sed[QI_UNRESOLVED_TOP].item(),
        "unresolved_qi_snap_input": frozen_q15.item(),
        "baseline_speed_lambda": baseline_ice_speed_lambda,
        "baseline_branch_signature": base_signature,
        "baseline_support_margins": base_margins,
        "source_constants": {
            "pidni": params.pidni,
            "pvti": params.pvti,
            "pvtin": params.pvtin,
            "rslopeibmax": params.rslopeibmax,
            "inverse_dmi_f32": INV_DMI_F32,
            "den0": c.DEN0,
        },
        "directions": directions,
        "cotangent": cotangent.tolist(),
        "selected_vjp": {
            "q21": vjp_q[K - 21].item(),
            "ni21": vjp_n[K - 21].item(),
            "q23": vjp_q[K - 23].item(),
            "ni23": vjp_n[K - 23].item(),
        },
        "analytic_selected_vjp": analytic_vjp,
        "transpose_checks": transpose,
        "fixed_speed_parent_status": "conditional, producer derivative omitted",
        "native_full_process_derivative_certified": False,
    }
    saved = json.loads(pinned(SAVED_RESULT, SAVED_RESULT_SHA256))
    for key in (
        "schema",
        "scientific_status",
        "physical_unit_status",
        "parent_capture_sha256",
        "target_native_levels_1based",
        "baseline_target_c3_ni",
        "unresolved_qi_native_level_1based",
        "unresolved_qi_snap_input",
        "native_full_process_derivative_certified",
    ):
        need(result[key] == saved[key], "saved speed-producer reference: " + key)
    for key in ("pidni", "pvti", "pvtin", "inverse_dmi_f32", "den0"):
        need(
            result["source_constants"][key] == saved["source_constants"][key],
            "saved f32-derived speed constant: " + key,
        )
    need(
        math.isclose(
            result["source_constants"]["rslopeibmax"],
            saved["source_constants"]["rslopeibmax"],
            rel_tol=1e-6,
        ),
        "saved f32 dry-ice slope constant",
    )
    need(
        result["source_attribution"]["archived_source_sha256"]
        == saved["source_attribution"]["archived_source_sha256"],
        "saved archived speed source identities",
    )
    for key in (
        "cpp_build_receipt_sha256",
        "linked_slope_object_sha256",
        "linked_thermo_object_sha256",
        "oracle_under_test",
        "source_to_object_provenance",
    ):
        need(
            result["source_attribution"][key] == saved["source_attribution"][key],
            "saved speed producer source lineage: " + key,
        )
    for label in directions:
        for key in ("analytic_dynamic",):
            need(
                all(
                    math.isclose(x, y, rel_tol=1e-12, abs_tol=1e-10)
                    for x, y in zip(
                        result["directions"][label][key],
                        saved["directions"][label][key],
                    )
                ),
                "saved analytic producer direction",
            )
    return result


if __name__ == "__main__":
    print(json.dumps(replay(), indent=2, sort_keys=True))
    print("NATIVE_QNICE_ICE_SPEED_AD_REPLAY_PASSED")
