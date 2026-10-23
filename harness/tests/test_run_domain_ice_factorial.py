import hashlib
import json
from pathlib import Path
from io import BytesIO

import numpy as np
import pytest

from harness.ice_factorial_batch import IN_HEADER, OUT_HEADER
from harness.run_domain_ice_factorial import (
    EXPECTED_MANIFEST_SHA256,
    GuardError,
    build_plan,
    execute_one,
    execute_plan,
    _load_chunk_from_bytes,
    _parse_time_log,
)
import harness.run_domain_ice_factorial as guarded


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_chunk(path, start=0, b=512):
    state = np.zeros((12, b, 39), dtype=np.float64)
    forcing = np.ones((4, b, 39), dtype=np.float64)
    xland = np.resize(np.array([1.0, 2.0]), b)
    indices = np.arange(start, start + b, dtype=np.int32)
    np.savez(
        path,
        state=state,
        forcing=forcing,
        xland=xland,
        flat_indices=indices,
        i=indices % 234,
        j=indices // 234,
    )
    return sha(path.read_bytes())


def task_for(tmp_path, monkeypatch):
    monkeypatch.setattr(guarded, "EXPECTED_MANIFEST_SHA256", "a" * 64)
    source = tmp_path / "chunk.npz"
    source_sha = write_chunk(source)
    tool = tmp_path / "tool"
    tool.write_bytes(b"immutable fake tool")
    monkeypatch.setattr(guarded, "EXPECTED_TOOL_SHA256", sha(tool.read_bytes()))
    return {
        "index": 0,
        "start": 0,
        "end": 512,
        "B": 512,
        "L": 39,
        "source_path": str(source),
        "source_sha256": source_sha,
        "manifest_sha256": "a" * 64,
        "tool_path": str(tool),
        "tool_sha256": sha(tool.read_bytes()),
        "output_dir": str(tmp_path / "run"),
        "mode": "raw_cap",
        "dt_seconds": 20.0,
        "ncmin_land": 10.0,
        "ncmin_sea": 10.0,
    }


def fake_runner(tool, request, response, log, mode):
    raw = request.read_bytes()
    _, _, b, levels, *_ = IN_HEADER.unpack_from(raw)
    pos = IN_HEADER.size
    ns = 12 * b * levels * 8
    nf = 4 * b * levels * 8
    state = raw[pos : pos + ns]
    forcing = raw[pos + ns : pos + ns + nf]
    response.write_bytes(
        OUT_HEADER.pack(b"K6BATO1\0", 1, b, levels)
        + state
        + forcing
        + state
        + bytes(3 * b * 8)
    )
    log.write_text("fake executor completed\n")
    return {"wall": 0.01, "user": 0.005, "system": 0.003, "peak_rss_bytes": 4096}


def test_execute_one_persists_receipt_and_resume_checks_response_hash(
    tmp_path, monkeypatch
):
    task = task_for(tmp_path, monkeypatch)
    result = execute_one(task, runner=fake_runner)
    assert result["status"] == "complete"
    receipt_path = tmp_path / "run" / "chunk-00000.receipt.json"
    receipt = json.loads(receipt_path.read_text())
    assert receipt["tool_sha256_after"] == task["tool_sha256"]
    assert receipt["response_sha256"] == result["response_sha256"]
    skipped = execute_one(
        task, runner=lambda *args: pytest.fail("resume called runner"), resume=True
    )
    assert skipped["status"] == "skipped_completed"
    response_path = tmp_path / "run" / "chunk-00000.response.bin"
    response_path.write_bytes(response_path.read_bytes() + b"tampered")
    with pytest.raises(GuardError, match="response hash mismatch"):
        execute_one(
            task,
            runner=lambda *args: pytest.fail("invalid resume called runner"),
            resume=True,
        )


def test_execute_one_rejects_source_and_tool_hash_changes(tmp_path, monkeypatch):
    task = task_for(tmp_path, monkeypatch)
    Path(task["source_path"]).write_bytes(b"changed input")
    with pytest.raises(GuardError, match="input chunk SHA"):
        execute_one(task, runner=fake_runner)
    (tmp_path / "second").mkdir()
    task = task_for(tmp_path / "second", monkeypatch)
    Path(task["tool_path"]).write_bytes(b"replaced executable")
    with pytest.raises(GuardError, match="executable changed"):
        execute_one(task, runner=fake_runner)


def test_execute_one_detects_tool_change_during_subprocess(tmp_path, monkeypatch):
    task = task_for(tmp_path, monkeypatch)

    def mutating_runner(tool, request, response, log, mode):
        result = fake_runner(tool, request, response, log, mode)
        tool.write_bytes(b"changed while running")
        return result

    with pytest.raises(GuardError, match="changed during"):
        execute_one(task, runner=mutating_runner)


def test_plan_admits_only_exact_manifest_and_tool_hash(tmp_path):
    tool = tmp_path / "tool"
    tool.write_bytes(b"tool bytes")
    chunks = []
    for index, start in enumerate(range(0, 65_988, 512)):
        end = min(start + 512, 65_988)
        chunks.append(
            {
                "start_flat": start,
                "stop_flat_exclusive": end,
                "columns": end - start,
                "path": f"chunk-{index}.npz",
                "sha256": "b" * 64,
            }
        )
    manifest = {
        "schema": "kdm6.ice_factorial_endpoint_preparation.v2",
        "coverage": {
            "columns_expected": 65_988,
            "columns_written": 65_988,
            "missing": 0,
            "duplicate": 0,
        },
        "mapping": {
            "state_order": [
                "TH",
                "Q",
                "QC",
                "QR",
                "QI",
                "QS",
                "QG",
                "NN",
                "NC",
                "NI",
                "NR",
                "BG",
            ],
            "forcing_order": ["DEN", "PII", "P", "DELZ"],
        },
        "chunks": chunks,
    }
    path = tmp_path / "manifest.json"
    raw = (json.dumps(manifest) + "\n").encode()
    path.write_bytes(raw)
    plan = build_plan(
        path, tool, manifest_sha=sha(raw), tool_sha=sha(tool.read_bytes()), workers=10
    )
    assert plan["execution"] == "dry_run_only" and plan["calls"] == 0
    assert plan["chunk_count"] == 129 and plan["chunks"][-1]["B"] == 452
    with pytest.raises(GuardError, match="manifest SHA"):
        build_plan(
            path,
            tool,
            manifest_sha=EXPECTED_MANIFEST_SHA256,
            tool_sha=sha(tool.read_bytes()),
        )
    with pytest.raises(GuardError, match="tool SHA"):
        build_plan(path, tool, manifest_sha=sha(raw), tool_sha="0" * 64)


@pytest.mark.parametrize("workers", [0, 11, True, 2.5])
def test_plan_rejects_worker_limits_outside_one_to_ten(workers, tmp_path):
    with pytest.raises(GuardError, match="workers"):
        build_plan(
            tmp_path / "does-not-need-to-exist", tmp_path / "no-tool", workers=workers
        )


@pytest.mark.parametrize("workers", [0, 11, True, 1.5])
def test_execution_rejects_worker_limits_outside_one_to_ten(workers, tmp_path):
    with pytest.raises(GuardError, match="workers"):
        execute_plan(
            {},
            output_dir=tmp_path / "run",
            executable=tmp_path / "tool",
            workers=workers,
        )


def test_task_mode_and_receipt_gate_are_exact(tmp_path, monkeypatch):
    task = task_for(tmp_path, monkeypatch)
    task["mode"] = "legacy"
    with pytest.raises(GuardError, match="mode"):
        execute_one(task, runner=fake_runner)


def test_native_grid_boundary_uses_nx234_independent_of_runner_constants():
    # Independent C-order boundary witness from the declared 234 x 282 grid.
    flat = np.array([233, 234], dtype=np.int32)
    expected_i = np.array([233, 0], dtype=np.int32)
    expected_j = np.array([0, 1], dtype=np.int32)
    assert (flat % 234).tolist() == expected_i.tolist()
    assert (flat // 234).tolist() == expected_j.tolist()


def test_chunk_loader_rejects_transposed_282_wide_coordinate_mapping(tmp_path):
    state = np.zeros((12, 512, 39), dtype=np.float64)
    forcing = np.ones((4, 512, 39), dtype=np.float64)
    xland = np.ones(512, dtype=np.float64)
    flat = np.arange(512, dtype=np.int32)
    buffer = BytesIO()
    np.savez(
        buffer,
        state=state,
        forcing=forcing,
        xland=xland,
        flat_indices=flat,
        i=flat % 282,
        j=flat // 282,
    )
    with pytest.raises(GuardError, match="indices"):
        _load_chunk_from_bytes(
            buffer.getvalue(), {"start_flat": 0, "stop_flat_exclusive": 512}, 0
        )


def test_darwin_time_log_accepts_multiple_spaces_and_requires_all_resources():
    log = "0.27 real 0.12 user 0.08 sys\n211976192  maximum resident set size\n"
    assert _parse_time_log(log) == {
        "wall": 0.27,
        "user": 0.12,
        "system": 0.08,
        "peak_rss_bytes": 211976192,
    }
    with pytest.raises(GuardError, match="missing required peak_rss_bytes"):
        _parse_time_log("0.27 real 0.12 user 0.08 sys\n")
