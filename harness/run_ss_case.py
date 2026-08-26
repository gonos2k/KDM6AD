#!/usr/bin/env python3
from __future__ import annotations
import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


def replace_line(text: str, key: str, value: str) -> str:
    lines=[]
    done=False
    for line in text.splitlines():
        stripped=line.strip()
        # exact-key match: key must be followed by '=' (after optional spaces),
        # so 'history_interval' does NOT clobber 'history_interval_s'.
        if stripped.startswith(key) and stripped[len(key):].lstrip().startswith('='):
            prefix=line[:len(line)-len(line.lstrip())]
            lines.append(f"{prefix}{key:<36}= {value},")
            done=True
        else:
            lines.append(line)
    if not done:
        raise SystemExit(f"missing namelist key {key}")
    return "\n".join(lines)+"\n"


def set_or_insert(text: str, key: str, value: str, section: str = "&domains") -> str:
    """Set `key`, inserting it into `section` when the namelist does not carry it.

    `replace_line` REFUSES a missing key, which is right for keys the namelist is
    supposed to have -- a typo there should stop the run, not silently add a new
    setting. `nproc_x`/`nproc_y` are different: WRF chooses the decomposition
    itself unless told, so their absence is the normal state and inserting them
    is the point.
    """
    try:
        return replace_line(text, key, value)
    except SystemExit:
        pass
    lines, done = [], False
    for line in text.splitlines():
        lines.append(line)
        if not done and line.strip().lower().startswith(section):
            lines.append(f" {key:<36}= {value},")
            done = True
    if not done:
        raise SystemExit(f"cannot insert {key}: no {section} section in the namelist")
    return "\n".join(lines) + "\n"


def remove_keys(text: str, keys: set[str]) -> str:
    out=[]
    for line in text.splitlines():
        stripped=line.strip()
        # exact-key match (same predicate as replace_line): key must be immediately
        # followed by '=', so 'fogvis_clw_min' does NOT also drop 'fogvis_clw_min_gm3'.
        if any(stripped.startswith(key) and stripped[len(key):].lstrip().startswith('=')
               for key in keys):
            continue
        out.append(line)
    return "\n".join(out)+"\n"


def parse_proc_grid(rsl_text: str) -> str | None:
    """The decomposition WRF actually used, as `NXxNY`, from rsl.error.0000.

    `--proc-grid` only pre-checks that the two factors multiply to `--np`. WRF
    is free to do something else -- and a run whose grid is not the requested
    one is a different experiment wearing the requested one's directory name
    (owner review 9.5). Returns None when the lines are not there, which is
    reported as "not found" rather than as agreement.
    """
    import re
    x = re.search(r"[Nn]tasks in X\s+(\d+)", rsl_text)
    y = re.search(r"ntasks in Y\s+(\d+)", rsl_text)
    return f"{x.group(1)}x{y.group(1)}" if (x and y) else None


def build_child_env() -> dict:
    # Single-thread fence for strict-bitwise parity. KMP_DUPLICATE_LIB_OK is
    # intentionally NOT set here: it is caller-owned — a parent UNSET stays unset,
    # an explicit parent TRUE/FALSE is preserved verbatim. The runner never forces it.
    env=os.environ.copy()
    env.update({
        'OMP_NUM_THREADS':'1',
        'VECLIB_MAXIMUM_THREADS':'1',
        'MKL_NUM_THREADS':'1',
        'OMP_THREAD_LIMIT':'1',
        'GFORTRAN_ERROR_BACKTRACE':'1',
    })
    return env


def main() -> int:
    ap=argparse.ArgumentParser()
    # 37/137: legacy KDM6 Fortran / KDM6AD C++.
    # 237/337: conservative-interface-v1 corrected Fortran reference / C++ v2
    # (docs/FREEZE_LIFT_CONSERVATIVE_INTERFACE_V1.md, C4).
    ap.add_argument('--mp', choices=['37','137','237','337'], required=True)
    ap.add_argument('--minutes', type=int, default=10)
    ap.add_argument('--seconds', type=int, default=0,
                    help='extra run_seconds — step-granular runs (dt=20: 1 step = --minutes 0 --seconds 20)')
    ap.add_argument('--history', type=int, default=1)
    ap.add_argument('--history-s', type=int, default=None, dest='history_s',
                    help='history_interval_s (seconds). Effective output interval '
                         '= history_interval*60 + history_interval_s, so the base '
                         '=20 drifts +20s/frame and never lands on the run-end '
                         'time; pass 0 for EXACT hourly frames that include the '
                         'terminal state. Default: leave the namelist value.')
    ap.add_argument('--np', type=int, default=1,
                    help='MPI ranks; np>1 adds --mca btl self,tcp (Open MPI shm BTL SEGVs with libtorch-loaded ranks)')
    ap.add_argument('--label', default='smoke')
    ap.add_argument('--allow-runner-drift', action='store_true',
                    help='run even though this copy differs from the repository runner')
    ap.add_argument('--fixed-dt', action='store_true', help='Disable adaptive time step for parity smoke runs')
    ap.add_argument('--proc-grid', default=None, metavar='NXxNY',
                    help='force the MPI decomposition, e.g. 1x4, 2x2, 4x1. WRF '
                         'picks one itself otherwise, so the seam direction is '
                         'not a variable the caller controls -- and separating '
                         'a seam-direction effect from a rank-count one needs '
                         'the same np run with different grids '
                         '(OPEN_QUESTIONS_after_pr167, item 3).')
    ap.add_argument('--radt', type=int, default=None,
                    help='radiation call interval in minutes. For the NEGATIVE '
                         'CONTROL on the six-minute field-count jump: if that '
                         'jump is the first radiation call, it must move when '
                         'this does, and stay put if it does not.')
    args=ap.parse_args()

    # ARGUMENT VALIDATION BEFORE FILESYSTEM ACCESS. The grid check first lived
    # beside the namelist edit, so on a host without the namelist the run died
    # on a missing file and never reached it -- a guard that only fires where it
    # is least needed.
    proc_grid = None
    if args.proc_grid is not None:
        try:
            nx, ny = (int(v) for v in args.proc_grid.lower().split('x'))
        except ValueError:
            raise SystemExit(f"--proc-grid wants NXxNY, got {args.proc_grid!r}")
        if nx * ny != args.np:
            raise SystemExit(
                f"--proc-grid {args.proc_grid} is {nx * ny} ranks and --np is "
                f"{args.np}; a grid that does not multiply to the rank count is "
                f"silently ignored by WRF, which would make the control a null")
        proc_grid = (nx, ny)

    # THIS SCRIPT RUNS FROM BESIDE ITS CASE, not from the repository: it reads
    # `namelist.input` and launches `wrf.exe` from its own directory, so a case
    # keeps its own copy. That is the design, and it means the copy can fall
    # behind the repository's -- which it had, by 12 lines, so a run made today
    # silently used a version without the binary-hash recording added this
    # morning. Symlinking the two is not the fix: `resolve()` follows the link
    # and the script then looks for the case's files in the repository.
    #
    # So: say so, loudly, rather than pretend there is one file.
    run=Path(__file__).resolve().parent
    _repo_copy = Path("/Users/yhlee/KDM6AD-k/harness/run_ss_case.py")
    # EVERYTHING AFTER THE LOCK IS INSIDE A RESTORE SCOPE. The protecting try
    # used to open ~90 lines below, so a failure in between -- a namelist key
    # that will not substitute, a write that fails, mkdir on a full disk --
    # left the lock held AND the namelist rewritten, and the case needed a
    # manual repair for a run that never started (owner review 9.1).
    _restore_needed = False
    original = None
    nml = run/'namelist.input'
    try:
        import hashlib as _h
        mine = _h.sha256(Path(__file__).read_bytes()).hexdigest()
        if _repo_copy.exists() and _repo_copy.resolve() != Path(__file__).resolve():
            theirs = _h.sha256(_repo_copy.read_bytes()).hexdigest()
            _runner_state = ("match" if mine == theirs else "DRIFTED")
            if mine != theirs and not args.allow_runner_drift:
                # FAIL CLOSED. Warning and continuing is how the hash recording added
                # one morning was absent from that day's runs: a stale copy silently
                # lacks whatever self-check was just added, which is exactly the
                # check that would have caught the staleness (owner review 9.1).
                print(f"run_ss_case: this copy differs from the repository's.\n"
                      f"             here {mine[:12]}  repo {theirs[:12]}\n"
                      f"             Anything added to the repository copy -- new flags,\n"
                      f"             new provenance -- is NOT in this run.\n"
                      f"             cp {_repo_copy} {Path(__file__).resolve()}\n"
                      f"             or pass --allow-runner-drift to run anyway.",
                      file=sys.stderr)
                return 2
        else:
            # "we could not look" must not read as "we looked and it matched": the
            # canonical path is one host's, so elsewhere there is nothing to compare.
            mine = theirs = None
            _runner_state = "uncomparable-no-repo-copy"
        # ONE RUN PER CASE DIRECTORY. This rewrites `namelist.input`, deletes the
        # previous rsl/wrfout, runs, then restores. Two concurrent runs interleave
        # all four: each overwrites the other's namelist, deletes the other's
        # output, archives results produced under the wrong settings, and the second
        # to finish restores a namelist the first had already replaced. This repo
        # has already paid for one shared-mutable-state race (the compile-time
        # fixture); the lock is the same answer (owner review 9.3).
        _lock = run/'.ss-case-lock'
        try:
            _lock_fd = os.open(_lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            try:
                held = _lock.read_text().strip() or "(holder wrote no name)"
            except OSError:
                held = "(released while we were reporting it; try again)"
            print(f"run_ss_case: {_lock.name} is held by: {held}\n"
                  f"             This case directory takes one run at a time.\n"
                  f"             Wait, or remove the lock if that process is gone.",
                  file=sys.stderr)
            return 3
        with os.fdopen(_lock_fd, 'w') as _lf:
            _lf.write(f"pid {os.getpid()} mp{args.mp} {args.label} "
                      f"{args.minutes}min np{args.np}\n")

        import hashlib
        try:
            _exe_path = str((run/'wrf.exe').resolve())
            _exe_before = hashlib.sha256((run/'wrf.exe').read_bytes()).hexdigest()
        except OSError as e:
            _exe_path, _exe_before = str(run/'wrf.exe'), f'unavailable: {e}'

        original=nml.read_text()
        text=original
        text=remove_keys(text, {
            'qnn_land_mult', 'qnn_sea_mult',
            'fogvis_vis_consis_opt', 'fogvis_hydro_gate_opt', 'fogvis_hydro_min',
            'fogvis_clw_gate_opt', 'fogvis_clw_min', 'fogvis_ccn_aer_opt',
            'fogvis_ccn_ref_cm3', 'fogvis_ccn_rh_opt', 'fogvis_ccn_drh',
            'fogvis_ccn_rh_low_opt', 'fogvis_ccn_rh_low0', 'fogvis_ccn_rh_low_drh',
            'fogvis_ccn_rh_low_min', 'fogvis_ff_thresh', 'fogvis_hydro_wc0_gm3',
            'fogvis_hydro_dwc_gm3', 'fogvis_clw_wc0_gm3', 'fogvis_clw_dwc_gm3',
            'fogvis_ccn_beta_ref', 'fogvis_ccn_gamma', 'fogvis_ccn_rh0',
            'fogvis_ccn_rh_max',
        })
        for key,value in [
            ('run_days','0'),
            ('run_hours','0'),
            ('run_minutes',str(args.minutes)),
            ('run_seconds',str(args.seconds)),
            ('input_inname','"wrfinput_d<domain>"'),
            ('bdy_inname','"wrfbdy_d<domain>"'),
            ('auxinput24_inname','"wrfchainp_d<domain>"'),
            ('history_interval',str(args.history)),
            ('frames_per_outfile','1000'),
            ('mp_physics',args.mp),
            ('nio_tasks_per_group','0'),
            ('nio_groups','1'),
        ]:
            text=replace_line(text,key,value)
        if args.history_s is not None:
            text=replace_line(text, 'history_interval_s', str(args.history_s))
        if proc_grid is not None:
            text=set_or_insert(text, 'nproc_x', str(proc_grid[0]))
            text=set_or_insert(text, 'nproc_y', str(proc_grid[1]))
        if args.radt is not None:
            text=replace_line(text, 'radt', str(args.radt))
        if args.fixed_dt:
            text=replace_line(text, 'use_adaptive_time_step', '.false.')
            text=replace_line(text, 'step_to_output_time', '.false.')
        _restore_needed = True
        nml.write_text(text)

        stamp=time.strftime('%Y%m%d_%H%M%S')
        _np_tag = f"_np{args.np}" if args.np != 1 else ''
        _sec_tag = f"{args.seconds}s" if args.seconds else ''
        _rad_tag = f"_radt{args.radt}" if args.radt is not None else ''
        _grid_tag = f"_{args.proc_grid}" if args.proc_grid is not None else ''
        out=run/'runs'/f"mp{args.mp}_{args.label}_{args.minutes}min{_sec_tag}_hist{args.history}{_rad_tag}{_np_tag}{_grid_tag}_{stamp}"
        # PID, and exist_ok=False. The stamp resolves to one second, so two runs
        # started in the same second with the same arguments shared a directory and
        # interleaved their archives. The case lock above already serialises runs in
        # ONE case dir; this keeps the collision impossible rather than unlikely,
        # and makes it loud if it ever happens anyway (owner review 9.4).
        out = out.with_name(f"{out.name}_p{os.getpid()}")
        out.mkdir(parents=True, exist_ok=False)
        for pat in ['rsl.error.*','rsl.out.*','wrfout_d01_*','klfs_lc05_fcst.*','klfs_lc05_prcp.*','klfs_lc05_ocean.*','klfs_lc05_energy.*','kdm6_step1_*.bin','kdm6_driver_step1_*.bin','kdm6_upstream_*.bin']:
            for p in run.glob(pat):
                if p.is_file() or p.is_symlink():
                    p.unlink()
        # KDM6_SUBSTEP_DUMP per-substep/graupel parity dumps: the Fortran dumps use position='append', so
        # they accumulate (duplicate-record corruption) unless cleaned each run. Clean ONLY the current run's
        # own tree (mp37=KDM6 writes fort_*, mp137=KDM6AD writes cpp_*) — NEVER the other tree's, which the
        # cross-tree comparison still needs. No-op when the dump macro is off (no such files exist).
        # Fortran schemes (37 legacy, 237 conservative reference) write fort_*;
        # C++ schemes (137 legacy, 337 conservative v2) write cpp_*.
        _dump_prefix = 'fort' if args.mp in ('37','237') else 'cpp'
        for pat in [_dump_prefix + '_*.bin']:  # ALL own-tree dumps (append-mode; stale mixed-schema records corrupt readers)
            for p in run.glob(pat):
                if p.is_file() or p.is_symlink():
                    p.unlink()
        env=build_child_env()
        stdout=out/f"wrf_mp{args.mp}_{args.label}.stdout"
        proc=None
    except BaseException:
        # Restore what was touched, release, and re-raise unchanged.
        if _restore_needed and original is not None:
            nml.write_text(original)
        _lock.unlink(missing_ok=True)
        raise
    try:
        with stdout.open('w') as f:
            # Inner try/except is scoped to the SPAWN ONLY (mpirun/wrf.exe launch). A
            # missing/non-executable launcher raises OSError here → catch it, leave proc=None,
            # and fall through to the rc=127 fallback instead of a bare traceback. A nonzero
            # WRF exit is NOT an exception — it returns via proc.returncode.
            # NOTE: opening the stdout log (the `with` above) is deliberately OUTSIDE this
            # except — a log-open failure is a setup/IO error, not a launch failure, and must
            # surface as itself rather than be mislabeled and mapped to rc=127. Likewise the
            # provenance copy below is outside it so a copy error is not swallowed.
            try:
                mpi_cmd=['mpirun','-np',str(args.np)]
                if args.np > 1:
                    mpi_cmd += ['--mca','btl','self,tcp']
                proc=subprocess.run(mpi_cmd+[str(run/'wrf.exe')], cwd=run, env=env,
                                    stdout=f, stderr=subprocess.STDOUT, check=False)
            except OSError as e:
                # Record the launch failure in BOTH stderr and the run's own stdout log, so the
                # cause is visible from the run directory alone (rsl logs won't exist — no spawn).
                msg = f"run_ss_case: launch failed: {e}"
                print(msg, file=sys.stderr)
                print(msg, file=f)
        # Provenance: WHICH BINARY RAN. Comparing two runs assumes they came from
        # the same wrf.exe, and nothing recorded it -- so a comparison made days
        # apart, across a session that swapped binaries for diagnostic arms,
        # could not be shown to be a fair one afterwards. The hash was checked
        # by hand at every swap, which is evidence in a transcript and not in
        # the run. It is in the run now.
        # BEFORE AND AFTER. Hashing only after the run records whatever the file
        # is when the run ENDS, which is not necessarily what executed: a
        # symlink retargeted or a binary rebuilt mid-run would be recorded as
        # the one that ran (owner review 9.2). Both are written, with the
        # resolved path, and a mismatch is stated rather than silently resolved.
        try:
            h_after = hashlib.sha256((run/'wrf.exe').read_bytes()).hexdigest()
        except OSError as e:
            h_after = f'unavailable: {e}'
        (out/'wrf_exe_sha256').write_text(
            f"{h_after}\n"
            f"before {_exe_before}\n"
            f"after  {h_after}\n"
            f"stable {'yes' if _exe_before == h_after else 'NO -- the binary changed during the run'}\n"
            f"path   {_exe_path}\n")
        # 9.5: WHAT WRF ACTUALLY DID, not what was asked for. `--proc-grid`
        # only pre-checks the arithmetic; WRF prints the decomposition it chose,
        # and a run whose grid is not the requested one is not the experiment
        # (owner review 9.5). Recorded either way; a mismatch is named.
        try:
            _r0 = next(iter(sorted(run.glob('rsl.error.0000'))), None)
            _actual = parse_proc_grid(
                _r0.read_text(errors='replace')[:20000]) if _r0 else None
        except OSError:
            _actual = None
        # And the runner's own identity, so "which script produced this" is a
        # fact in the run rather than a memory. `uncomparable` is written as
        # itself: on a host without the repository there is nothing to compare.
        (out/'runner_sha256').write_text(
            f"runner    {mine}\n"
            f"canonical {theirs if theirs else '(no repository copy on this host)'}\n"
            f"state     {_runner_state}\n")
        _requested = args.proc_grid
        (out/'proc_grid').write_text(
            f"requested {_requested or '(unset -- WRF chose)'}\n"
            f"actual    {_actual or '(not found in rsl.error.0000)'}\n"
            f"matches   {'yes' if (_actual and _requested and _actual == _requested) else ('n/a' if not _requested else 'NO -- this run is not the requested decomposition')}\n"
            f"np        {args.np}\n")
        # Provenance: archive the EXACT namelist used (before we restore the pristine one).
        if proc is not None:
            rsl=[p for pat in ('rsl.error.*','rsl.out.*') for p in run.glob(pat)]
            for src in [nml]+rsl:
                if src.exists(): shutil.copy2(src, out/src.name)
    finally:
        # ORDER. Restore, archive, and only then release: the outputs are still
        # in the case directory until they are copied, so a waiter that started
        # at the release would delete them as its own stale files. Releasing
        # first is the same fail-open the fixture lock was fixed for.
        # Restore the pristine working namelist so the next run / git-diff is not polluted
        # by this run's mutations (see the §10 namelist-race lesson: stale working-dir namelist
        # → truncated runs → phantom parity failures).
        nml.write_text(original)
        # THE RELEASE MUST SURVIVE A FAILING ARCHIVE. The copy loop is the only
        # step here that touches a filesystem it does not control -- a full
        # disk, a vanishing file -- and the unlink sat AFTER it, so one raised
        # copy left the lock held for a run that had already finished. Found by
        # injecting an OSError into shutil.copy2 (owner review 9.1, the half of
        # it that is not in setup).
        try:
            for pat in ['wrfout_d01_*','klfs_lc05_fcst.*','klfs_lc05_prcp.*','klfs_lc05_ocean.*','klfs_lc05_energy.*','kdm6_step1_*.bin','kdm6_driver_step1_*.bin','kdm6_upstream_*.bin']:
                for src in run.glob(pat):
                    if src.is_file(): shutil.copy2(src, out/src.name)
        finally:
            _lock.unlink(missing_ok=True)
    # THE EXPERIMENT'S VERDICT IS NOT THE MODEL'S EXIT CODE. A run whose binary
    # changed under it, or whose processor grid is not the one requested, is
    # recorded as such -- and a pipeline reading only the exit code took it as a
    # success anyway (owner review 9.2). The verdict is written beside the
    # metadata and, when the experiment is invalid, returned.
    _invalid = []
    if _exe_before != h_after:
        _invalid.append("binary_changed_during_run")
    if _requested and _actual and _actual != _requested:
        _invalid.append("processor_grid_mismatch")
    if _requested and not _actual:
        _invalid.append("processor_grid_not_found")
    if _runner_state == "DRIFTED":
        _invalid.append("runner_drifted")
    import json as _json
    (out/'experiment_valid.json').write_text(_json.dumps({
        "experiment_valid": not _invalid,
        "invalid_reasons": _invalid,
        "requested_proc_grid": _requested,
        "actual_proc_grid": _actual,
        "runner_state": _runner_state,
    }, indent=1) + "\n")

    # proc is None only if the launch raised OSError above (caught) → report 127
    # (command-not-found convention); otherwise use WRF's real exit code.
    rc = proc.returncode if proc is not None else 127
    (out/'exit_code').write_text(str(rc)+'\n')
    print(out)
    if _invalid and rc == 0:
        print(f"run_ss_case: the MODEL succeeded and the EXPERIMENT did not: "
              f"{_invalid}\n"
              f"             see {out.name}/experiment_valid.json",
              file=sys.stderr)
        return 4
    return rc

if __name__ == '__main__':
    raise SystemExit(main())
