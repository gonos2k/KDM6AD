#!/bin/bash
# Build one standalone Fortran G3.3-M case against the checked-in raw-bit fixture.
# Canonical host sources remain frozen; only the generated fixture module, driver
# and temporary instrumentation overlay are harness-owned.
set -euo pipefail
cd "$(dirname "$0")/../.."

HOST=host/KIM-meso_v1.0
HERE=harness/g33_fortran
FC=$(command -v gfortran || true)
[ -n "$FC" ] || { echo "gfortran not found" >&2; exit 2; }

# A canonical, B generated overlay/macro OFF, C same overlay/macro ON.
OUT=""; DUMP=0; OVERLAY=0; ALGO=legacy; OVERLAY_FILE_ARG=""
for a in "$@"; do
    case "$a" in
        --dump) DUMP=1; OVERLAY=1 ;;
        --overlay) OVERLAY=1 ;;
        --overlay-file=*) OVERLAY_FILE_ARG="${a#--overlay-file=}"; OVERLAY=1; DUMP=1 ;;
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

LIBMASSV="$HOST/frame/libmassv.F"
CONSTS="$HOST/share/module_model_constants.F"
RADAR="$HOST/phys/module_mp_radar.F"
FIXTURE_SRC="$HERE/g33_fixture_v1.f90"
for f in "$LIBMASSV" "$CONSTS" "$RADAR" "$MODULE" "$FIXTURE_SRC"; do
    [ -f "$f" ] || { echo "missing source: $f" >&2; exit 2; }
done

if [ -n "$OUT" ]; then
    [ -e "$OUT" ] && { echo "output path already exists (refusing): $OUT" >&2; exit 2; }
    mkdir "$OUT"
else
    OUT=$(mktemp -d "${TMPDIR:-/tmp}/g33-fortran.XXXXXX")
fi

COMMON_FLAGS=(-O2 -ftree-vectorize -funroll-loops -ffree-form -ffree-line-length-none
              -fconvert=big-endian -frecord-marker=4 -fallow-argument-mismatch
              -fallow-invalid-boz)
REF_FLAGS=("${COMMON_FLAGS[@]}" -w)
KDM6_FLAGS=("${COMMON_FLAGS[@]}" -w -ffp-contract=off)
CPP_FLAGS=(-cpp -DRWORDSIZE=4 -DEM_CORE=1)
DRIVER_FLAGS=("${COMMON_FLAGS[@]}" -ffp-contract=off -Wall)

CMDLOG="$OUT/commands.txt"
: >"$CMDLOG"
fc() {
    local out="$1"; shift
    printf '%q ' "$FC" -c "$@" -J"$OUT" -I"$OUT" -o "$out" >>"$CMDLOG"
    printf '\n' >>"$CMDLOG"
    "$FC" -c "$@" -J"$OUT" -I"$OUT" -o "$out" 2>"$out.err" \
        || { echo "FORTRAN COMPILE FAILED: $*"; head -20 "$out.err"; exit 1; }
}

fc "$OUT/g33_fixture_v1.o"        "${DRIVER_FLAGS[@]}" "$FIXTURE_SRC"
fc "$OUT/libmassv.o"              "${REF_FLAGS[@]}" "${CPP_FLAGS[@]}" "$LIBMASSV"
fc "$OUT/stub_wrf_error.o"        "${REF_FLAGS[@]}" "$HERE/stub_wrf_error.f90"
fc "$OUT/module_model_constants.o" "${REF_FLAGS[@]}" "${CPP_FLAGS[@]}" "$CONSTS"
fc "$OUT/module_mp_radar.o"       "${REF_FLAGS[@]}" "${CPP_FLAGS[@]}" "$RADAR"
DUMP_DEF=()
[ "$DUMP" = 1 ] && DUMP_DEF=(-DKDM6_G33_FORTRAN_DUMP)
if [ -n "$OVERLAY_FILE_ARG" ]; then
    MODULE_SRC="$OVERLAY_FILE_ARG"
elif [ "$OVERLAY" = 1 ]; then
    OVERLAY_FILE="$OUT/module_mp_ovl.F"
    python3 "$HERE/make_fortran_overlay.py" "$MODULE" "$OVERLAY_FILE" --algo="$ALGO" >/dev/null
    MODULE_SRC="$OVERLAY_FILE"
else
    MODULE_SRC="$MODULE"
fi
fc "$OUT/module_mp.o" "${KDM6_FLAGS[@]}" "${CPP_FLAGS[@]}" "${DUMP_DEF[@]}" "$MODULE_SRC"
fc "$OUT/g33_fortran_driver.o" "${DRIVER_FLAGS[@]}" "${CPP_FLAGS[@]}" "${DRVDEF[@]}" \
    "$HERE/g33_fortran_driver.f90"

LINK_OBJS=("$OUT/g33_fortran_driver.o" "$OUT/g33_fixture_v1.o" "$OUT/module_mp.o"
           "$OUT/module_mp_radar.o" "$OUT/module_model_constants.o"
           "$OUT/stub_wrf_error.o" "$OUT/libmassv.o")
printf '%q ' "$FC" "${COMMON_FLAGS[@]}" -o "$OUT/g33_fortran_driver" "${LINK_OBJS[@]}" >>"$CMDLOG"
printf '\n' >>"$CMDLOG"
"$FC" "${COMMON_FLAGS[@]}" -o "$OUT/g33_fortran_driver" "${LINK_OBJS[@]}" \
    2>"$OUT/link.err" || { echo "FORTRAN LINK FAILED"; head -20 "$OUT/link.err"; exit 1; }

python3 "$HERE/g33_provenance.py" "$OUT" "$ALGO" "$DUMP" "$FC" "$MODULE_SRC" "$MODULE"
echo "built ($ALGO): $OUT/g33_fortran_driver"
echo "$OUT"
