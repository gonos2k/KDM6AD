"""Authenticate and replay the saved east-edge cloud-gate interpretation."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys


PACKET = Path(__file__).resolve().parent
REPO = PACKET.parents[2]
PARENT = REPO / "harness/evidence/east_optical_witness_2026-10-31"
QNC = REPO / "harness/evidence/native_qnc_guard_control_direct_m0_2026-10-31"
PACKET_FILES = {
    "README.md",
    "analysis.json",
    "analyze.py",
    "replay.py",
    "test_replay.py",
}
UPSTREAM = {
    "harness/evidence/east_optical_witness_2026-10-31/source_manifest.json",
    "harness/evidence/east_optical_witness_2026-10-31/witness.json",
    "harness/evidence/east_optical_witness_2026-10-31/analysis.json",
    "harness/evidence/native_qnc_guard_control_direct_m0_2026-10-31/manifest.json",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_pins(root: Path, pins: dict[str, str], expected: set[str]) -> None:
    if not isinstance(pins, dict) or set(pins) != expected:
        raise ValueError("cloud-gate pin inventory differs")
    for relative, digest in pins.items():
        item = Path(relative)
        if item.is_absolute() or ".." in item.parts:
            raise ValueError("unsafe cloud-gate pin path")
        path = root / item
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("cloud-gate pin escapes root")
        if sha(path) != digest:
            raise ValueError(f"cloud-gate pinned file changed: {relative}")


def main() -> int:
    manifest = json.loads((PACKET / "manifest.json").read_text())
    if manifest.get("schema") != "east-optical-cloud-gate-manifest-v1":
        raise ValueError("cloud-gate manifest schema differs")
    check_pins(PACKET, manifest.get("packet_files_sha256"), PACKET_FILES)
    check_pins(REPO, manifest.get("upstream_sha256"), UPSTREAM)
    if manifest.get("model_calls_in_replay") != 0:
        raise ValueError("cloud-gate replay call count differs")

    prior = subprocess.run(
        [sys.executable, str(PARENT / "replay.py")],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    )
    parent_result = json.loads(prior.stdout.splitlines()[-1])
    if parent_result.get("profiles") != 10 or parent_result.get("model_calls") != 0:
        raise ValueError("parent optical replay differs")
    qnc = subprocess.run(
        [sys.executable, str(QNC / "packet_replay.py")],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    )
    qnc_result = json.loads(qnc.stdout.splitlines()[-1])
    if (
        qnc_result.get("status") != "OFFLINE_VERIFIED"
        or qnc_result.get("support_cells") != 377342
        or qnc_result.get("model_calls_in_verifier") != 0
    ):
        raise ValueError("QNC direct replay differs")

    produced = subprocess.run(
        [sys.executable, str(PACKET / "analyze.py")],
        cwd=REPO,
        check=True,
        capture_output=True,
    ).stdout
    if produced != (PACKET / "analysis.json").read_bytes():
        raise ValueError("cloud-gate analysis differs from published bytes")
    result = json.loads(produced)
    cloudy = result["strata"]["cloud_fraction_positive"]
    clear = result["strata"]["cloud_fraction_zero"]
    diameter = result["cloudy_diameter_changes"]
    if (
        result["native_levels_examined"] != 390
        or result["changed_moment_layers"] != 82
        or result["cloud_fraction_changed"] != 0
        or result["serialized_total_content_threshold_crossings"] != 0
        or (cloudy["ice_changed"], clear["ice_changed"]) != (42, 40)
        or (cloudy["diameter_changed"], clear["diameter_changed"]) != (1, 29)
        or (
            cloudy["diameter_bound_category_changed"],
            clear["diameter_bound_category_changed"],
        )
        != (0, 29)
        or (cloudy["ice_increase"], cloudy["ice_decrease"]) != (42, 0)
        or len(diameter) != 1
        or diameter[0]["native_ijk"] != [234, 52, 25]
        or diameter[0]["rttov_layer_1based"] != 42
        or diameter[0]["delta_um"] != diameter[0]["guard_float64_ulp_um"]
        or diameter[0]["same_float32"] is not True
        or result["bt_delta_K"]["negative"] != 70
        or result["bt_delta_K"]["positive"] != 0
        or result["huber"]["fixed_m0_denominator"] != 377342
        or not math.isclose(
            result["huber"]["fixed_m0_cost_delta"],
            parent_result["pilot_minus_qnc_contribution"],
            rel_tol=0,
            abs_tol=1e-18,
        )
    ):
        raise ValueError("cloud-gate reviewed values differ")
    print(
        json.dumps(
            {
                "status": "REPLAY_PASSED",
                "analysis_sha256": sha(PACKET / "analysis.json"),
                "cloudy_ice_changes": 42,
                "clear_diameter_bound_changes": 29,
                "fixed_m0_cost_delta": result["huber"]["fixed_m0_cost_delta"],
                "model_calls": 0,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
