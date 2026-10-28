"""Version the PR #474 QNC trace with pre-limit faces, receivers and a seam.

This overlay only adds opt-in recording. It captures each selected cell's six
correction faces before *any* PD limiter scale and all final applied faces
after the complete limiter loop, before tendency accumulation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.native_qnc_domain_preflight_advect_overlay import (  # noqa: E402
    ADVECT_SOURCE_SHA256 as PR471_SOURCE_SHA256,
    TARGET_COORDS_SHA256 as FAILURE_COORDS_SHA256,
    _module_declarations, failure_layer_coordinates,
)


SOURCE_SHA256 = "26d946fdfaf3926cb0997e01717bbcfd2c283038fdec0699571ba98d38c0b9e9"
UNION_SHA256 = "9813c6b79b087233c61e348e92cc394f8a66d952da81cd5c821895a5eeae1536"
SEAM_SENTINELS_IKJ = (
    (113, 12, 142), (113, 12, 143),
    (116, 6, 142), (116, 6, 143),
    (131, 8, 142), (131, 8, 143),
    (198, 12, 142), (198, 12, 143),
)
TRACE_ENV = "KDM6AD_QNC_CANDIDATE_INPUTS_DIR"


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _replace(text: str, before: str, after: str) -> str:
    if text.count(before) != 1:
        raise ValueError(f"PR474 candidate-face source anchor differs: {before[:72]!r}")
    return text.replace(before, after)


def receiver_union(failure_json: bytes) -> tuple[tuple[int, int, int], ...]:
    donors = failure_layer_coordinates(failure_json)
    cells = set(donors)
    for i, k, j in donors:
        cells.update(((i - 1, k, j), (i + 1, k, j), (i, k, j - 1),
                      (i, k, j + 1), (i, k - 1, j), (i, k + 1, j)))
    cells.update(SEAM_SENTINELS_IKJ)
    result = tuple(sorted(cells))
    raw = ("\n".join(f"{i},{k},{j}" for i, k, j in result) + "\n").encode()
    if (len(result) != 382 or sha(raw) != UNION_SHA256 or
            any(not (1 <= i <= 234 and 1 <= j <= 282 and 1 <= k <= 39)
                for i, k, j in result)):
        raise ValueError("QNC donor/receiver union differs")
    return result


def render_advect(source: bytes, failure_json: bytes) -> tuple[bytes, tuple[tuple[int, int, int], ...]]:
    if sha(source) != SOURCE_SHA256:
        raise ValueError("PR474 private advection source changed")
    donors = failure_layer_coordinates(failure_json)
    cells = receiver_union(failure_json)
    text = source.decode("utf-8")
    text = _replace(text, _module_declarations(donors), _module_declarations(cells))
    text = _replace(text, "'KDM6AD_QNC_DOMAIN_PREFLIGHT_DIR'", f"'{TRACE_ENV}'")
    text = _replace(text, "'/qnc_domain_preflight.tsv'", "'/qnc_candidate_faces.tsv'")
    text = _replace(text, "# KDM6AD_QNC_DOMAIN_PREFLIGHT_V1",
                    "# KDM6AD_QNC_CANDIDATE_FACES_V1")
    text = _replace(text, f"# SOURCE_SHA256 {PR471_SOURCE_SHA256}",
                    f"# SOURCE_SHA256 {SOURCE_SHA256}")
    text = _replace(text, f"# TARGET_COORDS_SHA256 {FAILURE_COORDS_SHA256}",
                    f"# CAPTURE_COORDS_SHA256 {UNION_SHA256}")
    text = _replace(text,
        "'FX_POST_WEST FX_POST_EAST FY_POST_SOUTH FY_POST_NORTH FZ_POST_BOTTOM FZ_POST_TOP'",
        "'FX_POST_WEST FX_POST_EAST FY_POST_SOUTH FY_POST_NORTH FZ_POST_BOTTOM FZ_POST_TOP ' // &\n"
        "         'FX_PRE_WEST FX_PRE_EAST FY_PRE_SOUTH FY_PRE_NORTH FZ_PRE_BOTTOM FZ_PRE_TOP'")
    text = _replace(text, "REAL,INTENT(IN) :: values(26)", "REAL,INTENT(IN) :: values(32)")
    text = _replace(text, "INTEGER(C_INT32_T) :: words(26)", "INTEGER(C_INT32_T) :: words(32)")
    text = _replace(text, "DO n=1,26", "DO n=1,32")
    text = _replace(text, "26(Z8.8,1X)", "32(Z8.8,1X)")
    sub_start = text.index("SUBROUTINE advect_scalar_pd")
    sub_end = text.index("END SUBROUTINE advect_scalar_pd", sub_start) + len("END SUBROUTINE advect_scalar_pd")
    block = text[sub_start:sub_end]
    block = _replace(block,
        "   REAL :: qnc_pref_scale(QNC_PREF_NTARGET)\n",
        "   REAL :: qnc_pref_scale(QNC_PREF_NTARGET)\n"
        "   REAL :: qnc_pref_pre(6,QNC_PREF_NTARGET)\n"
        "   LOGICAL :: qnc_pref_pre_seen(QNC_PREF_NTARGET)\n")
    begin = ("       qnc_pref_scale=1.0\n"
             "       qnc_pref_hit=0\n"
             "       qnc_pref_seen=.FALSE.\n"
             "     END IF\n"
             "   END IF\n   DO j=j_start, j_end")
    capture = ("       qnc_pref_scale=1.0\n"
               "       qnc_pref_hit=0\n"
               "       qnc_pref_seen=.FALSE.\n"
               "       qnc_pref_pre_seen=.FALSE.\n"
               "       DO qnc_pref_n=1,QNC_PREF_NTARGET\n"
               "         qnc_pref_cell_i=QNC_PREF_I(qnc_pref_n)\n"
               "         qnc_pref_cell_k=QNC_PREF_K(qnc_pref_n)\n"
               "         qnc_pref_cell_j=QNC_PREF_J(qnc_pref_n)\n"
               "         IF (qnc_pref_cell_i.GE.its .AND. qnc_pref_cell_i.LE.MIN(ite,ide-1) .AND. &\n"
               "             qnc_pref_cell_j.GE.jts .AND. qnc_pref_cell_j.LE.MIN(jte,jde-1) .AND. &\n"
               "             qnc_pref_cell_k.GE.kts .AND. qnc_pref_cell_k.LE.ktf) THEN\n"
               "           qnc_pref_pre(:,qnc_pref_n)=(/ &\n"
               "               fqx(qnc_pref_cell_i,qnc_pref_cell_k,qnc_pref_cell_j), &\n"
               "               fqx(qnc_pref_cell_i+1,qnc_pref_cell_k,qnc_pref_cell_j), &\n"
               "               fqy(qnc_pref_cell_i,qnc_pref_cell_k,qnc_pref_cell_j), &\n"
               "               fqy(qnc_pref_cell_i,qnc_pref_cell_k,qnc_pref_cell_j+1), &\n"
               "               fqz(qnc_pref_cell_i,qnc_pref_cell_k,qnc_pref_cell_j), &\n"
               "               fqz(qnc_pref_cell_i,qnc_pref_cell_k+1,qnc_pref_cell_j) /)\n"
               "           qnc_pref_pre_seen(qnc_pref_n)=.TRUE.\n"
               "         END IF\n"
               "       END DO\n"
               "     END IF\n"
               "   END IF\n   DO j=j_start, j_end")
    block = _replace(block, begin, capture)
    block = _replace(block,
        "IF (qnc_pref_seen(qnc_pref_n) .AND. &",
        "IF (qnc_pref_seen(qnc_pref_n) .AND. qnc_pref_pre_seen(qnc_pref_n) .AND. &")
    block = _replace(block,
        "fqz(qnc_pref_cell_i,qnc_pref_cell_k+1,qnc_pref_cell_j)/))",
        "fqz(qnc_pref_cell_i,qnc_pref_cell_k+1,qnc_pref_cell_j), &\n"
        "              qnc_pref_pre(:,qnc_pref_n)/))")
    if (block.count("qnc_pref_pre(:,qnc_pref_n)=") != 1 or
            block.count("CALL qnc_domain_preflight_emit(") != 1 or
            block.index("qnc_pref_pre(:,qnc_pref_n)=") > block.index("ph_low(i,k,j) =") or
            block.index("CALL qnc_domain_preflight_emit(") < block.index("qnc_pref_seen(qnc_pref_index)=.TRUE.")):
        raise ValueError("QNC pre-limit/post-limit recording order differs")
    text = text[:sub_start] + block + text[sub_end:]
    return text.encode("utf-8"), cells


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--advect-source", type=Path, required=True)
    parser.add_argument("--failure-json", type=Path, required=True)
    parser.add_argument("--advect-output", type=Path, required=True)
    args = parser.parse_args()
    sources = (args.advect_source, args.failure_json)
    output = args.advect_output
    if (output.exists() or output.is_symlink() or output.parent.is_symlink() or
            any(output.resolve() == source.resolve() for source in sources)):
        raise FileExistsError("candidate-face output must be new and distinct from inputs")
    generated, cells = render_advect(sources[0].read_bytes(), sources[1].read_bytes())
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(generated)
    print(json.dumps({"status": "QNC_CANDIDATE_FACES_SOURCE_WRITTEN",
                      "source_sha256": sha(generated), "captured_cells": len(cells)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
