#!/usr/bin/env python3
"""Apply the private, value-only V2 QC/NC host trace to a pinned WRF copy.

The overlay adds observation calls around the already existing KDM6AD bridge
and finish stages. It does not modify any model arithmetic. The default is a
check-only plan; ``--apply`` writes only to an explicitly supplied isolated
source tree after exact source hash and anchor checks.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


SOURCE_PINS = {
    "phys/module_mp_kdm6ad.f90": "457c9b904711397f4cbc01fbcd588c48a7739200ce50d00e30098209d220207a",
    "dyn_em/solve_em.f90": "2e82c883af596e50bb7daa879ff8597a8c572ce03d2b14d0859629201f61c0ea",
}

_MP_INSERTIONS: tuple[tuple[str, tuple[str, ...], tuple[str, ...], str], ...] = (
    (
        "use",
        ("         trace_set_step, trace_record",),
        (
            "    USE kdm6ad_moment_trace_v2, ONLY: moment_trace_begin_call, &",
            "         moment_trace_buffer_values, moment_trace_host_values",
        ),
        "after",
    ),
    (
        "call_id_decl",
        ("    INTEGER :: IM, KM, JM",),
        ("    INTEGER :: moment_trace_call_id",),
        "after",
    ),
    (
        "begin_call",
        ("    JM = JTE - JTS + 1",),
        (
            "    moment_trace_call_id = moment_trace_begin_call(ITIMESTEP, ITS, ITE, &",
            "        KTS, KTE, JTS, JTE, IM, KM, JM, REAL(DELT, c_double), &",
            "        REAL(ncmin_land, c_double), REAL(ncmin_sea, c_double))",
        ),
        "after",
    ),
    (
        "mp_input",
        ("    RC = kdm6_step(TH_IN, Q_IN, QC_IN, QR_IN, QI_IN, QS_IN, QG_IN, &",),
        (
            "    CALL moment_trace_buffer_values('MP_INPUT', moment_trace_call_id, &",
            "        ITS, ITE, KTS, KTE, JTS, JTE, IM, KM, JM, QC_IN, NC_IN)",
        ),
        "before",
    ),
    (
        "mp_output",
        ("    CALL kdm6ad_check_finite_2d(GRAUPEL_INC, 'GRAUPEL increment', ITS, JTS)",),
        (
            "    CALL moment_trace_buffer_values('MP_OUTPUT', moment_trace_call_id, &",
            "        ITS, ITE, KTS, KTE, JTS, JTE, IM, KM, JM, QC_OUT, NC_OUT)",
        ),
        "after",
    ),
    (
        "host_writeback",
        (
            "          diag_rhog(I, K, J) = REAL(RHOG_OUT(II, KK, JJ))",
            "        END DO",
            "      END DO",
            "    END DO",
        ),
        (
            "    CALL moment_trace_host_values('HOST_WRITEBACK', moment_trace_call_id, &",
            "        IMS, IME, KMS, KME, JMS, JME, ITS, ITE, KTS, KTE, JTS, JTE, QC, NC)",
        ),
        "after",
    ),
    (
        "wrapper_post",
        ("", "  END SUBROUTINE kdm6ad", ""),
        (
            "    CALL moment_trace_host_values('WRAPPER_POST', moment_trace_call_id, &",
            "        IMS, IME, KMS, KME, JMS, JME, ITS, ITE, KTS, KTE, JTS, JTE, QC, NC)",
        ),
        "before",
    ),
)

_SOLVE_INSERTIONS: tuple[tuple[str, tuple[str, ...], tuple[str, ...], str], ...] = (
    (
        "use",
        ("   USE module_microphysics_zero_out",),
        (
            "   USE kdm6ad_moment_trace_v2, ONLY: moment_trace_finish_values",
        ),
        "after",
    ),
    (
        "zero_out_pre",
        (
            "       IF ( config_flags%mp_zero_out > 0 ) THEN",
            "       CALL microphysics_zero_outb (                                    &",
        ),
        (
            "       CALL moment_trace_finish_values('ZERO_OUT_PRE', grid%itimestep, &",
            "           ims, ime, kms, kme, jms, jme, its, ite, k_start, k_end, jts, jte, &",
            "           moist(ims,kms,jms,P_QC), scalar(ims,kms,jms,P_QNC))",
        ),
        "before",
    ),
    (
        "moments_pre",
        ("       CALL moist_physics_finish_em( grid%t_2, grid%t_1, t0, grid%muts, th_phy,  &",),
        (
            "       CALL moment_trace_finish_values('MOMENTS_PRE', grid%itimestep, &",
            "           ims, ime, kms, kme, jms, jme, its, ite, k_start, k_end, jts, jte, &",
            "           moist(ims,kms,jms,P_QC), scalar(ims,kms,jms,P_QNC))",
            "",
        ),
        "before",
    ),
    (
        "moments_post",
        (
            "       CALL moist_physics_finish_em( grid%t_2, grid%t_1, t0, grid%muts, th_phy,  &",
            "                                     grid%h_diabatic, dtm,                       &",
            "                                     moist(ims,kms,jms,P_QV),grid%qv_diabatic,   &",
            "                                     moist(ims,kms,jms,P_QC),grid%qc_diabatic,   &",
            "                                     grid%th_phy_m_t0,                           &",
            "                                     config_flags,                               &",
            "                                     ids, ide, jds, jde, kds, kde,               &",
            "                                     ims, ime, jms, jme, kms, kme,               &",
            "                                     its, ite, jts, jte,                         &",
            "                                     k_start    , k_end                          )",
        ),
        (
            "       CALL moment_trace_finish_values('MOMENTS_POST', grid%itimestep, &",
            "           ims, ime, kms, kme, jms, jme, its, ite, k_start, k_end, jts, jte, &",
            "           moist(ims,kms,jms,P_QC), scalar(ims,kms,jms,P_QNC))",
        ),
        "after",
    ),
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _patch_text(text: str, insertions: tuple[tuple[str, tuple[str, ...], tuple[str, ...], str], ...]) -> tuple[str, dict[str, str]]:
    states: dict[str, str] = {}
    updated = text
    for name, anchor, code, position in insertions:
        anchor_text = "\n".join(anchor)
        code_text = "\n".join(code)
        if code_text and code_text in updated:
            states[name] = "already_present"
            continue
        count = updated.count(anchor_text)
        if count != 1:
            states[name] = "missing_or_ambiguous"
            continue
        replacement = f"{code_text}\n{anchor_text}" if position == "before" else f"{anchor_text}\n{code_text}"
        updated = updated.replace(anchor_text, replacement, 1)
        states[name] = "inserted"
    return updated, states


def build_overlay_plan(host_root: Path) -> dict[str, Any]:
    root = host_root.expanduser().resolve(strict=True)
    report: dict[str, Any] = {
        "schema": "kdm6ad.native_moment_trace_overlay.v2",
        "host_root": str(root),
        "status": "blocked",
        "files": [],
        "errors": [],
    }
    if not root.is_dir():
        report["errors"].append("host root must be an existing isolated source directory")
        return report
    for rel, expected in SOURCE_PINS.items():
        path = root / rel
        if path.is_symlink():
            report["errors"].append(f"refusing symlink source: {path}")
            continue
        try:
            before = path.read_bytes()
            text = before.decode("utf-8")
        except (OSError, UnicodeError) as exc:
            report["errors"].append(f"cannot read {path}: {exc}")
            continue
        actual = _sha256(before)
        if actual != expected:
            report["errors"].append(f"source pin mismatch for {rel}: expected {expected}, got {actual}")
            continue
        insertions = _MP_INSERTIONS if rel.startswith("phys/") else _SOLVE_INSERTIONS
        updated, states = _patch_text(text, insertions)
        if any(state != "inserted" for state in states.values()):
            report["errors"].append(f"overlay anchors not uniquely ready for {rel}: {states}")
        report["files"].append({
            "relative_path": rel,
            "source_sha256": actual,
            "overlay_sha256": _sha256(updated.encode("utf-8")),
            "insertions": states,
            "_path": str(path),
            "_content": updated,
        })
    if report["errors"]:
        return report
    report["status"] = "ready"
    return report


def apply_overlay(host_root: Path) -> dict[str, Any]:
    report = build_overlay_plan(host_root)
    if report["status"] != "ready":
        return report
    staged: list[tuple[Path, Path, str]] = []
    try:
        for item in report["files"]:
            path = Path(item["_path"])
            if _sha256(path.read_bytes()) != item["source_sha256"]:
                raise RuntimeError(f"source changed during overlay preflight: {path}")
            fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".moment-v2-tmp", dir=path.parent)
            temp_path = Path(name)
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                handle.write(item["_content"])
                handle.flush()
                os.fsync(handle.fileno())
            staged.append((path, temp_path, item["source_sha256"]))
        for path, temp_path, source_hash in staged:
            if _sha256(path.read_bytes()) != source_hash:
                raise RuntimeError(f"source changed before replacement: {path}")
            os.replace(temp_path, path)
        report["status"] = "applied"
    except Exception as exc:
        report["errors"].append(str(exc))
        report["status"] = "failed"
        for _, temp_path, _ in staged:
            temp_path.unlink(missing_ok=True)
    for item in report["files"]:
        item.pop("_path", None)
        item.pop("_content", None)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host-root", type=Path, required=True, help="explicit isolated private host source tree")
    parser.add_argument("--apply", action="store_true", help="write after source-pin and unique-anchor checks")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    report = apply_overlay(args.host_root) if args.apply else build_overlay_plan(args.host_root)
    serializable = {**report, "files": [{k: v for k, v in item.items() if not k.startswith("_")} for item in report["files"]]}
    rendered = json.dumps(serializable, indent=2, sort_keys=True)
    print(rendered)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["status"] in {"ready", "applied"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
