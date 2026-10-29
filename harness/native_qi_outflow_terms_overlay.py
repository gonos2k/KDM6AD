"""Add an independent opt-in QI lower-owner outflow trace to the pinned host source.

Array and record coordinates use (i,k,j). The first snapshot is after all
FLUX_OUT assignments and before any limiter mutation. No model values change.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

SOURCE_SHA = 'cb8882c7e7dd3646ed1b2793b6735b9326580dbd06c7652930d5da40e274c898'

def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()

def replace_once(text: str, anchor: str, replacement: str) -> str:
    if text.count(anchor) != 1:
        raise ValueError(f'Expected one source anchor: {anchor[:100]!r}')
    return text.replace(anchor, replacement, 1)

ROUTINES = '''
  SUBROUTINE qi_outflow_context(selected,step,rk,nranks)
    LOGICAL, INTENT(IN) :: selected
    INTEGER, INTENT(IN) :: step,rk,nranks
    CHARACTER(LEN=4096) :: env,filename
    INTEGER :: length,status,ios
    qi_out_selected=.FALSE.
    IF (.NOT.selected) RETURN
    IF (.NOT.qi_out_initialized) THEN
      qi_out_initialized=.TRUE.
      env=''
      CALL GET_ENVIRONMENT_VARIABLE('KDM6AD_QI_OUTFLOW_TRACE_DIR', &
           VALUE=env,LENGTH=length,STATUS=status)
      IF (status.NE.1 .AND. length.GT.0) THEN
        IF (status.NE.0 .OR. length.GT.LEN(env)) &
             ERROR STOP 'QI outflow trace directory invalid'
        filename=TRIM(env)//'/qi_outflow.tsv'
        OPEN(NEWUNIT=qi_out_unit,FILE=TRIM(filename),STATUS='NEW',ACTION='WRITE',IOSTAT=ios)
        IF (ios.NE.0) ERROR STOP 'QI outflow trace requires fresh file'
        WRITE(qi_out_unit,'(A)') '# KDM6AD_QI_OUTFLOW_TERMS_V1'
        WRITE(qi_out_unit,'(A)') '# BASE_ADVECT_SHA256 cb8882c7e7dd3646ed1b2793b6735b9326580dbd06c7652930d5da40e274c898'
        WRITE(qi_out_unit,'(A)') '# VAL step rk stage i k j field dtype raw_word_hex'
        qi_out_active=.TRUE.
      END IF
    END IF
    IF (.NOT.qi_out_active) RETURN
    IF (nranks.NE.1 .OR. .NOT.qi_face_env_one('OMP_NUM_THREADS') .OR. &
        .NOT.qi_face_env_one('MKL_NUM_THREADS') .OR. &
        .NOT.qi_face_env_one('OMP_THREAD_LIMIT') .OR. &
        .NOT.qi_face_env_one('VECLIB_MAXIMUM_THREADS')) &
         ERROR STOP 'QI outflow trace requires one MPI rank and one thread'
    qi_out_step=step
    qi_out_rk=rk
    qi_out_selected=.TRUE.
  END SUBROUTINE qi_outflow_context

  SUBROUTINE qi_out_real(stage,i,k,j,name,value)
    CHARACTER(LEN=*), INTENT(IN) :: stage,name
    INTEGER, INTENT(IN) :: i,k,j
    REAL, INTENT(IN) :: value
    WRITE(qi_out_unit,'(A,1X,I0,1X,I0,1X,A,1X,I0,1X,I0,1X,I0,1X,A,1X,A,1X,Z8.8)') &
         'VAL',qi_out_step,qi_out_rk,TRIM(stage),i,k,j,TRIM(name),'f32',TRANSFER(value,0_C_INT32_T)
  END SUBROUTINE qi_out_real

  SUBROUTINE qi_out_int(stage,i,k,j,name,value)
    CHARACTER(LEN=*), INTENT(IN) :: stage,name
    INTEGER, INTENT(IN) :: i,k,j,value
    WRITE(qi_out_unit,'(A,1X,I0,1X,I0,1X,A,1X,I0,1X,I0,1X,I0,1X,A,1X,A,1X,Z8.8)') &
         'VAL',qi_out_step,qi_out_rk,TRIM(stage),i,k,j,TRIM(name),'i32',INT(value,C_INT32_T)
  END SUBROUTINE qi_out_int
'''

def emit(stage: str, name: str, expr: str, k: int = 32) -> str:
    return f"     CALL qi_out_real('{stage}',2,{k},168,'{name}',{expr})\n"

def render(source: bytes) -> bytes:
    if sha(source) != SOURCE_SHA:
        raise ValueError('QI face producer source SHA mismatch')
    text = source.decode('utf-8')
    anchor = '  PUBLIC :: qi_face_trace_set_context\n'
    text = replace_once(text, anchor, anchor + '''  INTEGER, SAVE, PRIVATE :: qi_out_unit=0,qi_out_step=0,qi_out_rk=0
  LOGICAL, SAVE, PRIVATE :: qi_out_initialized=.FALSE.,qi_out_active=.FALSE.,qi_out_selected=.FALSE.
  PRIVATE :: qi_outflow_context,qi_out_real,qi_out_int
''')
    anchor = '  SUBROUTINE qi_face_trace_set_context(selected,step,rk,nranks)\n'
    text = replace_once(text, anchor, ROUTINES + '\n' + anchor)
    anchor = '    qi_face_selected=.FALSE.\n    IF (.NOT.selected) RETURN\n'
    text = replace_once(text, anchor, '    CALL qi_outflow_context(selected,step,rk,nranks)\n' + anchor)
    start = text.index('SUBROUTINE advect_scalar_pd')
    end = text.index('END SUBROUTINE advect_scalar_pd', start)
    block = text[start:end]
    faces = {'FX_WEST':'fqx(2,32,168)', 'FX_EAST':'fqx(3,32,168)',
             'FY_SOUTH':'fqy(2,32,168)', 'FY_NORTH':'fqy(2,32,169)',
             'FZ_BOTTOM':'fqz(2,32,168)', 'FZ_TOP':'fqz(2,33,168)'}
    low = {name: expr.replace('fqx(', 'fqxl(').replace('fqy(', 'fqyl(').replace('fqz(', 'fqzl(') for name, expr in faces.items()}
    gate = '''   IF (qi_out_selected .AND. qi_out_rk.EQ.3 .AND. &
       2.GE.its .AND. 2.LE.ite .AND. 168.GE.jts .AND. 168.LE.jte .AND. &
       32.GE.kts .AND. 33.LE.ktf) THEN
     IF (i_start.GT.2 .OR. i_end.LT.2 .OR. j_start.GT.168 .OR. j_end.LT.168) &
          ERROR STOP 'QI outflow owner outside limiter bounds'
'''
    snapshot = gate
    for stage, mapping in [('PRE', faces), ('LOW', low)]:
        for name, expr in mapping.items(): snapshot += emit(stage, name, expr)
    inputs = {'DT':'dt','MSFTX':'msftx(2,168)','MSFTY':'msfty(2,168)',
              'RDX':'rdx','RDY':'rdy','RDZW':'rdzw(32)', 'FIELD_OLD':'field_old(2,32,168)',
              'C1':'c1(32)','C2':'c2(32)','MU_OLD':'mu_old(2,168)','MUB':'mub(2,168)',
              'PH_LOW':'ph_low(2,32,168)','FLUX_OUT':'flux_out(2,32,168)'}
    for name, expr in inputs.items(): snapshot += emit('INPUT', name, expr)
    for name, expr in {'VERT_ORDER':'vert_order','HORZ_ORDER':'horz_order',
                       'KTS':'kts','KTF':'ktf','I_START':'i_start','I_END':'i_end',
                       'J_START':'j_start','J_END':'j_end'}.items():
        snapshot += f"     CALL qi_out_int('META',2,32,168,'{name}',{expr})\n"
    snapshot += '''     IF (vert_order.EQ.3 .AND. kts+2.LE.32 .AND. 33.LE.ktf-1) THEN
'''
    for level in (32,33):
        for name, expr in {'ROM':f'rom(2,{level},168)','RDZW':f'rdzw({level})',
                           'RDZW_PREV':f'rdzw({level-1})','C1':f'c1({level})',
                           'C2':f'c2({level})','MUT':'mut(2,168)'}.items():
            snapshot += emit('VERT',name,expr,level)
        for offset in (-2,-1,0,1):
            snapshot += emit('VERT', f'FIELD_{offset:+d}'.replace('+','P').replace('-','M'),
                             f'field(2,{level+offset},168)',level)
        for offset in (-1,0):
            snapshot += emit('VERT',f'OLD_{offset:+d}'.replace('+','P').replace('-','M'),
                             f'field_old(2,{level+offset},168)',level)
    snapshot += '''     END IF
     FLUSH(qi_out_unit)
   END IF
'''
    anchor = "  IF(qnc_trace_selected .AND. 113.GE.its .AND. 113.LE.ite .AND. &\n     70.GE.jts .AND. 70.LE.jte .AND. 12.GE.kts .AND. 12.LT.kte) THEN\n  CALL qnc_flux_trace_real('RK3_PD_PRE_LIMIT'"
    block = replace_once(block, anchor, snapshot + anchor)
    anchor = '     IF( flux_out(i,k,j) .gt. ph_low(i,k,j) ) THEN\n'
    visit = '''     IF (qi_out_selected .AND. qi_out_rk.EQ.3 .AND. &
         2.GE.its .AND. 2.LE.ite .AND. 168.GE.jts .AND. 168.LE.jte .AND. &
         32.GE.kts .AND. 33.LE.ktf .AND. &
         i.EQ.2 .AND. k.EQ.32 .AND. j.EQ.168) THEN
'''
    for name, expr in faces.items(): visit += emit('VISIT', name, expr)
    visit += '       FLUSH(qi_out_unit)\n     END IF\n'
    block = replace_once(block, anchor, visit + anchor)
    return (text[:start] + block + text[end:]).encode('utf-8')

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--advect-source', required=True, type=Path)
    parser.add_argument('--advect-output', required=True, type=Path)
    args = parser.parse_args()
    if args.advect_source.resolve() == args.advect_output.resolve() or args.advect_output.exists() or args.advect_output.is_symlink() or args.advect_output.parent.is_symlink():
        raise FileExistsError('Output must be fresh and distinct from input')
    result = render(args.advect_source.read_bytes())
    args.advect_output.parent.mkdir(parents=True, exist_ok=True)
    with args.advect_output.open('xb') as output: output.write(result)
    print(json.dumps({'status':'QI_OUTFLOW_SOURCE_WRITTEN','advect_sha256':sha(result)},sort_keys=True))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
