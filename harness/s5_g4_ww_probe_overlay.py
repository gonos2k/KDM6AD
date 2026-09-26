#!/usr/bin/env python3
"""Generate a source-pinned, opt-in calc_ww_cp diagnostic overlay.

The generated Fortran is intended for a later isolated capture build.  This
module does not compile, link, or run the host.  With
``KDM6AD_S5_WW_CAPTURE`` undefined, removing the marked blocks must reproduce
the pinned source byte-for-byte.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re


SOURCE_SHA256 = "27ce690b27b24c80247a5551b48d37fc32fc47470d806cbef1bb859d58edc31c"
GUARD = "KDM6AD_S5_WW_CAPTURE"
TARGET_I = (117, 234)
CAPTURE_CALLS = (1, 2, 3)  # invocation ordinal within each exact tile bound
EXPECTED_GLOBAL_BOUNDS = (1, 235, 1, 283, 1, 40)
EXPECTED_MEMORY_BOUNDS = {
    ("1x1", 0): (-4, 240, -4, 288, 1, 40),
    ("2x1", 0): (-4, 124, -4, 288, 1, 40),
    ("2x1", 1): (111, 240, -4, 288, 1, 40),
}

# These are the exact G4 tile extents from the accepted exact2 trace.  The
# expected schedule is independent of records/files that a future run emits.
TILES = {
    "1x1": (
        (0, 1, 235, 1, 142),
        (0, 1, 235, 143, 283),
    ),
    "2x1": (
        (0, 1, 117, 1, 142),
        (0, 1, 117, 143, 283),
        (1, 118, 235, 1, 142),
        (1, 118, 235, 143, 283),
    ),
}

DECL_ANCHOR = (
    "   REAL , DIMENSION( its:ite, kts:kte ) :: divv\n"
    "   REAL , DIMENSION( its:ite+1, jts:jte+1 ) :: muu, muv\n"
)
BOUNDS_ANCHOR = (
    "    jtf=MIN(jte,jde-1)\n"
    "    ktf=MIN(kte,kde-1)  \n"
    "    itf=MIN(ite,ide-1)\n"
)
MU_ARRAYS_ANCHOR = (
    "      DO j=jts,min(jte+1,jde)\n"
    "      DO i=its,itf\n"
    "        MUV(i,j) = 0.5*(MUP(i,j)+MUB(i,j)+MUP(i,j-1)+MUB(i,j-1))\n"
    "      ENDDO\n"
    "      ENDDO\n"
    "\n"
)
DIVV_ANCHOR = (
    "        ENDDO\n"
    "        ENDDO\n"
    "\n"
    "!       Further map scale factor notes:\n"
)
WW_ANCHOR = (
    "           ww(i,k,j)=ww(i,k-1,j) - dnw(k-1)*c1h(k-1)*dmdt(i) - divv(i,k-1)\n"
    "\n"
    "        ENDDO\n"
    "        ENDDO\n"
)
CLOSE_ANCHOR = (
    "        ENDDO\n"
    "        ENDDO\n"
    "     ENDDO\n"
    "\n"
    "\n"
)


DECL_BLOCK = f"""#ifdef {GUARD}
! S5_WW_PROBE_BEGIN:DECL
   INTEGER, SAVE :: s5_tile_count = 0
   INTEGER, SAVE :: s5_tile_bounds(4,4) = 0
   INTEGER, SAVE :: s5_tile_calls(4) = 0
   INTEGER :: s5_enabled, s5_status, s5_unit, s5_rank, s5_slot
   INTEGER :: s5_t, s5_target, s5_i, s5_j, s5_k, s5_bits
   INTEGER :: s5_real_bits, s5_integer_bits
   CHARACTER(LEN=512) :: s5_prefix, s5_file
   CHARACTER(LEN=32) :: s5_rank_text
! S5_WW_PROBE_END:DECL
#endif
"""

CALL_BLOCK = f"""#ifdef {GUARD}
! S5_WW_PROBE_BEGIN:CALL
      s5_enabled = 0
      s5_prefix = ' '
      CALL GET_ENVIRONMENT_VARIABLE('KDM6AD_S5_WW_CAPTURE_PREFIX', &
                                    s5_prefix, STATUS=s5_status)
      IF (s5_status == 0 .AND. LEN_TRIM(s5_prefix) > 0) THEN
         s5_slot = 0
         DO s5_t = 1, s5_tile_count
            IF (s5_tile_bounds(1,s5_t) == its .AND. &
                s5_tile_bounds(2,s5_t) == ite .AND. &
                s5_tile_bounds(3,s5_t) == jts .AND. &
                s5_tile_bounds(4,s5_t) == jte) s5_slot = s5_t
         ENDDO
         IF (s5_slot == 0 .AND. s5_tile_count < 4) THEN
            s5_tile_count = s5_tile_count + 1
            s5_slot = s5_tile_count
            s5_tile_bounds(:,s5_slot) = (/ its, ite, jts, jte /)
         ENDIF
         IF (s5_slot == 0) THEN
            WRITE(*,*) 'S5_CAPTURE_TILE_OVERFLOW', its, ite, jts, jte
            STOP 17
         ENDIF
         IF (s5_slot > 0) THEN
            s5_tile_calls(s5_slot) = s5_tile_calls(s5_slot) + 1
            IF (s5_tile_calls(s5_slot) <= 3) THEN
               s5_rank = -1
               s5_rank_text = ' '
               CALL GET_ENVIRONMENT_VARIABLE('OMPI_COMM_WORLD_RANK', &
                                             s5_rank_text, STATUS=s5_status)
               IF (s5_status == 0) READ(s5_rank_text,*,IOSTAT=s5_status) s5_rank
               IF (s5_status /= 0) THEN
                  s5_rank_text = ' '
                  CALL GET_ENVIRONMENT_VARIABLE('PMI_RANK', s5_rank_text, &
                                                STATUS=s5_status)
                  IF (s5_status == 0) READ(s5_rank_text,*,IOSTAT=s5_status) s5_rank
               ENDIF
               s5_file = ' '
               WRITE(s5_file,'(A,".r",I0,".c",I0,".i",I0,"-",I0,".j",I0,"-",I0,".txt")') &
                    TRIM(s5_prefix), s5_rank, s5_tile_calls(s5_slot), &
                    its, ite, jts, jte
               OPEN(NEWUNIT=s5_unit, FILE=TRIM(s5_file), STATUS='REPLACE', &
                    ACTION='WRITE', FORM='FORMATTED', IOSTAT=s5_status)
               IF (s5_status == 0) THEN
                  s5_enabled = 1
                  s5_real_bits = STORAGE_SIZE(0.0)
                  s5_integer_bits = STORAGE_SIZE(0)
                  WRITE(s5_unit,'(A,1X,25(I0,1X))') 'CALL', &
                       s5_tile_calls(s5_slot), s5_rank, ids, ide, jds, jde, &
                       kds, kde, ims, ime, jms, jme, kms, kme, &
                       its, ite, jts, jte, kts, kte, itf, jtf, ktf, &
                       s5_real_bits, s5_integer_bits
               ENDIF
            ENDIF
         ENDIF
      ENDIF
! S5_WW_PROBE_END:CALL
#endif
"""

MU_ARRAYS_BLOCK = f"""#ifdef {GUARD}
! S5_WW_PROBE_BEGIN:MU_ARRAYS
      IF (s5_enabled == 1) THEN
         DO s5_target = 1, 2
            s5_i = 117
            IF (s5_target == 2) s5_i = 234
            IF (s5_i >= its .AND. s5_i <= itf .AND. &
                s5_i+1 <= MIN(ite+1,ide)) THEN
               DO s5_j = MAX(jts,1), MIN(jtf,282)
                  DO s5_k = s5_i, s5_i+1
                     s5_bits = TRANSFER(muu(s5_k,s5_j),0)
                     WRITE(s5_unit,'(A,1X,A,1X,6(I0,1X))') &
                          'SAMPLE','MUU',s5_tile_calls(s5_slot), &
                          s5_i,s5_k,s5_j,0,s5_bits
                  ENDDO
               ENDDO
               DO s5_j = MAX(jts,1), MIN(jtf+1,jde)
                  s5_bits = TRANSFER(muv(s5_i,s5_j),0)
                  WRITE(s5_unit,'(A,1X,A,1X,6(I0,1X))') &
                       'SAMPLE','MUV',s5_tile_calls(s5_slot), &
                       s5_i,s5_i,s5_j,0,s5_bits
               ENDDO
            ENDIF
         ENDDO
      ENDIF
! S5_WW_PROBE_END:MU_ARRAYS
#endif
"""

DIVV_BLOCK = f"""#ifdef {GUARD}
! S5_WW_PROBE_BEGIN:DIVV
        IF (s5_enabled == 1 .AND. j >= 1 .AND. j <= 282) THEN
           DO s5_target = 1, 2
              s5_i = 117
              IF (s5_target == 2) s5_i = 234
              IF (s5_i >= its .AND. s5_i <= itf) THEN
                 DO s5_k = kts, ktf
                    s5_bits = TRANSFER(divv(s5_i,s5_k),0)
                    WRITE(s5_unit,'(A,1X,A,1X,6(I0,1X))') &
                         'SAMPLE','DIVV',s5_tile_calls(s5_slot), &
                         s5_i,s5_i,j,s5_k,s5_bits
                 ENDDO
                 s5_bits = TRANSFER(dmdt(s5_i),0)
                 WRITE(s5_unit,'(A,1X,A,1X,6(I0,1X))') &
                      'SAMPLE','DMDT',s5_tile_calls(s5_slot), &
                      s5_i,s5_i,j,0,s5_bits
              ENDIF
           ENDDO
        ENDIF
! S5_WW_PROBE_END:DIVV
#endif
"""

WW_BLOCK = f"""#ifdef {GUARD}
! S5_WW_PROBE_BEGIN:WW
        IF (s5_enabled == 1 .AND. j >= 1 .AND. j <= 282) THEN
           DO s5_target = 1, 2
              s5_i = 117
              IF (s5_target == 2) s5_i = 234
              IF (s5_i >= its .AND. s5_i <= itf) THEN
                 DO s5_k = kts, kte
                    s5_bits = TRANSFER(ww(s5_i,s5_k,j),0)
                    WRITE(s5_unit,'(A,1X,A,1X,6(I0,1X))') &
                         'SAMPLE','WW',s5_tile_calls(s5_slot), &
                         s5_i,s5_i,j,s5_k,s5_bits
                 ENDDO
              ENDIF
           ENDDO
        ENDIF
! S5_WW_PROBE_END:WW
#endif
"""

CLOSE_BLOCK = f"""#ifdef {GUARD}
! S5_WW_PROBE_BEGIN:CLOSE
      IF (s5_enabled == 1) CLOSE(s5_unit)
! S5_WW_PROBE_END:CLOSE
#endif
"""

BLOCKS = {
    "DECL": DECL_BLOCK,
    "CALL": CALL_BLOCK,
    "MU_ARRAYS": MU_ARRAYS_BLOCK,
    "DIVV": DIVV_BLOCK,
    "WW": WW_BLOCK,
    "CLOSE": CLOSE_BLOCK,
}


def _insert_once(text: str, anchor: str, block: str, name: str) -> str:
    count = text.count(anchor)
    if count != 1:
        raise ValueError(f"source anchor {name} occurs {count} times; expected once")
    return text.replace(anchor, anchor + block, 1)


def render_overlay_text(source_text: str) -> str:
    """Insert only CPP-guarded probes at uniquely checked source anchors."""
    routine_pattern = re.compile(
        r"(?im)^SUBROUTINE calc_ww_cp\s*\(.*?^END SUBROUTINE calc_ww_cp\s*$",
        re.DOTALL,
    )
    routines = list(routine_pattern.finditer(source_text))
    if len(routines) != 1:
        raise ValueError(f"calc_ww_cp source routine occurs {len(routines)} times; expected once")
    start, end = routines[0].span()
    routine = source_text[start:end]
    text = _insert_once(routine, DECL_ANCHOR, DECL_BLOCK, "local declarations")
    text = _insert_once(text, BOUNDS_ANCHOR, CALL_BLOCK, "computed call bounds")
    text = _insert_once(text, MU_ARRAYS_ANCHOR, MU_ARRAYS_BLOCK,
                        "local muu/muv completion")
    text = _insert_once(text, DIVV_ANCHOR, DIVV_BLOCK,
                        "post vertical divv/dmdt sum")
    text = _insert_once(text, CLOSE_ANCHOR, CLOSE_BLOCK,
                        "routine close after vertical loops")
    text = _insert_once(text, WW_ANCHOR, WW_BLOCK, "post ww recurrence")
    return source_text[:start] + text + source_text[end:]


_GUARDED_BLOCK = re.compile(
    rf"(?m)^#ifdef {GUARD}\n"
    r"! S5_WW_PROBE_BEGIN:([A-Z_]+)\n"
    r".*?"
    r"^! S5_WW_PROBE_END:\1\n"
    r"#endif\n",
    re.DOTALL,
)


def strip_guarded_blocks(overlay_text: str) -> str:
    """Remove generated probe blocks; refuse partial, duplicate, or unknown blocks."""
    matches = list(_GUARDED_BLOCK.finditer(overlay_text))
    if len(matches) != len(BLOCKS):
        raise ValueError(f"found {len(matches)} complete guarded blocks; expected {len(BLOCKS)}")
    names = [match.group(1) for match in matches]
    if set(names) != set(BLOCKS) or len(set(names)) != len(BLOCKS):
        raise ValueError("guarded block names are missing, duplicated, or unexpected")
    stripped = _GUARDED_BLOCK.sub("", overlay_text)
    if GUARD in stripped or "S5_WW_PROBE_" in stripped:
        raise ValueError("unpaired S5 guard marker remains after stripping")
    return stripped


def generate(source_path: Path, output_path: Path) -> dict[str, str]:
    raw = source_path.read_bytes()
    source_sha = hashlib.sha256(raw).hexdigest()
    if source_sha != SOURCE_SHA256:
        raise ValueError(f"refuse source SHA-256 {source_sha}; expected {SOURCE_SHA256}")
    text = raw.decode("ascii")
    overlay = render_overlay_text(text)
    if strip_guarded_blocks(overlay).encode("ascii") != raw:
        raise ValueError("macro-off strip does not reproduce pinned source bytes")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(overlay.encode("ascii"))
    return {
        "source_sha256": source_sha,
        "overlay_sha256": hashlib.sha256(overlay.encode("ascii")).hexdigest(),
        "macro_off_stripped_sha256": hashlib.sha256(
            strip_guarded_blocks(overlay).encode("ascii")
        ).hexdigest(),
        "guard": GUARD,
        "target_i": ",".join(map(str, TARGET_I)),
        "captured_invocations_per_tile": ",".join(map(str, CAPTURE_CALLS)),
    }


def tile_schedule(layout: str) -> tuple[tuple[int, int, int, int, int], ...]:
    try:
        return TILES[layout]
    except KeyError as exc:
        raise ValueError(f"unsupported declared layout: {layout}") from exc


def expected_headers(layout: str) -> set[tuple[int, int, int, int, int, int]]:
    """Expected (call, rank, its, ite, jts, jte), independent of captures."""
    return {
        (call, rank, its, ite, jts, jte)
        for call in CAPTURE_CALLS
        for rank, its, ite, jts, jte in tile_schedule(layout)
    }


def expected_sample_keys(
    layout: str,
) -> set[tuple[int, int, int, int, int, str, int, int, int, int]]:
    """Expected (call,tile...,field,target_i,array_i,array_j,array_k) keys."""
    keys: set[tuple[int, int, int, int, int, str, int, int, int, int]] = set()
    for call, rank, its, ite, jts, jte in expected_headers(layout):
        itf = min(ite, EXPECTED_GLOBAL_BOUNDS[1] - 1)
        jtf = min(jte, 282)
        selected_i = [i for i in TARGET_I if its <= i <= itf]
        output_js = range(max(1, jts), max(1, jtf) + 1) if jtf >= max(1, jts) else ()
        for i in selected_i:
            for j in output_js:
                keys.add((call, rank, its, ite, jts, jte, "MUU", i, i, j, 0))
                keys.add((call, rank, its, ite, jts, jte, "MUU", i, i + 1, j, 0))
                keys.add((call, rank, its, ite, jts, jte, "MUV", i, i, j, 0))
                keys.add((call, rank, its, ite, jts, jte, "MUV", i, i, j + 1, 0))
                keys.add((call, rank, its, ite, jts, jte, "DMDT", i, i, j, 0))
                for k in range(1, 40):
                    keys.add((call, rank, its, ite, jts, jte, "DIVV", i, i, j, k))
                for k in range(1, 41):
                    keys.add((call, rank, its, ite, jts, jte, "WW", i, i, j, k))
    return keys


def validate_declared_capture(
    layout: str,
    headers: list[tuple[int, int, int, int, int, int]],
    samples: list[tuple[int, int, int, int, int, int, str, int, int, int, int]],
) -> None:
    """Fail closed on missing/duplicate/relocated headers or selected samples."""
    expected_h = expected_headers(layout)
    if len(headers) != len(set(headers)) or set(headers) != expected_h:
        raise ValueError("capture header set differs from declared tile/call schedule")
    expected_s = expected_sample_keys(layout)
    if len(samples) != len(set(samples)) or set(samples) != expected_s:
        raise ValueError("capture samples differ from declared selected-cell schedule")


def parse_capture_files(layout: str, paths: list[Path]) -> tuple[
    dict[str, object],
    dict[tuple[int, int, int, int, int, int, str, int, int, int, int], int],
]:
    """Read formatted overlay captures and enforce the code-fixed schedule."""
    headers: list[tuple[int, int, int, int, int, int]] = []
    validated_tile_calls: list[dict[str, object]] = []
    sample_words: dict[
        tuple[int, int, int, int, int, int, str, int, int, int, int], int
    ] = {}
    expected_tiles = set(tile_schedule(layout))
    seen_files: set[tuple[int, int, int, int, int]] = set()
    allowed_fields = {"MUU", "MUV", "DIVV", "DMDT", "WW"}
    for path in paths:
        rows = path.read_text(encoding="ascii").splitlines()
        if not rows:
            raise ValueError(f"empty capture file: {path.name}")
        first = rows[0].split()
        if len(first) != 26 or first[0] != "CALL":
            raise ValueError(f"malformed CALL header in {path.name}")
        values = [int(token) for token in first[1:]]
        (call, rank, ids, ide, jds, jde, kds, kde, ims, ime, jms, jme,
         kms, kme, its, ite, jts, jte, kts, kte, itf, jtf, ktf,
         real_bits, integer_bits) = values
        tile = (rank, its, ite, jts, jte)
        if tile not in expected_tiles:
            raise ValueError(f"unexpected tile metadata in {path.name}: {tile}")
        if call not in CAPTURE_CALLS:
            raise ValueError(f"unexpected invocation ordinal in {path.name}: {call}")
        file_key = (call, *tile)
        if file_key in seen_files:
            raise ValueError(f"duplicate tile/call capture: {file_key}")
        seen_files.add(file_key)
        global_bounds = (ids, ide, jds, jde, kds, kde)
        if global_bounds != EXPECTED_GLOBAL_BOUNDS:
            raise ValueError(f"global bounds differ from the pinned LC05/G4 contract: {path.name}")
        if (itf != min(ite, ide - 1) or jtf != min(jte, jde - 1)
                or ktf != min(kte, kde - 1)
                or itf != min(ite, EXPECTED_GLOBAL_BOUNDS[1] - 1)
                or jtf != min(jte, EXPECTED_GLOBAL_BOUNDS[3] - 1)
                or ktf != 39):
            raise ValueError(f"derived loop bounds disagree in {path.name}")
        memory_bounds = (ims, ime, jms, jme, kms, kme)
        expected_memory = EXPECTED_MEMORY_BOUNDS[(layout, rank)]
        if memory_bounds != expected_memory:
            raise ValueError(f"rank memory bounds differ from the pinned G4 contract: {path.name}")
        if real_bits != 32 or integer_bits != 32:
            raise ValueError(f"raw-word capture requires default REAL/INTEGER(4): {path.name}")
        headers.append((call, rank, its, ite, jts, jte))
        validated_tile_calls.append({
            "call": call,
            "rank": rank,
            "tile_i": [its, ite],
            "tile_j": [jts, jte],
            "global_bounds": {
                "i": [ids, ide], "j": [jds, jde], "k": [kds, kde],
            },
            "memory_bounds": {
                "i": [ims, ime], "j": [jms, jme], "k": [kms, kme],
            },
            "derived_loop_bounds": {"itf": itf, "jtf": jtf, "ktf": ktf},
        })
        for row in rows[1:]:
            fields = row.split()
            if len(fields) != 8 or fields[0] != "SAMPLE":
                raise ValueError(f"malformed SAMPLE record in {path.name}")
            name = fields[1]
            if name not in allowed_fields:
                raise ValueError(f"unexpected sample field {name!r} in {path.name}")
            sample_call, target_i, i, j, k, bits = map(int, fields[2:])
            if (sample_call != call or target_i not in TARGET_I
                    or not -(2**31) <= bits < 2**31):
                raise ValueError(f"sample call/raw-word mismatch in {path.name}")
            key = (call, rank, its, ite, jts, jte, name, target_i, i, j, k)
            if key in sample_words:
                raise ValueError(f"duplicate selected sample in {path.name}: {key}")
            sample_words[key] = bits
    validate_declared_capture(layout, headers, list(sample_words))
    receipt: dict[str, object] = {
        "schema": 1,
        "layout": layout,
        "global_bounds": {
            "i": list(EXPECTED_GLOBAL_BOUNDS[0:2]),
            "j": list(EXPECTED_GLOBAL_BOUNDS[2:4]),
            "k": list(EXPECTED_GLOBAL_BOUNDS[4:6]),
        },
        "rank_memory_bounds": {
            str(rank): {
                "i": list(bounds[0:2]),
                "j": list(bounds[2:4]),
                "k": list(bounds[4:6]),
            }
            for (declared_layout, rank), bounds in EXPECTED_MEMORY_BOUNDS.items()
            if declared_layout == layout
        },
        "tile_calls": validated_tile_calls,
        "selected_sample_count": len(sample_words),
    }
    return receipt, sample_words


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="pinned private source path")
    parser.add_argument("output", type=Path, help="shadow overlay output path")
    args = parser.parse_args()
    try:
        receipt = generate(args.source, args.output)
    except (OSError, UnicodeError, ValueError) as exc:
        parser.error(str(exc))
    for key, value in receipt.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
