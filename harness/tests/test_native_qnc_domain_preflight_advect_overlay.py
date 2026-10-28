from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

from harness.native_qnc_domain_preflight_advect_overlay import (
    failure_layer_coordinates,
    render_advect,
    sha,
)


ROOT = Path(__file__).resolve().parents[1]
FAILURE_JSON = ROOT / "evidence/native_qnc_host_backoff_review_2026-10-28/residual_reason_rows.json"


BEGIN_ANCHOR = (
    "   DO j=j_start, j_end\n   DO k=kts, ktf\n!DIR$ vector always\n"
    "   DO i=i_start, i_end\n\n     ph_low(i,k,j) = ((c1(k)*mub(i,j)+c2(k))+")
EMIT_ANCHOR = (
    "     IF(qnc_trace_selected .AND. qnc_trace_rk.EQ.3) THEN\n"
    "       IF(ABS(i-113)+ABS(k-12)+ABS(j-70).LE.1) THEN\n"
    "         IF(flux_out(i,k,j).GT.ph_low(i,k,j)) THEN\n"
    "           CALL qnc_flux_trace_limit(i,k,j,ph_low(i,k,j),flux_out(i,k,j),scale,.TRUE.)\n"
    "         ELSE\n"
    "           CALL qnc_flux_trace_limit(i,k,j,ph_low(i,k,j),flux_out(i,k,j),1.0,.FALSE.)\n"
    "         END IF\n"
    "       END IF\n"
    "     END IF\n\n   ENDDO"
)
FINISH_ANCHOR = (
    "   ENDDO\n   ENDDO\n   ENDDO\n\n   END IF\n\n\n\n"
    "  IF(qnc_trace_selected .AND. 113.GE.its"
)


def _fixture() -> bytes:
    source = (
        "MODULE module_advect_em\n"
        "  USE, INTRINSIC :: ISO_C_BINDING, ONLY: C_INT32_T\n"
        "  INTEGER, SAVE, PRIVATE :: qnc_trace_rk=0, qnc_trace_step=0\n"
        "  LOGICAL, SAVE, PRIVATE :: qnc_trace_selected=.FALSE.\n"
        "  INTEGER, SAVE, PRIVATE :: qnc_shared_unit=0, qnc_shared_call=0\n"
        "  LOGICAL, SAVE, PRIVATE :: qnc_shared_initialized=.FALSE., &\n"
        "       qnc_shared_active=.FALSE., qnc_shared_owner=.FALSE.\n\n"
        "CONTAINS\n"
        "SUBROUTINE advect_scalar_pd(field_old,c1,c2,mu_old,mub,dt,msftx,msfty, &\n"
        "     rdx,rdy,rdzw,ph_low,flux_out,fqxl,fqyl,fqzl,fqx,fqy,fqz,scale, &\n"
        "     i,k,j,ids,ide,jds,jde,ims,ime,jms,jme,its,ite,jts,jte,kts,kte,time_step)\n"
        "  INTEGER :: i,k,j,ids,ide,jds,jde,ims,ime,jms,jme,its,ite,jts,jte,kts,kte,time_step\n"
        "  REAL :: field_old,c1,c2,mu_old,mub,dt,msftx,msfty,rdx,rdy,rdzw,ph_low,flux_out\n"
        "   REAL :: scale\n"
        "  REAL :: fqxl(2),fqyl(2),fqzl(2),fqx(2),fqy(2),fqz(2)\n"
        "  IF (pd_limit) THEN\n"
        + BEGIN_ANCHOR + "\n"
        "   DO j=j_start, j_end\n   DO k=kts, ktf\n   DO i=i_start, i_end\n"
        "     flux_out(i,k,j) = 1.0\n   ENDDO\n   ENDDO\n   ENDDO\n"
        "   DO j=j_start, j_end\n   DO k=kts, ktf\n   DO i=i_start, i_end\n"
        "     IF( flux_out(i,k,j) .gt. ph_low(i,k,j) ) THEN\n"
        "       scale = max(0.,ph_low(i,k,j)/(flux_out(i,k,j)+eps))\n"
        "       IF( fqx (i+1,k,j) .gt. 0.) fqx(i+1,k,j) = scale*fqx(i+1,k,j)\n"
        "     END IF\n"
        + EMIT_ANCHOR + "\n"
        + FINISH_ANCHOR + "\n"
        "   i_start = its\n"
        "   tendency (i,k,j) = 0.0\n"
        "! add in the pd-limited flux divergence\n"
        "END SUBROUTINE advect_scalar_pd\nEND MODULE module_advect_em\n"
    )
    return source.encode("utf-8")


def test_failure_layers_are_derived_from_pinned_json_not_embedded_coordinates():
    raw = FAILURE_JSON.read_bytes()
    coords = failure_layer_coordinates(raw)
    data = json.loads(raw)
    expected = sorted(
        (row["i_one_based"], k, row["j_one_based"])
        for row in data["rows"]
        for k in row["final_reason_levels_one_based"].get(
            "liquid_QC_positive_NC_nonpositive", [])
    )
    ice_only = {
        (row["i_one_based"], k, row["j_one_based"])
        for row in data["rows"]
        for k in row["final_reason_levels_one_based"].get(
            "ice_QI_positive_NI_nonpositive", [])
    }
    assert len(coords) == 54
    assert len(set(coords)) == 54
    assert list(coords) == expected
    assert not set(coords).intersection(ice_only)


def test_failure_json_pin_and_liquid_word_contract_are_enforced():
    raw = FAILURE_JSON.read_bytes()
    with pytest.raises(ValueError, match="residual_reason_rows.json SHA differs"):
        failure_layer_coordinates(raw + b" ")


def test_render_adds_only_env_gated_raw_operand_writes(monkeypatch):
    source = _fixture()
    monkeypatch.setattr(
        "harness.native_qnc_domain_preflight_advect_overlay.ADVECT_SOURCE_SHA256", sha(source))
    rendered = render_advect(source, FAILURE_JSON.read_bytes()).decode("utf-8")

    assert "KDM6AD_QNC_DOMAIN_PREFLIGHT_DIR" in rendered
    assert "qnc_trace_selected .AND. qnc_trace_rk .EQ. 3" in rendered
    assert "FIELD_OLD C1H C2H MU_OLD MU_BASE DT MSFTX MSFTY RDX RDY RDZW PH_LOW FLUX_OUT SCALE" in rendered
    assert "FX_LOW_WEST FX_LOW_EAST FY_LOW_SOUTH FY_LOW_NORTH FZ_LOW_BOTTOM FZ_LOW_TOP" in rendered
    assert "FX_POST_WEST FX_POST_EAST FY_POST_SOUTH FY_POST_NORTH FZ_POST_BOTTOM FZ_POST_TOP" in rendered
    assert "QNC_PREF_NTARGET=54" in rendered
    # The limiter's physical statements remain present once, in original order.
    for statement in (
        "scale = max(0.,ph_low(i,k,j)/(flux_out(i,k,j)+eps))",
        "fqx(i+1,k,j) = scale*fqx(i+1,k,j)",
    ):
        assert rendered.count(statement) == 1
    subroutine = rendered[
        rendered.index("SUBROUTINE advect_scalar_pd"):rendered.index("END SUBROUTINE advect_scalar_pd")
    ]
    emit_at = subroutine.index("CALL qnc_domain_preflight_emit(time_step")
    limiter_loops = "   ENDDO\n   ENDDO\n   ENDDO\n"
    assert subroutine.rfind(limiter_loops, 0, emit_at) < emit_at
    assert emit_at < subroutine.index("i_start = its", emit_at)
    assert emit_at < subroutine.index("tendency (i,k,j) =", emit_at)
    assert "qnc_pref_cell_i.GE.its .AND. qnc_pref_cell_i.LE.MIN(ite,ide-1)" in subroutine
    assert "qnc_pref_cell_j.GE.jts .AND. qnc_pref_cell_j.LE.MIN(jte,jde-1)" in subroutine


def test_local_indices_do_not_casefold_to_module_target_arrays(monkeypatch):
    source = _fixture()
    monkeypatch.setattr(
        "harness.native_qnc_domain_preflight_advect_overlay.ADVECT_SOURCE_SHA256", sha(source))
    rendered = render_advect(source, FAILURE_JSON.read_bytes()).decode("utf-8").lower()
    arrays = {"qnc_pref_i", "qnc_pref_k", "qnc_pref_j"}
    for local in ("qnc_pref_cell_i", "qnc_pref_cell_k", "qnc_pref_cell_j"):
        assert local in rendered
        assert local not in arrays
    assert all(array in rendered for array in arrays)


def test_renderer_rejects_other_advection_source():
    with pytest.raises(ValueError, match="source SHA differs"):
        render_advect(b"not PR471 source", FAILURE_JSON.read_bytes())


def test_cli_writes_only_a_new_distinct_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import harness.native_qnc_domain_preflight_advect_overlay as overlay

    source = _fixture()
    source_path = tmp_path / "pinned_input.f90"
    output_path = tmp_path / "rendered.f90"
    source_path.write_bytes(source)
    original_json = FAILURE_JSON.read_bytes()
    monkeypatch.setattr(overlay, "ADVECT_SOURCE_SHA256", sha(source))
    monkeypatch.setattr(sys, "argv", [
        "overlay", "--advect-source", str(source_path), "--failure-json", str(FAILURE_JSON),
        "--advect-output", str(output_path),
    ])

    assert overlay.main() == 0
    assert source_path.read_bytes() == source
    assert FAILURE_JSON.read_bytes() == original_json
    assert output_path.is_file()
    with pytest.raises(FileExistsError):
        overlay.main()
