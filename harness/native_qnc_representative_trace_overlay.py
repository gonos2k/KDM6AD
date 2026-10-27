"""Render an opt-in four-column QC/NC/QI/NI boundary trace in private solve_em.

Only trace targets, fields, stage calls, and output identity change. The
executed RK, scalar boundary, KDM and finish arithmetic remain untouched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


BASE_SHA256 = "0842aafdd2ba4fb252fe8dc58f18043d691a818b9fc092ee533c693f4574f85d"
TRACE_ENV = "KDM6AD_QNC_REPRESENTATIVE_TRACE_DIR"
TRACE_FILE = "representative_moments.tsv"
MAGIC = "# KDM6AD_REPRESENTATIVE_MOMENTS_V1"
TARGETS_IJK = ((153, 111, 4), (113, 70, 12), (155, 120, 15), (1, 168, 33))

REPLACEMENTS = (
    ("INTEGER, PARAMETER :: KDM6AD_UPNC_NTARGET = 7",
     "INTEGER, PARAMETER :: KDM6AD_UPNC_NTARGET = 4"),
    ("INTEGER, PARAMETER :: KDM6AD_UPNC_I(KDM6AD_UPNC_NTARGET) = (/ 221, 220, 222, 221, 221, 221, 221 /)",
     "INTEGER, PARAMETER :: KDM6AD_UPNC_I(KDM6AD_UPNC_NTARGET) = (/ 153, 113, 155, 1 /)"),
    ("INTEGER, PARAMETER :: KDM6AD_UPNC_K(KDM6AD_UPNC_NTARGET) = (/ 6, 6, 6, 6, 6, 5, 7 /)",
     "INTEGER, PARAMETER :: KDM6AD_UPNC_K(KDM6AD_UPNC_NTARGET) = (/ 4, 12, 15, 33 /)"),
    ("INTEGER, PARAMETER :: KDM6AD_UPNC_J(KDM6AD_UPNC_NTARGET) = (/ 63, 63, 63, 62, 64, 63, 63 /)",
     "INTEGER, PARAMETER :: KDM6AD_UPNC_J(KDM6AD_UPNC_NTARGET) = (/ 111, 70, 120, 168 /)"),
    ("KDM6AD_QNC_STATE7_TRACE_DIR", TRACE_ENV),
    ("'/qnc_state7.tsv'", f"'/{TRACE_FILE}'"),
    ("# KDM6AD_QNC_STATE7_TRACE_V2", MAGIC),
    ("      CALL kdm6ad_upnc_write_real(step, rk_step, stage, i, k, j, 'QNC', scalar(i,k,j,P_QNC))\n"
     "      IF (mode .EQ. 0) CYCLE",
     "      CALL kdm6ad_upnc_write_real(step, rk_step, stage, i, k, j, 'QNC', scalar(i,k,j,P_QNC))\n"
     "      CALL kdm6ad_upnc_write_real(step, rk_step, stage, i, k, j, 'QC', moist(i,k,j,P_QC))\n"
     "      CALL kdm6ad_upnc_write_real(step, rk_step, stage, i, k, j, 'QI', moist(i,k,j,P_QI))\n"
     "      CALL kdm6ad_upnc_write_real(step, rk_step, stage, i, k, j, 'NI', scalar(i,k,j,P_QNI))\n"
     "      IF (mode .EQ. 0) CYCLE"),
    ("     CALL wrf_debug ( 200 , ' call moist_physics_finish' )",
     "     CALL kdm6ad_upnc_trace('POST_MICROPHYSICS', grid%itimestep, 0, dtm, 0, &\n"
     "                           ids, ide-1, jds, jde-1, k_start, k_end)\n"
     "     CALL wrf_debug ( 200 , ' call moist_physics_finish' )"),
    ("CALL HALO_EM_THETAM_sub ( grid,",
     "     CALL kdm6ad_upnc_trace('POST_FINISH', grid%itimestep, 0, dtm, 0, &\n"
     "                           ids, ide-1, jds, jde-1, k_start, k_end)\n"
     "CALL HALO_EM_THETAM_sub ( grid,"),
)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def inject(text: str) -> str:
    for old, new in REPLACEMENTS:
        if text.count(old) != 1:
            raise ValueError(f"representative trace source anchor differs: {old[:72]!r}")
        text = text.replace(old, new, 1)
    if (text.count("CALL kdm6ad_upnc_trace('RKSCALAR_PD_BEFORE'") != 1 or
            text.count("CALL kdm6ad_upnc_trace('RKSCALAR_PD_AFTER'") != 1 or
            text.count("CALL kdm6ad_upnc_trace('RKSCALAR_BEFORE'") != 1 or
            text.count("CALL kdm6ad_upnc_trace('RKSCALAR_AFTER'") != 1 or
            text.count("CALL kdm6ad_upnc_trace('PRE_MICROPHYSICS'") != 1 or
            text.count("CALL kdm6ad_upnc_trace('POST_MICROPHYSICS'") != 1 or
            text.count("CALL kdm6ad_upnc_trace('POST_FINISH'") != 1):
        raise ValueError("representative RK/MP/finish stage inventory differs")
    return text


def render(raw: bytes) -> bytes:
    if sha(raw) != BASE_SHA256:
        raise ValueError("private state7 solve_em source SHA differs")
    return inject(raw.decode("utf-8")).encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink() or args.source.resolve() == args.output.resolve():
        raise FileExistsError("representative trace requires a fresh path distinct from source")
    output = render(args.source.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as stream:
        stream.write(output)
    print(json.dumps({"status": "REPRESENTATIVE_TRACE_OVERLAY_WRITTEN",
                      "base_sha256": BASE_SHA256, "overlay_sha256": sha(output),
                      "trace_env": TRACE_ENV, "trace_file": TRACE_FILE,
                      "targets_ijk_one_based": TARGETS_IJK}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
