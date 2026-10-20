#!/usr/bin/env python3
"""Opt-in overlay for a single-column native MP137 trace.

The tool only edits an explicitly supplied isolated host source root. Its
default mode checks exact active-source anchors and writes nothing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Insertion:
    name: str
    scope_start: str
    scope_end: str
    anchor: tuple[str, ...]
    code: tuple[str, ...]
    position: str = "after"

    @property
    def replacement(self) -> tuple[str, ...]:
        if self.position == "before":
            return self.code + self.anchor
        return self.anchor + self.code


@dataclass(frozen=True)
class SourceOverlay:
    relative_path: str
    insertions: tuple[Insertion, ...]


_TRACE_USE = (
    "    USE kdm6ad_native_trace, ONLY: trace_real_kind, trace_enabled, &",
    "         trace_target_i, trace_target_j, trace_current_step, &",
    "         trace_set_step, trace_record",
)

_MP_INPUT = (
    "    IF (trace_enabled .AND. trace_target_i >= ITS .AND. trace_target_i <= ITE .AND. &",
    "        trace_target_j >= JTS .AND. trace_target_j <= JTE) THEN",
    "      II = trace_target_i - ITS + 1",
    "      JJ = trace_target_j - JTS + 1",
    "      DO K = KTS, KTE",
    "        KK = K - KTS + 1",
    "        TRACE_VALUES(1) = REAL(DELT, trace_real_kind)",
    "        TRACE_VALUES(2) = TH_IN(II,KK,JJ)",
    "        TRACE_VALUES(3) = Q_IN(II,KK,JJ)",
    "        TRACE_VALUES(4) = QC_IN(II,KK,JJ)",
    "        TRACE_VALUES(5) = QR_IN(II,KK,JJ)",
    "        TRACE_VALUES(6) = QI_IN(II,KK,JJ)",
    "        TRACE_VALUES(7) = QS_IN(II,KK,JJ)",
    "        TRACE_VALUES(8) = QG_IN(II,KK,JJ)",
    "        TRACE_VALUES(9) = NN_IN(II,KK,JJ)",
    "        TRACE_VALUES(10) = NC_IN(II,KK,JJ)",
    "        TRACE_VALUES(11) = NI_IN(II,KK,JJ)",
    "        TRACE_VALUES(12) = NR_IN(II,KK,JJ)",
    "        TRACE_VALUES(13) = BG_IN(II,KK,JJ)",
    "        TRACE_VALUES(14) = DEN_IN(II,KK,JJ)",
    "        TRACE_VALUES(15) = PII_IN(II,KK,JJ)",
    "        TRACE_VALUES(16) = P_IN(II,KK,JJ)",
    "        TRACE_VALUES(17) = DELZ_IN(II,KK,JJ)",
    "        CALL trace_record('MP_INPUT', ITIMESTEP, trace_target_i, K, &",
    "                          trace_target_j, TRACE_VALUES(1:17))",
    "      END DO",
    "    END IF",
)

_MP_OUTPUT = (
    "    IF (trace_enabled .AND. trace_target_i >= ITS .AND. trace_target_i <= ITE .AND. &",
    "        trace_target_j >= JTS .AND. trace_target_j <= JTE) THEN",
    "      II = trace_target_i - ITS + 1",
    "      JJ = trace_target_j - JTS + 1",
    "      DO K = KTS, KTE",
    "        KK = K - KTS + 1",
    "        TRACE_VALUES(1) = REAL(DELT, trace_real_kind)",
    "        TRACE_VALUES(2) = TH_OUT(II,KK,JJ)",
    "        TRACE_VALUES(3) = Q_OUT(II,KK,JJ)",
    "        TRACE_VALUES(4) = QC_OUT(II,KK,JJ)",
    "        TRACE_VALUES(5) = QR_OUT(II,KK,JJ)",
    "        TRACE_VALUES(6) = QI_OUT(II,KK,JJ)",
    "        TRACE_VALUES(7) = QS_OUT(II,KK,JJ)",
    "        TRACE_VALUES(8) = QG_OUT(II,KK,JJ)",
    "        TRACE_VALUES(9) = NN_OUT(II,KK,JJ)",
    "        TRACE_VALUES(10) = NC_OUT(II,KK,JJ)",
    "        TRACE_VALUES(11) = NI_OUT(II,KK,JJ)",
    "        TRACE_VALUES(12) = NR_OUT(II,KK,JJ)",
    "        TRACE_VALUES(13) = BG_OUT(II,KK,JJ)",
    "        TRACE_VALUES(14) = RHOG_OUT(II,KK,JJ)",
    "        CALL trace_record('MP_OUTPUT', ITIMESTEP, trace_target_i, K, &",
    "                          trace_target_j, TRACE_VALUES(1:14))",
    "      END DO",
    "    END IF",
)

_FINISH_PRE = (
    "       IF (trace_enabled .AND. trace_current_step >= 0 .AND. &",
    "           i == trace_target_i .AND. j == trace_target_j) THEN",
    "         TRACE_VALUES(1) = REAL(dt, trace_real_kind)",
    "         TRACE_VALUES(2) = REAL(h_diabatic(i,k,j), trace_real_kind)",
    "         TRACE_VALUES(3) = REAL(qv_diabatic(i,k,j), trace_real_kind)",
    "         TRACE_VALUES(4) = REAL(th_phy(i,k,j), trace_real_kind)",
    "         TRACE_VALUES(5) = REAL(qv(i,k,j), trace_real_kind)",
    "         TRACE_VALUES(6) = REAL(qvten, trace_real_kind)",
    "         TRACE_VALUES(8) = REAL(mpten, trace_real_kind)",
    "         TRACE_VALUES(9) = REAL(t_new(i,k,j), trace_real_kind)",
    "         TRACE_VALUES(10) = REAL(t0, trace_real_kind)",
    "         TRACE_VALUES(11) = REAL(R_v/R_d, trace_real_kind)",
    "         TRACE_VALUES(12) = REAL(config_flags%mp_tend_lim, trace_real_kind)",
    "         CALL trace_record('FINISH_PRE', trace_current_step, i, k, j, &",
    "                           TRACE_VALUES(1:12))",
    "       END IF",
)

_FINISH_RAW_CAPTURE = (
    "          IF (trace_enabled .AND. trace_current_step >= 0 .AND. &",
    "              i == trace_target_i .AND. j == trace_target_j) THEN",
    "            TRACE_VALUES(7) = REAL(mpten, trace_real_kind)",
    "          END IF",
)

_FINISH_POST = (
    "       IF (trace_enabled .AND. trace_current_step >= 0 .AND. &",
    "           i == trace_target_i .AND. j == trace_target_j) THEN",
    "         TRACE_VALUES(1) = REAL(dt, trace_real_kind)",
    "         TRACE_VALUES(2) = REAL(t_new(i,k,j), trace_real_kind)",
    "         TRACE_VALUES(3) = REAL(t0, trace_real_kind)",
    "         TRACE_VALUES(4) = REAL(h_diabatic(i,k,j), trace_real_kind)",
    "         TRACE_VALUES(5) = REAL(qv_diabatic(i,k,j), trace_real_kind)",
    "         TRACE_VALUES(6) = REAL(qc_diabatic(i,k,j), trace_real_kind)",
    "         TRACE_VALUES(7) = REAL(th_phy_m_t0(i,k,j), trace_real_kind)",
    "         CALL trace_record('FINISH_POST', trace_current_step, i, k, j, &",
    "                           TRACE_VALUES(1:7))",
    "       END IF",
)

_MP_SCOPE = ("SUBROUTINE kdm6ad(", "END SUBROUTINE kdm6ad")
_FINISH_SCOPE = (
    "SUBROUTINE moist_physics_finish_em(",
    "END SUBROUTINE moist_physics_finish_em",
)

SOURCE_OVERLAYS = (
    SourceOverlay(
        "phys/module_mp_kdm6ad.F",
        (
            Insertion("mp_trace_use", *_MP_SCOPE, ("    IMPLICIT NONE",), _TRACE_USE, "before"),
            Insertion(
                "mp_trace_values", *_MP_SCOPE,
                ("    INTEGER :: I, J, K, II, JJ, KK",),
                ("    REAL(trace_real_kind) :: TRACE_VALUES(17)",),
            ),
            Insertion(
                "mp_trace_step", *_MP_SCOPE,
                ("    IM = ITE - ITS + 1",),
                ("    CALL trace_set_step(ITIMESTEP)",),
            ),
            Insertion(
                "mp_trace_input", *_MP_SCOPE,
                ("    CALL kdm6ad_check_finite_2d(XLAND_IN,'XLAND input',ITS,JTS)",),
                _MP_INPUT,
            ),
            Insertion(
                "mp_trace_output", *_MP_SCOPE,
                ("    CALL kdm6ad_check_finite_2d(GRAUPEL_INC, 'GRAUPEL increment', ITS, JTS)",),
                _MP_OUTPUT,
            ),
        ),
    ),
    SourceOverlay(
        "dyn_em/module_big_step_utilities_em.F",
        (
            Insertion(
                "finish_trace_use", *_FINISH_SCOPE,
                ("   IMPLICIT NONE",), _TRACE_USE, "before"),
            Insertion(
                "finish_trace_values", *_FINISH_SCOPE,
                ("   INTEGER :: i, j, k, imax, jmax, imin, jmin",),
                ("   REAL(trace_real_kind) :: TRACE_VALUES(12)",),
            ),
            Insertion(
                "finish_trace_raw_mpten", *_FINISH_SCOPE,
                ("          mpten = th_phy(i,k,j)-h_diabatic(i,k,j)",),
                _FINISH_RAW_CAPTURE,
            ),
            Insertion(
                "finish_trace_pre", *_FINISH_SCOPE,
                (
                    "          mpten=min(config_flags%mp_tend_lim*dt, mpten)",
                    "          mpten=max(-config_flags%mp_tend_lim*dt, mpten)",
                ),
                _FINISH_PRE,
            ),
            Insertion(
                "finish_trace_post", *_FINISH_SCOPE,
                (
                    "         qc_diabatic(i,k,j) =  qcten/dt",
                    "#endif",
                ),
                _FINISH_POST,
            ),
        ),
    ),
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _lines(text: str) -> tuple[list[str], list[tuple[int, int]]]:
    contents: list[str] = []
    offsets: list[tuple[int, int]] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        content = line.rstrip("\r\n")
        contents.append(content)
        offsets.append((offset, offset + len(content)))
        offset += len(line)
    return contents, offsets


def _scope_bounds(contents: list[str], scope: tuple[str, str]) -> tuple[int, int] | None:
    start_tag, end_tag = scope
    starts = [
        index for index, line in enumerate(contents)
        if not line.lstrip().startswith("!") and line.lstrip().upper().startswith(start_tag.upper())
    ]
    ends = [
        index for index, line in enumerate(contents)
        if not line.lstrip().startswith("!") and line.strip().upper() == end_tag.upper()
    ]
    if len(starts) != 1 or len(ends) != 1 or ends[0] <= starts[0]:
        return None
    return starts[0], ends[0] + 1


def _active_spans(
    text: str,
    pattern: tuple[str, ...],
    scope: tuple[str, str],
) -> list[tuple[int, int]]:
    contents, offsets = _lines(text)
    bounds = _scope_bounds(contents, scope)
    if bounds is None or not pattern:
        return []
    scope_start, scope_end = bounds
    spans: list[tuple[int, int]] = []
    last = scope_end - len(pattern)
    for start in range(scope_start, last + 1):
        candidate = contents[start:start + len(pattern)]
        if any(line.lstrip().startswith("!") for line in candidate):
            continue
        if tuple(candidate) == pattern:
            spans.append((offsets[start][0], offsets[start + len(pattern) - 1][1]))
    return spans


def _classify(text: str, insertion: Insertion) -> str:
    old_spans = _active_spans(text, insertion.anchor, (insertion.scope_start, insertion.scope_end))
    new_spans = _active_spans(text, insertion.replacement, (insertion.scope_start, insertion.scope_end))
    embedded_old = sum(
        1 for old_start, old_end in old_spans
        if any(new_start <= old_start and old_end <= new_end for new_start, new_end in new_spans)
    )
    if len(new_spans) == 1 and len(old_spans) == embedded_old:
        return "applied"
    if not new_spans and len(old_spans) == 1:
        return "ready"
    return "drift_or_ambiguous"


def _newline(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def _apply_insertion(text: str, insertion: Insertion) -> str:
    spans = _active_spans(text, insertion.anchor, (insertion.scope_start, insertion.scope_end))
    if len(spans) != 1:
        raise RuntimeError(f"active anchor changed while staging {insertion.name}")
    start, end = spans[0]
    replacement = _newline(text).join(insertion.replacement)
    return text[:start] + replacement + text[end:]


def _summary_item(item: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in item.items() if not key.endswith("_bytes")}


def patch_host_root(host_root: str | Path, *, apply: bool = False) -> dict[str, Any]:
    """Check or apply the trace overlay under an explicit isolated host root."""
    root = Path(host_root).expanduser().resolve()
    report: dict[str, Any] = {
        "schema": "kdm6ad.native_trace_overlay.v1",
        "host_root": str(root),
        "mode": "apply" if apply else "check-only",
        "status": "blocked",
        "files": [],
        "errors": [],
    }
    if not root.is_dir():
        report["status"] = "skipped"
        report["errors"].append(f"host root does not exist: {root}")
        return report

    planned: list[dict[str, Any]] = []
    states: list[str] = []
    for source_overlay in SOURCE_OVERLAYS:
        path = root / source_overlay.relative_path
        if path.is_symlink():
            report["errors"].append(f"refusing symlink source: {path}")
            continue
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(root)
            original = path.read_bytes()
            text = original.decode("utf-8")
        except (OSError, UnicodeError, ValueError) as exc:
            report["errors"].append(f"cannot safely read {path}: {exc}")
            continue

        insertion_states = {
            insertion.name: _classify(text, insertion)
            for insertion in source_overlay.insertions
        }
        states.extend(insertion_states.values())
        updated = text
        for insertion in source_overlay.insertions:
            if insertion_states[insertion.name] == "ready":
                updated = _apply_insertion(updated, insertion)
        planned.append({
            "path": str(path),
            "relative_path": source_overlay.relative_path,
            "before_sha256": _sha256(original),
            "after_sha256": _sha256(updated.encode("utf-8")),
            "insertions": insertion_states,
            "original_bytes": original,
            "updated_bytes": updated.encode("utf-8"),
            "mode": stat.S_IMODE(path.stat().st_mode),
        })

    if report["errors"]:
        report["status"] = "refused"
        return report
    if len(planned) != len(SOURCE_OVERLAYS):
        report["errors"].append("not all target sources passed preflight; no files changed")
        report["status"] = "refused"
        return report
    if any(state == "drift_or_ambiguous" for state in states):
        report["errors"].append("active source anchors are missing, duplicated, or drifted; no files changed")
        report["status"] = "refused"
        report["files"] = [_summary_item(item) for item in planned]
        return report
    if all(state == "applied" for state in states):
        report["status"] = "already_applied"
        report["files"] = [_summary_item(item) for item in planned]
        return report
    if not all(state == "ready" for state in states):
        report["errors"].append("target files are in mixed original/patched state; no files changed")
        report["status"] = "refused"
        report["files"] = [_summary_item(item) for item in planned]
        return report

    report["files"] = [_summary_item(item) for item in planned]
    if not apply:
        report["status"] = "ready"
        return report

    staged: list[tuple[Path, Path]] = []
    replaced: list[dict[str, Path]] = []
    try:
        for item in planned:
            path = Path(item["path"])
            fd, temporary_name = tempfile.mkstemp(
                prefix=f".{path.name}.", suffix=".trace-tmp", dir=path.parent
            )
            temporary = Path(temporary_name)
            with os.fdopen(fd, "wb") as handle:
                handle.write(item["updated_bytes"])
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, item["mode"])
            staged.append((path, temporary))

        for item in planned:
            path = Path(item["path"])
            if _sha256(path.read_bytes()) != item["before_sha256"]:
                raise RuntimeError(f"source changed during preflight: {path}")

        for path, temporary in staged:
            backup = path.with_name(f".{path.name}.trace-rollback-{os.getpid()}")
            fd, backup_name = tempfile.mkstemp(
                prefix=f".{path.name}.", suffix=".trace-backup-tmp", dir=path.parent
            )
            backup_temporary = Path(backup_name)
            with os.fdopen(fd, "wb") as handle:
                handle.write(next(item["original_bytes"] for item in planned if item["path"] == str(path)))
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(backup_temporary, stat.S_IMODE(path.stat().st_mode))
            os.replace(backup_temporary, backup)
            replaced.append({"path": path, "backup": backup})
            os.replace(temporary, path)
    except Exception as exc:
        rollback_errors = []
        for item in reversed(replaced):
            try:
                os.replace(item["backup"], item["path"])
            except OSError as rollback_exc:
                rollback_errors.append(f"{item['path']}: {rollback_exc}")
        report["errors"].append(f"apply failed and rollback attempted: {exc}")
        if rollback_errors:
            report["errors"].append("rollback failures: " + "; ".join(rollback_errors))
        report["status"] = "apply_failed"
        return report
    finally:
        for _, temporary in staged:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    for item in replaced:
        try:
            item["backup"].unlink()
        except FileNotFoundError:
            pass
    for item in report["files"]:
        item["after_sha256"] = _sha256(Path(item["path"]).read_bytes())
    report["status"] = "applied"
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host-root", type=Path, required=True,
                        help="explicit isolated host source root; canonical host is never the default")
    parser.add_argument("--apply", action="store_true", help="apply after exact-anchor preflight")
    parser.add_argument("--report", type=Path, help="optional JSON report destination")
    args = parser.parse_args(argv)
    report = patch_host_root(args.host_root, apply=args.apply)
    serialized = json.dumps(report, indent=2, sort_keys=True)
    print(serialized)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(serialized + "\n", encoding="utf-8")
    return 0 if report["status"] in {"ready", "already_applied", "applied", "skipped"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
