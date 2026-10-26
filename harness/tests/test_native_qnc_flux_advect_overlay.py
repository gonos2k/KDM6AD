from __future__ import annotations

import pytest

from harness import native_qnc_flux_advect_overlay as overlay


def test_ordinary_trace_brackets_the_executed_directional_updates():
    source = """  horizontal_order_test : IF( horz_order == 6 ) THEN
  ELSE IF( horz_order == 5 ) THEN
            tendency(i,k,j-1) = tendency(i,k,j-1) - mrdy*(fqy(i,k,jp1)-fqy(i,k,jp0))
            tendency(i,k,j) = tendency(i,k,j) - mrdx*(fqx(i+1,k)-fqx(i,k))
   ELSE IF( horz_order == 4 ) THEN
   ELSE IF (vert_order == 3) THEN
            tendency(i,k,j)=tendency(i,k,j)-rdzw(k)*(vflux(i,k+1)-vflux(i,k))
   ELSE IF (vert_order == 2) THEN
"""
    result = overlay._instrument_ordinary(source)
    assert result.index("RK1_START") < result.index("horizontal_order_test")
    for assignment, stage in (
        ("tendency(i,k,j-1) = tendency(i,k,j-1) - mrdy", "RK1_AFTER_Y"),
        ("tendency(i,k,j) = tendency(i,k,j) - mrdx", "RK1_AFTER_X"),
        ("tendency(i,k,j)=tendency(i,k,j)-rdzw", "RK1_AFTER_Z"),
    ):
        assert result.index(assignment) < result.index(stage)
        assert result.count(assignment) == 1


def test_pd_trace_keeps_prelimit_faces_before_the_limiter_sweep():
    source = """   DO j=j_start, j_end
   DO k=kts, ktf
   DO i=i_start, i_end
     IF( flux_out(i,k,j) .gt. ph_low(i,k,j) ) THEN
       scale = max(0.,ph_low(i,k,j)/(flux_out(i,k,j)+eps))
     END IF
     if (s15_here) then
     endif

   ENDDO
   ENDDO
   ENDDO

   END IF
  i_start = its
     if (s15_here) call s15_emit_axis
     if (s15_here) call s15_emit_axis
     if (s15_here) call s15_emit_axis
"""
    result = overlay._instrument_pd(source)
    assert result.index("RK3_PD_PRE_LIMIT") < result.index("IF( flux_out(i,k,j)")
    assert result.index("CALL qnc_flux_trace_limit") > result.index("scale = max")
    assert result.index("RK3_PD_POST_LIMIT_FACES") > result.index("   END IF")
    assert [result.index(stage) for stage in ("RK3_AFTER_Z", "RK3_AFTER_X", "RK3_AFTER_Y")] == sorted(
        result.index(stage) for stage in ("RK3_AFTER_Z", "RK3_AFTER_X", "RK3_AFTER_Y")
    )
    assert result.count("scale = max(0.,ph_low(i,k,j)/(flux_out(i,k,j)+eps))") == 1


def test_overlay_rejects_duplicate_or_missing_source_anchors():
    with pytest.raises(ValueError, match="expected one source anchor"):
        overlay._insert_once("abc abc", "abc", "new")
    with pytest.raises(ValueError, match="expected one source anchor"):
        overlay._insert_once("abc", "missing", "new")
