"""Trace the applied QI RK3 face producer at the remaining ice donor.

The opt-in overlay records one donor's PRE/LOW/POST faces, the seven local
limiter-owner decisions and the actual Z→X→Y tendency accumulation. It leaves
the inherited QNC guard, QI donor trace and numerical assignments intact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ADVECT_SHA256 = "2655e8e0f0e2d19db77fdee583f926ebd371c236c00dd1d580dd5283afed714b"
SOLVE_SHA256 = "75f17730a582de1bc49cfcc20e90a4f0c95dfa7bfa11a03f6ad0c8dd986a0b6b"
TRACE_ENV = "KDM6AD_QI_FACE_TRACE_DIR"


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _replace_once(text: str, before: str, after: str) -> str:
    if text.count(before) != 1:
        raise ValueError(f"QI face source anchor differs: {before[:90]!r}")
    return text.replace(before, after)


TRACE_ROUTINES = """
  LOGICAL FUNCTION qi_face_env_one(name)
    CHARACTER(LEN=*), INTENT(IN) :: name
    CHARACTER(LEN=64) :: value
    INTEGER :: length,status
    value=''
    CALL GET_ENVIRONMENT_VARIABLE(name,VALUE=value,LENGTH=length,STATUS=status)
    qi_face_env_one=status.EQ.0 .AND. TRIM(value).EQ.'1'
  END FUNCTION qi_face_env_one

  SUBROUTINE qi_face_trace_init()
    CHARACTER(LEN=4096) :: env,filename
    INTEGER :: length,status,ios
    IF (qi_face_initialized) RETURN
    qi_face_initialized=.TRUE.
    env=''
    CALL GET_ENVIRONMENT_VARIABLE('KDM6AD_QI_FACE_TRACE_DIR', &
         VALUE=env,LENGTH=length,STATUS=status)
    IF (status.EQ.1 .OR. length.EQ.0) RETURN
    IF (status.NE.0 .OR. length.GT.LEN(env)) &
         ERROR STOP 'QI face trace directory invalid'
    filename=TRIM(env)//'/qi_face.tsv'
    OPEN(NEWUNIT=qi_face_unit,FILE=TRIM(filename),STATUS='NEW',ACTION='WRITE',IOSTAT=ios)
    IF (ios.NE.0) ERROR STOP 'QI face trace requires a fresh output file'
    WRITE(qi_face_unit,'(A)') '# KDM6AD_QI_FACE_PRODUCER_V1'
    WRITE(qi_face_unit,'(A)') '# BASE_ADVECT_SHA256 2655e8e0f0e2d19db77fdee583f926ebd371c236c00dd1d580dd5283afed714b'
    WRITE(qi_face_unit,'(A)') '# VAL step rk stage i k j field dtype raw_word_hex'
    qi_face_active=.TRUE.
  END SUBROUTINE qi_face_trace_init

  SUBROUTINE qi_face_trace_set_context(selected,step,rk,nranks)
    LOGICAL, INTENT(IN) :: selected
    INTEGER, INTENT(IN) :: step,rk,nranks
    qi_face_selected=.FALSE.
    IF (.NOT.selected) RETURN
    CALL qi_face_trace_init()
    IF (.NOT.qi_face_active) RETURN
    IF (nranks.NE.1 .OR. .NOT.qi_face_env_one('OMP_NUM_THREADS') .OR. &
        .NOT.qi_face_env_one('MKL_NUM_THREADS') .OR. &
        .NOT.qi_face_env_one('OMP_THREAD_LIMIT') .OR. &
        .NOT.qi_face_env_one('VECLIB_MAXIMUM_THREADS')) &
         ERROR STOP 'QI face trace requires one MPI rank and one thread'
    qi_face_step=step
    qi_face_rk=rk
    qi_face_selected=.TRUE.
  END SUBROUTINE qi_face_trace_set_context

  LOGICAL FUNCTION qi_face_owns_donor(its,ite,jts,jte,kts,ktf)
    INTEGER, INTENT(IN) :: its,ite,jts,jte,kts,ktf
    qi_face_owns_donor=qi_face_selected .AND. qi_face_active .AND. &
         qi_face_rk.EQ.3 .AND. 2.GE.its .AND. 2.LE.ite .AND. &
         168.GE.jts .AND. 168.LE.jte .AND. 32.GE.kts .AND. 34.LE.ktf
  END FUNCTION qi_face_owns_donor

  SUBROUTINE qi_face_emit_word(stage,i,k,j,field,dtype,word)
    CHARACTER(LEN=*), INTENT(IN) :: stage,field,dtype
    INTEGER, INTENT(IN) :: i,k,j
    INTEGER(C_INT32_T), INTENT(IN) :: word
    IF (.NOT.qi_face_selected .OR. .NOT.qi_face_active) RETURN
    WRITE(qi_face_unit,'(A,1X,I0,1X,I0,1X,A,1X,I0,1X,I0,1X,I0,1X,A,1X,A,1X,Z8.8)') &
         'VAL',qi_face_step,qi_face_rk,TRIM(stage),i,k,j,TRIM(field),TRIM(dtype),word
  END SUBROUTINE qi_face_emit_word

  SUBROUTINE qi_face_emit_real(stage,i,k,j,field,value)
    CHARACTER(LEN=*), INTENT(IN) :: stage,field
    INTEGER, INTENT(IN) :: i,k,j
    REAL, INTENT(IN) :: value
    CALL qi_face_emit_word(stage,i,k,j,field,'f32',TRANSFER(value,0_C_INT32_T))
  END SUBROUTINE qi_face_emit_real

  SUBROUTINE qi_face_emit_int(stage,i,k,j,field,value)
    CHARACTER(LEN=*), INTENT(IN) :: stage,field
    INTEGER, INTENT(IN) :: i,k,j,value
    CALL qi_face_emit_word(stage,i,k,j,field,'i32',INT(value,C_INT32_T))
  END SUBROUTINE qi_face_emit_int

  SUBROUTINE qi_face_emit_bool(stage,i,k,j,field,value)
    CHARACTER(LEN=*), INTENT(IN) :: stage,field
    INTEGER, INTENT(IN) :: i,k,j
    LOGICAL, INTENT(IN) :: value
    CALL qi_face_emit_word(stage,i,k,j,field,'bool',INT(MERGE(1,0,value),C_INT32_T))
  END SUBROUTINE qi_face_emit_bool

  SUBROUTINE qi_face_emit_faces(stage,values)
    CHARACTER(LEN=*), INTENT(IN) :: stage
    REAL, INTENT(IN) :: values(6)
    CHARACTER(LEN=9), PARAMETER :: names(6)=(/ &
         'FX_WEST  ','FX_EAST  ','FY_SOUTH ','FY_NORTH ','FZ_BOTTOM','FZ_TOP   ' /)
    INTEGER :: n
    DO n=1,6
      CALL qi_face_emit_real(stage,2,33,168,TRIM(names(n)),values(n))
    END DO
  END SUBROUTINE qi_face_emit_faces

  SUBROUTINE qi_face_flush()
    IF (qi_face_selected .AND. qi_face_active) FLUSH(qi_face_unit)
  END SUBROUTINE qi_face_flush
"""


def render_advect(source: bytes) -> bytes:
    if sha(source) != ADVECT_SHA256:
        raise ValueError("V7 private advection source changed")
    text = source.decode("utf-8")
    text = _replace_once(text, "  PUBLIC :: qnc_flux_trace_set_context\n",
        "  PUBLIC :: qnc_flux_trace_set_context\n"
        "  PUBLIC :: qi_face_trace_set_context\n"
        "  PRIVATE :: qi_face_env_one,qi_face_trace_init,qi_face_owns_donor, &\n"
        "       qi_face_emit_word,qi_face_emit_real,qi_face_emit_int, &\n"
        "       qi_face_emit_bool,qi_face_emit_faces,qi_face_flush\n"
        "  INTEGER, SAVE, PRIVATE :: qi_face_unit=0,qi_face_step=0,qi_face_rk=0\n"
        "  LOGICAL, SAVE, PRIVATE :: qi_face_initialized=.FALSE., &\n"
        "       qi_face_active=.FALSE.,qi_face_selected=.FALSE.\n")
    text = _replace_once(text, "CONTAINS\n", "CONTAINS\n" + TRACE_ROUTINES)
    start = text.index("SUBROUTINE advect_scalar_pd")
    end = text.index("END SUBROUTINE advect_scalar_pd", start)
    block = text[start:end]
    block = _replace_once(block, "   INTEGER :: qnc_pref_n,qnc_pref_index,qnc_pref_cell_i,qnc_pref_cell_k,qnc_pref_cell_j\n",
        "   INTEGER :: qnc_pref_n,qnc_pref_index,qnc_pref_cell_i,qnc_pref_cell_k,qnc_pref_cell_j\n"
        "   LOGICAL :: qi_here,qi_owner_seen(7),qi_owner_hit(7)\n"
        "   REAL :: qi_pre(6),qi_low(6),qi_post(6),qi_owner_scale(7)\n"
        "   REAL :: qi_owner_available(7),qi_owner_flux_out(7)\n"
        "   INTEGER :: qi_owner_n\n"
        "   INTEGER, PARAMETER :: qi_oi(7)=(/2,1,3,2,2,2,2/)\n"
        "   INTEGER, PARAMETER :: qi_ok(7)=(/33,33,33,33,33,32,34/)\n"
        "   INTEGER, PARAMETER :: qi_oj(7)=(/168,168,168,167,169,168,168/)\n")
    block = _replace_once(block, "   IF (pd_limit) THEN\n",
                          "   qi_here=.FALSE.\n   IF (pd_limit) THEN\n")
    pre_anchor = "   qnc_pref_scale=1.0\n   qnc_pref_hit=0\n"
    pre = (
        "   qi_here=qi_face_owns_donor(its,ite,jts,jte,kts,ktf)\n"
        "   IF (qi_here) THEN\n"
        "     IF (i_start.GT.2 .OR. i_end.LT.3 .OR. &\n"
        "         j_start.GT.167 .OR. j_end.LT.169) &\n"
        "          ERROR STOP 'QI face donor/receiver limiter stencil unavailable'\n"
        "     qi_owner_seen=.FALSE.\n"
        "     qi_owner_hit=.FALSE.\n"
        "     qi_owner_scale=1.0\n"
        "     qi_pre=(/fqx(2,33,168),fqx(3,33,168), &\n"
        "          fqy(2,33,168),fqy(2,33,169),fqz(2,33,168),fqz(2,34,168)/)\n"
        "     qi_low=(/fqxl(2,33,168),fqxl(3,33,168), &\n"
        "          fqyl(2,33,168),fqyl(2,33,169),fqzl(2,33,168),fqzl(2,34,168)/)\n"
        "     CALL qi_face_emit_faces('PRE',qi_pre)\n"
        "     CALL qi_face_emit_faces('LOW',qi_low)\n"
        "     CALL qi_face_emit_real('INPUT',2,33,168,'FIELD',field(2,33,168))\n"
        "     CALL qi_face_emit_real('INPUT',2,33,168,'FIELD_OLD',field_old(2,33,168))\n"
        "     CALL qi_face_emit_real('INPUT',2,33,168,'C1H',c1(33))\n"
        "     CALL qi_face_emit_real('INPUT',2,33,168,'C2H',c2(33))\n"
        "     CALL qi_face_emit_real('INPUT',2,33,168,'MU_OLD',mu_old(2,168))\n"
        "     CALL qi_face_emit_real('INPUT',2,33,168,'MU_BASE',mub(2,168))\n"
        "     CALL qi_face_emit_real('INPUT',2,33,168,'MSFTX',msftx(2,168))\n"
        "     CALL qi_face_emit_real('INPUT',2,33,168,'MSFTY',msfty(2,168))\n"
        "     CALL qi_face_emit_real('INPUT',2,33,168,'RDX',rdx)\n"
        "     CALL qi_face_emit_real('INPUT',2,33,168,'RDY',rdy)\n"
        "     CALL qi_face_emit_real('INPUT',2,33,168,'RDZW',rdzw(33))\n"
        "     CALL qi_face_emit_real('INPUT',2,33,168,'DT',dt)\n"
        "     CALL qi_face_emit_real('INPUT',2,33,168,'EPS',eps)\n"
        "     CALL qi_face_emit_int('META',2,33,168,'HORZ_ORDER',horz_order)\n"
        "     CALL qi_face_emit_int('META',2,33,168,'VERT_ORDER',vert_order)\n"
        "     CALL qi_face_emit_int('META',2,33,168,'IDS',ids)\n"
        "     CALL qi_face_emit_int('META',2,33,168,'IDE',ide)\n"
        "     CALL qi_face_emit_int('META',2,33,168,'JDS',jds)\n"
        "     CALL qi_face_emit_int('META',2,33,168,'JDE',jde)\n"
        "     CALL qi_face_emit_int('META',2,33,168,'ITS',its)\n"
        "     CALL qi_face_emit_int('META',2,33,168,'ITE',ite)\n"
        "     CALL qi_face_emit_int('META',2,33,168,'JTS',jts)\n"
        "     CALL qi_face_emit_int('META',2,33,168,'JTE',jte)\n"
        "     CALL qi_face_emit_int('META',2,33,168,'LIM_I_START',i_start)\n"
        "     CALL qi_face_emit_int('META',2,33,168,'LIM_I_END',i_end)\n"
        "     CALL qi_face_emit_int('META',2,33,168,'LIM_J_START',j_start)\n"
        "     CALL qi_face_emit_int('META',2,33,168,'LIM_J_END',j_end)\n"
        "     CALL qi_face_emit_bool('META',2,33,168,'DEGRADE_XS',degrade_xs)\n"
        "     CALL qi_face_emit_bool('META',2,33,168,'DEGRADE_XE',degrade_xe)\n"
        "     CALL qi_face_emit_bool('META',2,33,168,'DEGRADE_YS',degrade_ys)\n"
        "     CALL qi_face_emit_bool('META',2,33,168,'DEGRADE_YE',degrade_ye)\n"
        "     CALL qi_face_emit_bool('META',2,33,168,'TENDEC',tenddec)\n"
        "   END IF\n"
    )
    block = _replace_once(block, pre_anchor, pre + pre_anchor)
    limiter_anchor = "     IF( flux_out(i,k,j) .gt. ph_low(i,k,j) ) THEN\n"
    # Capture the actual branch and scale after it has been computed; no-hit
    # cells use literal one, so the loop's stale local `scale` is never read.
    after_branch = "     if (s15_here) then\n      s15_pd_post(1)=fqx(i,k,j)\n"
    owner_capture = (
        "     IF (qi_here) THEN\n"
        "       DO qi_owner_n=1,7\n"
        "         IF (i.EQ.qi_oi(qi_owner_n) .AND. k.EQ.qi_ok(qi_owner_n) .AND. &\n"
        "             j.EQ.qi_oj(qi_owner_n)) THEN\n"
        "           IF (qi_owner_seen(qi_owner_n)) ERROR STOP 'QI owner limiter repeated'\n"
        "           qi_owner_seen(qi_owner_n)=.TRUE.\n"
        "           qi_owner_hit(qi_owner_n)=flux_out(i,k,j).GT.ph_low(i,k,j)\n"
        "           qi_owner_scale(qi_owner_n)=1.0\n"
        "           IF (qi_owner_hit(qi_owner_n)) qi_owner_scale(qi_owner_n)=scale\n"
        "           qi_owner_available(qi_owner_n)=ph_low(i,k,j)\n"
        "           qi_owner_flux_out(qi_owner_n)=flux_out(i,k,j)\n"
        "         END IF\n"
        "       END DO\n"
        "     END IF\n"
    )
    if block.count(limiter_anchor) != 1:
        raise ValueError("QI limiter branch anchor differs")
    block = _replace_once(block, after_branch, owner_capture + after_branch)
    post_anchor = "   IF (qnc_live_guard_is_active()) THEN\n     CALL qnc_live_guard_apply_tile"
    post = (
        "   IF (qi_here) THEN\n"
        "     qi_post=(/fqx(2,33,168),fqx(3,33,168), &\n"
        "          fqy(2,33,168),fqy(2,33,169),fqz(2,33,168),fqz(2,34,168)/)\n"
        "     CALL qi_face_emit_faces('POST',qi_post)\n"
        "     DO qi_owner_n=1,7\n"
        "       CALL qi_face_emit_bool('OWNER',qi_oi(qi_owner_n),qi_ok(qi_owner_n), &\n"
        "            qi_oj(qi_owner_n),'SEEN',qi_owner_seen(qi_owner_n))\n"
        "       IF (.NOT.qi_owner_seen(qi_owner_n)) CYCLE\n"
        "       CALL qi_face_emit_bool('OWNER',qi_oi(qi_owner_n),qi_ok(qi_owner_n), &\n"
        "            qi_oj(qi_owner_n),'HIT',qi_owner_hit(qi_owner_n))\n"
        "       CALL qi_face_emit_real('OWNER',qi_oi(qi_owner_n),qi_ok(qi_owner_n), &\n"
        "            qi_oj(qi_owner_n),'SCALE',qi_owner_scale(qi_owner_n))\n"
        "       CALL qi_face_emit_real('OWNER',qi_oi(qi_owner_n),qi_ok(qi_owner_n), &\n"
        "            qi_oj(qi_owner_n),'PH_LOW',qi_owner_available(qi_owner_n))\n"
        "       CALL qi_face_emit_real('OWNER',qi_oi(qi_owner_n),qi_ok(qi_owner_n), &\n"
        "            qi_oj(qi_owner_n),'FLUX_OUT',qi_owner_flux_out(qi_owner_n))\n"
        "     END DO\n"
        "     CALL qi_face_emit_real('TEND_START',2,33,168,'ADVECT_TEND',tendency(2,33,168))\n"
        "     CALL qi_face_flush()\n"
        "   END IF\n"
    )
    block = _replace_once(block, post_anchor, post + post_anchor)
    for axis in ("Z", "X", "Y"):
        anchor = f"     CALL qnc_flux_trace_real('RK3_AFTER_{axis}',i,k,j,'TENDENCY',tendency(i,k,j))"
        insert = ("     IF (qi_here .AND. i.EQ.2 .AND. k.EQ.33 .AND. j.EQ.168) THEN\n"
                  f"       CALL qi_face_emit_real('AFTER_{axis}',i,k,j,'ADVECT_TEND',tendency(i,k,j))\n"
                  "       CALL qi_face_flush()\n"
                  "     END IF\n")
        block = _replace_once(block, anchor, insert + anchor)
    text = text[:start] + block + text[end:]
    return text.encode("utf-8")


def render_solve(source: bytes) -> bytes:
    if sha(source) != SOLVE_SHA256:
        raise ValueError("QI donor private solve source changed")
    text = source.decode("utf-8")
    text = _replace_once(text, "   USE module_em\n",
        "   USE module_em\n   USE module_advect_em, ONLY: qi_face_trace_set_context\n")
    start = text.index("moist_variable_loop: DO im")
    end = text.index("ENDDO moist_variable_loop", start)
    block = text[start:end]
    before = "             !$OMP PARALLEL DO   &\n             !$OMP PRIVATE ( ij, tenddec )\n             moist_tile_loop_1:"
    set_context = (
        "             CALL qi_face_trace_set_context(im.EQ.P_QI .AND. rk_step.EQ.3, &\n"
        "                  grid%itimestep,rk_step,ntasks)\n"
    )
    block = _replace_once(block, before, set_context + before)
    after = "             ENDDO moist_tile_loop_1\n             !$OMP END PARALLEL DO\n"
    block = _replace_once(block, after, after +
        "             CALL qi_face_trace_set_context(.FALSE.,grid%itimestep,rk_step,ntasks)\n")
    text = text[:start] + block + text[end:]
    return text.encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--advect-source", type=Path, required=True)
    parser.add_argument("--solve-source", type=Path, required=True)
    parser.add_argument("--advect-output", type=Path, required=True)
    parser.add_argument("--solve-output", type=Path, required=True)
    args = parser.parse_args()
    sources = (args.advect_source, args.solve_source)
    outputs = (args.advect_output, args.solve_output)
    if (len({path.resolve() for path in (*sources, *outputs)}) != 4 or
            any(path.exists() or path.is_symlink() or path.parent.is_symlink()
                for path in outputs)):
        raise FileExistsError("QI face overlay outputs must be fresh and distinct")
    raw = (render_advect(sources[0].read_bytes()), render_solve(sources[1].read_bytes()))
    for path, content in zip(outputs, raw):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(content)
    print(json.dumps({"status":"QI_FACE_PRODUCER_SOURCE_WRITTEN",
                      "advect_sha256":sha(raw[0]),"solve_sha256":sha(raw[1])},sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
