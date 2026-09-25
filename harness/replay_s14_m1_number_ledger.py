"""Replay a fixed 600 s, single-column mp37 applied rain-number ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from collections import defaultdict
from pathlib import Path
from typing import Any

from harness.replay_s2_number_trace import (
    INPUT_SHA256,
    SOURCE_SHA256,
    TraceError,
    _verify_budget_updates,
    _verify_nraut,
    _verify_nr_caps,
    f32,
    f32_add,
    f32_div,
    f32_mul,
    f32_sub,
    parse_capture,
)

SCHEMA = "s14-m1-native-number-v1"
CELL = {"host_j": 153, "host_i": 144}
EXPECTED_STEPS = tuple(range(1, 31))
EXPECTED_CAPTURE_SHA256 = "56b4d91c4a4e4b35d7324ebc1b3a8e836427fa87db6533976ddf4c43ba68f6f4"
EXPECTED_CAPTURE_RECORDS = 25235
EXPECTED_CAPTURE_TAG_SCHEMA_SHA256 = "537de99a429d067c06c492ceaa1761ea8987a30b0975aaf6b1e89b4d901df641"
EXPECTED_TRANSPORT_GROUPS = 95
EXPECTED_ACTIVE_INTERFACE_OCCURRENCES = 1480
EXPECTED_MSTEP_BY_STEP = {
    1: 1, 2: 1, 3: 1, 4: 1, 5: 1, 6: 1,
    7: 2, 8: 2, 9: 3, 10: 6, 11: 6, 12: 5, 13: 5, 14: 5, 15: 5,
    16: 4, 17: 4, 18: 4, 19: 4, 20: 4,
    21: 3, 22: 3, 23: 3, 24: 3, 25: 3, 26: 3, 27: 3, 28: 3, 29: 3, 30: 3,
}
EXPECTED_CONTROL_EXE = "36bdabe26a1b5613bc25e9107f2118766dafb393dc49ba19027864da57492cd7"
EXPECTED_CAPTURE_EXE = "1fad13519d90729a3eccdad47051dcc7f05c55967abcb8df46b49e5d6169f5b5"
EXPECTED_HISTORY_SHA256 = "154ab800148c98fb16abb143665ad7d737b1537af87bab3fb5638803cbc705c9"
EXPECTED_HISTORY_BYTES = 635852228
EXPECTED_STRICT_REPORT_SHA256 = "d3150c00643e63cd0a733a80b3506b300245b77ff8ccab168a46677610966085"
EXPECTED_RUNNER_SHA256 = "175ade71058672b957d565ef88ffd7925bc7d74dfe559c36aaec61fa8de0d96e"
EXPECTED_NAMELIST_SHA256 = "f452ca5161987852c78e1bbdf3f00457f6f0f080e3f515e49783527e38f71f10"
EXPECTED_RUNS = {
    "control": {
        "run_id": "mp37_s14_m1_600_control_10min_hist10_20260925_193113_p15708",
        "campaign_id": "3bd06d32ca797fd7211bc8158c9ad11d978a025e29101e9469a3ccaaba628377",
    },
    "capture": {
        "run_id": "mp37_s14_m1_600_capture_10min_hist10_20260925_193504_p21441",
        "campaign_id": "4dceaccf65e3a4fe74d1c4c6786b2749bcbe95806bc2ce3b4143cff3b7f8d67b",
    },
}
EXPECTED_BDY_SHA256 = "d46e5d7117c076956d130b4ff905fc34a5d53dbd5a0d9571311582b0a60c5e6c"
EXPECTED_CHAIN_SHA256 = "c8e300d2aa52f98c9060803438ab6f796bddd1e1cdd6b75a14e39a398cb0c4e3"
EXPECTED_INPUT_SET = {
    "wrfinput_d01": INPUT_SHA256,
    "wrfbdy_d01": EXPECTED_BDY_SHA256,
    "wrfchainp_d01": EXPECTED_CHAIN_SHA256,
}
EXPECTED_HISTORY_TIMES = ["2025-07-19_00:00:00", "2025-07-19_00:10:00"]
EXPECTED_WARM_LEVELS = tuple(range(16, 40))
EXPECTED_COLD_LEVELS = tuple(range(1, 16))


def _rowmap(rows: list[dict[str, Any]], tag: str) -> dict[tuple[int, ...], dict[str, Any]]:
    return {r["key"][1:]: r for r in rows if r["tag"] == tag}


def _require_steps_and_host_layers(rows: list[dict[str, Any]]) -> None:
    expected = {(step, CELL["host_j"], CELL["host_i"], 0, 0, level)
                for step in EXPECTED_STEPS for level in range(1, 40)}
    for tag in ("HOST_ENTRY", "HOST_RETURN", "KERNEL_ENTRY", "KERNEL_RETURN"):
        actual = {r["key"][1:] for r in rows if r["tag"] == tag}
        if actual != expected:
            raise TraceError(f"{tag} does not cover every predeclared step/level")
    expected_column_keys = {(step, 153, 144, 1, 0, level)
                            for step in EXPECTED_STEPS for level in range(1, 40)}
    for tag in ("DSD_PRE_GATE", "DSD_POSTFREEZE_GATE", "DSD_FINAL_GATE",
                "NRAUT_GATE", "NR_MAX_GATE"):
        actual = {r["key"][1:] for r in rows if r["tag"] == tag}
        if actual != expected_column_keys:
            raise TraceError(f"{tag} lacks the full predeclared step/level census")


def _verify_threshold_flags(rows: list[dict[str, Any]]) -> dict[str, int]:
    checked: dict[str, int] = {}
    for tag in ("DSD_PRE_GATE", "DSD_POSTFREEZE_GATE", "DSD_FINAL_GATE"):
        selected = [r for r in rows if r["tag"] == tag]
        for row in selected:
            v = row["f32"]
            expected = (v["qrs(i,k,1)"] >= v["qcrmin"]
                        and v["nrs(i,k,1)"] >= v["nrmin"])
            flag = "qrs(i,k,1).ge.qcrmin .and. nrs(i,k,1).ge.nrmin"
            if bool(row["flags"][flag]) != expected:
                raise TraceError(f"{tag} threshold flag differs at {row['key']}")
        checked[tag] = len(selected)
    maximum = [r for r in rows if r["tag"] == "NR_MAX_GATE"]
    for row in maximum:
        v = row["f32"]
        if bool(row["flags"]["nrs(i,k,1).gt.nrmax"]) != \
                (v["nrs(i,k,1)"] > v["nrmax"]):
            raise TraceError(f"NR_MAX_GATE threshold flag differs at {row['key']}")
    checked["NR_MAX_GATE"] = len(maximum)
    gates = [r for r in rows if r["tag"] == "NRAUT_GATE"]
    for row in gates:
        v = row["f32"]
        if (bool(row["flags"]["qci(i,k,1).gt.qcr(i,k)"]) !=
                (v["qci(i,k,1)"] > v["qcr(i,k)"]) or
                bool(row["flags"]["nci(i,k,1).gt.ncmin"]) !=
                (v["nci(i,k,1)"] > v["ncmin"])):
            raise TraceError(f"NRAUT_GATE threshold flag differs at {row['key']}")
    checked["NRAUT_GATE"] = len(gates)
    dsd_branches = [r for r in rows if r["tag"] == "NRAUT_DSD_BRANCH"]
    for row in dsd_branches:
        v = row["f32"]
        if bool(row["flags"]["qrs(i,k,1).gt.lenconcr"]) != \
                (v["qrs(i,k,1)"] > v["lenconcr"]):
            raise TraceError(f"NRAUT DSD branch flag differs at {row['key']}")
    checked["NRAUT_DSD_BRANCH"] = len(dsd_branches)
    return checked


def _verify_branch_event_census(rows: list[dict[str, Any]]) -> None:
    warm_tags = ("NR_LIMIT_PRE", "NR_LIMIT_POST",
                 "NR_UPDATE_WARM_PRE", "NR_UPDATE_WARM_POST")
    cold_tags = ("NR_LIMIT_COLD_PRE", "NR_LIMIT_COLD_POST",
                 "NR_UPDATE_COLD_PRE", "NR_UPDATE_COLD_POST")
    for tags, levels, label in ((warm_tags, EXPECTED_WARM_LEVELS, "warm"),
                                (cold_tags, EXPECTED_COLD_LEVELS, "cold")):
        expected = {(step, 153, 144, 1, 0, level)
                    for step in EXPECTED_STEPS for level in levels}
        sets = {}
        for tag in tags:
            actual = {r["key"][1:] for r in rows if r["tag"] == tag}
            if actual != expected:
                raise TraceError(f"{label} branch event census differs for {tag}")
            sets[tag] = actual
        if len({frozenset(value) for value in sets.values()}) != 1:
            raise TraceError(f"{label} cap/update branch event keys are not cross-linked")


def _verify_s14_boundary(rows: list[dict[str, Any]]) -> dict[str, int]:
    host_in, local_in = _rowmap(rows, "HOST_ENTRY"), _rowmap(rows, "KERNEL_ENTRY")
    local_out, host_out = _rowmap(rows, "KERNEL_RETURN"), _rowmap(rows, "HOST_RETURN")
    if not (set(host_in) == set(local_in) == set(local_out) == set(host_out)):
        raise TraceError("host/kernel boundary event keys differ")
    clamped = {"nr": 0, "qr": 0, "qc": 0}
    entry_fields = (("nr(i,k,j)", "nrs(i,k,1)", "nr"),
                    ("qr(i,k,j)", "qrs(i,k,1)", "qr"),
                    ("qc(i,k,j)", "qci(i,k,1)", "qc"))
    for key, h in host_in.items():
        k = local_in[key]
        for host_name, local_name, label in entry_fields:
            expected = max(h["f32"][host_name], 0.0)
            if struct.pack(">f", f32(expected)).hex().upper() != \
                    k["f32_bits"][local_name]:
                raise TraceError(f"host/kernel entry {host_name} normalization differs at {key}")
            clamped[label] += h["f32"][host_name] < 0.0
        for host_name, local_name in (("q(i,k,j)", "q(i,k)"),
                                      ("den(i,k,j)", "den(i,k)"),
                                      ("delz(i,k,j)", "delz(i,k)")):
            if h["f32_bits"][host_name] != k["f32_bits"][local_name]:
                raise TraceError(f"host/kernel entry {host_name} differs at {key}")
    for key, local in local_out.items():
        host = host_out[key]
        for host_name, local_name in (("nr(i,k,j)", "nrs(i,k,1)"),
                                      ("qr(i,k,j)", "qrs(i,k,1)"),
                                      ("qc(i,k,j)", "qci(i,k,1)"),
                                      ("q(i,k,j)", "q(i,k,j)"),
                                      ("den(i,k,j)", "den(i,k,j)"),
                                      ("delz(i,k,j)", "delz(i,k,j)")):
            if host["f32_bits"][host_name] != local["f32_bits"][local_name]:
                raise TraceError(f"kernel/host return {host_name} differs at {key}")
    return {"steps": len({key[0] for key in host_in}),
            "host_entry_layers": len(host_in), "host_return_layers": len(host_out),
            "entry_negative_clamps": clamped}


def _verify_face_group(rows: list[dict[str, Any]], key: tuple[int, int, int]) -> dict[str, Any]:
    step, loop, sub = key
    face_pre = {r["level"]: r for r in rows if r["tag"] == "NR_FACE_PRE"
                and (r["step"], r["outer_loop"], r["substep"]) == key}
    face_post = {r["level"]: r for r in rows if r["tag"] == "NR_FACE_POST"
                 and (r["step"], r["outer_loop"], r["substep"]) == key}
    top_pre = {r["level"]: r for r in rows if r["tag"] == "NR_TOP_PRE"
               and (r["step"], r["outer_loop"], r["substep"]) == key}
    top_post = {r["level"]: r for r in rows if r["tag"] == "NR_TOP_POST"
                and (r["step"], r["outer_loop"], r["substep"]) == key}
    if set(face_pre) != set(range(1, 39)) or set(face_post) != set(range(1, 39)):
        raise TraceError(f"step/loop/substep {key} lacks all 38 internal-face rows")
    if set(top_pre) != {39} or set(top_post) != {39}:
        raise TraceError(f"step/loop/substep {key} lacks paired top-cell rows")

    def state(level: int) -> tuple[dict[str, Any], dict[str, Any]]:
        return ((top_pre[level], top_post[level]) if level == 39
                else (face_pre[level], face_post[level]))

    # Check exact source-order applied caps and stores at all internal faces.
    for level in range(1, 39):
        pre, post = face_pre[level], face_post[level]
        v = pre["f32"]
        out_offer = f32_mul(v["falkn(i,k,1)"], v["dtcld"])
        in_offer = f32_mul(f32_div(
            f32_mul(v["falkn(i,k+1,1)"], v["delz(i,k+1)"]),
            v["delz(i,k)"]), v["dtcld"])
        out_applied = min(out_offer, v["nrs(i,k,1)"])
        in_applied = min(in_offer, v["nrs(i,k+1,1)"])
        for name, expected in (("dnr(i,k)", out_applied), ("dnr(i,k+1)", in_applied)):
            if struct.pack(">f", f32(expected)).hex().upper() != pre["f32_bits"][name]:
                raise TraceError(f"applied number cap {name} differs at {pre['key']}")
        qr_out = min(f32_div(f32_mul(v["falk(i,k,1)"], v["dtcld"]),
                             v["dend(i,k)"]), v["qrs(i,k,1)"])
        qr_in_offer = f32_div(f32_mul(f32_div(
            f32_mul(v["falk(i,k+1,1)"], v["delz(i,k+1)"]),
            v["delz(i,k)"]), v["dtcld"]), v["dend(i,k)"])
        qr_in = min(qr_in_offer, v["qrs(i,k+1,1)"])
        for name, expected in (("dqr(i,k)", qr_out), ("dqr(i,k+1)", qr_in)):
            if struct.pack(">f", f32(expected)).hex().upper() != pre["f32_bits"][name]:
                raise TraceError(f"applied mass cap {name} differs at {pre['key']}")
        expected_state = max(f32_add(f32_sub(v["nrs(i,k,1)"], out_applied),
                                      in_applied), 0.0)
        if struct.pack(">f", f32(expected_state)).hex().upper() != \
                post["f32_bits"]["nrs(i,k,1)"]:
            raise TraceError(f"source-ordered face state differs at {pre['key']}")

    top, top_after = state(39)
    tv = top["f32"]
    top_offer = f32_mul(tv["falkn(i,k,1)"], tv["dtcld"])
    top_out = min(top_offer, tv["nrs(i,k,1)"])
    if struct.pack(">f", f32(max(f32_sub(tv["nrs(i,k,1)"], top_offer), 0.0))).hex().upper() != \
            top_after["f32_bits"]["nrs(i,k,1)"]:
        raise TraceError(f"top-cell source-ordered state differs at {top['key']}")

    names = ("dz_n", "rho_m_dz_n", "rho_d_dz_n")
    sums = {m: {k: 0.0 for k in ("density_metric", "cap_unmatched", "observed",
                                    "departure", "arrival")} for m in names}
    cap_counts = {"departure": 0, "arrival": 0}
    interfaces = []
    for lower_level in range(1, 39):
        lower = face_pre[lower_level]["f32"]
        upper_row, _ = state(lower_level + 1)
        upper = upper_row["f32"]
        out_offer = f32_mul(upper["falkn(i,k,1)"], upper["dtcld"])
        out = (min(out_offer, upper["nrs(i,k,1)"]) if lower_level + 1 == 39
               else upper["dnr(i,k)"])
        in_offer = f32_mul(f32_div(
            f32_mul(lower["falkn(i,k+1,1)"], lower["delz(i,k+1)"]),
            lower["delz(i,k)"]), lower["dtcld"])
        incoming = lower["dnr(i,k+1)"]
        upper_rhom, upper_qv, upper_dz = (
            upper["den(i,k)"], upper["q(i,k)"], upper["delz(i,k)"])
        lower_rhom, lower_qv, lower_dz = (
            lower["den(i,k)"], lower["q(i,k)"], lower["delz(i,k)"])
        weights = {
            "dz_n": (upper_dz, lower_dz),
            "rho_m_dz_n": (upper_rhom * upper_dz, lower_rhom * lower_dz),
            "rho_d_dz_n": (upper_rhom / (1.0 + upper_qv) * upper_dz,
                           lower_rhom / (1.0 + lower_qv) * lower_dz),
        }
        face = {"lower_level": lower_level, "upper_level": lower_level + 1,
                "dn_out": out, "dn_in": incoming,
                "dn_out_offer": out_offer, "dn_in_offer": in_offer,
                "dn_out_cap_remainder": out_offer - out,
                "dn_in_cap_remainder": in_offer - incoming,
                "upper_dz": upper_dz, "lower_dz": lower_dz,
                "upper_rho_m": upper_rhom, "lower_rho_m": lower_rhom,
                "upper_rho_d_conditional": upper_rhom / (1.0 + upper_qv),
                "lower_rho_d_conditional": lower_rhom / (1.0 + lower_qv),
                "residuals": {}}
        for measure, (wu, wl) in weights.items():
            density = wl * in_offer - wu * out_offer
            cap = wl * (incoming - in_offer) - wu * (out - out_offer)
            observed = wl * incoming - wu * out
            sums[measure]["density_metric"] += density
            sums[measure]["cap_unmatched"] += cap
            sums[measure]["observed"] += observed
            sums[measure]["departure"] += wu * out
            sums[measure]["arrival"] += wl * incoming
            face["residuals"][measure] = {
                "density_metric": density, "cap_unmatched": cap, "observed": observed}
        if out < out_offer:
            cap_counts["departure"] += 1
        if incoming < in_offer:
            cap_counts["arrival"] += 1
        if any((out_offer, in_offer, out, incoming)):
            interfaces.append(face)

    state_delta = {m: 0.0 for m in names}
    round_sum = {m: 0.0 for m in names}
    raw_state_delta = 0.0
    for level in range(1, 40):
        pre, post = state(level)
        v = pre["f32"]
        after = post["f32"]["nrs(i,k,1)"]
        if level == 39:
            out, incoming = top_out, 0.0
        else:
            out, incoming = v["dnr(i,k)"], v["dnr(i,k+1)"]
        round_error = float(after) - (float(v["nrs(i,k,1)"]) - float(out) + float(incoming))
        raw_state_delta += float(after) - float(v["nrs(i,k,1)"])
        weights = {
            "dz_n": v["delz(i,k)"],
            "rho_m_dz_n": v["den(i,k)"] * v["delz(i,k)"],
            "rho_d_dz_n": v["den(i,k)"] / (1.0 + v["q(i,k)"]) * v["delz(i,k)"],
        }
        for measure, weight in weights.items():
            state_delta[measure] += weight * (float(after) - float(v["nrs(i,k,1)"]))
            round_sum[measure] += weight * round_error

    bottom = face_pre[1]["f32"]
    bottom_out = bottom["dnr(i,k)"]
    bottom_export = {
        "dz_n": bottom["delz(i,k)"] * bottom_out,
        "rho_m_dz_n": bottom["den(i,k)"] * bottom["delz(i,k)"] * bottom_out,
        "rho_d_dz_n": bottom["den(i,k)"] / (1.0 + bottom["q(i,k)"])
                       * bottom["delz(i,k)"] * bottom_out,
    }
    for measure in names:
        closure = state_delta[measure] - sums[measure]["observed"] + bottom_export[measure]
        error = closure - round_sum[measure]
        if abs(error) > 1e-8 * max(1.0, abs(closure), abs(round_sum[measure])):
            raise TraceError(f"{measure} closure differs from source-order rounding at {key}")
        sums[measure].update({
            "bottom_export": bottom_export[measure],
            "inventory_delta": state_delta[measure],
            "source_ordered_store_rounding": round_sum[measure],
            "ledger_closure": closure,
            "closure_minus_rounding": error,
        })
    return {"step": step, "outer_loop": loop, "substep": sub,
            "levels": 39, "internal_faces": 38,
            "mstep": int(top["i32"]["mstep(i)"]),
            "active_interface_count": len(interfaces),
            "raw_inventory_delta_unweighted": raw_state_delta,
            "active_interfaces": interfaces, "cap_counts": cap_counts,
            "bottom_export_number": bottom_out,
            "measures": sums}


def _source_events(rows: list[dict[str, Any]]) -> dict[str, Any]:
    results: dict[str, list[dict[str, Any]]] = {
        "snow_melt": [], "graupel_melt": [], "rain_freeze_sink": []}
    pairs = (("snow_melt", "NR_SNOW_MELT_PRE", "NR_SNOW_MELT_POST",
              "sfac", "psmlt(i,k)", "qrs(i,k,2)"),
             ("graupel_melt", "NR_GRAUPEL_MELT_PRE", "NR_GRAUPEL_MELT_POST",
              "gfac", "pgmlt(i,k)", "qrs(i,k,3)"))
    for name, pre_tag, post_tag, factor, rate, reservoir in pairs:
        pre, post = _rowmap(rows, pre_tag), _rowmap(rows, post_tag)
        if set(pre) != set(post):
            raise TraceError(f"{pre_tag}/{post_tag} event keys differ")
        for key, before in pre.items():
            v = before["f32"]
            if not v[reservoir] > v["qcrmin"]:
                raise TraceError(f"{name} floor gate inactive at {key}")
            expected = f32_sub(v["nrs(i,k,1)"], f32_mul(v[factor], v[rate]))
            after = post[key]
            if struct.pack(">f", expected).hex().upper() != after["f32_bits"]["nrs(i,k,1)"]:
                raise TraceError(f"{name} source-order update differs at {key}")
            delta = after["f32"]["nrs(i,k,1)"] - v["nrs(i,k,1)"]
            if delta > 0:
                results[name].append({"step": before["step"], "level": before["level"],
                                      "applied_nr_increment": delta,
                                      "applied_mass_melt_rate": v[rate]})
    pre, post = _rowmap(rows, "NR_FREEZE_PRE"), _rowmap(rows, "NR_FREEZE_POST")
    if set(pre) != set(post):
        raise TraceError("NR_FREEZE_PRE/POST event keys differ")
    for key, before in pre.items():
        v = before["f32"]
        expected = f32(float(v["nrs(i,k,1)"]) - before["f64"]["nfrzdtr"])
        after = post[key]
        if struct.pack(">f", expected).hex().upper() != after["f32_bits"]["nrs(i,k,1)"]:
            raise TraceError(f"rain-freeze store differs at {key}")
        delta = after["f32"]["nrs(i,k,1)"] - v["nrs(i,k,1)"]
        if delta < 0:
            results["rain_freeze_sink"].append({"step": before["step"],
                                                "level": before["level"],
                                                "applied_nr_decrement": -delta})
    return {"counts": {key: len(value) for key, value in results.items()},
            "events": results}


def _call_process_ledger(rows: list[dict[str, Any]],
                         groups: list[dict[str, Any]],
                         source_events: dict[str, Any]) -> list[dict[str, Any]]:
    host_in, host_out = _rowmap(rows, "HOST_ENTRY"), _rowmap(rows, "HOST_RETURN")
    kernel_in, kernel_out = _rowmap(rows, "KERNEL_ENTRY"), _rowmap(rows, "KERNEL_RETURN")
    by_step: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for group in groups:
        by_step[group["step"]].append(group)
    update_tags = {
        "warm": ("NR_UPDATE_WARM_PRE", "NR_UPDATE_WARM_POST",
                 ("nraut(i,k)", "nrcol(i,k)", "niacr(i,k)", "nraci(i,k)",
                  "nsacr(i,k)", "ngacr(i,k)"), (1, -1, -1, -1, -1, -1)),
        "cold": ("NR_UPDATE_COLD_PRE", "NR_UPDATE_COLD_POST",
                 ("nraut(i,k)", "nrcol(i,k)", "nseml(i,k)", "ngeml(i,k)"),
                 (1, -1, 1, 1)),
    }
    source_by_step: dict[int, float] = defaultdict(float)
    for name, events in source_events["events"].items():
        for event in events:
            sign = -1.0 if name == "rain_freeze_sink" else 1.0
            source_by_step[event["step"]] += sign * event.get(
                "applied_nr_increment", event.get("applied_nr_decrement", 0.0))
    output = []
    for step in EXPECTED_STEPS:
        step_groups = sorted(by_step.get(step, []), key=lambda g: g["substep"])
        if not step_groups:
            raise TraceError(f"step {step} has no applied sedimentation group")
        msteps = {g["mstep"] for g in step_groups}
        substeps = {g["substep"] for g in step_groups}
        if len(msteps) != 1 or substeps != set(range(1, next(iter(msteps)) + 1)):
            raise TraceError(f"step {step} has incomplete or inconsistent mstep groups")
        first = step_groups[0]
        last = step_groups[-1]
        first_key = (step, first["outer_loop"], first["substep"])
        last_key = (step, last["outer_loop"], last["substep"])
        face_first = {r["level"]: r for r in rows if r["tag"] == "NR_FACE_PRE"
                      and (r["step"], r["outer_loop"], r["substep"]) == first_key}
        top_first = next(r for r in rows if r["tag"] == "NR_TOP_PRE"
                         and (r["step"], r["outer_loop"], r["substep"]) == first_key)
        face_last = {r["level"]: r for r in rows if r["tag"] == "NR_FACE_POST"
                     and (r["step"], r["outer_loop"], r["substep"]) == last_key}
        top_last = next(r for r in rows if r["tag"] == "NR_TOP_POST"
                        and (r["step"], r["outer_loop"], r["substep"]) == last_key)
        pre_sed_values = {k: (face_first[k] if k < 39 else top_first)
                          ["f32"]["nrs(i,k,1)"] for k in range(1, 40)}
        last_sed_values = {k: (face_last[k] if k < 39 else top_last)
                           ["f32"]["nrs(i,k,1)"] for k in range(1, 40)}
        pre_sed_sum = math.fsum(pre_sed_values.values())
        last_sed_sum = math.fsum(last_sed_values.values())
        sediment_delta = sum(g["raw_inventory_delta_unweighted"] for g in step_groups)
        host_entry_values = {k: host_in[(step, CELL["host_j"], CELL["host_i"], 0, 0, k)]
                             ["f32"]["nr(i,k,j)"] for k in range(1, 40)}
        kernel_entry_values = {k: kernel_in[(step, CELL["host_j"], CELL["host_i"], 0, 0, k)]
                               ["f32"]["nrs(i,k,1)"] for k in range(1, 40)}
        host_return_values = {k: host_out[(step, CELL["host_j"], CELL["host_i"], 0, 0, k)]
                              ["f32"]["nr(i,k,j)"] for k in range(1, 40)}
        kernel_return_values = {k: kernel_out[(step, CELL["host_j"], CELL["host_i"], 0, 0, k)]
                                ["f32"]["nrs(i,k,1)"] for k in range(1, 40)}
        host_entry_sum = math.fsum(host_entry_values.values())
        kernel_entry_sum = math.fsum(kernel_entry_values.values())
        host_return_sum = math.fsum(host_return_values.values())
        kernel_return_sum = math.fsum(kernel_return_values.values())
        if abs(last_sed_sum - pre_sed_sum - sediment_delta) > \
                1e-8 * max(1.0, abs(last_sed_sum), abs(pre_sed_sum)):
            raise TraceError(f"substep sedimentation state does not telescope at step {step}")
        update_summary = {}
        total_update_state = 0.0
        total_rate_amount = 0.0
        total_update_rounding = 0.0
        for label, (pre_tag, post_tag, fields, signs) in update_tags.items():
            pre_rows, post_rows = _rowmap(rows, pre_tag), _rowmap(rows, post_tag)
            state_delta = exact_amount = rounded_amount = 0.0
            count = 0
            for key, pre_row in pre_rows.items():
                if key[0] != step:
                    continue
                post_row = post_rows[key]
                v = pre_row["f32"]
                increment = v[fields[0]]
                exact_rate = float(v[fields[0]])
                for field, sign in zip(fields[1:], signs[1:]):
                    increment = (f32_add(increment, v[field]) if sign > 0
                                 else f32_sub(increment, v[field]))
                    exact_rate += sign * float(v[field])
                increment = f32_mul(increment, v["dtcld"])
                exact_amount += exact_rate * float(v["dtcld"])
                rounded_amount += increment
                state_delta += (post_row["f32"]["nrs(i,k,1)"]
                                - pre_row["f32"]["nrs(i,k,1)"])
                count += 1
            update_summary[label] = {
                "rows": count, "source_ordered_amount": rounded_amount,
                "real_arithmetic_rate_amount": exact_amount,
                "stored_state_delta": state_delta,
                "store_rounding_and_floor_remainder": state_delta - exact_amount,
            }
            total_update_state += state_delta
            total_rate_amount += rounded_amount
            total_update_rounding += state_delta - exact_amount
        entry_normalization_delta = math.fsum(
            kernel_entry_values[k] - host_entry_values[k] for k in range(1, 40))
        process_delta = math.fsum(
            pre_sed_values[k] - kernel_entry_values[k] for k in range(1, 40))
        late_process_delta = math.fsum(
            kernel_return_values[k] - last_sed_values[k] for k in range(1, 40))
        call_delta = math.fsum(
            host_return_values[k] - host_entry_values[k] for k in range(1, 40))
        call_closure = call_delta - (entry_normalization_delta + process_delta
                                     + sediment_delta + late_process_delta)
        if abs(call_closure) > 1e-8 * max(1.0, abs(host_return_sum), abs(host_entry_sum)):
            raise TraceError(f"host-call partition does not close at step {step}")
        output.append({
            "step": step,
            "mstep": next(iter(msteps)), "substeps": sorted(substeps),
            "host_entry_qnr_sum_raw": host_entry_sum,
            "kernel_entry_qnr_sum_after_nonnegative_normalization": kernel_entry_sum,
            "entry_normalization_delta_raw": entry_normalization_delta,
            "pre_sedimentation_qnr_sum_raw": pre_sed_sum,
            "within_call_process_delta_before_sedimentation_raw": process_delta,
            "direct_melt_and_freeze_source_delta_raw": source_by_step.get(step, 0.0),
            "warm_cold_rate_updates": update_summary,
            "warm_cold_stored_state_delta_raw": total_update_state,
            "warm_cold_source_ordered_rate_amount_raw": total_rate_amount,
            "warm_cold_store_rounding_and_floor_remainder_raw": total_update_rounding,
            "other_microphysics_threshold_remainder_raw":
                late_process_delta - source_by_step.get(step, 0.0) - total_update_state,
            "sedimentation_raw_inventory_delta": sediment_delta,
            "post_sedimentation_qnr_sum_raw": last_sed_sum,
            "within_call_process_delta_after_sedimentation_raw": late_process_delta,
            "host_return_qnr_sum_raw": host_return_sum,
            "kernel_return_qnr_sum_raw": kernel_return_sum,
            "within_call_host_entry_to_return_delta_raw": call_delta,
            "call_ledger_closure_raw": call_closure,
            "phase_order": "kernel entry → pre-sedimentation process state → applied sedimentation substeps → post-sedimentation process state → host return",
        })
    return output


def replay(evidence: dict[str, Any], capture_text: str,
           strict_report_text: str) -> dict[str, Any]:
    if evidence.get("schema") != SCHEMA:
        raise TraceError("wrong S14 M1 evidence schema")
    if evidence.get("physical_number_basis_resolved") is not False:
        raise TraceError("S14 evidence must keep the number basis unresolved")
    contract = evidence.get("run_contract", {})
    if (contract.get("mp_physics") != 37 or contract.get("run_seconds") != 600
            or contract.get("timestep_seconds") != 20
            or contract.get("expected_steps") != [1, 30]
            or contract.get("mpi_ranks") != 1
            or contract.get("actual_proc_grid") != "1x1"
            or contract.get("threads") != 1
            or contract.get("history_interval_minutes") != 10
            or contract.get("history_interval_seconds") != 0):
        raise TraceError("S14 requires the predeclared 600 s / 30 step mp37 run")
    if any(evidence.get("input_identity", {}).get(key) != value
           for key, value in (("wrfinput_d01_sha256", INPUT_SHA256),
                              ("wrfbdy_d01_sha256", EXPECTED_BDY_SHA256),
                              ("wrfchainp_d01_sha256", EXPECTED_CHAIN_SHA256))):
        raise TraceError("retained 5 km active input SHA set mismatch")
    source = evidence.get("source", {})
    if source.get("canonical_sha256") != SOURCE_SHA256 or source.get("capture_sha256") != \
            "5ceca0627c5be831f47c958e85b1ff2612fd9a50fd9bf1c3c40bf0ac6eb951c0":
        raise TraceError("canonical or instrumented mp37 source SHA mismatch")
    if evidence.get("capture", {}).get("sha256") != EXPECTED_CAPTURE_SHA256 or \
            hashlib.sha256(capture_text.encode()).hexdigest() != EXPECTED_CAPTURE_SHA256:
        raise TraceError("capture payload SHA differs from the S14 replay pin")
    records = sum(line.startswith("S2NR ") for line in capture_text.splitlines())
    if records != EXPECTED_CAPTURE_RECORDS or evidence["capture"].get("records") != records:
        raise TraceError("capture record count differs from the pinned S14 replay")
    for lane, expected_exe in (("control", EXPECTED_CONTROL_EXE),
                               ("capture", EXPECTED_CAPTURE_EXE)):
        run = evidence.get("lanes", {}).get(lane, {})
        expected_ids = EXPECTED_RUNS[lane]
        if (run.get("experiment_valid") is not True or run.get("exit_code") != 0
                or run.get("actual_proc_grid") != "1x1"
                or run.get("executable_sha256") != expected_exe
                or run.get("run_id") != expected_ids["run_id"]
                or run.get("campaign_id") != expected_ids["campaign_id"]
                or run.get("scheme") != "37"
                or run.get("minutes") != 10 or run.get("seconds") != 0
                or run.get("history_interval") != 10
                or run.get("history_interval_s") != 0
                or run.get("np") != 1 or run.get("threads") != 1
                or run.get("fixed_dt") is not False or run.get("radt") is not None
                or run.get("runner_sha256") != EXPECTED_RUNNER_SHA256
                or run.get("namelist_without_grid_sha256") != EXPECTED_NAMELIST_SHA256
                or run.get("active_inputs_complete") is not True
                or run.get("active_input_hashes_stable") is not True
                or run.get("input_canonical_sha256") !=
                    "12e132ecefa9e0f7e0a0bd67d57353ec3a7ec113ab1b43121474340293125fdf"
                or run.get("active_input_hashes") != EXPECTED_INPUT_SET
                or run.get("saved_times") != EXPECTED_HISTORY_TIMES
                or run.get("numeric_variables") != 253
                or run.get("history_sha256") != EXPECTED_HISTORY_SHA256
                or run.get("history_bytes") != EXPECTED_HISTORY_BYTES):
            raise TraceError(f"{lane} lane lacks the pinned valid run receipt")
    if evidence.get("noninterference", {}).get("history_files_byte_identical") is not True:
        raise TraceError("control/capture history files are not byte-identical")
    if evidence["lanes"]["control"].get("history_sha256") != \
            evidence["lanes"]["capture"].get("history_sha256"):
        raise TraceError("control/capture history hashes differ")
    strict_report_sha = hashlib.sha256(strict_report_text.encode()).hexdigest()
    if (strict_report_sha != EXPECTED_STRICT_REPORT_SHA256
            or evidence.get("noninterference", {}).get("strict_report_sha256")
            != strict_report_sha):
        raise TraceError("strict control/capture report digest differs from the code pin")
    frames = evidence.get("noninterference", {}).get("frames", [])
    if [f.get("time_seconds") for f in frames] != [0, 600]:
        raise TraceError("control/capture comparison must cover t=0 and t=600")
    for frame in frames:
        if (frame.get("returncode") != 0 or frame.get("common_numeric") != 253
                or frame.get("bitwise_match") != 253
                or frame.get("common_variables") != 254
                or frame.get("times_exact") is not True
                or frame.get("different") != 0
                or frame.get("unsupported_or_skipped") != 0):
            raise TraceError(f"control/capture noninterference failed at {frame}")
    tags = evidence.get("capture_source_tags")
    if not isinstance(tags, dict):
        raise TraceError("missing capture tag schema")
    schema_bytes = json.dumps(tags, sort_keys=True, separators=(",", ":")).encode()
    if hashlib.sha256(schema_bytes).hexdigest() != EXPECTED_CAPTURE_TAG_SCHEMA_SHA256:
        raise TraceError("capture source tag schema differs from the code-pinned schema")
    rows = parse_capture(capture_text, tags, allowed_steps=EXPECTED_STEPS)
    if len(rows) != records:
        raise TraceError("parsed and raw capture counts differ")
    _require_steps_and_host_layers(rows)
    _verify_branch_event_census(rows)
    boundary = _verify_s14_boundary(rows)
    dsd = _verify_threshold_flags(rows)
    nraut = _verify_nraut(rows)
    updates = _verify_budget_updates(rows)
    caps = _verify_nr_caps(rows)
    sources = _source_events(rows)
    face_groups = {(r["step"], r["outer_loop"], r["substep"])
                   for r in rows if r["tag"] == "NR_FACE_PRE"}
    top_groups = {(r["step"], r["outer_loop"], r["substep"])
                  for r in rows if r["tag"] == "NR_TOP_PRE"}
    if not face_groups or face_groups != top_groups:
        raise TraceError("no complete applied number-transport groups were captured")
    ledgers = [_verify_face_group(rows, key) for key in sorted(face_groups)]
    active = sum(g["active_interface_count"] for g in ledgers)
    if len(ledgers) != EXPECTED_TRANSPORT_GROUPS:
        raise TraceError(f"expected {EXPECTED_TRANSPORT_GROUPS} pinned transport groups")
    observed_mstep = {step: {g["mstep"] for g in ledgers if g["step"] == step}
                      for step in EXPECTED_STEPS}
    if any(values != {EXPECTED_MSTEP_BY_STEP[step]}
           for step, values in observed_mstep.items()):
        raise TraceError("per-call mstep/substep census differs from the pinned 600 s run")
    if active != EXPECTED_ACTIVE_INTERFACE_OCCURRENCES:
        raise TraceError("active interface occurrence count differs from the pinned capture")
    if active == 0:
        raise TraceError("no nonzero applied number transfer in the 600 s capture")
    call_process = _call_process_ledger(rows, ledgers, sources)

    entry = {(r["step"], r["level"]): r for r in rows if r["tag"] == "HOST_ENTRY"}
    returned = {(r["step"], r["level"]): r for r in rows if r["tag"] == "HOST_RETURN"}
    call = []
    for step in EXPECTED_STEPS:
        a = sum(entry[(step, level)]["f32"]["nr(i,k,j)"] for level in range(1, 40))
        b = sum(returned[(step, level)]["f32"]["nr(i,k,j)"] for level in range(1, 40))
        call.append({"step": step, "host_entry_qnr_column_sum_raw": a,
                     "host_return_qnr_column_sum_raw": b,
                     "within_call_raw_delta_unweighted": b - a})
    intercall = []
    for step in EXPECTED_STEPS[:-1]:
        delta = [{"level": level,
                  "prior_host_return_raw": returned[(step, level)]["f32"]["nr(i,k,j)"],
                  "next_host_entry_raw": entry[(step + 1, level)]["f32"]["nr(i,k,j)"],
                  "intercall_host_dynamics_remainder_raw":
                      entry[(step + 1, level)]["f32"]["nr(i,k,j)"]
                      - returned[(step, level)]["f32"]["nr(i,k,j)"]}
                 for level in range(1, 40)]
        intercall.append({"after_step": step, "before_step": step + 1, "levels": delta,
                          "interpretation": "unattributed between-call remainder; no RK/dynamics operand capture"})
    return {
        "schema": "s14-m1-number-ledger-replay-v1",
        "physical_number_basis_resolved": False,
        "capture_records": records,
        "host_kernel_boundary": boundary,
        "dsd_gate_checks": dsd,
        "nraut_checks": nraut,
        "source_update_checks": updates,
        "number_cap_checks": caps,
        "direct_source_events": sources,
        "transport_groups": len(ledgers),
        "active_interface_occurrences": active,
        "transport_ledgers_by_group": ledgers,
        "within_call_process_ledgers": call_process,
        "host_call_raw_qnr_summaries": call,
        "intercall_dynamics_remainders": intercall,
        "basis_limitation": "dz*n, rho_m*dz*n and conditional rho_d*dz*n are diagnostic measures only; no physical number unit is selected",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--evidence", type=Path, required=True)
    ap.add_argument("--capture", type=Path, required=True)
    ap.add_argument("--strict-report", type=Path, required=True)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    rendered = json.dumps(replay(json.loads(args.evidence.read_text()),
                                 args.capture.read_text(), args.strict_report.read_text()),
                          indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.write_text(rendered)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
