#!/usr/bin/env python3
"""Add opt-in, value-only QNC face-flux records to one pinned host source."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile


BASE_SHA256 = "6b2c541fc62ec0cd7f56d243bf68dc4692c782371752ec033187318db1c36bd7"
TRACE_ENV = "KDM6AD_QNC_FLUX_TRACE_DIR"
TARGET = (221, 6, 63)  # i, k, j; native one-based

_DECL = """
  USE, INTRINSIC :: ISO_C_BINDING, ONLY: C_INT32_T
  INTEGER, SAVE, PRIVATE :: qnc_trace_rk=0, qnc_trace_step=0, qnc_trace_unit=0
  LOGICAL, SAVE, PRIVATE :: qnc_trace_selected=.FALSE., qnc_trace_initialized=.FALSE., qnc_trace_active=.FALSE.
  REAL, SAVE, PRIVATE :: qnc_trace_dt=0.0
  PUBLIC :: qnc_flux_trace_set_context
"""

_HELPERS = """
  SUBROUTINE qnc_flux_trace_set_context(species, qnc_species, rk, dt, moist_step)
    INTEGER, INTENT(IN) :: species, qnc_species, rk
    REAL, INTENT(IN) :: dt
    LOGICAL, INTENT(IN) :: moist_step
    qnc_trace_selected = .NOT.moist_step .AND. species .EQ. qnc_species &
         .AND. (rk .EQ. 1 .OR. rk .EQ. 3)
    qnc_trace_rk = rk
    qnc_trace_dt = dt
    IF (qnc_trace_selected) CALL nl_get_time_step(1,qnc_trace_step)
  END SUBROUTINE qnc_flux_trace_set_context

  SUBROUTINE qnc_flux_trace_init()
    CHARACTER(LEN=4096) :: env, filename
    INTEGER :: length, status, ios
    IF (qnc_trace_initialized) RETURN
    qnc_trace_initialized=.TRUE.
    env=''
    CALL get_environment_variable('KDM6AD_QNC_FLUX_TRACE_DIR',value=env,length=length,status=status)
    IF (status .EQ. 1 .OR. length .EQ. 0) RETURN
    IF (status .NE. 0 .OR. length .GT. LEN(env)) ERROR STOP 'QNC flux trace directory invalid'
    filename=TRIM(env)//'/qnc_flux.tsv'
    OPEN(NEWUNIT=qnc_trace_unit,FILE=TRIM(filename),STATUS='NEW',ACTION='WRITE',IOSTAT=ios)
    IF (ios .NE. 0) ERROR STOP 'QNC flux trace requires a fresh writable file'
    WRITE(qnc_trace_unit,'(A)') '# KDM6AD_QNC_FLUX_TRACE_V2'
    WRITE(qnc_trace_unit,'(A)') '# VAL time_step_s rk_step stage i k j field dtype raw_hex'
    FLUSH(qnc_trace_unit)
    qnc_trace_active=.TRUE.
  END SUBROUTINE qnc_flux_trace_init

  SUBROUTINE qnc_flux_trace_real(stage,i,k,j,field,value)
    CHARACTER(LEN=*),INTENT(IN) :: stage,field
    INTEGER,INTENT(IN) :: i,k,j
    REAL,INTENT(IN) :: value
    INTEGER(C_INT32_T) :: bits
    IF (.NOT.qnc_trace_selected .OR. i.NE.221 .OR. k.NE.6 .OR. j.NE.63) RETURN
    CALL qnc_flux_trace_init()
    IF (.NOT.qnc_trace_active) RETURN
    bits=TRANSFER(value,0_C_INT32_T)
    WRITE(qnc_trace_unit,'(A,1X,I0,1X,I0,1X,A,1X,I0,1X,I0,1X,I0,1X,A,1X,A,1X,Z8.8)') &
         'VAL',qnc_trace_step,qnc_trace_rk,TRIM(stage),i,k,j,TRIM(field),'f32',bits
    FLUSH(qnc_trace_unit)
  END SUBROUTINE qnc_flux_trace_real

  SUBROUTINE qnc_flux_trace_limit(i,k,j,available,outgoing,applied_scale,hit)
    INTEGER,INTENT(IN) :: i,k,j
    REAL,INTENT(IN) :: available,outgoing,applied_scale
    LOGICAL,INTENT(IN) :: hit
    INTEGER :: raw
    IF (.NOT.qnc_trace_selected .OR. qnc_trace_rk.NE.3) RETURN
    IF (ABS(i-221)+ABS(k-6)+ABS(j-63).GT.1) RETURN
    CALL qnc_flux_trace_init()
    IF (.NOT.qnc_trace_active) RETURN
    CALL qnc_flux_trace_real_any('RK3_PD_LIMIT_CELL',i,k,j,'PH_LOW',available)
    CALL qnc_flux_trace_real_any('RK3_PD_LIMIT_CELL',i,k,j,'FLUX_OUT',outgoing)
    CALL qnc_flux_trace_real_any('RK3_PD_LIMIT_CELL',i,k,j,'SCALE',applied_scale)
    raw=MERGE(1,0,hit)
    WRITE(qnc_trace_unit,'(A,1X,I0,1X,I0,1X,A,1X,I0,1X,I0,1X,I0,1X,A,1X,A,1X,Z2.2)') &
         'VAL',qnc_trace_step,qnc_trace_rk,'RK3_PD_LIMIT_CELL',i,k,j,'LIMIT_HIT','bool',raw
    FLUSH(qnc_trace_unit)
  END SUBROUTINE qnc_flux_trace_limit

  SUBROUTINE qnc_flux_trace_real_any(stage,i,k,j,field,value)
    CHARACTER(LEN=*),INTENT(IN) :: stage,field
    INTEGER,INTENT(IN) :: i,k,j
    REAL,INTENT(IN) :: value
    INTEGER(C_INT32_T) :: bits
    bits=TRANSFER(value,0_C_INT32_T)
    WRITE(qnc_trace_unit,'(A,1X,I0,1X,I0,1X,A,1X,I0,1X,I0,1X,I0,1X,A,1X,A,1X,Z8.8)') &
         'VAL',qnc_trace_step,qnc_trace_rk,TRIM(stage),i,k,j,TRIM(field),'f32',bits
    FLUSH(qnc_trace_unit)
  END SUBROUTINE qnc_flux_trace_real_any

  SUBROUTINE qnc_flux_trace_rk1(stage,i,k,j,tend,low,high,metric)
    CHARACTER(LEN=*),INTENT(IN) :: stage
    INTEGER,INTENT(IN) :: i,k,j
    REAL,INTENT(IN) :: tend,low,high,metric
    IF (.NOT.qnc_trace_selected .OR. qnc_trace_rk.NE.1) RETURN
    IF (i.NE.221 .OR. k.NE.6 .OR. j.NE.63) RETURN
    CALL qnc_flux_trace_real(stage,i,k,j,'TENDENCY',tend)
    SELECT CASE(stage)
    CASE('RK1_AFTER_Y')
      CALL qnc_flux_trace_real(stage,i,k,j,'F_Y_LOWER',low)
      CALL qnc_flux_trace_real(stage,i,k,j,'F_Y_UPPER',high)
      CALL qnc_flux_trace_real(stage,i,k,j,'MRDY',metric)
    CASE('RK1_AFTER_X')
      CALL qnc_flux_trace_real(stage,i,k,j,'F_X_LOWER',low)
      CALL qnc_flux_trace_real(stage,i,k,j,'F_X_UPPER',high)
      CALL qnc_flux_trace_real(stage,i,k,j,'MRDX',metric)
    CASE('RK1_AFTER_Z')
      CALL qnc_flux_trace_real(stage,i,k,j,'F_Z_LOWER',low)
      CALL qnc_flux_trace_real(stage,i,k,j,'F_Z_UPPER',high)
      CALL qnc_flux_trace_real(stage,i,k,j,'RDZW',metric)
    END SELECT
  END SUBROUTINE qnc_flux_trace_rk1

  SUBROUTINE qnc_flux_trace_faces(stage,its,ite,kts,kte,jts,jte, &
       fqx,fqy,fqz,fqxl,fqyl,fqzl,ph_low,flux_out,msftx,msfty,rdx,rdy,rdzw)
    CHARACTER(LEN=*),INTENT(IN) :: stage
    INTEGER,INTENT(IN) :: its,ite,kts,kte,jts,jte
    REAL,INTENT(IN) :: fqx(its-1:ite+2,kts:kte,jts-1:jte+2), &
                       fqy(its-1:ite+2,kts:kte,jts-1:jte+2), &
                       fqz(its-1:ite+2,kts:kte,jts-1:jte+2), &
                       fqxl(its-1:ite+2,kts:kte,jts-1:jte+2), &
                       fqyl(its-1:ite+2,kts:kte,jts-1:jte+2), &
                       fqzl(its-1:ite+2,kts:kte,jts-1:jte+2), &
                       ph_low(its-1:ite+2,kts:kte,jts-1:jte+2), &
                       flux_out(its-1:ite+2,kts:kte,jts-1:jte+2)
    REAL,INTENT(IN) :: msftx,msfty,rdx,rdy,rdzw
    INTEGER,PARAMETER :: i=221,k=6,j=63
    IF (.NOT.qnc_trace_selected .OR. qnc_trace_rk.NE.3) RETURN
    IF (i.LT.its.OR.i.GT.ite.OR.j.LT.jts.OR.j.GT.jte.OR.k.LT.kts.OR.k.GE.kte) RETURN
    IF (stage.EQ.'RK3_PD_PRE_LIMIT') THEN
      CALL qnc_flux_trace_real(stage,i,k,j,'PH_LOW',ph_low(i,k,j))
      CALL qnc_flux_trace_real(stage,i,k,j,'FLUX_OUT',flux_out(i,k,j))
    END IF
    CALL qnc_flux_trace_real(stage,i,k,j,'FX_WEST',fqx(i,k,j))
    CALL qnc_flux_trace_real(stage,i,k,j,'FX_EAST',fqx(i+1,k,j))
    CALL qnc_flux_trace_real(stage,i,k,j,'FY_SOUTH',fqy(i,k,j))
    CALL qnc_flux_trace_real(stage,i,k,j,'FY_NORTH',fqy(i,k,j+1))
    CALL qnc_flux_trace_real(stage,i,k,j,'FZ_BOTTOM',fqz(i,k,j))
    CALL qnc_flux_trace_real(stage,i,k,j,'FZ_TOP',fqz(i,k+1,j))
    CALL qnc_flux_trace_real(stage,i,k,j,'FX_LOW_WEST',fqxl(i,k,j))
    CALL qnc_flux_trace_real(stage,i,k,j,'FX_LOW_EAST',fqxl(i+1,k,j))
    CALL qnc_flux_trace_real(stage,i,k,j,'FY_LOW_SOUTH',fqyl(i,k,j))
    CALL qnc_flux_trace_real(stage,i,k,j,'FY_LOW_NORTH',fqyl(i,k,j+1))
    CALL qnc_flux_trace_real(stage,i,k,j,'FZ_LOW_BOTTOM',fqzl(i,k,j))
    CALL qnc_flux_trace_real(stage,i,k,j,'FZ_LOW_TOP',fqzl(i,k+1,j))
    IF (stage.EQ.'RK3_PD_POST_LIMIT_FACES') THEN
      CALL qnc_flux_trace_real(stage,i,k,j,'MSFTX',msftx)
      CALL qnc_flux_trace_real(stage,i,k,j,'MSFTY',msfty)
      CALL qnc_flux_trace_real(stage,i,k,j,'RDX',rdx)
      CALL qnc_flux_trace_real(stage,i,k,j,'RDY',rdy)
      CALL qnc_flux_trace_real(stage,i,k,j,'RDZW',rdzw)
      CALL qnc_flux_trace_real(stage,i,k,j,'DT_STEP',qnc_trace_dt)
    END IF
  END SUBROUTINE qnc_flux_trace_faces
"""


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _insert_once(text: str, needle: str, code: str, *, after: bool = False) -> str:
    if text.count(needle) != 1:
        raise ValueError(
            f"expected one source anchor, got {text.count(needle)}: {needle[:60]!r}"
        )
    return text.replace(needle, needle + code if after else code + needle, 1)


def _between(text: str, start: str, end: str) -> tuple[str, str, str]:
    a = text.index(start)
    b = text.index(end, a + len(start))
    return text[:a], text[a:b], text[b:]


def _instrument_ordinary(body: str) -> str:
    body = _insert_once(
        body,
        "  horizontal_order_test : IF( horz_order == 6 ) THEN",
        (
            "  IF(qnc_trace_selected .AND. qnc_trace_rk.EQ.1) THEN\n"
            "    IF(221.GE.its.AND.221.LE.ite.AND.63.GE.jts.AND.63.LE.jte.AND.6.GE.kts.AND.6.LT.kte) &\n"
            "      CALL qnc_flux_trace_rk1('RK1_START',221,6,63,tendency(221,6,63),0.0,0.0,0.0)\n"
            "  END IF\n"
        ),
    )
    pre, h5, post = _between(
        body, "  ELSE IF( horz_order == 5 ) THEN", "   ELSE IF( horz_order == 4 ) THEN"
    )
    y = "            tendency(i,k,j-1) = tendency(i,k,j-1) - mrdy*(fqy(i,k,jp1)-fqy(i,k,jp0))"
    x = "            tendency(i,k,j) = tendency(i,k,j) - mrdx*(fqx(i+1,k)-fqx(i,k))"
    h5 = _insert_once(
        h5,
        y,
        "\n            CALL qnc_flux_trace_rk1('RK1_AFTER_Y',i,k,j-1,tendency(i,k,j-1), &\n                 fqy(i,k,jp0),fqy(i,k,jp1),mrdy)",
        after=True,
    )
    h5 = _insert_once(
        h5,
        x,
        "\n            CALL qnc_flux_trace_rk1('RK1_AFTER_X',i,k,j,tendency(i,k,j), &\n                 fqx(i,k),fqx(i+1,k),mrdx)",
        after=True,
    )
    body = pre + h5 + post
    pre, v3, post = _between(
        body, "   ELSE IF (vert_order == 3) THEN", "   ELSE IF (vert_order == 2) THEN"
    )
    z = "            tendency(i,k,j)=tendency(i,k,j)-rdzw(k)*(vflux(i,k+1)-vflux(i,k))"
    v3 = _insert_once(
        v3,
        z,
        "\n            CALL qnc_flux_trace_rk1('RK1_AFTER_Z',i,k,j,tendency(i,k,j), &\n                 vflux(i,k),vflux(i,k+1),rdzw(k))",
        after=True,
    )
    return pre + v3 + post


def _faces_call(stage: str) -> str:
    initial_tendency = (
        "  CALL qnc_flux_trace_real('RK3_PD_PRE_LIMIT',221,6,63,'TENDENCY',tendency(221,6,63))\n"
        if stage == "RK3_PD_PRE_LIMIT"
        else ""
    )
    return (
        "  IF(qnc_trace_selected .AND. 221.GE.its .AND. 221.LE.ite .AND. &\n"
        + "     63.GE.jts .AND. 63.LE.jte .AND. 6.GE.kts .AND. 6.LT.kte) THEN\n"
        + initial_tendency
        + "  CALL qnc_flux_trace_faces('"
        + stage
        + "',its,ite,kts,kte,jts,jte, &\n"
        + "       fqx,fqy,fqz,fqxl,fqyl,fqzl,ph_low,flux_out, &\n"
        + "       msftx(221,63),msfty(221,63),rdx,rdy,rdzw(6))\n"
        + "  END IF\n"
    )


def _tendency_call(stage: str) -> str:
    return (
        "     CALL qnc_flux_trace_real('"
        + stage
        + "',i,k,j,'TENDENCY',tendency(i,k,j))\n"
    )


def _instrument_pd(body: str) -> str:
    limit = "     IF( flux_out(i,k,j) .gt. ph_low(i,k,j) ) THEN"
    pos = body.index(limit)
    loop = body.rfind("   DO j=j_start, j_end", 0, pos)
    if loop < 0:
        raise ValueError("PD limiter loop missing")
    body = body[:loop] + _faces_call("RK3_PD_PRE_LIMIT") + body[loop:]
    pos = body.index(limit)
    marker = "     endif\n\n   ENDDO\n   ENDDO\n   ENDDO"
    tail = body.index(marker, pos)
    cell = (
        "     IF(qnc_trace_selected .AND. qnc_trace_rk.EQ.3) THEN\n"
        "       IF(ABS(i-221)+ABS(k-6)+ABS(j-63).LE.1) THEN\n"
        "         IF(flux_out(i,k,j).GT.ph_low(i,k,j)) THEN\n"
        "           CALL qnc_flux_trace_limit(i,k,j,ph_low(i,k,j),flux_out(i,k,j),scale,.TRUE.)\n"
        "         ELSE\n"
        "           CALL qnc_flux_trace_limit(i,k,j,ph_low(i,k,j),flux_out(i,k,j),1.0,.FALSE.)\n"
        "         END IF\n"
        "       END IF\n"
        "     END IF\n"
    )
    body = (
        body[: tail + len("     endif\n")] + cell + body[tail + len("     endif\n") :]
    )
    pos = body.index(limit)
    post = body.index("  i_start = its\n", pos)
    body = body[:post] + _faces_call("RK3_PD_POST_LIMIT_FACES") + body[post:]
    # The three existing S15 observations follow the actual Z, X and Y updates.
    pos = body.index("  i_start = its\n", body.index(limit))
    for stage in ("RK3_AFTER_Z", "RK3_AFTER_X", "RK3_AFTER_Y"):
        anchor = "     if (s15_here) call s15_emit_axis"
        here = body.index(anchor, pos)
        body = body[:here] + _tendency_call(stage) + body[here:]
        pos = here + len(_tendency_call(stage)) + len(anchor)
    return body


def render(source: bytes) -> tuple[bytes, dict[str, object]]:
    if _sha(source) != BASE_SHA256:
        raise ValueError("saved module_advect_em.f90 SHA differs")
    text = source.decode("utf-8")
    text = _insert_once(
        text,
        "  USE module_wrf_error\n",
        "  USE, INTRINSIC :: ISO_C_BINDING, ONLY: C_INT32_T\n",
        after=True,
    )
    text = _insert_once(
        text,
        "CONTAINS\n",
        _DECL.replace("  USE, INTRINSIC :: ISO_C_BINDING, ONLY: C_INT32_T\n", "")
        + "\n",
        after=False,
    )
    text = _insert_once(text, "CONTAINS\n", _HELPERS + "\n", after=True)
    a = "SUBROUTINE advect_scalar   ("
    b = "END SUBROUTINE advect_scalar"
    pre, body, post = _between(text, a, b)
    body = _instrument_ordinary(body)
    text = pre + body + post
    a = "SUBROUTINE advect_scalar_pd   ("
    b = "END SUBROUTINE advect_scalar_pd"
    pre, body, post = _between(text, a, b)
    body = _instrument_pd(body)
    text = pre + body + post
    data = text.encode("utf-8")
    return data, {
        "base_sha256": BASE_SHA256,
        "overlay_sha256": _sha(data),
        "trace_env": TRACE_ENV,
        "target_ikj": TARGET,
    }


def apply_overlay(
    source_path: Path, output_path: Path | None = None
) -> dict[str, object]:
    source_path = Path(source_path)
    if source_path.is_symlink() or not source_path.is_file():
        raise ValueError("source must be a regular file")
    output, details = render(source_path.read_bytes())
    if output_path is None:
        return {
            "status": "ready",
            "file": {
                "source_sha256": details["base_sha256"],
                "overlay_sha256": details["overlay_sha256"],
                "trace_env": TRACE_ENV,
            },
        }
    output_path = Path(output_path)
    if output_path.exists() or output_path.is_symlink():
        raise FileExistsError(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=output_path.parent, prefix=".qnc-flux-")
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(output)
            handle.flush()
            os.fsync(handle.fileno())
        if _sha(source_path.read_bytes()) != BASE_SHA256:
            raise RuntimeError("source changed during overlay")
        os.replace(temporary, output_path)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "status": "applied",
        "file": {
            "source_sha256": details["base_sha256"],
            "overlay_sha256": details["overlay_sha256"],
            "trace_env": TRACE_ENV,
            "output_path": str(output_path.resolve()),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    print(json.dumps(apply_overlay(args.source, args.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
