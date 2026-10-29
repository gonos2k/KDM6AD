"""Add opt-in i=1/2 ice-moment tracing to the pinned V7 QNC host variant.

This source overlay records the transient X-start donor and target through the
three RK stages and microphysics. It changes no tendency, state or boundary
assignment, and leaves the existing QNC guard and writer inventory intact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


SOURCE_SHA256 = "a498d4e801034d1a8b3d3488cd7ea3d49aca00a535d4504b21f2055c21255ce1"
TRACE_ENV = "KDM6AD_QI_DONOR_TRACE_DIR"
STAGES = ("QI_TEND_BEFORE", "QI_TEND_AFTER", "QI_RK_BEFORE", "QI_RK_AFTER",
          "QI_BDY_AFTER")


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _replace_once(source: str, before: str, after: str) -> str:
    if source.count(before) != 1:
        raise ValueError(f"QI donor trace source anchor differs: {before[:80]!r}")
    return source.replace(before, after)


def _trace_call(stage: str, indent: str = "               ") -> str:
    return (f"{indent}IF (im.EQ.P_QI) CALL qi_donor_trace('{stage}', &\n"
            f"{indent}     grid%itimestep,rk_step,dt_rk, &\n"
            f"{indent}     grid%i_start(ij),grid%i_end(ij), &\n"
            f"{indent}     grid%j_start(ij),grid%j_end(ij),k_start,k_end)\n")


TRACE_ROUTINES = """
  SUBROUTINE qi_donor_trace(stage,step,rk,dt_value,its,ite,jts,jte,kts,kte)
    CHARACTER(LEN=*), INTENT(IN) :: stage
    INTEGER, INTENT(IN) :: step,rk,its,ite,jts,jte,kts,kte
    REAL, INTENT(IN) :: dt_value
    INTEGER :: ii,ios,length,status
    CHARACTER(LEN=4096) :: env,filename
    IF (.NOT.QI_DONOR_INITIALIZED) THEN
      QI_DONOR_INITIALIZED=.TRUE.
      env=''
      CALL GET_ENVIRONMENT_VARIABLE('KDM6AD_QI_DONOR_TRACE_DIR', &
           VALUE=env,LENGTH=length,STATUS=status)
      IF (status.EQ.1 .OR. length.EQ.0) RETURN
      IF (status.NE.0 .OR. length.GT.LEN(env)) &
           ERROR STOP 'QI donor trace directory invalid'
      filename=TRIM(env)//'/qi_donor.tsv'
      OPEN(NEWUNIT=QI_DONOR_UNIT,FILE=TRIM(filename),STATUS='NEW', &
           ACTION='WRITE',IOSTAT=ios)
      IF (ios.NE.0) ERROR STOP 'QI donor trace needs a fresh output file'
      WRITE(QI_DONOR_UNIT,'(A)') '# KDM6AD_QI_DONOR_TRANSIENT_V1'
      WRITE(QI_DONOR_UNIT,'(A)') '# VAL step rk stage i k j field raw_word_hex'
      QI_DONOR_ACTIVE=.TRUE.
    END IF
    IF (.NOT.QI_DONOR_ACTIVE) RETURN
    IF (168.LT.jts .OR. 168.GT.jte .OR. 33.LT.kts .OR. 33.GT.kte) RETURN
    DO ii=1,2
      IF (ii.LT.its .OR. ii.GT.ite) CYCLE
      CALL qi_donor_write(step,rk,stage,ii,33,168,'QI', &
           TRANSFER(moist(ii,33,168,P_QI),0_C_INT32_T))
      CALL qi_donor_write(step,rk,stage,ii,33,168,'NI', &
           TRANSFER(scalar(ii,33,168,P_QNI),0_C_INT32_T))
      IF (rk.GT.0) THEN
        CALL qi_donor_write(step,rk,stage,ii,33,168,'RU_M', &
             TRANSFER(grid%ru_m(ii,33,168),0_C_INT32_T))
        CALL qi_donor_write(step,rk,stage,ii,33,168,'SPEC_ZONE', &
             INT(grid%spec_zone,C_INT32_T))
        CALL qi_donor_write(step,rk,stage,ii,33,168,'SPECIFIED', &
             INT(MERGE(1,0,config_flags%specified),C_INT32_T))
        CALL qi_donor_write(step,rk,stage,ii,33,168,'HAVE_BCS_MOIST', &
             INT(MERGE(1,0,config_flags%have_bcs_moist),C_INT32_T))
        CALL qi_donor_write(step,rk,stage,ii,33,168,'PERIODIC_X', &
             INT(MERGE(1,0,config_flags%periodic_x),C_INT32_T))
        CALL qi_donor_write(step,rk,stage,ii,33,168,'IDS', &
             INT(ids,C_INT32_T))
        CALL qi_donor_write(step,rk,stage,ii,33,168,'DONOR_I', &
             INT(ids+grid%spec_zone,C_INT32_T))
        CALL qi_donor_write(step,rk,stage,ii,33,168,'DONOR_J', &
             INT(MIN(MAX(168,jds+grid%spec_zone),(jde-1)-grid%spec_zone),C_INT32_T))
        IF (ii.EQ.2 .AND. stage.NE.'QI_TEND_BEFORE') THEN
        CALL qi_donor_write(step,rk,stage,ii,33,168,'MOIST_OLD', &
             TRANSFER(moist_old(ii,33,168,P_QI),0_C_INT32_T))
        CALL qi_donor_write(step,rk,stage,ii,33,168,'MOIST_TEND', &
             TRANSFER(moist_tend(ii,33,168,P_QI),0_C_INT32_T))
        CALL qi_donor_write(step,rk,stage,ii,33,168,'MU_OLD', &
             TRANSFER(grid%mu_1(ii,168),0_C_INT32_T))
        CALL qi_donor_write(step,rk,stage,ii,33,168,'MU_NEW', &
             TRANSFER(grid%mu_2(ii,168),0_C_INT32_T))
        CALL qi_donor_write(step,rk,stage,ii,33,168,'MU_BASE', &
             TRANSFER(grid%mub(ii,168),0_C_INT32_T))
        CALL qi_donor_write(step,rk,stage,ii,33,168,'C1H', &
             TRANSFER(grid%c1h(33),0_C_INT32_T))
        CALL qi_donor_write(step,rk,stage,ii,33,168,'C2H', &
             TRANSFER(grid%c2h(33),0_C_INT32_T))
        CALL qi_donor_write(step,rk,stage,ii,33,168,'DT_RK', &
             TRANSFER(dt_value,0_C_INT32_T))
        CALL qi_donor_write(step,rk,stage,ii,33,168,'MSFTY', &
             TRANSFER(grid%msfty(ii,168),0_C_INT32_T))
          CALL qi_donor_write(step,rk,stage,ii,33,168,'ADVECT_TEND', &
               TRANSFER(advect_tend(ii,33,168),0_C_INT32_T))
          CALL qi_donor_write(step,rk,stage,ii,33,168,'H_TENDENCY', &
               TRANSFER(h_tendency(ii,33,168),0_C_INT32_T))
          CALL qi_donor_write(step,rk,stage,ii,33,168,'Z_TENDENCY', &
               TRANSFER(z_tendency(ii,33,168),0_C_INT32_T))
        END IF
      END IF
    END DO
    FLUSH(QI_DONOR_UNIT)
  END SUBROUTINE qi_donor_trace

  SUBROUTINE qi_donor_write(step,rk,stage,i,k,j,field,word)
    INTEGER, INTENT(IN) :: step,rk,i,k,j
    CHARACTER(LEN=*), INTENT(IN) :: stage,field
    INTEGER(C_INT32_T), INTENT(IN) :: word
    WRITE(QI_DONOR_UNIT,'(A,1X,I0,1X,I0,1X,A,1X,I0,1X,I0,1X,I0,1X,A,1X,Z8.8)') &
         'VAL',step,rk,TRIM(stage),i,k,j,TRIM(field),word
  END SUBROUTINE qi_donor_write
"""


def render_solve(source: bytes) -> bytes:
    if sha(source) != SOURCE_SHA256:
        raise ValueError("V7 private solve source changed")
    text = source.decode("utf-8")
    text = _replace_once(text,
        "   INTEGER, SAVE :: KDM6AD_UPNC_UNIT = 0\n",
        "   INTEGER, SAVE :: QI_DONOR_UNIT = 0\n"
        "   LOGICAL, SAVE :: QI_DONOR_INITIALIZED=.FALSE.,QI_DONOR_ACTIVE=.FALSE.\n"
        "   INTEGER, SAVE :: KDM6AD_UPNC_UNIT = 0\n")
    start = text.index("moist_variable_loop: DO im")
    end = text.index("ENDDO moist_variable_loop", start)
    block = text[start:end]
    for stage in STAGES:
        anchor = ("               IF (im .EQ. P_QI .AND. rk_step .EQ. rk_order) THEN\n"
                  f"                 CALL kdm6ad_upnc_trace('{stage}'")
        block = _replace_once(block, anchor, _trace_call(stage) + anchor)
    boundary = "                   CALL flow_dep_bdy  (  moist(ims,kms,jms,im),"
    block = _replace_once(block,boundary,
        _trace_call("QI_BDY_INPUT", indent="                   ") + boundary)
    text = text[:start] + block + text[end:]
    for stage in ("PRE_MICROPHYSICS", "POST_MICROPHYSICS", "POST_FINISH"):
        anchor = f"     CALL kdm6ad_upnc_trace('{stage}', grid%itimestep, 0, dtm, 0, &"
        call = (f"     CALL qi_donor_trace('{stage}',grid%itimestep,0,dtm, &\n"
                "          ids,ide-1,jds,jde-1,k_start,k_end)\n")
        text = _replace_once(text, anchor, call + anchor)
    text = _replace_once(text,"END SUBROUTINE solve_em\n",TRACE_ROUTINES+"END SUBROUTINE solve_em\n")
    return text.encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if (args.output.exists() or args.output.is_symlink() or
            args.output.resolve() == args.source.resolve()):
        raise FileExistsError("QI donor trace output must be new and distinct")
    rendered = render_solve(args.source.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as stream:
        stream.write(rendered)
    print(json.dumps({"status":"QI_DONOR_TRACE_SOURCE_WRITTEN",
                      "source_sha256":sha(rendered)},sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
