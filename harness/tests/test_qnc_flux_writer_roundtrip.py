from __future__ import annotations

import os
import shutil
import subprocess
import sys

import pytest

from harness.native_qnc_flux_advect_overlay import _DECL, _HELPERS
from harness.replay_qnc_flux_limiter_trace import (
    FACE_NEIGHBORS_IKJ,
    TARGET_IKJ,
    read_qnc_flux_trace,
)


def _stub_source() -> str:
    return f"""MODULE qnc_flux_stub
{_DECL}
CONTAINS
{_HELPERS}
END MODULE qnc_flux_stub

SUBROUTINE nl_get_time_step(domain,step)
  INTEGER,INTENT(IN) :: domain
  INTEGER,INTENT(OUT) :: step
  step=20
END SUBROUTINE nl_get_time_step

PROGRAM writer_smoke
  USE qnc_flux_stub
  IMPLICIT NONE
  INTEGER,PARAMETER :: its=220,ite=222,kts=5,kte=7,jts=62,jte=64
  REAL :: fqx(its-1:ite+2,kts:kte,jts-1:jte+2)
  REAL :: fqy(its-1:ite+2,kts:kte,jts-1:jte+2)
  REAL :: fqz(its-1:ite+2,kts:kte,jts-1:jte+2)
  REAL :: fqxl(its-1:ite+2,kts:kte,jts-1:jte+2)
  REAL :: fqyl(its-1:ite+2,kts:kte,jts-1:jte+2)
  REAL :: fqzl(its-1:ite+2,kts:kte,jts-1:jte+2)
  REAL :: ph_low(its-1:ite+2,kts:kte,jts-1:jte+2)
  REAL :: flux_out(its-1:ite+2,kts:kte,jts-1:jte+2)
  INTEGER :: i,k,j
  fqx=1.; fqy=2.; fqz=3.; fqxl=4.; fqyl=5.; fqzl=6.
  ph_low=7.; flux_out=8.
  CALL qnc_flux_trace_set_context(1,1,1,6.6666665,.TRUE.)
  CALL qnc_flux_trace_rk1('RK1_START',221,6,63,-999.,0.,0.,0.)
  CALL qnc_flux_trace_set_context(1,1,1,6.6666665,.FALSE.)
  CALL qnc_flux_trace_rk1('RK1_START',221,6,63,0.,0.,0.,0.)
  CALL qnc_flux_trace_rk1('RK1_AFTER_Y',221,6,63,1.,2.,3.,4.)
  CALL qnc_flux_trace_rk1('RK1_AFTER_X',221,6,63,2.,3.,4.,5.)
  CALL qnc_flux_trace_rk1('RK1_AFTER_Z',221,6,63,3.,4.,5.,6.)
  CALL qnc_flux_trace_set_context(1,1,3,20.,.FALSE.)
  CALL qnc_flux_trace_real('RK3_PD_PRE_LIMIT',221,6,63,'TENDENCY',0.)
  CALL qnc_flux_trace_faces('RK3_PD_PRE_LIMIT',its,ite,kts,kte,jts,jte, &
       fqx,fqy,fqz,fqxl,fqyl,fqzl,ph_low,flux_out,1.,1.,1.,1.,1.)
  DO j=62,64
    DO k=5,7
      DO i=220,222
        IF (ABS(i-221)+ABS(k-6)+ABS(j-63).LE.1) &
          CALL qnc_flux_trace_limit(i,k,j,7.,8.,1.,.FALSE.)
      END DO
    END DO
  END DO
  CALL qnc_flux_trace_faces('RK3_PD_POST_LIMIT_FACES',its,ite,kts,kte,jts,jte, &
       fqx,fqy,fqz,fqxl,fqyl,fqzl,ph_low,flux_out,1.,1.,1.,1.,1.)
  CALL qnc_flux_trace_real('RK3_AFTER_Z',221,6,63,'TENDENCY',-1.)
  CALL qnc_flux_trace_real('RK3_AFTER_X',221,6,63,'TENDENCY',-2.)
  CALL qnc_flux_trace_real('RK3_AFTER_Y',221,6,63,'TENDENCY',-3.)
END PROGRAM writer_smoke
"""


def test_generated_fortran_writer_roundtrips_complete_trace(tmp_path):
    compiler = shutil.which("gfortran")
    if compiler is None:
        pytest.skip("gfortran is unavailable for the isolated writer stub")
    source = tmp_path / "writer_stub.f90"
    executable = tmp_path / "writer_stub"
    output_dir = tmp_path / "trace"
    output_dir.mkdir()
    source.write_text(_stub_source(), encoding="utf-8")
    compile_env = os.environ.copy()
    if sys.platform == "darwin" and not compile_env.get("SDKROOT"):
        sdk = subprocess.run(
            ["xcrun", "--sdk", "macosx", "--show-sdk-path"],
            check=False,
            capture_output=True,
            text=True,
        )
        if sdk.returncode == 0 and sdk.stdout.strip():
            compile_env["SDKROOT"] = sdk.stdout.strip()
    subprocess.run(
        [compiler, "-ffree-form", "-ffree-line-length-none", str(source), "-o", str(executable)],
        check=True,
        capture_output=True,
        text=True,
        env=compile_env,
    )
    env = os.environ.copy()
    env["KDM6AD_QNC_FLUX_TRACE_DIR"] = str(output_dir)
    subprocess.run([str(executable)], check=True, capture_output=True, text=True, env=env)

    trace = read_qnc_flux_trace(output_dir / "qnc_flux.tsv")
    assert trace.protocol_version == 2
    assert len(trace.groups) == 1
    group = trace.select_qnc_scalar_group()
    assert len(group.values) == 77
    assert group.at(1, "RK1_START", "TENDENCY").value == 0.0
    assert group.at(3, "RK3_PD_PRE_LIMIT", "TENDENCY").value == 0.0
    assert set(FACE_NEIGHBORS_IKJ).issubset({
        (key[3], key[4], key[5]) for key in group.values if key[2] == "RK3_PD_LIMIT_CELL"
    })
    assert all((key[3], key[4], key[5]) == TARGET_IKJ for key in group.values if key[2] != "RK3_PD_LIMIT_CELL")
    assert group.at(3, "RK3_PD_POST_LIMIT_FACES", "DT_STEP").value == 20.0
