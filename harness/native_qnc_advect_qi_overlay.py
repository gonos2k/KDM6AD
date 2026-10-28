"""Render opt-in QNC producer and QI writer traces for an isolated host build.

Both inputs are pinned private sources from the executed PR #468 variant. The
PR #465 one-ULP donor-scale operation remains at its original `(221,63,6)`
location; this overlay changes recording only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ADVECT_BASE_SHA256 = "5bf9c6308e129bf24b01ee25c8efeed7c7fe43283213fd968abcb45b6dba5544"
SOLVE_BASE_SHA256 = "ecb01b868cbffa664eb54d951014fc04f25ecd910b093180a5be1e2693de7b10"
QNC_TARGET_IKJ = (113, 12, 70)
QI_TARGET_IKJ = (1, 33, 168)
QC_TARGET_IKJ = (155, 15, 120)
ADVECT_TRACE_ENV = "KDM6AD_QNC_PRODUCER_TRACE_DIR"
MOMENT_TRACE_ENV = "KDM6AD_QI_WRITER_TRACE_DIR"


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _replace(text: str, old: str, new: str, count: int = 1) -> str:
    if text.count(old) != count:
        raise ValueError(f"private trace source anchor differs: {old[:88]!r}")
    return text.replace(old, new)


def render_advect(raw: bytes) -> bytes:
    if sha(raw) != ADVECT_BASE_SHA256:
        raise ValueError("PR #465 private advect source SHA differs")
    text = raw.decode("utf-8")
    physical_backoff = (
        "i.EQ.221 .AND. k.EQ.6 .AND. j.EQ.63 .AND. &\n"
        "           scale.GT.0. .AND. scale.LT.1.) scale=NEAREST(scale,-1.)"
    )
    if text.count(physical_backoff) != 1:
        raise ValueError("PR #465 physical donor-scale branch differs")
    replacements = (
        (".AND. (rk .EQ. 1 .OR. rk .EQ. 3)", ".AND. (rk .EQ. 2 .OR. rk .EQ. 3)", 1),
        ("KDM6AD_QNC_FLUX_TRACE_DIR", ADVECT_TRACE_ENV, 1),
        ("'/qnc_flux.tsv'", "'/qnc_producer.tsv'", 1),
        ("# KDM6AD_QNC_FLUX_TRACE_V2", "# KDM6AD_QNC_PRODUCER_TRACE_V1", 1),
        ("i.NE.221 .OR. k.NE.6 .OR. j.NE.63", "i.NE.113 .OR. k.NE.12 .OR. j.NE.70", 2),
        ("ABS(i-221)+ABS(k-6)+ABS(j-63)", "ABS(i-113)+ABS(k-12)+ABS(j-70)", 2),
        ("INTEGER,PARAMETER :: i=221,k=6,j=63", "INTEGER,PARAMETER :: i=113,k=12,j=70", 1),
        ("qnc_trace_rk.NE.1", "qnc_trace_rk.NE.2", 1),
        ("qnc_trace_rk.EQ.1", "qnc_trace_rk.EQ.2", 1),
        # The inherited helper name remains part of the module interface.
        # Its emitted stage labels below identify the actual RK2 call.
        ("RK1_START", "RK2_START", 1),
        ("RK1_AFTER_Y", "RK2_AFTER_Y", 2),
        ("RK1_AFTER_X", "RK2_AFTER_X", 2),
        ("RK1_AFTER_Z", "RK2_AFTER_Z", 2),
        ("221.GE.its", "113.GE.its", 3),
        ("221.LE.ite", "113.LE.ite", 3),
        ("63.GE.jts", "70.GE.jts", 3),
        ("63.LE.jte", "70.LE.jte", 3),
        ("6.GE.kts", "12.GE.kts", 3),
        ("6.LT.kte", "12.LT.kte", 3),
        ("221,6,63,tendency(221,6,63)", "113,12,70,tendency(113,12,70)", 1),
        ("221,6,63,'TENDENCY',tendency(221,6,63)",
         "113,12,70,'TENDENCY',tendency(113,12,70)", 1),
        ("msftx(221,63),msfty(221,63),rdx,rdy,rdzw(6)",
         "msftx(113,70),msfty(113,70),rdx,rdy,rdzw(12)", 2),
    )
    for old, new, count in replacements:
        text = _replace(text, old, new, count)
    if text.count(physical_backoff) != 1:
        raise ValueError("trace overlay changed the physical donor-scale branch")
    return text.encode("utf-8")


def render_solve(raw: bytes) -> bytes:
    if sha(raw) != SOLVE_BASE_SHA256:
        raise ValueError("PR #468 private solve source SHA differs")
    text = raw.decode("utf-8")
    text = _replace(text, "KDM6AD_QNC_REPRESENTATIVE_TRACE_DIR", MOMENT_TRACE_ENV)
    text = _replace(text, "/representative_moments.tsv", "/qi_writer_moments.tsv")
    text = _replace(text, "# KDM6AD_REPRESENTATIVE_MOMENTS_V1",
                    "# KDM6AD_QI_WRITER_MOMENTS_V1")
    coordinate_anchor = (
        "      i = KDM6AD_UPNC_I(target); k = KDM6AD_UPNC_K(target); j = KDM6AD_UPNC_J(target)\n"
        "      IF (i .LT. its .OR. i .GT. ite .OR. j .LT. jts .OR. j .GT. jte) CYCLE"
    )
    coordinate_new = (
        "      i = KDM6AD_UPNC_I(target); k = KDM6AD_UPNC_K(target); j = KDM6AD_UPNC_J(target)\n"
        "      IF (stage(1:3) .EQ. 'QI_' .AND. target .NE. 4) CYCLE\n"
        "      IF (stage(1:3) .EQ. 'QC_' .AND. target .NE. 3) CYCLE\n"
        "      IF (i .LT. its .OR. i .GT. ite .OR. j .LT. jts .OR. j .GT. jte) CYCLE"
    )
    text = _replace(text, coordinate_anchor, coordinate_new)
    extra = """      IF (mode .EQ. 3) THEN
        CALL kdm6ad_upnc_write_real(step, rk_step, stage, i, k, j, 'MOIST_OLD', moist_old(i,k,j,P_QI))
        CALL kdm6ad_upnc_write_real(step, rk_step, stage, i, k, j, 'MOIST_TEND', moist_tend(i,k,j,P_QI))
        CALL kdm6ad_upnc_write_real(step, rk_step, stage, i, k, j, 'ADVECT_TEND', advect_tend(i,k,j))
        CALL kdm6ad_upnc_write_real(step, rk_step, stage, i, k, j, 'H_TENDENCY', h_tendency(i,k,j))
        CALL kdm6ad_upnc_write_real(step, rk_step, stage, i, k, j, 'Z_TENDENCY', z_tendency(i,k,j))
        CALL kdm6ad_upnc_write_real(step, rk_step, stage, i, k, j, 'MU_OLD', grid%mu_1(i,j))
        CALL kdm6ad_upnc_write_real(step, rk_step, stage, i, k, j, 'MU_NEW', grid%mu_2(i,j))
        CALL kdm6ad_upnc_write_real(step, rk_step, stage, i, k, j, 'MU_BASE', grid%mub(i,j))
        CALL kdm6ad_upnc_write_real(step, rk_step, stage, i, k, j, 'C1H', grid%c1h(k))
        CALL kdm6ad_upnc_write_real(step, rk_step, stage, i, k, j, 'C2H', grid%c2h(k))
        CALL kdm6ad_upnc_write_real(step, rk_step, stage, i, k, j, 'MSFTY', grid%msfty(i,j))
        CALL kdm6ad_upnc_write_real(step, rk_step, stage, i, k, j, 'DT_RK', dt_value)
        word=INT(MERGE(1,0,config_flags%specified),C_INT32_T)
        CALL kdm6ad_upnc_write_word(step,rk_step,stage,i,k,j,'SPECIFIED','bool',word)
        word=INT(MERGE(1,0,config_flags%have_bcs_moist),C_INT32_T)
        CALL kdm6ad_upnc_write_word(step,rk_step,stage,i,k,j,'HAVE_BCS_MOIST','bool',word)
        CYCLE
      END IF
"""
    text = _replace(text, "      IF (mode .EQ. 0) CYCLE", extra + "      IF (mode .EQ. 0) CYCLE")

    def calls(suffix: str) -> str:
        lines = []
        for species, predicate, mode in (("QI", "im .EQ. P_QI .AND. rk_step .EQ. rk_order", 3),
                                         ("QC", "im .EQ. P_QC .AND. rk_step .EQ. 1", 0)):
            lines.extend((
                f"               IF ({predicate}) THEN",
                f"                 CALL kdm6ad_upnc_trace('{species}_{suffix}', grid%itimestep, rk_step, &",
                f"                      dt_rk, {mode}, grid%i_start(ij), grid%i_end(ij), &",
                "                      grid%j_start(ij), grid%j_end(ij), k_start, k_end)",
                "               END IF",
            ))
        return "\n".join(lines)

    start = text.index("moist_variable_loop: DO im = PARAM_FIRST_SCALAR")
    end = text.index("ENDDO moist_variable_loop", start)
    block = text[start:end]
    anchors = (
        ("tenddec = .false.\n\n\n               CALL rk_scalar_tend",
         "tenddec = .false.\n" + calls("TEND_BEFORE") + "\n\n               CALL rk_scalar_tend"),
        ("k_start    , k_end               )\n\n               IF( rk_step == 1",
         "k_start    , k_end               )\n" + calls("TEND_AFTER") + "\n\n               IF( rk_step == 1"),
        ("tenddec = .false.\n\n\n               CALL rk_update_scalar",
         "tenddec = .false.\n" + calls("RK_BEFORE") + "\n\n               CALL rk_update_scalar"),
        ("kts=k_start    , kte=k_end                              )\n               IF( rk_step == rk_order",
         "kts=k_start    , kte=k_end                              )\n" + calls("RK_AFTER") +
         "\n               IF( rk_step == rk_order"),
        ("               ENDIF\n\n\n             ENDDO moist_tile_loop_2",
         "               ENDIF\n" + calls("BDY_AFTER") + "\n\n             ENDDO moist_tile_loop_2"),
    )
    for old, new in anchors:
        block = _replace(block, old, new)
    text = text[:start] + block + text[end:]
    for stage in ("QI_TEND_BEFORE", "QI_TEND_AFTER", "QI_RK_BEFORE", "QI_RK_AFTER",
                  "QI_BDY_AFTER", "QC_TEND_BEFORE", "QC_TEND_AFTER", "QC_RK_BEFORE",
                  "QC_RK_AFTER", "QC_BDY_AFTER"):
        if text.count(f"CALL kdm6ad_upnc_trace('{stage}'") != 1:
            raise ValueError(f"missing or repeated {stage} writer-stage insertion")
    return text.encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--advect-source", type=Path, required=True)
    parser.add_argument("--solve-source", type=Path, required=True)
    parser.add_argument("--advect-output", type=Path, required=True)
    parser.add_argument("--solve-output", type=Path, required=True)
    args = parser.parse_args()
    inputs = (args.advect_source, args.solve_source)
    outputs = (args.advect_output, args.solve_output)
    if (any(path.exists() or path.is_symlink() for path in outputs) or
            any(output.resolve() == source.resolve() for output in outputs for source in inputs) or
            outputs[0].resolve() == outputs[1].resolve()):
        raise FileExistsError("trace outputs must be new and distinct from input sources")
    generated = (render_advect(inputs[0].read_bytes()), render_solve(inputs[1].read_bytes()))
    for path, raw in zip(outputs, generated):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(raw)
    print(json.dumps({"status": "ADVECT_QI_TRACE_SOURCES_WRITTEN",
                      "advect_sha256": sha(generated[0]), "solve_sha256": sha(generated[1]),
                      "qnc_target_ikj": QNC_TARGET_IKJ,
                      "qi_target_ikj": QI_TARGET_IKJ,
                      "qc_target_ikj": QC_TARGET_IKJ}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
