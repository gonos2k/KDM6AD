from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from make_progb_czero_guard import (  # noqa: E402
    ZERO_QG_MACRO,
    add_zero_qg_guard,
    strip_czero_capture,
    strip_macro_else,
)


def _rho(label: str, consumer: int, indent: str = "            ") -> str:
    return (
        f"! S10_CAPTURE_BEGIN:{label}\n"
        "#ifdef KDM6_PROGB_VALIDITY_CAPTURE\n"
        "         if (capture_enabled .and. capture_step.eq.1 .and. lat.eq.73) then\n"
        f"           write(*,*) 'S10RHO', {consumer}\n"
        "         endif\n"
        "#endif\n"
        f"! S10_CAPTURE_END:{label}\n"
    )


def _source_stub() -> str:
    return (
        "subroutine kdm62d\n"
        "! S10_CAPTURE_BEGIN:kdm62d_capture_arrays\n"
        "#ifdef KDM6_PROGB_VALIDITY_CAPTURE\n"
        "integer :: capture_last_site\n"
        "#endif\n"
        "! S10_CAPTURE_END:kdm62d_capture_arrays\n"
        "          if(t(i,k).gt.t0c) then\n"
        "if(qrs(i,k,3).gt.0.) then\n"
        "              qrs(i,k,3) = qrs(i,k,3) + pgmlt(i,k)\n"
        "              qrs(i,k,1) = qrs(i,k,1) - pgmlt(i,k)\n"
        "              t(i,k) = t(i,k) + xlf/cpm(i,k)*pgmlt(i,k)\n"
        + _rho("rhox_pgmlt", 1418)
        + "              brs(i,k) = brs(i,k) + (pgmlt(i,k)/rhox(i,k))\n"
        "            endif\n"
        "!---------------------------------------------------------------\n"
        "! pimlt:\n"
        "          endif\n"
        "          if(supcol.lt.0.) then\n"
        "            qrs(i,k,3) = max(qrs(i,k,3)+(pgdep(i,k)+pgaut(i,k)                 &\n"
        "                           +piacr(i,k)*(1.-delta3)                             &\n"
        "                           +praci(i,k)*(1.-delta3)+psacr(i,k)*(1.-delta2)      &\n"
        "                           +pracs(i,k)*(1.-delta2)+pgaci(i,k)+paacw(i,k)       &\n"
        "                           +pgacr(i,k)+pgacs(i,k))*dtcld,0.)\n"
        + _rho("rhox_pgdep", 2824)
        + "            brs(i,k) = max(brs(i,k)+(pgdep(i,k)/rhox(i,k)+biacr(i,k)           &\n"
        "                           +braci(i,k)+bsacr(i,k)+bracs(i,k)+bgaci(i,k)        &\n"
        "                           +baacw(i,k)+bgacr(i,k))*dtcld,0.)\n"
        "            xlwork2 = -xls*(psdep(i,k)+pgdep(i,k)+pidep(i,k)+pinud(i,k))\n"
        "            t(i,k) = t(i,k)-xlwork2/cpm(i,k)*dtcld\n"
        "          else\n"
        "            work2(i,k)=-(prevp(i,k)+psevp(i,k)+pgevp(i,k))\n"
        + _rho("rhox_pgevp", 2915)
        + "            bgevp(i,k)=pgevp(i,k)/rhox(i,k)\n"
        + _rho("rhox_pgeml", 2916)
        + "            bgeml(i,k)=pgeml(i,k)/rhox(i,k)\n"
        "            qrs(i,k,3) = max(qrs(i,k,3)+(pgacs(i,k)+pgevp(i,k)                 &\n"
        "                           +pgeml(i,k))*dtcld,0.)\n"
        "            brs(i,k) = max(brs(i,k)+(bgevp(i,k)+bgeml(i,k))*dtcld,0.)\n"
        "            xlwork2 = -xl(i,k)*(prevp(i,k)+psevp(i,k)+pgevp(i,k))\n"
        "            t(i,k) = t(i,k)-xlwork2/cpm(i,k)*dtcld\n"
        "          endif\n"
        "end subroutine\n"
    )


def test_guard_arm_wraps_all_four_density_consumers_and_logs_explicit_actions():
    rendered, contract = add_zero_qg_guard(_source_stub())
    assert rendered.count("if (qrs(i,k,3).eq.0. .and.") == 4
    assert rendered.count("'S10ZG'") == 4
    assert "brs(i,k) = brs(i,k) + (0.)" in rendered
    assert "brs(i,k) = max(brs(i,k)+(0.+biacr(i,k)" in rendered
    assert "if(qrs(i,k,3).gt.0.) then" in rendered
    assert "s10_guard_term = pgmlt(i,k)/rhox(i,k)" in rendered
    assert "s10_guard_term = pgdep(i,k)/rhox(i,k)" in rendered
    assert "s10_guard_term = pgevp(i,k)/rhox(i,k)" in rendered
    assert "s10_guard_term = pgeml(i,k)/rhox(i,k)" in rendered
    # The C action-1 and macro-off B branches keep the original inline
    # expression; the third occurrence is diagnostic-only S10ZG serialization.
    assert rendered.count("pgdep(i,k)/rhox(i,k)") == 3
    assert "biacr(i,k)" in rendered and "bgacr(i,k)" in rendered
    assert "pgmlt(i,k)" in rendered and "pgevp(i,k)" in rendered
    assert "xlwork2" in rendered and "S10HEAT" in rendered
    assert contract["not_approved"] is True
    assert "unchanged B midpoint" in contract["positive_trace_policy"]
    assert "exact original inline" in contract["guard_action_one"]
    assert "never feeds the physical" in contract["diagnostic_quotient"]


def test_macro_off_c_source_is_exact_b_midpoint_physical_source():
    baseline = _source_stub()
    rendered, _ = add_zero_qg_guard(baseline)
    macro_off = strip_macro_else(rendered, ZERO_QG_MACRO)
    macro_off = strip_czero_capture(macro_off)
    assert macro_off == baseline
