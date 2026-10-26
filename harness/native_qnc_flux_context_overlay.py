#!/usr/bin/env python3
"""Source-pinned value-only QNC context setter around RK advection calls.

This overlay changes only an isolated saved ``module_em.f90`` source copy. It
adds the trace context before the generic and positive-definite scalar
advection calls inside ``rk_scalar_tend`` and clears it immediately afterward.
It never changes physics values or the external Fortran/C ABI.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any


SOURCE_RELATIVE_PATH = "dyn_em/module_em.f90"
BASE_SOURCE_SHA256 = "53207a03dba5b3a42edb43891368f09318a59d44ced480f8ef982184a9e0034e"

_ADVECT_USE_ANCHOR = (
    "   USE module_advect_em, only: advect_u, advect_v, advect_w, advect_scalar, advect_scalar_pd, advect_scalar_mono, &",
    "        advect_weno_u, advect_weno_v, advect_weno_w, advect_scalar_weno,  advect_scalar_wenopd",
)
_ADVECT_USE_CODE = ("   USE module_advect_em, ONLY: qnc_flux_trace_set_context",)
_STATE_USE_ANCHOR = (
    "  USE module_state_description, only: param_first_scalar, p_qr, p_qv, p_qc, p_qg, p_qi, p_qs, tiedtkescheme,ntiedtkescheme, heldsuarez, &",
    "        positivedef, gdscheme, g3scheme, gfscheme, kfetascheme, mskfscheme, monotonic, wenopd_scalar, weno_scalar, weno_mom",
)
_STATE_USE_CODE = ("  USE module_state_description, ONLY: P_QNC",)

_PD_CALL = (
    "        CALL advect_scalar_pd       ( scalar(ims,kms,jms,im),             &",
    "                                      scalar_old(ims,kms,jms,im),         &",
    "                                      advect_tend(ims,kms,jms),           &",
    "                                      h_tendency(ims,kms,jms),            &",
    "                                      z_tendency(ims,kms,jms),            &",
    "                                      ru, rv, wwE, c1h, c2h,              &",
    "                                      mut, mub, mu_old,                   &",
    "                                      time_step, config_flags, tenddec,   &",
    "                                      msfux, msfuy, msfvx, msfvy,         &",
    "                                      msftx, msfty, fnm, fnp,             &",
    "                                      rdx, rdy, rdnw, dt_step,            &",
    "                                      ids, ide, jds, jde, kds, kde,       &",
    "                                      ims, ime, jms, jme, kms, kme,       &",
    "                                      its, ite, jts, jte, kts, kte, &",
    "                                         s15_step=s15_step, &",
    "                                         s15_rk=s15_rk, &",
    "                                         s15_owner=s15_owner, &",
    "                                         s15_tile=s15_tile, &",
    "                                         s15_branch=2 )",
)
_GENERIC_CALL = (
    "        CALL advect_scalar     ( scalar(ims,kms,jms,im),        &",
    "                                 scalar(ims,kms,jms,im),        &",
    "                                 advect_tend(ims,kms,jms),      &",
    "                                 ru, rv, wwE, c1h, c2h,         &",
    "                                 mut, time_step,                &",
    "                                 config_flags,                  &",
    "                                 msfux, msfuy, msfvx, msfvy,    &",
    "                                 msftx, msfty, fnm, fnp,        &",
    "                                 rdx, rdy, rdnw,                &",
    "                                 ids, ide, jds, jde, kds, kde,  &",
    "                                 ims, ime, jms, jme, kms, kme,  &",
    "                                 its, ite, jts, jte, kts, kte, &",
    "                                    s15_step=s15_step, &",
    "                                    s15_rk=s15_rk, &",
    "                                    s15_owner=s15_owner, &",
    "                                    s15_tile=s15_tile, &",
    "                                    s15_branch=1 )",
)

_PD_SET = (
    "        CALL qnc_flux_trace_set_context(im, P_QNC, rk_step, dt_step, moist_step)",
)
_PD_RESET = (
    "        CALL qnc_flux_trace_set_context(0, P_QNC, 0, 0.0, .TRUE.)",
)
_GENERIC_SET = _PD_SET
_GENERIC_RESET = _PD_RESET


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _anchor_matches(text: str, anchor: tuple[str, ...]) -> list[tuple[int, int]]:
    lines = text.splitlines(keepends=True)
    normalized = [" ".join(line.rstrip("\r\n").split()) for line in lines]
    offsets: list[int] = []
    position = 0
    for line in lines:
        offsets.append(position)
        position += len(line)
    pattern = [" ".join(line.split()) for line in anchor if line.strip()]
    matches = []
    for start, line in enumerate(normalized):
        if line != pattern[0]:
            continue
        index = start
        found = True
        for expected in pattern[1:]:
            index += 1
            while index < len(normalized) and not normalized[index].strip():
                index += 1
            if index >= len(normalized) or normalized[index] != expected:
                found = False
                break
        if found:
            end = offsets[index] + len(lines[index].rstrip("\r\n"))
            matches.append((offsets[start], end))
    return matches


def _apply_insertions(text: str) -> tuple[str, dict[str, str]]:
    updated = text
    insertions: dict[str, str] = {}

    def apply(name: str, anchor: tuple[str, ...], code: tuple[str, ...], *, before: bool) -> None:
        nonlocal updated
        spans = _anchor_matches(updated, anchor)
        insertions[name] = "ready" if len(spans) == 1 else "missing_or_ambiguous"
        if len(spans) != 1:
            return
        start, end = spans[0]
        newline = "\r\n" if "\r\n" in updated else "\n"
        statement = newline.join(code)
        if before:
            updated = updated[:start] + statement + newline + updated[start:]
        else:
            updated = updated[:end] + newline + statement + updated[end:]

    apply("advect_trace_use", _ADVECT_USE_ANCHOR, _ADVECT_USE_CODE, before=False)
    apply("qnc_index_use", _STATE_USE_ANCHOR, _STATE_USE_CODE, before=False)
    apply("pd_context_set", _PD_CALL, _PD_SET, before=True)
    apply("pd_context_reset", _PD_CALL, _PD_RESET, before=False)
    apply("generic_context_set", _GENERIC_CALL, _GENERIC_SET, before=True)
    apply("generic_context_reset", _GENERIC_CALL, _GENERIC_RESET, before=False)
    return updated, insertions


def build_overlay_plan(source_path: Path) -> dict[str, Any]:
    path = Path(source_path).expanduser()
    report: dict[str, Any] = {
        "schema": "kdm6ad.qnc_flux_context_overlay.v1",
        "status": "blocked",
        "errors": [],
        "file": None,
    }
    if path.is_symlink() or not path.is_file():
        report["errors"].append(f"refusing missing or symlink module_em source: {path}")
        return report
    original = path.read_bytes()
    actual = _sha256(original)
    report["file"] = {"path": str(path.resolve()), "source_sha256": actual}
    if actual != BASE_SOURCE_SHA256:
        report["errors"].append(f"module_em source pin mismatch: expected {BASE_SOURCE_SHA256}, got {actual}")
        return report
    try:
        text = original.decode("utf-8")
    except UnicodeDecodeError as exc:
        report["errors"].append(f"module_em source is not UTF-8 text: {exc}")
        return report
    updated, insertions = _apply_insertions(text)
    report["file"]["insertions"] = insertions
    report["file"]["overlay_sha256"] = _sha256(updated.encode())
    if any(value != "ready" for value in insertions.values()):
        report["errors"].append("one or more exact module_em anchors are missing or ambiguous")
        return report
    for call, prefix in ((_PD_CALL, "pd"), (_GENERIC_CALL, "generic")):
        span = _anchor_matches(updated, call)
        if len(span) != 1:
            report["errors"].append(f"{prefix} advect call is missing or ambiguous after overlay")
            return report
        start, end = span[0]
        set_pos = updated.index("CALL qnc_flux_trace_set_context(im, P_QNC, rk_step, dt_step, moist_step)", 0, start)
        reset_pos = updated.index("CALL qnc_flux_trace_set_context(0, P_QNC, 0, 0.0, .TRUE.)", end)
        if not (set_pos < start < end < reset_pos):
            report["errors"].append(f"{prefix} context setter/reset do not bracket its advect call")
            return report
    report["status"] = "ready"
    return report


def apply_overlay(source_path: Path, *, output_path: Path) -> dict[str, Any]:
    report = build_overlay_plan(source_path)
    if report["status"] != "ready":
        return report
    source = Path(source_path).resolve(strict=True)
    output = Path(output_path)
    if output.exists() or output.is_symlink():
        report["status"] = "refused"
        report["errors"].append(f"overlay output must be new: {output}")
        return report
    original = source.read_bytes()
    updated, states = _apply_insertions(original.decode("utf-8"))
    if any(value != "ready" for value in states.values()):
        report["status"] = "refused"
        report["errors"].append("source anchors changed between preflight and write")
        return report
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".qnc-context-tmp", dir=output.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(updated)
            handle.flush()
            os.fsync(handle.fileno())
        if _sha256(source.read_bytes()) != BASE_SOURCE_SHA256:
            raise RuntimeError("module_em source changed during preflight")
        if output.exists() or output.is_symlink():
            raise FileExistsError(output)
        os.replace(temporary, output)
        report["file"]["output_path"] = str(output.resolve())
        report["file"]["overlay_sha256"] = _sha256(output.read_bytes())
        report["status"] = "applied"
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        report["status"] = "failed"
        report["errors"].append(str(exc))
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="pinned saved V3 module_em.f90 input")
    parser.add_argument("--output", type=Path, help="new private module_em.f90 destination")
    parser.add_argument("--apply", action="store_true", help="write after exact pin and anchor checks")
    args = parser.parse_args(argv)
    if args.apply and args.output is None:
        parser.error("--output is required with --apply")
    report = apply_overlay(args.source, output_path=args.output) if args.apply else build_overlay_plan(args.source)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] in {"ready", "applied"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
