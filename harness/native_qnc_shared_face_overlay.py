#!/usr/bin/env python3
"""Add an opt-in seven-cell QNC face trace to the saved PR457 Fortran source.

The input is the already instrumented, hash-pinned V3 module_advect_em.f90.
Only trace calls and module-private writers are inserted; scalar arithmetic,
the public Fortran interface and the KDM ABI are unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


BASE_SHA256 = "72403b4bb9ac713ec20f06a1ff362c44302bcae32c69d5c5f8769d457975d1b5"
TRACE_ENV = "KDM6AD_QNC_SHARED_TRACE_DIR"

_DECL = """
  INTEGER, SAVE, PRIVATE :: qnc_shared_unit=0, qnc_shared_call=0
  LOGICAL, SAVE, PRIVATE :: qnc_shared_initialized=.FALSE., &
       qnc_shared_active=.FALSE., qnc_shared_owner=.FALSE.
"""

_HELPERS = """
  SUBROUTINE qnc_shared_init()
    CHARACTER(LEN=4096) :: env, filename
    INTEGER :: length, status, ios
    IF (qnc_shared_initialized) RETURN
    qnc_shared_initialized=.TRUE.
    env=''
    CALL get_environment_variable('KDM6AD_QNC_SHARED_TRACE_DIR', &
         value=env,length=length,status=status)
    IF (status.EQ.1 .OR. length.EQ.0) RETURN
    IF (status.NE.0 .OR. length.GT.LEN(env)) ERROR STOP 'QNC shared trace directory invalid'
    filename=TRIM(env)//'/qnc_shared.tsv'
    OPEN(NEWUNIT=qnc_shared_unit,FILE=TRIM(filename),STATUS='NEW',ACTION='WRITE',IOSTAT=ios)
    IF (ios.NE.0) ERROR STOP 'QNC shared trace requires a fresh writable file'
    WRITE(qnc_shared_unit,'(A)') '# KDM6AD_QNC_SHARED_TRACE_V1'
    WRITE(qnc_shared_unit,'(A)') '# CALL id rk model_step_arg time_step_s dt_bits owned'
    WRITE(qnc_shared_unit,'(A)') '# META id field integer_value'
    WRITE(qnc_shared_unit,'(A)') '# VAL id stage i k j field dtype raw_hex'
    FLUSH(qnc_shared_unit)
    qnc_shared_active=.TRUE.
  END SUBROUTINE qnc_shared_init

  SUBROUTINE qnc_shared_meta(field,value)
    CHARACTER(LEN=*),INTENT(IN) :: field
    INTEGER,INTENT(IN) :: value
    WRITE(qnc_shared_unit,'(A,1X,I0,1X,A,1X,I0)') &
         'META',qnc_shared_call,TRIM(field),value
  END SUBROUTINE qnc_shared_meta

  SUBROUTINE qnc_shared_begin(its,ite,kts,kte,jts,jte,ktf, &
       ids,ide,jds,jde,ims,ime,jms,jme,dt,time_step)
    INTEGER,INTENT(IN) :: its,ite,kts,kte,jts,jte,ktf
    INTEGER,INTENT(IN) :: ids,ide,jds,jde,ims,ime,jms,jme,time_step
    REAL,INTENT(IN) :: dt
    INTEGER(C_INT32_T) :: dt_bits
    IF (.NOT.qnc_trace_selected .OR. qnc_trace_rk.NE.3) RETURN
    CALL qnc_shared_init()
    IF (.NOT.qnc_shared_active) RETURN
    qnc_shared_call=qnc_shared_call+1
    qnc_shared_owner=220.GE.its .AND. 222.LE.MIN(ite,ide-1) .AND. &
         62.GE.jts .AND. 64.LE.MIN(jte,jde-1) .AND. &
         5.GE.kts .AND. 7.LE.ktf
    dt_bits=TRANSFER(dt,0_C_INT32_T)
    WRITE(qnc_shared_unit,'(A,1X,I0,1X,I0,1X,I0,1X,I0,1X,Z8.8,1X,I0)') &
         'CALL',qnc_shared_call,qnc_trace_rk,time_step,qnc_trace_step, &
         dt_bits,MERGE(1,0,qnc_shared_owner)
    CALL qnc_shared_meta('ITS',its)
    CALL qnc_shared_meta('ITE',ite)
    CALL qnc_shared_meta('JTS',jts)
    CALL qnc_shared_meta('JTE',jte)
    CALL qnc_shared_meta('KTS',kts)
    CALL qnc_shared_meta('KTE',kte)
    CALL qnc_shared_meta('KTF',ktf)
    CALL qnc_shared_meta('IDS',ids)
    CALL qnc_shared_meta('IDE',ide)
    CALL qnc_shared_meta('JDS',jds)
    CALL qnc_shared_meta('JDE',jde)
    CALL qnc_shared_meta('IMS',ims)
    CALL qnc_shared_meta('IME',ime)
    CALL qnc_shared_meta('JMS',jms)
    CALL qnc_shared_meta('JME',jme)
    FLUSH(qnc_shared_unit)
  END SUBROUTINE qnc_shared_begin

  SUBROUTINE qnc_shared_real(stage,i,k,j,field,value)
    CHARACTER(LEN=*),INTENT(IN) :: stage,field
    INTEGER,INTENT(IN) :: i,k,j
    REAL,INTENT(IN) :: value
    INTEGER(C_INT32_T) :: bits
    IF (.NOT.qnc_shared_active .OR. .NOT.qnc_shared_owner) RETURN
    bits=TRANSFER(value,0_C_INT32_T)
    WRITE(qnc_shared_unit,'(A,1X,I0,1X,A,1X,I0,1X,I0,1X,I0,1X,A,1X,A,1X,Z8.8)') &
         'VAL',qnc_shared_call,TRIM(stage),i,k,j,TRIM(field),'f32',bits
    FLUSH(qnc_shared_unit)
  END SUBROUTINE qnc_shared_real

  SUBROUTINE qnc_shared_capture(its,ite,kts,kte,jts,jte, &
       ims,ime,kms,kme,jms,jme,fqx,fqy,fqz,fqxl,fqyl,fqzl, &
       tendency,msftx,msfty,rdzw,rdx,rdy)
    INTEGER,INTENT(IN) :: its,ite,kts,kte,jts,jte,ims,ime,kms,kme,jms,jme
    REAL,INTENT(IN) :: fqx(its-1:ite+2,kts:kte,jts-1:jte+2), &
         fqy(its-1:ite+2,kts:kte,jts-1:jte+2), &
         fqz(its-1:ite+2,kts:kte,jts-1:jte+2), &
         fqxl(its-1:ite+2,kts:kte,jts-1:jte+2), &
         fqyl(its-1:ite+2,kts:kte,jts-1:jte+2), &
         fqzl(its-1:ite+2,kts:kte,jts-1:jte+2)
    REAL,INTENT(IN) :: tendency(ims:ime,kms:kme,jms:jme), &
         msftx(ims:ime,jms:jme),msfty(ims:ime,jms:jme),rdzw(kms:kme)
    REAL,INTENT(IN) :: rdx,rdy
    INTEGER,PARAMETER :: ci(7)=(/221,220,222,221,221,221,221/)
    INTEGER,PARAMETER :: ck(7)=(/6,6,6,6,6,5,7/)
    INTEGER,PARAMETER :: cj(7)=(/63,63,63,62,64,63,63/)
    INTEGER :: n,i,k,j
    IF (.NOT.qnc_shared_active .OR. .NOT.qnc_shared_owner) RETURN
    DO n=1,7
      i=ci(n)
      k=ck(n)
      j=cj(n)
      CALL qnc_shared_real('RK3_POST',i,k,j,'FX_WEST',fqx(i,k,j))
      CALL qnc_shared_real('RK3_POST',i,k,j,'FX_EAST',fqx(i+1,k,j))
      CALL qnc_shared_real('RK3_POST',i,k,j,'FY_SOUTH',fqy(i,k,j))
      CALL qnc_shared_real('RK3_POST',i,k,j,'FY_NORTH',fqy(i,k,j+1))
      CALL qnc_shared_real('RK3_POST',i,k,j,'FZ_BOTTOM',fqz(i,k,j))
      CALL qnc_shared_real('RK3_POST',i,k,j,'FZ_TOP',fqz(i,k+1,j))
      CALL qnc_shared_real('RK3_POST',i,k,j,'FX_LOW_WEST',fqxl(i,k,j))
      CALL qnc_shared_real('RK3_POST',i,k,j,'FX_LOW_EAST',fqxl(i+1,k,j))
      CALL qnc_shared_real('RK3_POST',i,k,j,'FY_LOW_SOUTH',fqyl(i,k,j))
      CALL qnc_shared_real('RK3_POST',i,k,j,'FY_LOW_NORTH',fqyl(i,k,j+1))
      CALL qnc_shared_real('RK3_POST',i,k,j,'FZ_LOW_BOTTOM',fqzl(i,k,j))
      CALL qnc_shared_real('RK3_POST',i,k,j,'FZ_LOW_TOP',fqzl(i,k+1,j))
      CALL qnc_shared_real('RK3_POST',i,k,j,'MSFTX',msftx(i,j))
      CALL qnc_shared_real('RK3_POST',i,k,j,'MSFTY',msfty(i,j))
      CALL qnc_shared_real('RK3_POST',i,k,j,'RDX',rdx)
      CALL qnc_shared_real('RK3_POST',i,k,j,'RDY',rdy)
      CALL qnc_shared_real('RK3_POST',i,k,j,'RDZW',rdzw(k))
      CALL qnc_shared_real('RK3_POST',i,k,j,'TENDENCY',tendency(i,k,j))
    END DO
  END SUBROUTINE qnc_shared_capture

  SUBROUTINE qnc_shared_tendency(stage,i,k,j,value)
    CHARACTER(LEN=*),INTENT(IN) :: stage
    INTEGER,INTENT(IN) :: i,k,j
    REAL,INTENT(IN) :: value
    IF (.NOT.qnc_shared_active .OR. .NOT.qnc_shared_owner) RETURN
    IF (.NOT.((i.EQ.221 .AND. j.EQ.63 .AND. ABS(k-6).LE.1) .OR. &
         (k.EQ.6 .AND. j.EQ.63 .AND. ABS(i-221).LE.1) .OR. &
         (i.EQ.221 .AND. k.EQ.6 .AND. ABS(j-63).LE.1))) RETURN
    CALL qnc_shared_real(stage,i,k,j,'TENDENCY',value)
  END SUBROUTINE qnc_shared_tendency
"""


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _replace_one(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"expected one source anchor: {old[:100]!r}")
    return text.replace(old, new, 1)


def render(source: bytes) -> bytes:
    if _sha(source) != BASE_SHA256:
        raise ValueError("saved PR457 module_advect_em.f90 SHA differs")
    text = source.decode("utf-8")
    text = _replace_one(text, "\nCONTAINS\n", _DECL + "\nCONTAINS\n" + _HELPERS + "\n")
    start = text.index("SUBROUTINE advect_scalar_pd   (")
    end = text.index("END SUBROUTINE advect_scalar_pd", start)
    before, body, after = text[:start], text[start:end], text[end:]
    order_anchor = "  vert_order = config_flags%v_sca_adv_order\n"
    begin = (
        "  CALL qnc_shared_begin(its,ite,kts,kte,jts,jte,ktf, &\n"
        "       ids,ide,jds,jde,ims,ime,jms,jme,dt,time_step)\n"
    )
    body = _replace_one(body, order_anchor, order_anchor + begin)
    post = body.index("RK3_PD_POST_LIMIT_FACES")
    block_end = body.index("  i_start = its\n", post)
    capture = (
        "  CALL qnc_shared_capture(its,ite,kts,kte,jts,jte, &\n"
        "       ims,ime,kms,kme,jms,jme,fqx,fqy,fqz,fqxl,fqyl,fqzl, &\n"
        "       tendency,msftx,msfty,rdzw,rdx,rdy)\n"
    )
    body = body[:block_end] + capture + body[block_end:]
    for stage in ("RK3_AFTER_Z", "RK3_AFTER_X", "RK3_AFTER_Y"):
        old = f"     CALL qnc_flux_trace_real('{stage}',i,k,j,'TENDENCY',tendency(i,k,j))"
        new = old + f"\n     CALL qnc_shared_tendency('{stage}',i,k,j,tendency(i,k,j))"
        body = _replace_one(body, old, new)
    return (before + body + after).encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    source = args.source.read_bytes()
    output = render(source)
    result = {"base_sha256": _sha(source), "overlay_sha256": _sha(output), "trace_env": TRACE_ENV}
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("xb") as stream:
            stream.write(output)
        result["output"] = str(args.output)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
