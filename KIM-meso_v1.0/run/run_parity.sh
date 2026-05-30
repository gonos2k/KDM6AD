#!/bin/bash
# KDM6 (mp=37) vs KDM6AD (mp=137) parity runner for a deterministic ideal case.
#
# Runs ideal.exe + wrf.exe twice — once per mp_physics — from the SAME namelist
# (only mp_physics differs). The case must have a DETERMINISTIC IC generator
# (no live `call random_seed`); otherwise the two ideal.exe runs draw different
# perturbations and the comparison is invalid (the harness frame-0 gate catches
# that). libtorch/libomp single-thread fences are exported for BOTH runs because
# wrf.exe loads libkdm6_c (hence libomp) at startup even when mp=37 never calls it.
#
# Usage: run_parity.sh <case-slug> [history_interval_min]
set -uo pipefail

export OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 MKL_NUM_THREADS=1
export OMP_THREAD_LIMIT=1 KMP_DUPLICATE_LIB_OK=TRUE GFORTRAN_ERROR_BACKTRACE=1

cd "$(dirname "$0")"
CASE="${1:?usage: run_parity.sh <case-slug> [hist_min]}"
HIST="${2:-2}"
RC_FINAL=0   # propagated to the script exit so failures aren't masked

# Clear stale renamed outputs from a prior invocation so the parity gate can
# never compare this run's output against a previous run's leftover file.
rm -f "wrfout.37.${CASE}.nc" "wrfout.137.${CASE}.nc"

# Frequent output to resolve the early seed + divergence onset.
sed -i.paritybak "s/^ history_interval .*/ history_interval                    = ${HIST},   ${HIST},   ${HIST},/" namelist.input

for MP in 37 137; do
  echo "=================== mp_physics = ${MP} ==================="
  sed -i.mpbak "s/^ mp_physics .*/ mp_physics                          = ${MP},     ${MP},     ${MP},/" namelist.input
  rm -f rsl.error.* rsl.out.* wrfinput_d01 wrfout_d01_*
  echo "  [ideal] mp=${MP} ..."
  mpirun -np 1 ../main/ideal.exe > ideal.${CASE}.${MP}.log 2>&1
  if [ ! -f wrfinput_d01 ]; then echo "  ERROR: ideal.exe produced no wrfinput (mp=${MP})"; tail -5 ideal.${CASE}.${MP}.log; RC_FINAL=1; continue; fi
  echo "  [wrf]   mp=${MP} ..."
  # Retry the intermittent libtorch/libomp init crash (SIGSEGV 139 / SIGABRT 134
  # at dylib load, BEFORE any integration — T11). Physics/CFL crashes (other rc)
  # are real and not retried.
  RC=0
  for wtry in 1 2 3 4; do
    rm -f rsl.error.0000
    mpirun -np 1 ../main/wrf.exe > wrf.${CASE}.${MP}.log 2>&1
    RC=$?
    # Retry ONLY a genuine libtorch-load INIT crash, identified by THREE conditions
    # together: (1) rc=139/134 (SIGSEGV/SIGABRT), (2) NO "SUCCESS COMPLETE WRF"
    # marker, and (3) NO "Timing for main" line — i.e. NO timestep ever completed,
    # so the crash was at dylib load BEFORE integration. A 139/134 that occurs
    # AFTER integration started (timestep lines present) is a REAL mid-run crash
    # and must NOT be retried; nor is a cosmetic post-success abort (marker present)
    # nor a non-139/134 crash (NaN/CFL).
    grep -q "SUCCESS COMPLETE WRF" rsl.error.0000 2>/dev/null && break
    if { [ $RC -eq 139 ] || [ $RC -eq 134 ]; } \
       && ! grep -q "Timing for main" rsl.error.0000 2>/dev/null; then
      echo "    init-crash (rc=${RC}, no integration started), retry ${wtry}"
      continue
    fi
    break
  done
  # Authoritative completion = the "SUCCESS COMPLETE WRF" marker in rsl.error,
  # NOT the exit code: a cosmetic shutdown SIGSEGV/SIGABRT (rc!=0) fires AFTER
  # success with data already on disk, while a real mid-run crash (NaN-fatal/CFL,
  # also rc!=0) never writes the marker. So RC alone is unreliable in BOTH
  # directions — keying off the marker avoids false-pass (crash + partial output)
  # and false-fail (cosmetic shutdown abort).
  COMPLETED=0
  grep -q "SUCCESS COMPLETE WRF" rsl.error.0000 2>/dev/null && COMPLETED=1
  OUT=$(ls -t wrfout_d01_* 2>/dev/null | head -1)
  if [ -n "${OUT}" ]; then
    mv "${OUT}" "wrfout.${MP}.${CASE}.nc"
    NF=$(ncdump -h "wrfout.${MP}.${CASE}.nc" 2>/dev/null | grep -oE "Time = UNLIMITED.*\([0-9]+ currently\)" | grep -oE "[0-9]+ currently" | grep -oE "[0-9]+")
    echo "  -> wrfout.${MP}.${CASE}.nc  (${NF:-?} frames, wrf rc=${RC}, completed=${COMPLETED})"
  else
    echo "  ERROR: no wrfout for mp=${MP} (wrf rc=${RC}); tail:"; tail -8 wrf.${CASE}.${MP}.log
    RC_FINAL=1
  fi
  if [ "${COMPLETED}" -ne 1 ]; then
    echo "  ERROR: mp=${MP} wrf.exe did NOT reach 'SUCCESS COMPLETE WRF' (rc=${RC}); crashed mid-integration (partial output is not a valid run)"
    RC_FINAL=1
  fi
done
echo "DONE ${CASE}"

# Gated parity check — assert completion via --expect-frames (run_minutes/HIST + IC
# frame) so a both-runs-aborted-at-the-same-frame case fails as INCOMPLETE. The
# gate's exit code is PROPAGATED to the script's exit so a failed verdict (or a
# run that produced no wrfout) is never masked as success.
RUNMIN=$(grep -oE "^ run_minutes *= *[0-9]+" namelist.input | grep -oE "[0-9]+" | head -1)
if [ -n "${RUNMIN}" ] && [ -f "wrfout.37.${CASE}.nc" ] && [ -f "wrfout.137.${CASE}.nc" ]; then
  EXPECT=$(( RUNMIN / HIST + 1 ))
  echo "=== parity gate (expect ${EXPECT} frames) ==="
  python3 /Users/yhlee/KDM6AD/kdm6_libtorch/tools/kdm6_parity.py \
      "wrfout.37.${CASE}.nc" "wrfout.137.${CASE}.nc" --case "${CASE}" --expect-frames "${EXPECT}"
  PRC=$?
  echo "parity gate exit=${PRC}"
  [ "${PRC}" -ne 0 ] && RC_FINAL="${PRC}"
else
  echo "ERROR: cannot run parity gate — missing wrfout(s) or run_minutes (a run failed)"
  RC_FINAL=1
fi

echo "run_parity.sh ${CASE} overall exit=${RC_FINAL}"
exit "${RC_FINAL}"
