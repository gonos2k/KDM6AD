#!/usr/bin/env python3
"""Replay the seven-cell saved QNC PD/face/RK state budget offline."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys


PACKET = Path(__file__).resolve().parent
REPO = PACKET.parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from harness.analyze_native_qnc_saved_state_budget import analyze_saved_state_budget  # noqa: E402
from harness.analyze_native_qnc_state7_trace import analyze_state7, read_state7_trace  # noqa: E402
from harness.analyze_qnc_shared_face_trace import read_shared_trace  # noqa: E402


OLD_PACKET = REPO / "harness/evidence/native_qnc_state7_2026-10-27"
OLD_MANIFEST_SHA256 = "6737fdabf1c023fe808c00c39b5d1007a43aa1323737f19a63ba1b7fb643ed02"
OLD_ANALYZER_SHA256 = "31485ee7664fef2f73328fe079a611515697732c2f798978db0d5d23ea69b78f"
RUNS = {"control": "control_state7_v1_on", "alpha025": "alpha025_state7_v1_on"}


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _check_files(root: Path, manifest: dict) -> None:
    for item in manifest["files"]:
        path = root / item["path"]
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"packet path escapes: {item['path']}")
        raw = path.read_bytes()
        if len(raw) != item["bytes"] or _sha(raw) != item["sha256"]:
            raise ValueError(f"packet asset differs: {item['path']}")


def _validate() -> None:
    manifest = json.loads((PACKET / "manifest.json").read_text())
    if manifest.get("schema") != "kdm6.native_qnc_state_budget_public_packet.v1":
        raise ValueError("wrong state-budget packet schema")
    _check_files(PACKET, manifest)
    for name, expected in manifest["external_source_pins"].items():
        if _sha((REPO / name).read_bytes()) != expected:
            raise ValueError(f"state-budget source changed: {name}")


def _target_boundary(data: Path, state, checkpoint: dict) -> dict:
    """Join the existing target KDM/host moment records to the RK3 output."""
    headers = []
    for file in ("kernel.hex", "host.hex"):
        calls = [line.split() for line in (data / file).read_text().splitlines()
                 if line.startswith("CALL ")]
        if not calls or any(len(call) != 15 for call in calls):
            raise ValueError(f"invalid target call headers in {file}")
        headers.append(calls)
    if headers[0] != headers[1]:
        raise ValueError("KDM and host call headers differ")
    owners = [call[1] for call in headers[0] if
              int(call[3]) <= 221 <= int(call[4]) and
              int(call[5]) <= 6 <= int(call[6]) and
              int(call[7]) <= 63 <= int(call[8])]
    if len(owners) != 1:
        raise ValueError("target must belong to exactly one wrapper call")
    owner = owners[0]
    observed = {}
    for file, stages in (("kernel.hex", {"FP64_INPUT", "FP64_OUTPUT"}),
                         ("host.hex", {"MP_INPUT", "MOMENTS_POST"})):
        for line in (data / file).read_text().splitlines():
            parts = line.split()
            if (len(parts) != 9 or parts[0] != "VAL" or parts[1] != owner
                    or parts[2] not in stages or parts[3:6] != ["221", "6", "63"]
                    or parts[7] not in {"QC", "NC"}):
                continue
            stage, dtype, field, word = parts[2], parts[6], parts[7], parts[8]
            if dtype not in {"f32", "f64"} or len(word) != (8 if dtype == "f32" else 16):
                raise ValueError(f"invalid target moment record: {line}")
            key = (stage, field)
            if key in observed:
                raise ValueError(f"duplicate target moment record: {key}")
            observed[key] = (dtype, word, struct.unpack(">f" if dtype == "f32" else ">d",
                                                    bytes.fromhex(word))[0])
    if len(observed) != 8:
        raise ValueError("target KDM/host moment records incomplete")
    rk_bits = int(state.at((221, 63, 6), 0, "PRE_MICROPHYSICS", "QNC").bits)
    saved = checkpoint["cells"]["i221_j63_k6"]
    for field in ("NC", "QC"):
        if (observed[("MP_INPUT", field)][0] != "f32" or
                observed[("MOMENTS_POST", field)][0] != "f32" or
                observed[("FP64_INPUT", field)][0] != "f64" or
                observed[("FP64_OUTPUT", field)][0] != "f64" or
                observed[("FP64_INPUT", field)][2] != observed[("MP_INPUT", field)][2] or
                struct.pack(">f", observed[("FP64_OUTPUT", field)][2]).hex().upper() !=
                observed[("MOMENTS_POST", field)][1]):
            raise ValueError(f"target KDM/host {field} conversion differs")
    if (int(observed[("MP_INPUT", "NC")][1], 16) != rk_bits or
            observed[("MOMENTS_POST", "NC")][1] != saved["final_nc_bits_hex"] or
            observed[("MOMENTS_POST", "QC")][1] != saved["final_qc_bits_hex"]):
        raise ValueError("target RK3→KDM→checkpoint moment handoff differs")
    if observed[("FP64_OUTPUT", "QC")][2] <= 0 or observed[("MOMENTS_POST", "QC")][2] <= 0:
        raise ValueError("target output no longer has positive QC")
    return {
        "native_one_based_ijk": [221, 63, 6],
        "owner_call_id": int(owner),
        "fp64_input_nc_raw": observed[("FP64_INPUT", "NC")][2],
        "fp64_output_nc_raw": observed[("FP64_OUTPUT", "NC")][2],
        "fp64_output_qc_kg_per_kg_dry": observed[("FP64_OUTPUT", "QC")][2],
        "host_moments_post_nc_raw": observed[("MOMENTS_POST", "NC")][2],
        "host_moments_post_qc_kg_per_kg_dry": observed[("MOMENTS_POST", "QC")][2],
    }


def build_analysis() -> dict:
    old_bytes = (OLD_PACKET / "manifest.json").read_bytes()
    if _sha(old_bytes) != OLD_MANIFEST_SHA256:
        raise ValueError("PR461 historical manifest changed")
    old_manifest = json.loads(old_bytes)
    _check_files(OLD_PACKET, old_manifest)
    snapshot = PACKET / "source_snapshots/pr461_analyze_native_qnc_state7_trace.py.txt"
    for name, expected in old_manifest["external_source_pins"].items():
        if name == "harness/analyze_native_qnc_state7_trace.py":
            if expected != OLD_ANALYZER_SHA256 or _sha(snapshot.read_bytes()) != expected:
                raise ValueError("historical PR461 analyzer pin differs")
        elif _sha((REPO / name).read_bytes()) != expected:
            raise ValueError(f"historical PR461 producer/source differs: {name}")
    old_shared = REPO / "harness/evidence/native_qnc_shared_face_2026-10-27/manifest.json"
    if _sha(old_shared.read_bytes()) != old_manifest["historical_pr459_packet_manifest_sha256"]:
        raise ValueError("historical PR459 shared-face manifest differs")
    saved = json.loads((OLD_PACKET / "analysis.json").read_text())
    cases = {}
    for case, run_id in RUNS.items():
        data = OLD_PACKET / "data" / case
        state = read_state7_trace(data / "qnc_state7.tsv")
        shared = read_shared_trace(data / "qnc_shared.tsv")
        checkpoint = json.loads((data / "checkpoint_context.json").read_text())
        current = json.loads(json.dumps(analyze_state7(
            state, run_id=run_id,
            checkpoint_context=checkpoint,
            shared_face_trace=shared,
        )))
        if current != saved["cases"][case]:
            raise ValueError(f"hardened state7 analyzer changed the {case} published result")
        cases[case] = analyze_saved_state_budget(state, shared, run_id=run_id)
        cases[case]["target_kdm_boundary"] = _target_boundary(data, state, checkpoint)
    return {
        "schema": "kdm6.native_qnc_saved_state_budget_public_analysis.v1",
        "status": "SEVEN_CELL_SAVED_STATE_LEDGER_PASSED_PHYSICAL_BUDGET_OPEN",
        "historical_pr461_manifest_sha256": OLD_MANIFEST_SHA256,
        "cases": cases,
        "offline_model_calls": {"host": 0, "KDM6": 0, "RTTOV": 0, "optimizer": 0},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="write to a new path inside this packet")
    args = parser.parse_args()
    _validate()
    result = build_analysis()
    payload = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    if args.out is None:
        if (PACKET / "analysis.json").read_bytes() != payload:
            raise ValueError("saved state-budget analysis differs from published bytes")
        print(json.dumps({"status": "REPLAY_PASSED", "analysis_sha256": _sha(payload),
                          "offline_model_calls": result["offline_model_calls"]}, sort_keys=True))
        return 0
    output = args.out if args.out.is_absolute() else PACKET / args.out
    if output.is_symlink() or not output.resolve(strict=False).is_relative_to(PACKET.resolve()):
        raise ValueError("state-budget replay output must stay inside its packet")
    with output.open("xb") as stream:
        stream.write(payload)
    print(json.dumps({"status": "ANALYSIS_WRITTEN_NEW", "sha256": _sha(payload)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
