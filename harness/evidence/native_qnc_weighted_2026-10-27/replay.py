#!/usr/bin/env python3
"""Replay the exact seven-cell QNC numerical ledger from the PR459 packet."""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys


PACKET = Path(__file__).resolve().parent
REPO = PACKET.parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from harness.analyze_qnc_shared_face_trace import analyze_shared_trace, read_shared_trace  # noqa: E402
from harness.analyze_qnc_weighted_ledger import analyze_weighted_ledger  # noqa: E402


PR459_PACKET = REPO / "harness/evidence/native_qnc_shared_face_2026-10-27"
PR459_MANIFEST_SHA256 = "3bfe4111f89c77c475567b515789550606df3077dd5fcaaf4c6457d6be14a922"
RUNS = {"control": "control_shared_v1_on", "alpha025": "alpha025_shared_v1_on"}


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _verify_files(root: Path, manifest: dict) -> None:
    for item in manifest["files"]:
        path = root / item["path"]
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"packet path escapes its root: {item['path']}")
        raw = path.read_bytes()
        if len(raw) != item["bytes"] or _sha(raw) != item["sha256"]:
            raise ValueError(f"packet file differs: {item['path']}")


def _validate_current_packet() -> None:
    manifest = json.loads((PACKET / "manifest.json").read_text())
    if manifest.get("schema") != "kdm6.native_qnc_weighted_public_packet.v1":
        raise ValueError("wrong weighted-ledger packet schema")
    _verify_files(PACKET, manifest)
    for name, expected in manifest["external_source_pins"].items():
        if _sha((REPO / name).read_bytes()) != expected:
            raise ValueError(f"current weighted-ledger source changed: {name}")


def build_analysis() -> dict:
    old_bytes = (PR459_PACKET / "manifest.json").read_bytes()
    if _sha(old_bytes) != PR459_MANIFEST_SHA256:
        raise ValueError("historical PR459 packet manifest changed")
    old = json.loads(old_bytes)
    _verify_files(PR459_PACKET, old)
    saved = json.loads((PR459_PACKET / "analysis.json").read_text())
    cases = {}
    for case, run_id in RUNS.items():
        data = PR459_PACKET / "data" / case
        shared = read_shared_trace(data / "qnc_shared.tsv")
        current = json.loads(json.dumps(analyze_shared_trace(
            shared, flux_path=data / "qnc_flux.tsv",
            upstream_path=data / "upstream_nc.tsv", run_id=run_id)))
        previous = saved["cases"][case]
        for key, value in previous.items():
            if key == "same_run_pr457_target_join":
                if any(current[key].get(name) != old_value for name, old_value in value.items()):
                    raise ValueError(f"{case} old target joins changed")
            elif current[key] != value:
                raise ValueError(f"{case} published shared-face result changed: {key}")
        if current["same_run_pr457_target_join"].get("MSFTY") is not True:
            raise ValueError(f"{case} new same-run MSFTY join failed")
        cases[case] = analyze_weighted_ledger(shared, run_id=run_id)
    control, alpha = cases["control"], cases["alpha025"]
    differences = {}
    for key in ("exact_face_total", "perimeter_total", "recorded_weighted_tendency_total",
                "recorded_minus_exact_face"):
        value = Fraction(alpha[key]["exact"]) - Fraction(control[key]["exact"])
        differences[key + "_alpha_minus_control"] = {"exact": str(value), "approximately": float(value)}
    return {
        "schema": "kdm6.native_qnc_weighted_public_analysis.v1",
        "historical_pr459_manifest_sha256": PR459_MANIFEST_SHA256,
        "cases": cases,
        "between_input_differences_raw_coordinate": differences,
        "status": "SEVEN_CELL_NUMERICAL_LEDGER_PASSED_STATE_AND_DOMAIN_OPEN",
        "offline_model_calls": {"host": 0, "KDM6": 0, "RTTOV": 0, "optimizer": 0},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="write to a fresh path inside the weighted packet")
    args = parser.parse_args()
    _validate_current_packet()
    result = build_analysis()
    payload = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    if args.out is None:
        if (PACKET / "analysis.json").read_bytes() != payload:
            raise ValueError("weighted ledger differs from published analysis")
        print(json.dumps({"status": "REPLAY_PASSED", "analysis_sha256": _sha(payload),
                          "offline_model_calls": result["offline_model_calls"]}, sort_keys=True))
        return 0
    output = args.out if args.out.is_absolute() else PACKET / args.out
    if output.is_symlink() or not output.resolve(strict=False).is_relative_to(PACKET.resolve()):
        raise ValueError("weighted replay output must stay in the packet")
    with output.open("xb") as stream:
        stream.write(payload)
    print(json.dumps({"status": "ANALYSIS_WRITTEN_NEW", "sha256": _sha(payload)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
