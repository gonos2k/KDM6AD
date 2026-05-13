#!/bin/bash
# Canonical launch wrapper for KDM6AD slot-137 wrf.exe runs.
#
# Why env vars: libtorch_cpu.dylib pulls LLVM libomp into the WRF process.
# libomp reads its thread-pool config at *dylib load time* (before any
# kdm6_step_c call). Without these env vars set in the parent shell, libomp
# auto-spawns workers and:
#   - SIGTRAPs in ra_init prologue at first parallel region (G1 host wiring), AND
#   - even when at::set_num_threads(1) is enforced via the libkdm6_c dylib
#     constructor + dlsym fence, downstream wrfout writes fail to flush
#     (frames written report SUCCESS but contain only netCDF FillValue).
#
# The dylib's __attribute__((constructor)) sets these via setenv(...,0)
# (no-overwrite), but that is too late: libomp has already initialized by
# the time libkdm6_c loads (libtorch_cpu loads first as its dependency).
# The shell-level export below is the only reliable single-thread fence.
#
# Both layers (env vars + dylib fence) are kept as defense in depth.

set -euo pipefail

export OMP_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export MKL_NUM_THREADS=1
export OMP_THREAD_LIMIT=1
export KMP_DUPLICATE_LIB_OK=TRUE
export GFORTRAN_ERROR_BACKTRACE=1

# Required: regenerate wrfinput from current namelist before each run, since
# state field allocation can differ across mp_physics changes (slot 37 ↔ 137).
rm -f rsl.error.0000 rsl.out.0000 wrfinput_d01 wrfout_d01_*

cd "$(dirname "$0")"
mpirun -np 1 ../main/ideal.exe > rsl.out.ideal 2>&1
# T12 reversal note (2026-05-12): direct ../main/wrf.exe crashes after step 1
# on this stack. Codex's mpirun-only hypothesis was based on an lldb test that
# did not reproduce. mpirun -np 1 is required for runtime stability — the
# post-success shutdown SIGSEGV/SIGABRT is cosmetic (data is on disk before
# the abort fires).
mpirun -np 1 ../main/wrf.exe > rsl.out.stderr 2>&1
