#!/usr/bin/env python3
"""Apply a value-only upstream QNC trace to the pinned V3 solve_em source.

Default behavior is a read-only exact-source/anchor check. ``--apply`` modifies
only an explicitly supplied isolated source tree. The trace is opt-in through
``KDM6AD_UPSTREAM_NC_TRACE_DIR`` and does not alter the numerical statements.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any


SOURCE_RELATIVE_PATH = "dyn_em/solve_em.f90"
BASE_SOURCE_SHA256 = "17de10c1e376eca42777853bc9cb8a9d5d6d12b474f45c56a50e6800e790af79"
TRACE_ENV = "KDM6AD_UPSTREAM_NC_TRACE_DIR"
TRACE_FILE_NAME = "upstream_nc.tsv"
TARGETS = ((221, 6, 63), (91, 4, 94))  # i,k,j, one-based


_USE_ANCHOR = ("   USE module_microphysics_zero_out",)
_USE_CODE = ("   USE, INTRINSIC :: ISO_C_BINDING, ONLY: C_INT32_T",)
_DECL_ANCHOR = ("   INTEGER :: rk_order, iwmax, jwmax, kwmax",)
_DECL_CODE = (
    "   INTEGER, PARAMETER :: KDM6AD_UPNC_NTARGET = 2",
    "   INTEGER, PARAMETER :: KDM6AD_UPNC_I(KDM6AD_UPNC_NTARGET) = (/ 221, 91 /)",
    "   INTEGER, PARAMETER :: KDM6AD_UPNC_K(KDM6AD_UPNC_NTARGET) = (/ 6, 4 /)",
    "   INTEGER, PARAMETER :: KDM6AD_UPNC_J(KDM6AD_UPNC_NTARGET) = (/ 63, 94 /)",
    "   INTEGER, SAVE :: KDM6AD_UPNC_UNIT = 0",
    "   LOGICAL, SAVE :: KDM6AD_UPNC_INITIALIZED = .FALSE.",
    "   LOGICAL, SAVE :: KDM6AD_UPNC_ACTIVE = .FALSE.",
    "   CHARACTER(LEN=4096), SAVE :: KDM6AD_UPNC_DIR = ''",
)
_DECL_COMMENT = "   INTEGER :: rk_order, iwmax, jwmax, kwmax"

_SCALAR_UPDATE_CALL = (
    "           CALL rk_update_scalar( scs=is, sce=is,                                         &",
    "                                  scalar_1=scalar_old(ims,kms,jms,is),                    &",
    "                                  scalar_2=scalar(ims,kms,jms,is),                        &",
    "                                  sc_tend=scalar_tend(ims,kms,jms,is),                    &",
    "                                  advect_tend=advect_tend,                                &",
    "                                  h_tendency=h_tendency, z_tendency=z_tendency,           &",
    "                                  msftx=grid%msftx,msfty=grid%msfty,                      &",
    "                                  c1=grid%c1h, c2=grid%c2h,                               &",
    "                                  mu_old=grid%mu_1, mu_new=grid%mu_2, mu_base=grid%mub,   &",
    "                                  rk_step=rk_step, dt=dt_rk, spec_zone=grid%spec_zone,    &",
    "                                  config_flags=config_flags, tenddec=tenddec,             &",
    "                                  ids=ids, ide=ide, jds=jds, jde=jde, kds=kds, kde=kde,   &",
    "                                  ims=ims, ime=ime, jms=jms, jme=jme, kms=kms, kme=kme,   &",
    "                                  its=grid%i_start(ij), ite=grid%i_end(ij),               &",
    "                                  jts=grid%j_start(ij), jte=grid%j_end(ij),               &",
    "                                  kts=k_start    , kte=k_end                              )",
)

_SCALAR_PD_CALL = (
    "           CALL rk_update_scalar_pd( im, im,                                  &",
    "                                     scalar_old(ims,kms,jms,im),              &",
    "                                     scalar_tend(ims,kms,jms,im),             &",
    "                                     grid%c1h, grid%c2h,                      &",
    "                                     grid%mu_1, grid%mu_1, grid%mub,           &",
    "                                     rk_step, dt_rk, grid%spec_zone,           &",
    "                                     config_flags,                            &",
    "                                     ids, ide, jds, jde, kds, kde,            &",
    "                                     ims, ime, jms, jme, kms, kme,            &",
    "                                     grid%i_start(ij), grid%i_end(ij),        &",
    "                                     grid%j_start(ij), grid%j_end(ij),        &",
    "                                     k_start    , k_end                      )",
)

_PRE_MICROPHYSICS_ANCHOR = ("     CALL microphysics_driver(                                            &",)
_END_ANCHOR = ("END SUBROUTINE solve_em",)

_TRACE_SETUP = (
    "     CALL kdm6ad_upnc_trace('PRE_MICROPHYSICS', grid%itimestep, 0, dtm, 0, &",
    "                           ids, ide-1, jds, jde-1, k_start, k_end)",
)

_RK_BEFORE = (
    "           IF (is .EQ. P_QNC) THEN",
    "             CALL kdm6ad_upnc_trace('RKSCALAR_BEFORE', grid%itimestep, rk_step, &",
    "                  dt_rk, 1, grid%i_start(ij), grid%i_end(ij), &",
    "                  grid%j_start(ij), grid%j_end(ij), k_start, k_end)",
    "           END IF",
)
_RK_AFTER = (
    "           IF (is .EQ. P_QNC) THEN",
    "             CALL kdm6ad_upnc_trace('RKSCALAR_AFTER', grid%itimestep, rk_step, &",
    "                  dt_rk, 1, grid%i_start(ij), grid%i_end(ij), &",
    "                  grid%j_start(ij), grid%j_end(ij), k_start, k_end)",
    "           END IF",
)
_PD_BEFORE = (
    "           IF (im .EQ. P_QNC) THEN",
    "             CALL kdm6ad_upnc_trace('RKSCALAR_PD_BEFORE', grid%itimestep, rk_step, &",
    "                  dt_rk, 2, grid%i_start(ij), grid%i_end(ij), &",
    "                  grid%j_start(ij), grid%j_end(ij), k_start, k_end)",
    "           END IF",
)
_PD_AFTER = (
    "           IF (im .EQ. P_QNC) THEN",
    "             CALL kdm6ad_upnc_trace('RKSCALAR_PD_AFTER', grid%itimestep, rk_step, &",
    "                  dt_rk, 2, grid%i_start(ij), grid%i_end(ij), &",
    "                  grid%j_start(ij), grid%j_end(ij), k_start, k_end)",
    "           END IF",
)

_INTERNAL_ROUTINES = (
    "CONTAINS",
    "  SUBROUTINE kdm6ad_upnc_init()",
    "    CHARACTER(LEN=4096) :: env_value, trace_path",
    "    INTEGER :: env_status, env_length, open_status",
    "    IF (KDM6AD_UPNC_INITIALIZED) RETURN",
    "    KDM6AD_UPNC_INITIALIZED = .TRUE.",
    "    env_value = ''",
    f"    CALL get_environment_variable('{TRACE_ENV}', value=env_value, &",
    "                                 length=env_length, status=env_status)",
    "    IF (env_status .EQ. 1 .OR. env_length .EQ. 0) RETURN",
    "    IF (env_status .NE. 0 .OR. env_length .GT. LEN(env_value)) &",
    "         CALL wrf_error_fatal('upstream NC trace directory is invalid or too long')",
    "    KDM6AD_UPNC_DIR = TRIM(env_value)",
    f"    trace_path = TRIM(KDM6AD_UPNC_DIR)//'/{TRACE_FILE_NAME}'",
    "    OPEN(NEWUNIT=KDM6AD_UPNC_UNIT, FILE=TRIM(trace_path), STATUS='NEW', &",
    "         ACTION='WRITE', FORM='FORMATTED', IOSTAT=open_status)",
    "    IF (open_status .NE. 0) CALL wrf_error_fatal('upstream NC trace must use a new writable file')",
    "    WRITE(KDM6AD_UPNC_UNIT,'(A)') '# KDM6AD_UPSTREAM_NC_TRACE_V1'",
    "    WRITE(KDM6AD_UPNC_UNIT,'(A)') '# VAL'//CHAR(9)//'step'//CHAR(9)//'rk_step'//CHAR(9)//'stage'// &",
    "         CHAR(9)//'i'//CHAR(9)//'k'//CHAR(9)//'j'//CHAR(9)//'field'//CHAR(9)//'dtype'//CHAR(9)//'raw_hex'",
    "    FLUSH(KDM6AD_UPNC_UNIT)",
    "    KDM6AD_UPNC_ACTIVE = .TRUE.",
    "  END SUBROUTINE kdm6ad_upnc_init",
    "",
    "  SUBROUTINE kdm6ad_upnc_trace(stage, step, rk_step, dt_value, mode, &",
    "                              its, ite, jts, jte, kts, kte)",
    "    CHARACTER(LEN=*), INTENT(IN) :: stage",
    "    INTEGER, INTENT(IN) :: step, rk_step, mode, its, ite, jts, jte, kts, kte",
    "    REAL, INTENT(IN) :: dt_value",
    "    INTEGER :: target, i, k, j, bool_word",
    "    INTEGER(C_INT32_T) :: word",
    "    CALL kdm6ad_upnc_init()",
    "    IF (.NOT. KDM6AD_UPNC_ACTIVE) RETURN",
    "    DO target = 1, KDM6AD_UPNC_NTARGET",
    "      i = KDM6AD_UPNC_I(target); k = KDM6AD_UPNC_K(target); j = KDM6AD_UPNC_J(target)",
    "      IF (i .LT. its .OR. i .GT. ite .OR. j .LT. jts .OR. j .GT. jte) CYCLE",
    "      IF (k .LT. kts .OR. k .GT. kte) CYCLE",
    "      CALL kdm6ad_upnc_write_real(step, rk_step, stage, i, k, j, 'QNC', scalar(i,k,j,P_QNC))",
    "      IF (mode .EQ. 0) CYCLE",
    "      CALL kdm6ad_upnc_write_real(step, rk_step, stage, i, k, j, 'SCALAR_OLD', scalar_old(i,k,j,P_QNC))",
    "      CALL kdm6ad_upnc_write_real(step, rk_step, stage, i, k, j, 'SCALAR_TEND', scalar_tend(i,k,j,P_QNC))",
    "      IF (mode .EQ. 1) THEN",
    "        CALL kdm6ad_upnc_write_real(step, rk_step, stage, i, k, j, 'ADVECT_TEND', advect_tend(i,k,j))",
    "        CALL kdm6ad_upnc_write_real(step, rk_step, stage, i, k, j, 'H_TENDENCY', h_tendency(i,k,j))",
    "        CALL kdm6ad_upnc_write_real(step, rk_step, stage, i, k, j, 'Z_TENDENCY', z_tendency(i,k,j))",
    "        CALL kdm6ad_upnc_write_real(step, rk_step, stage, i, k, j, 'MU_OLD', grid%mu_1(i,j))",
    "        CALL kdm6ad_upnc_write_real(step, rk_step, stage, i, k, j, 'MU_NEW', grid%mu_2(i,j))",
    "        CALL kdm6ad_upnc_write_real(step, rk_step, stage, i, k, j, 'MU_BASE', grid%mub(i,j))",
    "        CALL kdm6ad_upnc_write_real(step, rk_step, stage, i, k, j, 'C1H', grid%c1h(k))",
    "        CALL kdm6ad_upnc_write_real(step, rk_step, stage, i, k, j, 'C2H', grid%c2h(k))",
    "        CALL kdm6ad_upnc_write_real(step, rk_step, stage, i, k, j, 'MSFTY', grid%msfty(i,j))",
    "        CALL kdm6ad_upnc_write_real(step, rk_step, stage, i, k, j, 'DT_RK', dt_value)",
    "        bool_word = MERGE(1,0,tenddec)",
    "        word = INT(bool_word,C_INT32_T)",
    "        CALL kdm6ad_upnc_write_word(step, rk_step, stage, i, k, j, 'TENDEC', 'bool', word)",
    "      ELSE IF (mode .EQ. 2) THEN",
    "        CALL kdm6ad_upnc_write_real(step, rk_step, stage, i, k, j, 'MU_OLD_ARG', grid%mu_1(i,j))",
    "        CALL kdm6ad_upnc_write_real(step, rk_step, stage, i, k, j, 'MU_NEW_ARG', grid%mu_1(i,j))",
    "        CALL kdm6ad_upnc_write_real(step, rk_step, stage, i, k, j, 'MU_BASE', grid%mub(i,j))",
    "        CALL kdm6ad_upnc_write_real(step, rk_step, stage, i, k, j, 'C1H', grid%c1h(k))",
    "        CALL kdm6ad_upnc_write_real(step, rk_step, stage, i, k, j, 'C2H', grid%c2h(k))",
    "        CALL kdm6ad_upnc_write_real(step, rk_step, stage, i, k, j, 'DT_RK', dt_value)",
    "      ELSE",
    "        CALL wrf_error_fatal('upstream NC trace received an unsupported event mode')",
    "      END IF",
    "    END DO",
    "  END SUBROUTINE kdm6ad_upnc_trace",
    "",
    "  SUBROUTINE kdm6ad_upnc_write_real(step, rk_step, stage, i, k, j, field, value)",
    "    INTEGER, INTENT(IN) :: step, rk_step, i, k, j",
    "    CHARACTER(LEN=*), INTENT(IN) :: stage, field",
    "    REAL, INTENT(IN) :: value",
    "    INTEGER(C_INT32_T) :: word",
    "    word = TRANSFER(value,0_C_INT32_T)",
    "    CALL kdm6ad_upnc_write_word(step,rk_step,stage,i,k,j,field,'f32',word)",
    "  END SUBROUTINE kdm6ad_upnc_write_real",
    "",
    "  SUBROUTINE kdm6ad_upnc_write_word(step, rk_step, stage, i, k, j, field, dtype, word)",
    "    INTEGER, INTENT(IN) :: step, rk_step, i, k, j",
    "    CHARACTER(LEN=*), INTENT(IN) :: stage, field, dtype",
    "    INTEGER(C_INT32_T), INTENT(IN) :: word",
    "    CHARACTER(LEN=16) :: step_text, rk_text, i_text, k_text, j_text, bits_text",
    "    CHARACTER(LEN=512) :: record",
    "    IF (.NOT. KDM6AD_UPNC_ACTIVE) RETURN",
    "    WRITE(step_text,'(I0)') step",
    "    WRITE(rk_text,'(I0)') rk_step",
    "    WRITE(i_text,'(I0)') i",
    "    WRITE(k_text,'(I0)') k",
    "    WRITE(j_text,'(I0)') j",
    "    IF (dtype .EQ. 'bool') THEN",
    "      WRITE(bits_text,'(Z2.2)') word",
    "    ELSE",
    "      WRITE(bits_text,'(Z8.8)') word",
    "    END IF",
    "    record = 'VAL'//CHAR(9)//TRIM(step_text)//CHAR(9)//TRIM(rk_text)//CHAR(9)//TRIM(stage)// &",
    "        CHAR(9)//TRIM(i_text)//CHAR(9)//TRIM(k_text)//CHAR(9)//TRIM(j_text)//CHAR(9)// &",
    "        TRIM(field)//CHAR(9)//TRIM(dtype)//CHAR(9)//TRIM(bits_text)",
    "    WRITE(KDM6AD_UPNC_UNIT,'(A)') TRIM(record)",
    "    FLUSH(KDM6AD_UPNC_UNIT)",
    "  END SUBROUTINE kdm6ad_upnc_write_word",
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _anchor_matches(text: str, anchor: tuple[str, ...]) -> list[tuple[int, int, list[str]]]:
    """Find exact Fortran statement lines while ignoring layout whitespace."""
    lines = text.splitlines(keepends=True)
    normalized = [" ".join(line.rstrip("\r\n").split()) for line in lines]
    offsets = []
    position = 0
    for line in lines:
        offsets.append(position)
        position += len(line)
    pattern = [" ".join(line.split()) for line in anchor if line.strip()]
    found = []
    for start, line in enumerate(normalized):
        if line != pattern[0]:
            continue
        index = start
        matched = True
        for wanted in pattern[1:]:
            index += 1
            while index < len(normalized) and not normalized[index].strip():
                index += 1
            if index >= len(normalized) or normalized[index] != wanted:
                matched = False
                break
        if matched:
            end = offsets[index] + len(lines[index].rstrip("\r\n"))
            found.append((offsets[start], end, lines))
    return found


def _apply_insertions(text: str) -> tuple[str, dict[str, str]]:
    """Match exact active lines, ignoring generated F90 trailing spaces/blanks."""
    updated = text
    status: dict[str, str] = {}

    def replace_anchor(name: str, anchor: tuple[str, ...], code: tuple[str, ...], *, before: bool) -> None:
        nonlocal updated
        found = _anchor_matches(updated, anchor)
        status[name] = "ready" if len(found) == 1 else "missing_or_ambiguous"
        if len(found) != 1:
            return
        start, end, _ = found[0]
        newline = "\r\n" if "\r\n" in updated else "\n"
        rendered = newline.join(code)
        if before:
            updated = updated[:start] + rendered + newline + updated[start:]
        else:
            updated = updated[:end] + newline + rendered + updated[end:]

    replace_anchor("use_c_int32", _USE_ANCHOR, _USE_CODE, before=False)
    replace_anchor("declarations", _DECL_ANCHOR, _DECL_CODE, before=False)
    replace_anchor("rk_scalar_pre", _SCALAR_UPDATE_CALL, _RK_BEFORE, before=True)
    replace_anchor("rk_scalar_post", _SCALAR_UPDATE_CALL, _RK_AFTER, before=False)
    replace_anchor("rk_scalar_pd_pre", _SCALAR_PD_CALL, _PD_BEFORE, before=True)
    replace_anchor("rk_scalar_pd_post", _SCALAR_PD_CALL, _PD_AFTER, before=False)
    replace_anchor("premicro", _PRE_MICROPHYSICS_ANCHOR, _TRACE_SETUP, before=True)
    replace_anchor("internal_routines", _END_ANCHOR, _INTERNAL_ROUTINES, before=True)
    return updated, status


def build_overlay_plan(source_path: Path) -> dict[str, Any]:
    path = Path(source_path).expanduser()
    report: dict[str, Any] = {"schema": "kdm6ad.upstream_nc_trace_overlay.v1", "status": "blocked", "errors": [], "file": None}
    if path.is_symlink() or not path.is_file():
        report["errors"].append(f"refusing missing or symlink solve_em source: {path}")
        return report
    original = path.read_bytes()
    actual = _sha256(original)
    report["file"] = {"path": str(path.resolve()), "source_sha256": actual}
    if actual != BASE_SOURCE_SHA256:
        report["errors"].append(f"solve_em source pin mismatch: expected {BASE_SOURCE_SHA256}, got {actual}")
        return report
    try:
        text = original.decode("utf-8")
    except UnicodeDecodeError as exc:
        report["errors"].append(f"solve_em source is not UTF-8 text: {exc}")
        return report
    updated, insertions = _apply_insertions(text)
    report["file"]["insertions"] = insertions
    report["file"]["overlay_sha256"] = _sha256(updated.encode())
    if any(value != "ready" for value in insertions.values()):
        report["errors"].append("one or more source anchors are absent or ambiguous")
        return report
    # Ensure instrumentation surrounds the intended calls without moving them.
    generic_span = _anchor_matches(updated, _SCALAR_UPDATE_CALL)
    pd_span = _anchor_matches(updated, _SCALAR_PD_CALL)
    premicro_span = _anchor_matches(updated, _PRE_MICROPHYSICS_ANCHOR)
    if len(generic_span) != 1 or len(pd_span) != 1 or len(premicro_span) != 1:
        report["errors"].append("one or more post-insertion source anchors are missing or ambiguous")
        return report
    generic_start, generic_end, _ = generic_span[0]
    pd_start, pd_end, _ = pd_span[0]
    micro_start, _, _ = premicro_span[0]
    if not (updated.index("CALL kdm6ad_upnc_trace('RKSCALAR_BEFORE'") < generic_start < generic_end <
            updated.index("CALL kdm6ad_upnc_trace('RKSCALAR_AFTER'")):
        report["errors"].append("generic RK trace events are not ordered around the update call")
        return report
    if not (updated.index("CALL kdm6ad_upnc_trace('RKSCALAR_PD_BEFORE'") < pd_start < pd_end <
            updated.index("CALL kdm6ad_upnc_trace('RKSCALAR_PD_AFTER'")):
        report["errors"].append("PD RK trace events are not ordered around the PD update call")
        return report
    if updated.index("CALL kdm6ad_upnc_trace('PRE_MICROPHYSICS'") > micro_start:
        report["errors"].append("pre-microphysics event is not before microphysics_driver")
        return report
    report["status"] = "ready"
    return report


def apply_overlay(source_path: Path, *, output_path: Path) -> dict[str, Any]:
    """Write an overlay only to a distinct, new private F90 path."""
    report = build_overlay_plan(source_path)
    if report["status"] != "ready":
        return report
    source = Path(source_path).resolve(strict=True)
    output = Path(output_path)
    if output.exists() or output.is_symlink():
        report["status"] = "refused"
        report["errors"].append(f"overlay output must be new: {output}")
        return report
    output_parent = output.parent.resolve(strict=False)
    try:
        output_parent.relative_to(source.parent)
    except ValueError:
        pass
    else:
        if output.resolve(strict=False) == source or source in output.resolve(strict=False).parents:
            report["status"] = "refused"
            report["errors"].append("overlay output overlaps or would replace its input tree")
            return report
    original = source.read_bytes()
    updated, states = _apply_insertions(original.decode("utf-8"))
    if any(value != "ready" for value in states.values()):
        report["status"] = "refused"
        report["errors"].append("source anchors changed between preflight and write")
        return report
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".upnc-tmp", dir=output.parent)
    temp = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(updated)
            handle.flush()
            os.fsync(handle.fileno())
        if _sha256(source.read_bytes()) != BASE_SOURCE_SHA256:
            raise RuntimeError("source changed after preflight")
        if output.exists() or output.is_symlink():
            raise FileExistsError(output)
        os.replace(temp, output)
        report["file"]["output_path"] = str(output.resolve())
        report["file"]["overlay_sha256"] = _sha256(output.read_bytes())
        report["status"] = "applied"
    except Exception as exc:
        temp.unlink(missing_ok=True)
        report["status"] = "failed"
        report["errors"].append(str(exc))
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="pinned V3 solve_em.f90 input")
    parser.add_argument("--output", type=Path, help="new private overlay solve_em.f90 destination")
    parser.add_argument("--apply", action="store_true", help="write the new overlay after exact-pin checks")
    args = parser.parse_args(argv)
    if args.apply and args.output is None:
        parser.error("--output is required with --apply")
    report = apply_overlay(args.source, output_path=args.output) if args.apply else build_overlay_plan(args.source)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] in {"ready", "applied"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
