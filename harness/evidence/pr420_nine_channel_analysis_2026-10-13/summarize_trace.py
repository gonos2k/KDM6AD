#!/usr/bin/env python3
"""Recover complete recorded V2 trace by labelled schema; never calls H or M."""
from __future__ import annotations
import csv
import hashlib
import json
from pathlib import Path
import re

PACKET = Path(__file__).resolve().parent
ROOT = PACKET.parents[2]
PRIVATE = Path("/Users/yhlee/KDM6AD-k/host/research_evidence/pr420_nine_channel_20261013")
RUN = PRIVATE / "SAVED07_TRACE_CORRECTED_01"
FIRST = PRIVATE / "SAVED07_TRACE_ONCE"
HEAD = re.compile(r"^(EDD_[A-Z_]+|SCATT_HYDRO)call=\s*(\d+)\s+array_slot=\s*(\d+)\s+internal_idx=\s*(\d+)\s+profile=\s*(\d+)\s*(.*)$")
LAYER = re.compile(r"^layer=\s*(\d+)\s+overlap_col=\s*(\d+)\s+(.*)$")
FIELDS = ("p_top_hPa", "p_lay_hPa", "p_bottom_hPa", "T_K", "q_internal", "ltick_vertical_km",
          "pathsat", "slant_length_km", "coszen", "layer_od_slant", "clear_unfloored_km_inv",
          "clear_floored_km_inv", "aerosol_km_inv", "hydro_km_inv", "ext_all_logged", "pre_km_inv",
          "icldarr_logged", "column_weight")


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    plan = json.loads((PACKET / "TRACE_V2_PLAN.json").read_text())
    for p, digest in plan["bindings"].items():
        if sha(p) != digest:
            raise ValueError("recorded trace input/source changed: " + p)
    case = next((RUN / "H").glob("*/case"))
    channels = [int(s) for s in (case / "in/channels.txt").read_text().split()]
    assert channels == [8, 9]
    mapping = {i+1: ch for i, ch in enumerate(channels)}
    rows, posts, quality = {}, {}, []
    for line in (RUN / "EXT_TRACE.txt").read_text().splitlines():
        match = HEAD.match(line.strip())
        if not match:
            continue
        tag, call, slot, internal, profile, tail = match.groups()
        call, slot, internal, profile = map(int, (call, slot, internal, profile))
        assert internal in mapping and slot == internal and profile == 1
        if tag == "EDD_POST_QUALITY":
            q = re.fullmatch(r"quality_before=\s*(\d+)\s+quality_after=\s*(\d+)\s+fired=\s*([TF])\s+quality_bit=\s*(\d+)", tail)
            assert q is not None
            quality.append({"call": call, "channel": mapping[internal], "before": int(q[1]),
                            "after": int(q[2]), "fired": q[3] == "T", "bit": int(q[4])})
            continue
        if tag not in ("EDD_PRE", "EDD_POST_LAYER"):
            continue
        layer = LAYER.match(tail)
        assert layer is not None
        lev, col = int(layer[1]), int(layer[2])
        values = [float(v.replace("D", "E")) for v in layer[3].split()]
        key = (call, mapping[internal], lev, col)
        if tag == "EDD_PRE":
            assert len(values) == len(FIELDS) and key not in rows
            row = dict(zip(FIELDS, values))
            # ext_all/icldarr of the clear column are not used as scientific
            # evidence: these arrays may start at1 when aerosols are disabled.
            if col == 0:
                row["ext_all_logged"] = None
                row["icldarr_logged"] = None
            rows[key] = row
        else:
            assert len(values) == 1 and key not in posts
            posts[key] = values[0]
    assert set(rows) == set(posts)
    expected = {(c, ch, k, col) for c in (1, 2) for ch in (8, 9) for k in range(1, 67) for col in (0, 1)}
    assert set(rows) == expected
    assert len(quality) == 4 and all(q["after"] == 32768 and q["bit"] == 15 and q["fired"] for q in quality)
    triggered = []
    for key, row in rows.items():
        assert posts[key] == min(row["pre_km_inv"], 20.0)
        assert abs(row["clear_unfloored_km_inv"] - row["layer_od_slant"] / row["ltick_vertical_km"] * row["coszen"]) < 1e-12
        assert row["aerosol_km_inv"] == 0 and row["hydro_km_inv"] == 0
        if row["pre_km_inv"] > 20:
            triggered.append({"call": key[0], "channel": key[1], "layer_topdown_1based": key[2],
                              "overlap_column": key[3], **row, "post_km_inv": posts[key]})
    for key, row in rows.items():
        if key[0] == 1:
            assert row == rows[(2, *key[1:])]
    products = ("direct/radiance.txt", "direct/transmission.txt", "k/radiance.txt", "k/transmission.txt", "k/profiles_k.txt")
    control = next((FIRST / "control").glob("*/case"))
    comparison = {rel: {"control_sha256": sha(control / "out" / rel), "trace_sha256": sha(case / "out" / rel),
                         "byte_equal": (control / "out" / rel).read_bytes() == (case / "out" / rel).read_bytes()} for rel in products}
    assert all(v["byte_equal"] for v in comparison.values())
    event = json.loads((RUN / "H_RESULT.json").read_text())
    original = json.loads((ROOT / "harness/evidence/pr418_nine_channels_2026-10-12/RESULT.json").read_text())["events_added_channels"][1]
    assert event["BT_K"] == original["BT_K"] and event["rad_quality"] == original["rad_quality"]
    result = {"status": "RECOVERED_COMPLETE_PASSIVE_TRACE_NO_MODEL_REPLAY", "snapshot": "2025-07-19_07:00:00",
              "physical_channels": channels, "profile_rows_per_direct_K_call": len(rows)//2,
              "trigger_rows": triggered, "quality": quality, "raw_noninterference": comparison,
              "all_raw_products_byte_equal": True, "matches_PR418_BT_bits": True,
              "contribution": "aggregate clear/gas extinction alone exceeds20km^-1; aerosol and hydrometeor additions zero in this saved07 profile",
              "individual_gas_attribution": False, "source_to_original_executable_attestation": False,
              "invalid_clear_column_diagnostic_fields_excluded": ["ext_all(0)", "icldarr(0)"],
              "first_trace_incomplete": True, "second_trace_complete_postprocessing_schema_mismatch_recovered": True,
              "actual_trace_campaign_logical_H_calls": 3, "M_optimizer_native_calls": 0,
              "trace_sha256": sha(RUN / "EXT_TRACE.txt"), "runtime_case": str(case)}
    with (PACKET / "EXTINCTION_TRACE_SUMMARY.json").open("x") as f:
        json.dump(result, f, indent=2, allow_nan=False)
        f.write("\n")
    with (PACKET / "EXTINCTION_TRIGGER_ROWS.csv").open("x", newline="") as f:
        fields = ["call", "channel", "layer_topdown_1based", "overlap_column", "p_top_hPa", "p_lay_hPa", "p_bottom_hPa",
                  "T_K", "q_internal", "ltick_vertical_km", "pathsat", "slant_length_km", "clear_floored_km_inv", "hydro_km_inv", "pre_km_inv", "post_km_inv"]
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(triggered)
    print(json.dumps({"status": result["status"], "trigger_rows": len(triggered), "raw_byte_equal": True}))


if __name__ == "__main__":
    main()
