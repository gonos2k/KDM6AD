from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]


def test_finish_stages_are_clipped_to_each_target_owners_k_bounds(tmp_path):
    """Finish's wider storage bounds must not add a stage-40 mass-level row."""
    gfortran = shutil.which("gfortran")
    cc = shutil.which("cc")
    if gfortran is None or cc is None:
        pytest.skip("Fortran/C compilers unavailable for owner-bound fixture")

    stub = tmp_path / "setter.c"
    stub.write_text(
        "void kdm6_moment_trace_context_c(int a,int b,int c,int d,int e,int f,int g,int h) "
        "{ (void)a;(void)b;(void)c;(void)d;(void)e;(void)f;(void)g;(void)h; }\n",
        encoding="utf-8",
    )
    program = tmp_path / "owner_bounds.f90"
    program.write_text(
        """program owner_bounds
use iso_c_binding, only: c_double, c_float
use kdm6ad_moment_trace_v2, only: moment_trace_begin_call, moment_trace_finish_values
implicit none
real(c_float) :: qc(154:222,1:4,24:64), nc(154:222,1:4,24:64)
integer :: call_id
integer :: i, k, j
do j=24,64
  do k=1,4
    do i=154,222
      qc(i,k,j)=real(100000*i+100*k+j,c_float)
      nc(i,k,j)=-qc(i,k,j)
    end do
  end do
end do
call_id=moment_trace_begin_call(3,154,156,1,2,24,27,3,2,4,20.0_c_double,10.0_c_double,10.0_c_double)
if (call_id /= 1) error stop 1
call_id=moment_trace_begin_call(3,220,222,2,3,62,64,3,2,3,20.0_c_double,10.0_c_double,10.0_c_double)
if (call_id /= 2) error stop 2
call moment_trace_finish_values('ZERO_OUT_PRE',3,154,222,1,4,24,64,154,222,1,4,24,64,qc,nc)
call moment_trace_finish_values('MOMENTS_PRE',3,154,222,1,4,24,64,154,222,1,4,24,64,qc,nc)
call moment_trace_finish_values('MOMENTS_POST',3,154,222,1,4,24,64,154,222,1,4,24,64,qc,nc)
end program
""",
        encoding="utf-8",
    )
    module_object = tmp_path / "moment_trace.o"
    setter_object = tmp_path / "setter.o"
    binary = tmp_path / "owner_bounds"
    subprocess.run(
        [gfortran, "-ffp-contract=off", "-c", "-J" + str(tmp_path),
         str(ROOT / "harness/native_trace/kdm6ad_moment_trace_v2.f90"), "-o", str(module_object)],
        check=True,
        capture_output=True,
    )
    subprocess.run([cc, "-c", str(stub), "-o", str(setter_object)], check=True, capture_output=True)
    runtime_link = []
    if sys.platform == "darwin":
        sdk = subprocess.run(
            ["xcrun", "--show-sdk-path"], check=True, capture_output=True, text=True
        ).stdout.strip()
        runtime_link = ["-Wl,-syslibroot," + sdk, "-L" + sdk + "/usr/lib"]
    subprocess.run(
        [gfortran, "-ffp-contract=off", "-ffree-line-length-none", "-I" + str(tmp_path),
         str(program), str(module_object), str(setter_object), *runtime_link, "-o", str(binary)],
        check=True,
        capture_output=True,
    )
    trace_dir = tmp_path / "trace"
    trace_dir.mkdir()
    subprocess.run(
        [str(binary)],
        env={**os.environ, "KDM6AD_MOMENT_TRACE_V2_DIR": str(trace_dir)},
        check=True,
        capture_output=True,
    )

    lines = (trace_dir / "host.hex").read_text(encoding="utf-8").splitlines()
    values = [line.split() for line in lines if line.startswith("VAL ")]
    for stage in ("ZERO_OUT_PRE", "MOMENTS_PRE", "MOMENTS_POST"):
        rows = [row for row in values if row[2] == stage]
        actual = {(int(row[1]), int(row[3]), int(row[4]), int(row[5]), row[7]) for row in rows}
        expected = {
            (1, 155, 1, 25, "QC"), (1, 155, 1, 25, "NC"),
            (1, 155, 2, 25, "QC"), (1, 155, 2, 25, "NC"),
            (2, 221, 2, 63, "QC"), (2, 221, 2, 63, "NC"),
            (2, 221, 3, 63, "QC"), (2, 221, 3, 63, "NC"),
        }
        assert actual == expected
        assert all(row[6] == "f32" for row in rows)
