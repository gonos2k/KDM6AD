#!/usr/bin/env python3
"""Hash-bound offline replay of the native seven-cell QNC PD→RK3 trace."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


PACKET = Path(__file__).resolve().parent
REPO = PACKET.parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from harness.analyze_native_qnc_state7_trace import analyze_state7, read_state7_trace  # noqa: E402
from harness.analyze_qnc_shared_face_trace import read_shared_trace  # noqa: E402


RUNS = {"control": "control_state7_v1_on", "alpha025": "alpha025_state7_v1_on"}
SOURCE_PLAN_SHA = {
    "control": "6032da73badc756c06410669d540daf53491afaa4f9705765ba7f270ac4343f7",
    "alpha025": "d31c18fc2a0e97c6fbdc6b2d4250b3bc561b9c2c808afa9835224f37eba499ab",
}
EXPECTED_RUNTIME = {
    "MP_PHYSICS": "137", "SCALAR_ADV_OPT": "11*1", "RK_ORD": "3",
    "H_SCA_ADV_ORDER": "11*5", "V_SCA_ADV_ORDER": "11*3",
    "ZADVECT_IMPLICIT": "0", "NO_MP_HEATING": "0", "USE_Q_DIABATIC": "0",
    "RA_LW_PHYSICS": "4", "RA_SW_PHYSICS": "4", "BL_PBL_PHYSICS": "11",
    "CU_PHYSICS": "37", "NUMTILES": "2", "NPROC_X": "1", "NPROC_Y": "1",
}


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _validate() -> dict:
    manifest = json.loads((PACKET / "manifest.json").read_text())
    if manifest.get("schema") != "kdm6.native_qnc_state7_public_packet.v1":
        raise ValueError("wrong state7 packet schema")
    seen = set()
    for item in manifest["files"]:
        rel = item["path"]
        if (not isinstance(rel, str) or Path(rel).is_absolute() or ".." in Path(rel).parts
                or rel in seen):
            raise ValueError(f"unsafe/repeated state7 packet path: {rel}")
        seen.add(rel)
        path = PACKET / rel
        if path.is_symlink() or not path.resolve().is_relative_to(PACKET.resolve()):
            raise ValueError(f"state7 packet asset escapes: {rel}")
        raw = path.read_bytes()
        if len(raw) != item["bytes"] or _sha(raw) != item["sha256"]:
            raise ValueError(f"state7 packet asset changed: {rel}")
    for rel, expected in manifest["external_source_pins"].items():
        if _sha((REPO / rel).read_bytes()) != expected:
            raise ValueError(f"state7 replay source changed: {rel}")
    old = REPO / "harness/evidence/native_qnc_shared_face_2026-10-27/manifest.json"
    if _sha(old.read_bytes()) != manifest["historical_pr459_packet_manifest_sha256"]:
        raise ValueError("historical PR459 shared-face packet changed")
    return manifest


def build_analysis() -> dict:
    execution = json.loads((PACKET / "receipts/execution_summary.json").read_text())
    runtime = json.loads((PACKET / "receipts/runtime_flags.json").read_text())
    build = json.loads((PACKET / "receipts/build_summary.json").read_text())
    if (execution["full_host_steps_completed"] != 4 or execution["RTTOV_calls"] != 0
            or execution["optimizer_calls"] != 0 or execution["accepted_analysis_updates"] != 0
            or execution["ranks"] != 1 or execution["threads"] != 1 or execution["numtiles"] != 2
            or execution["KDM_wrapper_entries_expected"] != 8):
        raise ValueError("state7 execution accounting differs")
    cases = {}
    for case, run_id in RUNS.items():
        arms = execution["cases"][case]
        pair = arms["pair"]
        origin_hashes = set()
        for mode in ("off", "on"):
            path = PACKET / "receipts/plans" / f"{case}_{mode}.json"
            raw = path.read_bytes()
            plan = json.loads(raw)
            arm = arms[mode]
            origin_hashes.add(plan["origin_checkpoint_sha256"])
            if (_sha(raw) != arm["plan_sha256"] or plan["run_id"] != arm["run_id"]
                    or plan["trace_mode"] != mode or plan["source_case"] != case
                    or plan["source_plan_sha256"] != arm["source_plan_sha256"]
                    or arm["source_plan_sha256"] != SOURCE_PLAN_SHA[case]
                    or plan["build_receipt_sha256"] != build["private_build_receipt_sha256"]
                    or plan["executable_sha256"] != build["executable_sha256"]
                    or plan["dso_sha256"] != build["dso_sha256"]
                    or plan["expected_reference_checkpoint_sha256"] != arm["checkpoint_sha256"]
                    or plan["host_steps_requested"] != 1 or plan["RTTOV_calls"] != 0
                    or plan["optimizer_calls"] != 0):
                raise ValueError(f"{case} {mode} plan/source/build/run binding differs")
        if len(origin_hashes) != 1:
            raise ValueError(f"{case} off/on arms have different READY40 checkpoints")
        if (arms["off"]["status"] != "PASS" or arms["on"]["status"] != "PASS"
                or arms["off"]["checkpoint_sha256"] != arms["on"]["checkpoint_sha256"]
                or arms["off"]["ack_sha256"] != arms["on"]["ack_sha256"]
                or not pair["raw_bitwise_equal"] or not pair["ack_byte_identical"]
                or pair["variable_count"] != 652 or pair["numeric_elements_compared"] != 322426586
                or pair["numeric_element_mismatches"] != 0):
            raise ValueError(f"{case} full-state noninterference differs")
        values = runtime["cases"][case]["raw_values"]
        if any(values.get(key) != expected for key, expected in EXPECTED_RUNTIME.items()):
            raise ValueError(f"{case} native run configuration differs")
        data = PACKET / "data" / case
        for tag, filename in (("state7", "qnc_state7.tsv"), ("shared", "qnc_shared.tsv"),
                              ("flux", "qnc_flux.tsv"), ("host", "host.hex"),
                              ("kernel", "kernel.hex")):
            raw = (data / filename).read_bytes()
            source = arms["on"]["trace_artifacts"][tag]
            if len(raw) != source["bytes"] or _sha(raw) != source["sha256"]:
                raise ValueError(f"{case} {tag} differs from same-run receipt")
        if sum(line.startswith("CALL ") for line in (data / "host.hex").read_text().splitlines()) != 2:
            raise ValueError(f"{case} KDM host trace must have two wrapper calls")
        context = data / "checkpoint_context.json"
        if _sha(context.read_bytes()) != arms["on"]["checkpoint_context_sha256"]:
            raise ValueError(f"{case} saved checkpoint context differs")
        result = analyze_state7(
            read_state7_trace(data / "qnc_state7.tsv"),
            run_id=run_id,
            checkpoint_context=json.loads(context.read_text()),
            shared_face_trace=read_shared_trace(data / "qnc_shared.tsv"),
        )
        cases[case] = result
    return {
        "schema": "kdm6.native_qnc_state7_public_analysis.v1",
        "status": "SEVEN_CELL_PD_RK3_STATE_REPLAY_PASSED_LATER_INTERVAL_OPEN",
        "cases": cases,
        "full_host_steps_from_receipts": 4,
        "off_on_variable_count": 652,
        "off_on_numeric_elements": 322426586,
        "offline_model_calls": {"host": 0, "KDM6": 0, "RTTOV": 0, "optimizer": 0},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="write only to a fresh file inside the packet")
    args = parser.parse_args()
    _validate()
    result = build_analysis()
    payload = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    if args.out is None:
        if (PACKET / "analysis.json").read_bytes() != payload:
            raise ValueError("state7 replay differs from published analysis")
        print(json.dumps({"status": "REPLAY_PASSED", "analysis_sha256": _sha(payload),
                          "offline_model_calls": result["offline_model_calls"]}, sort_keys=True))
        return 0
    output = args.out if args.out.is_absolute() else PACKET / args.out
    if output.is_symlink() or not output.resolve(strict=False).is_relative_to(PACKET.resolve()):
        raise ValueError("replay output must stay inside the packet")
    with output.open("xb") as stream:
        stream.write(payload)
    print(json.dumps({"status": "ANALYSIS_WRITTEN_NEW", "sha256": _sha(payload)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
