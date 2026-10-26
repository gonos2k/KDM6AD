from __future__ import annotations

import importlib.util
from dataclasses import replace
import json
from pathlib import Path

import pytest

from harness.analyze_upstream_nc_trace import read_upstream_nc_trace
from harness.native_moment_trace_records import read_moment_trace_v2


PACKET = Path(__file__).parents[1] / "evidence/native_upstream_nc_2026-10-26"
SPEC = importlib.util.spec_from_file_location("upstream_nc_replay", PACKET / "replay.py")
REPLAY = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(REPLAY)


def test_saved_upstream_result_replays_byte_identically():
    result = REPLAY.replay_manifest(PACKET / "input_manifest.json")
    rendered = json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n"
    assert result["status"] == "UPSTREAM_NC_REPLAY_PASSED"
    assert rendered.encode() == (PACKET / "analysis.json").read_bytes()
    assert all(pair["full_checkpoint_raw_bitwise_equal"] and pair["ack_byte_identical"]
               for pair in result["execution_summary"]["pairs"])


def test_replay_rejects_a_modified_trace_before_analysis(tmp_path):
    manifest = json.loads((PACKET / "input_manifest.json").read_text())
    for case in manifest["runs"].values():
        for label in ("upstream_trace", "host_trace", "kernel_trace", "context"):
            relative = Path(case[label]["file"])
            target = tmp_path / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((PACKET / relative).read_bytes())
    item = manifest["execution_summary"]
    summary = tmp_path / item["file"]
    summary.parent.mkdir(parents=True, exist_ok=True)
    summary.write_bytes((PACKET / item["file"]).read_bytes())
    trace = tmp_path / manifest["runs"]["alpha025"]["upstream_trace"]["file"]
    raw = trace.read_bytes()
    trace.write_bytes(raw[:-1] + (b"X" if raw[-1:] != b"X" else b"Y"))
    path = tmp_path / "input_manifest.json"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="alpha025 upstream_trace SHA-256 differs"):
        REPLAY.replay_manifest(path)


def test_replay_requires_rk3_output_to_reach_microphysics_unchanged():
    source = PACKET / "data/control"
    upstream = read_upstream_nc_trace(source / "upstream_nc.tsv")
    kdm = read_moment_trace_v2(source / "host.hex", source / "kernel.hex")
    context = REPLAY._context((source / "context.npz").read_bytes(), "control_upstream_nc_v6_on")
    key = (3, 3, "RKSCALAR_AFTER", 221, 6, 63, "QNC")
    values = dict(upstream.values)
    values[key] = replace(values[key], bits=values[key].bits ^ 1)
    changed = replace(upstream, values=values)
    targets = json.loads((PACKET / "input_manifest.json").read_text())["targets"]
    with pytest.raises(ValueError, match="state boundary bits disagree"):
        REPLAY._context_links(changed, kdm, context, targets)


def test_replay_rejects_fractional_native_coordinate_before_asset_reads(tmp_path):
    manifest = json.loads((PACKET / "input_manifest.json").read_text())
    manifest["targets"][0]["i"] = 221.9
    path = tmp_path / "input_manifest.json"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="target target_221_63_6 i must be an integer"):
        REPLAY.replay_manifest(path)
