#!/bin/bash
# Build the timestep-refinement driver (owner review §9).
#
# A separate script from fortran_build.sh for the same reason the driver is a
# separate file: that script produces the four-leg DECISION bundles and its
# output is anchored by manifest hash. This one produces an experiment, links a
# different driver, and writes no provenance record -- so a refinement run can
# never be mistaken for, or contaminate, a decision artifact.
set -euo pipefail
cd "$(dirname "$0")/../.."
HOST=host/KIM-meso_v1.0
HERE=harness/g33_fortran
FC=$(command -v gfortran || true)
[ -n "$FC" ] || { echo "gfortran not found" >&2; exit 2; }

ALGO=legacy; FIXTURE_NAME=g33_fixture_v1; OUT=""; DUMP=0
for a in "$@"; do
    case "$a" in
        --algo=*)    ALGO="${a#--algo=}" ;;
        --fixture=*) FIXTURE_NAME="${a#--fixture=}" ;;
        # DIAGNOSTIC. Builds the instrumented overlay so the kernel emits its own
        # per-sub-cycle records (mstep, gate) alongside the refinement stream. The
        # refinement measures the OPERATOR, so this is not the default -- and any
        # run using it must be checked to produce a bit-identical final state
        # against the uninstrumented build before its records are believed.
        --dump)      DUMP=1 ;;
        --*) echo "unknown flag: $a" >&2; exit 2 ;;
        *) [ -z "$OUT" ] && OUT="$a" || { echo "unexpected arg: $a" >&2; exit 2; } ;;
    esac
done
case "$ALGO" in
    legacy)       MODULE="$HOST/phys/module_mp_kdm6.F";      DRVDEF=() ;;
    conservative) MODULE="$HOST/phys/module_mp_kdm6_cons.F"; DRVDEF=(-DKDM6_CONS) ;;
    *) echo "--algo must be legacy or conservative" >&2; exit 2 ;;
esac
FIXTURE_SRC="$HERE/${FIXTURE_NAME}.f90"
[ -f "$FIXTURE_SRC" ] || { echo "no such fixture: $FIXTURE_SRC" >&2; exit 2; }
[ -n "$OUT" ] || OUT=$(mktemp -d "${TMPDIR:-/tmp}/g33-refine.XXXXXX")
[ -d "$OUT" ] || mkdir -p "$OUT"

COMMON_FLAGS=(-O2 -ftree-vectorize -funroll-loops -ffree-form -ffree-line-length-none
              -fconvert=big-endian -frecord-marker=4 -fallow-argument-mismatch
              -fallow-invalid-boz)
REF_FLAGS=("${COMMON_FLAGS[@]}" -w)
KDM6_FLAGS=("${COMMON_FLAGS[@]}" -w -ffp-contract=off)
CPP_FLAGS=(-cpp -DRWORDSIZE=4 -DEM_CORE=1)
DRIVER_FLAGS=("${COMMON_FLAGS[@]}" -ffp-contract=off -Wall)
fc() { local o="$1"; shift; "$FC" -c "$@" -J"$OUT" -I"$OUT" -o "$o" 2>"$o.err" \
        || { echo "COMPILE FAILED: $*"; head -25 "$o.err"; exit 1; }; }

fc "$OUT/g33_fixture_v1.o"         "${DRIVER_FLAGS[@]}" "$FIXTURE_SRC"
fc "$OUT/libmassv.o"               "${REF_FLAGS[@]}" "${CPP_FLAGS[@]}" "$HOST/frame/libmassv.F"
fc "$OUT/stub_wrf_error.o"         "${REF_FLAGS[@]}" "$HERE/stub_wrf_error.f90"
fc "$OUT/module_model_constants.o" "${REF_FLAGS[@]}" "${CPP_FLAGS[@]}" "$HOST/share/module_model_constants.F"
fc "$OUT/module_mp_radar.o"        "${REF_FLAGS[@]}" "${CPP_FLAGS[@]}" "$HOST/phys/module_mp_radar.F"
# The PINNED module by default: this measures the reference operator, and
# instrumentation would otherwise be a second difference between sweep members.
# --dump swaps in the generated overlay, whose macro-OFF form is textually
# identical to the pinned source (the A/B/C non-invasiveness proof).
MODULE_SRC="$MODULE"; DUMP_DEF=()
if [ "$DUMP" = 1 ]; then
    MODULE_SRC="$OUT/module_mp_ovl.F"
    python3 "$HERE/make_fortran_overlay.py" "$MODULE" "$MODULE_SRC" --algo="$ALGO" >/dev/null
    DUMP_DEF=(-DKDM6_G33_FORTRAN_DUMP)
fi
fc "$OUT/module_mp.o"              "${KDM6_FLAGS[@]}" "${CPP_FLAGS[@]}" ${DUMP_DEF[@]+"${DUMP_DEF[@]}"} "$MODULE_SRC"
fc "$OUT/g33_refine_driver.o"      "${DRIVER_FLAGS[@]}" "${CPP_FLAGS[@]}" ${DRVDEF[@]+"${DRVDEF[@]}"} ${DUMP_DEF[@]+"${DUMP_DEF[@]}"} \
                                   "$HERE/g33_refine_driver.f90"
"$FC" "${COMMON_FLAGS[@]}" -o "$OUT/g33_refine_driver" \
    "$OUT/g33_refine_driver.o" "$OUT/g33_fixture_v1.o" "$OUT/module_mp.o" \
    "$OUT/module_mp_radar.o" "$OUT/module_model_constants.o" \
    "$OUT/stub_wrf_error.o" "$OUT/libmassv.o" 2>"$OUT/link.err" \
    || { echo "LINK FAILED"; head -25 "$OUT/link.err"; exit 1; }
echo "$OUT"
