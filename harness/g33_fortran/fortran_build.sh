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
# SHA-pinned instrumentation overlay (-DKDM6_G33_FORTRAN_DUMP) that emits the
# per-op sed ladder; without it, the canonical reference (byte-identical).
#
# HERMETIC: set -euo pipefail + a fresh, owned output dir (no rm -rf; explicit
# path must not pre-exist, default is a private mktemp dir).
set -euo pipefail
cd "$(dirname "$0")/../.."

HOST=host/KIM-meso_v1.0
HERE=harness/g33_fortran
FC=$(command -v gfortran || true)
[ -n "$FC" ] || { echo "gfortran not found" >&2; exit 2; }

OUT=""; DUMP=0; ALGO=legacy
for a in "$@"; do
    case "$a" in
        --dump) DUMP=1 ;;
        --algo=*) ALGO="${a#--algo=}" ;;
        --*) echo "unknown flag: $a" >&2; exit 2 ;;
        *) [ -z "$OUT" ] && OUT="$a" || { echo "unexpected arg: $a" >&2; exit 2; } ;;
    esac
done
case "$ALGO" in
    legacy)       MODULE="$HOST/phys/module_mp_kdm6.F";      DRVDEF="" ;;
    conservative) MODULE="$HOST/phys/module_mp_kdm6_cons.F"; DRVDEF="-DKDM6_CONS" ;;
    *) echo "--algo must be legacy or conservative, got $ALGO" >&2; exit 2 ;;
esac

# Reference sources must be present (frozen host tree).
for f in "$HOST/frame/libmassv.F" "$HOST/share/module_model_constants.F" \
         "$HOST/phys/module_mp_radar.F" "$MODULE"; do
    [ -f "$f" ] || { echo "missing reference source: $f" >&2; exit 2; }
done

if [ -n "$OUT" ]; then
    [ -e "$OUT" ] && { echo "output path already exists (refusing): $OUT" >&2; exit 2; }
    mkdir -p "$OUT"
else
    OUT=$(mktemp -d "${TMPDIR:-/tmp}/g33-fortran.XXXXXX")
fi

GEN="-O2 -ftree-vectorize -funroll-loops -w -ffree-form -ffree-line-length-none \
     -fconvert=big-endian -frecord-marker=4 -fallow-argument-mismatch -fallow-invalid-boz"
KDM6="$GEN -ffp-contract=off"          # ffp-contract=off is required for f32 parity
CPPDEF="-cpp -DRWORDSIZE=4 -DEM_CORE=1"

fc() {  # $1 flags-extra  $2 src  $3 out.o
    # shellcheck disable=SC2086
    "$FC" -c $GEN $1 -J"$OUT" -I"$OUT" "$2" -o "$3" 2>"$3.err" \
        || { echo "FORTRAN COMPILE FAILED: $2"; head -20 "$3.err"; exit 1; }
}

# dependency order: constants + massv + wrf stub, then radar, then the mp module,
# then the driver (driver is -cpp so -DKDM6_CONS can rename the module entry).
fc "$CPPDEF" "$HOST/frame/libmassv.F"                 "$OUT/libmassv.o"
fc ""        "$HERE/stub_wrf_error.f90"               "$OUT/stub_wrf_error.o"
fc "$CPPDEF" "$HOST/share/module_model_constants.F"   "$OUT/module_model_constants.o"
fc "$CPPDEF" "$HOST/phys/module_mp_radar.F"           "$OUT/module_mp_radar.o"
if [ "$DUMP" = 1 ]; then
    python3 "$HERE/make_fortran_overlay.py" "$MODULE" "$OUT/module_mp_ovl.F" \
        --algo="$ALGO" >/dev/null
    fc "$KDM6 $CPPDEF -DKDM6_G33_FORTRAN_DUMP" "$OUT/module_mp_ovl.F" "$OUT/module_mp.o"
else
    fc "$KDM6 $CPPDEF" "$MODULE"                       "$OUT/module_mp.o"
fi
fc "$KDM6 $CPPDEF $DRVDEF" "$HERE/g33_fortran_driver.f90" "$OUT/g33_fortran_driver.o"

# shellcheck disable=SC2086
"$FC" $GEN -o "$OUT/g33_fortran_driver" \
    "$OUT/g33_fortran_driver.o" "$OUT/module_mp.o" "$OUT/module_mp_radar.o" \
    "$OUT/module_model_constants.o" "$OUT/stub_wrf_error.o" "$OUT/libmassv.o" \
    2>"$OUT/link.err" || { echo "FORTRAN LINK FAILED"; head -20 "$OUT/link.err"; exit 1; }

echo "built ($ALGO): $OUT/g33_fortran_driver"
echo "$OUT"
