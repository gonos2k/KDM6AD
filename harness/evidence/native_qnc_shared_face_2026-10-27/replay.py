#!/usr/bin/env python3
"""Hash-bound offline replay of the two full-domain QNC shared-face traces."""
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

from harness.analyze_qnc_shared_face_trace import analyze_shared_trace, read_shared_trace  # noqa: E402


RUNS = {"control": "control_shared_v1_on", "alpha025": "alpha025_shared_v1_on"}
EXPECTED_CONFIG = {
    "MP_PHYSICS": "137", "SCALAR_ADV_OPT": "11*1", "RK_ORD": "3",
    "H_SCA_ADV_ORDER": "11*5", "V_SCA_ADV_ORDER": "11*3",
    "ZADVECT_IMPLICIT": "0", "NO_MP_HEATING": "0", "USE_Q_DIABATIC": "0",
    "RA_LW_PHYSICS": "4", "RA_SW_PHYSICS": "4", "BL_PBL_PHYSICS": "11",
    "CU_PHYSICS": "37", "NUMTILES": "2", "NPROC_X": "1", "NPROC_Y": "1",
}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate() -> dict:
    manifest = json.loads((PACKET / "manifest.json").read_text())
    if manifest.get("schema") != "kdm6.native_qnc_shared_face_public_packet.v1":
        raise ValueError("wrong shared-face packet manifest")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("shared-face packet has no file inventory")
    seen = set()
    for item in files:
        rel = item["path"]
        if (not isinstance(rel, str) or Path(rel).is_absolute() or ".." in Path(rel).parts
                or rel in seen):
            raise ValueError(f"unsafe or repeated packet path: {rel}")
        seen.add(rel)
        path = PACKET / rel
        if path.is_symlink() or not path.resolve().is_relative_to(PACKET.resolve()):
            raise ValueError(f"packet path escapes the packet: {rel}")
        raw = path.read_bytes()
        if len(raw) != item["bytes"] or _sha(raw) != item["sha256"]:
            raise ValueError(f"packet asset differs: {rel}")
    for rel, expected in manifest["external_source_pins"].items():
        if _sha((REPO / rel).read_bytes()) != expected:
            raise ValueError(f"shared-face replay source changed: {rel}")
    old_packet = REPO / "harness/evidence/native_qnc_flux_2026-10-27/manifest.json"
    if _sha(old_packet.read_bytes()) != manifest["historical_pr457_packet_manifest_sha256"]:
        raise ValueError("historical QNC flux packet manifest changed")
    return manifest


def build_analysis() -> dict:
    summary = json.loads((PACKET / "receipts/execution_summary.json").read_text())
    flags = json.loads((PACKET / "receipts/runtime_flags.json").read_text())
    if summary["full_host_steps_completed"] != 4 or summary["RTTOV_calls"] != 0:
        raise ValueError("shared-face run accounting differs")
    cases = {}
    for case, run_id in RUNS.items():
        arms = summary["cases"][case]
        pair = arms["pair"]
        if (arms["off"]["status"] != "PASS" or arms["on"]["status"] != "PASS"
                or arms["off"]["checkpoint_sha256"] != arms["on"]["checkpoint_sha256"]
                or arms["off"]["ack_sha256"] != arms["on"]["ack_sha256"]
                or not pair["raw_bitwise_equal"] or not pair["ack_byte_identical"]
                or pair["numeric_elements_compared"] != 322426586
                or pair["variable_count"] != 652 or pair["numeric_element_mismatches"] != 0):
            raise ValueError(f"{case} full-domain off/on comparison differs")
        values = flags["cases"][case]["raw_values"]
        if any(values.get(key) != expected for key, expected in EXPECTED_CONFIG.items()):
            raise ValueError(f"{case} runtime physics/advect configuration differs")
        data = PACKET / "data" / case
        for tag, filename in (("shared", "qnc_shared.tsv"), ("flux", "qnc_flux.tsv"),
                              ("upstream", "upstream_nc.tsv"), ("host", "host.hex"),
                              ("kernel", "kernel.hex")):
            raw = (data / filename).read_bytes()
            if (_sha(raw) != arms["on"]["trace_artifacts"][tag]["sha256"]
                    or len(raw) != arms["on"]["trace_artifacts"][tag]["bytes"]):
                raise ValueError(f"{case} {tag} differs from its same-run receipt")
        if sum(line.startswith("CALL ") for line in (data / "host.hex").read_text().splitlines()) != 2:
            raise ValueError(f"{case} did not record two KDM wrapper entries")
        shared = read_shared_trace(data / "qnc_shared.tsv")
        case_analysis = analyze_shared_trace(
            shared, flux_path=data / "qnc_flux.tsv",
            upstream_path=data / "upstream_nc.tsv", run_id=run_id)
        if not case_analysis["all_captured_checks_pass"]:
            raise ValueError(f"{case} shared-face/source-order checks failed")
        cases[case] = case_analysis
    face_differences = {
        name: {
            "correction_alpha_minus_control": cases["alpha025"]["six_internal_faces"][name]["correction"]["value"]
            - cases["control"]["six_internal_faces"][name]["correction"]["value"],
            "low_order_alpha_minus_control": cases["alpha025"]["six_internal_faces"][name]["low_order"]["value"]
            - cases["control"]["six_internal_faces"][name]["low_order"]["value"],
        }
        for name in cases["control"]["six_internal_faces"]
    }
    return {
        "schema": "kdm6.native_qnc_shared_face_public_analysis.v1",
        "cases": cases,
        "between_input_face_differences_raw_coordinate": face_differences,
        "full_host_steps_from_receipts": 4,
        "same_input_off_on_checkpoint_variables": 652,
        "same_input_off_on_numeric_elements": 322426586,
        "shared_correction_and_low_face_pairs_per_case": 6,
        "directional_tendency_checks_per_case": 21,
        "offline_model_calls": {"host": 0, "KDM6": 0, "RTTOV": 0, "optimizer": 0},
        "status": "SHARED_FACE_REPLAY_PASSED_LOCAL_LEDGER_OPEN",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="write only to a fresh file under this packet")
    args = parser.parse_args()
    _validate()
    analysis = build_analysis()
    payload = (json.dumps(analysis, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    if args.out is None:
        if (PACKET / "analysis.json").read_bytes() != payload:
            raise ValueError("shared-face replay differs from published analysis")
        print(json.dumps({"status": "REPLAY_PASSED", "analysis_sha256": _sha(payload),
                          "offline_model_calls": analysis["offline_model_calls"]}, sort_keys=True))
        return 0
    target = args.out if args.out.is_absolute() else PACKET / args.out
    if target.is_symlink() or not target.resolve(strict=False).is_relative_to(PACKET.resolve()):
        raise ValueError("replay output must remain in this packet")
    with target.open("xb") as stream:
        stream.write(payload)
    print(json.dumps({"status": "ANALYSIS_WRITTEN_NEW", "sha256": _sha(payload)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
