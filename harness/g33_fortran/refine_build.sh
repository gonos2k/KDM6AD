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

ALGO=legacy; FIXTURE_NAME=g33_fixture_v1; OUT=""; DUMP=0; NFLUX=0; F64=0; PROBE=0
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
        # The surface number flux and the ice sub-step count. Its own macro, so
        # the decision-bundle build (fortran_build.sh) never emits them.
        --nflux)     DUMP=1; NFLUX=1 ;;
        # Promote the whole Fortran leg to f64 and print a full-precision probe
        # stream. For the roundoff-attribution experiment ONLY: this is not the
        # reference operator and produces no decision evidence.
        --f64)       F64=1; PROBE=1 ;;
        # The same full-precision probe stream at the REFERENCE f32 precision --
        # the control arm of the roundoff experiment.
        --probe)     PROBE=1 ;;
        --*) echo "unknown flag: $a" >&2; exit 2 ;;
        *) [ -z "$OUT" ] && OUT="$a" || { echo "unexpected arg: $a" >&2; exit 2; } ;;
    esac
done
# f64 + nflux WAS refused here: the G33F records wrote `'f32', transfer(<real>,
# 0)`, and under -fdefault-real-8 that took FOUR bytes of an EIGHT-byte value
# into an int32 mold and labelled the result f32, so a reader parsed a
# valid-looking f32 bit pattern that was not the number.
#
# The remedy is the record family, not the refusal (owner D6). The overlay now
# emits reals through a Z edit descriptor whose WIDTH follows this build's
# default real -- passed below as --real-kind, from the same variable that adds
# the flag -- and the driver writes a G33N PROTOCOL header carrying what
# `storage_size` says the compiler actually did.
REAL_KIND=f32
[ "$F64" = 1 ] && REAL_KIND=f64
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
if [ "$F64" = 1 ]; then
    # -fdefault-double-8 is required with -fdefault-real-8: without it `double
    # precision` promotes to REAL(16) and the radar hostmatrix call fails to
    # typecheck.
    # KDM6_G33_F64 still suppresses the G33R state stream. Its records carry no
    # dtype token at all -- `G33R STATE <fld> <i> <k> <8hex>` -- so widening
    # them needs a record change the archived streams would not survive, which
    # is a separate protocol question from the G33F family fixed here.
    COMMON_FLAGS+=(-fdefault-real-8 -fdefault-double-8 -DKDM6_G33_F64)
fi
[ "$PROBE" = 1 ] && COMMON_FLAGS+=(-DKDM6_G33_PRECISION_PROBE)
# The probe header names the experiment, so the fixture identity has to reach the
# driver rather than living only in the build script (owner P0-5).
COMMON_FLAGS+=("-DKDM6_G33_FIXTURE='$FIXTURE_NAME'")
# gfortran records each source's path in the binary (for backtraces), and under
# --dump/--nflux the compiled overlay lives in $OUT, so the SAME instrumented
# build produced a different executable digest in every output directory
# (owner §9.1). Remap the prefix so the embedded name is stable.
COMMON_FLAGS+=("-ffile-prefix-map=$OUT=<OUT>")
REF_FLAGS=("${COMMON_FLAGS[@]}" -w)
KDM6_FLAGS=("${COMMON_FLAGS[@]}" -w -ffp-contract=off)
CPP_FLAGS=(-cpp -DRWORDSIZE=4 -DEM_CORE=1)
DRIVER_FLAGS=("${COMMON_FLAGS[@]}" -ffp-contract=off -Wall)
# Every compile command is logged. An empty command list in a manifest is
# indistinguishable from a build nobody recorded, so the build writes it rather
# than leaving it to a caller that may not pass it (owner §9).
CMDLOG="$OUT/commands.txt"; : >"$CMDLOG"
# ...and every source. The manifest digested only the module and fixture, so a
# change to libmassv, the model constants, the radar module, the stub or the
# driver was invisible -- and host/** is gitignored, so repo_commit and
# tree_dirty do not see them either (owner P0-3).
SRCLOG="$OUT/sources.txt"; : >"$SRCLOG"
fc() { local o="$1"; shift
       printf '%s\n' "${@: -1}" >>"$SRCLOG"
       printf '%q ' "$FC" -c "$@" -J"$OUT" -I"$OUT" -o "$o" >>"$CMDLOG"; printf '\n' >>"$CMDLOG"
       "$FC" -c "$@" -J"$OUT" -I"$OUT" -o "$o" 2>"$o.err" \
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
    # CONTENT-ADDRESSED overlay path (owner §9.1). gfortran embeds each source's
    # filename in the binary for backtraces -- `-ffile-prefix-map` does not reach
    # that string -- so an overlay written into $OUT gave the same instrumented
    # build a different executable digest in every output directory. Naming it by
    # its own digest makes the path a function of the content: identical overlays
    # compile from an identical path, different ones cannot collide.
    python3 "$HERE/make_fortran_overlay.py" "$MODULE" "$OUT/module_mp_ovl.F" \
        --algo="$ALGO" --real-kind="$REAL_KIND" >/dev/null
    OVLFULL=$(shasum -a 256 "$OUT/module_mp_ovl.F" | cut -d' ' -f1)
    # CONTENT-ADDRESSED on the FULL digest (owner §13 P1-4). A 16-hex truncation
    # left a real race: two builds whose overlays share a 64-bit prefix but
    # differ in content both see "no file", both write, and the loser's compile
    # can read the winner's source. With the whole digest in the name, same
    # digest means same content and different content means a different path,
    # so there is no collision to guard -- only a partial write, which the
    # temp-then-rename handles.
    MODULE_SRC="${TMPDIR:-/tmp}/g33-ovl-${OVLFULL}.F"
    cp "$OUT/module_mp_ovl.F" "$MODULE_SRC.$$.tmp"
    mv -f "$MODULE_SRC.$$.tmp" "$MODULE_SRC"
    DUMP_DEF=(-DKDM6_G33_FORTRAN_DUMP)
    [ "$NFLUX" = 1 ] && DUMP_DEF+=(-DKDM6_G33_NUMBER_DUMP)
fi
fc "$OUT/module_mp.o"              "${KDM6_FLAGS[@]}" "${CPP_FLAGS[@]}" ${DUMP_DEF[@]+"${DUMP_DEF[@]}"} "$MODULE_SRC"
fc "$OUT/g33_refine_driver.o"      "${DRIVER_FLAGS[@]}" "${CPP_FLAGS[@]}" ${DRVDEF[@]+"${DRVDEF[@]}"} ${DUMP_DEF[@]+"${DUMP_DEF[@]}"} \
                                   "$HERE/g33_refine_driver.f90"
LINK=("$FC" "${COMMON_FLAGS[@]}" -o "$OUT/g33_refine_driver"
      "$OUT/g33_refine_driver.o" "$OUT/g33_fixture_v1.o" "$OUT/module_mp.o"
      "$OUT/module_mp_radar.o" "$OUT/module_model_constants.o"
      "$OUT/stub_wrf_error.o" "$OUT/libmassv.o")
printf '%q ' "${LINK[@]}" >>"$CMDLOG"; printf '\n' >>"$CMDLOG"
"${LINK[@]}" 2>"$OUT/link.err" \
    || { echo "LINK FAILED"; head -25 "$OUT/link.err"; exit 1; }
# What built this -- compiler digest, every source, and the binary that ran.
# The PINNED module is what the experiment is about; MODULE_SRC is what the
# compiler saw, which is the macro-gated overlay under --dump/--nflux. Both are
# recorded: binding only the compiled one would make an instrumented bundle
# unlinkable to the reference it instruments.
python3 "$(dirname "$0")/../g33_build_provenance.py" \
    "$OUT" "$FC" "$MODULE" "$FIXTURE_SRC" "$0" "$OUT/g33_refine_driver" "$MODULE_SRC"
echo "$OUT"
