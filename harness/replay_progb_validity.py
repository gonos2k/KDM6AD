"""Validate S10 validity-bit streams without inspecting inactive OUT values.

A successful replay describes branch assignment and reached consumers only.  It
never claims that the value read through an unassigned native INTENT(OUT) was
zero, harmless, or physically acceptable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
PRESELECT = {"lat": 73, "active_i": 113, "inactive_i": 115}
INITIAL_ACTIVE_LEVELS = set(range(1, 12))
# The second column was selected as inactive from the retained t=0 QGRAUP/QIB
# fields, but the actual first ProgB call also sees the `brs > brs_min` arm.
# Native traces show that gate active on levels 4..11 and inactive on 1..3.
MIXED_COLUMN_ACTIVE_LEVELS = set(range(4, 12))
LEVELS = set(range(1, 40))
PROGB_CALL_CONTEXTS = {
    (1, 73, 1, 0, 0),
    (1, 73, 2, 1, 1),
    (1, 73, 2, 1, 2),
    (1, 73, 3, 1, 1),
    (1, 73, 4, 1, 0),
    (1, 73, 5, 1, 0),
    (1, 73, 6, 1, 0),
    (1, 73, 7, 1, 0),
}
RECORD_WIDTHS = {"S10CMG": 9, "S10PB": 12, "S10SLP": 18,
                 "S10RHO": 10, "S10DIAG": 7, "S10SCAN": 6,
                 "S10TRACE": 14, "S10TRS": 16}
SOURCE_SHA256 = {
    "mp37": "fc0a72d33a5e61803fea56eb9118018039c6da8b5775813032b4861a2bd66eb5",
    "mp237": "4f0103c8a8321b8e854d3500f4ae567755e41eb78746fac54519eca2686a6648",
}
INPUT_SHA256 = {
    "wrfinput_d01": "5a9ae8da992028dbf3a2a7652eb61532c1efab2acea7ea0e393e4cac8fd4c970",
    "wrfbdy_d01": "d46e5d7117c076956d130b4ff905fc34a5d53dbd5a0d9571311582b0a60c5e6c",
    "wrfchainp_d01": "c8e300d2aa52f98c9060803438ab6f796bddd1e1cdd6b75a14e39a398cb0c4e3",
}
CAPTURE_GOLDENS = {
    "mp37": {
        "sha256": "63319cb120a1f16d46b5be1a56b800a7d0289ef67a9b2627284947b0878fd684",
        "record_count": 5662,
        "record_counts": {
            "S10SCAN": 1974, "S10TRACE": 763, "S10TRS": 763,
            "S10CMG": 624, "S10PB": 624, "S10SLP": 624,
            "S10RHO": 212, "S10DIAG": 78,
        },
    },
    "mp237": {
        "sha256": "dc3d122fa9252a4c6bfd51db032d08223e0fc390a73f87ebdd866d3aeea922e0",
        "record_count": 5678,
        "record_counts": {
            "S10SCAN": 1974, "S10TRACE": 771, "S10TRS": 771,
            "S10CMG": 624, "S10PB": 624, "S10SLP": 624,
            "S10RHO": 212, "S10DIAG": 78,
        },
    },
}
RHO_CONSUMER_ID_CONTRACT = {
    "1418": {"operation": "pgmlt/rhox", "source_line_mp37": 1418, "source_line_mp237": 1456},
    "2824": {"operation": "pgdep/rhox", "source_line_mp37": 2824, "source_line_mp237": 2862},
    "2915": {"operation": "pgevp/rhox", "source_line_mp37": 2915, "source_line_mp237": 2953},
    "2916": {"operation": "pgeml/rhox", "source_line_mp37": 2916, "source_line_mp237": 2954},
    "3027": {"operation": "preProgB max/rhox", "source_line_mp37": 3027, "source_line_mp237": 3065},
}
FLAG_INDICES = {
    "S10CMG": (7, 8),
    "S10PB": (7, 8, 9, 10, 11),
    "S10SLP": tuple(range(7, 18)),
    "S10RHO": (8, 9),
    "S10DIAG": (4, 5, 6),
    "S10SCAN": (5,),
    "S10TRACE": tuple(range(7, 14)),
    "S10TRS": tuple(range(7, 16)),
}


def parse_event_lines(lines: Iterable[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_no, line in enumerate(lines, 1):
        fields = line.split()
        if not fields or fields[0] not in RECORD_WIDTHS:
            continue
        tag = fields[0]
        if len(fields) != RECORD_WIDTHS[tag] + 1:
            raise ValueError(f"line {line_no}: {tag} has {len(fields)-1} fields; "
                             f"expected {RECORD_WIDTHS[tag]}")
        try:
            values = [int(value, 10) for value in fields[1:]]
        except ValueError as exc:
            raise ValueError(f"line {line_no}: {tag} records must contain integers only") from exc
        for index in FLAG_INDICES[tag]:
            if values[index] not in (0, 1):
                raise ValueError(f"line {line_no}: {tag} flag {index} is not 0/1")
        records.append({"tag": tag, "values": values, "line": line_no})
    if not records:
        raise ValueError("event stream contains no S10 validity records")
    return records


def _site_key(values: list[int]) -> tuple[int, ...]:
    # step, lat, site, loop, substep, i, k
    return tuple(values[:7])


def validate_events(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_tag: dict[str, list[dict[str, Any]]] = {
        tag: [row for row in records if row["tag"] == tag]
        for tag in RECORD_WIDTHS
    }
    for tag in ("S10CMG", "S10PB", "S10SLP"):
        keys = [_site_key(row["values"]) for row in by_tag[tag]]
        if len(keys) != len(set(keys)):
            raise ValueError(f"duplicate {tag} site/cell record")
    pb = {_site_key(row["values"]): row["values"] for row in by_tag["S10PB"]}
    cmg = {_site_key(row["values"]): row["values"] for row in by_tag["S10CMG"]}
    slope = {_site_key(row["values"]): row["values"] for row in by_tag["S10SLP"]}
    expected_producer_keys = {
        (*context, i, k)
        for context in PROGB_CALL_CONTEXTS
        for i in (PRESELECT["active_i"], PRESELECT["inactive_i"])
        for k in LEVELS
    }
    for tag, keyed in (("S10PB", pb), ("S10CMG", cmg), ("S10SLP", slope)):
        if set(keyed) != expected_producer_keys:
            missing = len(expected_producer_keys - set(keyed))
            extra = len(set(keyed) - expected_producer_keys)
            raise ValueError(f"{tag} producer/consumer universe mismatch: "
                             f"missing={missing}, extra={extra}")

    diag_keys = {tuple(row["values"][:4]) for row in by_tag["S10DIAG"]}
    expected_diag_keys = {
        (1, PRESELECT["lat"], i, k)
        for i in (PRESELECT["active_i"], PRESELECT["inactive_i"])
        for k in LEVELS
    }
    if diag_keys != expected_diag_keys:
        raise ValueError(f"final diagnostic consumer universe mismatch: "
                         f"missing={len(expected_diag_keys-diag_keys)}, "
                         f"extra={len(diag_keys-expected_diag_keys)}")

    first_call = (1, PRESELECT["lat"], 1, 0, 0)
    first = {key: values for key, values in pb.items()
             if key[:5] == first_call}
    expected = {
        (1, PRESELECT["lat"], 1, 0, 0, PRESELECT["active_i"], k)
        for k in LEVELS
    } | {
        (1, PRESELECT["lat"], 1, 0, 0, PRESELECT["inactive_i"], k)
        for k in LEVELS
    }
    if set(first) != expected:
        missing, extra = expected - set(first), set(first) - expected
        raise ValueError(f"site-1 selected-column coverage mismatch: missing={len(missing)}, "
                         f"extra={len(extra)}")

    active_flags: dict[int, dict[int, int]] = {}
    for i in (PRESELECT["active_i"], PRESELECT["inactive_i"]):
        active_flags[i] = {}
        for k in LEVELS:
            key = (1, PRESELECT["lat"], 1, 0, 0, i, k)
            values = first[key]
            active = values[7]
            expected_active = int(
                (i == PRESELECT["active_i"] and k in INITIAL_ACTIVE_LEVELS)
                or (i == PRESELECT["inactive_i"] and k in MIXED_COLUMN_ACTIVE_LEVELS)
            )
            if active != expected_active:
                raise ValueError(f"site-1 activity disagrees with preselected IC at i={i}, k={k}")
            active_flags[i][k] = active
            # The original producer reaches its cmg test after both active and
            # inactive branches.  On inactive cells the assigned bit is false;
            # this records source-level undefined-read exposure, not read value.
            if cmg[key][8] != 1:
                raise ValueError(f"site-1 cmg test was not reached at i={i}, k={k}")
            cmg_assigned = cmg[key][7]
            if cmg_assigned != values[9]:
                raise ValueError(f"cmg assignment bit disagrees between records at i={i}, k={k}")
            # An immediate slope call consumes pvtg unconditionally and chooses
            # pidn0g/bvtg or rslopegbmax by the same qg threshold branch.
            sv = slope[key]
            if sv[17] != 1 or sv[13] != 1:
                raise ValueError(f"site-1 slope consumer did not reach pvtg at i={i}, k={k}")
            if sv[14] != active or sv[15] != active or sv[16] != (1 - active):
                raise ValueError(f"site-1 slope read-mask differs from qg branch at i={i}, k={k}")
            if active and not (sv[7] and sv[8] and sv[9] and sv[10] and sv[11]):
                raise ValueError(f"active site-1 density/table outputs were not assigned at i={i}, k={k}")

    unsafe_cmg = [row for row in by_tag["S10CMG"]
                  if row["values"][0] == 1 and row["values"][2] == 1
                  and row["values"][7] == 0 and row["values"][8] == 1]
    unsafe_slope = [row for row in by_tag["S10SLP"]
                    if row["values"][0] == 1 and row["values"][2] == 1
                    and not all(row["values"][index] for index in (7, 8, 10))
                    and row["values"][13] == 1]
    unassigned_rhox_reads = [row for row in by_tag["S10RHO"]
                             if row["values"][8] == 0 and row["values"][9] == 1]
    unknown_rhox_consumer_ids = sorted({str(row["values"][7]) for row in by_tag["S10RHO"]}
                                       - set(RHO_CONSUMER_ID_CONTRACT))
    if unknown_rhox_consumer_ids:
        raise ValueError(f"S10RHO contains unknown semantic consumer IDs: {unknown_rhox_consumer_ids}")
    diag_bad = [row for row in by_tag["S10DIAG"]
                if row["values"][4] == 1 and row["values"][5] == 0 and row["values"][6] == 1]
    scans = {tuple(row["values"][:5]): row["values"] for row in by_tag["S10SCAN"]}
    if len(scans) != len(by_tag["S10SCAN"]):
        raise ValueError("duplicate ProgB per-call trace scan summary")
    trace = {tuple(row["values"][:5]): row["values"] for row in by_tag["S10TRACE"]}
    trace_slope = {tuple(row["values"][:5]): row["values"] for row in by_tag["S10TRS"]}
    if len(trace) != len(by_tag["S10TRACE"]) or len(trace_slope) != len(by_tag["S10TRS"]):
        raise ValueError("duplicate trace cell record for one producer call")
    if set(trace) != set(trace_slope):
        raise ValueError("trace producer and slope-consumer records do not pair")
    for key, scan_values in scans.items():
        expected_found = int(key in trace)
        if scan_values[5] != expected_found:
            raise ValueError("per-call trace summary disagrees with trace detail")
        if key in trace:
            producer, consumer = trace[key], trace_slope[key]
            if producer[7:10] != [1, 0, 0]:
                raise ValueError("trace producer row does not satisfy qg>0 inactive-gate predicate")
            if consumer[7:9] != [1, 0] or consumer[13:16] != [1, 1, 1]:
                raise ValueError("trace slope row does not attest the expected reached reads")
    site1_scans = {key for key in scans
                   if key[0] == 1 and key[1] in range(2, 282) and key[2] == 1
                   and key[3:] == (0, 0)}
    expected_site1_scans = {(1, lat, 1, 0, 0) for lat in range(2, 282)}
    if site1_scans != expected_site1_scans:
        raise ValueError(f"initial ProgB trace scan lacks full latitude coverage: "
                         f"missing={len(expected_site1_scans-site1_scans)}, "
                         f"extra={len(site1_scans-expected_site1_scans)}")
    selected_call_keys = {key[:5] for key in pb}
    if not selected_call_keys.issubset(scans):
        raise ValueError("a selected-column ProgB call lacks its trace-scan record")

    return {
        "schema": "progb-validity-replay-v1",
        "records": {tag: len(rows) for tag, rows in by_tag.items()},
        "site1_selected_cells": 2,
        "site1_levels_per_cell": len(LEVELS),
        "site1_expected_active_levels": sorted(INITIAL_ACTIVE_LEVELS),
        "site1_observed_active_levels_by_i": {
            str(PRESELECT["active_i"]): sorted(INITIAL_ACTIVE_LEVELS),
            str(PRESELECT["inactive_i"]): sorted(MIXED_COLUMN_ACTIVE_LEVELS),
        },
        "trace_qg_nonzero_inactive_gate_records": len(trace),
        "source_level_p2": {
            "cmg_intent_out_test_reached_without_assignment": len(unsafe_cmg) > 0,
            "slope_parameter_read_reached_without_defined_producer_chain": len(unsafe_slope) > 0,
            "rhox_read_reached_without_assignment": len(unassigned_rhox_reads) > 0,
            "final_diagnostic_read_reached_without_assignment": len(diag_bad) > 0,
            "unsafe_record_counts": {
                "cmg": len(unsafe_cmg), "slope": len(unsafe_slope),
                "rhox": len(unassigned_rhox_reads), "diag": len(diag_bad),
            },
        },
        "undefined_output_values_serialized": False,
        "undefined_output_physical_impact": "NOT_MEASURED",
        "physical_number_or_trace_policy": "OPEN",
    }


def validate_capture_payload(manifest: dict[str, Any], lines: Iterable[str]) -> None:
    """Pin the exact event census so deleting paired/conditional rows fails closed."""
    variant = manifest.get("source", {}).get("variant")
    if variant not in CAPTURE_GOLDENS:
        raise ValueError("capture payload has no source-pinned golden")
    golden = CAPTURE_GOLDENS[variant]
    normalized = [line.rstrip("\r\n") for line in lines]
    payload = ("\n".join(normalized) + "\n").encode("utf-8")
    capture = manifest.get("capture", {})
    if (capture.get("event_payload_sha256") != golden["sha256"]
            or capture.get("event_record_count") != golden["record_count"]
            or capture.get("event_record_counts") != golden["record_counts"]):
        raise ValueError("manifest capture census differs from the code-pinned golden")
    if hashlib.sha256(payload).hexdigest() != golden["sha256"]:
        raise ValueError("capture event payload SHA-256 differs from the code-pinned golden")
    records = parse_event_lines(normalized)
    counts: dict[str, int] = {}
    for record in records:
        counts[record["tag"]] = counts.get(record["tag"], 0) + 1
    expected_counts = capture.get("event_record_counts")
    if counts != expected_counts:
        raise ValueError("capture event record counts differ from the code-pinned golden")
    if len(records) != golden["record_count"]:
        raise ValueError("capture event record total differs from the code-pinned golden")


def validate_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("schema") != "progb-validity-run-v1":
        raise ValueError("manifest schema must be progb-validity-run-v1")
    if manifest.get("execution_status") != "completed":
        raise ValueError("prepared manifest only: native execution has not been accepted")
    source = manifest.get("source", {})
    if source.get("strip_exact") is not True:
        raise ValueError("capture source does not attest strip-exact recovery")
    variant = source.get("variant")
    if variant not in SOURCE_SHA256:
        raise ValueError("unsupported Fortran variant")
    if source.get("canonical_source_sha256") != SOURCE_SHA256[variant]:
        raise ValueError("capture source is not the current canonical private source")
    capture = manifest.get("capture", {})
    golden = CAPTURE_GOLDENS[variant]
    if (capture.get("event_payload_sha256") != golden["sha256"]
            or capture.get("event_record_count") != golden["record_count"]
            or capture.get("event_record_counts") != golden["record_counts"]):
        raise ValueError("manifest capture census differs from the code-pinned golden")
    if capture.get("rhox_consumer_id_contract") != RHO_CONSUMER_ID_CONTRACT:
        raise ValueError("manifest S10RHO consumer-ID meanings differ from the code-pinned contract")
    run = manifest.get("run", {})
    expected_scheme = 37 if variant == "mp37" else 237
    if (run.get("mp_physics") != expected_scheme or run.get("dt_s") != 20
            or run.get("actual_proc_grid") != "1x1" or run.get("ranks") != 1
            or run.get("threads_per_rank") != 1):
        raise ValueError("native scope must use the declared 20 s serial LC05 run")
    if run.get("saved_times") != ["2025-07-19_00:00:00", "2025-07-19_00:00:20"]:
        raise ValueError("native scope must save exactly t=0 and t=20 s")
    input_hashes = manifest.get("input_sha256", {})
    if any(input_hashes.get(name) != digest for name, digest in INPUT_SHA256.items()):
        raise ValueError("native input/boundary identities differ from the retained LC05 set")
    noninterference = manifest.get("noninterference", {})
    if noninterference.get("numeric_raw_bits_equal") is not True:
        raise ValueError("logging capture does not attest raw-bit history equality")
    if noninterference.get("saved_times_equal") is not True:
        raise ValueError("logging capture does not attest identical saved times")
    control = noninterference.get("history_sha256", {}).get("control")
    capture = noninterference.get("history_sha256", {}).get("capture")
    if not control or control != capture:
        raise ValueError("control/capture histories are absent or differ")
    exe = noninterference.get("executable_sha256", {})
    if not exe.get("control") or exe.get("control") != exe.get("capture"):
        raise ValueError("logging-off/on arms must use the same executable")
    identities = noninterference.get("input_identity_sha256", {})
    if not identities.get("control") or identities.get("control") != identities.get("capture"):
        raise ValueError("logging-off/on arms must use identical input identities")
    namelists = noninterference.get("namelist_sha256", {})
    if not namelists.get("control") or namelists.get("control") != namelists.get("capture"):
        raise ValueError("logging-off/on arms must use identical namelists")
    logging = noninterference.get("logging_enabled", {})
    if logging.get("control") is not False or logging.get("capture") is not True:
        raise ValueError("control must disable logging and capture must enable it")
    if manifest.get("physical_validity_policy") != "OPEN":
        raise ValueError("this probe cannot close or choose the physical validity policy")


def replay(manifest: dict[str, Any], lines: Iterable[str]) -> dict[str, Any]:
    validate_manifest(manifest)
    event_lines = list(lines)
    validate_capture_payload(manifest, event_lines)
    result = validate_events(parse_event_lines(event_lines))
    result["source"] = manifest["source"]
    result["noninterference"] = manifest["noninterference"]
    result["capture_payload"] = {
        "event_payload_sha256": manifest["capture"]["event_payload_sha256"],
        "event_record_count": manifest["capture"]["event_record_count"],
        "event_record_counts": manifest["capture"]["event_record_counts"],
        "rhox_consumer_id_contract": manifest["capture"]["rhox_consumer_id_contract"],
    }
    result["execution_status"] = "completed"
    result["physical_validity_policy"] = "OPEN"
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True,
                        help="combined host stdout/stderr text containing S10 records")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = replay(json.loads(args.manifest.read_text()), args.events.read_text().splitlines())
    payload = json.dumps(result, indent=2) + "\n"
    if args.out:
        args.out.write_text(payload)
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()
