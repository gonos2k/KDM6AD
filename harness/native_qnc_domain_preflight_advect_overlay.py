"""Render an opt-in QNC RK3 failed-layer operand trace into PR471 source.

The overlay only inserts guarded I/O after the existing PD scale application.
It does not change limiter decisions, face words, or tendency/state updates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ADVECT_SOURCE_SHA256 = "1da7a56d7099ad47095146f0404e74ab39ad406ef87557aea69309c271c2e988"
FAILURE_JSON_SHA256 = "fa7ba0a92ccec5f1b8001a3c218b8a737ca90c1b9ed4a24f6253e616c1f6257e"
TARGET_COORDS_SHA256 = "af3c2f703b6d4ca54bd5dc22cb4aae04ea702070233bf02bdb92ed6648b99f53"
TARGET_COUNT = 54
TRACE_ENV = "KDM6AD_QNC_DOMAIN_PREFLIGHT_DIR"


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _replace(text: str, old: str, new: str, count: int = 1) -> str:
    if text.count(old) != count:
        raise ValueError(f"PR471 advection source anchor differs: {old[:96]!r}")
    return text.replace(old, new)


def failure_layer_coordinates(raw: bytes) -> tuple[tuple[int, int, int], ...]:
    """Return sorted one-based (i,k,j) layers from the pinned M0 failure receipt."""
    if sha(raw) != FAILURE_JSON_SHA256:
        raise ValueError("PR466 residual_reason_rows.json SHA differs")
    try:
        data = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("failure-layer receipt is not valid JSON") from exc
    rows = data.get("rows")
    if (not isinstance(rows, list) or len(rows) != TARGET_COUNT or
            data.get("remaining_invalid_M0_profiles") != TARGET_COUNT or
            data.get("remaining_invalid_M0_channel_cells") != TARGET_COUNT * 7 or
            data.get("reason_profile_counts", {}).get("liquid_QC_positive_NC_nonpositive") != 53):
        raise ValueError("failure-layer receipt inventory differs")

    coords: list[tuple[int, int, int]] = []
    for row in rows:
        try:
            i, j = row["i_one_based"], row["j_one_based"]
            reason_levels = row["final_reason_levels_one_based"]
            witnesses = row["failing_level_words"]
        except (KeyError, TypeError) as exc:
            raise ValueError("failure-layer row schema differs") from exc
        if (type(i) is not int or type(j) is not int or i < 1 or j < 1 or
                not isinstance(reason_levels, dict) or not isinstance(witnesses, list)):
            raise ValueError("failure-layer row coordinates/reasons are invalid")
        liquid_levels = reason_levels.get("liquid_QC_positive_NC_nonpositive")
        if not isinstance(liquid_levels, list) or not liquid_levels:
            continue
        witnesses_by_k = {}
        for item in witnesses:
            if not isinstance(item, dict) or type(item.get("native_k_one_based")) is not int:
                raise ValueError("failure-layer witness schema differs")
            k = item["native_k_one_based"]
            if k < 1:
                raise ValueError("failure-layer k coordinate is invalid")
            if k in witnesses_by_k:
                raise ValueError("failure-layer k witness is repeated")
            witnesses_by_k[k] = item
        for k in liquid_levels:
            item = witnesses_by_k.get(k)
            if item is None:
                raise ValueError("liquid failure layer lacks a raw-word witness")
            words = item.get("final_f32_hex")
            if not isinstance(words, dict):
                raise ValueError("liquid failure raw-word witness is malformed")
            try:
                qc = int(words["QCLOUD"], 16)
                qnc = int(words["QNCLOUD"], 16)
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("liquid failure raw words are malformed") from exc
            if (qc == 0 or qc & 0x80000000 or qnc & 0x7F800000 == 0x7F800000 or
                    (qnc != 0 and not (qnc & 0x80000000))):
                raise ValueError("target layer is not a finite QC-positive/NC-nonpositive failure")
            coords.append((i, k, j))

    result = tuple(sorted(coords))
    if len(result) != TARGET_COUNT or len(set(result)) != TARGET_COUNT:
        raise ValueError("failure-layer coordinates are not 54 unique layers")
    encoded = ("\n".join(f"{i},{k},{j}" for i, k, j in result) + "\n").encode("ascii")
    if sha(encoded) != TARGET_COORDS_SHA256:
        raise ValueError("derived failure-layer coordinate pin differs")
    return result


def _fortran_array(name: str, values: tuple[int, ...]) -> str:
    rows = [", ".join(str(value) for value in values[i:i + 12])
            for i in range(0, len(values), 12)]
    body = ", &\n       ".join(rows)
    return (f"  INTEGER, PARAMETER, PRIVATE :: {name}(QNC_PREF_NTARGET)=(/ &\n"
            f"       {body} /)")


def _module_declarations(coords: tuple[tuple[int, int, int], ...]) -> str:
    ci = _fortran_array("QNC_PREF_I", tuple(coord[0] for coord in coords))
    ck = _fortran_array("QNC_PREF_K", tuple(coord[1] for coord in coords))
    cj = _fortran_array("QNC_PREF_J", tuple(coord[2] for coord in coords))
    return f"""
  INTEGER, PARAMETER, PRIVATE :: QNC_PREF_NTARGET={len(coords)}
{ci}
{ck}
{cj}
  INTEGER, SAVE, PRIVATE :: qnc_pref_unit=0, qnc_pref_call=0
  LOGICAL, SAVE, PRIVATE :: qnc_pref_initialized=.FALSE., qnc_pref_active=.FALSE.
  PRIVATE :: qnc_domain_preflight_init,qnc_domain_preflight_begin
  PRIVATE :: qnc_domain_preflight_target,qnc_domain_preflight_emit,qnc_domain_preflight_end
"""


def _procedure_source() -> str:
    return f"""
  SUBROUTINE qnc_domain_preflight_init()
    CHARACTER(LEN=4096) :: env, filename
    INTEGER :: length, status, ios
    IF (qnc_pref_initialized) RETURN
    qnc_pref_initialized=.TRUE.
    env=''
    CALL get_environment_variable('{TRACE_ENV}',value=env,length=length,status=status)
    IF (status .EQ. 1 .OR. length .EQ. 0) RETURN
    IF (status .NE. 0 .OR. length .GT. LEN(env)) &
         ERROR STOP 'QNC domain preflight directory invalid'
    filename=TRIM(env)//'/qnc_domain_preflight.tsv'
    OPEN(NEWUNIT=qnc_pref_unit,FILE=TRIM(filename),STATUS='NEW',ACTION='WRITE',IOSTAT=ios)
    IF (ios .NE. 0) ERROR STOP 'QNC domain preflight requires a fresh writable file'
    WRITE(qnc_pref_unit,'(A)') '# KDM6AD_QNC_DOMAIN_PREFLIGHT_V1'
    WRITE(qnc_pref_unit,'(A)') '# SOURCE_SHA256 {ADVECT_SOURCE_SHA256}'
    WRITE(qnc_pref_unit,'(A)') '# FAILURE_JSON_SHA256 {FAILURE_JSON_SHA256}'
    WRITE(qnc_pref_unit,'(A)') '# TARGET_COORDS_SHA256 {TARGET_COORDS_SHA256}'
    WRITE(qnc_pref_unit,'(A)') &
         '# CALL id time_step trace_step rk ids ide jds jde ims ime jms jme its ite jts jte kts kte dt_bits_hex'
    WRITE(qnc_pref_unit,'(A)') &
         '# VAL call time_step trace_step rk i k j ids ide jds jde ims ime jms jme its ite jts jte kts kte limit_hit ' // &
         'FIELD_OLD C1H C2H MU_OLD MU_BASE DT MSFTX MSFTY RDX RDY RDZW PH_LOW FLUX_OUT SCALE ' // &
         'FX_LOW_WEST FX_LOW_EAST FY_LOW_SOUTH FY_LOW_NORTH FZ_LOW_BOTTOM FZ_LOW_TOP ' // &
         'FX_POST_WEST FX_POST_EAST FY_POST_SOUTH FY_POST_NORTH FZ_POST_BOTTOM FZ_POST_TOP'
    qnc_pref_active=.TRUE.
    FLUSH(qnc_pref_unit)
  END SUBROUTINE qnc_domain_preflight_init

  SUBROUTINE qnc_domain_preflight_begin(time_step,ids,ide,jds,jde,ims,ime,jms,jme, &
       its,ite,jts,jte,kts,kte)
    INTEGER,INTENT(IN) :: time_step,ids,ide,jds,jde,ims,ime,jms,jme,its,ite,jts,jte,kts,kte
    INTEGER(C_INT32_T) :: dt_bits
    CALL qnc_domain_preflight_init()
    IF (.NOT.qnc_pref_active) RETURN
    qnc_pref_call=qnc_pref_call+1
    dt_bits=TRANSFER(qnc_trace_dt,0_C_INT32_T)
    WRITE(qnc_pref_unit,'(A,1X,18(I0,1X),Z8.8)') 'CALL',qnc_pref_call,time_step, &
         qnc_trace_step,qnc_trace_rk,ids,ide,jds,jde,ims,ime,jms,jme, &
         its,ite,jts,jte,kts,kte,dt_bits
  END SUBROUTINE qnc_domain_preflight_begin

  INTEGER FUNCTION qnc_domain_preflight_target(i,k,j)
    INTEGER,INTENT(IN) :: i,k,j
    INTEGER :: lo,hi,mid
    qnc_domain_preflight_target=0
    lo=1
    hi=QNC_PREF_NTARGET
    DO WHILE (lo .LE. hi)
      mid=(lo+hi)/2
      IF (i .LT. QNC_PREF_I(mid)) THEN
        hi=mid-1
      ELSE IF (i .GT. QNC_PREF_I(mid)) THEN
        lo=mid+1
      ELSE IF (k .LT. QNC_PREF_K(mid)) THEN
        hi=mid-1
      ELSE IF (k .GT. QNC_PREF_K(mid)) THEN
        lo=mid+1
      ELSE IF (j .LT. QNC_PREF_J(mid)) THEN
        hi=mid-1
      ELSE IF (j .GT. QNC_PREF_J(mid)) THEN
        lo=mid+1
      ELSE
        qnc_domain_preflight_target=mid
        RETURN
      END IF
    END DO
  END FUNCTION qnc_domain_preflight_target

  SUBROUTINE qnc_domain_preflight_emit(time_step,i,k,j,ids,ide,jds,jde,ims,ime,jms,jme, &
       its,ite,jts,jte,kts,kte,limit_hit,values)
    INTEGER,INTENT(IN) :: time_step,i,k,j,ids,ide,jds,jde,ims,ime,jms,jme
    INTEGER,INTENT(IN) :: its,ite,jts,jte,kts,kte,limit_hit
    REAL,INTENT(IN) :: values(26)
    INTEGER(C_INT32_T) :: words(26)
    INTEGER :: n
    IF (.NOT.qnc_pref_active) RETURN
    DO n=1,26
      words(n)=TRANSFER(values(n),0_C_INT32_T)
    END DO
    WRITE(qnc_pref_unit,'(A,1X,22(I0,1X),26(Z8.8,1X))') 'VAL',qnc_pref_call, &
         time_step,qnc_trace_step,qnc_trace_rk,i,k,j,ids,ide,jds,jde,ims,ime,jms,jme, &
         its,ite,jts,jte,kts,kte,limit_hit,words
  END SUBROUTINE qnc_domain_preflight_emit

  SUBROUTINE qnc_domain_preflight_end()
    IF (qnc_pref_active) FLUSH(qnc_pref_unit)
  END SUBROUTINE qnc_domain_preflight_end
"""


def render_advect(raw: bytes, failure_json: bytes) -> bytes:
    if sha(raw) != ADVECT_SOURCE_SHA256:
        raise ValueError("PR471 private advection source SHA differs")
    coords = failure_layer_coordinates(failure_json)
    text = raw.decode("utf-8")
    marker = ("  LOGICAL, SAVE, PRIVATE :: qnc_shared_initialized=.FALSE., &\n"
              "       qnc_shared_active=.FALSE., qnc_shared_owner=.FALSE.\n\nCONTAINS")
    declarations = _module_declarations(coords)
    with_declarations = marker.replace(
        "\n\nCONTAINS", "\n" + declarations + "\nCONTAINS")
    text = _replace(text, marker, with_declarations)
    text = _replace(text, "CONTAINS\n", "CONTAINS\n" + _procedure_source(), count=1)
    sub_start = text.index("SUBROUTINE advect_scalar_pd")
    sub_end = text.index("END SUBROUTINE advect_scalar_pd", sub_start) + len("END SUBROUTINE advect_scalar_pd")
    block = text[sub_start:sub_end]

    decl_anchor = "   REAL :: scale\n"
    decl_new = (decl_anchor +
                "   REAL :: qnc_pref_scale(QNC_PREF_NTARGET)\n"
                "   INTEGER :: qnc_pref_hit(QNC_PREF_NTARGET)\n"
                "   LOGICAL :: qnc_pref_seen(QNC_PREF_NTARGET)\n"
                "   INTEGER :: qnc_pref_n,qnc_pref_index,qnc_pref_cell_i,qnc_pref_cell_k,qnc_pref_cell_j\n")
    block = _replace(block, decl_anchor, decl_new)

    begin_anchor = ("   DO j=j_start, j_end\n   DO k=kts, ktf\n!DIR$ vector always\n"
                    "   DO i=i_start, i_end\n\n     ph_low(i,k,j) = ((c1(k)*mub(i,j)+c2(k))+")
    begin_new = ("   IF (qnc_trace_selected .AND. qnc_trace_rk .EQ. 3) THEN\n"
                 "     CALL qnc_domain_preflight_begin(time_step,ids,ide,jds,jde,ims,ime,jms,jme, &\n"
                 "          its,ite,jts,jte,kts,kte)\n"
                 "     IF (qnc_pref_active) THEN\n"
                 "       qnc_pref_scale=1.0\n"
                 "       qnc_pref_hit=0\n"
                 "       qnc_pref_seen=.FALSE.\n"
                 "     END IF\n"
                 "   END IF\n" + begin_anchor)
    block = _replace(block, begin_anchor, begin_new)

    emit_anchor = ("     IF(qnc_trace_selected .AND. qnc_trace_rk.EQ.3) THEN\n"
                   "       IF(ABS(i-113)+ABS(k-12)+ABS(j-70).LE.1) THEN\n"
                   "         IF(flux_out(i,k,j).GT.ph_low(i,k,j)) THEN\n"
                   "           CALL qnc_flux_trace_limit(i,k,j,ph_low(i,k,j),flux_out(i,k,j),scale,.TRUE.)\n"
                   "         ELSE\n"
                   "           CALL qnc_flux_trace_limit(i,k,j,ph_low(i,k,j),flux_out(i,k,j),1.0,.FALSE.)\n"
                   "         END IF\n"
                   "       END IF\n"
                   "     END IF\n\n   ENDDO")
    remember = """     IF (qnc_trace_selected .AND. qnc_trace_rk .EQ. 3 .AND. qnc_pref_active) THEN
       qnc_pref_index=qnc_domain_preflight_target(i,k,j)
       IF (qnc_pref_index .NE. 0) THEN
         qnc_pref_seen(qnc_pref_index)=.TRUE.
         IF (flux_out(i,k,j) .GT. ph_low(i,k,j)) THEN
           qnc_pref_scale(qnc_pref_index)=scale
           qnc_pref_hit(qnc_pref_index)=1
         ELSE
           qnc_pref_scale(qnc_pref_index)=1.0
           qnc_pref_hit(qnc_pref_index)=0
         END IF
       END IF
     END IF

   ENDDO"""
    emit_new = emit_anchor[:-len("\n\n   ENDDO")] + "\n" + remember
    block = _replace(block, emit_anchor, emit_new)

    finish_anchor = "   ENDDO\n   ENDDO\n   ENDDO\n\n   END IF\n\n\n\n  IF(qnc_trace_selected .AND. 113.GE.its"
    finish_new = """   ENDDO
   ENDDO
   ENDDO
   IF (qnc_trace_selected .AND. qnc_trace_rk .EQ. 3 .AND. qnc_pref_active) THEN
     DO qnc_pref_n=1,QNC_PREF_NTARGET
       qnc_pref_cell_i=QNC_PREF_I(qnc_pref_n)
       qnc_pref_cell_k=QNC_PREF_K(qnc_pref_n)
       qnc_pref_cell_j=QNC_PREF_J(qnc_pref_n)
       IF (qnc_pref_seen(qnc_pref_n) .AND. &
           qnc_pref_cell_i.GE.its .AND. qnc_pref_cell_i.LE.MIN(ite,ide-1) .AND. &
           qnc_pref_cell_j.GE.jts .AND. qnc_pref_cell_j.LE.MIN(jte,jde-1) .AND. &
           qnc_pref_cell_k.GE.kts .AND. qnc_pref_cell_k.LE.ktf) THEN
         CALL qnc_domain_preflight_emit(time_step,qnc_pref_cell_i,qnc_pref_cell_k,qnc_pref_cell_j, &
              ids,ide,jds,jde,ims,ime,jms,jme,its,ite,jts,jte,kts,kte, &
              qnc_pref_hit(qnc_pref_n), &
              (/ field_old(qnc_pref_cell_i,qnc_pref_cell_k,qnc_pref_cell_j), &
              c1(qnc_pref_cell_k),c2(qnc_pref_cell_k), &
              mu_old(qnc_pref_cell_i,qnc_pref_cell_j),mub(qnc_pref_cell_i,qnc_pref_cell_j),dt, &
              msftx(qnc_pref_cell_i,qnc_pref_cell_j),msfty(qnc_pref_cell_i,qnc_pref_cell_j), &
              rdx,rdy,rdzw(qnc_pref_cell_k), &
              ph_low(qnc_pref_cell_i,qnc_pref_cell_k,qnc_pref_cell_j), &
              flux_out(qnc_pref_cell_i,qnc_pref_cell_k,qnc_pref_cell_j),qnc_pref_scale(qnc_pref_n), &
              fqxl(qnc_pref_cell_i,qnc_pref_cell_k,qnc_pref_cell_j), &
              fqxl(qnc_pref_cell_i+1,qnc_pref_cell_k,qnc_pref_cell_j), &
              fqyl(qnc_pref_cell_i,qnc_pref_cell_k,qnc_pref_cell_j), &
              fqyl(qnc_pref_cell_i,qnc_pref_cell_k,qnc_pref_cell_j+1), &
              fqzl(qnc_pref_cell_i,qnc_pref_cell_k,qnc_pref_cell_j), &
              fqzl(qnc_pref_cell_i,qnc_pref_cell_k+1,qnc_pref_cell_j), &
              fqx(qnc_pref_cell_i,qnc_pref_cell_k,qnc_pref_cell_j), &
              fqx(qnc_pref_cell_i+1,qnc_pref_cell_k,qnc_pref_cell_j), &
              fqy(qnc_pref_cell_i,qnc_pref_cell_k,qnc_pref_cell_j), &
              fqy(qnc_pref_cell_i,qnc_pref_cell_k,qnc_pref_cell_j+1), &
              fqz(qnc_pref_cell_i,qnc_pref_cell_k,qnc_pref_cell_j), &
              fqz(qnc_pref_cell_i,qnc_pref_cell_k+1,qnc_pref_cell_j)/))
       END IF
     END DO
     CALL qnc_domain_preflight_end()
   END IF

   END IF



  IF(qnc_trace_selected .AND. 113.GE.its"""
    block = _replace(block, finish_anchor, finish_new)

    if (block.count("CALL qnc_domain_preflight_emit(") != 1 or
            block.count("qnc_domain_preflight_remember") != 0 or
            block.count("qnc_domain_preflight_target(i,k,j)") != 1 or
            block.count("qnc_domain_preflight_begin(time_step") != 1 or
            block.count("qnc_domain_preflight_end()") != 1):
        raise ValueError("preflight writer insertion inventory differs")
    text = text[:sub_start] + block + text[sub_end:]
    return text.encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--advect-source", type=Path, required=True)
    parser.add_argument("--failure-json", type=Path, required=True)
    parser.add_argument("--advect-output", type=Path, required=True)
    args = parser.parse_args()
    output = args.advect_output
    if (output.exists() or output.is_symlink() or
            output.resolve() == args.advect_source.resolve() or
            output.resolve() == args.failure_json.resolve()):
        raise FileExistsError("overlay output must be a new file distinct from pinned inputs")
    rendered = render_advect(args.advect_source.read_bytes(), args.failure_json.read_bytes())
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(rendered)
    coords = failure_layer_coordinates(args.failure_json.read_bytes())
    print(json.dumps({"status": "QNC_DOMAIN_PREFLIGHT_SOURCE_WRITTEN",
                      "source_sha256": ADVECT_SOURCE_SHA256,
                      "failure_json_sha256": FAILURE_JSON_SHA256,
                      "target_coords_sha256": TARGET_COORDS_SHA256,
                      "target_layers": len(coords),
                      "advect_output_sha256": sha(rendered)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
