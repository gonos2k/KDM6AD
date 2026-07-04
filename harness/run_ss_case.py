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


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--mp', choices=['37','137'], required=True)
    ap.add_argument('--minutes', type=int, default=10)
    ap.add_argument('--history', type=int, default=1)
    ap.add_argument('--label', default='smoke')
    ap.add_argument('--fixed-dt', action='store_true', help='Disable adaptive time step for parity smoke runs')
    args=ap.parse_args()

    run=Path(__file__).resolve().parent
    nml=run/'namelist.input'
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
        ('run_seconds','0'),
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
    if args.fixed_dt:
        text=replace_line(text, 'use_adaptive_time_step', '.false.')
        text=replace_line(text, 'step_to_output_time', '.false.')
    nml.write_text(text)

    stamp=time.strftime('%Y%m%d_%H%M%S')
    out=run/'runs'/f"mp{args.mp}_{args.label}_{args.minutes}min_hist{args.history}_{stamp}"
    out.mkdir(parents=True, exist_ok=True)
    for pat in ['rsl.error.0000','rsl.out.0000','rsl.out.stderr','wrfout_d01_*','klfs_lc05_fcst.*','klfs_lc05_prcp.*','klfs_lc05_ocean.*','klfs_lc05_energy.*','kdm6_step1_*.bin','kdm6_driver_step1_*.bin','kdm6_upstream_*.bin']:
        for p in run.glob(pat):
            if p.is_file() or p.is_symlink():
                p.unlink()
    # KDM6_SUBSTEP_DUMP per-substep/graupel parity dumps: the Fortran dumps use position='append', so
    # they accumulate (duplicate-record corruption) unless cleaned each run. Clean ONLY the current run's
    # own tree (mp37=KDM6 writes fort_*, mp137=KDM6AD writes cpp_*) — NEVER the other tree's, which the
    # cross-tree comparison still needs. No-op when the dump macro is off (no such files exist).
    _dump_prefix = 'fort' if args.mp == '37' else 'cpp'
    for pat in [_dump_prefix + '_*.bin']:  # ALL own-tree dumps (append-mode; stale mixed-schema records corrupt readers)
        for p in run.glob(pat):
            if p.is_file() or p.is_symlink():
                p.unlink()
    env=os.environ.copy()
    env.update({
        'OMP_NUM_THREADS':'1',
        'VECLIB_MAXIMUM_THREADS':'1',
        'MKL_NUM_THREADS':'1',
        'OMP_THREAD_LIMIT':'1',
        'KMP_DUPLICATE_LIB_OK':'TRUE',
        'GFORTRAN_ERROR_BACKTRACE':'1',
    })
    stdout=out/f"wrf_mp{args.mp}_{args.label}.stdout"
    proc=None
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
                proc=subprocess.run(['mpirun','-np','1',str(run/'wrf.exe')], cwd=run, env=env,
                                    stdout=f, stderr=subprocess.STDOUT, check=False)
            except OSError as e:
                print(f"run_ss_case: launch failed: {e}", file=sys.stderr)
        # Provenance: archive the EXACT namelist used (before we restore the pristine one).
        if proc is not None:
            for src in [nml, run/'rsl.error.0000', run/'rsl.out.0000']:
                if src.exists(): shutil.copy2(src, out/src.name)
    finally:
        # Restore the pristine working namelist so the next run / git-diff is not polluted
        # by this run's mutations (see the §10 namelist-race lesson: stale working-dir namelist
        # → truncated runs → phantom parity failures).
        nml.write_text(original)
    for pat in ['wrfout_d01_*','klfs_lc05_fcst.*','klfs_lc05_prcp.*','klfs_lc05_ocean.*','klfs_lc05_energy.*','kdm6_step1_*.bin','kdm6_driver_step1_*.bin','kdm6_upstream_*.bin']:
        for src in run.glob(pat):
            if src.is_file(): shutil.copy2(src, out/src.name)
    # proc is None only if the launch raised OSError above (caught) → report 127
    # (command-not-found convention); otherwise use WRF's real exit code.
    rc = proc.returncode if proc is not None else 127
    (out/'exit_code').write_text(str(rc)+'\n')
    print(out)
    return rc

if __name__ == '__main__':
    raise SystemExit(main())
