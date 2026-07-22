#!/bin/bash
# Build a G3.3-M standalone Fortran driver. Compiles the CANONICAL reference
# Fortran (host/KIM-meso_v1.0) + the reference microphysics module + a harness
# fixture driver with gfortran, Fortran-only (no C++/libtorch). The host sources
# are compiled AS-IS (never modified — they are frozen); only harness/g33_fortran/
# files are ours. Bit-parity flags match the reference build (-ffp-contract=off
# is load-bearing for KDM6 f32 parity).
#
#   fortran_build.sh [OUT] [--dump] [--algo=legacy|conservative]
#
# --algo legacy (default) builds module_mp_kdm6; conservative builds
# module_mp_kdm6_cons (mp237, ρΔz interface). --dump compiles a TEMPORARY
# SHA-pinned instrumentation overlay (-DKDM6_G33_FORTRAN_DUMP); without it, the
# canonical reference (byte-identical).
#
# On success writes OUT/provenance.json — a DECISION-GRADE record of every input
# (host source SHAs, overlay generator + generated overlay + driver SHAs, the
# executable SHA, compiler path/version, exact flags + compile/link commands).
# The Fortran leg is local-only (gitignored reference tree), so this manifest is
# what makes a local result reproducible/auditable. The driver run adds the
# fixture + stdout SHAs.
#
# HERMETIC: set -euo pipefail + a fresh, owned output dir (no rm -rf; explicit
# path must not pre-exist, default is a private mktemp dir).
set -euo pipefail
cd "$(dirname "$0")/../.."

HOST=host/KIM-meso_v1.0
HERE=harness/g33_fortran
FC=$(command -v gfortran || true)
[ -n "$FC" ] || { echo "gfortran not found" >&2; exit 2; }

# Three build configs for the Fortran A/B/C non-invasiveness gate:
#   A = (neither flag)         canonical module               -> emits 0 op records
#   B = --overlay              generated overlay, macro OFF    -> emits 0 op records
#   C = --overlay --dump       generated overlay, macro ON     -> emits the op stream
# A==B==C must be raw-bit identical in final state + precip (the overlay only adds
# guarded WRITEs). --dump implies --overlay.
OUT=""; DUMP=0; OVERLAY=0; ALGO=legacy
for a in "$@"; do
    case "$a" in
        --dump) DUMP=1; OVERLAY=1 ;;
        --overlay) OVERLAY=1 ;;
        --algo=*) ALGO="${a#--algo=}" ;;
        --*) echo "unknown flag: $a" >&2; exit 2 ;;
        *) [ -z "$OUT" ] && OUT="$a" || { echo "unexpected arg: $a" >&2; exit 2; } ;;
    esac
done
case "$ALGO" in
    legacy)       MODULE="$HOST/phys/module_mp_kdm6.F";      DRVDEF=() ;;
    conservative) MODULE="$HOST/phys/module_mp_kdm6_cons.F"; DRVDEF=(-DKDM6_CONS) ;;
    *) echo "--algo must be legacy or conservative, got $ALGO" >&2; exit 2 ;;
esac

# Reference sources (frozen host tree) — all four must be present.
LIBMASSV="$HOST/frame/libmassv.F"
CONSTS="$HOST/share/module_model_constants.F"
RADAR="$HOST/phys/module_mp_radar.F"
for f in "$LIBMASSV" "$CONSTS" "$RADAR" "$MODULE"; do
    [ -f "$f" ] || { echo "missing reference source: $f" >&2; exit 2; }
done

if [ -n "$OUT" ]; then
    [ -e "$OUT" ] && { echo "output path already exists (refusing): $OUT" >&2; exit 2; }
    mkdir "$OUT"                       # parent exists; non-existence checked above
else
    OUT=$(mktemp -d "${TMPDIR:-/tmp}/g33-fortran.XXXXXX")
fi

# ── flag arrays (path-safe, no word-split surprises) ──────────────────────────
COMMON_FLAGS=(-O2 -ftree-vectorize -funroll-loops -ffree-form -ffree-line-length-none
              -fconvert=big-endian -frecord-marker=4 -fallow-argument-mismatch
              -fallow-invalid-boz)
# canonical reference is compiled AS-IS; -w silences ITS warnings (not ours),
# -ffp-contract=off is required for f32 bit-parity with the C++ side.
REF_FLAGS=("${COMMON_FLAGS[@]}" -w)
KDM6_FLAGS=("${COMMON_FLAGS[@]}" -w -ffp-contract=off)
CPP_FLAGS=(-cpp -DRWORDSIZE=4 -DEM_CORE=1)
# our harness driver is held to a higher bar: warnings ON.
DRIVER_FLAGS=("${COMMON_FLAGS[@]}" -ffp-contract=off -Wall)

CMDLOG="$OUT/commands.txt"
: >"$CMDLOG"
fc() {  # $1 out.o ; rest: flags + src
    local out="$1"; shift
    printf '%q ' "$FC" -c "$@" -J"$OUT" -I"$OUT" -o "$out" >>"$CMDLOG"; printf '\n' >>"$CMDLOG"
    # shellcheck disable=SC2086
    "$FC" -c "$@" -J"$OUT" -I"$OUT" -o "$out" 2>"$out.err" \
        || { echo "FORTRAN COMPILE FAILED: $*"; head -20 "$out.err"; exit 1; }
}

# dependency order: constants + massv + wrf stub, then radar, then the mp module,
# then the driver (driver is -cpp so -DKDM6_CONS can rename the module entry).
fc "$OUT/libmassv.o"              "${REF_FLAGS[@]}" "${CPP_FLAGS[@]}" "$LIBMASSV"
fc "$OUT/stub_wrf_error.o"        "${REF_FLAGS[@]}" "$HERE/stub_wrf_error.f90"
fc "$OUT/module_model_constants.o" "${REF_FLAGS[@]}" "${CPP_FLAGS[@]}" "$CONSTS"
fc "$OUT/module_mp_radar.o"       "${REF_FLAGS[@]}" "${CPP_FLAGS[@]}" "$RADAR"
DUMP_DEF=()
[ "$DUMP" = 1 ] && DUMP_DEF=(-DKDM6_G33_FORTRAN_DUMP)
if [ "$OVERLAY" = 1 ]; then
    OVERLAY_FILE="$OUT/module_mp_ovl.F"
    python3 "$HERE/make_fortran_overlay.py" "$MODULE" "$OVERLAY_FILE" --algo="$ALGO" >/dev/null
    MODULE_SRC="$OVERLAY_FILE"
else
    MODULE_SRC="$MODULE"
fi
fc "$OUT/module_mp.o" "${KDM6_FLAGS[@]}" "${CPP_FLAGS[@]}" "${DUMP_DEF[@]}" "$MODULE_SRC"
fc "$OUT/g33_fortran_driver.o" "${DRIVER_FLAGS[@]}" "${CPP_FLAGS[@]}" "${DRVDEF[@]}" \
    "$HERE/g33_fortran_driver.f90"

LINK_OBJS=("$OUT/g33_fortran_driver.o" "$OUT/module_mp.o" "$OUT/module_mp_radar.o"
           "$OUT/module_model_constants.o" "$OUT/stub_wrf_error.o" "$OUT/libmassv.o")
printf '%q ' "$FC" "${COMMON_FLAGS[@]}" -o "$OUT/g33_fortran_driver" "${LINK_OBJS[@]}" >>"$CMDLOG"
printf '\n' >>"$CMDLOG"
# shellcheck disable=SC2086
"$FC" "${COMMON_FLAGS[@]}" -o "$OUT/g33_fortran_driver" \
    "$OUT/g33_fortran_driver.o" "$OUT/module_mp.o" "$OUT/module_mp_radar.o" \
    "$OUT/module_model_constants.o" "$OUT/stub_wrf_error.o" "$OUT/libmassv.o" \
    2>"$OUT/link.err" || { echo "FORTRAN LINK FAILED"; head -20 "$OUT/link.err"; exit 1; }

# ── decision-grade provenance manifest (a plain script, not a heredoc) ────────
python3 "$HERE/g33_provenance.py" "$OUT" "$ALGO" "$DUMP" "$FC" "$MODULE_SRC" "$MODULE"

echo "built ($ALGO): $OUT/g33_fortran_driver"
echo "$OUT"
