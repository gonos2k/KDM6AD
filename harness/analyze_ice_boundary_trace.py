"""Strict parser and source-equation checks for the legacy ice trace."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import struct

if __package__:
    from . import make_ice_boundary_overlay as overlay_generator
else:  # Direct `python harness/analyze_ice_boundary_trace.py` execution.
    import make_ice_boundary_overlay as overlay_generator

SCHEMA = "kdm6.ice_boundary_trace.v1"
FIELDS = {
    "ice_velocity": set(
        "schema record order stage basis dtcld_s mstepmax variant column level_top0 mstep work1_qi workn_qi DEND_kg_m3 DELZ_m".split()
    ),
    "ice_layer": set(
        "schema record order substep dtcld_s column level_top0 top mstep gate DEND_kg_m3 DEND_safe_kg_m3 DELZ_m DELZ_safe_m DELZ_above_m work1_qi workn_qi QI_before_kg_kg NI_before_number_m3 falk_qi_stored_kg_m3_s falk_ni_stored_number_m3_s fall_qi_accum_before_kg_m3_s fall_qi_accum_after_kg_m3_s fall_ni_accum_before_number_m3_s fall_ni_accum_after_number_m3_s out_attempt_qi_kg_kg out_applied_qi_kg_kg upstream_falk_qi_stored_kg_m3_s source_post_QI_kg_kg arrival_attempt_qi_kg_kg arrival_applied_qi_kg_kg QI_after_kg_kg top_clip_qi_kg_kg out_attempt_ni_number_m3 out_applied_ni_number_m3 upstream_falk_ni_stored_number_m3_s source_post_NI_number_m3 arrival_attempt_ni_number_m3 arrival_applied_ni_number_m3 NI_after_number_m3 top_clip_ni_number_m3".split()
    ),
    "ice_bottom": set(
        "schema record order dtcld_s column levels bottom_top0 fall_qi_bottom_kg_m3_s fall_ni_bottom_number_m3_s DELZ_bottom_m rain_increment_total_mm snow_ice_subset_mm graupel_subset_mm".split()
    ),
}
INTEGER_FIELDS = {
    "ice_velocity": {"mstepmax", "variant", "column", "level_top0", "mstep"},
    "ice_layer": {"substep", "column", "level_top0", "top", "mstep"},
    "ice_bottom": {"column", "levels", "bottom_top0"},
}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ordered_float(bits):
    return (~bits & ((1 << 64) - 1)) if bits >> 63 else bits | (1 << 63)


def close_ulps(actual, expected, limit=2):
    if actual == expected:
        return True
    a = struct.unpack("<Q", struct.pack("<d", actual))[0]
    b = struct.unpack("<Q", struct.pack("<d", expected))[0]
    return abs(ordered_float(a) - ordered_float(b)) <= limit


def parse_trace(path):
    rows = []
    for no, line in enumerate(Path(path).read_text().splitlines(), 1):
        if not line:
            raise ValueError(f"blank line {no}")
        row = {}
        for token in line.split():
            if "=" not in token:
                raise ValueError(f"bad token at line {no}")
            key, value = token.split("=", 1)
            if key in row:
                raise ValueError(f"duplicate key {key} at line {no}")
            row[key] = value
        if row.get("schema") != SCHEMA or row.get("record") not in FIELDS:
            raise ValueError(f"bad schema or record at line {no}")
        if set(row) != FIELDS[row["record"]]:
            raise ValueError(f"wrong field set at line {no}")
        for key, value in tuple(row.items()):
            if key in {"schema", "record", "order", "stage", "basis"}:
                continue
            number = float(value)
            if not math.isfinite(number):
                raise ValueError(f"nonfinite {key} at line {no}")
            if key in INTEGER_FIELDS[row["record"]] and number != int(number):
                raise ValueError(f"non-integer {key} at line {no}")
            row[key] = number
        if row["order"] != "top_first":
            raise ValueError(f"unexpected vertical order at line {no}")
        rows.append(row)
    if not rows:
        raise ValueError("empty trace")
    return rows


def _request(path):
    data = Path(path).read_bytes()
    if len(data) < 48:
        raise ValueError("truncated request header")
    magic, version, levels, dt, xland, nland, nsea = struct.unpack_from("<8sII4d", data)
    if magic != b"K6BUDG1\0" or version != 1 or levels < 1:
        raise ValueError("unsupported request")
    if len(data) != 48 + 16 * levels * 8:
        raise ValueError("request payload length mismatch")
    values = struct.unpack_from(f"<{16 * levels}d", data, 48)
    if not all(math.isfinite(x) for x in values):
        raise ValueError("request payload contains nonfinite data")
    state = [values[k * levels : (k + 1) * levels] for k in range(12)]
    forcing = [values[(12 + k) * levels : (13 + k) * levels] for k in range(4)]
    if not math.isfinite(dt) or dt <= 0.0 or not math.isfinite(xland):
        raise ValueError("request contains invalid dt or XLAND")
    if any(x <= 0.0 for row in forcing for x in row):
        raise ValueError("request forcing must be finite and positive")
    return {
        "levels": levels,
        "dt": dt,
        "xland": xland,
        "ncmin_land": nland,
        "ncmin_sea": nsea,
        "sha256": sha(path),
        "_state": state,
        "_forcing": forcing,
    }


def _verify_source_manifest(manifest):
    source_dir = Path(__file__).parents[1] / "libtorch/src"
    transforms = {
        "runtime.cpp": overlay_generator.instrument_runtime,
        "coordinator.cpp": overlay_generator.instrument_coordinator,
        "sedimentation.cpp": overlay_generator.instrument_sedimentation,
    }
    for name, transform in transforms.items():
        source = source_dir / name
        digest = overlay_generator.sha256(source)
        if digest != overlay_generator.SOURCE_PINS[name]:
            raise ValueError(f"public source pin changed for {name}")
        if manifest["source_sha256"][name] != digest:
            raise ValueError(f"manifest base-source SHA mismatch for {name}")
        rendered = transform(source.read_text()).encode()
        if (
            manifest["overlay_source_sha256"][name]
            != hashlib.sha256(rendered).hexdigest()
        ):
            raise ValueError(f"manifest overlay-source SHA mismatch for {name}")
    build_pins = manifest.get("base_build_inputs_sha256", {})
    required = {
        "base_archive",
        "compile_flags",
        "tool_object",
        "tool_link",
        "capi_object",
        "capi_link",
    }
    if set(build_pins) != required or any(
        not isinstance(v, str)
        or len(v) != 64
        or any(c not in "0123456789abcdef" for c in v)
        for v in build_pins.values()
    ):
        raise ValueError("manifest base-build input SHA set is incomplete or malformed")


def _response_precip(path, request_path, levels):
    data = Path(path).read_bytes()
    if len(data) != 16 + (28 * levels + 3) * 8:
        raise ValueError("response size mismatch for the requested level count")
    magic, version, response_levels = struct.unpack_from("<8sII", data)
    if magic != b"K6BOUT1\0" or version != 1 or response_levels != levels:
        raise ValueError("response header mismatch")
    request = Path(request_path).read_bytes()
    state_bytes = 12 * levels * 8
    forcing_bytes = 4 * levels * 8
    if data[16 : 16 + state_bytes] != request[48 : 48 + state_bytes]:
        raise ValueError("response state echo differs from request bits")
    if (
        data[16 + state_bytes : 16 + state_bytes + forcing_bytes]
        != request[48 + state_bytes : 48 + state_bytes + forcing_bytes]
    ):
        raise ValueError("response forcing echo differs from request bits")
    values = struct.unpack_from(f"<{28 * levels + 3}d", data, 16)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("response contains nonfinite binary64 output")
    return struct.unpack_from("<3d", data, 16 + 28 * levels * 8)


def analyze(
    trace_path,
    manifest_path,
    request_path,
    control_response_path=None,
    traced_response_path=None,
):
    manifest = json.loads(Path(manifest_path).read_text())
    if manifest.get("schema") != SCHEMA:
        raise ValueError("manifest schema mismatch")
    _verify_source_manifest(manifest)
    unit_contract = manifest.get("unit_contract", {})
    required_unit_notes = {
        "QI_state",
        "NI_state",
        "legacy_velocity_handoff",
        "trace_suffixes",
        "interface_terms",
        "bottom_comparison",
    }
    if set(unit_contract) != required_unit_notes or any(
        not isinstance(value, str) or not value.strip()
        for value in unit_contract.values()
    ):
        raise ValueError(
            "manifest lacks the explicit nominal-state/physical-flux unit caveats"
        )
    request = _request(request_path)
    if request["sha256"] != manifest.get("request_sha256"):
        raise ValueError("request SHA differs from manifest")
    if (request["levels"], request["dt"], request["xland"]) != (39, 20.0, 2.0):
        raise ValueError("analyzer is scoped to this 39-level, dt=20, XLAND=2 capture")
    for group in ("source_sha256", "overlay_source_sha256"):
        pins = manifest.get(group, {})
        if set(pins) != {"runtime.cpp", "coordinator.cpp", "sedimentation.cpp"}:
            raise ValueError(f"manifest {group} file set mismatch")
        if any(
            not isinstance(v, str)
            or len(v) != 64
            or any(c not in "0123456789abcdef" for c in v)
            for v in pins.values()
        ):
            raise ValueError(f"manifest {group} has invalid hash")
    if manifest.get("trace_environment_variable") != "KDM6_ICE_BOUNDARY_TRACE":
        raise ValueError("trace environment name mismatch")
    rows = parse_trace(trace_path)
    velocities = [r for r in rows if r["record"] == "ice_velocity"]
    layers = [r for r in rows if r["record"] == "ice_layer"]
    bottoms = [r for r in rows if r["record"] == "ice_bottom"]
    levels = request["levels"]
    stages = {"runtime_input_normalized", "post_main_handoff"}
    if {r["stage"] for r in velocities} != stages:
        raise ValueError("missing velocity checkpoint")
    columns = sorted({int(r["column"]) for r in velocities})
    if columns != list(range(len(columns))) or not columns:
        raise ValueError("columns are not contiguous")
    if columns != [0]:
        raise ValueError("this capture is scoped to one column")
    if [r["stage"] for r in velocities] != ["runtime_input_normalized"] * levels + [
        "post_main_handoff"
    ] * levels:
        raise ValueError("velocity checkpoint groups are interleaved or out of order")
    if [r["stage"] for r in velocities] != ["runtime_input_normalized"] * levels + [
        "post_main_handoff"
    ] * levels:
        raise ValueError("velocity checkpoint groups are interleaved or out of order")
    for stage in stages:
        group = [r for r in velocities if r["stage"] == stage]
        if [(int(r["column"]), int(r["level_top0"])) for r in group] != [
            (b, k) for b in columns for k in range(levels)
        ]:
            raise ValueError(f"incomplete/out-of-order velocity checkpoint {stage}")
        if any(int(r["variant"]) != 0 for r in group):
            raise ValueError("trace is not Legacy variant")
    initial = {
        (int(r["column"]), int(r["level_top0"])): r
        for r in velocities
        if r["stage"] == "runtime_input_normalized"
    }
    handoff = {
        (int(r["column"]), int(r["level_top0"])): r
        for r in velocities
        if r["stage"] == "post_main_handoff"
    }
    maxima = {int(r["mstepmax"]) for r in velocities}
    if len(maxima) != 1:
        raise ValueError("mstepmax varies across records")
    mstepmax = next(iter(maxima))
    if mstepmax != 1:
        raise ValueError(
            "this captured request has one internal ice substep; mstepmax must be 1"
        )
    record_order = [r["record"] for r in rows]
    expected_record_order = ["ice_velocity"] * (2 * levels)
    expected_record_order += ["ice_layer"] * (mstepmax * levels)
    expected_record_order += ["ice_bottom"] * len(columns)
    if record_order != expected_record_order:
        raise ValueError("trace record groups are incomplete or out of order")
    expected_msteps = {}
    for key, x in initial.items():
        y = handoff[key]
        if x["basis"] != "vt_over_delz" or y["basis"] != "raw_vt":
            raise ValueError("velocity basis labels mismatch")
        if not close_ulps(y["work1_qi"], x["work1_qi"] * x["DELZ_m"]):
            raise ValueError("vt_i handoff does not reconstruct from normalized input")
        if not close_ulps(y["workn_qi"], x["workn_qi"] * x["DELZ_m"]):
            raise ValueError("vtn_i handoff does not reconstruct from normalized input")
        if not close_ulps(y["DEND_kg_m3"], x["DEND_kg_m3"]):
            raise ValueError(
                "DEND changed between initial checkpoint and main→ice handoff"
            )
        if not close_ulps(y["DELZ_m"], x["DELZ_m"]):
            raise ValueError(
                "DELZ changed between initial checkpoint and main→ice handoff"
            )
        if x["mstep"] != y["mstep"]:
            raise ValueError("ice mstep changed across handoff")
        b, _ = key
        expected_msteps.setdefault(b, []).append(x)
    for b, records in expected_msteps.items():
        vmax = max(max(r["work1_qi"], r["workn_qi"]) for r in records)
        expected = min(100.0, max(1.0, math.floor(vmax * request["dt"] + 1.0)))
        if any(r["mstep"] != expected for r in records):
            raise ValueError(
                "mstep does not reconstruct from normalized runtime input velocities"
            )
        if mstepmax != max(expected_msteps[b][0]["mstep"] for b in expected_msteps):
            raise ValueError("mstepmax differs from the column mstep maximum")

    if any(r["dtcld_s"] != request["dt"] for r in velocities):
        raise ValueError("this one-loop capture requires velocity dtcld == request dt")
    for k in range(levels):
        wrf_k = levels - 1 - k
        src = initial[(0, k)]
        expected_den = float(request["_forcing"][0][wrf_k])
        expected_delz = float(request["_forcing"][3][wrf_k])
        if not close_ulps(src["DEND_kg_m3"], expected_den):
            raise ValueError(
                "initial velocity checkpoint DEND differs from request forcing row 0"
            )
        if not close_ulps(src["DELZ_m"], expected_delz):
            raise ValueError(
                "initial velocity checkpoint DELZ differs from request forcing row 3"
            )

    expected = [
        (n, b, k)
        for n in range(1, mstepmax + 1)
        for k in range(levels)
        for b in columns
    ]
    actual = [
        (int(r["substep"]), int(r["column"]), int(r["level_top0"])) for r in layers
    ]
    if actual != expected:
        raise ValueError("ice layer rows incomplete or out of order")
    if any(r["dtcld_s"] != request["dt"] for r in layers):
        raise ValueError("this one-loop capture requires layer dtcld == request dt")
    bykey = {
        (int(r["substep"]), int(r["column"]), int(r["level_top0"])): r for r in layers
    }
    for r in layers:
        n, b, k = int(r["substep"]), int(r["column"]), int(r["level_top0"])
        if int(r["top"]) != int(k == 0):
            raise ValueError("top flag mismatch")
        if r["gate"] != float(r["mstep"] >= n):
            raise ValueError("mstep gate mismatch")
        velocity_handoff = handoff[(b, k)]
        if r["mstep"] != velocity_handoff["mstep"]:
            raise ValueError("ice-layer mstep differs from recorded handoff mstep")
        wrf_k = levels - 1 - k
        expected_qi = max(float(request["_state"][4][wrf_k]), 0.0)
        expected_ni = min(max(float(request["_state"][9][wrf_k]), 0.0), 1.0e6)
        if n == 1 and (
            not close_ulps(r["QI_before_kg_kg"], expected_qi)
            or not close_ulps(r["NI_before_number_m3"], expected_ni)
        ):
            raise ValueError(
                "first ICE state differs from request after runtime entry clamps"
            )
        if not close_ulps(r["DEND_kg_m3"], float(request["_forcing"][0][wrf_k])):
            raise ValueError("ice-layer DEND differs from request forcing row 0")
        if not close_ulps(r["DELZ_m"], float(request["_forcing"][3][wrf_k])):
            raise ValueError("ice-layer DELZ differs from request forcing row 3")
        if not close_ulps(r["work1_qi"], velocity_handoff["work1_qi"]):
            raise ValueError("ice-layer work1_qi differs from main-to-ice handoff")
        if not close_ulps(r["workn_qi"], velocity_handoff["workn_qi"]):
            raise ValueError("ice-layer workn_qi differs from main-to-ice handoff")
        fqi = (
            r["DEND_kg_m3"]
            * r["QI_before_kg_kg"]
            * r["work1_qi"]
            / r["mstep"]
            * r["gate"]
        )
        fni = r["NI_before_number_m3"] * r["workn_qi"] / r["mstep"] * r["gate"]
        oq = fqi * r["dtcld_s"] / r["DEND_safe_kg_m3"]
        on = fni * r["dtcld_s"]
        for name, got, want in (
            ("falk QI", r["falk_qi_stored_kg_m3_s"], fqi),
            ("falk NI", r["falk_ni_stored_number_m3_s"], fni),
            ("QI out attempt", r["out_attempt_qi_kg_kg"], oq),
            ("NI out attempt", r["out_attempt_ni_number_m3"], on),
        ):
            if not close_ulps(got, want):
                raise ValueError(f"{name} source reconstruction mismatch")
        if not close_ulps(
            r["fall_qi_accum_after_kg_m3_s"],
            r["fall_qi_accum_before_kg_m3_s"] + r["falk_qi_stored_kg_m3_s"],
        ):
            raise ValueError("stored QI fall accumulator is inconsistent")
        if not close_ulps(
            r["fall_ni_accum_after_number_m3_s"],
            r["fall_ni_accum_before_number_m3_s"] + r["falk_ni_stored_number_m3_s"],
        ):
            raise ValueError("stored NI fall accumulator is inconsistent")
        if not close_ulps(r["DEND_safe_kg_m3"], max(r["DEND_kg_m3"], 1.0e-9)):
            raise ValueError("DEND safe value differs from the source 1e-9 clamp")
        if not close_ulps(r["DELZ_safe_m"], max(r["DELZ_m"], 1.0e-9)):
            raise ValueError("DELZ safe value differs from the source 1e-9 clamp")
        if k == 0:
            if any(
                r[x] != 0
                for x in (
                    "upstream_falk_qi_stored_kg_m3_s",
                    "source_post_QI_kg_kg",
                    "arrival_attempt_qi_kg_kg",
                    "arrival_applied_qi_kg_kg",
                    "upstream_falk_ni_stored_number_m3_s",
                    "source_post_NI_number_m3",
                    "arrival_attempt_ni_number_m3",
                    "arrival_applied_ni_number_m3",
                )
            ):
                raise ValueError("top boundary has nonzero inflow")
            if not close_ulps(
                r["top_clip_qi_kg_kg"],
                max(r["out_attempt_qi_kg_kg"] - r["QI_before_kg_kg"], 0.0),
            ):
                raise ValueError(
                    "top QI positivity projection does not match raw outflow"
                )
            if not close_ulps(
                r["top_clip_ni_number_m3"],
                max(r["out_attempt_ni_number_m3"] - r["NI_before_number_m3"], 0.0),
            ):
                raise ValueError(
                    "top NI positivity projection does not match raw outflow"
                )
        else:
            prev = bykey[(n, b, k - 1)]
            if not close_ulps(r["DELZ_above_m"], prev["DELZ_m"]):
                raise ValueError(
                    "upstream DELZ differs from the previous top-first layer"
                )
            for field, expected_value in (
                ("upstream_falk_qi_stored_kg_m3_s", prev["falk_qi_stored_kg_m3_s"]),
                (
                    "upstream_falk_ni_stored_number_m3_s",
                    prev["falk_ni_stored_number_m3_s"],
                ),
                ("source_post_QI_kg_kg", prev["QI_after_kg_kg"]),
                ("source_post_NI_number_m3", prev["NI_after_number_m3"]),
            ):
                if not close_ulps(r[field], expected_value):
                    raise ValueError(
                        f"upstream state/flux mismatch at level {k}: {field}"
                    )
            aq = (
                r["upstream_falk_qi_stored_kg_m3_s"]
                * r["DELZ_above_m"]
                / r["DELZ_safe_m"]
                * r["dtcld_s"]
                / r["DEND_safe_kg_m3"]
            )
            an = (
                r["upstream_falk_ni_stored_number_m3_s"]
                * r["DELZ_above_m"]
                / r["DELZ_safe_m"]
                * r["dtcld_s"]
            )
            if not close_ulps(r["arrival_attempt_qi_kg_kg"], aq) or not close_ulps(
                r["arrival_attempt_ni_number_m3"], an
            ):
                raise ValueError("upstream stored-falk arrival reconstruction mismatch")
            if not close_ulps(
                r["arrival_applied_qi_kg_kg"], min(aq, r["source_post_QI_kg_kg"])
            ):
                raise ValueError("QI arrival is not capped by source post-reservoir")
            if not close_ulps(
                r["arrival_applied_ni_number_m3"],
                min(an, r["source_post_NI_number_m3"]),
            ):
                raise ValueError("NI arrival is not capped by source post-reservoir")
        # Interior outflow and arrival min operations, and state update.
        outq = min(oq, r["QI_before_kg_kg"])
        outn = min(on, r["NI_before_number_m3"])
        if not close_ulps(r["out_applied_qi_kg_kg"], outq) or not close_ulps(
            r["out_applied_ni_number_m3"], outn
        ):
            raise ValueError("applied outflow differs from raw source cap")
        arrq = 0.0 if k == 0 else r["arrival_applied_qi_kg_kg"]
        arrn = 0.0 if k == 0 else r["arrival_applied_ni_number_m3"]
        if not close_ulps(
            r["QI_after_kg_kg"], max(r["QI_before_kg_kg"] - outq + arrq, 0.0)
        ):
            raise ValueError("QI poststate does not match source update")
        if not close_ulps(
            r["NI_after_number_m3"], max(r["NI_before_number_m3"] - outn + arrn, 0.0)
        ):
            raise ValueError("NI poststate does not match source update")

    if len(bottoms) != len(columns) or [int(r["column"]) for r in bottoms] != columns:
        raise ValueError("bottom records incomplete/out of order")
    for bottom in bottoms:
        if (
            int(bottom["levels"]) != levels
            or int(bottom["bottom_top0"]) != levels - 1
            or bottom["dtcld_s"] != request["dt"]
        ):
            raise ValueError("bottom diagnostic levels/dt differ from the request")
    if not close_ulps(
        bottoms[0]["DELZ_bottom_m"], float(request["_forcing"][3][0])
    ) or not close_ulps(
        bottoms[0]["DELZ_bottom_m"], bykey[(mstepmax, 0, levels - 1)]["DELZ_m"]
    ):
        raise ValueError("bottom diagnostic DELZ differs from request bottom interface")
    summaries = []
    for b in columns:
        group = [
            bykey[(n, b, k)] for n in range(1, mstepmax + 1) for k in range(levels)
        ]
        qi_change = math.fsum(
            (r["QI_after_kg_kg"] - r["QI_before_kg_kg"]) * r["DEND_kg_m3"] * r["DELZ_m"]
            for r in group
        )
        ni_change = math.fsum(
            (r["NI_after_number_m3"] - r["NI_before_number_m3"]) * r["DELZ_m"]
            for r in group
        )
        qidef = []
        nidef = []
        qi_pairs = []
        ni_pairs = []
        for n in range(1, mstepmax + 1):
            for k in range(levels - 1):
                src, rec = bykey[(n, b, k)], bykey[(n, b, k + 1)]
                qout = src["out_applied_qi_kg_kg"] * src["DEND_kg_m3"] * src["DELZ_m"]
                qin = (
                    rec["arrival_applied_qi_kg_kg"] * rec["DEND_kg_m3"] * rec["DELZ_m"]
                )
                nout = src["out_applied_ni_number_m3"] * src["DELZ_m"]
                nin = rec["arrival_applied_ni_number_m3"] * rec["DELZ_m"]
                qidef.append(qout - qin)
                nidef.append(nout - nin)
                qi_pairs.append(
                    {
                        "substep": n,
                        "source_level_top0": k,
                        "receiver_level_top0": k + 1,
                        "source_outflow_kg_m2": qout,
                        "receiver_arrival_kg_m2": qin,
                        "interface_defect_kg_m2": qout - qin,
                        "attempted_arrival_kg_kg": rec["arrival_attempt_qi_kg_kg"],
                        "applied_arrival_kg_kg": rec["arrival_applied_qi_kg_kg"],
                        "source_post_reservoir_kg_kg": rec["source_post_QI_kg_kg"],
                        "arrival_cap_bound": rec["arrival_applied_qi_kg_kg"]
                        < rec["arrival_attempt_qi_kg_kg"],
                    }
                )
                ni_pairs.append(
                    {
                        "substep": n,
                        "source_level_top0": k,
                        "receiver_level_top0": k + 1,
                        "source_outflow_number_m2": nout,
                        "receiver_arrival_number_m2": nin,
                        "interface_defect_number_m2": nout - nin,
                        "attempted_arrival_number_m3": rec[
                            "arrival_attempt_ni_number_m3"
                        ],
                        "applied_arrival_number_m3": rec[
                            "arrival_applied_ni_number_m3"
                        ],
                        "source_post_reservoir_number_m3": rec[
                            "source_post_NI_number_m3"
                        ],
                        "arrival_cap_bound": rec["arrival_applied_ni_number_m3"]
                        < rec["arrival_attempt_ni_number_m3"],
                    }
                )
        bottom = bottoms[b]
        qi_bottom_diagnostic = (
            bottom["fall_qi_bottom_kg_m3_s"]
            * bottom["DELZ_bottom_m"]
            * bottom["dtcld_s"]
        )
        ni_bottom_diagnostic = (
            bottom["fall_ni_bottom_number_m3_s"]
            * bottom["DELZ_bottom_m"]
            * bottom["dtcld_s"]
        )
        bottom_layer = bykey[(mstepmax, b, levels - 1)]
        if not close_ulps(
            bottom["fall_qi_bottom_kg_m3_s"],
            bottom_layer["fall_qi_accum_after_kg_m3_s"],
        ):
            raise ValueError(
                "bottom QI diagnostic does not match the final stored ice fall"
            )
        if not close_ulps(
            bottom["fall_ni_bottom_number_m3_s"],
            bottom_layer["fall_ni_accum_after_number_m3_s"],
        ):
            raise ValueError(
                "bottom NI diagnostic does not match final stored ice number fall"
            )
        qi_bottom_outflow = (
            bottom_layer["out_applied_qi_kg_kg"]
            * bottom_layer["DEND_kg_m3"]
            * bottom_layer["DELZ_m"]
        )
        ni_bottom_outflow = (
            bottom_layer["out_applied_ni_number_m3"] * bottom_layer["DELZ_m"]
        )
        summaries.append(
            {
                "column": b,
                "qi_column_delta_kg_m2": qi_change,
                "qi_bottom_applied_outflow_kg_m2": qi_bottom_outflow,
                "qi_bottom_stored_falk_equivalent_kg_m2": qi_bottom_diagnostic,
                "qi_bottom_diagnostic_minus_applied_kg_m2": qi_bottom_diagnostic
                - qi_bottom_outflow,
                "qi_interface_defect_kg_m2": math.fsum(qidef),
                "qi_interface_pairs": qi_pairs,
                "qi_state_export_defect_identity_residual_kg_m2": math.fsum(
                    (qi_change, qi_bottom_outflow, math.fsum(qidef))
                ),
                "ni_column_delta_number_m2": ni_change,
                "ni_bottom_applied_outflow_number_m2": ni_bottom_outflow,
                "ni_bottom_stored_falk_equivalent_number_m2": ni_bottom_diagnostic,
                "ni_bottom_diagnostic_minus_applied_number_m2": ni_bottom_diagnostic
                - ni_bottom_outflow,
                "ni_interface_defect_number_m2": math.fsum(nidef),
                "ni_interface_pairs": ni_pairs,
                "ni_state_export_defect_identity_residual_number_m2": math.fsum(
                    (ni_change, ni_bottom_outflow, math.fsum(nidef))
                ),
                "qi_interface_defect_by_substep_kg_m2": [qidef],
                "surface_rain_increment_total_mm": bottom["rain_increment_total_mm"],
                "snow_ice_subset_mm": bottom["snow_ice_subset_mm"],
                "graupel_subset_mm": bottom["graupel_subset_mm"],
                "qi_arrival_cap_bound_count": sum(
                    1
                    for n in range(1, mstepmax + 1)
                    for k in range(1, levels)
                    if bykey[(n, b, k)]["arrival_applied_qi_kg_kg"]
                    < bykey[(n, b, k)]["arrival_attempt_qi_kg_kg"]
                ),
                "ni_arrival_cap_bound_count": sum(
                    1
                    for n in range(1, mstepmax + 1)
                    for k in range(1, levels)
                    if bykey[(n, b, k)]["arrival_applied_ni_number_m3"]
                    < bykey[(n, b, k)]["arrival_attempt_ni_number_m3"]
                ),
            }
        )
    response_comparison = None
    if (control_response_path is None) != (traced_response_path is None):
        raise ValueError("control and traced response files must be provided together")
    if control_response_path is not None:
        control_bytes = Path(control_response_path).read_bytes()
        traced_bytes = Path(traced_response_path).read_bytes()
        flux = _response_precip(traced_response_path, request_path, levels)
        bottom = bottoms[0]
        for label, value, field in zip(
            ("rain_increment_total_mm", "snow_ice_subset_mm", "graupel_subset_mm"),
            flux,
            ("rain_increment_total_mm", "snow_ice_subset_mm", "graupel_subset_mm"),
        ):
            if not close_ulps(float(bottom[field]), float(value)):
                raise ValueError(f"bottom {label} differs from the returned FnResult")
        response_comparison = {
            "control_sha256": sha(control_response_path),
            "traced_sha256": sha(traced_response_path),
            "full_response_bitwise_equal": control_bytes == traced_bytes,
            "FnResult_precipitation_mm": list(flux),
            "bottom_record_matches_FnResult": True,
        }
        if not response_comparison["full_response_bitwise_equal"]:
            raise ValueError("instrumentation changed the full request response bytes")
    public_request = {k: v for k, v in request.items() if not k.startswith("_")}
    return {
        "schema": "kdm6.ice_boundary_trace_analysis.v1",
        "analyzer_source_sha256": sha256(__file__),
        "manifest_sha256": sha256(manifest_path),
        "trace_sha256": sha256(trace_path),
        "request": public_request,
        "response_noninterference": response_comparison,
        "source_sha256": manifest["source_sha256"],
        "overlay_source_sha256": manifest["overlay_source_sha256"],
        "record_counts": {
            "velocity": len(velocities),
            "ice_layer": len(layers),
            "ice_bottom": len(bottoms),
        },
        "mstepmax_ice": mstepmax,
        "level_order": "trace top_first; map top-index k to WRF bottom-first index L-1-k",
        "number_basis": "volumetric KDM NI operand (# m-3) inferred from source equations; no original host basis certification",
        "water_basis": "QI is kg kg-1; layer water measure DEND*DELZ*QI (kg m-2)",
        "unit_contract": manifest.get("unit_contract"),
        "columns": summaries,
        "limits": [
            "Source-equation reconstruction of this captured legacy call only.",
            "No claim that the incoming host NI payload is physically per-m3 without producer provenance.",
            "No host integration, RTTOV, or physics-map change.",
        ],
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--trace", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--request", type=Path, required=True)
    p.add_argument("--control-response", type=Path)
    p.add_argument("--traced-response", type=Path)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    result = analyze(
        a.trace, a.manifest, a.request, a.control_response, a.traced_response
    )
    with a.output.open("x") as f:
        json.dump(result, f, indent=2, allow_nan=False)
        f.write("\n")
    print(
        json.dumps(
            {
                "trace_sha256": result["trace_sha256"],
                "record_counts": result["record_counts"],
                "columns": result["columns"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
