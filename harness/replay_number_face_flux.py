#!/usr/bin/env python3
"""Replay measured PD face transfers and host stores; not a positivity repair.

The local arithmetic helpers have no grid-size assumption. ``replay`` retains
an explicit schedule for this two-call, two-tile native regression so missing
records cannot redefine its coverage. Source files and NetCDF are not reread.
"""

import json
import math
from fractions import Fraction
from pathlib import Path

from replay_native_number import f32
from replay_negative_number_trace import fma32, rk_value

EVIDENCE = Path(__file__).parent / "evidence/number_face_flux_2026-09-24.json"
SPECIES = {"QNCLOUD": 3, "QNICE": 4, "QNRAIN": 6}
TARGETS = (
    ("QNCLOUD", 191, 6, 281),
    ("QNCLOUD", 204, 7, 281),
    ("QNCLOUD", 233, 4, 168),
    ("QNCLOUD", 233, 6, 164),
    ("QNCLOUD", 233, 12, 124),
    ("QNCLOUD", 233, 21, 160),
    ("QNICE", 30, 15, 281),
    ("QNICE", 67, 29, 2),
    ("QNICE", 184, 25, 281),
    ("QNICE", 233, 16, 272),
    ("QNICE", 233, 17, 180),
    ("QNICE", 233, 21, 81),
    ("QNRAIN", 233, 13, 116),
    ("QNRAIN", 233, 13, 142),
    ("QNRAIN", 233, 13, 150),
    ("QNRAIN", 233, 17, 93),
)
TAGS = ("PRE", "POST", "Z", "X", "Y")
HISTORY = {
    "original": "7d2afb3236ea6ea53a1df5c75f17b2b1da27f963ace697a8a912eda871c0f750",
    "normalized": "a065598b870815220ba36f7b2fbcdc6f65f8d69910c2e261961203b78d6683d8",
}


def scaled_faces(high, neighbor_budgets, eps):
    """Apply each face's one donor decision, including reversed z orientation.

    Budgets: self, west, east, south, north, bottom, top; each is
    (inside_limiter, stored_ph_low, stored_flux_out). A donor outside the
    limiter retains its face. This does not recalculate upstream high fluxes.
    """
    assert len(high) == 6 and len(neighbor_budgets) == 7 and eps > 0
    result = []
    for face, value in enumerate(high):
        outward = value < 0 if face in (0, 2, 5) else value > 0
        valid, available, offered = neighbor_budgets[0 if outward else face + 1]
        assert valid in (0, 1)
        scale = 1.0
        if valid and offered > available:
            scale = max(0.0, f32(available / f32(offered + eps)))
        result.append(f32(value * scale))
    return result


def divergence_stores(initial, high, low, rdzw, msftx, rdx, rdy):
    """Source-grouped binary32 differences and observed host fused subtraction.

    This host-object witness is separate from the KDM no-contraction contract.
    Return stored tendencies after Z, X and Y, not independently summed terms.
    """
    out = []
    value = initial
    for axis in (2, 0, 1):
        i = 2 * axis
        delta = f32(f32(f32(high[i + 1] - high[i]) + low[i + 1]) - low[i])
        factor = rdzw if axis == 2 else msftx
        term = delta if axis == 2 else f32((rdx if axis == 0 else rdy) * delta)
        value = fma32(-factor, term, value)
        out.append(value)
    return out


def exact_face_budget(pre, post):
    """Real-arithmetic budget of the *stored* binary32 face operands.

    Exact rational arithmetic separates face/limiter rounding already present
    in the operands from subsequent divergence/RK rounding. It is not an exact
    solution of advection or a physical particle-count budget.
    """
    p, q = [list(map(Fraction, values)) for values in (pre, post)]

    def divergence(x, start):
        face = x[start : start + 6]
        return x[8] * x[9] * (
            x[10] * (face[1] - face[0]) + x[11] * (face[3] - face[2])
        ) + x[9] * x[12] * (face[5] - face[4])

    storage = (p[6] * (p[4] + p[5]) + p[7]) * p[1]
    available = storage - p[13] * divergence(p, 23)
    final = storage - p[13] * (divergence(q, 17) + divergence(q, 23))
    return dict(
        low_order_numerator=float(available),
        stored_low_order_error=float(p[15] - available),
        post_face_numerator=float(final),
    )


def summary_key(x):
    return x["step"], x["rk"], x["stage"], x["field"], x["tile"], x["buffer"]


def expected_summaries():
    """Schedule from the executed configuration, never inferred from receipts."""
    expected = set()
    for step in (1, 2):
        for field in SPECIES:
            for stage in ("BEGIN", "MICRO_BEFORE", "MICRO_AFTER", "END"):
                expected.add((step, 0, stage, field, 0, 0))
            for tile in (1, 2):
                for rk in (1, 2, 3):
                    for stage in (
                        "RK_TEND_BEFORE",
                        "RK_TEND_AFTER",
                        "RK_BEFORE",
                        "RK_AFTER",
                        "FLOW_BC_BEFORE",
                        "FLOW_BC_AFTER",
                    ):
                        expected.add((step, rk, stage, field, tile, 0))
                    if rk < 3:
                        for suffix in ("BEFORE", "AFTER"):
                            expected.add(
                                (step, rk, "RK_PHYS_BC_" + suffix, field, tile, 0)
                            )
                for suffix in ("BEFORE", "AFTER"):
                    for buffer in (0, 1):
                        expected.add((step, 3, "RK_PD_" + suffix, field, tile, buffer))
                    expected.add((step, 3, "PD_OLD_PHYS_BC_" + suffix, field, tile, 1))
                    # Fortran DO rk_step ends at 4 after the three-stage loop.
                    expected.add((step, 4, "FINAL_PHYS_BC_" + suffix, field, tile, 0))
    return expected


def check_summaries(rows, events):
    keys = [summary_key(x) for x in rows]
    assert len(keys) == len(set(keys)) and set(keys) == expected_summaries()
    transitions = {}
    for event in events:
        if event["record_kind"] == "TRANSITION":
            transitions.setdefault(summary_key(event), []).append(event)
    assert set(transitions) <= set(keys)
    for x in rows:
        assert x["rank"] == 0
        assert x["selected"] == (0 if x["tile"] == 0 else SPECIES[x["field"]])
        assert x["i0"] == x["k0"] == 1 and x["i1"] == 234 and x["k1"] == 39
        j0, j1 = (
            (1, 282) if x["tile"] == 0 else ((1, 142) if x["tile"] == 1 else (143, 282))
        )
        assert (x["j0"], x["j1"]) == (j0, j1)
        size = 234 * 39 * (j1 - j0 + 1)
        assert x["owned"] == x["finite"] == size and x["nonfinite"] == 0
        assert 0 <= x["new_negative"] <= x["negative"] <= size
        assert 0 <= x["recovered"] <= size and 0 <= x["first_sample"] <= size
        assert x["first_new_valid"] == (x["new_negative"] > 0)
        assert (x["min"] < 0) == (x["negative"] > 0)
        assert x["negative_abs_sum"] >= 0 and x["pressure_weighted_deficit"] >= 0
        if x["new_negative"]:
            assert x["first_new_previous"] >= 0 > x["first_new_value"]
            assert j0 <= x["first_new_j"] <= j1 and 1 <= x["first_new_i"] <= 234
            assert 1 <= x["first_new_k"] <= 39
        top = transitions.get(summary_key(x), [])
        assert len(top) == min(8, x["new_negative"])
        coords = [(e["i"], e["k"], e["j"]) for e in top]
        assert len(coords) == len(set(coords))
        assert top == sorted(top, key=lambda e: (e["value"], e["k"], e["j"], e["i"]))
        for e in top:
            assert e["rank"] == 0 and e["species"] == SPECIES[e["field"]]
            assert e["selected"] == x["selected"]
            assert e["previous"] >= 0 > e["value"] >= x["min"]
            assert j0 <= e["j"] <= j1 and 1 <= e["i"] <= 234 and 1 <= e["k"] <= 39
            assert e["negative_abs"] == -e["value"]
            assert e["pressure_weight"] > 0
            assert (
                e["pressure_weighted_deficit"]
                == e["pressure_weight"] * e["negative_abs"]
            )
    return {
        x["field"]: x["negative"]
        for x in rows
        if x["step"] == 2 and x["stage"] == "END"
    }


def finite_tree(x):
    if isinstance(x, dict):
        for v in x.values():
            finite_tree(v)
    elif isinstance(x, list):
        for v in x:
            finite_tree(v)
    elif isinstance(x, float):
        assert math.isfinite(x), "nonfinite evidence"


def replay(data):
    if not __debug__:
        raise RuntimeError("assertions must remain enabled")
    assert data["schema"] == "number-face-flux-v1"
    finite_tree(data)
    for flag in (
        "operational_fix_applied",
        "physical_number_basis_resolved",
        "accepted_observation_cost",
        "positivity_approved",
    ):
        assert data[flag] is False
    assert set(data["variants"]) == set(HISTORY)
    assert data["provenance"]["advect_source"]["stripped_exact"] is True
    assert data["provenance"]["solver_source"]["stripped_exact"] is True
    results = {}
    for variant, d in data["variants"].items():
        proof = d["noninterference"]
        assert (
            proof["control_history_sha256"]
            == proof["capture_history_sha256"]
            == HISTORY[variant]
        )
        assert proof["inputs_equal"] and proof["effective_namelist_equal"]
        assert (
            proof["run_valid"]["model_completed"]
            and proof["run_valid"]["experiment_valid"]
        )
        assert proof["run_valid"]["exit_code"] == 0
        cfg = d["config"]
        assert len(cfg) == 12 and len({tuple(x[:4]) for x in cfg}) == 12
        assert {tuple(x[:4]) for x in cfg} == {
            (s, 3, sp, t) for s in (1, 2) for sp in SPECIES.values() for t in (1, 2)
        }
        for c in cfg:
            assert c[4:10] == [1, 235, 1, 283, 1, 40]
            assert c[10:16] == (
                [2, 233, 2, 143, 1, 39] if c[3] == 1 else [2, 233, 142, 281, 1, 39]
            )
            assert c[16:26] == [5, 3, 1, 0, 0, 0, 0, 0, 0, 0]
            assert c[26:] == ([1, 1, 1, 0] if c[3] == 1 else [1, 1, 0, 1])
        rows = {}
        for a in d["flux"]:
            assert len(a) == 112
            tag, step, rk, species, tile, target, i, k, j = a[:9]
            assert 1 <= target <= 16
            field, xi, xk, xj = TARGETS[target - 1]
            assert (i, k, j, species) == (xi, xk, xj, SPECIES[field]) and rk == 3
            assert tile == (1 if j <= 142 else 2)
            key = tag, step, target
            assert key not in rows
            rows[key] = a[9:]
            assert all(f32(v) == v for v in a[9:])
        assert set(rows) == {
            (tag, step, t) for tag in TAGS for step in (1, 2) for t in range(1, 17)
        }
        operands = {}
        for e in d["events"]:
            assert e["record_kind"] in ("TRANSITION", "RK_OPERAND", "PD_OLD_OPERAND")
            if e["record_kind"] == "TRANSITION":
                continue
            assert e["rank"] == 0 and e["species"] == SPECIES[e["field"]]
            assert e["selected"] == e["species"]
            assert e["tile"] == (1 if e["j"] <= 142 else 2)
            assert e["buffer"] == int(e["record_kind"] == "PD_OLD_OPERAND")
            assert (e["field"], e["i"], e["k"], e["j"]) in TARGETS
            key = (
                e["record_kind"],
                e["step"],
                e["rk"],
                e["stage"],
                e["field"],
                e["i"],
                e["k"],
                e["j"],
            )
            assert key not in operands
            operands[key] = e
        expected = set()
        for field, i, k, j in TARGETS:
            for step in (1, 2):
                for rk in (1, 2, 3):
                    for suffix in ("BEFORE", "AFTER"):
                        expected.add(
                            ("RK_OPERAND", step, rk, "RK_" + suffix, field, i, k, j)
                        )
                for suffix in ("BEFORE", "AFTER"):
                    expected.add(
                        ("PD_OLD_OPERAND", step, 3, "RK_PD_" + suffix, field, i, k, j)
                    )
        assert set(operands) == expected
        n_updates = 0
        for key, b in operands.items():
            if not b["stage"].endswith("BEFORE"):
                continue
            after_key = (*key[:3], key[3].replace("BEFORE", "AFTER"), *key[4:])
            a = operands[after_key]
            x = dict(
                old=b["scalar_old"],
                rk=b["rk"],
                value=b["value"],
                mu_old=b["mu1"],
                mu_new=b["mu2"],
                mu_base=b["mub"],
                c1=b["c1h"],
                c2=b["c2h"],
                advect_tend=b["advect_tend"],
                msfty=b["msfty"],
                sc_tend=b["scalar_tend"],
                dt=b["dt_rk"],
                i=b["i"],
                j=b["j"],
            )
            assert rk_value(x, pd=key[0] == "PD_OLD_OPERAND") == a["value"]
            n_updates += 1
        budgets = []
        for step in (1, 2):
            for t, (field, i, k, j) in enumerate(TARGETS, 1):
                pre, post, z, x, y = (rows[tag, step, t] for tag in TAGS)
                assert pre[:3] == post[:3] and pre[3:17] == post[3:17]
                assert pre[23:] == post[23:]
                budget = [pre[p : p + 3] for p in range(29, 50, 3)]
                assert budget[0] == [1, pre[15], pre[16]]
                assert pre[70] == pre[72] == int(pre[16] > pre[15])
                expected_scale = (
                    max(0, f32(pre[15] / f32(pre[16] + pre[14]))) if pre[70] else 0
                )
                assert pre[71] == expected_scale
                assert scaled_faces(pre[17:23], budget, pre[14]) == post[17:23]
                for value in (z, x, y):
                    assert value[:2] == post[:2] and value[3:] == post[3:]
                assert divergence_stores(
                    post[2],
                    post[17:23],
                    post[23:29],
                    *[post[p] for p in (12, 8, 10, 11)],
                ) == [z[2], x[2], y[2]]
                b = operands["RK_OPERAND", step, 3, "RK_BEFORE", field, i, k, j]
                assert b["advect_tend"] == y[2]
                assert b["value"] == pre[0] and b["scalar_old"] == pre[1]
                assert b["scalar_tend"] == 0 and b["dt_rk"] == pre[13]
                budgets.append(
                    dict(step=step, target=t, **exact_face_budget(pre, post))
                )
        assert budgets == d["exact_stored_face_budgets"]
        history = d["history_negative_cells"]
        assert len(history) == 3 and history[:2] == [[], []]
        edge_events = [
            e
            for e in d["events"]
            if e["record_kind"] == "TRANSITION"
            and e["step"] == 2
            and e["rk"] == 3
            and e["stage"] == "FLOW_BC_AFTER"
        ]

        def cell_key(e):
            return e["field"], e["i"], e["k"], e["j"], e["value"]

        assert len(history[2]) == len({cell_key(e) for e in history[2]})
        assert {cell_key(e) for e in history[2]} == {cell_key(e) for e in edge_events}
        for x in d["summaries"]:
            if x["step"] == 2 and x["stage"] in ("MICRO_AFTER", "END"):
                assert x["negative"] == sum(
                    e["field"] == x["field"] for e in history[2]
                )
        for e in history[2]:
            i, j = e["i"], e["j"]
            assert i == 234 or j in (1, 282)
            di, dj = (i - 1, j) if i == 234 else (i, j + 1 if j == 1 else j - 1)
            donor = operands["RK_OPERAND", 2, 3, "RK_AFTER", e["field"], di, e["k"], dj]
            assert donor["value"] == e["value"]
        results[variant] = dict(
            face_values=192,
            directional_stores=96,
            host_updates=n_updates,
            final_negative_counts=check_summaries(d["summaries"], d["events"]),
        )
    return dict(
        scope="arithmetic_replay_only",
        variants=results,
        operational_fix_applied=False,
        positivity_approved=False,
        accepted_observation_cost=False,
    )


if __name__ == "__main__":
    print(json.dumps(replay(json.loads(EVIDENCE.read_text())), indent=2))
