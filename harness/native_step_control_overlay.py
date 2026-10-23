#!/usr/bin/env python3
"""Opt-in single-file host overlay for the native step-control hook.

The helper module is compiled separately from
``harness/native_step_control/kdm6ad_step_control.f90``. This tool only patches
an explicitly supplied isolated host source tree's
``share/mediation_integrate.F``. Default operation is check-only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any


_RELATIVE_SOURCE = Path("share/mediation_integrate.F")
_SUBROUTINE = "SUBROUTINE med_before_solve_io ( grid , config_flags )"
_END_SUBROUTINE = "END SUBROUTINE med_before_solve_io"
_PATCH_MARKER = "KDM6AD_STEP_CONTROL_HOOK_BEGIN"
_PATCH_END = "KDM6AD_STEP_CONTROL_HOOK_END"

_DOMAIN_OLD = "   USE module_domain    , ONLY : domain, domain_clock_get"
_DOMAIN_NEW = "   USE module_domain    , ONLY : domain, domain_clock_get, get_ijk_from_grid"
_WRFPLUS_DOMAIN_OLD = "   USE module_domain    , ONLY : domain_clock_set, get_ijk_from_grid"
_WRFPLUS_DOMAIN_NEW = "   USE module_domain    , ONLY : domain_clock_set"
_STREAMS_ANCHOR = "   USE module_streams"
_STEP_CONTROL_USES = (
    "#ifdef DM_PARALLEL",
    "#if (WRFPLUS != 1)",
    "   USE module_dm, ONLY : ntasks",
    "#endif",
    "#endif",
    "#ifdef _OPENMP",
    "   USE omp_lib, ONLY : omp_get_max_threads",
    "#endif",
    "   USE kdm6ad_step_control, ONLY : step_control_real_kind, await_step_command, &",
    "        prepare_h_diabatic_updates, write_applied_ack, await_analysis_command, &",
    "        prepare_analysis_updates, write_analysis_ack",
)
_RC_ANCHOR = "   INTEGER                                    :: rc"
_STEP_CONTROL_DECLARATIONS = (
    "   INTEGER :: bctx_status, bctx_env_status, bctx_env_length, bctx_n, bctx_m",
    "   INTEGER :: bctx_family_status, bctx_family_length, bctx_capture_status, bctx_capture_length",
    "   INTEGER :: bctx_bounds(6)",
    "   INTEGER :: bctx_ids, bctx_ide, bctx_jds, bctx_jde, bctx_kds, bctx_kde",
    "   INTEGER :: bctx_ims, bctx_ime, bctx_jms, bctx_jme, bctx_kms, bctx_kme",
    "   INTEGER :: bctx_ips, bctx_ipe, bctx_jps, bctx_jpe, bctx_kps, bctx_kpe",
    "   INTEGER, ALLOCATABLE :: bctx_i(:), bctx_k(:), bctx_j(:)",
    "   REAL(step_control_real_kind), ALLOCATABLE :: bctx_delta(:), bctx_old(:), bctx_new(:)",
    "   REAL(step_control_real_kind), ALLOCATABLE :: bctx_delta_t2(:), bctx_delta_qv(:)",
    "   REAL(step_control_real_kind), ALLOCATABLE :: bctx_old_t2(:), bctx_old_qv(:), &",
    "        bctx_new_t2(:), bctx_new_qv(:)",
    "   LOGICAL :: bctx_enabled",
    "   LOGICAL :: bctx_is_tq, bctx_capture_initial",
    "   CHARACTER(LEN=19) :: bctx_timestamp",
    "   CHARACTER(LEN=4096) :: bctx_root",
    "   CHARACTER(LEN=256) :: bctx_error",
    "   CHARACTER(LEN=32) :: bctx_family, bctx_env_family",
    "   CHARACTER(LEN=8) :: bctx_env_capture",
)

_HOOK = (
    "! KDM6AD_STEP_CONTROL_HOOK_BEGIN: opt-in native state increments",
    "   bctx_env_family = ''",
    "   CALL get_environment_variable('KDM6AD_STEP_CONTROL_FAMILY', value=bctx_env_family, &",
    "                                length=bctx_family_length, status=bctx_family_status)",
    "   IF (bctx_family_status .EQ. -1 .OR. bctx_family_length .GT. LEN(bctx_env_family)) &",
    "        CALL wrf_error_fatal('KDM6AD step-control family is too long')",
    "   IF (bctx_family_status .EQ. 1 .OR. bctx_family_length .EQ. 0) THEN",
    "     bctx_family = 'H_RATE'",
    "   ELSE IF (bctx_family_status .NE. 0) THEN",
    "     CALL wrf_error_fatal('KDM6AD step-control family environment is invalid')",
    "   ELSE IF (bctx_family_length .EQ. 6 .AND. bctx_env_family(1:6) .EQ. 'H_RATE') THEN",
    "     bctx_family = 'H_RATE'",
    "   ELSE IF (bctx_family_length .EQ. 11 .AND. bctx_env_family(1:11) .EQ. 'ANALYSIS_TQ') THEN",
    "     bctx_family = 'ANALYSIS_TQ'",
    "   ELSE",
    "     CALL wrf_error_fatal('KDM6AD step-control family must be exact H_RATE or ANALYSIS_TQ')",
    "   END IF",
    "   bctx_is_tq = bctx_family .EQ. 'ANALYSIS_TQ'",
    "   IF (.NOT. bctx_is_tq .AND. bctx_family .NE. 'H_RATE') &",
    "        CALL wrf_error_fatal('KDM6AD step-control family must be H_RATE or ANALYSIS_TQ')",
    "   bctx_env_capture = ''",
    "   CALL get_environment_variable('KDM6AD_STEP_CONTROL_CAPTURE_INITIAL', value=bctx_env_capture, &",
    "                                length=bctx_capture_length, status=bctx_capture_status)",
    "   IF (bctx_capture_status .EQ. -1 .OR. bctx_capture_length .GT. LEN(bctx_env_capture)) &",
    "        CALL wrf_error_fatal('KDM6AD initial-checkpoint capture flag is too long')",
    "   bctx_capture_initial = .FALSE.",
    "   IF (bctx_capture_status .EQ. 0 .AND. bctx_capture_length .GT. 0) THEN",
    "     IF (bctx_capture_length .NE. 1 .OR. bctx_env_capture(1:1) .NE. '1') CALL wrf_error_fatal( &",
    "          'KDM6AD initial-checkpoint capture flag must be 1 when set')",
    "     bctx_capture_initial = .TRUE.",
    "   ELSE IF (bctx_capture_status .NE. 0 .AND. bctx_capture_status .NE. 1) THEN",
    "     CALL wrf_error_fatal('KDM6AD initial-checkpoint capture flag is invalid')",
    "   END IF",
    "   bctx_root = ''",
    "   CALL get_environment_variable('KDM6AD_STEP_CONTROL_ROOT', value=bctx_root, &",
    "                                length=bctx_env_length, status=bctx_env_status)",
    "   IF (bctx_env_status .EQ. -1) CALL wrf_error_fatal( &",
    "        'KDM6AD step-control root is too long')",
    "   IF (bctx_env_status .EQ. 0 .AND. bctx_env_length .GT. 0) THEN",
    "     IF (grid%id .NE. 1) CALL wrf_error_fatal( &",
    "          'KDM6AD step control requires domain 1')",
    "     IF (.NOT. bctx_is_tq .AND. grid%itimestep .LT. 1) CALL wrf_error_fatal( &",
    "          'KDM6AD H_RATE control requires a warm completed-step checkpoint')",
    "     IF (bctx_is_tq .AND. grid%itimestep .LT. 0) CALL wrf_error_fatal( &",
    "          'KDM6AD ANALYSIS_TQ control requires a nonnegative timestep')",
    "#ifdef DM_PARALLEL",
    "     IF (ntasks .NE. 1) CALL wrf_error_fatal( &",
    "          'KDM6AD step control requires one MPI rank')",
    "#endif",
    "#ifdef _OPENMP",
    "     IF (omp_get_max_threads() .NE. 1) CALL wrf_error_fatal( &",
    "          'KDM6AD step control requires one OpenMP thread')",
    "#endif",
    "     IF (config_flags%mp_physics .NE. 137 .OR. grid%dt .NE. 20.0 .OR. &",
    "         config_flags%use_adaptive_time_step) CALL wrf_error_fatal( &",
    "          'KDM6AD step control requires fixed-dt MP137 with dt=20 s')",
    "     IF (config_flags%no_mp_heating .NE. 0 .OR. config_flags%use_theta_m .NE. 1 .OR. &",
    "         config_flags%use_q_diabatic .NE. 0) CALL wrf_error_fatal( &",
    "          'KDM6AD step control requires the audited heating/theta_m/q_diabatic settings')",
    "     IF (bctx_capture_initial) THEN",
    "       CALL WRFU_ClockGet(grid%domain_clock, CurrTime=currTime, StartTime=startTime)",
    "       IF (currTime .EQ. startTime) CALL med_restart_out(grid, config_flags)",
    "     END IF",
    "     CALL get_ijk_from_grid(grid, bctx_ids, bctx_ide, bctx_jds, bctx_jde, &",
    "                           bctx_kds, bctx_kde, bctx_ims, bctx_ime, &",
    "                           bctx_jms, bctx_jme, bctx_kms, bctx_kme, &",
    "                           bctx_ips, bctx_ipe, bctx_jps, bctx_jpe, &",
    "                           bctx_kps, bctx_kpe)",
    "     bctx_bounds = (/ bctx_ids, bctx_ide-1, bctx_kds, bctx_kde-1, &",
    "                     bctx_jds, bctx_jde-1 /)",
    "     CALL domain_clock_get(grid, current_timestr=bctx_timestamp)",
    "     IF (bctx_is_tq) THEN",
    "       CALL await_analysis_command(grid%itimestep, grid%id, bctx_timestamp, bctx_bounds, &",
    "                                    3600, bctx_enabled, bctx_status, bctx_i, bctx_k, &",
    "                                    bctx_j, bctx_delta_t2, bctx_delta_qv, bctx_error)",
    "     ELSE",
    "       CALL await_step_command(grid%itimestep, grid%id, bctx_timestamp, bctx_bounds, &",
    "                               3600, bctx_enabled, bctx_status, bctx_i, bctx_k, &",
    "                               bctx_j, bctx_delta, bctx_error)",
    "     END IF",
    "     IF (bctx_status .NE. 0 .AND. bctx_status .NE. 1) &",
    "          CALL wrf_error_fatal(TRIM(bctx_error))",
    "     IF (bctx_enabled) THEN",
    "       bctx_n = SIZE(bctx_i)",
    "       IF (bctx_is_tq) THEN",
    "         ALLOCATE(bctx_old_t2(bctx_n), bctx_old_qv(bctx_n), bctx_new_t2(bctx_n), &",
    "                  bctx_new_qv(bctx_n), STAT=bctx_status)",
    "         IF (bctx_status .NE. 0) CALL wrf_error_fatal( &",
    "              'KDM6AD analysis control could not allocate T_2/QV buffers')",
    "         IF (bctx_n .GT. 0) THEN",
    "           IF (STORAGE_SIZE(grid%t_2(bctx_i(1),bctx_k(1),bctx_j(1))) .NE. 32 .OR. &",
    "               STORAGE_SIZE(grid%moist(bctx_i(1),bctx_k(1),bctx_j(1),P_QV)) .NE. 32) &",
    "                CALL wrf_error_fatal('KDM6AD analysis control requires binary32 T_2/QV')",
    "           DO bctx_m = 1, bctx_n",
    "             bctx_old_t2(bctx_m) = REAL(grid%t_2(bctx_i(bctx_m),bctx_k(bctx_m), &",
    "                                              bctx_j(bctx_m)), kind=step_control_real_kind)",
    "             bctx_old_qv(bctx_m) = REAL(grid%moist(bctx_i(bctx_m),bctx_k(bctx_m), &",
    "                                              bctx_j(bctx_m),P_QV), kind=step_control_real_kind)",
    "           END DO",
    "         END IF",
    "         CALL prepare_analysis_updates(bctx_old_t2, bctx_old_qv, bctx_delta_t2, &",
    "                bctx_delta_qv, bctx_new_t2, bctx_new_qv, bctx_status, bctx_error)",
    "         IF (bctx_status .NE. 0) CALL wrf_error_fatal(TRIM(bctx_error))",
    "         DO bctx_m = 1, bctx_n",
    "           grid%t_2(bctx_i(bctx_m),bctx_k(bctx_m),bctx_j(bctx_m)) = bctx_new_t2(bctx_m)",
    "           grid%moist(bctx_i(bctx_m),bctx_k(bctx_m),bctx_j(bctx_m),P_QV) = bctx_new_qv(bctx_m)",
    "         END DO",
    "         CALL write_analysis_ack(grid%itimestep, grid%id, bctx_i, bctx_k, bctx_j, &",
    "              bctx_old_t2, bctx_old_qv, bctx_delta_t2, bctx_delta_qv, &",
    "              bctx_new_t2, bctx_new_qv, bctx_status, bctx_error)",
    "         IF (bctx_status .NE. 0) CALL wrf_error_fatal(TRIM(bctx_error))",
    "         DEALLOCATE(bctx_old_t2, bctx_old_qv, bctx_new_t2, bctx_new_qv, &",
    "                    bctx_delta_t2, bctx_delta_qv)",
    "       ELSE",
    "         ALLOCATE(bctx_old(bctx_n), bctx_new(bctx_n), STAT=bctx_status)",
    "         IF (bctx_status .NE. 0) CALL wrf_error_fatal( &",
    "              'KDM6AD step control could not allocate H_DIABATIC buffers')",
    "         IF (bctx_n .GT. 0) THEN",
    "           IF (STORAGE_SIZE(grid%h_diabatic(bctx_i(1),bctx_k(1),bctx_j(1))) .NE. 32) &",
    "                CALL wrf_error_fatal('KDM6AD step control requires binary32 H_DIABATIC')",
    "           DO bctx_m = 1, bctx_n",
    "             bctx_old(bctx_m) = REAL(grid%h_diabatic(bctx_i(bctx_m),bctx_k(bctx_m), &",
    "                                              bctx_j(bctx_m)), kind=step_control_real_kind)",
    "           END DO",
    "           CALL prepare_h_diabatic_updates(bctx_old, bctx_delta, bctx_new, &",
    "                                            bctx_status, bctx_error)",
    "           IF (bctx_status .NE. 0) CALL wrf_error_fatal(TRIM(bctx_error))",
    "           DO bctx_m = 1, bctx_n",
    "             grid%h_diabatic(bctx_i(bctx_m),bctx_k(bctx_m),bctx_j(bctx_m)) = bctx_new(bctx_m)",
    "           END DO",
    "         END IF",
    "         CALL write_applied_ack(grid%itimestep, grid%id, bctx_i, bctx_k, bctx_j, &",
    "                               bctx_old, bctx_delta, bctx_new, bctx_status, bctx_error)",
    "         IF (bctx_status .NE. 0) CALL wrf_error_fatal(TRIM(bctx_error))",
    "         DEALLOCATE(bctx_old, bctx_new, bctx_delta)",
    "       END IF",
    "       DEALLOCATE(bctx_i, bctx_k, bctx_j)",
    "     END IF",
    "   END IF",
    "! KDM6AD_STEP_CONTROL_HOOK_END",
)


def _scope(lines: list[str]) -> tuple[int, int]:
    starts = [i for i, line in enumerate(lines) if line.strip() == _SUBROUTINE]
    if len(starts) != 1:
        raise ValueError(f"expected one active {_SUBROUTINE!r} scope, found {len(starts)}")
    start = starts[0]
    ends = [i for i in range(start + 1, len(lines)) if lines[i].strip() == _END_SUBROUTINE]
    if len(ends) != 1:
        raise ValueError(f"expected one {_END_SUBROUTINE!r}, found {len(ends)}")
    return start, ends[0]


def _active_indices(lines: list[str], start: int, end: int, text: str) -> list[int]:
    return [i for i in range(start, end) if lines[i].rstrip("\r\n") == text]


def _replace_once(lines: list[str], start: int, end: int, old: str,
                  new_lines: tuple[str, ...], label: str) -> None:
    hits = _active_indices(lines, start, end, old)
    if len(hits) != 1:
        raise ValueError(f"{label}: expected one exact active anchor, found {len(hits)}")
    index = hits[0]
    ending = "\r\n" if lines[index].endswith("\r\n") else "\n"
    lines[index:index + 1] = [line + ending for line in new_lines]


def _insert_after_once(lines: list[str], start: int, end: int, anchor: str,
                       inserted: tuple[str, ...], label: str) -> None:
    hits = _active_indices(lines, start, end, anchor)
    if len(hits) != 1:
        raise ValueError(f"{label}: expected one exact active anchor, found {len(hits)}")
    index = hits[0]
    ending = "\r\n" if lines[index].endswith("\r\n") else "\n"
    lines[index + 1:index + 1] = [line + ending for line in inserted]


def _insert_before_once(lines: list[str], start: int, end: int, anchor: str,
                        inserted: tuple[str, ...], label: str) -> None:
    hits = _active_indices(lines, start, end, anchor)
    if len(hits) != 1:
        raise ValueError(f"{label}: expected one exact active anchor, found {len(hits)}")
    index = hits[0]
    ending = "\r\n" if lines[index].endswith("\r\n") else "\n"
    lines[index:index] = [line + ending for line in inserted]


def _remove_block_once(lines: list[str], start: int, end: int,
                       block: tuple[str, ...], label: str) -> None:
    hits: list[int] = []
    width = len(block)
    for index in range(start, end - width + 1):
        candidate = tuple(line.rstrip("\r\n") for line in lines[index:index + width])
        if candidate == block:
            hits.append(index)
    if len(hits) != 1:
        raise ValueError(f"{label}: expected one exact active block, found {len(hits)}")
    del lines[hits[0]:hits[0] + width]


def _reverse_exact_overlay(text: str) -> str:
    lines = text.splitlines(keepends=True)
    start, end = _scope(lines)
    active_scope = "".join(lines[start:end])
    if _PATCH_MARKER not in active_scope and _PATCH_END not in active_scope:
        raise ValueError("overlay markers are missing")
    if active_scope.count(_PATCH_MARKER) != 1 or active_scope.count(_PATCH_END) != 1:
        raise ValueError("overlay markers are duplicated or partial")

    _remove_block_once(lines, start, end, _HOOK, "step-control hook")
    start, end = _scope(lines)
    _remove_block_once(lines, start, end, _STEP_CONTROL_DECLARATIONS, "step-control declarations")
    start, end = _scope(lines)
    _remove_block_once(lines, start, end, _STEP_CONTROL_USES, "step-control imports")
    start, end = _scope(lines)
    _replace_once(lines, start, end, _DOMAIN_NEW, (_DOMAIN_OLD,), "domain import reverse")
    start, end = _scope(lines)
    _replace_once(lines, start, end, _WRFPLUS_DOMAIN_NEW, (_WRFPLUS_DOMAIN_OLD,),
                  "WRFPLUS domain import reverse")
    return "".join(lines)


def _transform(original: str) -> tuple[str, str]:
    lines = original.splitlines(keepends=True)
    start, end = _scope(lines)
    active_scope = "".join(lines[start:end])
    if _PATCH_MARKER in active_scope or _PATCH_END in active_scope:
        recovered = _reverse_exact_overlay(original)
        reapplied, state = _transform(recovered)
        if state != "ready" or reapplied != original:
            raise ValueError("existing overlay does not match the complete expected patch")
        return original, "already_applied"

    _replace_once(lines, start, end, _DOMAIN_OLD, (_DOMAIN_NEW,), "domain import")
    start, end = _scope(lines)
    _replace_once(lines, start, end, _WRFPLUS_DOMAIN_OLD, (_WRFPLUS_DOMAIN_NEW,), "WRFPLUS domain import")
    start, end = _scope(lines)
    _insert_after_once(lines, start, end, _STREAMS_ANCHOR, _STEP_CONTROL_USES, "step-control imports")
    start, end = _scope(lines)
    _insert_after_once(lines, start, end, _RC_ANCHOR, _STEP_CONTROL_DECLARATIONS, "step-control declarations")
    start, end = _scope(lines)
    return_anchor = "   RETURN"
    hits = _active_indices(lines, start, end, return_anchor)
    if len(hits) != 1:
        raise ValueError(f"med_before_solve_io: expected one terminal RETURN, found {len(hits)}")
    _insert_before_once(lines, start, end, return_anchor, _HOOK, "step-control hook")
    return "".join(lines), "ready"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_replace(path: Path, content: bytes, mode: int) -> None:
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.step-control-", dir=path.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp, stat.S_IMODE(mode))
        os.replace(temp, path)
    except BaseException:
        try:
            temp.unlink(missing_ok=True)
        finally:
            raise


def overlay_host_root(host_root: str | Path, *, apply: bool = False) -> dict[str, Any]:
    root = Path(host_root).expanduser().resolve()
    report: dict[str, Any] = {
        "schema": "kdm6ad.native_step_control_overlay.v1",
        "host_root": str(root),
        "source": str(_RELATIVE_SOURCE),
        "mode": "apply" if apply else "check-only",
        "status": "blocked",
        "helper_source": "harness/native_step_control/kdm6ad_step_control.f90",
        "edits": [],
        "errors": [],
    }
    path = root / _RELATIVE_SOURCE
    if not root.is_dir():
        report["status"] = "skipped"
        report["errors"].append(f"host root does not exist: {root}")
        return report
    if path.is_symlink():
        report["errors"].append(f"refusing symlink source: {path}")
        return report
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
        before = path.read_bytes()
        mode = path.stat(follow_symlinks=False).st_mode
        text = before.decode("utf-8")
    except (OSError, UnicodeError, ValueError) as exc:
        report["errors"].append(f"cannot safely read source: {exc}")
        return report
    try:
        updated, state = _transform(text)
    except ValueError as exc:
        report["errors"].append(str(exc))
        return report
    after = updated.encode("utf-8")
    report["status"] = "already_applied" if state == "already_applied" else "ready"
    report["before_sha256"] = _sha256(before)
    report["after_sha256"] = _sha256(after)
    report["edits"] = [
        {"source": str(path), "before_sha256": report["before_sha256"],
         "after_sha256": report["after_sha256"], "state": state}
    ]
    if apply and state == "ready":
        try:
            if path.read_bytes() != before:
                raise RuntimeError("source changed after preflight")
            _atomic_replace(path, after, mode)
            report["status"] = "applied"
        except (OSError, RuntimeError) as exc:
            report["status"] = "blocked"
            report["errors"].append(f"atomic source replacement failed: {exc}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host-root", required=True, type=Path)
    parser.add_argument("--apply", action="store_true", help="apply after exact-source preflight")
    parser.add_argument("--report", type=Path, help="optional JSON report path")
    args = parser.parse_args()
    report = overlay_host_root(args.host_root, apply=args.apply)
    payload = json.dumps(report, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload)
    print(payload, end="")
    return 0 if report["status"] in ("ready", "applied", "already_applied", "skipped") else 1


if __name__ == "__main__":
    raise SystemExit(main())
