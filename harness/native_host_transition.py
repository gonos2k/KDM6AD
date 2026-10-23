"""Value-only MP137 transition using an explicit origin-bound replay context.

No checkpoint field is converted to a floating control: integer fields, strings,
global metadata, prognostic fields and retained physics memory stay together in
the original NetCDF. Hashes define explicit value boundaries. This implements
one logical host timestep by replaying the continuous prefix through run_ss_case.py;
it does not implement a host adjoint, control transform or observation operator.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from typing import TYPE_CHECKING

import numpy as np

from harness.run_ss_case import (
    _namelist_assignments, _parse_max_dom, _parse_nocolons_flag, set_or_insert,
)

if TYPE_CHECKING:
    from oracle.kdm6.da_host_window import HostTransition

_STAMP = "%Y-%m-%d_%H:%M:%S"
_ESSENTIAL = frozenset({"Times", "ITIMESTEP", "H_DIABATIC", "QV_DIABATIC",
                        "QC_DIABATIC", "QNCCN"})


def _checkpoint_header(dataset) -> tuple[str, int, tuple]:
    from harness.native_replay_compare import _decoded_char_frame

    if "Time" not in dataset.dimensions or len(dataset.dimensions["Time"]) != 1:
        raise ValueError("native checkpoint needs exactly one Time record")
    if not _ESSENTIAL <= dataset.variables.keys():
        raise ValueError(f"incomplete native restart fields: {sorted(_ESSENTIAL - dataset.variables.keys())}")
    times = dataset["Times"]
    if tuple(times.dimensions) != ("Time", "DateStrLen") or np.dtype(times.dtype).kind != "S":
        raise ValueError("native Times must be character (Time, DateStrLen)")
    stamp = _decoded_char_frame(np.asarray(times[0]))
    datetime.strptime(stamp, _STAMP)
    values = np.asarray(dataset["ITIMESTEP"][:])
    if values.dtype.kind not in "iu" or values.size != 1:
        raise ValueError("native ITIMESTEP must be one integer")
    counter = int(values.reshape(-1)[0])
    if counter < 0:
        raise ValueError("native ITIMESTEP must be nonnegative")
    dims = tuple(sorted((name, len(dim)) for name, dim in dataset.dimensions.items()))
    variables = tuple((name, np.dtype(var.dtype).str, tuple(var.dimensions), tuple(var.shape))
                      for name, var in sorted(dataset.variables.items()))
    return stamp, counter, (dims, variables)


def file_sha256(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


@dataclass(frozen=True)
class PinnedFile:
    path: Path
    sha256: str

    @classmethod
    def bind(cls, path: str | Path) -> PinnedFile:
        source = Path(path).resolve(strict=True)
        if not source.is_file():
            raise ValueError(f"expected a file: {source}")
        return cls(source, file_sha256(source))

    def verify(self) -> None:
        if file_sha256(self.path) != self.sha256:
            raise RuntimeError(f"pinned file changed: {self.path}")


@dataclass(frozen=True)
class NativeCheckpoint:
    """A hash-bound completed-timestep value, including discrete context.

    The caller must choose an audited restart/timestep boundary. Presence of
    these fields alone is not a proof that every host configuration is replayable.
    ``schema`` retains every variable's dtype, dimensions and complete shape.
    """
    file: PinnedFile
    time: str
    itimestep: int
    schema: tuple
    receipt: Path | None = None
    replay: NativeReplayContext | None = field(default=None, init=False, repr=False, compare=False)
    _validated_sha256: str = field(default="", init=False, repr=False, compare=False)

    @classmethod
    def capture(cls, path: str | Path, *, expected_time: str,
                expected_itimestep: int, receipt: Path | None = None) -> NativeCheckpoint:
        import netCDF4
        from harness.native_replay_compare import _declared_missing_mask, _declared_missing_values

        datetime.strptime(expected_time, _STAMP)
        if type(expected_itimestep) is not int or expected_itimestep < 0:
            raise ValueError("expected_itimestep must be a nonnegative integer")
        pinned = PinnedFile.bind(path)
        with netCDF4.Dataset(pinned.path, "r") as dataset:
            dataset.set_auto_maskandscale(False)
            stamp, counter, schema = _checkpoint_header(dataset)
            if stamp != expected_time:
                raise ValueError("native checkpoint timestamp differs from expected_time")
            if counter != expected_itimestep:
                raise ValueError("native checkpoint ITIMESTEP differs from expected value")
            for name, variable in sorted(dataset.variables.items()):
                dtype = np.dtype(variable.dtype)
                if dtype.kind not in "fiuS":
                    raise ValueError(f"unsupported native checkpoint dtype: {name}: {dtype}")
                if dtype.kind in "fiu":
                    data = np.asarray(variable[:])
                    if not np.isfinite(data).all():
                        raise ValueError(f"nonfinite native checkpoint field: {name}")
                    if _declared_missing_mask(data, _declared_missing_values(variable)).any():
                        raise ValueError(f"declared missing native checkpoint field: {name}")
        pinned.verify()  # A concurrent change during inspection is not a snapshot.
        checkpoint = cls(pinned, expected_time, expected_itimestep, schema, receipt)
        # A public dataclass constructor alone does not certify finite values.
        # The certificate stays in the explicit checkpoint and binds its scan to
        # immutable file bytes; no mutable backend validation cache is needed.
        object.__setattr__(checkpoint, "_validated_sha256", pinned.sha256)
        return checkpoint

    @property
    def fields(self) -> frozenset[str]:
        return frozenset(row[0] for row in self.schema[1])


@dataclass(frozen=True)
class NativeReplayContext:
    """Explicit reconstruction recipe, not a claim of restart sufficiency.

    Frames are plain hash-bound checkpoints, including the current frame. All
    remain part of the value and must survive snapshots/replay. Intermediate
    analysis increments are unsupported: a new trial starts at the origin.
    """
    origin: NativeCheckpoint
    frames: tuple[NativeCheckpoint, ...]
    inputs_sha256: str
    runtime_sha256: str


@dataclass(frozen=True)
class NativeInputs:
    """Prescribed namelist/assets/environment, separate from evolving state.

    Asset entries are (case basename, pinned file). Environment values are never
    written into receipts; only their hash is recorded. They must be supplied
    explicitly rather than inherited afresh at each optimization trial.
    """
    namelist: PinnedFile
    assets: tuple[tuple[str, PinnedFile], ...]
    environment: tuple[tuple[str, str], ...]

    def verify(self) -> None:
        names = [name for name, _ in self.assets]
        # Trace and validation receipts are writer-owned too: a staged asset
        # symlink must never turn either output into a write to a pinned input.
        reserved = {"namelist.input", "namelist.output", "wrf.exe", "runs",
                    "native_trace.hex", "transition.json", "validation"}
        if len(set(names)) != len(names) or any(
                Path(n).name != n or n.casefold() in reserved or n in ("", ".", "..")
                or n.casefold().startswith(("wrfrst_", "checkpoint_input_", "rsl.",
                                           "klfs_", "wrfout_", "prefix_compare_"))
                for n in names):
            raise ValueError("native assets need unique safe case basenames")
        keys = [key for key, _ in self.environment]
        if len(keys) != len(set(keys)) or "PATH" not in keys:
            raise ValueError("native environment needs unique keys and an explicit PATH")
        for key, value in self.environment:
            if not isinstance(key, str) or not isinstance(value, str) or not key or "=" in key or "\0" in key + value:
                raise ValueError("invalid native environment entry")
            if key.startswith("KDM6AD_NATIVE_TRACE_") or key in (
                    "LD_PRELOAD", "LD_LIBRARY_PATH", "DYLD_INSERT_LIBRARIES",
                    "DYLD_LIBRARY_PATH", "DYLD_FALLBACK_LIBRARY_PATH"):
                raise ValueError(f"native environment cannot override controlled instrumentation/loading: {key}")
        self.namelist.verify()
        for _, pinned in self.assets:
            pinned.verify()


def _copy_checkpoint(source: Path, target: Path) -> None:
    """Independent regular file; APFS clone avoids duplicating large checkpoints."""
    if sys.platform == "darwin":
        result = subprocess.run(["/bin/cp", "-c", "-p", str(source), str(target)],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if result.returncode == 0:
            return
        target.unlink(missing_ok=True)
    shutil.copy2(source, target)


def _runner_group_quiescent(pgid: int) -> bool:
    """Confirm no integrating member after an EPERM signal probe.

    A reaped leader can leave a transient zombie-only process group on macOS.
    EPERM itself is never evidence of termination: an unavailable/ambiguous ps
    snapshot or any non-zombie group member must preserve the original error.
    """
    try:
        result = subprocess.run(["ps", "-axo", "pgid=,stat="], capture_output=True,
                                text=True, timeout=2, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    if result.returncode != 0:
        return False
    for row in result.stdout.splitlines():
        fields = row.split()
        if len(fields) != 2 or not fields[0].isdigit():
            return False
        if int(fields[0]) == pgid and not fields[1].startswith("Z"):
            return False
    return True


def _signal_runner_group(pgid: int, sig: int) -> bool:
    """Signal the owned group, ignoring only verified absent/exited groups."""
    try:
        os.killpg(pgid, sig)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        if _runner_group_quiescent(pgid):
            return False
        raise


def _stop_runner_group(process: subprocess.Popen) -> None:
    """Terminate only the new session created for this runner and its children."""
    _signal_runner_group(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    # Give MPI time to forward termination to application processes, including
    # children which it may have placed in another process group.
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if not _signal_runner_group(process.pid, 0):
            break
        time.sleep(0.05)
    # The runner may exit before a descendant which ignores SIGTERM.
    _signal_runner_group(process.pid, signal.SIGKILL)
    process.wait(timeout=5)


def _run_runner(command: list[str], *, env: dict[str, str], stdout,
                timeout: float) -> subprocess.CompletedProcess:
    if os.name != "posix":
        raise OSError("native host execution requires POSIX process-group cleanup")
    process = subprocess.Popen(command, env=env, stdout=stdout, stderr=subprocess.STDOUT,
                               start_new_session=True)
    try:
        code = process.wait(timeout=timeout)
        if code != 0:
            _stop_runner_group(process)
        return subprocess.CompletedProcess(command, code)
    except BaseException:
        _stop_runner_group(process)
        raise


# With override_restart_timers=true, input_wrf skips output-alarm restoration.
# The audited host uses stream 1=history and 7=auxhist6. Their ringing bits
# differ when a checkpoint is a terminal versus an interior prefix output.
# No prognostic/input/boundary alarm or other metadata is normalized.
_OUTPUT_RING_ATTRIBUTES = frozenset({"WRF_ALARM_ISRINGING_01", "WRF_ALARM_ISRINGING_07"})


def compare_restart_metadata(reference, candidate) -> dict:
    """Compare all attributes, with two explicitly output-only ringing bits.

    This normalization is specific to this backend's reset-IO-alarm policy;
    it is not part of the general native raw-variable comparator.
    """
    differences, normalized = [], []
    def check(a, b, scope, ignored=frozenset()):
        names_a, names_b = set(a.ncattrs()), set(b.ncattrs())
        if names_a != names_b:
            differences.append({"scope": scope, "attribute_names_differ": True})
        for name in sorted(names_a & names_b):
            x, y = np.asarray(a.getncattr(name)), np.asarray(b.getncattr(name))
            equal = x.dtype == y.dtype and x.shape == y.shape and x.tobytes() == y.tobytes()
            if not equal:
                item = {"scope": scope, "attribute": name}
                if name in ignored:
                    # Only the expected integer Boolean ringer representation
                    # qualifies. Different or malformed metadata still refuses.
                    if (x.shape == y.shape == () and x.dtype == y.dtype == np.dtype("int32")
                            and int(x) in (0, 1) and int(y) in (0, 1)):
                        normalized.append(dict(item, reference=int(x), candidate=int(y)))
                        continue
                differences.append(item)
    check(reference, candidate, "global", _OUTPUT_RING_ATTRIBUTES)
    if set(reference.variables) != set(candidate.variables):
        differences.append({"scope": "variables", "variable_names_differ": True})
    for name in sorted(set(reference.variables) & set(candidate.variables)):
        check(reference[name], candidate[name], name)
    return {"passed": not differences, "differences": differences,
            "output_ringing_normalizations": normalized,
            "policy": "override_restart_timers=true; only history/auxhist6 Boolean ringing bits normalized"}


def native_step_namelist(text: str, *, start_time: str, dt_seconds: int) -> str:
    assignments = _namelist_assignments(text)
    if _parse_max_dom(assignments) != 1 or _parse_nocolons_flag(assignments):
        raise ValueError("native transition currently supports one colon-named domain")
    start = datetime.strptime(start_time, _STAMP)
    end = start + timedelta(seconds=dt_seconds)
    values = {"run_days": 0, "run_hours": 0, "run_minutes": 0,
              "run_seconds": dt_seconds, "restart": ".true.",
              "write_restart_at_0h": ".false.", "write_hist_at_0h_rst": ".false.",
              "override_restart_timers": ".true.",
              "rst_inname": '"checkpoint_input_d<domain>_<date>"',
              "rst_outname": '"wrfrst_d<domain>_<date>"',
              "restart_interval": 0, "restart_interval_d": 0,
              "restart_interval_h": 0, "restart_interval_m": 0,
              "restart_interval_s": dt_seconds,
              "history_interval": 0, "history_interval_s": dt_seconds}
    for prefix, stamp in (("start", start), ("end", end)):
        for key in ("year", "month", "day", "hour", "minute", "second"):
            values[prefix + "_" + key] = getattr(stamp, key)
    for key, value in values.items():
        text = set_or_insert(text, key, str(value), section="&time_control")
    for key, value, section in (
        ("mp_physics", 137, "&physics"), ("no_mp_heating", 0, "&physics"),
        ("use_theta_m", 1, "&dynamics"), ("use_q_diabatic", 0, "&dynamics"),
        ("time_step", dt_seconds, "&domains"),
        ("time_step_fract_num", 0, "&domains"), ("time_step_fract_den", 1, "&domains"),
        ("nproc_x", 1, "&domains"), ("nproc_y", 1, "&domains"),
        ("use_adaptive_time_step", ".false.", "&domains"),
        ("step_to_output_time", ".false.", "&domains"),
    ):
        text = set_or_insert(text, key, str(value), section=section)
    # The shared exact-key setter is intentionally narrow. Upper/lower-case
    # duplicates or other ambiguous template forms must not override a fence.
    _namelist_assignments(text)
    return text


class NativeHostTransition:
    """Structural HostTransition[NativeCheckpoint, NativeInputs], value_only.

    Each call replays from the supplied trial's origin through the next full dt.
    Every prior frame is compared before accepting the new output. Restarting
    directly from an intermediate file has NOT passed native bitwise replay.
    This origin-bound reference backend costs O(N²) for N calls, requires fixed
    prescribed inputs, and cannot inject a control increment mid-window.
    The reference declares the serialized schema, not complete hidden host state.
    """
    mp_physics = 137
    derivative_scope = "value_only"

    def __init__(self, *, reference: NativeCheckpoint, executable: PinnedFile,
                 library: PinnedFile, runner: PinnedFile, work_root: str | Path,
                 dt_seconds: int = 20, trace_column: tuple[int, int] | None = None,
                 timeout_seconds: float = 3600):
        if type(dt_seconds) is not int or dt_seconds <= 0:
            raise ValueError("native dt must be positive integer seconds")
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("native timeout must be finite and positive")
        if trace_column is not None and (len(trace_column) != 2 or any(type(v) is not int or v <= 0 for v in trace_column)):
            raise ValueError("trace column uses positive one-based native i,j")
        self.executable, self.library, self.runner = executable, library, runner
        self.work_root = Path(work_root).resolve()
        self.work_root.mkdir(parents=True, exist_ok=True)
        self.dt_seconds, self.timeout_seconds, self.trace_column = dt_seconds, timeout_seconds, trace_column
        self.reference = reference
        self.required_state_fields = reference.fields
        self.snapshot(reference)
        if trace_column:
            dims = dict(reference.schema[0])
            if (dims.get("bottom_top", 0) <= 0 or trace_column[0] > dims.get("west_east", 0)
                    or trace_column[1] > dims.get("south_north", 0)):
                raise ValueError("trace column is outside the native checkpoint grid")

    def snapshot(self, state: NativeCheckpoint) -> NativeCheckpoint:
        import netCDF4

        if not isinstance(state, NativeCheckpoint) or state.schema != self.reference.schema:
            raise ValueError("native checkpoint schema differs from complete reference")
        if state._validated_sha256 != state.file.sha256:
            raise ValueError("native checkpoint must be validated with NativeCheckpoint.capture")
        if not _ESSENTIAL <= state.fields:
            raise ValueError("incomplete native checkpoint")
        state.file.verify()
        with netCDF4.Dataset(state.file.path, "r") as dataset:
            dataset.set_auto_maskandscale(False)
            stamp, counter, schema = _checkpoint_header(dataset)
        if (stamp, counter, schema) != (state.time, state.itimestep, state.schema):
            raise ValueError("native checkpoint descriptor differs from actual file context")
        if state.replay is not None:
            context = state.replay
            if (context.origin.replay is not None or not context.frames
                    or any(frame.replay is not None for frame in context.frames)
                    or context.frames[-1].file != state.file):
                raise ValueError("invalid origin-bound replay context")
            self.snapshot(context.origin)
            for index, frame in enumerate(context.frames, 1):
                self.snapshot(frame)
                expected = datetime.strptime(context.origin.time, _STAMP) + timedelta(seconds=index * self.dt_seconds)
                if frame.time != expected.strftime(_STAMP) or frame.itimestep != context.origin.itimestep + index:
                    raise ValueError("replay context has a nonconsecutive checkpoint")
        return state  # Immutable descriptor + verified file bytes, not a hidden cache.

    def _namelist(self, text: str, state: NativeCheckpoint) -> str:
        return native_step_namelist(text, start_time=state.time, dt_seconds=self.dt_seconds)

    def forward(self, step: int, state: NativeCheckpoint,
                external: NativeInputs, dt: float) -> NativeCheckpoint:
        if type(step) is not int or step < 0 or isinstance(dt, bool) or dt != self.dt_seconds:
            raise ValueError("native forward requires a nonnegative step and its fixed dt")
        state = self.snapshot(state)
        expected = datetime.strptime(self.reference.time, _STAMP) + timedelta(seconds=step * self.dt_seconds)
        if state.time != expected.strftime(_STAMP) or state.itimestep != self.reference.itimestep + step:
            raise ValueError("native checkpoint is not at the requested full-step boundary")
        external.verify()
        for pinned in (self.executable, self.library, self.runner):
            pinned.verify()
        inputs_signature = hashlib.sha256(json.dumps({
            "namelist": external.namelist.sha256,
            "assets": [(name, pin.sha256) for name, pin in external.assets],
            "environment": sorted(external.environment),
        }, sort_keys=True).encode()).hexdigest()
        runtime_signature = hashlib.sha256(json.dumps({
            "executable": self.executable.sha256, "library_candidate": self.library.sha256,
            "runner": self.runner.sha256, "adapter": file_sha256(Path(__file__)),
            "python": file_sha256(Path(sys.executable).resolve()),
            "dt": self.dt_seconds, "trace_column": self.trace_column,
        }, sort_keys=True).encode()).hexdigest()
        if step == 0:
            if state.replay is not None:
                raise ValueError("new trial must start from a plain origin checkpoint")
            origin, prior_frames = state, ()
        else:
            context = state.replay
            if context is None or len(context.frames) != step:
                raise ValueError("intermediate state requires an explicit origin-bound replay context")
            if context.inputs_sha256 != inputs_signature or context.runtime_sha256 != runtime_signature:
                raise ValueError("prescribed inputs/runtime changed within an origin-bound replay")
            origin, prior_frames = context.origin, context.frames
        if origin.time != self.reference.time or origin.itimestep != self.reference.itimestep:
            raise ValueError("replay origin is outside the reference boundary")
        duration = (step + 1) * self.dt_seconds
        text = self._namelist(external.namelist.path.read_text(), origin)
        text = set_or_insert(text, "run_seconds", str(duration), section="&time_control")
        target_time = expected + timedelta(seconds=self.dt_seconds)
        for key in ("year", "month", "day", "hour", "minute", "second"):
            text = set_or_insert(text, "end_" + key, str(getattr(target_time, key)), section="&time_control")
        case = Path(tempfile.mkdtemp(prefix=f"step{step:04d}_", dir=self.work_root))
        receipt = case / "transition.json"
        input_path = case / ("checkpoint_input_d01_" + origin.time)
        _copy_checkpoint(origin.file.path, input_path)
        if file_sha256(input_path) != origin.file.sha256:
            raise RuntimeError("copied checkpoint bytes differ from requested state")
        for name, pinned in external.assets:
            if name == input_path.name or name.startswith("wrfrst_"):
                raise ValueError("prescribed asset collides with evolving restart state")
            (case / name).symlink_to(pinned.path)
        (case / "wrf.exe").symlink_to(self.executable.path)
        (case / "namelist.input").write_text(text)
        env = dict(external.environment)
        trace_file = case / "native_trace.hex"
        if self.trace_column is not None:
            env.update(KDM6AD_NATIVE_TRACE_FILE=str(trace_file),
                       KDM6AD_NATIVE_TRACE_I=str(self.trace_column[0]),
                       KDM6AD_NATIVE_TRACE_J=str(self.trace_column[1]))
        command = [sys.executable, str(self.runner.path), "--case", str(case),
                   "--mp", "137", "--minutes", "0", "--seconds", str(duration),
                   "--history", "0", "--history-s", str(self.dt_seconds),
                   "--np", "1", "--proc-grid", "1x1", "--fixed-dt", "--label", "native_transition"]
        record = {"scope": "value_only_origin_bound_prefix_replay", "status": "started",
                  "origin_checkpoint_sha256": origin.file.sha256, "origin_time": origin.time,
                  "prefix_steps": step + 1, "executed_seconds": duration,
                  "inputs_signature": inputs_signature, "runtime_signature": runtime_signature,
                  "replay_policy": "reintegrate continuous origin prefix; require all prior checkpoint fields bitwise equal",
                  "step": step, "input_checkpoint_sha256": state.file.sha256,
                  "input_time": state.time, "input_itimestep": state.itimestep,
                  "dt_seconds": self.dt_seconds, "command": command,
                  "runner_input_environment_sha256": hashlib.sha256(json.dumps(sorted(env.items())).encode()).hexdigest(),
                  "wrf_child_environment_policy": "run_ss_case.py forces OMP_NUM_THREADS, VECLIB_MAXIMUM_THREADS, MKL_NUM_THREADS, OMP_THREAD_LIMIT=1 and GFORTRAN_ERROR_BACKTRACE=1",
                  "executable_sha256": self.executable.sha256, "library_sha256": self.library.sha256,
                  "library_binding_scope": "pinned candidate; actual loaded library requires a separate native loader receipt",
                  "runner_sha256": self.runner.sha256, "namelist_sha256": file_sha256(case / "namelist.input"),
                  "trace_file": str(trace_file) if self.trace_column else None,
                  "io_timer_policy": "reset_io_alarms_per_full_step; no initial history write"}
        receipt.write_text(json.dumps(record, indent=2) + "\n")
        try:
            with (case / "harness.stdout").open("x") as log:
                result = _run_runner(command, env=env, stdout=log, timeout=self.timeout_seconds)
            archives = list((case / "runs").iterdir())
            if len(archives) != 1:
                raise RuntimeError("native runner did not produce one explicit archive")
            valid = json.loads((archives[0] / "experiment_valid.json").read_text())
            record.update(returncode=result.returncode, archive=str(archives[0]), execution=valid)
            if (result.returncode != 0 or valid.get("experiment_valid") is not True
                    or valid.get("active_input_identity_complete") is not True
                    or valid.get("model_completed") is not True or valid.get("actual_proc_grid") != "1x1"
                    or type(valid.get("exit_code")) is not int or valid["exit_code"] != 0):
                raise RuntimeError("native host execution is incomplete or invalid")
            import netCDF4
            from harness.native_replay_compare import compare_frames

            record["prefix_comparisons"] = []
            for frame_index, previous in enumerate(prior_frames, 1):
                replayed = NativeCheckpoint.capture(case / ("wrfrst_d01_" + previous.time),
                    expected_time=previous.time, expected_itimestep=previous.itimestep)
                self.snapshot(replayed)
                with netCDF4.Dataset(previous.file.path) as a, netCDF4.Dataset(replayed.file.path) as b:
                    a.set_auto_maskandscale(False)
                    b.set_auto_maskandscale(False)
                    comparison = compare_frames(a, b, 0, 0, previous.time)
                    comparison["restart_metadata"] = compare_restart_metadata(a, b)
                    comparison["passed"] = comparison["passed"] and comparison["restart_metadata"]["passed"]
                comparison_path = case / f"prefix_compare_{frame_index:04d}.json"
                comparison_path.write_text(json.dumps(comparison, indent=2) + "\n")
                record["prefix_comparisons"].append({"time": previous.time,
                    "passed": comparison["passed"], "report": str(comparison_path)})
                if not comparison["passed"]:
                    raise RuntimeError("continuous prefix does not reproduce the supplied intermediate state")
            stamp = target_time.strftime(_STAMP)
            output = NativeCheckpoint.capture(case / ("wrfrst_d01_" + stamp), expected_time=stamp,
                                              expected_itimestep=state.itimestep + 1, receipt=receipt)
            self.snapshot(output)
            state.file.verify()
            origin.file.verify()
            if file_sha256(input_path) != origin.file.sha256:
                raise RuntimeError("host changed the staged restart input")
            external.verify()
            for pinned in (self.executable, self.library, self.runner):
                pinned.verify()
            if self.trace_column:
                from harness.native_trace_records import validate_window_trace
                validate_window_trace(trace_file,
                    steps=tuple(range(origin.itimestep + 1, output.itimestep + 1)),
                    i=self.trace_column[0], j=self.trace_column[1],
                    levels=dict(state.schema[0])["bottom_top"], dt=self.dt_seconds)
            record.update(status="complete", output_checkpoint_sha256=output.file.sha256,
                          output_time=output.time, output_itimestep=output.itimestep)
            # Keep plain checkpoint frames in the explicit replay recipe. Avoid
            # recursive context chains and any hidden state stored on the backend.
            returned = NativeCheckpoint.capture(output.file.path, expected_time=output.time,
                expected_itimestep=output.itimestep, receipt=receipt)
            object.__setattr__(returned, "replay", NativeReplayContext(
                origin, prior_frames + (output,), inputs_signature, runtime_signature))
            return self.snapshot(returned)
        except BaseException as exc:
            record.update(status="failed", error=f"{type(exc).__name__}: {exc}")
            raise
        finally:
            receipt.write_text(json.dumps(record, indent=2) + "\n")

    def vjp(self, *args, **kwargs):
        raise RuntimeError("NativeHostTransition is value_only; full-host VJP is unavailable")

    def jvp(self, *args, **kwargs):
        raise RuntimeError("NativeHostTransition is value_only; full-host JVP is unavailable")
