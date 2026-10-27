from __future__ import annotations

import hashlib
import os
import shutil
import subprocess

import pytest

from harness import native_qnc_shared_face_overlay as overlay


def test_overlay_rejects_any_nonpinned_fortran_source():
    with pytest.raises(ValueError, match="SHA differs"):
        overlay.render(b"MODULE module_advect_em\nCONTAINS\nEND MODULE\n")


def test_overlay_only_adds_trace_calls_at_pinned_pd_boundaries(monkeypatch):
    source = b"""
MODULE module_advect_em
CONTAINS
SUBROUTINE advect_scalar_pd   (field)
  vert_order = config_flags%v_sca_adv_order
  CALL qnc_flux_trace_faces('RK3_PD_POST_LIMIT_FACES',its,ite,kts,kte,jts,jte, &
       fqx,fqy,fqz,fqxl,fqyl,fqzl,ph_low,flux_out, &
       msftx(221,63),msfty(221,63),rdx,rdy,rdzw(6))
  END IF
  i_start = its
     tendency(i,k,j) = tendency(i,k,j) - rdzw(k)*flux_delta
     CALL qnc_flux_trace_real('RK3_AFTER_Z',i,k,j,'TENDENCY',tendency(i,k,j))
     CALL qnc_flux_trace_real('RK3_AFTER_X',i,k,j,'TENDENCY',tendency(i,k,j))
     CALL qnc_flux_trace_real('RK3_AFTER_Y',i,k,j,'TENDENCY',tendency(i,k,j))
END SUBROUTINE advect_scalar_pd
"""
    monkeypatch.setattr(overlay, "BASE_SHA256", hashlib.sha256(source).hexdigest())
    output = overlay.render(source).decode()
    assert output.count("CALL qnc_shared_begin(") == 1
    assert output.count("CALL qnc_shared_capture(") == 1
    assert output.index("CALL qnc_shared_capture(") < output.index("  i_start = its")
    for stage in ("RK3_AFTER_Z", "RK3_AFTER_X", "RK3_AFTER_Y"):
        assert output.count(f"CALL qnc_shared_tendency('{stage}'") == 1
    assert output.count("tendency(i,k,j) = tendency(i,k,j) - rdzw(k)*flux_delta") == 1
    assert "# KDM6AD_QNC_SHARED_TRACE_V1" in output


def test_selected_owner_does_not_leak_into_next_scalar_call(tmp_path):
    if shutil.which("gfortran") is None:
        pytest.skip("gfortran is needed to check the Fortran trace writer")
    source = tmp_path / "writer.f90"
    source.write_text(
        "MODULE qnc_shared_test\n"
        " USE, INTRINSIC :: ISO_C_BINDING, ONLY: C_INT32_T\n"
        " INTEGER :: qnc_trace_rk=3, qnc_trace_step=20\n"
        " LOGICAL :: qnc_trace_selected=.TRUE.\n"
        + overlay._DECL + "\nCONTAINS\n" + overlay._HELPERS + "\nEND MODULE\n"
        "PROGRAM test_writer\n"
        " USE qnc_shared_test\n"
        " CALL qnc_shared_begin(1,235,1,40,1,142,39,1,235,1,283,-4,240,-4,288,20.0,20)\n"
        " CALL qnc_shared_tendency('RK3_AFTER_Z',221,6,63,1.0)\n"
        " qnc_trace_selected=.FALSE.\n"
        " qnc_trace_rk=0\n"
        " CALL qnc_shared_begin(1,235,1,40,1,142,39,1,235,1,283,-4,240,-4,288,20.0,20)\n"
        " CALL qnc_shared_tendency('RK3_AFTER_Z',221,6,63,99.0)\n"
        " CALL qnc_shared_real('RK3_AFTER_Z',221,6,63,'TENDENCY',99.0)\n"
        "END PROGRAM\n"
    )
    executable = tmp_path / "writer"
    env = os.environ.copy()
    if shutil.which("xcrun") is not None:
        sdk = subprocess.run(
            ["xcrun", "--sdk", "macosx", "--show-sdk-path"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        env["SDKROOT"] = sdk
    subprocess.run(
        ["gfortran", "-O0", "-fcheck=all", "-ffree-line-length-none", str(source), "-o", str(executable)],
        check=True, cwd=tmp_path, env=env, capture_output=True, text=True,
    )
    trace_dir = tmp_path / "trace"
    trace_dir.mkdir()
    env[overlay.TRACE_ENV] = str(trace_dir)
    subprocess.run([str(executable)], check=True, env=env, cwd=tmp_path, capture_output=True, text=True)
    lines = (trace_dir / "qnc_shared.tsv").read_text().splitlines()
    assert sum(line.startswith("CALL ") for line in lines) == 1
    values = [line for line in lines if line.startswith("VAL ")]
    assert values == ["VAL 1 RK3_AFTER_Z 221 6 63 TENDENCY f32 3F800000"]
