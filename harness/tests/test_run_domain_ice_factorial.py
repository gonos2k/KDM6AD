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


def cli_files(tmp_path, monkeypatch):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    paths = {
        role: inputs / name
        for role, name in (
            ("manifest", "manifest.json"),
            ("executable", "tool"),
            ("chunk", "chunk.npz"),
        )
    }
    for role, path in paths.items():
        path.write_bytes((role + " sentinel").encode())
    plan = {
        "manifest_path": str(paths["manifest"]),
        "tool_path": str(paths["executable"]),
        "chunks": [{"source_path": str(paths["chunk"])}],
        "calls": 0,
    }
    calls = []

    def fake_build(*args, **kwargs):
        calls.append("build")
        return plan

    def fake_execute(*args, **kwargs):
        calls.append("execute")
        return {"calls": 129, "test_double": True}

    monkeypatch.setattr(guarded, "build_plan", fake_build)
    monkeypatch.setattr(guarded, "execute_plan", fake_execute)
    args = [
        "--manifest",
        str(paths["manifest"]),
        "--executable",
        str(paths["executable"]),
    ]
    return paths, args, plan, calls


@pytest.mark.parametrize("execute", [False, True])
@pytest.mark.parametrize(
    "role", ["manifest", "executable", "chunk", "existing_artifact"]
)
def test_cli_existing_output_never_overwrites_inputs_or_artifacts(
    tmp_path, monkeypatch, execute, role
):
    paths, args, _, calls = cli_files(tmp_path, monkeypatch)
    paths["existing_artifact"] = tmp_path / "earlier.response.bin"
    paths["existing_artifact"].write_bytes(b"earlier result")
    before = {name: p.read_bytes() for name, p in paths.items()}
    if execute:
        args += ["--execute", "--output-dir", str(tmp_path / "new_run")]
    with pytest.raises(GuardError, match="already exists"):
        guarded.main(args + ["--plan-json", str(paths[role])])
    assert calls == []  # neither plan admission nor workers were started
    assert {name: p.read_bytes() for name, p in paths.items()} == before


@pytest.mark.parametrize("kind", ["hardlink", "symlink", "dangling_symlink"])
def test_cli_existing_output_alias_is_refused_before_execution(
    tmp_path, monkeypatch, kind
):
    paths, args, _, calls = cli_files(tmp_path, monkeypatch)
    alias = tmp_path / "alias.json"
    if kind == "hardlink":
        alias.hardlink_to(paths["manifest"])
    else:
        alias.symlink_to(
            paths["manifest"] if kind == "symlink" else tmp_path / "absent"
        )
    with pytest.raises(GuardError, match="already exists"):
        guarded.main(
            args
            + [
                "--execute",
                "--output-dir",
                str(tmp_path / "run"),
                "--plan-json",
                str(alias),
            ]
        )
    assert calls == []
    assert paths["manifest"].read_bytes() == b"manifest sentinel"
    if kind == "dangling_symlink":
        assert alias.is_symlink() and not alias.exists()
        assert not (tmp_path / "absent").exists()


@pytest.mark.parametrize(
    "alias", ["direct", "symlink_parent", "case_alias", "ancestor"]
)
def test_cli_future_output_collision_is_refused_before_any_worker(
    tmp_path, monkeypatch, alias
):
    _, args, _, calls = cli_files(tmp_path, monkeypatch)
    run = tmp_path / "run"
    report = run / "chunk-00000.receipt.json"
    if alias == "symlink_parent":
        link = tmp_path / "directory_alias"
        link.symlink_to(tmp_path, target_is_directory=True)
        report = link / "run" / "chunk-00000.request.bin"
    elif alias == "case_alias":
        report = tmp_path / "RUN" / "chunk-00000.response.bin"
    elif alias == "ancestor":
        report, run = tmp_path / "new_parent", tmp_path / "new_parent" / "run"
    with pytest.raises(GuardError, match="outside the execution output tree"):
        guarded.main(
            args + ["--execute", "--output-dir", str(run), "--plan-json", str(report)]
        )
    assert calls == [] and not run.exists() and not report.exists()


def test_cli_missing_chunk_name_still_cannot_be_used_as_report(tmp_path, monkeypatch):
    paths, args, _, calls = cli_files(tmp_path, monkeypatch)
    paths["chunk"].unlink()
    with pytest.raises(GuardError, match="protected input"):
        guarded.main(args + ["--plan-json", str(paths["chunk"])])
    assert calls == ["build"] and not paths["chunk"].exists()


def test_cli_run_directory_cannot_contain_inputs_even_on_resume(tmp_path, monkeypatch):
    paths, args, _, calls = cli_files(tmp_path, monkeypatch)
    with pytest.raises(GuardError, match="overlaps a protected input"):
        guarded.main(
            args
            + ["--execute", "--resume", "--output-dir", str(paths["manifest"].parent)]
        )
    assert calls == ["build"]
    assert paths["executable"].read_bytes() == b"executable sentinel"


@pytest.mark.parametrize("execute", [False, True])
def test_cli_fresh_external_report_publishes_without_changing_inputs(
    tmp_path, monkeypatch, execute
):
    paths, args, plan, calls = cli_files(tmp_path, monkeypatch)
    before = {name: p.read_bytes() for name, p in paths.items()}
    report = tmp_path / "reports" / "plan.json"
    if execute:
        args += ["--execute", "--output-dir", str(tmp_path / "run")]
    assert guarded.main(args + ["--plan-json", str(report)]) == 0
    assert json.loads(report.read_text()) == (
        {"calls": 129, "test_double": True} if execute else plan
    )
    assert calls == (["build", "execute"] if execute else ["build"])
    assert {name: p.read_bytes() for name, p in paths.items()} == before


def test_cli_publication_race_preserves_new_owner_and_cleans_tempfile(
    tmp_path, monkeypatch
):
    _, args, _, calls = cli_files(tmp_path, monkeypatch)
    report = tmp_path / "report.json"
    real_link = guarded.os.link

    def racing_link(source, destination):
        assert Path(destination) == report
        report.write_bytes(b"new owner created after preflight")
        real_link(source, destination)

    monkeypatch.setattr(guarded.os, "link", racing_link)
    with pytest.raises(GuardError, match="output already exists"):
        guarded.main(
            args
            + [
                "--execute",
                "--output-dir",
                str(tmp_path / "run"),
                "--plan-json",
                str(report),
            ]
        )
    assert calls == ["build", "execute"]  # only a test double, never KDM
    assert report.read_bytes() == b"new owner created after preflight"
    assert not list(tmp_path.glob(".report.json.tmp.*"))


def test_cli_report_uses_canonical_parent_after_symlink_is_retargeted(
    tmp_path, monkeypatch
):
    _, args, _, calls = cli_files(tmp_path, monkeypatch)
    admitted_parent = tmp_path / "admitted_reports"
    admitted_parent.mkdir()
    unrelated_parent = tmp_path / "unrelated"
    unrelated_parent.mkdir()
    alias = tmp_path / "reports_alias"
    alias.symlink_to(admitted_parent, target_is_directory=True)

    def retargeting_executor(*args, **kwargs):
        calls.append("execute")
        alias.unlink()
        alias.symlink_to(unrelated_parent, target_is_directory=True)
        return {"test_double": True}

    monkeypatch.setattr(guarded, "execute_plan", retargeting_executor)
    assert (
        guarded.main(
            args
            + [
                "--execute",
                "--output-dir",
                str(tmp_path / "run"),
                "--plan-json",
                str(alias / "result.json"),
            ]
        )
        == 0
    )
    assert json.loads((admitted_parent / "result.json").read_text()) == {
        "test_double": True
    }
    assert not (unrelated_parent / "result.json").exists()


def test_cli_report_with_file_parent_is_refused_before_plan_or_execution(
    tmp_path, monkeypatch
):
    paths, args, _, calls = cli_files(tmp_path, monkeypatch)
    with pytest.raises(GuardError, match="parent is not a directory"):
        guarded.main(
            args
            + [
                "--execute",
                "--output-dir",
                str(tmp_path / "run"),
                "--plan-json",
                str(paths["manifest"] / "report.json"),
            ]
        )
    assert calls == []
    assert paths["manifest"].read_bytes() == b"manifest sentinel"


@pytest.mark.parametrize("role", ["report", "run_dir", "case_alias"])
def test_cli_missing_source_file_cannot_become_an_output_directory(
    tmp_path, monkeypatch, role
):
    paths, args, _, calls = cli_files(tmp_path, monkeypatch)
    paths["chunk"].unlink()
    reserved = paths["chunk"]
    if role == "case_alias":
        reserved = reserved.with_name(reserved.name.upper())
    if role == "run_dir":
        args += ["--execute", "--output-dir", str(reserved / "run")]
    else:
        args += ["--plan-json", str(reserved / "report.json")]
    with pytest.raises(GuardError, match="protected input"):
        guarded.main(args)
    assert calls == ["build"]
    assert not reserved.exists() and not paths["chunk"].exists()
