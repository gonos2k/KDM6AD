from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import struct

import numpy as np
import pytest


REPLAY_PATH = Path(__file__).parents[1] / "evidence/native_qc_nc_trace_2026-10-26/replay.py"
SPEC = importlib.util.spec_from_file_location("native_qc_nc_trace_replay", REPLAY_PATH)
REPLAY = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(REPLAY)

TARGETS = [
    {"name": "T1", "i": 155, "j": 25},
    {"name": "T2", "i": 221, "j": 63},
    {"name": "T3", "i": 91, "j": 94},
]
HOST_STAGES = (
    "MP_INPUT", "MP_OUTPUT", "HOST_WRITEBACK", "WRAPPER_POST",
    "ZERO_OUT_PRE", "MOMENTS_PRE", "MOMENTS_POST",
)
KERNEL_STAGES = ("FP64_INPUT", "FP64_OUTPUT")
DT_HEX = "4034000000000000"
NCMIN_LAND_HEX = "4050000000000000"
NCMIN_SEA_HEX = "4030000000000000"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _f32hex(value: float) -> str:
    return f"{int(np.asarray([np.float32(value)], dtype=np.float32).view(np.uint32)[0]):08X}"


def _f64hex(value: float) -> str:
    return struct.pack(">d", float(value)).hex().upper()


def _write_context(path: Path, *, candidate=False) -> dict:
    ready_qc = np.zeros((3, 39), dtype=np.float32)
    ready_nc = np.ones((3, 39), dtype=np.float32)
    final_qc = ready_qc.copy()
    final_nc = ready_nc.copy()
    if candidate:
        final_qc[0, 18] = np.float32(0.1)
        final_nc[0, 18] = np.float32(0.0)
    with path.open("wb") as stream:
        np.savez_compressed(stream, ready_qc=ready_qc, ready_nc=ready_nc,
                            final_qc=final_qc, final_nc=final_nc)
    return {"file":path.name,"bytes":path.stat().st_size,"sha256":_sha(path.read_bytes())}


def _write_trace_pair(directory: Path, *, candidate=False) -> dict:
    call = f"CALL 1 3 1 234 1 39 1 282 234 39 282 {DT_HEX} {NCMIN_LAND_HEX} {NCMIN_SEA_HEX}"
    host = ["# KDM6AD_MOMENT_TRACE_V2", call]
    kernel = ["# KDM6AD_MOMENT_TRACE_V2", call]
    for owner, stages, dtype in (("host", HOST_STAGES, "f32"), ("kernel", KERNEL_STAGES, "f64")):
        rows = host if owner == "host" else kernel
        for stage in stages:
            for target in TARGETS:
                for k in range(1, 40):
                    for field, value in (("QC", 0.0), ("NC", 1.0)):
                        if candidate and target["name"] == "T1" and k == 19 and stage in ("MOMENTS_PRE", "MOMENTS_POST") and field == "QC":
                            value = 0.1
                        if candidate and target["name"] == "T1" and k == 19 and stage in ("MOMENTS_PRE", "MOMENTS_POST") and field == "NC":
                            value = 0.0
                        hexbits = _f32hex(value) if dtype == "f32" else _f64hex(value)
                        rows.append(f"VAL 1 {stage} {target['i']} {k} {target['j']} {dtype} {field} {hexbits}")
    host_path = directory / f"{'candidate' if candidate else 'control'}_host.hex"
    kernel_path = directory / f"{'candidate' if candidate else 'control'}_kernel.hex"
    host_path.write_text("\n".join(host) + "\n", encoding="ascii")
    kernel_path.write_text("\n".join(kernel) + "\n", encoding="ascii")
    return {
        "host": {"file":host_path.name,"bytes":host_path.stat().st_size,"sha256":_sha(host_path.read_bytes())},
        "kernel": {"file":kernel_path.name,"bytes":kernel_path.stat().st_size,"sha256":_sha(kernel_path.read_bytes())},
    }


def _manifest(tmp_path: Path, *, tamper_hash=False):
    runs = []
    for run_id, candidate in (("control_off", False), ("alpha_025", True)):
        context_path = tmp_path / f"{run_id}_context.npz"
        context_asset = _write_context(context_path, candidate=candidate)
        traces = _write_trace_pair(tmp_path, candidate=candidate)
        if tamper_hash and run_id == "control_off":
            traces["host"]["sha256"] = "0" * 64
        runs.append({"run_id":run_id,"traces":traces,"context_npz":context_asset,"expected_call_count":1})
    return {
        "schema":"kdm6.native_moment_trace_replay_inputs.v1",
        "levels":39,
        "global_shape_i_k_j":[234,39,282],
        "step":3,
        "dt_hex64":DT_HEX,
        "ncmin_land_hex64":NCMIN_LAND_HEX,
        "ncmin_sea_hex64":NCMIN_SEA_HEX,
        "levels_of_interest":[19,6,4],
        "targets":[dict(row) for row in TARGETS],
        "runs":runs,
        "comparisons":[{"control_run_id":"control_off","candidate_run_id":"alpha_025"}],
    }


def test_replay_manifest_validates_hashes_and_runs_strict_trace_analysis(tmp_path):
    manifest = _manifest(tmp_path)
    path = tmp_path / "input_manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    result = REPLAY.replay_manifest(path)

    assert result["status"] == "NATIVE_MOMENT_TRACE_REPLAY_PASSED"
    assert result["model_calls"] == {"host": 0, "KDM": 0, "RTTOV": 0, "optimizer": 0}
    assert result["runs"]["control_off"]["trace_completeness"]["complete"]
    t1 = result["comparisons"][0]["targets"]["T1"]["19"]
    assert t1["first_differing_boundary"]["boundary"] == "MOMENTS_PRE"
    assert t1["first_differing_boundary"]["field"] == "QC"


def test_replay_manifest_fails_on_trace_sha_mismatch(tmp_path):
    manifest = _manifest(tmp_path, tamper_hash=True)
    path = tmp_path / "input_manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="host trace SHA-256 differs"):
        REPLAY.replay_manifest(path)


def test_replay_context_npz_is_strictly_float32_and_shape_bound(tmp_path):
    manifest = _manifest(tmp_path)
    context = tmp_path / "control_off_context.npz"
    with context.open("wb") as stream:
        np.savez_compressed(
            stream,
            ready_qc=np.zeros((3, 38), dtype=np.float32),
            ready_nc=np.ones((3, 38), dtype=np.float32),
            final_qc=np.zeros((3, 38), dtype=np.float32),
            final_nc=np.ones((3, 38), dtype=np.float32),
        )
    manifest["runs"][0]["context_npz"] = {
        "file":context.name,"bytes":context.stat().st_size,"sha256":_sha(context.read_bytes())
    }
    path = tmp_path / "input_manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match=r"float32\[3,39\]"):
        REPLAY.replay_manifest(path)


@pytest.mark.parametrize("field,value,label", [
    ("levels", 39.9, "levels"),
    ("levels", True, "levels"),
    ("levels", "39", "levels"),
    ("step", 3.1, "step"),
    ("shape", 234.5, "global_shape_i_k_j"),
    ("target", 155.5, "target T1 i"),
    ("interest", 19.5, "levels_of_interest"),
    ("calls", 1.5, "expected_call_count"),
    ("bytes", 1.5, "byte count"),
])
def test_replay_rejects_fractional_integer_metadata(tmp_path, field, value, label):
    manifest = _manifest(tmp_path)
    if field in ("levels", "step"):
        manifest[field] = value
    elif field == "shape":
        manifest["global_shape_i_k_j"][0] = value
    elif field == "target":
        manifest["targets"][0]["i"] = value
    elif field == "interest":
        manifest["levels_of_interest"][0] = value
    elif field == "calls":
        manifest["runs"][0]["expected_call_count"] = value
    else:
        manifest["runs"][0]["traces"]["host"]["bytes"] = value
    path = tmp_path / "input_manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match=f"{label}.*integer"):
        REPLAY.replay_manifest(path)
