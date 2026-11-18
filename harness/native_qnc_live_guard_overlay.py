"""Insert the bounded, opt-in QNC RK3 live guard into pinned PR #475 host sources.

The selected donor roster is fixed to the 54 liquid failures in the public
packet. Scale choices are computed from the current host operands by the
Fortran guard; this overlay does not encode the choices from PR #476.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from harness.native_qnc_candidate_face_overlay import receiver_union
from harness.native_qnc_domain_preflight_advect_overlay import failure_layer_coordinates


ADVECT_SHA256 = "a77a0484425b0e7823e233844663073d982cab9548481c7c0e281808d035dd0a"
SOLVE_SHA256 = "bfeb3b359708c0da36f56c92593592daa1b95b92376b7c8e7e6741c9ccab250b"
FAILURE_SHA256 = "fa7ba0a92ccec5f1b8001a3c218b8a737ca90c1b9ed4a24f6253e616c1f6257e"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _replace_once(text: str, before: str, after: str) -> str:
    if text.count(before) != 1:
        raise ValueError(f"live guard source anchor differs: {before[:90]!r}")
    return text.replace(before, after)


def _check_failure_rows(raw: bytes) -> None:
    if _sha(raw) != FAILURE_SHA256 or len(failure_layer_coordinates(raw)) != 54:
        raise ValueError("selected 54-donor source changed")
    if len(receiver_union(raw)) != 382:
        raise ValueError("selected 382-cell capture changed")


def render_advect(source: bytes, failure_rows: bytes) -> bytes:
    if _sha(source) != ADVECT_SHA256:
        raise ValueError("PR #475 advection source changed")
    _check_failure_rows(failure_rows)
    text = source.decode("utf-8")
    text = _replace_once(text, "  USE module_wrf_error\n",
                         "  USE module_wrf_error\n"
                         "  USE qnc_live_guard_tile, ONLY: qnc_live_guard_is_active, &\n"
                         "       qnc_live_guard_apply_tile\n")
    text = _replace_once(text, "  PUBLIC :: qnc_flux_trace_set_context\n",
                         "  PUBLIC :: qnc_flux_trace_set_context\n"
                         "  PRIVATE :: qnc_live_guard_is_active,qnc_live_guard_apply_tile\n")
    sub_start = text.index("SUBROUTINE advect_scalar_pd")
    sub_end = text.index("END SUBROUTINE advect_scalar_pd", sub_start)
    block = text[sub_start:sub_end]
    block = _replace_once(block,
        "   INTEGER :: qnc_pref_n,qnc_pref_index,qnc_pref_cell_i,qnc_pref_cell_k,qnc_pref_cell_j\n",
        "   INTEGER :: qnc_pref_n,qnc_pref_index,qnc_pref_cell_i,qnc_pref_cell_k,qnc_pref_cell_j\n"
        "   INTEGER :: qnc_live_status,qnc_live_nulp(54),qnc_live_donors\n")
    block = _replace_once(block,
        "   IF (qnc_trace_selected .AND. qnc_trace_rk .EQ. 3) THEN\n"
        "     CALL qnc_domain_preflight_begin",
        "   qnc_pref_scale=1.0\n"
        "   qnc_pref_hit=0\n"
        "   qnc_pref_seen=.FALSE.\n"
        "   qnc_pref_pre=0.0\n"
        "   qnc_pref_pre_seen=.FALSE.\n"
        "   IF ((qnc_trace_selected .AND. qnc_trace_rk .EQ. 3) .OR. &\n"
        "       qnc_live_guard_is_active()) THEN\n"
        "     CALL qnc_domain_preflight_begin")
    block = _replace_once(block,
        "     IF (qnc_pref_active) THEN\n       qnc_pref_scale=1.0\n",
        "     IF (qnc_pref_active .OR. qnc_live_guard_is_active()) THEN\n"
        "       qnc_pref_scale=1.0\n")
    anchor = "   IF (qnc_trace_selected .AND. qnc_trace_rk .EQ. 3 .AND. qnc_pref_active) THEN\n     DO qnc_pref_n=1,QNC_PREF_NTARGET\n"
    call = (
        "   IF (qnc_live_guard_is_active()) THEN\n"
        "     CALL qnc_live_guard_apply_tile(field_old,c1,c2,mu_old,mub,msftx,msfty, &\n"
        "          rdx,rdy,rdzw,dt,qnc_pref_pre,qnc_pref_pre_seen, &\n"
        "          qnc_pref_scale,qnc_pref_hit,ph_low,flux_out, &\n"
        "          fqxl,fqyl,fqzl,fqx,fqy,fqz, &\n"
        "          ids,ide,jds,jde,kds,kde,ims,ime,jms,jme,kms,kme, &\n"
        "          its,ite,jts,jte,kts,kte,qnc_live_status,qnc_live_nulp, &\n"
        "          qnc_live_donors)\n"
        "     IF (qnc_live_status.NE.1) ERROR STOP 'QNC live guard tile rejected'\n"
        "   END IF\n"
    )
    block = _replace_once(block, anchor, call + anchor)
    block = _replace_once(block,
        "qnc_trace_rk .EQ. 3 .AND. qnc_pref_active) THEN\n       qnc_pref_index=",
        "(qnc_trace_rk .EQ. 3 .AND. qnc_pref_active) .OR. &\n"
        "         qnc_live_guard_is_active()) THEN\n"
        "       qnc_pref_index=")
    text = text[:sub_start] + block + text[sub_end:]
    return text.encode("utf-8")


def render_solve(source: bytes, failure_rows: bytes) -> bytes:
    if _sha(source) != SOLVE_SHA256:
        raise ValueError("PR #475 solve source changed")
    _check_failure_rows(failure_rows)
    text = source.decode("utf-8")
    text = _replace_once(text, "   USE module_em\n",
                         "   USE module_em\n"
                         "   USE qnc_live_guard_tile, ONLY: qnc_live_guard_set_context, &\n"
                         "        qnc_live_guard_is_active, qnc_live_guard_check_tile, &\n"
                         "        qnc_live_guard_clear_context\n")
    # The status lives in the solve_em scope, outside the two tile loops.
    anchor = "   IMPLICIT NONE\n"
    text = _replace_once(text, anchor, anchor + "   INTEGER :: qnc_live_status\n")
    anchor = "         !$OMP PARALLEL DO   &\n         !$OMP PRIVATE ( ij, tenddec )\n         scalar_tile_loop_1:"
    set_context = (
        "         IF (is.EQ.P_QNC .AND. rk_step.EQ.3) THEN\n"
        "           CALL qnc_live_guard_set_context( &\n"
        "                scalar_tend(ims,kms,jms,is),grid%mu_2, &\n"
        "                ims,ime,kms,kme,jms,jme,ids,ide,jds,jde,kds,kde, &\n"
        "                ntasks,1,qnc_live_status)\n"
        "           IF (qnc_live_status.LT.0) ERROR STOP 'QNC live guard context rejected'\n"
        "           IF (qnc_live_guard_is_active()) THEN\n"
        "             IF (config_flags%mp_physics.NE.137 .OR. &\n"
        "                 config_flags%rk_ord.NE.3 .OR. &\n"
        "                 config_flags%scalar_adv_opt.NE.POSITIVEDEF .OR. &\n"
        "                 config_flags%zadvect_implicit.NE.0) &\n"
        "                 ERROR STOP 'QNC live guard requires explicit RK3 positive-definite path'\n"
        "           END IF\n"
        "         END IF\n"
    )
    text = _replace_once(text, anchor, set_context + anchor)
    anchor = "           IF (is .EQ. P_QNC) THEN\n             CALL kdm6ad_upnc_trace('RKSCALAR_AFTER'"
    check = (
        "           IF (is.EQ.P_QNC .AND. rk_step.EQ.3 .AND. &\n"
        "               qnc_live_guard_is_active()) THEN\n"
        "             CALL qnc_live_guard_check_tile(scalar(ims,kms,jms,is), &\n"
        "                  ids,ide,jds,jde,kds,kde,ims,ime,jms,jme,kms,kme, &\n"
        "                  grid%i_start(ij),grid%i_end(ij), &\n"
        "                  grid%j_start(ij),grid%j_end(ij), &\n"
        "                  k_start,k_end,qnc_live_status)\n"
        "             IF (qnc_live_status.NE.1) ERROR STOP 'QNC live guard RK output differs'\n"
        "           END IF\n"
    )
    text = _replace_once(text, anchor, check + anchor)
    anchor = "         ENDDO scalar_tile_loop_2\n         !$OMP END PARALLEL DO\n"
    clear = ("         ENDDO scalar_tile_loop_2\n"
             "         !$OMP END PARALLEL DO\n"
             "         IF (is.EQ.P_QNC .AND. rk_step.EQ.3) &\n"
             "              CALL qnc_live_guard_clear_context()\n")
    text = _replace_once(text, anchor, clear)
    return text.encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--advect-source", type=Path, required=True)
    parser.add_argument("--solve-source", type=Path, required=True)
    parser.add_argument("--failure-json", type=Path, required=True)
    parser.add_argument("--advect-output", type=Path, required=True)
    parser.add_argument("--solve-output", type=Path, required=True)
    args = parser.parse_args()
    inputs = (args.advect_source, args.solve_source, args.failure_json)
    outputs = (args.advect_output, args.solve_output)
    if (len({path.resolve() for path in (*inputs, *outputs)}) != 5 or
            any(path.exists() or path.is_symlink() or path.parent.is_symlink()
                for path in outputs)):
        raise FileExistsError("live guard outputs must be new and distinct from inputs")
    failure_rows = args.failure_json.read_bytes()
    rendered = (render_advect(args.advect_source.read_bytes(), failure_rows),
                render_solve(args.solve_source.read_bytes(), failure_rows))
    for path, raw in zip(outputs, rendered):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(raw)
    print(json.dumps({"status": "QNC_LIVE_GUARD_SOURCE_WRITTEN",
                      "advect_sha256": _sha(rendered[0]),
                      "solve_sha256": _sha(rendered[1])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
