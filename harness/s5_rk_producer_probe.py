#!/usr/bin/env python3
"""Add a small, opt-in RK producer witness to the pinned private solve_em.F."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re

from s5_g4_ww_probe_overlay import TILES


SOURCE_SHA = "d66e9db1bba8f37e3f46d30c2fd74bdf8def411adf233376a69e0b401c6d3d1f"
GUARD = "KDM6AD_S5_RK_PROBE"
STAGES = ("PREP_BEFORE", "PREP_AFTER", "UV_BEFORE", "UV_AFTER",
          "MU_TEND_BEFORE", "MU_TEND_AFTER", "SMALL_BEFORE", "SMALL_AFTER")
ANCHORS = {
    "PREP_BEFORE": ("       CALL small_step_prep( grid%u_1", False),
    "PREP_AFTER": ("\n \n       CALL calc_p_rho( grid%al", False),
    "UV_BEFORE": ("BENCH_START(advance_uv_tim)\n", False),
    "UV_AFTER": ("BENCH_END(advance_uv_tim)\n", True),
    "MU_TEND_BEFORE": ("BENCH_START(advance_mu_t_tim)\n", False),
    "MU_TEND_AFTER": ("BENCH_END(advance_mu_t_tim)\n", True),
    "SMALL_BEFORE": ("BENCH_START(small_step_finish_tim)\n", False),
    "SMALL_AFTER": ("!  call  to set ru_m, rv_m and ww_m b.c's for PD advection\n", True),
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def point(field: str, expr: str, i: int, j: int, k: int) -> str:
    return (f"               s5_bits = TRANSFER({expr},0)\n"
            "               WRITE(s5_unit,'(A,1X,A,1X,4(I0,1X))') &\n"
            f"                    'POINT','{field}',{i},{j},{k},s5_bits\n")


def block(stage: str) -> str:
    body = []
    for j, entries in (
        (119, ((116, "grid%mu_2(116,119)"), (117, "grid%mu_2(117,119)"))),
        (158, ((117, "grid%mu_2(117,157)"), (117, "grid%mu_2(117,158)"))),
        (193, ((117, "grid%mu_2(117,193)"), (118, "grid%mu_2(118,193)"))),
    ):
        body.append(f"            IF (117 >= s5_its .AND. 117 <= s5_itf .AND. &\n"
                    f"                {j} >= s5_jts .AND. {j} <= s5_jtf) THEN\n")
        for i, expr in entries:
            jj = 157 if "(117,157)" in expr else j
            body.append(point("MU2", expr, i, jj, 0))
        body.append("            ENDIF\n")
    body.append("            IF (117 >= s5_its .AND. 117 <= s5_itf .AND. &\n"
                "                2 >= s5_jts .AND. 2 <= s5_jtf) THEN\n")
    body.extend((point("U2", "grid%u_2(117,1,2)", 117, 2, 1),
                 point("U2", "grid%u_2(118,1,2)", 118, 2, 1),
                 point("V2", "grid%v_2(117,1,3)", 117, 3, 1)))
    body.append("            ENDIF\n")
    body.append("            IF (234 >= s5_its .AND. 234 <= s5_itf .AND. &\n"
                "                1 >= s5_jts .AND. 1 <= s5_jtf) THEN\n")
    body.append(point("V2", "grid%v_2(234,1,1)", 234, 1, 1))
    body.append("            ENDIF\n")
    return (f"#ifdef {GUARD}\n! S5_RK_BEGIN:{stage}\n"
            "      IF (rk_step == 1) THEN\n"
            "         BLOCK\n"
            "            INTEGER :: s5_unit, s5_status, s5_rank, s5_bits\n"
            "            INTEGER :: s5_its, s5_ite, s5_jts, s5_jte, s5_itf, s5_jtf\n"
            "            CHARACTER(LEN=512) :: s5_prefix, s5_path\n"
            "            CHARACTER(LEN=32) :: s5_rank_text\n"
            "            s5_prefix = ' '\n"
            "            CALL GET_ENVIRONMENT_VARIABLE('KDM6AD_S5_RK_PREFIX', &\n"
            "                                          s5_prefix, STATUS=s5_status)\n"
            "            IF (s5_status == 0 .AND. LEN_TRIM(s5_prefix) > 0) THEN\n"
            "               s5_its = grid%i_start(ij)\n"
            "               s5_ite = grid%i_end(ij)\n"
            "               s5_jts = grid%j_start(ij)\n"
            "               s5_jte = grid%j_end(ij)\n"
            "               s5_itf = MIN(s5_ite,ide-1)\n"
            "               s5_jtf = MIN(s5_jte,jde-1)\n"
            "               s5_rank_text = ' '\n"
            "               CALL GET_ENVIRONMENT_VARIABLE('OMPI_COMM_WORLD_RANK', &\n"
            "                                             s5_rank_text, STATUS=s5_status)\n"
            "               IF (s5_status /= 0) STOP 21\n"
            "               READ(s5_rank_text,*,IOSTAT=s5_status) s5_rank\n"
            "               IF (s5_status /= 0) STOP 22\n"
            f"               WRITE(s5_path,'(A,\".{stage}.r\",I0,\".i\",I0,\"-\",I0, &\n"
            "                    \".j\",I0,\"-\",I0,\".txt\")') &\n"
            "                    TRIM(s5_prefix),s5_rank,s5_its,s5_ite,s5_jts,s5_jte\n"
            "               OPEN(NEWUNIT=s5_unit,FILE=TRIM(s5_path), &\n"
            "                    STATUS='REPLACE',ACTION='WRITE',IOSTAT=s5_status)\n"
            "               IF (s5_status /= 0) STOP 23\n"
            f"               WRITE(s5_unit,'(A,1X,A,1X,5(I0,1X))') &\n"
            f"                    'STAGE','{stage}',s5_rank,s5_its,s5_ite,s5_jts,s5_jte\n"
            + "".join(body)
            + "               CLOSE(s5_unit)\n"
              "            ENDIF\n"
              "         END BLOCK\n"
              "      ENDIF\n"
              f"! S5_RK_END:{stage}\n#endif\n")


def render(source: str) -> str:
    result = source
    for stage in STAGES:
        anchor, after = ANCHORS[stage]
        if result.count(anchor) != 1:
            raise ValueError(f"{stage} source anchor occurs {result.count(anchor)} times")
        if stage == "PREP_AFTER":
            result = result.replace(anchor, anchor.replace(
                "       CALL calc_p_rho", block(stage) + "       CALL calc_p_rho"), 1)
        else:
            result = result.replace(anchor, anchor + block(stage) if after
                                    else block(stage) + anchor, 1)
    return result


def strip(overlay: str) -> str:
    pattern = re.compile(rf"(?ms)^#ifdef {GUARD}\n! S5_RK_BEGIN:([A-Z_]+)\n"
                         r".*?^! S5_RK_END:\1\n#endif\n")
    matches = list(pattern.finditer(overlay))
    if len(matches) != len(STAGES) or {m.group(1) for m in matches} != set(STAGES):
        raise ValueError("missing or duplicate RK probe block")
    original = pattern.sub("", overlay)
    if GUARD in original or "S5_RK_" in original:
        raise ValueError("orphan RK probe marker")
    return original


def expected_rows(layout: str) -> set[tuple]:
    """Expected (stage, rank, tile bounds, field, i, j, k) from the run plan."""
    rows = set()
    for stage in STAGES:
        for rank, its, ite, jts, jte in TILES[layout]:
            tile = (stage, rank, its, ite, jts, jte)
            if its <= 117 <= min(ite, 234):
                for j, points in ((119, ((116, 119), (117, 119))),
                                  (158, ((117, 157), (117, 158))),
                                  (193, ((117, 193), (118, 193)))):
                    if jts <= j <= min(jte, 282):
                        rows.update((*tile, "MU2", i, jj, 0) for i, jj in points)
                if jts <= 2 <= min(jte, 282):
                    rows.update(((*tile, "U2", 117, 2, 1),
                                 (*tile, "U2", 118, 2, 1),
                                 (*tile, "V2", 117, 3, 1)))
            if its <= 234 <= min(ite, 234) and jts <= 1 <= min(jte, 282):
                rows.add((*tile, "V2", 234, 1, 1))
    return rows


def parse_capture(layout: str, files: list[Path]) -> dict[tuple, int]:
    """Reject a missing, relocated or repeated stage/tile/point record."""
    expected_files = {(stage, *tile) for stage in STAGES for tile in TILES[layout]}
    pattern = re.compile(r"\.([A-Z_]+)\.r(\d+)\.i(-?\d+)-(-?\d+)"
                         r"\.j(-?\d+)-(-?\d+)\.txt$")
    seen, words = set(), {}
    for path in files:
        match = pattern.search(path.name)
        if match is None:
            raise ValueError(f"invalid RK capture filename: {path.name}")
        stage = match.group(1)
        rank, its, ite, jts, jte = map(int, match.groups()[1:])
        tile = (stage, rank, its, ite, jts, jte)
        if tile not in expected_files or tile in seen:
            raise ValueError(f"unexpected or duplicate RK stage/tile: {tile}")
        seen.add(tile)
        lines = path.read_text(encoding="ascii").splitlines()
        if not lines or lines[0].split() != ["STAGE", stage, str(rank),
                                               str(its), str(ite), str(jts), str(jte)]:
            raise ValueError(f"invalid RK capture header: {path.name}")
        for line in lines[1:]:
            fields = line.split()
            if len(fields) != 6 or fields[0] != "POINT":
                raise ValueError(f"invalid RK point: {path.name}")
            name = fields[1]
            i, j, k, bits = map(int, fields[2:])
            if not -(2**31) <= bits < 2**31:
                raise ValueError(f"invalid RK raw word: {path.name}")
            key = (*tile, name, i, j, k)
            if key in words:
                raise ValueError(f"duplicate RK point: {key}")
            words[key] = bits
    if seen != expected_files or set(words) != expected_rows(layout):
        raise ValueError("RK stage/tile/point set differs from the declared schedule")
    return words


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source", type=Path)
    ap.add_argument("output", type=Path)
    args = ap.parse_args()
    raw = args.source.read_bytes()
    if sha(raw) != SOURCE_SHA:
        raise ValueError("private solve_em.F differs from the pinned S5 source")
    overlay = render(raw.decode("ascii"))
    if strip(overlay).encode("ascii") != raw:
        raise ValueError("macro-off overlay differs from the pinned source")
    args.output.write_text(overlay, encoding="ascii")
    print(f"source_sha256={sha(raw)}")
    print(f"overlay_sha256={sha(overlay.encode('ascii'))}")


if __name__ == "__main__":
    main()
