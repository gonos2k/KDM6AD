#!/usr/bin/env python3
"""Build and compare a bounded shadow trace of G4's first resumed RK physics.

The overlay is generated from private host sources supplied by the caller. It
does not edit those sources. Its fixed sample is the five G4 columns selected
from model input before the restart comparison: clear, warm liquid, mixed,
ice and rain. Values are written as exact binary32 words in text form.

The native trace is intentionally bounded to one domain and step 2. It can
locate the first differing producer among the emitted fields at those five
columns; it cannot prove the first divergence elsewhere in the full domain.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
from typing import Any


FIRST_RK_PIN = "108a82b213c423acf916b91a0dd5f8084dc79288a01ca82d9f8d0ccb8febd53f"
TARGET_STEP = 2
EXPECTED_MASS_LEVELS = 39
EXPECTED_INTERFACE_LEVELS = 40
EXPECTED_SOIL_LEVELS = 4
EXPECTED_MASS_BOUNDS = (1, 39)
EXPECTED_INTERFACE_BOUNDS = (1, 40)
EXPECTED_MOIST_SPECIES = 7
EXPECTED_SCALAR_SPECIES = 6
PROBE_COORDINATES = (
    ("clear", 145, 11),
    ("warm_liquid", 139, 106),
    ("mixed", 124, 144),
    ("ice", 130, 209),
    ("rain", 112, 212),
)

FIRST_RK_ANCHORS = (
    (0, "    rk_step = 1", "after"),
    (1, "BENCH_END(phy_prep_tim)", "after"),
    (2, "BENCH_END(rad_driver_tim)", "after"),
    (3, "BENCH_END(surf_driver_tim)", "after"),
    (4, "BENCH_END(pbl_driver_tim)", "after"),
    (6, "BENCH_END(cu_driver_tim)", "after"),
    (7, "BENCH_END(shcu_driver_tim)", "after"),
    (8, "BENCH_END(fdda_driver_tim)", "after"),
)

_GUARD = "KDM6AD_G4_RESTART_PROBE"
EXPECTED_STAGES = tuple(stage for stage, _, _ in FIRST_RK_ANCHORS)
MASS_FIELDS = {
    "U2", "V2", "T2", "RTHRATEN", "RTHRATENLW", "RTHRATENSW",
    "RUBLTEN", "RVBLTEN", "RTHBLTEN", "RQVBLTEN", "RQCblTEN",
    "RQIBLTEN", "TPHY", "PPHY", "PIPHY",
}
INTERFACE_FIELDS = {"W2", "PH2"}
SOIL_FIELDS = {"TSLB", "SMOIS", "SH2O"}
SURFACE_FIELDS = {
    "TIMESTEP", "STEPRA", "RADTACTTIME", "BLDTACTTIME", "CUDTACTTIME",
    "RADT", "BLDT", "ADAPT", "SWDOWN", "GLW", "HFX", "LH", "QFX",
    "GRDFLX", "TSK", "PBLH", "UST", "MU2", "MUB",
}


class ProbeError(ValueError):
    """The host overlay or its captured records are incomplete."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _call(stage: int) -> str:
    return (
        f"#ifdef {_GUARD}\n"
        f"      CALL g4_restart_snapshot ( {stage}, grid, moist, scalar, &\n"
        "           t_phy, p_phy, pi_phy, adapt_step_flag, &\n"
        "           ims, ime, jms, jme, kms, kme, k_start, k_end, kde )\n"
        "#endif\n"
    )


def _physics_helper() -> str:
    coords = ", ".join(str(x) for _, j, i in PROBE_COORDINATES for x in (i, j))
    return f'''#ifdef {_GUARD}

   SUBROUTINE g4_restart_snapshot ( stage, grid, moist, scalar, &
                                    t_phy, p_phy, pi_phy, adapt_step_flag, &
                                    ims, ime, jms, jme, kms, kme, k_start, k_end, kde )
      USE, INTRINSIC :: ISO_FORTRAN_ENV, ONLY : INT32
      USE module_domain, ONLY : domain
      USE module_state_description, ONLY : num_moist, num_scalar
      IMPLICIT NONE
      INTEGER, INTENT(IN) :: stage, ims, ime, jms, jme, kms, kme, k_start, k_end, kde
      TYPE(domain), INTENT(IN) :: grid
      REAL, INTENT(IN) :: moist(ims:ime,kms:kme,jms:jme,num_moist)
      REAL, INTENT(IN) :: scalar(ims:ime,kms:kme,jms:jme,num_scalar)
      REAL, INTENT(IN) :: t_phy(ims:ime,kms:kme,jms:jme)
      REAL, INTENT(IN) :: p_phy(ims:ime,kms:kme,jms:jme)
      REAL, INTENT(IN) :: pi_phy(ims:ime,kms:kme,jms:jme)
      LOGICAL, INTENT(IN) :: adapt_step_flag
      INTEGER, PARAMETER :: nprobe=5
      INTEGER, PARAMETER :: probe_ij(2,nprobe)=RESHAPE((/ {coords} /),(/2,nprobe/))
      CHARACTER(LEN=16), PARAMETER :: probe_name(nprobe) = (/ &
           'clear           ', 'warm_liquid     ', 'mixed           ', &
           'ice             ', 'rain            ' /)
      CHARACTER(LEN=512) :: prefix, path
      CHARACTER(LEN=24) :: rank_text
      INTEGER :: status, unit, sample, i, j, k, m
      INTEGER :: nsoil, mass_first, mass_last, interface_first, interface_last

      IF ( grid%itimestep /= {TARGET_STEP} ) RETURN
      CALL GET_ENVIRONMENT_VARIABLE('KDM6AD_G4_RESTART_PROBE_PREFIX', &
                                    prefix, STATUS=status)
      IF ( status /= 0 .OR. LEN_TRIM(prefix) == 0 ) RETURN
      WRITE(rank_text,'(I0)') grid%id
      path = TRIM(prefix)//'.domain'//TRIM(rank_text)//'.log'
      OPEN(NEWUNIT=unit, FILE=TRIM(path), FORM='FORMATTED', &
           STATUS='UNKNOWN', POSITION='APPEND', ACTION='WRITE', IOSTAT=status)
      IF ( status /= 0 ) RETURN
      nsoil = SIZE(grid%smois,2)

      DO sample=1,nprobe
         i=probe_ij(1,sample); j=probe_ij(2,sample)
         IF ( i < ims .OR. i > ime .OR. j < jms .OR. j > jme ) CYCLE
         mass_first=MAX(kms,k_start)
         mass_last=MIN(kme,MIN(k_end,kde-1))
         interface_first=MAX(kms,k_start)
         interface_last=MIN(kme,k_end)
         WRITE(unit,'(A,1X,I0,1X,I0,1X,I0,1X,A,1X,9(I0,1X))') &
              'SAMPLE',stage,grid%itimestep,grid%id,TRIM(probe_name(sample)), &
              j,i,mass_first,mass_last,interface_first,interface_last, &
              num_moist,num_scalar,nsoil
         CALL g4_emit_2d(unit,stage,grid%itimestep,grid%id,probe_name(sample), &
                         j,i,0,'TIMESTEP',REAL(grid%itimestep))
         CALL g4_emit_2d(unit,stage,grid%itimestep,grid%id,probe_name(sample), &
                         j,i,0,'STEPRA',REAL(grid%stepra))
         CALL g4_emit_2d(unit,stage,grid%itimestep,grid%id,probe_name(sample), &
                         j,i,0,'RADTACTTIME',grid%radtacttime)
         CALL g4_emit_2d(unit,stage,grid%itimestep,grid%id,probe_name(sample), &
                         j,i,0,'BLDTACTTIME',grid%bldtacttime)
         CALL g4_emit_2d(unit,stage,grid%itimestep,grid%id,probe_name(sample), &
                         j,i,0,'CUDTACTTIME',grid%cudtacttime)
         CALL g4_emit_2d(unit,stage,grid%itimestep,grid%id,probe_name(sample), &
                         j,i,0,'RADT',grid%radt)
         CALL g4_emit_2d(unit,stage,grid%itimestep,grid%id,probe_name(sample), &
                         j,i,0,'BLDT',grid%bldt)
         CALL g4_emit_2d(unit,stage,grid%itimestep,grid%id,probe_name(sample), &
                         j,i,0,'ADAPT',MERGE(1.0,0.0,adapt_step_flag))
         CALL g4_emit_2d(unit,stage,grid%itimestep,grid%id,probe_name(sample), &
                         j,i,0,'MU2',grid%mu_2(i,j))
         CALL g4_emit_2d(unit,stage,grid%itimestep,grid%id,probe_name(sample), &
                         j,i,0,'MUB',grid%mub(i,j))
         DO k=mass_first,mass_last
            CALL g4_emit_3d(unit,stage,grid%itimestep,grid%id,probe_name(sample),j,i,k,'U2',grid%u_2)
            CALL g4_emit_3d(unit,stage,grid%itimestep,grid%id,probe_name(sample),j,i,k,'V2',grid%v_2)
            CALL g4_emit_3d(unit,stage,grid%itimestep,grid%id,probe_name(sample),j,i,k,'T2',grid%t_2)
            CALL g4_emit_3d(unit,stage,grid%itimestep,grid%id,probe_name(sample),j,i,k,'RTHRATEN',grid%rthraten)
            CALL g4_emit_3d(unit,stage,grid%itimestep,grid%id,probe_name(sample),j,i,k,'RTHRATENLW',grid%rthratenlw)
            CALL g4_emit_3d(unit,stage,grid%itimestep,grid%id,probe_name(sample),j,i,k,'RTHRATENSW',grid%rthratensw)
            CALL g4_emit_3d(unit,stage,grid%itimestep,grid%id,probe_name(sample),j,i,k,'RUBLTEN',grid%rublten)
            CALL g4_emit_3d(unit,stage,grid%itimestep,grid%id,probe_name(sample),j,i,k,'RVBLTEN',grid%rvblten)
            CALL g4_emit_3d(unit,stage,grid%itimestep,grid%id,probe_name(sample),j,i,k,'RTHBLTEN',grid%rthblten)
            CALL g4_emit_3d(unit,stage,grid%itimestep,grid%id,probe_name(sample),j,i,k,'RQVBLTEN',grid%rqvblten)
            CALL g4_emit_3d(unit,stage,grid%itimestep,grid%id,probe_name(sample),j,i,k,'RQCblTEN',grid%rqcblten)
            CALL g4_emit_3d(unit,stage,grid%itimestep,grid%id,probe_name(sample),j,i,k,'RQIBLTEN',grid%rqiblten)
            CALL g4_emit_3d(unit,stage,grid%itimestep,grid%id,probe_name(sample),j,i,k,'TPHY',t_phy)
            CALL g4_emit_3d(unit,stage,grid%itimestep,grid%id,probe_name(sample),j,i,k,'PPHY',p_phy)
            CALL g4_emit_3d(unit,stage,grid%itimestep,grid%id,probe_name(sample),j,i,k,'PIPHY',pi_phy)
            DO m=1,num_moist
               CALL g4_emit_4d(unit,stage,grid%itimestep,grid%id,probe_name(sample), &
                                j,i,k,'MOIST',m,moist)
            END DO
            DO m=1,num_scalar
               CALL g4_emit_4d(unit,stage,grid%itimestep,grid%id,probe_name(sample), &
                                j,i,k,'SCALAR',m,scalar)
            END DO
         END DO
         DO k=interface_first,interface_last
            CALL g4_emit_3d(unit,stage,grid%itimestep,grid%id,probe_name(sample),j,i,k,'W2',grid%w_2)
            CALL g4_emit_3d(unit,stage,grid%itimestep,grid%id,probe_name(sample),j,i,k,'PH2',grid%ph_2)
         END DO
         DO k=1,nsoil
            CALL g4_emit_3d(unit,stage,grid%itimestep,grid%id,probe_name(sample),j,i,k,'TSLB',grid%tslb)
            CALL g4_emit_3d(unit,stage,grid%itimestep,grid%id,probe_name(sample),j,i,k,'SMOIS',grid%smois)
            CALL g4_emit_3d(unit,stage,grid%itimestep,grid%id,probe_name(sample),j,i,k,'SH2O',grid%sh2o)
         END DO
         CALL g4_emit_2d(unit,stage,grid%itimestep,grid%id,probe_name(sample),j,i,0,'SWDOWN',grid%swdown(i,j))
         CALL g4_emit_2d(unit,stage,grid%itimestep,grid%id,probe_name(sample),j,i,0,'GLW',grid%glw(i,j))
         CALL g4_emit_2d(unit,stage,grid%itimestep,grid%id,probe_name(sample),j,i,0,'HFX',grid%hfx(i,j))
         CALL g4_emit_2d(unit,stage,grid%itimestep,grid%id,probe_name(sample),j,i,0,'LH',grid%lh(i,j))
         CALL g4_emit_2d(unit,stage,grid%itimestep,grid%id,probe_name(sample),j,i,0,'QFX',grid%qfx(i,j))
         CALL g4_emit_2d(unit,stage,grid%itimestep,grid%id,probe_name(sample),j,i,0,'GRDFLX',grid%grdflx(i,j))
         CALL g4_emit_2d(unit,stage,grid%itimestep,grid%id,probe_name(sample),j,i,0,'TSK',grid%tsk(i,j))
         CALL g4_emit_2d(unit,stage,grid%itimestep,grid%id,probe_name(sample),j,i,0,'PBLH',grid%pblh(i,j))
         CALL g4_emit_2d(unit,stage,grid%itimestep,grid%id,probe_name(sample),j,i,0,'UST',grid%ust(i,j))
      END DO
      CLOSE(unit)
   END SUBROUTINE g4_restart_snapshot

   SUBROUTINE g4_emit_2d(unit,stage,step,domain_id,name,j,i,k,field,value)
      USE, INTRINSIC :: ISO_FORTRAN_ENV, ONLY : INT32
      IMPLICIT NONE
      INTEGER,INTENT(IN)::unit,stage,step,domain_id,j,i,k
      CHARACTER(*),INTENT(IN)::name,field
      REAL,INTENT(IN)::value
      INTEGER(INT32)::word
      word=TRANSFER(value,word)
      WRITE(unit,'(6(I0,1X),A,1X,A,1X,Z8.8)') &
           stage,step,domain_id,j,i,k,TRIM(name),TRIM(field),word
   END SUBROUTINE g4_emit_2d

   SUBROUTINE g4_emit_3d(unit,stage,step,domain_id,name,j,i,k,field,a)
      USE, INTRINSIC :: ISO_FORTRAN_ENV, ONLY : INT32
      IMPLICIT NONE
      INTEGER,INTENT(IN)::unit,stage,step,domain_id,j,i,k
      CHARACTER(*),INTENT(IN)::name,field
      REAL,INTENT(IN)::a(:,:,:)
      INTEGER(INT32)::word
      INTEGER::ii,kk,jj
      ii=i-LBOUND(a,1)+1; kk=k-LBOUND(a,2)+1; jj=j-LBOUND(a,3)+1
      word=TRANSFER(a(ii,kk,jj),word)
      WRITE(unit,'(6(I0,1X),A,1X,A,1X,Z8.8)') &
           stage,step,domain_id,j,i,k,TRIM(name),TRIM(field),word
   END SUBROUTINE g4_emit_3d

   SUBROUTINE g4_emit_4d(unit,stage,step,domain_id,name,j,i,k,field,m,a)
      USE, INTRINSIC :: ISO_FORTRAN_ENV, ONLY : INT32
      IMPLICIT NONE
      INTEGER,INTENT(IN)::unit,stage,step,domain_id,j,i,k,m
      CHARACTER(*),INTENT(IN)::name,field
      REAL,INTENT(IN)::a(:,:,:,:)
      INTEGER(INT32)::word
      INTEGER::ii,kk,jj,mm
      ii=i-LBOUND(a,1)+1; kk=k-LBOUND(a,2)+1; jj=j-LBOUND(a,3)+1
      mm=m-LBOUND(a,4)+1
      word=TRANSFER(a(ii,kk,jj,mm),word)
      WRITE(unit,'(6(I0,1X),A,1X,A,I0,1X,Z8.8)') &
           stage,step,domain_id,j,i,k,TRIM(name),TRIM(field),m,word
   END SUBROUTINE g4_emit_4d

#endif
'''


def build_first_rk_overlay(source: str) -> str:
    """Insert output-only snapshots around first-RK physics producers."""
    if _sha256(source.encode()) != FIRST_RK_PIN:
        raise ProbeError("module_first_rk_step_part1.F differs from its source pin")
    lines = source.splitlines(keepends=True)
    out: list[str] = [f"#define {_GUARD}\n"]
    placed: dict[int, bool] = {}
    for line in lines:
        key = line.rstrip("\n").strip()
        for stage, anchor, position in FIRST_RK_ANCHORS:
            if key == anchor.strip() and position == "before":
                if stage in placed:
                    raise ProbeError(f"duplicate first-RK anchor for stage {stage}")
                placed[stage] = True
                out.append(_call(stage))
        out.append(line)
        for stage, anchor, position in FIRST_RK_ANCHORS:
            if key == anchor.strip() and position == "after":
                if stage in placed:
                    raise ProbeError(f"duplicate first-RK anchor for stage {stage}")
                placed[stage] = True
                out.append(_call(stage))
    if set(placed) != {stage for stage, _, _ in FIRST_RK_ANCHORS}:
        missing = sorted({stage for stage, _, _ in FIRST_RK_ANCHORS} - set(placed))
        raise ProbeError(f"first-RK source anchors missing: {missing}")
    body = "".join(out)
    tail = "END MODULE module_first_rk_step_part1"
    if body.count(tail) != 1:
        raise ProbeError("expected one first-RK module tail")
    return body.replace(tail, _physics_helper() + tail, 1)


def strip_first_rk_overlay(source: str) -> str:
    """Remove this probe's guarded additions and require exact source recovery."""
    lines = source.splitlines(keepends=True)
    if not lines or lines[0] != f"#define {_GUARD}\n":
        raise ProbeError("missing first-RK overlay define")
    lines = lines[1:]
    out: list[str] = []
    depth = 0
    for line in lines:
        stripped = line.strip()
        if depth:
            if stripped.startswith(("#if", "#ifdef", "#ifndef")):
                depth += 1
            elif stripped.startswith("#endif"):
                depth -= 1
            continue
        if stripped == f"#ifdef {_GUARD}":
            depth = 1
            continue
        out.append(line)
    if depth:
        raise ProbeError("unbalanced restart-probe preprocessor guard")
    return "".join(out)


def parse_trace(path: Path) -> dict[tuple[int, int, int, str, int, int, int, str], int]:
    """Parse exact raw-word records; reject malformed and duplicate keys."""
    records: dict[tuple[int, int, int, str, int, int, int, str], int] = {}
    if not path.is_file():
        raise ProbeError(f"probe trace is missing: {path}")
    samples: dict[tuple[int, int, int, str, int, int], tuple[int, ...]] = {}
    opener = gzip.open if path.suffix == ".gz" else open
    try:
        with opener(path, "rt", encoding="ascii") as stream:
            lines = stream.read().splitlines()
    except (OSError, EOFError, UnicodeError) as exc:
        raise ProbeError(f"cannot read probe trace {path}: {exc}") from exc
    for line_no, line in enumerate(lines,1):
        parts=line.split()
        if not parts:
            continue
        if parts[0] == "SAMPLE":
            if len(parts) != 14:
                raise ProbeError(f"malformed sample header {path}:{line_no}")
            try:
                sample_key=(int(parts[1]),int(parts[2]),int(parts[3]),parts[4],
                            int(parts[5]),int(parts[6]))
                bounds=tuple(int(x) for x in parts[7:14])
            except ValueError as exc:
                raise ProbeError(f"invalid sample header {path}:{line_no}") from exc
            if sample_key in samples:
                raise ProbeError(f"duplicate sample header {sample_key}")
            samples[sample_key]=bounds
            continue
        if len(parts) != 9:
            raise ProbeError(f"malformed trace row {path}:{line_no}")
        try:
            stage,step,domain_id,j,i,k=(int(x) for x in parts[:6])
            name,field=parts[6:8]
            word=parts[8]
            if re.fullmatch(r"[0-9A-F]{8}",word) is None:
                raise ValueError("word is not eight uppercase hex digits")
        except ValueError as exc:
            raise ProbeError(f"invalid trace row {path}:{line_no}: {exc}") from exc
        key=(stage,step,domain_id,name,j,i,k,field)
        if key in records:
            raise ProbeError(f"duplicate trace key {key} at {path}:{line_no}")
        records[key]=int(word,16)
    if len(records)==0:
        raise ProbeError(f"probe trace has no value rows: {path}")
    expected_samples={
        (stage,TARGET_STEP,1,name,j,i)
        for stage in EXPECTED_STAGES
        for name,j,i in PROBE_COORDINATES
    }
    if set(samples) != expected_samples:
        raise ProbeError(
            f"probe sample plan incomplete in {path}; missing="
            f"{sorted(expected_samples-set(samples))}, "
            f"unexpected={sorted(set(samples)-expected_samples)}"
        )
    for sample_key,bounds in samples.items():
        stage,step,domain_id,name,j,i=sample_key
        mass_first,mass_last,interface_first,interface_last,nmoist,nscalar,nsoil=bounds
        if step != TARGET_STEP or domain_id != 1:
            raise ProbeError(f"invalid sample metadata for {sample_key}: {bounds}")
        expected_bounds = (
            *EXPECTED_MASS_BOUNDS,
            *EXPECTED_INTERFACE_BOUNDS,
            EXPECTED_MOIST_SPECIES,
            EXPECTED_SCALAR_SPECIES,
            EXPECTED_SOIL_LEVELS,
        )
        if bounds != expected_bounds:
            raise ProbeError(
                f"G4 fixed vertical/species plan changed for {sample_key}: {bounds}"
            )
        expected_keys=set()
        for field in SURFACE_FIELDS:
            expected_keys.add((stage,step,domain_id,name,j,i,0,field))
        for field in MASS_FIELDS:
            expected_keys.update((stage,step,domain_id,name,j,i,k,field)
                                 for k in range(mass_first,mass_last+1))
        for field in INTERFACE_FIELDS:
            expected_keys.update((stage,step,domain_id,name,j,i,k,field)
                                 for k in range(interface_first,interface_last+1))
        for field in SOIL_FIELDS:
            expected_keys.update((stage,step,domain_id,name,j,i,k,field)
                                 for k in range(1,nsoil+1))
        for member in range(1, EXPECTED_MOIST_SPECIES + 1):
            expected_keys.update((stage,step,domain_id,name,j,i,k,f"MOIST{member}")
                                 for k in range(mass_first,mass_last+1))
        for member in range(1, EXPECTED_SCALAR_SPECIES + 1):
            expected_keys.update((stage,step,domain_id,name,j,i,k,f"SCALAR{member}")
                                 for k in range(mass_first,mass_last+1))
        actual_keys={key for key in records if key[:6]==sample_key}
        if actual_keys!=expected_keys:
            raise ProbeError(
                f"trace field/level coverage incomplete at stage={stage} {name} "
                f"j={j} i={i}: missing={sorted(expected_keys-actual_keys)[:20]}, "
                f"unexpected={sorted(actual_keys-expected_keys)[:20]}"
            )
    expected_record_keys = {
        (stage, step, domain_id, name, j, i, k, field)
        for sample_key in expected_samples
        for stage, step, domain_id, name, j, i in (sample_key,)
        for k, field in (
            [(0, field) for field in SURFACE_FIELDS]
            + [(k, field) for field in MASS_FIELDS
               for k in range(EXPECTED_MASS_BOUNDS[0], EXPECTED_MASS_BOUNDS[1] + 1)]
            + [(k, field) for field in INTERFACE_FIELDS for k in range(EXPECTED_INTERFACE_BOUNDS[0], EXPECTED_INTERFACE_BOUNDS[1] + 1)]
            + [(k, field) for field in SOIL_FIELDS for k in range(1, EXPECTED_SOIL_LEVELS + 1)]
            + [(k, f"MOIST{member}") for member in range(1, EXPECTED_MOIST_SPECIES + 1)
               for k in range(EXPECTED_MASS_BOUNDS[0], EXPECTED_MASS_BOUNDS[1] + 1)]
            + [(k, f"SCALAR{member}") for member in range(1, EXPECTED_SCALAR_SPECIES + 1)
               for k in range(EXPECTED_MASS_BOUNDS[0], EXPECTED_MASS_BOUNDS[1] + 1)]
        )
    }
    if set(records) != expected_record_keys:
        raise ProbeError(
            "trace global record universe incomplete; "
            f"missing={sorted(expected_record_keys-set(records))[:20]}, "
            f"unexpected={sorted(set(records)-expected_record_keys)[:20]}"
        )
    return records


def compare_traces(left_path: Path, right_path: Path) -> dict[str, Any]:
    left=parse_trace(left_path)
    right=parse_trace(right_path)
    if set(left)!=set(right):
        missing_left=sorted(set(right)-set(left))[:20]
        missing_right=sorted(set(left)-set(right))[:20]
        raise ProbeError(f"trace event sets differ; left missing={missing_left}, right missing={missing_right}")
    differences=[]
    for key in sorted(left):
        if left[key]!=right[key]:
            stage,step,domain_id,name,j,i,k,field=key
            differences.append({"stage":stage,"step":step,"domain":domain_id,
                                "sample":name,"j":j,"i":i,"k":k,"field":field,
                                "continuous_word":f"{left[key]:08X}",
                                "restart_word":f"{right[key]:08X}"})
    stages=sorted({key[0] for key in left})
    first_stage=next((stage for stage in stages if any(x["stage"]==stage for x in differences)),None)
    return {
        "schema":"g4-restart-first-rk-trace-v1",
        "comparison":"continuous_step2_vs_restart_step2",
        "records_compared":len(left),
        "raw_word_equal":not differences,
        "first_differing_stage":first_stage,
        "difference_count":len(differences),
        "differences":differences,
        "scope":{"selected_g4_columns_only":True,"full_domain_first_producer_claimed":False},
    }


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="command", required=True)
    b=sub.add_parser("overlay-first-rk")
    b.add_argument("source", type=Path)
    b.add_argument("output", type=Path)
    c=sub.add_parser("compare")
    c.add_argument("continuous", type=Path)
    c.add_argument("restart", type=Path)
    c.add_argument("--output", type=Path)
    args=parser.parse_args()
    if args.command=="overlay-first-rk":
        text=args.source.read_text(encoding="utf-8")
        result=build_first_rk_overlay(text)
        if strip_first_rk_overlay(result)!=text:
            raise ProbeError("generated first-RK overlay fails exact strip audit")
        args.output.write_text(result,encoding="utf-8")
        print(json.dumps({"source_sha256":FIRST_RK_PIN,"overlay_sha256":_sha256(result.encode()),"strip_exact":True},indent=2))
    elif args.command=="compare":
        result = compare_traces(args.continuous, args.restart)
        payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.write_text(payload, encoding="utf-8")
        print(json.dumps({k:v for k,v in result.items() if k!="differences"},indent=2))
    else:  # pragma: no cover - argparse constrains command choices
        raise ProbeError(f"unsupported command: {args.command}")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
