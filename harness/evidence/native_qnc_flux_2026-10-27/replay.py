#!/usr/bin/env python3
"""Offline replay of the source-bound PR457 QNC flux packet.

This entry point validates the packet inventory and replays only saved V2 flux
and same-run upstream NC traces. It never launches the host, KDM, RTTOV or an
optimizer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

PACKET = Path(__file__).resolve().parent
REPO_ROOT = PACKET.parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from harness.analyze_upstream_nc_trace import read_upstream_nc_trace  # noqa: E402
from harness.replay_qnc_flux_limiter_trace import (  # noqa: E402
    analyze_qnc_flux_limiter_trace,
    read_qnc_flux_trace,
)

EXTERNAL_SOURCE_PINS = {
    "harness/replay_qnc_flux_limiter_trace.py": "b9dfde89f5d62eac6deb414a99d869c0297d05ded8f67c6914696c340d3170b7",
    "harness/analyze_upstream_nc_trace.py": "561148d6bb930f9f655a2deca56b6319260a9b4d55d1c71cdf73b03af6211f5a",
    "harness/native_qnc_flux_advect_overlay.py": "d3390212e9a37e208d6b25a9d4322ecaa7541a9c1fd47aa9fa4c3aa0cdf74027",
    "harness/native_qnc_flux_context_overlay.py": "09506bea263af4e5dea58f178f16e9a62018c05549a7f38eb4b2bb581f84d4ad",
}
RUNS = {
    "control": {
        "run_id": "control_pr457_v5_on",
        "flux": "data/control/qnc_flux.tsv",
        "upstream": "data/control/upstream_nc.tsv",
        "trace_rows": 77,
    },
    "alpha025": {
        "run_id": "alpha025_pr457_v6_on",
        "flux": "data/alpha025/qnc_flux.tsv",
        "upstream": "data/alpha025/upstream_nc.tsv",
        "trace_rows": 77,
    },
}
EXPECTED_RUN_CONFIG = {
    "scalar_adv_opt": 1,
    "rk_ord": 3,
    "h_sca_adv_order": 5,
    "v_sca_adv_order": 3,
    "zadvect_implicit": 0,
}
RUN_CONFIG_READBACK_FIELDS = {
    "SCALAR_ADV_OPT": "scalar_adv_opt",
    "RK_ORD": "rk_ord",
    "H_SCA_ADV_ORDER": "h_sca_adv_order",
    "V_SCA_ADV_ORDER": "v_sca_adv_order",
    "ZADVECT_IMPLICIT": "zadvect_implicit",
}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _parse_namelist_integer_list(value: str) -> list[int]:
    """Parse the scalar or repeat-count integer syntax used in namelist.output."""
    text = value.strip().replace(" ", "")
    if "*" in text:
        count_text, item_text = text.split("*", 1)
        count, item = int(count_text), int(item_text)
        if count <= 0:
            raise ValueError(f"invalid namelist repeat count: {value!r}")
        return [item] * count
    return [int(text)]


def _run_config_from_readback(runtime_flags: dict[str, Any], case: str) -> dict[str, int]:
    readback = runtime_flags.get("namelist_run_config_readback", {}).get(case)
    normalized = runtime_flags.get("normalized_run_config", {}).get(case)
    if not isinstance(readback, dict) or not isinstance(normalized, dict):
        raise ValueError(f"runtime flags omit namelist run-config readback for {case}")
    parsed: dict[str, int] = {}
    for nml_name, config_name in RUN_CONFIG_READBACK_FIELDS.items():
        if nml_name not in readback:
            raise ValueError(f"runtime flags omit {case} {nml_name}")
        items = _parse_namelist_integer_list(str(readback[nml_name]))
        if len(set(items)) != 1:
            raise ValueError(f"{case} {nml_name} entries are not uniform: {items}")
        parsed[config_name] = items[0]
    if parsed != EXPECTED_RUN_CONFIG or normalized != EXPECTED_RUN_CONFIG:
        raise ValueError(f"{case} namelist configuration disagrees with replay contract: {parsed}")
    return parsed


def _validate_packet_manifest() -> dict[str, Any]:
    manifest_path = PACKET / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema") != "kdm6.native_qnc_flux_public_packet.v1":
        raise ValueError("unexpected packet manifest schema")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("packet manifest has no file inventory")
    seen: set[str] = set()
    packet_root = PACKET.resolve()
    for row in files:
        rel = row.get("path")
        if not isinstance(rel, str) or rel.startswith("/") or ".." in Path(rel).parts:
            raise ValueError(f"unsafe manifest path: {rel!r}")
        if rel in seen:
            raise ValueError(f"duplicate manifest path: {rel}")
        seen.add(rel)
        path = PACKET / rel
        if path.is_symlink() or not path.resolve().is_relative_to(packet_root):
            raise ValueError(f"packet asset is a symlink or escapes packet root: {rel}")
        raw = path.read_bytes()
        if len(raw) != row.get("bytes") or _sha(raw) != row.get("sha256"):
            raise ValueError(f"packet asset does not match manifest: {rel}")
    recorded_sources = manifest.get("external_source_pins", {})
    for rel, expected in EXTERNAL_SOURCE_PINS.items():
        if recorded_sources.get(rel) != expected:
            raise ValueError(f"manifest source pin does not match replay code: {rel}")
        raw = (REPO_ROOT / rel).read_bytes()
        if _sha(raw) != expected:
            raise ValueError(f"external replay dependency changed: {rel}")
    for case, spec in RUNS.items():
        for key in ("flux", "upstream"):
            rel = spec[key]
            if rel not in seen:
                raise ValueError(f"manifest omits {case} {key} trace: {rel}")
        flux_lines = (PACKET / spec["flux"]).read_text(encoding="ascii").splitlines()
        count = sum(line.startswith("VAL ") for line in flux_lines)
        if count != spec["trace_rows"]:
            raise ValueError(f"{case} trace has {count} VAL rows, expected {spec['trace_rows']}")
    return manifest


def replay() -> dict[str, Any]:
    _validate_packet_manifest()
    results: dict[str, Any] = {}
    runtime_flags = json.loads((PACKET / "receipts/runtime_flags.json").read_text())
    run_configs: dict[str, dict[str, int]] = {}
    for case, spec in RUNS.items():
        run_config = _run_config_from_readback(runtime_flags, case)
        run_configs[case] = run_config
        flux = read_qnc_flux_trace(PACKET / spec["flux"])
        upstream = read_upstream_nc_trace(PACKET / spec["upstream"])
        results[case] = analyze_qnc_flux_limiter_trace(
            flux,
            upstream_trace=upstream,
            run_id=spec["run_id"],
            upstream_run_id=spec["run_id"],
            run_config=run_config,
        )
    return {
        "schema": "kdm6.native_qnc_flux_offline_replay.v1",
        "scope": "Saved V2 flux and same-run upstream NC arithmetic only; no new model execution or physical closure claim.",
        "model_calls": {"host": 0, "KDM6": 0, "RTTOV": 0, "optimizer": 0},
        "run_config_by_case": run_configs,
        "cases": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None, help="write to a new path inside this packet; never overwrites")
    args = parser.parse_args()
    result = replay()
    payload = (json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode()
    if args.out is None:
        target = PACKET / "analysis.json"
        existing = target.read_bytes()
        if existing != payload:
            raise ValueError("offline replay differs from pinned analysis.json")
        print(json.dumps({"status": "REPLAY_PASSED", "analysis_sha256": _sha(payload), "bytes": len(payload), "model_calls": result["model_calls"]}, sort_keys=True))
        return 0
    target = args.out if args.out.is_absolute() else PACKET / args.out
    packet_root = PACKET.resolve()
    if target.is_symlink() or not target.resolve(strict=False).is_relative_to(packet_root):
        raise ValueError("--out must be a new path inside this packet and must not be a symlink")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(payload)
    print(json.dumps({"status": "ANALYSIS_WRITTEN_NEW", "output": target.relative_to(PACKET).as_posix(), "bytes": len(payload), "sha256": _sha(payload), "model_calls": result["model_calls"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
