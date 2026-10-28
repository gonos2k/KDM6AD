"""Render opt-in seven-cell QNC and QI boundary-donor traces.

Inputs are pinned private sources of the executed PR #469 variant. The output
changes recording only and preserves the PR #465 physical scale branch at
`(i,k,j)=(221,6,63)`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ADVECT_BASE_SHA256 = "421d3922768a75d2c53f1fc241764506b549b7cb3dad5f9e9a71800b1b596548"
SOLVE_BASE_SHA256 = "0c8bec83d424fa75954c9568e8ec97cd8103c7c172c40ad3853f102710ef1cc4"
STAR_IKJ = ((113, 12, 70), (112, 12, 70), (114, 12, 70),
            (113, 12, 69), (113, 12, 71), (113, 11, 70), (113, 13, 70))
QI_IKJ = (1, 33, 168)
STAR_ENV = "KDM6AD_QNC_STAR_TRACE_DIR"
WRITER_ENV = "KDM6AD_QNC_STAR_QI_TRACE_DIR"


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _replace(text: str, old: str, new: str, count: int = 1) -> str:
    if text.count(old) != count:
        raise ValueError(f"private trace source anchor differs: {old[:88]!r}")
    return text.replace(old, new)


def render_advect(raw: bytes) -> bytes:
    if sha(raw) != ADVECT_BASE_SHA256:
        raise ValueError("PR #469 private advection source SHA differs")
    text = raw.decode("utf-8")
    physical = ("i.EQ.221 .AND. k.EQ.6 .AND. j.EQ.63 .AND. &\n"
                "           scale.GT.0. .AND. scale.LT.1.) scale=NEAREST(scale,-1.)")
    if text.count(physical) != 1:
        raise ValueError("PR #465 physical donor-scale branch differs")
    begin = text.index("SUBROUTINE qnc_shared_init")
    end = text.index("SUBROUTINE qnc_flux_trace_set_context", begin)
    block = text[begin:end]
    replacements = (
        ("KDM6AD_QNC_SHARED_TRACE_DIR", STAR_ENV, 1),
        ("'/qnc_shared.tsv'", "'/qnc_star.tsv'", 1),
        ("# KDM6AD_QNC_SHARED_TRACE_V1", "# KDM6AD_QNC_STAR_TRACE_V1", 1),
        ("    IF (.NOT.qnc_trace_selected .OR. qnc_trace_rk.NE.3) RETURN",
         "    qnc_shared_owner=.FALSE.\n"
         "    IF (.NOT.qnc_trace_selected .OR. qnc_trace_rk.NE.3) RETURN", 1),
        ("qnc_shared_owner=220.GE.its .AND. 222.LE.MIN(ite,ide-1) .AND. &\n"
         "         62.GE.jts .AND. 64.LE.MIN(jte,jde-1) .AND. &\n"
         "         5.GE.kts .AND. 7.LE.ktf",
         "qnc_shared_owner=112.GE.its .AND. 114.LE.MIN(ite,ide-1) .AND. &\n"
         "         69.GE.jts .AND. 71.LE.MIN(jte,jde-1) .AND. &\n"
         "         11.GE.kts .AND. 13.LE.ktf .AND. 14.LE.kte", 1),
        ("IF (.NOT.qnc_shared_active .OR. .NOT.qnc_shared_owner) RETURN",
         "IF (.NOT.qnc_trace_selected .OR. qnc_trace_rk.NE.3 .OR. &\n"
         "        .NOT.qnc_shared_active .OR. .NOT.qnc_shared_owner) RETURN", 3),
        ("INTEGER,PARAMETER :: ci(7)=(/221,220,222,221,221,221,221/)",
         "INTEGER,PARAMETER :: ci(7)=(/113,112,114,113,113,113,113/)", 1),
        ("INTEGER,PARAMETER :: ck(7)=(/6,6,6,6,6,5,7/)",
         "INTEGER,PARAMETER :: ck(7)=(/12,12,12,12,12,11,13/)", 1),
        ("INTEGER,PARAMETER :: cj(7)=(/63,63,63,62,64,63,63/)",
         "INTEGER,PARAMETER :: cj(7)=(/70,70,70,69,71,70,70/)", 1),
        ("IF (.NOT.((i.EQ.221 .AND. j.EQ.63 .AND. ABS(k-6).LE.1) .OR. &\n"
         "         (k.EQ.6 .AND. j.EQ.63 .AND. ABS(i-221).LE.1) .OR. &\n"
         "         (i.EQ.221 .AND. k.EQ.6 .AND. ABS(j-63).LE.1))) RETURN",
         "IF (.NOT.((i.EQ.113 .AND. j.EQ.70 .AND. ABS(k-12).LE.1) .OR. &\n"
         "         (k.EQ.12 .AND. j.EQ.70 .AND. ABS(i-113).LE.1) .OR. &\n"
         "         (i.EQ.113 .AND. k.EQ.12 .AND. ABS(j-70).LE.1))) RETURN", 1),
    )
    for old, new, count in replacements:
        block = _replace(block, old, new, count)
    text = text[:begin] + block + text[end:]
    if text.count(physical) != 1:
        raise ValueError("trace overlay altered the physical donor-scale branch")
    return text.encode("utf-8")


def render_solve(raw: bytes) -> bytes:
    if sha(raw) != SOLVE_BASE_SHA256:
        raise ValueError("PR #469 private solve source SHA differs")
    text = raw.decode("utf-8")
    targets = (
        ("KDM6AD_UPNC_NTARGET = 4", "KDM6AD_UPNC_NTARGET = 10"),
        ("KDM6AD_UPNC_I(KDM6AD_UPNC_NTARGET) = (/ 153, 113, 155, 1 /)",
         "KDM6AD_UPNC_I(KDM6AD_UPNC_NTARGET) = (/ 153, 113, 155, 1, 112, 114, 113, 113, 113, 113 /)"),
        ("KDM6AD_UPNC_K(KDM6AD_UPNC_NTARGET) = (/ 4, 12, 15, 33 /)",
         "KDM6AD_UPNC_K(KDM6AD_UPNC_NTARGET) = (/ 4, 12, 15, 33, 12, 12, 12, 12, 11, 13 /)"),
        ("KDM6AD_UPNC_J(KDM6AD_UPNC_NTARGET) = (/ 111, 70, 120, 168 /)",
         "KDM6AD_UPNC_J(KDM6AD_UPNC_NTARGET) = (/ 111, 70, 120, 168, 70, 70, 69, 71, 70, 70 /)"),
        ("KDM6AD_QI_WRITER_TRACE_DIR", WRITER_ENV),
        ("/qi_writer_moments.tsv", "/qnc_star_qi_moments.tsv"),
        ("# KDM6AD_QI_WRITER_MOMENTS_V1", "# KDM6AD_QNC_STAR_QI_MOMENTS_V1"),
    )
    for old, new in targets:
        text = _replace(text, old, new)
    text = _replace(text, "INTEGER :: target, i, k, j, bool_word",
                    "INTEGER :: target, i, k, j, bool_word, donor_i, donor_j")
    donor_block = """      IF (mode .EQ. 4) THEN
        donor_i=ids+grid%spec_zone
        donor_j=MIN(MAX(j,jds+grid%spec_zone),(jde-1)-grid%spec_zone)
        IF (donor_i.LT.ims .OR. donor_i.GT.ime .OR. donor_j.LT.jms .OR. donor_j.GT.jme) &
             CALL wrf_error_fatal('QI boundary donor is outside memory domain')
        CALL kdm6ad_upnc_write_real(step,rk_step,stage,i,k,j,'DONOR_QI',moist(donor_i,k,donor_j,P_QI))
        CALL kdm6ad_upnc_write_real(step,rk_step,stage,i,k,j,'X_WIND',grid%ru_m(i,k,j))
        word=INT(donor_i,C_INT32_T)
        CALL kdm6ad_upnc_write_word(step,rk_step,stage,i,k,j,'DONOR_I','i32',word)
        word=INT(donor_j,C_INT32_T)
        CALL kdm6ad_upnc_write_word(step,rk_step,stage,i,k,j,'DONOR_J','i32',word)
        word=INT(grid%spec_zone,C_INT32_T)
        CALL kdm6ad_upnc_write_word(step,rk_step,stage,i,k,j,'SPEC_ZONE','i32',word)
        word=INT(ids,C_INT32_T)
        CALL kdm6ad_upnc_write_word(step,rk_step,stage,i,k,j,'IDS','i32',word)
        word=INT(ide,C_INT32_T)
        CALL kdm6ad_upnc_write_word(step,rk_step,stage,i,k,j,'IDE','i32',word)
        word=INT(jds,C_INT32_T)
        CALL kdm6ad_upnc_write_word(step,rk_step,stage,i,k,j,'JDS','i32',word)
        word=INT(jde,C_INT32_T)
        CALL kdm6ad_upnc_write_word(step,rk_step,stage,i,k,j,'JDE','i32',word)
        word=INT(its,C_INT32_T)
        CALL kdm6ad_upnc_write_word(step,rk_step,stage,i,k,j,'TILE_ITS','i32',word)
        word=INT(ite,C_INT32_T)
        CALL kdm6ad_upnc_write_word(step,rk_step,stage,i,k,j,'TILE_ITE','i32',word)
        word=INT(jts,C_INT32_T)
        CALL kdm6ad_upnc_write_word(step,rk_step,stage,i,k,j,'TILE_JTS','i32',word)
        word=INT(jte,C_INT32_T)
        CALL kdm6ad_upnc_write_word(step,rk_step,stage,i,k,j,'TILE_JTE','i32',word)
        word=INT(MERGE(1,0,config_flags%periodic_x),C_INT32_T)
        CALL kdm6ad_upnc_write_word(step,rk_step,stage,i,k,j,'PERIODIC_X','bool',word)
        word=INT(MERGE(1,0,(.NOT.config_flags%periodic_x) .AND. &
             (its-ids.LT.grid%spec_zone) .AND. &
             (i.GE.its) .AND. (i.LE.MIN(ite,ids+grid%spec_zone-1)) .AND. &
             (j.GE.MAX(jts,(i-ids)+jds+1)) .AND. &
             (j.LE.MIN(jte,(jde-1)-(i-ids)-1)) .AND. &
             (k.GE.kts) .AND. (k.LE.MIN(kte,kde-1))),C_INT32_T)
        CALL kdm6ad_upnc_write_word(step,rk_step,stage,i,k,j,'X_START_ELIGIBLE','bool',word)
        word=INT(MERGE(1,0,grid%ru_m(i,k,j).LT.0.),C_INT32_T)
        CALL kdm6ad_upnc_write_word(step,rk_step,stage,i,k,j,'X_WIND_NEGATIVE','bool',word)
        CYCLE
      END IF
"""
    text = _replace(text, "      IF (mode .EQ. 0) CYCLE", donor_block + "      IF (mode .EQ. 0) CYCLE")
    call_anchor = "                   CALL flow_dep_bdy  (  moist(ims,kms,jms,im),"
    call_new = ("                   IF (im .EQ. P_QI .AND. rk_step .EQ. rk_order) THEN\n"
                "                     CALL kdm6ad_upnc_trace('QI_BDY_INPUT', grid%itimestep, rk_step, &\n"
                "                          dt_rk, 4, grid%i_start(ij), grid%i_end(ij), &\n"
                "                          grid%j_start(ij), grid%j_end(ij), k_start, k_end)\n"
                "                   END IF\n" + call_anchor)
    text = _replace(text, call_anchor, call_new)
    if (text.count("IF (stage(1:3) .EQ. 'QI_' .AND. target .NE. 4) CYCLE") != 1 or
            text.count("IF (stage(1:3) .EQ. 'QC_' .AND. target .NE. 3) CYCLE") != 1 or
            text.count("CALL kdm6ad_upnc_trace('QI_BDY_INPUT'") != 1):
        raise ValueError("QI/QC target filtering or donor stage differs")
    return text.encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--advect-source", type=Path, required=True)
    parser.add_argument("--solve-source", type=Path, required=True)
    parser.add_argument("--advect-output", type=Path, required=True)
    parser.add_argument("--solve-output", type=Path, required=True)
    args = parser.parse_args()
    inputs = (args.advect_source, args.solve_source)
    outputs = (args.advect_output, args.solve_output)
    if (any(path.exists() or path.is_symlink() for path in outputs) or
            any(output.resolve() == source.resolve() for output in outputs for source in inputs) or
            outputs[0].resolve() == outputs[1].resolve()):
        raise FileExistsError("trace outputs must be new and distinct from input sources")
    generated = (render_advect(inputs[0].read_bytes()), render_solve(inputs[1].read_bytes()))
    for path, data in zip(outputs, generated):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(data)
    print(json.dumps({"status": "QNC_STAR_QI_TRACE_SOURCES_WRITTEN",
                      "advect_sha256": sha(generated[0]), "solve_sha256": sha(generated[1]),
                      "star_ikj_one_based": STAR_IKJ,
                      "qi_ikj_one_based": QI_IKJ}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
