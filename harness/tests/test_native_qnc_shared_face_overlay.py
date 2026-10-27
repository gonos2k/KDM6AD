from __future__ import annotations

import hashlib

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
