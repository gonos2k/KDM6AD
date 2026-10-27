from __future__ import annotations

import hashlib

import pytest

from harness import native_qnc_state7_overlay as overlay


def test_state7_overlay_rejects_source_drift():
    with pytest.raises(ValueError, match="source SHA differs"):
        overlay.render(b"SUBROUTINE solve_em\nEND SUBROUTINE\n")


def test_state7_overlay_changes_trace_selection_without_rk_arithmetic(monkeypatch):
    anchors = "\n".join(old for old, _ in overlay._REPLACEMENTS)
    source = (
        anchors + "\n"
        "CALL kdm6ad_upnc_trace('RKSCALAR_PD_BEFORE', grid%itimestep, rk_step, &\n"
        "CALL kdm6ad_upnc_trace('RKSCALAR_PD_AFTER', grid%itimestep, rk_step, &\n"
        "CALL kdm6ad_upnc_trace('RKSCALAR_BEFORE', grid%itimestep, rk_step, &\n"
        "CALL kdm6ad_upnc_trace('RKSCALAR_AFTER', grid%itimestep, rk_step, &\n"
        "scalar(i,k,j,im) = ((c1(k)*muold(i)+c2(k))*scalar(i,k,j,im)+dt*tendency(i,k,j))/denominator\n"
    ).encode()
    monkeypatch.setattr(overlay, "BASE_SHA256", hashlib.sha256(source).hexdigest())
    output = overlay.render(source).decode()
    assert "KDM6AD_UPNC_NTARGET = 7" in output
    assert output.count("CALL kdm6ad_upnc_trace('POST_SCALAR_BDY'") == 1
    assert "KDM6AD_QNC_STATE7_TRACE_DIR" in output
    assert "# KDM6AD_QNC_STATE7_TRACE_V2" in output
    assert output.count("scalar(i,k,j,im) = ((c1(k)*muold(i)+c2(k))*scalar(i,k,j,im)+dt*tendency(i,k,j))/denominator") == 1
