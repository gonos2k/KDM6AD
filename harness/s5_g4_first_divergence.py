#!/usr/bin/env python3
"""S5 overlay/replay adapter for the retained normalized-mp237 G4 MPI case.

The existing G33 stage probe remains the emitter and raw-word reader. This
adapter adds the full call-argument set of ``calc_ww_cp`` at the existing RK
entry checkpoint, plus its vertical coefficient vectors and scalar metrics.
It intentionally does not edit the canonical private host source.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys

PIN_SOLVE_EM = "d66e9db1bba8f37e3f46d30c2fd74bdf8def411adf233376a69e0b401c6d3d1f"
PIN_G4_CONS = "d362bc846b30119cc0b4f14f2e5088f9ab7c3e40205dde641aba83fb5a75e5d2"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import g33_dyn_probe as dyn  # noqa: E402


def configure_s5() -> None:
    """Capture full RK-entry memory values for the calc_ww_cp stencil."""
    if 5 not in dyn.GROUPS:
        dyn.GROUPS[5] = [
            ("u_2", "H", "X"),
            ("v_2", "H", "Y"),
            ("mu_2", "HS", "M"),
            ("mub", "HS", "M"),
            ("c1h", "V", "M"),
            ("c2h", "V", "M"),
            ("dnw", "V", "M"),
            ("msftx", "HS", "M"),
            ("msfty", "HS", "M"),
            ("msfux", "HS", "X"),
            ("msfuy", "HS", "X"),
            ("msfvx", "HS", "Y"),
            ("msfvx_inv", "HS", "Y"),
            ("msfvy", "HS", "M"),
            ("rdx", "C", "M"),
            ("rdy", "C", "M"),
        ]
    if not any(5 in groups for _, groups, _, _ in dyn.ANCHORS):
        dyn.ANCHORS = [
            (stage, tuple(groups) + ((5,) if stage in (0, 1) else ()), anchor, where)
            for stage, groups, anchor, where in dyn.ANCHORS
        ]
    # Keep shared comparisons on owned mass columns. Group 5 extends its
    # memory slice to i=ide, the east-staggered input consumed at i=ide-1.
    dyn.WINDOWS = [(100, 134), (213, 234)]
    dyn.HALO_WINDOW = tuple(sorted(set(dyn.HALO_WINDOW) | {5}))
    if "INTEGER             :: st, w, i0, i1, ju, ku, iu, jhi" not in dyn.HELPER:
        dyn.HELPER = dyn.HELPER.replace(
            "INTEGER             :: st, w, i0, i1, ju, ku, iu",
            "INTEGER             :: st, w, i0, i1, ju, ku, iu, jlo, jhi, meta_un, tile",
            1,
        )
        dyn.HELPER = dyn.HELPER.replace(
            "LOGICAL, SAVE       :: asked = .FALSE., armed = .FALSE.",
            "LOGICAL, SAVE       :: asked = .FALSE., armed = .FALSE., meta_written = .FALSE.",
            1,
        )
        dyn.HELPER = dyn.HELPER.replace(
            "CHARACTER(LEN=512)  :: dir, fn",
            "CHARACTER(LEN=512)  :: dir, fn, meta_fn",
            1,
        )
        meta_anchor = "      IF ( .NOT. armed ) RETURN\n"
        meta_block = """      IF ( .NOT. armed ) RETURN
      IF ( .NOT. meta_written ) THEN
         meta_written = .TRUE.
         meta_fn = TRIM(fn)//'.meta'
         OPEN( NEWUNIT=meta_un, FILE=TRIM(meta_fn), FORM='UNFORMATTED', &
               ACCESS='STREAM', STATUS='REPLACE', ACTION='WRITE', IOSTAT=st )
         IF ( st == 0 ) THEN
            WRITE(meta_un) 50503, ids, ide, jds, jde, kds, kde, &
                           ims, ime, jms, jme, kms, kme, &
                           ips, ipe, jps, jpe, kps, kpe, grid%num_tiles
            DO tile = 1, grid%num_tiles
               WRITE(meta_un) grid%i_start(tile), grid%i_end(tile), &
                              grid%j_start(tile), grid%j_end(tile)
            END DO
            CLOSE(meta_un)
         END IF
      END IF
"""
        if dyn.HELPER.count(meta_anchor) != 1:
            raise SystemExit("G33 rank metadata anchor changed")
        dyn.HELPER = dyn.HELPER.replace(meta_anchor, meta_block, 1)
        old = "         WRITE(un) stage, grp, i0, i1, jps, ju, kps, ku, ips, iu\n"
        new_header = (
            "         jlo = jps\n"
            "         IF (grp == 5) jlo = MAX(jms,jps-1)\n"
            "         jhi = ju\n"
            "         IF (grp == 5) jhi = MIN(jpe,jde)\n"
            "         WRITE(un) stage, grp, i0, i1, jlo, jhi, kps, ku, ips, iu\n"
        )
        if dyn.HELPER.count(old) != 1:
            raise SystemExit("G33 stage-probe record header anchor changed")
        dyn.HELPER = dyn.HELPER.replace(old, new_header, 1)


def make_overlay(source: Path, output: Path) -> dict[str, str]:
    configure_s5()
    raw = source.read_bytes()
    source_sha = hashlib.sha256(raw).hexdigest()
    if source_sha != PIN_SOLVE_EM:
        raise SystemExit(
            f"refuse solve_em source SHA {source_sha}; expected {PIN_SOLVE_EM}"
        )
    rendered = dyn.build(raw.decode())
    stripped = dyn.strip_guarded(rendered)
    if stripped.encode() != raw:
        raise SystemExit("G33 guarded-block stripping did not recover solve_em bytes")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered)
    return {
        "canonical_sha256": source_sha,
        "overlay_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "stripped_sha256": hashlib.sha256(stripped.encode()).hexdigest(),
        "groups": "G33 groups 1-4 plus S5 group 5 actual calc_ww_cp arguments",
    }


def make_cons_input_overlay(source: Path, output: Path) -> dict[str, str]:
    """Snapshot the actual mp237 G4 Fortran-kernel inputs at kdm6_cons entry."""
    raw = source.read_bytes()
    source_sha = hashlib.sha256(raw).hexdigest()
    if source_sha != PIN_G4_CONS:
        raise SystemExit(
            f"refuse G4 census source SHA {source_sha}; expected {PIN_G4_CONS}"
        )
    text = "#define KDM6AD_S5_KDM_INPUT_CAPTURE\n" + raw.decode()
    decl_anchor = "   real :: z_sum\n"
    decl = """   real :: z_sum
#ifdef KDM6AD_S5_KDM_INPUT_CAPTURE
   integer :: s5_unit, s5_status, s5_window, s5_i0, s5_i1
   character(len=512) :: s5_prefix, s5_file
#endif
"""
    if text.count(decl_anchor) != 1:
        raise SystemExit("G4 kdm6_cons local declaration anchor is not unique")
    text = text.replace(decl_anchor, decl, 1)

    call_anchor = "#ifdef KDM6AD_NORMALIZATION_CAPTURE\n   g4_census_step = itimestep\n#endif\n"
    dump = """#ifdef KDM6AD_S5_KDM_INPUT_CAPTURE
   if (itimestep .eq. 1) then
     s5_prefix = ''
     call get_environment_variable('KDM6AD_S5_CONS_INPUT_PREFIX', s5_prefix, status=s5_status)
     if (s5_status .eq. 0 .and. len_trim(s5_prefix) .gt. 0) then
       do s5_window = 1, 2
         if (s5_window .eq. 1) then
           s5_i0 = max(its,101)
           s5_i1 = min(ite,133)
         else
           s5_i0 = max(its,214)
           s5_i1 = min(ite,234)
         endif
         if (s5_i0 .gt. s5_i1) cycle
         write(s5_file,'(A,".rank",I0,".step",I0,".w",I0,".i",I0,"-",I0,".j",I0,"-",I0,".bin")') &
              trim(s5_prefix), mytask, itimestep, s5_window, s5_i0, s5_i1, jts, jte
         open(newunit=s5_unit, file=trim(s5_file), form='unformatted', access='stream', &
              status='replace', action='write', iostat=s5_status)
         if (s5_status .eq. 0) then
           write(s5_unit) 50502, itimestep, s5_window, mytask, ids, ide, jds, jde, kds, kde, &
                          ims, ime, jms, jme, kms, kme, its, ite, jts, jte, kts, kte, s5_i0, s5_i1
           write(s5_unit) delt, g, cpd, cpv, ccn0, rd, rv, t0c, ep1, ep2, qmin, &
                          xls, xlv0, xlf0, den0, denr, scale_h, ncmin_land, ncmin_sea, cliq, cice, psat
           write(s5_unit) has_reqc, has_reqi, has_reqs
           write(s5_unit) th(s5_i0:s5_i1,kts:kte,jts:jte)
           write(s5_unit) q(s5_i0:s5_i1,kts:kte,jts:jte)
           write(s5_unit) qc(s5_i0:s5_i1,kts:kte,jts:jte)
           write(s5_unit) qr(s5_i0:s5_i1,kts:kte,jts:jte)
           write(s5_unit) qi(s5_i0:s5_i1,kts:kte,jts:jte)
           write(s5_unit) qs(s5_i0:s5_i1,kts:kte,jts:jte)
           write(s5_unit) qg(s5_i0:s5_i1,kts:kte,jts:jte)
           write(s5_unit) nn(s5_i0:s5_i1,kts:kte,jts:jte)
           write(s5_unit) nc(s5_i0:s5_i1,kts:kte,jts:jte)
           write(s5_unit) ni(s5_i0:s5_i1,kts:kte,jts:jte)
           write(s5_unit) nr(s5_i0:s5_i1,kts:kte,jts:jte)
           write(s5_unit) bg(s5_i0:s5_i1,kts:kte,jts:jte)
           write(s5_unit) den(s5_i0:s5_i1,kts:kte,jts:jte)
           write(s5_unit) pii(s5_i0:s5_i1,kts:kte,jts:jte)
           write(s5_unit) p(s5_i0:s5_i1,kts:kte,jts:jte)
           write(s5_unit) delz(s5_i0:s5_i1,kts:kte,jts:jte)
           write(s5_unit) xland(s5_i0:s5_i1,jts:jte)
           close(s5_unit)
         endif
       enddo
     endif
   endif
#endif

"""
    if text.count(call_anchor) != 1:
        raise SystemExit("G4 kdm6_cons entry anchor is not unique")
    text = text.replace(call_anchor, dump + call_anchor, 1)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text)
    stripped = text.replace("#define KDM6AD_S5_KDM_INPUT_CAPTURE\n", "", 1)
    stripped = stripped.replace(decl, decl_anchor, 1)
    stripped = stripped.replace(dump + call_anchor, call_anchor, 1)
    if stripped.encode() != raw:
        raise SystemExit("G4 input guard stripping did not recover G4 source bytes")
    return {
        "canonical_sha256": source_sha,
        "overlay_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "stripped_sha256": hashlib.sha256(stripped.encode()).hexdigest(),
        "record_schema": "50502, 24 int32 header, 22 f32 scalars, 3 int32 flags, 16 f32 3D + 1 f32 2D arrays",
    }



CONS_INPUT_FIELDS_3D = (
    "th", "q", "qc", "qr", "qi", "qs", "qg", "nn", "nc", "ni",
    "nr", "bg", "den", "pii", "p", "delz",
)
CONS_INPUT_FIELDS_2D = ("xland",)
CONS_INPUT_SCALARS = (
    "delt", "g", "cpd", "cpv", "ccn0", "rd", "rv", "t0c", "ep1",
    "ep2", "qmin", "xls", "xlv0", "xlf0", "den0", "denr", "scale_h",
    "ncmin_land", "ncmin_sea", "cliq", "cice", "psat",
)


def read_cons_input_tree(directory: Path, grid: str) -> dict:
    """Read every rank/tile raw stream and reject incomplete or duplicate coverage."""
    import numpy as np

    files = sorted(directory.glob("*.bin"))
    if not files:
        raise ValueError(f"no kdm6_cons input streams under {directory}")
    by_column: dict[tuple[str, int, int, int], object] = {}
    metadata = []
    scalar_words = None
    flag_words = None
    for path in files:
        raw = path.read_bytes()
        offset = 0

        def take(dtype, count):
            nonlocal offset
            dt = np.dtype(dtype)
            nbyte = dt.itemsize * count
            if offset + nbyte > len(raw):
                raise ValueError(f"truncated {path.name} at byte {offset}")
            array = np.frombuffer(raw, dtype=dt, count=count, offset=offset).copy()
            offset += nbyte
            return array

        header = take(">i4", 24)
        (schema, step, window, rank, ids, ide, jds, jde, kds, kde, ims, ime,
         jms, jme, kms, kme, its, ite, jts, jte, kts, kte, i0, i1) = map(int, header)
        if schema != 50502 or step != 1 or window not in (1, 2):
            raise ValueError(f"unexpected schema/step/window in {path.name}: {schema,step,window}")
        if i0 > i1 or jts > jte or kts > kte:
            raise ValueError(f"invalid bounds in {path.name}")
        ni, nk, nj = i1 - i0 + 1, kte - kts + 1, jte - jts + 1
        scalars = take(">f4", len(CONS_INPUT_SCALARS)).view(">u4")
        flags = take(">i4", 3)
        if scalar_words is None:
            scalar_words, flag_words = scalars, flags
        elif not np.array_equal(scalar_words, scalars) or not np.array_equal(flag_words, flags):
            raise ValueError(f"run-level scalar/flag inputs differ at {path.name}")
        fields = {}
        for name in CONS_INPUT_FIELDS_3D:
            vals = take(">f4", ni * nk * nj).reshape((ni, nk, nj), order="F")
            fields[name] = vals.view(">u4")
        for name in CONS_INPUT_FIELDS_2D:
            vals = take(">f4", ni * nj).reshape((ni, nj), order="F")
            fields[name] = vals.view(">u4")
        if offset != len(raw):
            raise ValueError(f"unexpected trailing bytes in {path.name}: {len(raw)-offset}")
        metadata.append({"file": path.name, "rank": rank, "window": window,
                         "global_i": [i0, i1], "j": [jts, jte], "k": [kts, kte],
                         "patch_i": [its, ite], "bytes": len(raw),
                         "sha256": hashlib.sha256(raw).hexdigest()})
        for name, array in fields.items():
            for local, i in enumerate(range(i0, i1 + 1)):
                key = (name, i, jts, jte)
                if key in by_column:
                    raise ValueError(f"duplicate owned KDM input column {key}")
                by_column[key] = array[local]
    if not by_column:
        raise ValueError(f"no decoded KDM input data under {directory}")
    if grid == "1x1":
        territories = {0: (2, 233)}
        expected_files = {
            (0, 1, 101, 133, 2, 142), (0, 1, 101, 133, 143, 281),
            (0, 2, 214, 233, 2, 142), (0, 2, 214, 233, 143, 281),
        }
    elif grid == "2x1":
        territories = {0: (2, 117), 1: (118, 233)}
        expected_files = {
            (0, 1, 101, 117, 2, 142), (0, 1, 101, 117, 143, 281),
            (1, 1, 118, 133, 2, 142), (1, 1, 118, 133, 143, 281),
            (1, 2, 214, 233, 2, 142), (1, 2, 214, 233, 143, 281),
        }
    else:
        raise ValueError("grid must be the declared S5 case 1x1 or 2x1")
    j_tiles = {(2, 142), (143, 281)}
    got_files = set()
    for row in metadata:
        rank = row["rank"]
        if rank not in territories:
            raise ValueError(f"unexpected owner rank {rank} in {row['file']}")
        pi0, pi1 = territories[rank]
        if row["patch_i"] != [pi0, pi1] or tuple(row["j"]) not in j_tiles:
            raise ValueError(f"rank territory mismatch in {row['file']}")
        i0, i1 = row["global_i"]
        j0, j1 = row["j"]
        got_files.add((rank, row["window"], i0, i1, j0, j1))
        if row["k"] != [1, 39]:
            raise ValueError(f"unexpected native levels in {row['file']}: {row['k']}")
    if got_files != expected_files:
        raise ValueError(f"KDM input file schedule mismatch: missing={sorted(expected_files-got_files)} unexpected={sorted(got_files-expected_files)}")
    expected_keys = {
        (name, i, j0, j1)
        for name in (*CONS_INPUT_FIELDS_3D, *CONS_INPUT_FIELDS_2D)
        for j0, j1 in ((2, 142), (143, 281))
        for i in (*range(101, 134), *range(214, 234))
    }
    if set(by_column) != expected_keys:
        raise ValueError(f"KDM input field coverage mismatch: missing={sorted(expected_keys-set(by_column))[:8]} unexpected={sorted(set(by_column)-expected_keys)[:8]}")
    return {"grid": grid, "columns": by_column, "metadata": metadata,
            "scalars": scalar_words, "flags": flag_words}


def compare_cons_inputs(left: Path, right: Path, left_grid: str, right_grid: str) -> dict:
    """Compare same-column kdm6_cons entry operands as raw f32 words."""
    import numpy as np
    a, b = read_cons_input_tree(left, left_grid), read_cons_input_tree(right, right_grid)
    if a["columns"].keys() != b["columns"].keys():
        raise ValueError("KDM operand coverage differs: refusing partial comparison")
    if not np.array_equal(a["scalars"], b["scalars"]):
        scalar_diffs = [CONS_INPUT_SCALARS[i] for i, (x, y) in enumerate(zip(a["scalars"], b["scalars"])) if x != y]
    else:
        scalar_diffs = []
    if not np.array_equal(a["flags"], b["flags"]):
        flag_diffs = [int(i) for i, (x, y) in enumerate(zip(a["flags"], b["flags"])) if x != y]
    else:
        flag_diffs = []
    by_field = {}
    first = None
    for name in (*CONS_INPUT_FIELDS_3D, *CONS_INPUT_FIELDS_2D):
        differing_words = 0
        differing_columns = []
        max_abs = 0.0
        for key in sorted((k for k in a["columns"] if k[0] == name), key=lambda k:(k[2],k[1])):
            av, bv = a["columns"][key], b["columns"][key]
            if av.shape != bv.shape:
                raise ValueError(f"shape mismatch at {key}: {av.shape} vs {bv.shape}")
            diff = av != bv
            n = int(np.count_nonzero(diff))
            if n:
                differing_words += n
                differing_columns.append(key[1])
                avf = av.view(">f4").astype(np.float64)
                bvf = bv.view(">f4").astype(np.float64)
                with np.errstate(invalid="ignore"):
                    max_abs = max(max_abs, float(np.nanmax(np.abs(avf-bvf))))
                if first is None:
                    loc = np.argwhere(diff)[0]
                    first = {"field": name, "i": key[1], "j_start": key[2],
                             "j_index": int(key[2] + loc[-1]),
                             "k_index": int(loc[0]) + 1 if len(loc)==2 else None,
                             "left_u32": int(av.reshape(-1)[np.ravel_multi_index(tuple(loc),av.shape)]),
                             "right_u32": int(bv.reshape(-1)[np.ravel_multi_index(tuple(loc),bv.shape)])}
        by_field[name] = {"differing_words": differing_words,
                          "differing_i_columns": sorted(set(differing_columns)),
                          "max_absolute": max_abs}
    return {"schema":"s5-kdm-cons-input-bit-compare-v1", "left":str(left),"right":str(right),
            "left_grid":left_grid,"right_grid":right_grid,
            "coverage_records_left":a["metadata"],"coverage_records_right":b["metadata"],
            "common_owned_column_slices":len(a["columns"]),
            "run_scalar_differences":scalar_diffs,"run_flag_differences":flag_diffs,
            "first_difference":first,"fields":by_field}

def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    overlay = sub.add_parser("overlay")
    overlay.add_argument("canonical", type=Path)
    overlay.add_argument("output", type=Path)
    cons_overlay = sub.add_parser("cons-overlay")
    cons_overlay.add_argument("canonical", type=Path)
    cons_overlay.add_argument("output", type=Path)
    compare = sub.add_parser("compare-cons")
    compare.add_argument("left", type=Path)
    compare.add_argument("right", type=Path)
    compare.add_argument("output", type=Path)
    compare.add_argument("--left-grid", choices=("1x1", "2x1"), required=True)
    compare.add_argument("--right-grid", choices=("1x1", "2x1"), required=True)
    args = parser.parse_args()
    if args.command == "overlay":
        import json

        print(json.dumps(make_overlay(args.canonical, args.output), indent=2))
        return 0
    if args.command == "cons-overlay":
        import json

        print(json.dumps(make_cons_input_overlay(args.canonical, args.output), indent=2))
        return 0
    if args.command == "compare-cons":
        import json

        result = compare_cons_inputs(args.left, args.right, args.left_grid, args.right_grid)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2))
        print(json.dumps({"first_difference": result["first_difference"],
                          "common_owned_column_slices": result["common_owned_column_slices"],
                          "scalar_differences": result["run_scalar_differences"],
                          "flag_differences": result["run_flag_differences"]}, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
