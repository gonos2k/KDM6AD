"""File/process boundary tests with a synthetic runner, never native evidence."""
import copy
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import numpy as np
import pytest

nc = pytest.importorskip("netCDF4", reason="native checkpoint boundary tests require netCDF4")

import harness.native_host_transition as native
from harness.native_host_transition import (
    NativeCheckpoint, NativeHostTransition, NativeInputs, PinnedFile,
)
from harness.native_replay_compare import compare_frames


T0 = "2025-07-19_00:02:00"
T1 = "2025-07-19_00:02:20"


def _restart(path, *, missing=None, numeric_times=False):
    with nc.Dataset(path, "w") as ds:
        ds.createDimension("Time", 1)
        ds.createDimension("DateStrLen", 19)
        ds.createDimension("CharLen", 20)
        ds.createDimension("west_east", 2)
        ds.createDimension("south_north", 2)
        ds.createDimension("bottom_top", 2)
        if numeric_times:
            ds.createVariable("Times", "i4", ("Time",))[:] = [0]
        else:
            ds.createVariable("Times", "S1", ("Time", "DateStrLen"))[:] = np.frombuffer(T0.encode(), dtype="S1")[None, :]
        ds.createVariable("ITIMESTEP", "i4", ("Time",))[:] = [6]
        ds.createVariable("DISCRETE_MEMORY", "i8", ("Time",))[:] = [2**53 + 17]
        ds.createVariable("CHAR_MEMORY", "S1", ("CharLen",))[:] = np.frombuffer(b"retained-discrete-xx", dtype="S1")
        for name in ("H_DIABATIC", "QV_DIABATIC", "QC_DIABATIC", "QNCCN"):
            if name != missing:
                ds.createVariable(name, "f4", ("Time",))[:] = [0.25]
        ds.setncattr("PHYSICS_CONTEXT", "retained metadata")


def _metadata_pair(tmp_path):
    reference_path = tmp_path / "metadata_reference.nc"
    candidate_path = tmp_path / "metadata_candidate.nc"
    _restart(reference_path)
    _restart(candidate_path)
    return reference_path, candidate_path


@pytest.fixture
def setup_native(tmp_path, monkeypatch):
    state_path = tmp_path / "restart.nc"
    _restart(state_path)
    state = NativeCheckpoint.capture(state_path, expected_time=T0, expected_itimestep=6)
    files = []
    for name in ("executable", "library", "runner", "table"):
        path = tmp_path / name
        path.write_text(name)
        files.append(PinnedFile.bind(path))
    namelist = tmp_path / "template.nml"
    namelist.write_text("&time_control\n nocolons=.false.,\n/\n&domains\n max_dom=1,\n/\n&physics\n mp_physics=137,\n/\n&dynamics\n use_theta_m=1,\n/\n")
    inputs = NativeInputs(PinnedFile.bind(namelist), (("table.dat", files[3]),),
                          (("PATH", os.environ["PATH"]),))
    model = NativeHostTransition(reference=state, executable=files[0], library=files[1],
                                 runner=files[2], work_root=tmp_path / "calls")
    monkeypatch.setattr(native, "_copy_checkpoint", shutil.copy2)
    return model, state, inputs


def _synthetic_runner(calls, *, valid=True, counter_increment=1, mismatch_prefix=False):
    def run(command, **kwargs):
        case = Path(command[command.index("--case") + 1])
        calls.append(case)
        source = next(case.glob("checkpoint_input_*"))
        minutes = int(command[command.index("--minutes") + 1])
        seconds = int(command[command.index("--seconds") + 1])
        duration = 60 * minutes + seconds
        if duration <= 0 or duration % 20 != 0:
            raise ValueError("synthetic runner only supports positive 20-second increments")
        with nc.Dataset(source) as ds:
            stamp = b"".join(ds["Times"][0].tolist()).decode()
        current = source
        for increment in range(1, duration // 20 + 1):
            end = (datetime.strptime(stamp, "%Y-%m-%d_%H:%M:%S") + timedelta(seconds=20)).strftime("%Y-%m-%d_%H:%M:%S")
            output = case / ("wrfrst_d01_" + end)
            shutil.copy2(current, output)
            with nc.Dataset(output, "r+") as ds:
                ds["Times"][:] = np.frombuffer(end.encode(), dtype="S1")[None, :]
                ds["ITIMESTEP"][:] = ds["ITIMESTEP"][:] + counter_increment
                ds["H_DIABATIC"][:] = ds["H_DIABATIC"][:] + np.float32(1)
                if mismatch_prefix and duration > 20 and increment == 1:
                    ds["H_DIABATIC"][:] = ds["H_DIABATIC"][:] + np.float32(0.5)
            stamp = end
            current = output
        archive = case / "runs/synthetic_runner"
        archive.mkdir(parents=True)
        (archive / "experiment_valid.json").write_text(json.dumps({
            "experiment_valid": valid, "active_input_identity_complete": True,
            "model_completed": True, "actual_proc_grid": "1x1", "exit_code": 0,
        }))
        return subprocess.CompletedProcess(command, 0)
    return run


def test_full_file_context_survives_and_fresh_trials_replay_from_same_origin(setup_native, monkeypatch):
    model, state, inputs = setup_native
    initial_hash = state.file.sha256
    calls = []
    monkeypatch.setattr(native, "_run_runner", _synthetic_runner(calls))
    first = model.forward(0, state, inputs, 20)
    second = model.forward(0, state, inputs, 20)
    assert first.time == second.time == T1
    assert first.itimestep == second.itimestep == 7
    assert first.replay is not None and second.replay is not None
    assert first.replay.origin.file.sha256 == state.file.sha256
    assert second.replay.origin.file.sha256 == state.file.sha256
    assert len(first.replay.frames) == len(second.replay.frames) == 1
    assert calls[0] != calls[1]
    assert state.file.sha256 == initial_hash
    state.file.verify()
    with nc.Dataset(first.file.path) as a, nc.Dataset(second.file.path) as b:
        a.set_auto_maskandscale(False)
        b.set_auto_maskandscale(False)
        assert compare_frames(a, b, 0, 0, T1)["passed"]
        assert int(a["DISCRETE_MEMORY"][0]) == 2**53 + 17
        assert a.getncattr("PHYSICS_CONTEXT") == "retained metadata"
    record = json.loads(first.receipt.read_text())
    assert record["status"] == "complete"
    assert record["input_checkpoint_sha256"] == initial_hash
    assert record["command"][record["command"].index("--seconds") + 1] == "20"
    assert record["command"][record["command"].index("--proc-grid") + 1] == "1x1"
    text = (calls[0] / "namelist.input").read_text()
    assert "override_restart_timers" in text and ".true." in text
    assert "write_hist_at_0h_rst" in text and "history_interval_s" in text


def test_origin_prefix_replay_uses_20_then_40_seconds_and_checks_every_prior_frame(setup_native, monkeypatch):
    model, state, inputs = setup_native
    calls = []
    monkeypatch.setattr(native, "_run_runner", _synthetic_runner(calls))

    at_140 = model.forward(0, state, inputs, 20)
    at_160 = model.forward(1, at_140, inputs, 20)

    assert at_140.time == "2025-07-19_00:02:20"
    assert at_140.itimestep == 7
    assert at_160.time == "2025-07-19_00:02:40"
    assert at_160.itimestep == 8
    assert len(calls) == 2
    assert calls[0] != calls[1]
    seconds = [
        case.joinpath("transition.json").read_text()
        for case in calls
    ]
    assert json.loads(seconds[0])["command"][json.loads(seconds[0])["command"].index("--seconds") + 1] == "20"
    assert json.loads(seconds[1])["command"][json.loads(seconds[1])["command"].index("--seconds") + 1] == "40"
    replayed_origin = next(calls[1].glob("checkpoint_input_*"))
    assert native.file_sha256(replayed_origin) == state.file.sha256
    record = json.loads((calls[1] / "transition.json").read_text())
    assert record["status"] == "complete"
    assert record["prefix_comparisons"] == [{
        "time": at_140.time,
        "passed": True,
        "report": str(calls[1] / "prefix_compare_0001.json"),
    }]


def test_intermediate_or_recaptured_mutation_without_origin_context_is_refused(setup_native, monkeypatch):
    model, state, inputs = setup_native
    calls = []
    monkeypatch.setattr(native, "_run_runner", _synthetic_runner(calls))
    at_140 = model.forward(0, state, inputs, 20)

    recaptured = NativeCheckpoint.capture(
        at_140.file.path, expected_time=at_140.time, expected_itimestep=at_140.itimestep
    )
    assert recaptured.replay is None
    with pytest.raises(ValueError, match="origin-bound replay context"):
        model.forward(1, recaptured, inputs, 20)

    changed_path = at_140.file.path.with_name("changed_intermediate.nc")
    shutil.copy2(at_140.file.path, changed_path)
    with nc.Dataset(changed_path, "r+") as ds:
        ds["H_DIABATIC"][:] = ds["H_DIABATIC"][:] + np.float32(0.5)
    changed = NativeCheckpoint.capture(
        changed_path, expected_time=at_140.time, expected_itimestep=at_140.itimestep
    )
    changed_with_old_context = copy.copy(at_140)
    object.__setattr__(changed_with_old_context, "file", changed.file)
    object.__setattr__(changed_with_old_context, "_validated_sha256", changed.file.sha256)
    with pytest.raises(ValueError, match="invalid origin-bound replay context"):
        model.forward(1, changed_with_old_context, inputs, 20)
    assert len(calls) == 1


def test_origin_prefix_mismatch_is_recorded_as_failed_and_not_returned(setup_native, monkeypatch):
    model, state, inputs = setup_native
    calls = []
    monkeypatch.setattr(native, "_run_runner", _synthetic_runner(calls, mismatch_prefix=True))
    at_140 = model.forward(0, state, inputs, 20)

    with pytest.raises(RuntimeError, match="prefix does not reproduce"):
        model.forward(1, at_140, inputs, 20)

    assert len(calls) == 2
    record = json.loads((calls[1] / "transition.json").read_text())
    assert record["status"] == "failed"
    assert record["prefix_comparisons"] == [{
        "time": at_140.time,
        "passed": False,
        "report": str(calls[1] / "prefix_compare_0001.json"),
    }]


def test_origin_context_rejects_changed_external_or_runtime_before_launch(setup_native, monkeypatch, tmp_path):
    model, state, inputs = setup_native
    calls = []
    monkeypatch.setattr(native, "_run_runner", _synthetic_runner(calls))
    at_140 = model.forward(0, state, inputs, 20)

    changed_asset = tmp_path / "changed_table.dat"
    changed_asset.write_text("changed external input")
    changed_inputs = NativeInputs(
        inputs.namelist,
        (("table.dat", PinnedFile.bind(changed_asset)),),
        inputs.environment,
    )
    with pytest.raises(ValueError, match="prescribed inputs/runtime changed"):
        model.forward(1, at_140, changed_inputs, 20)

    changed_executable = tmp_path / "changed_executable"
    changed_executable.write_text("changed runtime")
    changed_model = NativeHostTransition(
        reference=state, executable=PinnedFile.bind(changed_executable),
        library=model.library, runner=model.runner, work_root=model.work_root,
    )
    with pytest.raises(ValueError, match="prescribed inputs/runtime changed"):
        changed_model.forward(1, at_140, inputs, 20)
    assert len(calls) == 1


def test_wrong_step_or_forged_clock_descriptor_cannot_launch(setup_native, monkeypatch):
    model, state, inputs = setup_native
    calls = []
    monkeypatch.setattr(native, "_run_runner", _synthetic_runner(calls))
    with pytest.raises(ValueError, match="requested full-step"):
        model.forward(1, state, inputs, 20)
    forged = copy.copy(state)
    object.__setattr__(forged, "time", T1)
    object.__setattr__(forged, "itimestep", 7)
    with pytest.raises(ValueError, match="actual file context"):
        model.forward(1, forged, inputs, 20)
    assert calls == []


def test_changed_checkpoint_or_prescribed_input_is_not_a_snapshot(setup_native, monkeypatch):
    model, state, inputs = setup_native
    calls = []
    monkeypatch.setattr(native, "_run_runner", _synthetic_runner(calls))
    inputs.assets[0][1].path.write_text("changed table")
    with pytest.raises(RuntimeError, match="pinned file changed"):
        model.forward(0, state, inputs, 20)
    assert not calls


@pytest.mark.parametrize("valid,counter", [(False, 1), (True, 2)])
def test_incomplete_execution_or_wrong_counter_never_returns_checkpoint(setup_native, monkeypatch, valid, counter):
    model, state, inputs = setup_native
    calls = []
    monkeypatch.setattr(native, "_run_runner", _synthetic_runner(calls, valid=valid, counter_increment=counter))
    with pytest.raises((RuntimeError, ValueError)):
        model.forward(0, state, inputs, 20)
    record = json.loads((calls[0] / "transition.json").read_text())
    assert record["status"] == "failed"


@pytest.mark.parametrize("kwargs", [{"numeric_times": True}, {"missing": "H_DIABATIC"}])
def test_checkpoint_capture_rejects_numeric_time_and_missing_memory(tmp_path, kwargs):
    path = tmp_path / "bad.nc"
    _restart(path, **kwargs)
    with pytest.raises(ValueError):
        NativeCheckpoint.capture(path, expected_time=T0, expected_itimestep=6)


def test_native_backend_cannot_be_used_as_full_host_derivative(setup_native):
    pytest.importorskip("torch")
    from oracle.kdm6.da_host_window import CoupledHostWindow, FrozenSupport
    model, state, inputs = setup_native
    with pytest.raises(RuntimeError, match="value_only"):
        model.vjp(0, state, inputs, 20, {})
    with pytest.raises(RuntimeError, match="value_only"):
        model.jvp(0, state, inputs, 20, {})
    window = CoupledHostWindow(model, [{}], dt=20, observe=lambda *a, **k: None,
                               supports={0: FrozenSupport(1, "synthetic")})
    with pytest.raises(RuntimeError, match="full-host derivatives required"):
        window.evaluate(state)


def test_header_only_trace_cannot_complete_native_transition(setup_native, monkeypatch):
    model, state, inputs = setup_native
    model.trace_column = (1, 1)
    calls = []
    execute = _synthetic_runner(calls)

    def header_only(command, **kwargs):
        result = execute(command, **kwargs)
        (calls[-1] / "native_trace.hex").write_text("# KDM6AD_NATIVE_TRACE_V1\n")
        return result

    monkeypatch.setattr(native, "_run_runner", header_only)
    with pytest.raises(ValueError, match="no records"):
        model.forward(0, state, inputs, 20)
    assert json.loads((calls[0] / "transition.json").read_text())["status"] == "failed"


def test_out_of_domain_trace_column_is_rejected_before_launch(setup_native):
    model, state, _ = setup_native
    with pytest.raises(ValueError, match="outside the native"):
        NativeHostTransition(reference=state, executable=model.executable, library=model.library,
                             runner=model.runner, work_root=model.work_root, trace_column=(3, 1))


@pytest.mark.parametrize("bad", [np.float32(np.nan), np.float32(-999)])
def test_direct_checkpoint_constructor_cannot_bypass_value_validation(setup_native, tmp_path, bad):
    model, state, _ = setup_native
    path = tmp_path / "invalid_values.nc"
    shutil.copy2(state.file.path, path)
    with nc.Dataset(path, "r+") as ds:
        ds["H_DIABATIC"].setncattr("missing_value", np.float32(-999))
        ds["H_DIABATIC"][:] = [bad]
    direct = NativeCheckpoint(PinnedFile.bind(path), T0, 6, state.schema)
    with pytest.raises(ValueError, match="NativeCheckpoint.capture"):
        model.snapshot(direct)
    with pytest.raises(ValueError, match="nonfinite|declared missing"):
        NativeCheckpoint.capture(path, expected_time=T0, expected_itimestep=6)


@pytest.mark.skipif(os.name != "posix", reason="POSIX runner process-group contract")
def test_runner_timeout_terminates_its_descendant(tmp_path):
    log_path = tmp_path / "timeout.log"
    code = (
        "import subprocess,sys,time; "
        "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
        "print(p.pid,flush=True); time.sleep(60)"
    )
    with log_path.open("w") as log, pytest.raises(subprocess.TimeoutExpired):
        native._run_runner([sys.executable, "-c", code], env=os.environ.copy(),
                           stdout=log, timeout=1)
    child_pid = int(log_path.read_text().strip())
    deadline = time.monotonic() + 2
    while True:
        result = subprocess.run(["ps", "-o", "stat=", "-p", str(child_pid)],
                                capture_output=True, text=True)
        state = result.stdout.strip()
        if not state or state.startswith("Z"):
            break  # Exited (possibly awaiting reaping), never still integrating.
        assert time.monotonic() < deadline, f"runner descendant survived timeout: {state}"
        time.sleep(0.05)


def test_runner_group_eperm_is_ignored_only_when_ps_shows_absent_or_zombie_group(monkeypatch):
    def ps(stdout, returncode=0):
        return subprocess.CompletedProcess(["ps"], returncode, stdout=stdout, stderr="")

    monkeypatch.setattr(native.subprocess, "run", lambda *args, **kwargs: ps(" 10 S\n 11 Ss\n"))
    assert native._runner_group_quiescent(42)

    monkeypatch.setattr(native.subprocess, "run", lambda *args, **kwargs: ps(" 42 Z\n 42 Z+\n"))
    assert native._runner_group_quiescent(42)

    permission = PermissionError(1, "group signal denied")

    def denied(_pgid, _signal):
        raise permission

    monkeypatch.setattr(native.os, "killpg", denied)
    assert native._signal_runner_group(42, 15) is False

    monkeypatch.setattr(native.subprocess, "run", lambda *args, **kwargs: ps(" 42 S\n"))
    with pytest.raises(PermissionError) as raised:
        native._signal_runner_group(42, 15)
    assert raised.value is permission


@pytest.mark.parametrize("ps_result", [
    subprocess.CompletedProcess(["ps"], 1, stdout="", stderr="ps failed"),
    OSError("ps unavailable"),
    subprocess.TimeoutExpired(["ps"], 2),
])
def test_runner_group_permission_error_propagates_when_ps_is_not_trustworthy(
        monkeypatch, ps_result):
    permission = PermissionError(1, "group signal denied")

    def denied(_pgid, _signal):
        raise permission

    def failed_ps(*args, **kwargs):
        if isinstance(ps_result, BaseException):
            raise ps_result
        return ps_result

    monkeypatch.setattr(native.os, "killpg", denied)
    monkeypatch.setattr(native.subprocess, "run", failed_ps)
    with pytest.raises(PermissionError) as raised:
        native._signal_runner_group(42, 15)
    assert raised.value is permission


def test_stop_runner_group_uses_quiescence_fallback_for_term_probe_and_kill(monkeypatch):
    class Child:
        pid = 42

        def __init__(self):
            self.wait_calls = []

        def wait(self, timeout=None):
            self.wait_calls.append(timeout)
            return -15

    child = Child()
    signals = []
    ps_calls = []

    def denied(_pgid, sig):
        signals.append(sig)
        raise PermissionError(1, "group signal denied")

    def zombie_group(*args, **kwargs):
        ps_calls.append(args[0])
        return subprocess.CompletedProcess(["ps"], 0, stdout=" 42 Z\n", stderr="")

    monkeypatch.setattr(native.os, "killpg", denied)
    monkeypatch.setattr(native.subprocess, "run", zombie_group)

    native._stop_runner_group(child)

    assert signals == [native.signal.SIGTERM, 0, native.signal.SIGKILL]
    assert len(ps_calls) == 3
    assert child.wait_calls == [5, 5]


def test_stop_runner_group_does_not_hide_eperm_for_live_group(monkeypatch):
    class Child:
        pid = 42
        waited = False

        def wait(self, timeout=None):
            self.waited = True
            return -15

    child = Child()
    permission = PermissionError(1, "group signal denied")

    def denied(_pgid, _signal):
        raise permission

    monkeypatch.setattr(native.os, "killpg", denied)
    monkeypatch.setattr(native.subprocess, "run", lambda *args, **kwargs:
                        subprocess.CompletedProcess(["ps"], 0, stdout=" 42 S\n", stderr=""))
    with pytest.raises(PermissionError) as raised:
        native._stop_runner_group(child)
    assert raised.value is permission
    assert not child.waited


def test_restart_metadata_rejects_changed_global_physics_context(tmp_path):
    reference_path, candidate_path = _metadata_pair(tmp_path)
    with nc.Dataset(reference_path, "r") as reference, nc.Dataset(candidate_path, "r+") as candidate:
        candidate.setncattr("PHYSICS_CONTEXT", "changed physics context")
        result = native.compare_restart_metadata(reference, candidate)

    assert not result["passed"]
    assert any(item.get("scope") == "global" and item.get("attribute") == "PHYSICS_CONTEXT"
               for item in result["differences"])
    assert result["output_ringing_normalizations"] == []


def test_restart_metadata_rejects_changed_variable_units(tmp_path):
    reference_path, candidate_path = _metadata_pair(tmp_path)
    with nc.Dataset(reference_path, "r+") as reference, nc.Dataset(candidate_path, "r+") as candidate:
        reference["H_DIABATIC"].setncattr("units", "K s-1")
        candidate["H_DIABATIC"].setncattr("units", "K")
        result = native.compare_restart_metadata(reference, candidate)

    assert not result["passed"]
    assert any(item.get("scope") == "H_DIABATIC" and item.get("attribute") == "units"
               for item in result["differences"])


def test_restart_metadata_normalizes_only_boolean_output_ring_values_with_same_dtype(tmp_path):
    reference_path, candidate_path = _metadata_pair(tmp_path)
    ring_attrs = ("WRF_ALARM_ISRINGING_01", "WRF_ALARM_ISRINGING_07")
    with nc.Dataset(reference_path, "r+") as reference, nc.Dataset(candidate_path, "r+") as candidate:
        for name in ring_attrs:
            reference.setncattr(name, np.int32(0))
            candidate.setncattr(name, np.int32(1))
        result = native.compare_restart_metadata(reference, candidate)

    assert result["passed"]
    assert result["differences"] == []
    assert {(item["attribute"], item["reference"], item["candidate"])
            for item in result["output_ringing_normalizations"]} == {
                (name, 0, 1) for name in ring_attrs
            }


@pytest.mark.parametrize(
    "reference_value,candidate_value",
    [(np.int32(0), np.int32(2)), (np.int32(0), np.int64(1))],
    ids=["nonboolean-value", "integer-width-mismatch"],
)
def test_restart_metadata_refuses_malformed_or_width_mismatched_ring_flags(
        tmp_path, reference_value, candidate_value):
    reference_path, candidate_path = _metadata_pair(tmp_path)
    name = "WRF_ALARM_ISRINGING_01"
    with nc.Dataset(reference_path, "r+") as reference, nc.Dataset(candidate_path, "r+") as candidate:
        reference.setncattr(name, reference_value)
        candidate.setncattr(name, candidate_value)
        result = native.compare_restart_metadata(reference, candidate)

    assert not result["passed"]
    assert result["output_ringing_normalizations"] == []
    assert any(item.get("scope") == "global" and item.get("attribute") == name
               for item in result["differences"])
