#!/usr/bin/env python3
"""Opt-in, exact-context patch for restart-time host initializers.

Default operation is check-only.  The tool targets only the two specifically
named private host sources and refuses drifted or partially patched contexts.
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
class Snippet:
    name: str
    old: str
    new: str


@dataclass(frozen=True)
class SourcePatch:
    relative_path: str
    snippets: tuple[Snippet, ...]


_TREE_CANOPY = Snippet(
    name="tree_canopy_restart_guard",
    old="   IF (itree_canopy .ne. 0) then",
    new="   IF ((itree_canopy .ne. 0) .AND. (.NOT. restart)) then",
)

_URBAN_FLUXES = Snippet(
    name="urban_restart_flux_guards",
    old=(
        "      SH_URB2D(I,J)=0.\n"
        "      LH_URB2D(I,J)=0.\n"
        "      G_URB2D(I,J)=0.\n"
        "      RN_URB2D(I,J)=0."
    ),
    new=(
        "      IF (.NOT.restart) THEN\n"
        "      SH_URB2D(I,J)=0.\n"
        "      LH_URB2D(I,J)=0.\n"
        "      G_URB2D(I,J)=0.\n"
        "      RN_URB2D(I,J)=0.\n"
        "      ENDIF"
    ),
)

_URBAN_QC = Snippet(
    name="urban_restart_qc_guard",
    old="      QC_URB2D(I,J)=0.01",
    new="      IF (.NOT.restart) QC_URB2D(I,J)=0.01",
)

SOURCE_PATCHES = (
    SourcePatch("phys/module_physics_init.F", (_TREE_CANOPY,)),
    SourcePatch("phys/module_sf_urban.F", (_URBAN_FLUXES, _URBAN_QC)),
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _classify(text: str, snippet: Snippet) -> str:
    old_count = text.count(snippet.old)
    new_count = text.count(snippet.new)
    embedded_old_count = 1 if snippet.old in snippet.new else 0
    if new_count == 1 and old_count == embedded_old_count:
        return "applied"
    if new_count == 0 and old_count == 1:
        return "ready"
    return "drift_or_ambiguous"


def patch_host_root(host_root: str | Path, *, apply: bool = False) -> dict[str, Any]:
    """Check/apply under ``host_root``; caught replace failures trigger rollback.

    A hard interruption between the two file replacements can leave mixed
    state.  A later invocation refuses that state for manual review.
    """
    root = Path(host_root).expanduser().resolve()
    report: dict[str, Any] = {
        "schema": "kdm6ad.restart_state_init_patch.v1",
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
    for source_patch in SOURCE_PATCHES:
        path = root / source_patch.relative_path
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

        snippet_states = {snippet.name: _classify(text, snippet) for snippet in source_patch.snippets}
        states.extend(snippet_states.values())
        updated = text
        for snippet in source_patch.snippets:
            if snippet_states[snippet.name] == "ready":
                updated = updated.replace(snippet.old, snippet.new, 1)
        planned.append({
            "path": str(path),
            "relative_path": source_patch.relative_path,
            "before_sha256": _sha256(original),
            "after_sha256": _sha256(updated.encode("utf-8")),
            "snippet_states": snippet_states,
            "original_bytes": original,
            "updated_bytes": updated.encode("utf-8"),
            "mode": stat.S_IMODE(path.stat().st_mode),
        })

    if report["errors"]:
        report["status"] = "refused"
        return report
    if any(state == "drift_or_ambiguous" for state in states):
        report["errors"].append("source context is missing, duplicated, or drifted; no files changed")
        report["status"] = "refused"
        report["files"] = [{k: v for k, v in item.items() if not k.endswith("_bytes")} for item in planned]
        return report
    if len(planned) != len(SOURCE_PATCHES):
        report["errors"].append("not all target sources passed preflight; no files changed")
        report["status"] = "refused"
        return report

    if all(state == "applied" for state in states):
        report["status"] = "already_applied"
        report["files"] = [{k: v for k, v in item.items() if not k.endswith("_bytes")} for item in planned]
        return report
    if not all(state == "ready" for state in states):
        report["errors"].append("target files are in mixed original/patched state; no files changed")
        report["status"] = "refused"
        report["files"] = [{k: v for k, v in item.items() if not k.endswith("_bytes")} for item in planned]
        return report

    report["files"] = [{k: v for k, v in item.items() if not k.endswith("_bytes")} for item in planned]
    if not apply:
        report["status"] = "ready"
        return report

    staged: list[tuple[Path, Path, int]] = []
    replaced: list[dict[str, Any]] = []
    try:
        for item in planned:
            path = Path(item["path"])
            fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".patch-tmp", dir=path.parent)
            temp = Path(temp_name)
            with os.fdopen(fd, "wb") as handle:
                handle.write(item["updated_bytes"])
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temp, item["mode"])
            staged.append((path, temp, item["mode"]))

        # Recheck both originals after staging and before the first replacement.
        for item in planned:
            path = Path(item["path"])
            if _sha256(path.read_bytes()) != item["before_sha256"]:
                raise RuntimeError(f"source changed during preflight: {path}")

        for path, temp, mode in staged:
            backup = path.with_name(f".{path.name}.rollback-{os.getpid()}")
            fd, backup_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".rollback-tmp", dir=path.parent)
            backup_temp = Path(backup_name)
            with os.fdopen(fd, "wb") as handle:
                handle.write(next(item["original_bytes"] for item in planned if item["path"] == str(path)))
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(backup_temp, mode)
            os.replace(backup_temp, backup)
            replaced.append({"path": path, "backup": backup})
            os.replace(temp, path)
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
        for _, temp, _ in staged:
            try:
                temp.unlink()
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


def _default_host_root() -> Path:
    return Path(__file__).resolve().parents[1] / "host" / "KIM-meso_v1.0"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host-root", type=Path, default=_default_host_root(),
                        help="private host/KIM-meso_v1.0 source root (default: sibling host tree)")
    parser.add_argument("--apply", action="store_true", help="write the preflighted patch; default is check-only")
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
