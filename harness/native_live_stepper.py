"""Owned, sequential, value-only native MP137 stepping without host restart.

A LiveState is a one-use view of an owned running process. It is not a
copyable/Markov-complete checkpoint, a HostTransition AD backend, or a physical
balance certificate. Model time advances by dt; analysis-time/observation policy
belongs to the caller. Intermediate heating-rate controls are consumed through
the host RK/dynamics, not reapplied as an external temperature increment.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid
from typing import Sequence

import numpy as np

from harness.native_host_transition import (
    NativeCheckpoint, NativeHostTransition, NativeInputs, PinnedFile,
    _copy_checkpoint, _stop_runner_group, file_sha256, native_step_namelist,
)
from harness.native_step_control import (
    HeatingUpdate, StepReady, _f32_bits,
    atomic_write_command, encode_command, read_applied, read_ready,
)
from harness.native_analysis_control import (
    apply_pair, encode_analysis_command, prepare_effective_analysis,
    read_analysis_applied,
)
from harness.native_analysis_increment import NativeAnalysisIncrement
from harness.run_ss_case import set_or_insert

_STAMP = '%Y-%m-%d_%H:%M:%S'


@dataclass(frozen=True)
class NativeColdStart:
    """A pinned cold input, not an initialized or copyable host checkpoint."""
    file: PinnedFile
    time: str
    schema: tuple
    _validated_sha256: str = field(default='', init=False, repr=False)

    @property
    def itimestep(self):
        return 0

    @classmethod
    def capture(cls, path, *, expected_time):
        import netCDF4
        from harness.native_replay_compare import _decoded_char_frame
        pin = PinnedFile.bind(path)
        datetime.strptime(expected_time, _STAMP)
        with netCDF4.Dataset(pin.path) as ds:
            ds.set_auto_maskandscale(False)
            if 'Time' not in ds.dimensions or len(ds.dimensions['Time']) != 1:
                raise ValueError('cold input needs one Time record')
            if ('Times' not in ds.variables or ds['Times'].dimensions != ('Time', 'DateStrLen')
                    or np.dtype(ds['Times'].dtype).kind != 'S'
                    or _decoded_char_frame(np.asarray(ds['Times'][0])) != expected_time):
                raise ValueError('cold input timestamp differs from requested time')
            dims = tuple(sorted((name, len(value)) for name, value in ds.dimensions.items()))
            sizes = dict(dims)
            if any(sizes.get(name, 0) <= 0 for name in ('west_east', 'south_north', 'bottom_top')):
                raise ValueError('cold input has no native mass-grid geometry')
            for name in ('T', 'THM', 'QVAPOR'):
                if (name not in ds.variables or ds[name].dimensions !=
                        ('Time', 'bottom_top', 'south_north', 'west_east')
                        or np.dtype(ds[name].dtype) != np.dtype('float32')
                        or not np.isfinite(np.asarray(ds[name][:])).all()):
                    raise ValueError('cold input lacks finite native thermodynamic fields')
            variables = tuple((name, np.dtype(var.dtype).str, tuple(var.dimensions), tuple(var.shape))
                              for name, var in sorted(ds.variables.items()))
        pin.verify()
        result = cls(pin, expected_time, (dims, variables))
        object.__setattr__(result, '_validated_sha256', pin.sha256)
        return result


@dataclass(frozen=True)
class LiveState:
    checkpoint: NativeCheckpoint
    session: str
    generation: int
    ready: StepReady | None


def checkpoint_geometry_id(checkpoint: NativeCheckpoint) -> str:
    """Value-only identity for native mass-grid coordinates/projection."""
    import netCDF4
    checkpoint.file.verify()
    with netCDF4.Dataset(checkpoint.file.path) as ds:
        ds.set_auto_maskandscale(False)
        if 'XLAT' not in ds.variables or 'XLONG' not in ds.variables:
            raise ValueError('native analysis binding requires mass-grid XLAT/XLONG')
        coords = {}
        for name in ('XLAT', 'XLONG', 'ZNU', 'ZNW'):
            if name in ds.variables:
                values = np.asarray(ds[name][:])
                coords[name] = (values.dtype.str, tuple(values.shape), hashlib.sha256(values.tobytes()).hexdigest())
        payload = {'dimensions': {n: len(ds.dimensions[n]) for n in
                   ('west_east', 'south_north', 'bottom_top', 'bottom_top_stag') if n in ds.dimensions},
                   'coordinates': coords,
                   'projection': {n: str(ds.getncattr(n)) for n in
                   ('MAP_PROJ', 'DX', 'DY', 'TRUELAT1', 'TRUELAT2', 'STAND_LON') if n in ds.ncattrs()}}
    checkpoint.file.verify()
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


class NativeLiveStepper:
    """Each advance consumes the current live state; snapshots cannot fork it.

    H_RATE is a retained-rate transport probe; ANALYSIS_TQ applies a bound
    prognostic moist-theta/QV increment and leaves physics to compute tendencies.
    This is not an observation optimizer or a general balanced-state encoder.
    Callers must choose controls and scientific acceptance criteria.
    """
    derivative_scope = 'value_only'
    mp_physics = 137

    def __init__(self, *, initial: NativeCheckpoint | NativeColdStart, external: NativeInputs,
                 executable: PinnedFile, library: PinnedFile, runner: PinnedFile,
                 work_root: str | Path, steps: int, dt_seconds: int = 20,
                 trace_column: tuple[int, int] | None = None,
                 radiation_every_step: bool = True, control_family: str = 'H_RATE',
                 timeout_seconds: float = 3600):
        if type(steps) is not int or not 1 <= steps <= 1_000_000:
            raise ValueError('steps must be a positive bounded integer')
        if dt_seconds != 20 or type(dt_seconds) is not int:
            raise ValueError('live native pilot currently requires fixed dt=20 s')
        if type(radiation_every_step) is not bool:
            raise ValueError('radiation_every_step must be an explicit Boolean')
        self.radiation_every_step = radiation_every_step
        external.verify()
        if any(key.startswith('KDM6AD_STEP_CONTROL_') for key, _ in external.environment):
            raise ValueError('step-control environment is owned by the live session')
        if control_family not in ('H_RATE', 'ANALYSIS_TQ'):
            raise ValueError('unknown live control family')
        self.control_family = control_family
        self.cold_start = isinstance(initial, NativeColdStart)
        if self.cold_start:
            if initial._validated_sha256 != initial.file.sha256:
                raise ValueError('cold input must be captured/validated')
            if control_family != 'ANALYSIS_TQ':
                raise ValueError('cold pilot supports analysis T/Q controls only')
        elif not isinstance(initial, NativeCheckpoint) or initial.replay is not None:
            raise ValueError('live session requires a plain initial checkpoint')
        if control_family == 'H_RATE' and initial.itimestep < 1:
            raise ValueError('live pilot requires a completed noninitial timestep with rate-memory semantics')
        if radiation_every_step and not self.cold_start:
            self._require_radiation_step(initial)
        self.origin = initial
        self.initial, self.external = initial, external
        self.executable, self.library, self.runner, self.trace_column = executable, library, runner, trace_column
        self.steps, self.dt_seconds, self.timeout_seconds = steps, dt_seconds, timeout_seconds
        root = Path(work_root).resolve()
        root.mkdir(parents=True, exist_ok=True)
        self.case = Path(tempfile.mkdtemp(prefix='live_', dir=root))
        self.control_root = self.case / 'control'
        self.control_root.mkdir()
        self.base = None if self.cold_start else NativeHostTransition(
            reference=initial, executable=executable, library=library, runner=runner,
            work_root=self.case / 'validation', dt_seconds=dt_seconds,
            trace_column=trace_column, timeout_seconds=timeout_seconds)
        if trace_column is not None:
            dims = dict(initial.schema[0])
            if (len(trace_column) != 2 or any(type(x) is not int or x < 1 for x in trace_column)
                    or trace_column[0] > dims['west_east'] or trace_column[1] > dims['south_north']):
                raise ValueError('trace column is outside the native physical grid')
        self.session = uuid.uuid4().hex
        self.current: LiveState | None = None
        self.process: subprocess.Popen | None = None
        self._log = None
        self._closed = False
        self._record = {
            'scope': 'owned_sequential_value_only_native_process', 'status': 'prepared',
            'session': self.session, 'origin_kind': 'cold_input' if self.cold_start else 'restart',
            'control_family': control_family, 'initial_checkpoint': str(initial.file.path),
            'initial_sha256': initial.file.sha256, 'initial_time': initial.time,
            'initial_itimestep': initial.itimestep, 'dt_seconds': dt_seconds,
            'radiation_cadence': 'every_model_step' if radiation_every_step else 'prescribed_template',
            'radt_minutes': dt_seconds / 60 if radiation_every_step else None,
            'steps': steps, 'controls': [], 'state_carry_status': 'not_run',
            'adjustment_decisions': [],
            'stepper_source_sha256': file_sha256(Path(__file__)),
            'protocol_source_sha256': file_sha256(Path(__file__).with_name('native_step_control.py')),
            'executable_sha256': executable.sha256, 'library_candidate_sha256': library.sha256,
            'runner_sha256': runner.sha256, 'clock_policy': 'native physical time advances; analysis/observation time not assigned',
            'state_contract': 'one-use process-owned current state; file alone is not a complete working-state snapshot',
            'balance_scope': 'native RK/dynamics response; no independent equilibrium or general balance certificate',
        }
        self._save()

    @staticmethod
    def _require_radiation_step(state):
        import netCDF4
        with netCDF4.Dataset(state.file.path) as ds:
            ds.set_auto_maskandscale(False)
            if 'STEPRA' not in ds.variables:
                raise ValueError('every-step radiation needs an explicit STEPRA=1 checkpoint seed')
            value = np.asarray(ds['STEPRA'][:])
            if value.dtype != np.dtype('int32') or value.size != 1 or int(value.reshape(-1)[0]) != 1:
                raise ValueError('every-step radiation needs an explicit STEPRA=1 checkpoint seed')
        state.file.verify()

    def _save(self):
        (self.case / 'live_session.json').write_text(json.dumps(self._record, indent=2) + '\n')

    def _verify_pins(self):
        self.origin.file.verify()
        if self.base is not None:
            self.base.snapshot(self.initial)
        self.external.verify()
        for pin in (self.executable, self.library, self.runner):
            pin.verify()

    def _fail(self, exc):
        self._record.update(status='failed', error=f'{type(exc).__name__}: {exc}')
        self._save()
        self.close()

    def __enter__(self):
        if self.process is not None or self._closed:
            raise RuntimeError('a live session cannot be entered twice')
        try:
            self._verify_pins()
            initial_path = self.case / ('wrfinput_d01' if self.cold_start else 'checkpoint_input_d01_' + self.origin.time)
            _copy_checkpoint(self.origin.file.path, initial_path)
            if file_sha256(initial_path) != self.origin.file.sha256:
                raise RuntimeError('staged live input differs from initial state')
            self.input_path = initial_path
            for name, pin in self.external.assets:
                if name == initial_path.name:
                    if pin.sha256 != self.origin.file.sha256:
                        raise ValueError('cold input asset conflicts with the pinned origin')
                    continue
                (self.case / name).symlink_to(pin.path)
            (self.case / 'wrf.exe').symlink_to(self.executable.path)
            duration = self.steps * self.dt_seconds
            end = datetime.strptime(self.origin.time, _STAMP) + timedelta(seconds=duration)
            nml = native_step_namelist(self.external.namelist.path.read_text(),
                start_time=self.origin.time, dt_seconds=self.dt_seconds)
            if self.cold_start:
                nml = set_or_insert(nml, 'restart', '.false.', section='&time_control')
                nml = set_or_insert(nml, 'input_inname', '"wrfinput_d<domain>"', section='&time_control')
            nml = set_or_insert(nml, 'run_seconds', str(duration), section='&time_control')
            if self.radiation_every_step:
                nml = set_or_insert(nml, 'radt', format(self.dt_seconds / 60, '.17g'), section='&physics')
            for key in ('year', 'month', 'day', 'hour', 'minute', 'second'):
                nml = set_or_insert(nml, 'end_' + key, str(getattr(end, key)), section='&time_control')
            (self.case / 'namelist.input').write_text(nml)
            env = dict(self.external.environment)
            env['KDM6AD_STEP_CONTROL_ROOT'] = str(self.control_root)
            env['KDM6AD_STEP_CONTROL_FAMILY'] = self.control_family
            if self.cold_start:
                env['KDM6AD_STEP_CONTROL_CAPTURE_INITIAL'] = '1'
            if self.trace_column:
                env.update(KDM6AD_NATIVE_TRACE_FILE=str(self.case / 'native_trace.hex'),
                    KDM6AD_NATIVE_TRACE_I=str(self.trace_column[0]),
                    KDM6AD_NATIVE_TRACE_J=str(self.trace_column[1]))
            if sys.platform == 'darwin':
                env['DYLD_PRINT_LIBRARIES'] = '1'
            command = [sys.executable, str(self.runner.path), '--case', str(self.case),
                '--mp', '137', '--minutes', '0', '--seconds', str(duration), '--history', '0',
                '--history-s', str(self.dt_seconds), '--np', '1', '--proc-grid', '1x1',
                '--fixed-dt', '--label', 'live_step_control']
            self._record.update(command=command, namelist_sha256=file_sha256(self.case / 'namelist.input'),
                runner_input_environment_sha256=hashlib.sha256(json.dumps(sorted(env.items())).encode()).hexdigest())
            self._log = (self.case / 'harness.stdout').open('x')
            if os.name != 'posix':
                raise OSError('live native runner requires POSIX process-group ownership')
            self.process = subprocess.Popen(command, env=env, stdout=self._log,
                stderr=subprocess.STDOUT, start_new_session=True)
            self._record.update(status='running', runner_pid=self.process.pid)
            self._save()
            ready = self._await_ready(0)
            if self.cold_start:
                startup = NativeCheckpoint.capture(self.case / ('wrfrst_d01_' + self.origin.time),
                    expected_time=self.origin.time, expected_itimestep=0, receipt=self.case / 'live_session.json')
                self.base = NativeHostTransition(reference=startup, executable=self.executable,
                    library=self.library, runner=self.runner, work_root=self.case / 'validation',
                    dt_seconds=self.dt_seconds, trace_column=self.trace_column, timeout_seconds=self.timeout_seconds)
                if self.radiation_every_step:
                    self._require_radiation_step(startup)
                self.initial = startup
                self._record.update(startup_checkpoint=str(startup.file.path), startup_sha256=startup.file.sha256,
                    startup_variable_count=len(startup.fields))
                self._save()
            self.current = LiveState(self.initial, self.session, 0, ready)
            return self
        except BaseException as exc:
            self._fail(exc)
            raise

    def _await_file(self, path: Path):
        deadline = time.monotonic() + self.timeout_seconds
        while not path.exists():
            if self.process is None or self.process.poll() is not None:
                raise RuntimeError('native process exited before the required control boundary')
            if time.monotonic() >= deadline:
                raise TimeoutError(f'native control boundary timed out: {path.name}')
            time.sleep(0.05)

    def _await_ready(self, generation):
        step = self.origin.itimestep + generation
        path = self.control_root / f'ready_{step:010d}.txt'
        self._await_file(path)
        ready = read_ready(path, expected_step=step)
        expected = datetime.strptime(self.origin.time, _STAMP) + timedelta(seconds=generation * self.dt_seconds)
        dims = dict(self.origin.schema[0])
        if (ready.time != expected.strftime(_STAMP) or ready.bounds !=
                (1, dims['west_east'], 1, dims['bottom_top'], 1, dims['south_north'])):
            raise ValueError('native ready clock/physical domain differs from the pinned case')
        return ready

    def _checkpoint(self, generation):
        stamp = (datetime.strptime(self.initial.time, _STAMP) +
                 timedelta(seconds=generation * self.dt_seconds)).strftime(_STAMP)
        state = NativeCheckpoint.capture(self.case / ('wrfrst_d01_' + stamp),
            expected_time=stamp, expected_itimestep=self.initial.itimestep + generation,
            receipt=self.case / 'live_session.json')
        result = self.base.snapshot(state)
        if self.radiation_every_step:
            self._require_radiation_step(result)
        return result

    def advance(self, state: LiveState, updates: Sequence[HeatingUpdate] | NativeAnalysisIncrement = ()) -> LiveState:
        """Apply one H_RATE or ANALYSIS_TQ command and carry the host through dt."""
        if (self._closed or self.process is None or self.current is None
                or state is not self.current or state.session != self.session
                or state.generation >= self.steps or state.ready is None):
            raise ValueError('advance requires the current unconsumed state of this live session')
        analysis_binding = None
        analysis_background_t = None
        analysis_background_q = None
        prepared_analysis = None
        if self.control_family == 'ANALYSIS_TQ' and isinstance(updates, NativeAnalysisIncrement):
            increment = updates
            dims = dict(state.checkpoint.schema[0])
            expected_shape = (dims['west_east'], dims['bottom_top'], dims['south_north'])
            geometry = checkpoint_geometry_id(state.checkpoint)
            if (increment.model_valid_time != state.checkpoint.time
                    or increment.background_checkpoint_id != state.checkpoint.file.sha256
                    or increment.geometry_id != geometry or increment.native_layout != 'i,k,j'):
                raise ValueError('analysis increment time/geometry/background differs from current host state')
            dt, dq, mask = increment.delta_theta_m, increment.delta_qv, increment.unchanged_mask
            if (not isinstance(dt, np.ndarray) or not isinstance(dq, np.ndarray)
                    or not isinstance(mask, np.ndarray) or mask.dtype != np.dtype(bool)
                    or dt.shape != expected_shape or dq.shape != expected_shape or mask.shape != expected_shape
                    or dt.dtype.kind != 'f' or dq.dtype != dt.dtype
                    or not np.isfinite(dt).all() or not np.isfinite(dq).all()
                    or not np.array_equal(mask, (dt == 0.0) & (dq == 0.0))):
                raise ValueError('analysis increment arrays differ from the full native i,k,j layout')
            # One read per native prognostic field, then a k,j,i -> i,k,j
            # transpose. No NetCDF scalar reads occur in the sparse update loop.
            try:
                import netCDF4

                with netCDF4.Dataset(state.checkpoint.file.path) as ds:
                    ds.set_auto_maskandscale(False)
                    file_shape = (
                        dims['bottom_top'], dims['south_north'], dims['west_east']
                    )
                    loaded = []
                    for name in ('THM_2', 'QVAPOR'):
                        if (name not in ds.variables
                                or ds[name].dimensions != ('Time', 'bottom_top', 'south_north', 'west_east')
                                or np.dtype(ds[name].dtype) != np.dtype(np.float32)
                                or ds[name].shape != (1,) + file_shape):
                            raise ValueError('analysis background requires full native float32 THM_2/QVAPOR')
                        file_order = np.asarray(ds[name][0])
                        if not np.isfinite(file_order).all():
                            raise ValueError(f'analysis background {name} must be finite')
                        native_order = np.ascontiguousarray(np.transpose(file_order, (2, 0, 1)))
                        if native_order.shape != expected_shape:
                            raise ValueError('analysis background transpose differs from native i,k,j bounds')
                        loaded.append(native_order)
                analysis_background_t, analysis_background_q = loaded
                prepared_analysis = prepare_effective_analysis(
                    analysis_background_t, analysis_background_q, dt, dq, mask,
                    bounds=state.ready.bounds,
                )
            except BaseException as exc:
                self._fail(exc)
                raise
            updates = prepared_analysis.updates
            analysis_binding = {'model_valid_time': increment.model_valid_time,
                'geometry_id': geometry, 'background_checkpoint_id': increment.background_checkpoint_id,
                'posterior_checkpoint_id': increment.posterior_checkpoint_id,
                'delta_theta_m_sha256': hashlib.sha256(dt.tobytes()).hexdigest(),
                'delta_qv_sha256': hashlib.sha256(dq.tobytes()).hexdigest(),
                'effective_delta_theta_m_sha256': hashlib.sha256(prepared_analysis.delta_theta_m.tobytes()).hexdigest(),
                'effective_delta_qv_sha256': hashlib.sha256(prepared_analysis.delta_qv.tobytes()).hexdigest(),
                'effective_theta_m_sha256': hashlib.sha256(prepared_analysis.effective_theta_m.tobytes()).hexdigest(),
                'effective_qv_sha256': hashlib.sha256(prepared_analysis.effective_qv.tobytes()).hexdigest(),
                'native_layout': 'i,k,j', 'effective_counts': dict(prepared_analysis.counts),
                'all_noop': prepared_analysis.all_noop,
                'no_applied_update': prepared_analysis.all_noop,
                'background_arrays_read_once': ['THM_2', 'QVAPOR'],
                'background_variable_read_counts': {'THM_2': 1, 'QVAPOR': 1},
                'per_point_netcdf_reads': 0}
        else:
            updates = tuple(updates)
            if self.control_family == 'ANALYSIS_TQ' and updates:
                raise ValueError('nonempty analysis requires a bound NativeAnalysisIncrement')
            if self.control_family == 'ANALYSIS_TQ':
                dims = dict(state.checkpoint.schema[0])
                grid_points = dims['west_east'] * dims['bottom_top'] * dims['south_north']
                analysis_binding = {
                    'native_layout': 'i,k,j',
                    'effective_counts': {
                        'requested_points': 0, 'noop_points': 0, 'applied_points': 0,
                        'empty_points': grid_points, 'requested_nonzero_components': 0,
                        'applied_components': 0, 'zero_effect_components': 0,
                    },
                    'all_noop': True, 'no_applied_update': True,
                    'background_arrays_read_once': [],
                    'background_variable_read_counts': {'THM_2': 0, 'QVAPOR': 0},
                    'per_point_netcdf_reads': 0,
                    'source': 'explicit empty update sequence',
                }
        try:
            self._verify_pins()
            self.base.snapshot(state.checkpoint)
            packet = (encode_command if self.control_family == 'H_RATE' else encode_analysis_command)(
                state.ready.step, updates, state.ready.bounds)
            # The ready phase is after restart IO and before the next host step.
            # Check the command's expected memory values before publishing it.
            import netCDF4
            before_bits = []
            if self.control_family == 'H_RATE':
                with netCDF4.Dataset(state.checkpoint.file.path) as ds:
                    ds.set_auto_maskandscale(False)
                    if ('H_DIABATIC' not in ds.variables
                            or ds['H_DIABATIC'].dimensions !=
                            ('Time', 'bottom_top', 'south_north', 'west_east')):
                        raise ValueError('unexpected native control coordinate convention')
                    for update in updates:
                        index = (0, update.k - 1, update.j - 1, update.i - 1)
                        old = np.float32(ds['H_DIABATIC'][index])
                        with np.errstate(over='ignore'):
                            new = np.float32(old + np.float32(update.delta))
                        if not np.isfinite(new) or _f32_bits(new) == _f32_bits(old):
                            raise ValueError('heating proposal has no finite representable memory departure')
                        before_bits.append((_f32_bits(old),))
            else:
                if analysis_background_t is None or analysis_background_q is None:
                    if updates:
                        raise RuntimeError('effective analysis background was not prepared')
                for update in updates:
                    index = (update.i - 1, update.k - 1, update.j - 1)
                    old_t = np.float32(analysis_background_t[index])
                    old_q = np.float32(analysis_background_q[index])
                    expected_t, expected_q = apply_pair(
                        old_t, old_q, update.delta_theta_m, update.delta_qv
                    )
                    if (prepared_analysis is None
                            or _f32_bits(expected_t) != _f32_bits(prepared_analysis.effective_theta_m[index])
                            or _f32_bits(expected_q) != _f32_bits(prepared_analysis.effective_qv[index])):
                        raise RuntimeError('effective arrays differ from strict paired apply_pair')
                    before_bits.append((_f32_bits(old_t), _f32_bits(old_q)))
            step = state.ready.step
            command_path = self.control_root / f'command_{step:010d}.txt'
            atomic_write_command(command_path, packet)
            ack_path = self.control_root / f'applied_{step:010d}.txt'
            self._await_file(ack_path)
            applied = (read_applied if self.control_family == 'H_RATE' else read_analysis_applied)(
                ack_path, expected_step=step, updates=updates)
            observed = ([(row.old_bits,) for row in applied] if self.control_family == 'H_RATE' else
                        [(row.old_t_bits, row.old_q_bits) for row in applied])
            if observed != before_bits:
                raise RuntimeError('live heating memory differs from the exposed completed-step checkpoint'
                    if self.control_family == 'H_RATE' else 'live analysis state differs from the exposed checkpoint')
            record = {'generation': state.generation, 'model_time': state.ready.time,
                'input_checkpoint_sha256': state.checkpoint.file.sha256,
                'command_sha256': file_sha256(command_path), 'ack_sha256': file_sha256(ack_path),
                'control_family': self.control_family, 'analysis_binding': analysis_binding,
                'applied': [dict(asdict(row), update={key: float(value) if isinstance(value, np.floating) else value
                    for key, value in asdict(row.update).items()}) for row in applied]}
            self._record['controls'].append(record)
            self._save()
            generation = state.generation + 1
            if generation < self.steps:
                ready = self._await_ready(generation)
                checkpoint = self._checkpoint(generation)
            else:
                self._finish()
                ready, checkpoint = None, self._checkpoint(generation)
            state.checkpoint.file.verify()
            next_state = LiveState(checkpoint, self.session, generation, ready)
            self.current = next_state
            record.update(output_checkpoint_sha256=checkpoint.file.sha256,
                          output_time=checkpoint.time, output_itimestep=checkpoint.itimestep)
            self._save()
            return next_state
        except BaseException as exc:
            self._fail(exc)
            raise

    def _finish(self):
        if self.process is None:
            raise RuntimeError('native session never started')
        code = self.process.wait(timeout=self.timeout_seconds)
        archives = list((self.case / 'runs').iterdir())
        if len(archives) != 1:
            raise RuntimeError('native live runner did not produce one explicit archive')
        valid = json.loads((archives[0] / 'experiment_valid.json').read_text())
        if (code != 0 or valid.get('experiment_valid') is not True
                or valid.get('active_input_identity_complete') is not True
                or valid.get('model_completed') is not True
                or valid.get('actual_proc_grid') != '1x1'
                or type(valid.get('exit_code')) is not int or valid['exit_code'] != 0):
            raise RuntimeError('native live execution was incomplete or invalid')
        self._verify_pins()
        if file_sha256(self.input_path) != self.origin.file.sha256:
            raise RuntimeError('native live host changed its staged initial input')
        if self.trace_column:
            from harness.native_trace_records import validate_window_trace
            validate_window_trace(self.case / 'native_trace.hex',
                steps=tuple(range(self.initial.itimestep + 1, self.initial.itimestep + self.steps + 1)),
                i=self.trace_column[0], j=self.trace_column[1],
                levels=dict(self.initial.schema[0])['bottom_top'], dt=self.dt_seconds)
        loader = []
        for path in archives[0].glob('wrf_*.stdout'):
            loader.extend(line for line in path.read_text(errors='replace').splitlines()
                          if 'dyld[' in line and 'libkdm6_c' in line)
        if sys.platform == 'darwin':
            expected = str(self.library.path)
            if not loader or any(not line.endswith('> ' + expected) for line in loader):
                raise RuntimeError('actual native loaded KDM library differs from the pinned candidate')
        self._record.update(status='complete', returncode=code, archive=str(archives[0]),
                            execution=valid, loaded_library_lines=loader)
        self._save()

    def close(self):
        if not self._closed:
            if self.process is not None and self.process.poll() is None:
                _stop_runner_group(self.process)
            if self._record['status'] not in ('failed', 'complete'):
                self._record['status'] = 'closed_before_completion'
                self._save()
            if self._log is not None:
                self._log.close()
            self._closed = True

    def __exit__(self, exc_type, exc, traceback):
        if exc is not None and self._record['status'] not in ('failed', 'complete'):
            self._record.update(status='failed', error=f'{exc_type.__name__}: {exc}')
            self._save()
        self.close()

    def vjp(self, *args, **kwargs):
        raise RuntimeError('live native stepping is value_only; no full-host VJP')

    def jvp(self, *args, **kwargs):
        raise RuntimeError('live native stepping is value_only; no full-host JVP')


@dataclass(frozen=True)
class AdjustmentDecision:
    """Caller's declared physical-adjustment gate; not inferred from exit code."""
    accepted: bool
    evidence: str


@dataclass(frozen=True)
class StateCarryResult:
    states: tuple[LiveState, ...]
    decisions: tuple[AdjustmentDecision, ...]


def run_state_carry_loop(stepper: NativeLiveStepper, *, propose, validate_adjustment) -> StateCarryResult:
    """Propose from current state, adjust once, accept, then carry it forward.

    ``propose`` supplies H_RATE or ANALYSIS_TQ controls, potentially from an
    external analysis solver. ``validate_adjustment`` must explicitly judge the modeled
    response; successful integration alone never certifies physical balance.
    A rejected adjustment closes the owned process before another step can run.
    No observations, optimizer, or default physical-balance criterion is invented.
    """
    if not callable(propose) or not callable(validate_adjustment):
        raise TypeError('state carry needs proposal and physical-adjustment callbacks')
    states, decisions = [], []
    stepper._record['state_carry_status'] = 'running'
    stepper._save()
    try:
        with stepper as live:
            current = live.current
            if current is None:
                raise RuntimeError('live initial state was not exposed')
            states.append(current)
            for _ in range(live.steps):
                before = current
                proposal = propose(before)
                controls = proposal if isinstance(proposal, NativeAnalysisIncrement) else tuple(proposal)
                after = live.advance(before, controls)
                decision = validate_adjustment(before, after, controls)
                if (not isinstance(decision, AdjustmentDecision)
                        or type(decision.accepted) is not bool
                        or not isinstance(decision.evidence, str) or not decision.evidence.strip()):
                    raise ValueError('adjustment gate needs an explicit Boolean decision and evidence')
                stepper._record['adjustment_decisions'].append({
                    'input_generation': before.generation, 'output_generation': after.generation,
                    'accepted': decision.accepted, 'evidence': decision.evidence})
                stepper._save()
                if not decision.accepted:
                    raise RuntimeError('physical adjustment rejected: ' + decision.evidence)
                decisions.append(decision)
                current = after
                states.append(current)
            stepper._record['state_carry_status'] = 'accepted'
            stepper._save()
            return StateCarryResult(tuple(states), tuple(decisions))
    except BaseException as exc:
        stepper._record.update(state_carry_status='rejected_or_failed',
                              state_carry_error=f'{type(exc).__name__}: {exc}')
        stepper._save()
        stepper.close()
        raise
