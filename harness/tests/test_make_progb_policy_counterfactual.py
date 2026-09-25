from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from make_progb_policy_counterfactual import _midpoint_policy, _retention_policy
from make_progb_validity_capture import _add_slope_events


def _policy_stub() -> str:
    return """SUBROUTINE ProgB_param(
  REAL, DIMENSION( its:ite , kts:kte),INTENT(OUT)   :: rhox
  REAL, DIMENSION( its:ite , kts:kte),INTENT(OUT)   :: cmg,pidn0g
  REAL, DIMENSION( its:ite , kts:kte),INTENT(OUT)   :: avtg,pvtg,precg2
  REAL, DIMENSION( its:ite , kts:kte),INTENT(OUT)   :: bvtg,bvtg1,bvtg2,bvtg3,bvtg4,rslopegbmax,&
                                                       g1pbg,g3pbg,g4pbg,g5pbgo2,g1pdgbgmg,dgbgmug1
  LOGICAL :: capture_active,capture_rhox_written,capture_cmg_written, &
       capture_pidn0g_written,capture_params_written,capture_trace_seen
      do k = kts, kte
! S10_CAPTURE_BEGIN:progb_cell_flags
#ifdef KDM6_PROGB_VALIDITY_CAPTURE
        do i = its, ite
#ifdef KDM6_PROGB_VALIDITY_CAPTURE
          capture_active = .false.
          capture_rhox_written = .false.
          capture_cmg_written = .false.
          capture_pidn0g_written = .false.
          capture_params_written = .false.
          if (k.eq.kts .and. i.eq.its) capture_trace_seen = .false.
          capture_rhox_assigned(i,k) = .false.
          capture_cmg_assigned(i,k) = .false.
          capture_pidn0g_assigned(i,k) = .false.
          capture_params_assigned(i,k) = .false.
#endif
     if (qrs(i,k,3).gt. qcrmin .or. brs(i,k).gt. brs_min) then
#else
        do i = its, ite
     if (qrs(i,k,3).gt. qcrmin .or. brs(i,k).gt. brs_min) then
#endif
! S10_CAPTURE_END:progb_cell_flags
        rhox(i,k) = qrs(i,k,3)/brs(i,k)
        if (rhox(i,k).ge. rho_min .and. rhox(i,k).le. rho_max) then
        brs(i,k)  = qrs(i,k,3)/rhox(i,k)
        cmg(i,k) = pi*rhox(i,k)/6
        pidn0g(i,k) = cmg(i,k)*n0g*g1pdgmg/g1pmg
        endif
        endif
      endif
! S10_CAPTURE_BEGIN:progb_cmg_read
#ifdef KDM6_PROGB_VALIDITY_CAPTURE
         if (capture_enabled) then
           write(*,*) 'S10CMG'
         endif
#endif
! S10_CAPTURE_END:progb_cmg_read
         if (cmg(i,k).gt. 0) then
           avtg(i,k)=1.
           bvtg(i,k)=1.
           rslopegbmax(i,k)=1.
           pvtg(i,k)=1.
           precg2(i,k)=1.
         endif
        enddo
      enddo
END subroutine ProgB_param
"""


def test_retention_variant_changes_only_prog_b_physical_output_intents():
    result, contract = _retention_policy(_policy_stub())
    assert result.count("INTENT(INOUT)") == 4
    assert result.count("INTENT(OUT)") == 0
    assert contract["inactive_rule"].startswith("retain the latest current-loop value")
    assert contract["changes_qg_or_brs_inside_ProgB"] is False
    assert "i,k,0,qrs(i,k,3),retention_brs_before" in result
    assert "i,k,3,qrs(i,k,3),retention_brs_before" in result


def test_midpoint_variant_seeds_all_outputs_and_logs_the_explicit_volume_delta():
    result, contract = _midpoint_policy(_policy_stub())
    assert "rhox(i,k) = 0." in result
    assert "pvtg(i,k) = 0." in result
    assert "capture_rhox_assigned(i,k) = .true." in result
    assert "rhox(i,k) = rho_mid" in result
    assert "brs(i,k) = qrs(i,k,3)/rho_mid" in result
    assert "brs(i,k) = 0." in result
    assert "'S10VOL'" in result
    assert "policy_gate_active = qrs(i,k,3).gt.qcrmin .or. brs(i,k).gt.brs_min" in result
    assert "if (.not.policy_gate_active) then" in result
    assert "i,k,0,qrs(i,k,3),policy_brs_before" in result
    assert "merge(1,2,qrs(i,k,3).gt.0.)" in result
    assert "policy_delta_brs = brs(i,k)-policy_brs_before" in result
    assert contract["not_approved"] is True
    assert contract["rho_mid_kg_m3"] == 400.0
    assert contract["inactive_gate"].startswith("qg<=qcrmin")
    assert contract["active_branch_changed"] is False
    assert "qg mass is unchanged" in contract["state_change"]


def test_slope_capture_records_defined_shape_and_velocity_at_fixed_witnesses():
    source = "".join(
        "call slope_kdm6(\n  qrs,qci,nrs,nci,den,denfac,t,rslope,\n"
        "  rslopeb,rslope2,rslope3,rslopemu,rsloped,vt,vtn,its,ite,kts,kte,\n"
        "  qmin,pidn0g,pvtg,bvtg,rslopegbmax)\n"
        for _ in range(7)
    )
    instrumented = _add_slope_events(source)
    assert instrumented.count("'S10SHAPE'") == 14
    assert "qrs_tmp(i,k,3),brs(i,k),rhox(i,k),cmg(i,k)" in instrumented
    assert "rslopegbmax(i,k),rslope(i,k,3)" in instrumented
    assert "qrs_tmp(142,17,3),brs(142,17),rhox(142,17)" in instrumented
