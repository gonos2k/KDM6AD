"""Synthetic process/file tests for NativeLiveStepper ownership.

The child process below imitates only the step-control protocol and restart
container. It is not WRF and its outputs are not native-model evidence.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import json
from dataclasses import replace
import os
from pathlib import Path
import shutil
import struct
import sys
import textwrap
import time

import netCDF4 as nc
import numpy as np
import pytest

import harness.native_live_stepper as live
from harness.native_host_transition import NativeCheckpoint, NativeInputs, PinnedFile
from harness.native_live_stepper import (
    AdjustmentDecision,
    LiveState,
    NativeColdStart,
    NativeLiveStepper,
    checkpoint_geometry_id,
    run_state_carry_loop,
)
from harness.native_step_control import HeatingUpdate
from harness.native_step_control import StepReady
from harness.native_analysis_control import AnalysisUpdate, apply_pair
from harness.native_analysis_increment import NativeAnalysisIncrement


T0 = "2025-07-19_00:02:00"
T1 = "2025-07-19_00:02:20"
BOUNDS = (1, 2, 1, 2, 1, 2)


def _bits(value):
    return struct.unpack(">I", struct.pack(">f", float(value)))[0]


def _restart(path, *, stamp=T0, timestep=6, h_value=1.0, stepra=1,
             include_thm2=True):
    with nc.Dataset(path, "w") as ds:
        ds.createDimension("Time", 1)
        ds.createDimension("DateStrLen", 19)
        ds.createDimension("bottom_top", 2)
        ds.createDimension("south_north", 2)
        ds.createDimension("west_east", 2)
        ds.createDimension("bottom_top_stag", 3)
        ds.createVariable("Times", "S1", ("Time", "DateStrLen"))[:] = np.frombuffer(
            stamp.encode("ascii"), dtype="S1")[None, :]
        ds.createVariable("ITIMESTEP", "i4", ("Time",))[:] = [timestep]
        ds.createVariable("STEPRA", "i4", ("Time",))[:] = [stepra]
        ds.createVariable("H_DIABATIC", "f4", (
            "Time", "bottom_top", "south_north", "west_east"))[:] = np.full(
                (1, 2, 2, 2), h_value, dtype=np.float32)
        ds.createVariable("T", "f4", (
            "Time", "bottom_top", "south_north", "west_east"))[:] = np.full(
                (1, 2, 2, 2), 280.0, dtype=np.float32)
        if include_thm2:
            ds.createVariable("THM_2", "f4", (
                "Time", "bottom_top", "south_north", "west_east"))[:] = np.full(
                    (1, 2, 2, 2), 300.0, dtype=np.float32)
        ds.createVariable("QVAPOR", "f4", (
            "Time", "bottom_top", "south_north", "west_east"))[:] = np.full(
                (1, 2, 2, 2), 0.01, dtype=np.float32)
        lat = np.arange(4, dtype=np.float32).reshape(1, 2, 2) + 36.0
        lon = np.arange(4, dtype=np.float32).reshape(1, 2, 2) - 120.0
        ds.createVariable("XLAT", "f4", ("Time", "south_north", "west_east"))[:] = lat
        ds.createVariable("XLONG", "f4", ("Time", "south_north", "west_east"))[:] = lon
        ds.createVariable("ZNU", "f4", ("Time", "bottom_top"))[:] = [[0.75, 0.25]]
        ds.createVariable("ZNW", "f4", ("Time", "bottom_top_stag"))[:] = [[1.0, 0.5, 0.0]]
        for name in ("QV_DIABATIC", "QC_DIABATIC", "QNCCN"):
            ds.createVariable(name, "f4", ("Time",))[:] = [0.0]
        ds.createVariable("SYNTHETIC_MEMORY", "i8", ("Time",))[:] = [2**53 + 17]
        ds.setncattr("PHYSICS_CONTEXT", "synthetic test only")


def _cold_input(path, *, stamp=T0):
    with nc.Dataset(path, "w") as ds:
        ds.createDimension("Time", 1)
        ds.createDimension("DateStrLen", 19)
        ds.createDimension("bottom_top", 2)
        ds.createDimension("bottom_top_stag", 3)
        ds.createDimension("south_north", 2)
        ds.createDimension("west_east", 2)
        ds.createVariable("Times", "S1", ("Time", "DateStrLen"))[:] = np.frombuffer(
            stamp.encode("ascii"), dtype="S1")[None, :]
        dims = ("Time", "bottom_top", "south_north", "west_east")
        ds.createVariable("T", "f4", dims)[:] = np.full((1,2,2,2), 280.0, np.float32)
        ds.createVariable("THM", "f4", dims)[:] = np.full((1,2,2,2), 300.0, np.float32)
        ds.createVariable("QVAPOR", "f4", dims)[:] = np.full((1,2,2,2), .01, np.float32)
        lat = np.arange(4, dtype=np.float32).reshape(1, 2, 2) + 36.0
        lon = np.arange(4, dtype=np.float32).reshape(1, 2, 2) - 120.0
        ds.createVariable("XLAT", "f4", ("Time", "south_north", "west_east"))[:] = lat
        ds.createVariable("XLONG", "f4", ("Time", "south_north", "west_east"))[:] = lon
        ds.createVariable("ZNU", "f4", ("Time", "bottom_top"))[:] = [[.75, .25]]
        ds.createVariable("ZNW", "f4", ("Time", "bottom_top_stag"))[:] = [[1., .5, 0.]]
        ds.setncattr("PHYSICS_CONTEXT", "synthetic cold input only")


def _increment(checkpoint, *, theta=.25, qv=.001):
    dims = dict(checkpoint.schema[0])
    shape = (dims["west_east"], dims["bottom_top"], dims["south_north"])
    dt = np.zeros(shape, dtype=np.float64)
    dq = np.zeros(shape, dtype=np.float64)
    dt[0, 0, 0] = theta
    dq[0, 0, 0] = qv
    return NativeAnalysisIncrement(
        delta_theta_m=dt,
        delta_qv=dq,
        unchanged_mask=(dt == 0) & (dq == 0),
        model_valid_time=checkpoint.time,
        geometry_id=checkpoint_geometry_id(checkpoint),
        native_layout="i,k,j",
        background_checkpoint_id=checkpoint.file.sha256,
        posterior_checkpoint_id="synthetic-posterior",
    )


def _cold_stepper(tmp_path, make_stepper):
    template = make_stepper(control_family="ANALYSIS_TQ", steps=1)
    cold_path = tmp_path / "cold_wrfinput.nc"
    _cold_input(cold_path)
    cold = NativeColdStart.capture(cold_path, expected_time=T0)
    external = NativeInputs(
        template.external.namelist,
        (("wrfinput_d01", PinnedFile.bind(cold_path)),),
        template.external.environment,
    )
    stepper = NativeLiveStepper(
        initial=cold,
        external=external,
        executable=template.executable,
        library=template.library,
        runner=template.runner,
        work_root=tmp_path / "cold_live_work",
        steps=1,
        timeout_seconds=3,
        control_family="ANALYSIS_TQ",
    )
    return stepper, cold, template


def _fake_runner_source():
    return textwrap.dedent(r'''
        import json, os, shutil, sys, time
        from datetime import datetime, timedelta
        from pathlib import Path
        import numpy as np
        import netCDF4 as nc

        def arg(name):
            return sys.argv[sys.argv.index(name) + 1]
        case = Path(arg('--case'))
        seconds = int(arg('--seconds'))
        nsteps = seconds // 20
        mode = os.environ.get('FAKE_MODE', 'ok')
        family = os.environ.get('KDM6AD_STEP_CONTROL_FAMILY', 'H_RATE')
        cold = os.environ.get('KDM6AD_STEP_CONTROL_CAPTURE_INITIAL') == '1'
        root = Path(os.environ['KDM6AD_STEP_CONTROL_ROOT'])
        src = case / 'wrfinput_d01' if cold else next(case.glob('checkpoint_input_*'))
        with nc.Dataset(src) as ds:
            stamp = b''.join(ds['Times'][0].tolist()).decode('ascii')
            step = 0 if cold else int(ds['ITIMESTEP'][0])
        if cold:
            startup = case / ('wrfrst_d01_' + stamp)
            shutil.copy2(src, startup)
            with nc.Dataset(startup, 'r+') as ds:
                shape = ds['THM'].shape
                ds.createVariable('ITIMESTEP', 'i4', ('Time',))[:] = [0]
                ds.createVariable('STEPRA', 'i4', ('Time',))[:] = [1]
                ds.createVariable('H_DIABATIC', 'f4', ds['THM'].dimensions)[:] = np.zeros(shape, np.float32)
                ds.createVariable('THM_2', 'f4', ds['THM'].dimensions)[:] = ds['THM'][:]
                ds.createVariable('QV_DIABATIC', 'f4', ds['QVAPOR'].dimensions)[:] = np.zeros(shape, np.float32)
                ds.createVariable('QC_DIABATIC', 'f4', ds['QVAPOR'].dimensions)[:] = np.zeros(shape, np.float32)
                ds.createVariable('QNCCN', 'f4', ds['QVAPOR'].dimensions)[:] = np.ones(shape, np.float32)
                ds.createVariable('SYNTHETIC_MEMORY', 'i8', ('Time',))[:] = [2**53 + 17]
                ds.setncattr('PHYSICS_CONTEXT', 'synthetic cold startup only')
            src = startup
        if mode == 'exit_before_ready':
            raise SystemExit(7)

        def publish(path, data):
            temp = path.with_name('.' + path.name + '.tmp')
            temp.write_bytes(data)
            os.replace(temp, path)

        def bits(value):
            return int(np.asarray([value], np.float32).view(np.uint32)[0])

        def frombits(value):
            return np.asarray([value], np.uint32).view(np.float32)[0]

        current = src
        pid = os.getpid()
        for index in range(nsteps):
            current_stamp = stamp
            current_step = step
            ready_stamp = current_stamp
            if mode == 'stale_clock' and index == 0:
                ready_stamp = '2025-07-19_00:02:01'
            bounds = (1, 2, 1, 2, 1, 2)
            text = ('KDM6AD_READY_V1\n' + f'{current_step:010d} {1:010d}\n'
                    + ready_stamp + '\n'
                    + ' '.join(f'{x:010d}' for x in bounds) + '\n')
            publish(root / f'ready_{current_step:010d}.txt', text.encode('ascii'))
            command = root / f'command_{current_step:010d}.txt'
            deadline = time.monotonic() + 10
            while not command.exists() and time.monotonic() < deadline:
                time.sleep(.01)
            if not command.exists():
                raise SystemExit(8)
            rows = command.read_text('ascii').splitlines()
            request_step, count = map(int, rows[1].split())
            if request_step != current_step:
                raise SystemExit(10)
            if family == 'H_RATE':
                if rows[0] != 'KDM6AD_STEP_V1':
                    raise SystemExit(9)
                updates = []
                with nc.Dataset(current) as ds:
                    old_array = np.asarray(ds['H_DIABATIC'][:], dtype=np.float32)
                new_array = old_array.copy()
                for row in rows[2:]:
                    tag, si, sk, sj, shex = row.split()
                    if tag != 'H_DIABATIC':
                        raise SystemExit(11)
                    i, k, j = int(si), int(sk), int(sj)
                    delta_bits = int(shex, 16)
                    old = np.float32(old_array[0, k-1, j-1, i-1])
                    if mode == 'ack_old_mismatch' and index == 0:
                        ack_old = np.float32(old + np.float32(1.0))
                    else:
                        ack_old = old
                    delta = frombits(delta_bits)
                    with np.errstate(over='ignore'):
                        new = np.float32(old + delta)
                    updates.append((i, k, j, bits(ack_old), delta_bits,
                                    bits(np.float32(ack_old + delta))))
                    new_array[0, k-1, j-1, i-1] = new
                if len(updates) != count:
                    raise SystemExit(12)
                ack = ['KDM6AD_APPLIED_V1', f'{current_step:010d} {len(updates):010d}']
                for i, k, j, old, delta, new in updates:
                    ack.append(f'H_DIABATIC {i:010d} {k:010d} {j:010d} {old:08X} {delta:08X} {new:08X}')
            else:
                if rows[0] != 'KDM6AD_TQ_V1':
                    raise SystemExit(13)
                updates = []
                with nc.Dataset(current) as ds:
                    old_t = np.asarray(ds['THM_2'][:], dtype=np.float32)
                    old_q = np.asarray(ds['QVAPOR'][:], dtype=np.float32)
                new_t, new_q = old_t.copy(), old_q.copy()
                for row in rows[2:]:
                    tag, si, sk, sj, shex_t, shex_q = row.split()
                    if tag != 'THETA_M_QV':
                        raise SystemExit(14)
                    i, k, j = int(si), int(sk), int(sj)
                    dt_bits, dq_bits = int(shex_t, 16), int(shex_q, 16)
                    before_t = np.float32(old_t[0, k-1, j-1, i-1])
                    before_q = np.float32(old_q[0, k-1, j-1, i-1])
                    delta_t, delta_q = frombits(dt_bits), frombits(dq_bits)
                    after_t = before_t if delta_t == 0 else np.float32(before_t + delta_t)
                    after_q = before_q if delta_q == 0 else np.float32(before_q + delta_q)
                    updates.append((i, k, j, bits(before_t), bits(before_q), dt_bits, dq_bits,
                                    bits(after_t), bits(after_q)))
                    new_t[0, k-1, j-1, i-1] = after_t
                    new_q[0, k-1, j-1, i-1] = after_q
                if len(updates) != count:
                    raise SystemExit(15)
                ack = ['KDM6AD_TQ_APPLIED_V1', f'{current_step:010d} {len(updates):010d}']
                for i, k, j, old_t_b, old_q_b, dt_b, dq_b, new_t_b, new_q_b in updates:
                    ack.append(f'THETA_M_QV {i:010d} {k:010d} {j:010d} '
                               f'{old_t_b:08X} {old_q_b:08X} {dt_b:08X} {dq_b:08X} '
                               f'{new_t_b:08X} {new_q_b:08X}')
            publish(root / f'applied_{current_step:010d}.txt', ('\n'.join(ack) + '\n').encode('ascii'))
            event = case / 'fake_events.log'
            with event.open('a') as stream:
                stream.write(f'{pid} {current_step} {current_stamp}\n')

            next_time = (datetime.strptime(current_stamp, '%Y-%m-%d_%H:%M:%S')
                         + timedelta(seconds=20)).strftime('%Y-%m-%d_%H:%M:%S')
            output = case / ('wrfrst_d01_' + next_time)
            shutil.copy2(current, output)
            with nc.Dataset(output, 'r+') as ds:
                ds['Times'][:] = np.frombuffer(next_time.encode('ascii'), dtype='S1')[None, :]
                ds['ITIMESTEP'][:] = int(ds['ITIMESTEP'][0]) + 1
                # Fake host response after command consumption, for state-carry checks.
                if family == 'H_RATE':
                    ds['H_DIABATIC'][:] = new_array + np.float32(.125)
                else:
                    ds['THM_2'][:] = new_t + np.float32(.125)
                    ds['QVAPOR'][:] = new_q
                if mode == 'bad_schema' and index == 0:
                    ds.renameVariable('SYNTHETIC_MEMORY', 'RENAMED_MEMORY')
            current, stamp, step = output, next_time, current_step + 1

        archive = case / 'runs' / 'fake-native-run'
        archive.mkdir(parents=True)
        (archive / 'experiment_valid.json').write_text(json.dumps({
            'experiment_valid': True,
            'active_input_identity_complete': True,
            'model_completed': True,
            'actual_proc_grid': '1x1',
            'exit_code': 0,
        }))
    ''').lstrip()


@pytest.fixture
def make_stepper(tmp_path, monkeypatch):
    # Avoid platform-loader attestation in this synthetic child-process fixture.
    monkeypatch.setattr(live.sys, "platform", "linux")
    repo = Path(__file__).parents[2]
    monkeypatch.syspath_prepend(str(repo))

    def build(*, mode="ok", steps=2, h_value=1.0, timestep=6,
              stepra=1, radiation_every_step=True, control_family="H_RATE",
              include_thm2=True):
        state_path = tmp_path / f"input_{mode}_{steps}.nc"
        _restart(state_path, h_value=h_value, timestep=timestep, stepra=stepra,
                 include_thm2=include_thm2)
        initial = NativeCheckpoint.capture(state_path, expected_time=T0, expected_itimestep=timestep)
        exe = tmp_path / "fake-wrf.exe"
        library = tmp_path / "fake-libkdm6.so"
        runner = tmp_path / "synthetic_runner.py"
        namelist = tmp_path / "namelist.template"
        for path, content in ((exe, "fake exe marker"), (library, "fake library marker"),
                              (runner, _fake_runner_source())):
            path.write_text(content)
        namelist.write_text(
            "&time_control\n nocolons=.false.,\n/\n"
            "&domains\n max_dom=1,\n nproc_x=1,\n nproc_y=1,\n/\n"
            "&physics\n mp_physics=137,\n/\n"
            "&dynamics\n use_theta_m=1,\n/\n")
        pins = [PinnedFile.bind(path) for path in (exe, library, runner)]
        ext = NativeInputs(
            PinnedFile.bind(namelist), (),
            (("PATH", os.environ["PATH"]),
             ("PYTHONPATH", str(repo)),
             ("FAKE_MODE", mode)))
        return NativeLiveStepper(initial=initial, external=ext, executable=pins[0],
            library=pins[1], runner=pins[2], work_root=tmp_path / "work",
            steps=steps, radiation_every_step=radiation_every_step,
            control_family=control_family, timeout_seconds=3)
    return build


def test_live_state_is_identity_owned_sequential_and_final_state_cannot_advance(make_stepper):
    stepper = make_stepper(steps=2)
    with stepper:
        first = stepper.current
        forged_equal_state = LiveState(first.checkpoint, first.session, first.generation, first.ready)
        with pytest.raises(ValueError, match="current unconsumed state"):
            stepper.advance(forged_equal_state)

        second = stepper.advance(first, (HeatingUpdate(1, 1, 1, 0.25),))
        with pytest.raises(ValueError, match="current unconsumed state"):
            stepper.advance(first)
        third = stepper.advance(second, (HeatingUpdate(1, 1, 1, 0.5),))

        assert third.generation == 2
        assert third.ready is None
        with pytest.raises(ValueError, match="current unconsumed state"):
            stepper.advance(third)
        assert stepper._record["status"] == "complete"
        events = [line.split() for line in (stepper.case / "fake_events.log").read_text().splitlines()]
        assert len(events) == 2
        assert events[0][0] == events[1][0]  # one owned process carried both steps
        assert [int(event[1]) for event in events] == [6, 7]

    with pytest.raises(RuntimeError, match="cannot be entered twice"):
        stepper.__enter__()


@pytest.mark.parametrize("mode,phase,match", [
    ("stale_clock", "enter", "clock/physical domain"),
    ("exit_before_ready", "enter", "exited before"),
    ("ack_old_mismatch", "advance", "memory differs"),
    ("bad_schema", "advance", "schema differs"),
])
def test_invalid_boundary_or_ack_fails_and_closes_owned_process(make_stepper, mode, phase, match):
    stepper = make_stepper(mode=mode, steps=2)
    if phase == "enter":
        with pytest.raises((RuntimeError, ValueError), match=match):
            stepper.__enter__()
    else:
        with stepper:
            current = stepper.current
            if mode == "bad_schema":
                # Command succeeds, then next boundary's checkpoint has a changed schema.
                with pytest.raises(ValueError, match=match):
                    stepper.advance(current, (HeatingUpdate(1, 1, 1, 0.25),))
            else:
                with pytest.raises(RuntimeError, match=match):
                    stepper.advance(current, (HeatingUpdate(1, 1, 1, 0.25),))
    assert stepper._record["status"] == "failed"
    assert stepper.process is not None and stepper.process.poll() is not None
    assert stepper._closed


def test_unrepresentable_memory_departure_refuses_before_command_and_closes_session(make_stepper):
    stepper = make_stepper(mode="ok", steps=2, h_value=1.0)
    with stepper:
        state = stepper.current
        command = stepper.control_root / f"command_{state.ready.step:010d}.txt"
        with pytest.raises(ValueError, match="no finite representable memory departure"):
            stepper.advance(state, (HeatingUpdate(1, 1, 1, 1e-45),))
        assert not command.exists()
        assert stepper._record["status"] == "failed"
        assert stepper.process.poll() is not None


def test_live_stepper_refuses_uninitialized_timestep_before_creating_session(make_stepper):
    with pytest.raises(ValueError, match="completed noninitial timestep"):
        make_stepper(timestep=0)


def test_every_step_radiation_requires_stepra_one_but_legacy_template_mode_allows_other_cadence(
        make_stepper):
    with pytest.raises(ValueError, match="STEPRA=1 checkpoint seed"):
        make_stepper(stepra=15)

    # The opt-out preserves legacy prescribed-cadence use; it records that the
    # seed interval came from the template instead of claiming every-step RT.
    legacy = make_stepper(stepra=15, radiation_every_step=False)
    assert legacy._record["radiation_cadence"] == "prescribed_template"
    assert legacy._record["radt_minutes"] is None
    assert legacy.process is None


@pytest.mark.parametrize("asset_name", ["validation", "VALIDATION"])
def test_validation_asset_name_is_refused_before_case_creation_or_child_launch(
        tmp_path, make_stepper, monkeypatch, asset_name):
    template = make_stepper(steps=1)
    asset = tmp_path / "caller-validation-asset"
    asset.write_bytes(b"caller-owned validation asset\n")
    before = asset.read_bytes()
    external = NativeInputs(
        template.external.namelist,
        ((asset_name, PinnedFile.bind(asset)),),
        template.external.environment,
    )
    child_launches = []
    monkeypatch.setattr(live.subprocess, "Popen",
                        lambda *args, **kwargs: child_launches.append(args))
    work_root = tmp_path / "reserved-validation-work"

    with pytest.raises(ValueError, match="native assets need unique safe case basenames"):
        NativeLiveStepper(
            initial=template.initial,
            external=external,
            executable=template.executable,
            library=template.library,
            runner=template.runner,
            work_root=work_root,
            steps=1,
        )

    assert child_launches == []
    assert not work_root.exists()
    assert asset.read_bytes() == before


def test_numpy_float32_control_is_logged_as_json_without_changing_packet_bits(make_stepper):
    stepper = make_stepper(steps=1)
    proposal = np.float32(0.1)
    expected_bits = _bits(proposal)
    with stepper:
        after = stepper.advance(stepper.current, (HeatingUpdate(1, 1, 1, proposal),))
        assert after.generation == 1

    packet = (stepper.control_root / "command_0000000006.txt").read_text("ascii")
    assert packet.splitlines()[2].split()[-1] == f"{expected_bits:08X}"
    record = json.loads((stepper.case / "live_session.json").read_text())
    logged_update = record["controls"][0]["applied"][0]["update"]
    assert type(logged_update["delta"]) is float
    assert logged_update["delta"] == float(proposal)
    assert _bits(logged_update["delta"]) == expected_bits == 0x3DCCCCCD


def test_warm_analysis_increment_binds_to_current_thm2_and_qv_not_diagnostic_t(make_stepper):
    stepper = make_stepper(steps=1, control_family="ANALYSIS_TQ")
    initial = stepper.initial
    with nc.Dataset(initial.file.path) as ds:
        diagnostic_t = np.float32(ds["T"][0, 0, 0, 0])
        thm2 = np.float32(ds["THM_2"][0, 0, 0, 0])
        qv = np.float32(ds["QVAPOR"][0, 0, 0, 0])
    assert diagnostic_t == np.float32(280.0)
    assert thm2 == np.float32(300.0)
    assert diagnostic_t != thm2

    increment = _increment(initial)
    with stepper:
        after = stepper.advance(stepper.current, increment)
        assert after.generation == 1
        assert after.checkpoint.itimestep == initial.itimestep + 1
        with nc.Dataset(after.checkpoint.file.path) as ds:
            assert np.float32(ds["T"][0, 0, 0, 0]) == diagnostic_t
            assert np.float32(ds["THM_2"][0, 0, 0, 0]) == np.float32(300.375)
            assert np.float32(ds["QVAPOR"][0, 0, 0, 0]) == np.float32(qv + np.float32(.001))

    record = stepper._record["controls"][0]
    assert record["control_family"] == "ANALYSIS_TQ"
    assert record["analysis_binding"]["background_checkpoint_id"] == initial.file.sha256
    assert record["analysis_binding"]["geometry_id"] == increment.geometry_id
    applied = record["applied"][0]
    assert applied["old_t_bits"] == _bits(thm2)
    assert applied["old_t_bits"] != _bits(diagnostic_t)
    assert applied["old_q_bits"] == _bits(qv)


def test_effective_analysis_filters_float32_noop_and_reads_background_arrays_once(make_stepper):
    stepper = make_stepper(steps=1, control_family="ANALYSIS_TQ")
    increment = _increment(stepper.initial)
    delta_t = increment.delta_theta_m.copy()
    delta_q = increment.delta_qv.copy()
    delta_t[1, 0, 0] = 1.0e-8  # representable as f32, but rounds away at THM_2=300
    increment = replace(increment, delta_theta_m=delta_t, delta_qv=delta_q,
                        unchanged_mask=(delta_t == 0) & (delta_q == 0))

    with stepper:
        after = stepper.advance(stepper.current, increment)
        assert after.generation == 1
        command = (stepper.control_root / "command_0000000006.txt").read_text("ascii")
        assert command.splitlines()[0] == "KDM6AD_TQ_V1"
        assert command.splitlines()[1] == "0000000006 0000000001"

    binding = stepper._record["controls"][0]["analysis_binding"]
    assert binding["effective_counts"] == {
        "requested_points": 2,
        "noop_points": 1,
        "applied_points": 1,
        "empty_points": 6,
        "requested_nonzero_components": 3,
        "applied_components": 2,
        "zero_effect_components": 1,
    }
    assert binding["all_noop"] is False
    assert binding["background_variable_read_counts"] == {"THM_2": 1, "QVAPOR": 1}
    assert binding["per_point_netcdf_reads"] == 0
    assert len(stepper._record["controls"][0]["applied"]) == 1


def test_all_noop_and_empty_analysis_advance_with_zero_update_commands(make_stepper):
    stepper = make_stepper(steps=2, control_family="ANALYSIS_TQ")
    with stepper:
        noop = _increment(stepper.current.checkpoint, theta=1.0e-8, qv=0.0)
        first = stepper.advance(stepper.current, noop)
        second = stepper.advance(first, ())
        assert first.generation == 1 and second.generation == 2
        command0 = (stepper.control_root / "command_0000000006.txt").read_text("ascii")
        command1 = (stepper.control_root / "command_0000000007.txt").read_text("ascii")
        assert command0.splitlines()[1] == "0000000006 0000000000"
        assert command1.splitlines()[1] == "0000000007 0000000000"

    first_binding, second_binding = [
        record["analysis_binding"] for record in stepper._record["controls"]
    ]
    assert first_binding["all_noop"] is True
    assert first_binding["no_applied_update"] is True
    assert first_binding["effective_counts"]["requested_points"] == 1
    assert first_binding["effective_counts"]["noop_points"] == 1
    assert first_binding["effective_counts"]["applied_points"] == 0
    assert first_binding["background_variable_read_counts"] == {"THM_2": 1, "QVAPOR": 1}
    assert first_binding["per_point_netcdf_reads"] == 0
    assert second_binding["all_noop"] is True
    assert second_binding["effective_counts"]["requested_points"] == 0
    assert second_binding["effective_counts"]["empty_points"] == 8
    assert second_binding["source"] == "explicit empty update sequence"
    assert second_binding["background_variable_read_counts"] == {"THM_2": 0, "QVAPOR": 0}
    assert all(not record["applied"] for record in stepper._record["controls"])


@pytest.mark.parametrize("binding,match", [
    ("time", "time/geometry/background"),
    ("geometry", "time/geometry/background"),
    ("background", "time/geometry/background"),
    ("layout", "time/geometry/background"),
    ("shape", "full native i,k,j layout"),
])
def test_analysis_increment_requires_current_time_geometry_background_and_full_layout(
        make_stepper, binding, match):
    stepper = make_stepper(steps=1, control_family="ANALYSIS_TQ")
    state = stepper.initial
    increment = _increment(state)
    if binding == "time":
        increment = replace(increment, model_valid_time=T1)
    elif binding == "geometry":
        increment = replace(increment, geometry_id="other-grid")
    elif binding == "background":
        increment = replace(increment, background_checkpoint_id="other-checkpoint")
    elif binding == "layout":
        increment = replace(increment, native_layout="j,k,i")
    elif binding == "shape":
        wrong = np.zeros((2, 2), dtype=np.float64)
        increment = replace(increment, delta_theta_m=wrong, delta_qv=wrong.copy(),
                            unchanged_mask=np.ones_like(wrong, dtype=bool))

    stepper.current = LiveState(
        state, stepper.session, 0, StepReady(6, 1, T0, BOUNDS))
    stepper.process = object()  # No subprocess should be needed to reject a bad binding.
    with pytest.raises(ValueError, match=match):
        stepper.advance(stepper.current, increment)
    assert not (stepper.control_root / "command_0000000006.txt").exists()


def test_nonempty_tq_packet_requires_bound_native_analysis_increment(make_stepper):
    stepper = make_stepper(steps=1, control_family="ANALYSIS_TQ")
    state = stepper.initial
    stepper.current = LiveState(state, stepper.session, 0, StepReady(6, 1, T0, BOUNDS))
    stepper.process = object()
    with pytest.raises(ValueError, match="bound NativeAnalysisIncrement"):
        stepper.advance(stepper.current, (AnalysisUpdate(1, 1, 1, .25, .001),))
    assert not (stepper.control_root / "command_0000000006.txt").exists()


def test_cold_start_is_captured_then_tq_control_uses_initialized_thm2_and_qv(
        tmp_path, make_stepper):
    stepper, cold, _template = _cold_stepper(tmp_path, make_stepper)
    assert stepper.cold_start is True
    assert stepper.base is None
    assert stepper._record["origin_kind"] == "cold_input"
    with stepper:
        initialized = stepper.current.checkpoint
        assert initialized.itimestep == 0
        assert initialized.time == T0
        assert initialized.file.sha256 != cold.file.sha256
        with nc.Dataset(initialized.file.path) as ds:
            assert np.float32(ds["T"][0, 0, 0, 0]) == np.float32(280.0)
            assert np.float32(ds["THM_2"][0, 0, 0, 0]) == np.float32(300.0)
            assert np.float32(ds["QVAPOR"][0, 0, 0, 0]) == np.float32(.01)
        increment = _increment(initialized, theta=.125, qv=.0005)
        after = stepper.advance(stepper.current, increment)
        assert after.checkpoint.time == T1 and after.checkpoint.itimestep == 1
        assert stepper._record["status"] == "complete"
        assert stepper._record["controls"][0]["analysis_binding"][
            "background_checkpoint_id"] == initialized.file.sha256
        assert stepper._record["controls"][0]["applied"][0]["old_t_bits"] == _bits(300.0)


def test_cold_start_refuses_h_rate_family(tmp_path, make_stepper):
    template = make_stepper(control_family="ANALYSIS_TQ", steps=1)
    cold_path = tmp_path / "cold_h_forbidden.nc"
    _cold_input(cold_path)
    cold = NativeColdStart.capture(cold_path, expected_time=T0)
    external = NativeInputs(template.external.namelist,
        (("wrfinput_d01", PinnedFile.bind(cold_path)),), template.external.environment)
    with pytest.raises(ValueError, match="cold pilot supports analysis T/Q"):
        NativeLiveStepper(initial=cold, external=external,
            executable=template.executable, library=template.library, runner=template.runner,
            work_root=tmp_path / "forbidden_cold_h", steps=1, control_family="H_RATE")


def test_native_tq_binding_reads_prognostic_thm2_and_carries_updated_pair(make_stepper):
    stepper = make_stepper(steps=1, control_family="ANALYSIS_TQ")
    initial = stepper.initial
    with nc.Dataset(initial.file.path) as ds:
        t_diagnostic = np.float32(ds["T"][0, 0, 0, 0])
        thm2 = np.float32(ds["THM_2"][0, 0, 0, 0])
        qv = np.float32(ds["QVAPOR"][0, 0, 0, 0])
    assert t_diagnostic == np.float32(280.0)
    assert thm2 == np.float32(300.0)
    assert thm2 != t_diagnostic
    increment = _increment(initial)

    with stepper:
        after = stepper.advance(stepper.current, increment)
        assert after.generation == 1
        assert after.checkpoint.time == T1 and after.checkpoint.itimestep == 7
        with nc.Dataset(after.checkpoint.file.path) as ds:
            assert np.float32(ds["T"][0, 0, 0, 0]) == t_diagnostic
            assert np.float32(ds["THM_2"][0, 0, 0, 0]) == np.float32(300.375)
            assert np.float32(ds["QVAPOR"][0, 0, 0, 0]) == np.float32(qv + np.float32(.001))

    applied = stepper._record["controls"][0]["applied"][0]
    assert applied["old_t_bits"] == _bits(thm2)
    assert applied["old_t_bits"] != _bits(t_diagnostic)
    assert applied["old_q_bits"] == _bits(qv)
    binding = stepper._record["controls"][0]["analysis_binding"]
    assert binding["background_checkpoint_id"] == initial.file.sha256
    assert binding["geometry_id"] == increment.geometry_id


@pytest.mark.parametrize("bad_binding,match", [
    ("time", "time/geometry/background"),
    ("geometry", "time/geometry/background"),
    ("background", "time/geometry/background"),
    ("layout", "time/geometry/background"),
    ("shape", "full native i,k,j layout"),
])
def test_native_tq_refuses_stale_time_geometry_background_layout_or_shape(
        make_stepper, bad_binding, match):
    stepper = make_stepper(steps=1, control_family="ANALYSIS_TQ")
    increment = _increment(stepper.initial)
    if bad_binding == "time":
        increment = replace(increment, model_valid_time=T1)
    elif bad_binding == "geometry":
        increment = replace(increment, geometry_id="different-geometry")
    elif bad_binding == "background":
        increment = replace(increment, background_checkpoint_id="different-checkpoint")
    elif bad_binding == "layout":
        increment = replace(increment, native_layout="j,k,i")
    elif bad_binding == "shape":
        wrong = np.zeros((2, 2), dtype=np.float64)
        increment = replace(increment, delta_theta_m=wrong, delta_qv=wrong.copy(),
                            unchanged_mask=np.ones_like(wrong, dtype=bool))

    with stepper:
        current = stepper.current
        with pytest.raises(ValueError, match=match):
            stepper.advance(current, increment)
        assert not (stepper.control_root / f"command_{current.ready.step:010d}.txt").exists()
    assert stepper._closed
    assert stepper.process.poll() is not None


def test_tq_state_carry_loop_rebinds_each_increment_to_current_output(make_stepper):
    stepper = make_stepper(steps=2, control_family="ANALYSIS_TQ")
    proposals = []

    def propose(current):
        increment = _increment(current.checkpoint, theta=.125, qv=.0005)
        proposals.append((current.generation, current.checkpoint.file.sha256,
                          increment.background_checkpoint_id, increment))
        return increment

    def accept_admissible_transition(before, after, increment):
        return AdjustmentDecision(
            True,
            f"synthetic transition admissibility only; {before.generation}->{after.generation}; "
            f"background={increment.background_checkpoint_id}",
        )

    result = run_state_carry_loop(
        stepper, propose=propose, validate_adjustment=accept_admissible_transition)

    assert [(row[0], row[1], row[2]) for row in proposals] == [
        (0, stepper.initial.file.sha256, stepper.initial.file.sha256),
        (1, result.states[1].checkpoint.file.sha256, result.states[1].checkpoint.file.sha256),
    ]
    assert proposals[1][1] != stepper.initial.file.sha256
    assert result.states[2].checkpoint.file.sha256 != result.states[1].checkpoint.file.sha256
    assert stepper._record["control_family"] == "ANALYSIS_TQ"
    assert stepper._record["state_carry_status"] == "accepted"
    assert [decision.accepted for decision in result.decisions] == [True, True]
    assert [record["analysis_binding"]["background_checkpoint_id"]
            for record in stepper._record["controls"]] == [row[1] for row in proposals]
    assert [record["input_generation"] for record in stepper._record["adjustment_decisions"]] == [0, 1]


def test_analysis_tq_refuses_restart_without_thm2_even_if_diagnostic_t_exists(make_stepper):
    stepper = make_stepper(steps=1, control_family="ANALYSIS_TQ", include_thm2=False)
    state_path = stepper.initial.file.path
    increment = _increment(stepper.initial)
    with nc.Dataset(state_path) as ds:
        assert "T" in ds.variables and "THM_2" not in ds.variables

    with stepper:
        current = stepper.current
        with pytest.raises(ValueError, match="requires full native float32 THM_2/QVAPOR"):
            stepper.advance(current, increment)
        assert not (stepper.control_root / f"command_{current.ready.step:010d}.txt").exists()
    assert stepper._record["status"] == "failed"
    assert stepper._closed


def test_nonempty_tq_requires_bound_increment_not_raw_updates(make_stepper):
    stepper = make_stepper(steps=1, control_family="ANALYSIS_TQ")
    with stepper:
        current = stepper.current
        with pytest.raises(ValueError, match="bound NativeAnalysisIncrement"):
            stepper.advance(current, (AnalysisUpdate(1, 1, 1, .25, .001),))
        assert not (stepper.control_root / f"command_{current.ready.step:010d}.txt").exists()
    assert stepper._closed


def test_cold_tq_initializes_and_binds_increment_to_warm_startup_checkpoint(
        tmp_path, make_stepper):
    stepper, cold, _template = _cold_stepper(tmp_path, make_stepper)
    with stepper:
        startup_state = stepper.current.checkpoint
        assert stepper.cold_start
        assert startup_state.itimestep == 0
        assert startup_state.time == T0
        assert startup_state.file.sha256 != cold.file.sha256
        with nc.Dataset(startup_state.file.path) as ds:
            assert np.float32(ds["T"][0, 0, 0, 0]) == np.float32(280.0)
            assert np.float32(ds["THM_2"][0, 0, 0, 0]) == np.float32(300.0)
        increment = _increment(startup_state, theta=.125, qv=.0005)
        after = stepper.advance(stepper.current, increment)
        assert after.checkpoint.time == T1 and after.checkpoint.itimestep == 1
        control = stepper._record["controls"][0]
        assert control["analysis_binding"]["background_checkpoint_id"] == startup_state.file.sha256
        assert control["applied"][0]["old_t_bits"] == _bits(300.0)
        assert stepper._record["status"] == "complete"


def test_state_carry_proposes_from_each_updated_output_and_persists_explicit_acceptance(make_stepper):
    stepper = make_stepper(steps=2)
    proposed = []
    validated = []

    def read_h(state):
        with nc.Dataset(state.checkpoint.file.path) as ds:
            ds.set_auto_maskandscale(False)
            return np.float32(ds["H_DIABATIC"][0, 0, 0, 0])

    def propose(current):
        # Trial 2 must start from step 1's output, not the original checkpoint.
        proposed.append((current.generation, current.checkpoint.file.sha256, read_h(current)))
        return (HeatingUpdate(1, 1, 1, 0.25 if current.generation == 0 else 0.5),)

    def validate(before, after, controls):
        validated.append((before.generation, after.generation, read_h(before), read_h(after)))
        return AdjustmentDecision(True, f"synthetic gate accepted transition {before.generation}")

    result = run_state_carry_loop(stepper, propose=propose, validate_adjustment=validate)

    assert [row[0] for row in proposed] == [0, 1]
    assert proposed[0][1] == stepper.initial.file.sha256
    assert proposed[1][1] == result.states[1].checkpoint.file.sha256
    assert proposed[1][1] != stepper.initial.file.sha256
    assert proposed[1][2] == np.float32(1.375)
    assert [(before, after) for before, after, *_ in validated] == [(0, 1), (1, 2)]
    assert validated[1][2] == np.float32(1.375)
    assert len(result.states) == 3 and len(result.decisions) == 2
    assert result.states[0].checkpoint.file.sha256 == stepper.initial.file.sha256
    assert stepper._record["state_carry_status"] == "accepted"
    assert stepper._record["status"] == "complete"
    assert [row["accepted"] for row in stepper._record["adjustment_decisions"]] == [True, True]
    assert [row["input_generation"] for row in stepper._record["adjustment_decisions"]] == [0, 1]
    assert stepper._record["adjustment_decisions"] == json.loads(
        (stepper.case / "live_session.json").read_text())["adjustment_decisions"]


def test_final_native_completion_does_not_imply_rejected_state_adjustment_was_accepted(make_stepper):
    stepper = make_stepper(steps=1)

    with pytest.raises(RuntimeError, match="physical adjustment rejected"):
        run_state_carry_loop(
            stepper,
            propose=lambda current: (HeatingUpdate(1, 1, 1, 0.25),),
            validate_adjustment=lambda before, after, controls: AdjustmentDecision(
                False, "synthetic explicit rejection"),
        )

    # The native child completed successfully, yet the scientific state-carry
    # result records rejection and exposes no accepted analysis result.
    assert stepper._record["status"] == "complete"
    assert stepper._record["state_carry_status"] == "rejected_or_failed"
    assert stepper._record["adjustment_decisions"] == [{
        "input_generation": 0, "output_generation": 1,
        "accepted": False, "evidence": "synthetic explicit rejection"}]
    assert "accepted_state" not in stepper._record
    assert not (stepper.case / "accepted_state.json").exists()


@pytest.mark.parametrize("decision", [
    object(),
    AdjustmentDecision(True, "   "),
])
def test_invalid_or_evidence_free_adjustment_decision_fails_before_next_step(
        make_stepper, decision):
    stepper = make_stepper(steps=2)
    with pytest.raises(ValueError, match="explicit Boolean decision and evidence"):
        run_state_carry_loop(
            stepper,
            propose=lambda current: (HeatingUpdate(1, 1, 1, 0.25),),
            validate_adjustment=lambda before, after, controls: decision,
        )

    assert (stepper.control_root / "command_0000000006.txt").exists()
    assert not (stepper.control_root / "command_0000000007.txt").exists()
    assert stepper.process is not None and stepper.process.poll() is not None
    assert stepper._closed
    assert stepper._record["state_carry_status"] == "rejected_or_failed"
    assert stepper._record["status"] == "failed"
    assert stepper._record["adjustment_decisions"] == []


def test_proposal_exception_closes_process_before_another_command(make_stepper):
    stepper = make_stepper(steps=3)

    def propose(current):
        if current.generation == 1:
            raise RuntimeError("synthetic proposal failure")
        return (HeatingUpdate(1, 1, 1, 0.25),)

    with pytest.raises(RuntimeError, match="synthetic proposal failure"):
        run_state_carry_loop(
            stepper,
            propose=propose,
            validate_adjustment=lambda before, after, controls: AdjustmentDecision(
                True, "synthetic explicit acceptance"),
        )

    assert (stepper.control_root / "command_0000000006.txt").exists()
    assert not (stepper.control_root / "command_0000000007.txt").exists()
    assert stepper.process is not None and stepper.process.poll() is not None
    assert stepper._closed
    assert stepper._record["state_carry_status"] == "rejected_or_failed"
    assert stepper._record["status"] == "failed"
