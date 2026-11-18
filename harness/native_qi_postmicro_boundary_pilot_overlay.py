"""Generate the opt-in post-microphysics ice-boundary diagnostic source.

The existing boundary map replaces each eligible edge value by its same-species
interior donor on outflow, or zero on inflow. Its QI/NI deltas are external
boundary increments, not conservative transfers; units and physical weighting
remain to be certified. For a fixed velocity-sign branch, its JVP copies the
donor tangent or zero and its VJP accumulates onto the donor or zero; velocity
sign changes are discontinuous. This host map is outside the KDM ABI AD contract.
All eligible edges, corners and levels can change, including places other than
the trace target. The late replacement can leave earlier diagnostics stale.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

SOURCE_SHA256 = "73d4ac972e3576d151b4a04ee8a263da0e3a9d19734ba6e75a1d83c1a055a451"


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"postmicro source anchor differs: {old[:90]!r}")
    return text.replace(old, new, 1)


ROUTINE = '''
  SUBROUTINE qi_post_bdy_pilot()
    CHARACTER(LEN=4096) :: pilot, trace_dir, filename
    INTEGER :: plen,pstatus,tlen,tstatus,ios,ii
    INTEGER, SAVE :: unit=0
    LOGICAL, SAVE :: trace_open=.FALSE.
    LOGICAL :: enabled,tracing,qi_gate,ni_gate
    pilot=''
    trace_dir=''
    CALL GET_ENVIRONMENT_VARIABLE('KDM6AD_QI_POST_BDY_PILOT', &
         VALUE=pilot,LENGTH=plen,STATUS=pstatus)
    enabled=pstatus.EQ.0 .AND. plen.EQ.1 .AND. pilot(1:1).EQ.'1'
    CALL GET_ENVIRONMENT_VARIABLE('KDM6AD_QI_POST_BDY_TRACE_DIR', &
         VALUE=trace_dir,LENGTH=tlen,STATUS=tstatus)
    tracing=tstatus.EQ.0 .AND. tlen.GT.0
    IF (pstatus.NE.0 .AND. pstatus.NE.1) &
         ERROR STOP 'QI boundary pilot flag invalid'
    IF (pstatus.EQ.0 .AND. plen.GT.0 .AND. .NOT.enabled .AND. &
        .NOT.(plen.EQ.1 .AND. pilot(1:1).EQ.'0')) &
         ERROR STOP 'QI boundary pilot flag must be 1 or unset'
    IF (tstatus.NE.0 .AND. tstatus.NE.1) &
         ERROR STOP 'QI boundary trace directory invalid'
    IF (.NOT.enabled .AND. .NOT.tracing) RETURN
    IF (ntasks.NE.1 .OR. &
        .NOT.qi_post_env_one('OMP_NUM_THREADS') .OR. &
        .NOT.qi_post_env_one('MKL_NUM_THREADS') .OR. &
        .NOT.qi_post_env_one('OMP_THREAD_LIMIT')) &
         ERROR STOP 'QI boundary pilot requires one rank and thread'
    IF (grid%id.NE.1 .OR. config_flags%mp_physics.NE.137 .OR. &
        .NOT.config_flags%specified .OR. config_flags%nested .OR. &
        config_flags%periodic_x .OR. grid%spec_zone.NE.1 .OR. &
        ids.NE.1 .OR. ips.NE.ids .OR. ipe.LT.ide-1 .OR. &
        jps.NE.jds .OR. jpe.LT.jde-1 .OR. &
        168.LT.jds+1 .OR. 168.GT.jde-2 .OR. &
        33.LT.k_start .OR. 33.GT.k_end .OR. &
        P_QI.LT.PARAM_FIRST_SCALAR .OR. P_QNI.LT.PARAM_FIRST_SCALAR .OR. &
        P_QI.GT.num_moist .OR. P_QNI.GT.num_scalar) &
         ERROR STOP 'QI boundary pilot outside audited host case'
    qi_gate=.NOT.config_flags%have_bcs_moist
    ni_gate=.NOT.config_flags%have_bcs_scalar
    IF (enabled .AND. (config_flags%polar .OR. .NOT.F_QI .OR. .NOT.F_QNI)) &
         ERROR STOP 'QI boundary pilot requires nonpolar active ice moments'
    IF (enabled .AND. (.NOT.qi_gate .OR. .NOT.ni_gate)) &
         ERROR STOP 'QI boundary pilot requires both moment boundary gates'
    IF (tracing .AND. .NOT.trace_open) THEN
      filename=TRIM(trace_dir)//'/qi_post_bdy.tsv'
      OPEN(NEWUNIT=unit,FILE=TRIM(filename),STATUS='NEW',ACTION='WRITE',IOSTAT=ios)
      IF (ios.NE.0) ERROR STOP 'QI boundary trace requires fresh file'
      WRITE(unit,'(A)') '# KDM6AD_QI_POST_BDY_V1'
      WRITE(unit,'(A)') '# VAL step stage i k j field raw_word_hex'
      trace_open=.TRUE.
    END IF
    IF (tracing) THEN
      WRITE(unit,'(A,1X,I0,1X,3(I0,1X))') 'GATES',grid%itimestep, &
           MERGE(1,0,enabled),MERGE(1,0,qi_gate),MERGE(1,0,ni_gate)
      CALL qi_post_snapshot(unit,'BEFORE')
    END IF
    IF (enabled) THEN
      DO ii=1,grid%num_tiles
        IF (qi_gate) CALL flow_dep_bdy(moist(ims,kms,jms,P_QI), &
             grid%ru_m,grid%rv_m,config_flags,grid%spec_zone, &
             ids,ide,jds,jde,kds,kde,ims,ime,jms,jme,kms,kme, &
             ips,ipe,jps,jpe,kps,kpe,grid%i_start(ii),grid%i_end(ii), &
             grid%j_start(ii),grid%j_end(ii),k_start,k_end)
        IF (ni_gate) CALL flow_dep_bdy(scalar(ims,kms,jms,P_QNI), &
             grid%ru_m,grid%rv_m,config_flags,grid%spec_zone, &
             ids,ide,jds,jde,kds,kde,ims,ime,jms,jme,kms,kme, &
             ips,ipe,jps,jpe,kps,kpe,grid%i_start(ii),grid%i_end(ii), &
             grid%j_start(ii),grid%j_end(ii),k_start,k_end)
      END DO
    END IF
    IF (tracing) THEN
      CALL qi_post_snapshot(unit,'AFTER')
    END IF
  END SUBROUTINE qi_post_bdy_pilot

  LOGICAL FUNCTION qi_post_env_one(name)
    CHARACTER(LEN=*), INTENT(IN) :: name
    CHARACTER(LEN=64) :: value
    INTEGER :: length,status
    value=''
    CALL GET_ENVIRONMENT_VARIABLE(name,VALUE=value,LENGTH=length,STATUS=status)
    qi_post_env_one=status.EQ.0 .AND. length.EQ.1 .AND. value(1:1).EQ.'1'
  END FUNCTION qi_post_env_one

  SUBROUTINE qi_post_snapshot(unit,stage)
    INTEGER, INTENT(IN) :: unit
    CHARACTER(LEN=*), INTENT(IN) :: stage
    INTEGER :: ii,k
    DO k=30,33
      IF (k.LT.k_start .OR. k.GT.k_end) CYCLE
      DO ii=1,2
        WRITE(unit,'(A,1X,I0,1X,A,1X,3(I0,1X),A,1X,Z8.8)') &
             'VAL',grid%itimestep,stage,ii,k,168,'QI',TRANSFER(moist(ii,k,168,P_QI),0_C_INT32_T)
        WRITE(unit,'(A,1X,I0,1X,A,1X,3(I0,1X),A,1X,Z8.8)') &
             'VAL',grid%itimestep,stage,ii,k,168,'NI',TRANSFER(scalar(ii,k,168,P_QNI),0_C_INT32_T)
        WRITE(unit,'(A,1X,I0,1X,A,1X,3(I0,1X),A,1X,Z8.8)') &
             'VAL',grid%itimestep,stage,ii,k,168,'RU_M',TRANSFER(grid%ru_m(ii,k,168),0_C_INT32_T)
      END DO
      WRITE(unit,'(A,1X,I0,1X,A,1X,I0,1X,I0,1X,A,1X,I0)') &
           'BRANCH',grid%itimestep,stage,k,168,'WEST_OUTFLOW_U_LT_ZERO', &
           MERGE(1,0,grid%ru_m(ids,k,168).LT.0.)
    END DO
    FLUSH(unit)
  END SUBROUTINE qi_post_snapshot
'''


def render_solve(source: bytes) -> bytes:
    if sha(source) != SOURCE_SHA256:
        raise ValueError("PR #481 private solve source SHA mismatch")
    text = source.decode("utf-8")
    anchor = "     CALL qi_donor_trace('POST_FINISH',grid%itimestep,0,dtm, &\n"
    text = replace_once(text, anchor, "     CALL qi_post_bdy_pilot()\n" + anchor)
    text = replace_once(text, "END SUBROUTINE solve_em\n", ROUTINE + "END SUBROUTINE solve_em\n")
    return text.encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--solve-source', type=Path, required=True)
    parser.add_argument('--solve-output', type=Path, required=True)
    args = parser.parse_args()
    if (args.solve_output.exists() or args.solve_output.is_symlink() or
            args.solve_output.parent.is_symlink() or
            args.solve_output.resolve() == args.solve_source.resolve()):
        raise FileExistsError('output must be fresh and distinct')
    result = render_solve(args.solve_source.read_bytes())
    args.solve_output.parent.mkdir(parents=True, exist_ok=True)
    with args.solve_output.open('xb') as output:
        output.write(result)
    print(json.dumps({'status': 'QI_POST_BDY_SOURCE_WRITTEN', 'source_sha256': sha(result)}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
