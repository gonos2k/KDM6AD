"""Compare the hardened QNC reader with the immutable PR457 saved analysis.

The PR457 packet pins its original reader and deliberately rejects a changed
source. This companion verifies the unchanged packet files, then compares the
current reader's two results with that saved analysis. It makes no model calls.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from harness.analyze_upstream_nc_trace import read_upstream_nc_trace
from harness.replay_qnc_flux_limiter_trace import analyze_qnc_flux_limiter_trace, read_qnc_flux_trace


PACKET = Path(__file__).resolve().parent / "evidence/native_qnc_flux_2026-10-27"
PR457_MANIFEST_SHA256 = "bc6a31a3c5e454a652b01ae9c261fb846817949408bda5063685b0275d2477f9"
PR457_READER_SHA256 = "b9dfde89f5d62eac6deb414a99d869c0297d05ded8f67c6914696c340d3170b7"
RUN_IDS = {"control": "control_pr457_v5_on", "alpha025": "alpha025_pr457_v6_on"}


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def replay() -> dict[str, object]:
    manifest_bytes = (PACKET / "manifest.json").read_bytes()
    if _sha(manifest_bytes) != PR457_MANIFEST_SHA256:
        raise ValueError("PR457 packet manifest changed")
    manifest = json.loads(manifest_bytes)
    if manifest["external_source_pins"]["harness/replay_qnc_flux_limiter_trace.py"] != PR457_READER_SHA256:
        raise ValueError("PR457 historical reader pin changed")
    for item in manifest["files"]:
        path = PACKET / item["path"]
        if path.is_symlink() or not path.resolve().is_relative_to(PACKET.resolve()):
            raise ValueError(f"unsafe PR457 packet path: {item['path']}")
        raw = path.read_bytes()
        if len(raw) != item["bytes"] or _sha(raw) != item["sha256"]:
            raise ValueError(f"PR457 packet asset changed: {item['path']}")
    saved = json.loads((PACKET / "analysis.json").read_text())
    flags = json.loads((PACKET / "receipts/runtime_flags.json").read_text())
    for case, run_id in RUN_IDS.items():
        data = PACKET / "data" / case
        result = analyze_qnc_flux_limiter_trace(
            read_qnc_flux_trace(data / "qnc_flux.tsv"),
            upstream_trace=read_upstream_nc_trace(data / "upstream_nc.tsv"),
            run_id=run_id,
            upstream_run_id=run_id,
            run_config=flags["normalized_run_config"][case],
        )
        if result != saved["cases"][case]:
            raise ValueError(f"hardened reader changed the saved {case} analysis")
    return {
        "status": "HARDENED_REPLAY_PASSED",
        "packet_manifest_sha256": PR457_MANIFEST_SHA256,
        "historical_reader_sha256": PR457_READER_SHA256,
        "cases": list(RUN_IDS),
        "model_calls": {"host": 0, "KDM6": 0, "RTTOV": 0, "optimizer": 0},
    }


def main() -> int:
    print(json.dumps(replay(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
