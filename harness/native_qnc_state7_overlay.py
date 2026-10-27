#!/usr/bin/env python3
"""Expand the saved opt-in upstream QNC trace to the native seven-cell star.

The input is the hash-pinned generated solve_em.f90 used by the PR456–PR459
private executable lineage. Only trace target constants and trace output
identity change; the RK/PD update expressions and external ABI do not.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


BASE_SHA256 = "a10a2aae453f1d0fcaa96d288d235db0087df3c6a28a4d4035e39f53790c8f71"
TRACE_ENV = "KDM6AD_QNC_STATE7_TRACE_DIR"
TRACE_FILE = "qnc_state7.tsv"
MAGIC = "# KDM6AD_QNC_STATE7_TRACE_V2"

_REPLACEMENTS = (
    ("INTEGER, PARAMETER :: KDM6AD_UPNC_NTARGET = 2",
     "INTEGER, PARAMETER :: KDM6AD_UPNC_NTARGET = 7"),
    ("INTEGER, PARAMETER :: KDM6AD_UPNC_I(KDM6AD_UPNC_NTARGET) = (/ 221, 91 /)",
     "INTEGER, PARAMETER :: KDM6AD_UPNC_I(KDM6AD_UPNC_NTARGET) = (/ 221, 220, 222, 221, 221, 221, 221 /)"),
    ("INTEGER, PARAMETER :: KDM6AD_UPNC_K(KDM6AD_UPNC_NTARGET) = (/ 6, 4 /)",
     "INTEGER, PARAMETER :: KDM6AD_UPNC_K(KDM6AD_UPNC_NTARGET) = (/ 6, 6, 6, 6, 6, 5, 7 /)"),
    ("INTEGER, PARAMETER :: KDM6AD_UPNC_J(KDM6AD_UPNC_NTARGET) = (/ 63, 94 /)",
     "INTEGER, PARAMETER :: KDM6AD_UPNC_J(KDM6AD_UPNC_NTARGET) = (/ 63, 63, 63, 62, 64, 63, 63 /)"),
    ("KDM6AD_UPSTREAM_NC_TRACE_DIR", TRACE_ENV),
    ("'/upstream_nc.tsv'", f"'/{TRACE_FILE}'"),
    ("# KDM6AD_UPSTREAM_NC_TRACE_V1", MAGIC),
    ("         ENDDO scalar_tile_loop_2",
     "           IF (is .EQ. P_QNC .AND. rk_step .EQ. rk_order) THEN\n"
     "             CALL kdm6ad_upnc_trace('POST_SCALAR_BDY', grid%itimestep, rk_step, &\n"
     "                  dt_rk, 0, grid%i_start(ij), grid%i_end(ij), &\n"
     "                  grid%j_start(ij), grid%j_end(ij), k_start, k_end)\n"
     "           END IF\n"
     "         ENDDO scalar_tile_loop_2"),
)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def render(source: bytes) -> bytes:
    if _sha(source) != BASE_SHA256:
        raise ValueError("saved solve_em.f90 source SHA differs")
    text = source.decode("utf-8")
    for old, new in _REPLACEMENTS:
        if text.count(old) != 1:
            raise ValueError(f"expected exactly one trace-only source anchor: {old!r}")
        text = text.replace(old, new, 1)
    if text.count("CALL kdm6ad_upnc_trace('RKSCALAR_PD_BEFORE'") != 1:
        raise ValueError("PD-before event must still have exactly one call site")
    if text.count("CALL kdm6ad_upnc_trace('RKSCALAR_PD_AFTER'") != 1:
        raise ValueError("PD-after event must still have exactly one call site")
    if text.count("CALL kdm6ad_upnc_trace('RKSCALAR_BEFORE'") != 1:
        raise ValueError("RK-before event must still have exactly one call site")
    if text.count("CALL kdm6ad_upnc_trace('RKSCALAR_AFTER'") != 1:
        raise ValueError("RK-after event must still have exactly one call site")
    if text.count("CALL kdm6ad_upnc_trace('POST_SCALAR_BDY'") != 1:
        raise ValueError("post-boundary state event must have exactly one call site")
    return text.encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", type=Path, help="write only to a new path")
    args = parser.parse_args()
    source = args.source.read_bytes()
    output = render(source)
    result = {"base_sha256": _sha(source), "overlay_sha256": _sha(output),
              "trace_env": TRACE_ENV, "trace_file": TRACE_FILE}
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("xb") as stream:
            stream.write(output)
        result["output"] = str(args.output)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
