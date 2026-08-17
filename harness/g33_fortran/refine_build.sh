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
# CONTENT-ADDRESSED STAGING for every private source (owner §10). The build
# compiled straight from the host tree and the provenance collector re-read
# those same paths afterwards, so an edit in between yielded an executable
# from one byte set and a record of another. Staging by digest makes the two
# the same bytes by construction: what is hashed is what was compiled, and a
# concurrent edit produces a different staged path rather than a silent
# substitution. The overlay has been content-addressed since §9.1; this
# extends it to the sources it is built beside.
# OUTSIDE the output directory, and named by content: gfortran embeds each
# source's filename in the binary, so staging under $OUT made the same
# experiment compile to different executables in different output
# directories -- the exact property the overlay was content-addressed for
# (§9.1). Same bytes, same path, same binary.
STAGE="${TMPDIR:-/tmp}/g33-stage"; mkdir -p "$STAGE"
# The staged path is an IMPLEMENTATION detail -- it lives under the output
# directory, so logging it would make the source record vary per build
# directory and two builds of one experiment would address differently. The
# map keeps the LOGICAL path, which is what the record is about; the staged
# bytes are what gets compiled and hashed.
STAGE_MAP="$OUT/staged-map.txt"; : >"$STAGE_MAP"
stage() {
    local src="$1" d b
    d=$(shasum -a 256 "$src" | cut -d' ' -f1); b=$(basename "$src")
    local dst="$STAGE/$d-$b"
    [ -f "$dst" ] || { cp "$src" "$dst.$$.tmp" && mv -f "$dst.$$.tmp" "$dst"; }
    printf '%s\t%s\n' "$dst" "$src" >>"$STAGE_MAP"
    printf '%s' "$dst"
}

SRCLOG="$OUT/sources.txt"; : >"$SRCLOG"
fc() { local o="$1"; shift
       # The LOGICAL path with the digest of the bytes ACTUALLY COMPILED
       # (Codex): logging the logical path alone sent the collector back to
       # the host file, which is the very re-read staging exists to remove --
       # an edit between compile and collect would then record bytes the
       # compiler never saw. The name says what this source IS; the digest
       # says what was fed to the compiler, taken here, at that moment.
       local last="${@: -1}" logical sha
       logical=$(awk -F'\t' -v k="$last" '$1==k{print $2}' "$STAGE_MAP" 2>/dev/null | tail -1)
       sha=$(shasum -a 256 "$last" | cut -d' ' -f1)
       printf '%s\t%s\n' "${logical:-$last}" "$sha" >>"$SRCLOG"
       printf '%q ' "$FC" -c "$@" -J"$OUT" -I"$OUT" -o "$o" >>"$CMDLOG"; printf '\n' >>"$CMDLOG"
       "$FC" -c "$@" -J"$OUT" -I"$OUT" -o "$o" 2>"$o.err" \
        || { echo "COMPILE FAILED: $*"; head -25 "$o.err"; exit 1; }; }

fc "$OUT/g33_fixture_v1.o"         "${DRIVER_FLAGS[@]}" "$(stage "$FIXTURE_SRC")"
fc "$OUT/libmassv.o"               "${REF_FLAGS[@]}" "${CPP_FLAGS[@]}" "$(stage "$HOST/frame/libmassv.F")"
fc "$OUT/stub_wrf_error.o"         "${REF_FLAGS[@]}" "$(stage "$HERE/stub_wrf_error.f90")"
fc "$OUT/module_model_constants.o" "${REF_FLAGS[@]}" "${CPP_FLAGS[@]}" "$(stage "$HOST/share/module_model_constants.F")"
fc "$OUT/module_mp_radar.o"        "${REF_FLAGS[@]}" "${CPP_FLAGS[@]}" "$(stage "$HOST/phys/module_mp_radar.F")"
# The PINNED module by default: this measures the reference operator, and
# instrumentation would otherwise be a second difference between sweep members.
# --dump swaps in the generated overlay, whose macro-OFF form is textually
# identical to the pinned source (the A/B/C non-invasiveness proof).
MODULE_STAGED=$(stage "$MODULE")
MODULE_SRC="$MODULE_STAGED"; DUMP_DEF=()
if [ "$DUMP" = 1 ]; then
    # CONTENT-ADDRESSED overlay path (owner §9.1). gfortran embeds each source's
    # filename in the binary for backtraces -- `-ffile-prefix-map` does not reach
    # that string -- so an overlay written into $OUT gave the same instrumented
    # build a different executable digest in every output directory. Naming it by
    # its own digest makes the path a function of the content: identical overlays
    # compile from an identical path, different ones cannot collide.
    python3 "$HERE/make_fortran_overlay.py" "$MODULE_STAGED" "$OUT/module_mp_ovl.F" \
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
    # ...and the source log names it as the bundle publishes it: the
    # content-addressed path lives under TMPDIR, which differs per machine,
    # and a machine-specific string in the provenance would move the same
    # experiment's address between hosts.
    printf '%s\t%s\n' "$MODULE_SRC" "module_mp_ovl.F" >>"$STAGE_MAP"
    DUMP_DEF=(-DKDM6_G33_FORTRAN_DUMP)
    [ "$NFLUX" = 1 ] && DUMP_DEF+=(-DKDM6_G33_NUMBER_DUMP)
fi
fc "$OUT/module_mp.o"              "${KDM6_FLAGS[@]}" "${CPP_FLAGS[@]}" ${DUMP_DEF[@]+"${DUMP_DEF[@]}"} "$MODULE_SRC"
# The window header's loop count is the KERNEL's arithmetic, so its limit has
# to be the KERNEL's constant. The driver held a literal 120.0, which agreed
# with the pinned kernel by coincidence and would have gone on agreeing with
# nothing if the kernel's limit ever moved (owner review §11). Taken from
# $MODULE_SRC -- the bytes about to be compiled, overlay included -- so the
# two cannot disagree by construction rather than by inspection.
DTCLDCR=$(sed -n 's/.*::[[:space:]]*dtcldcr[[:space:]]*=[[:space:]]*\([0-9.]\{1,\}\).*/\1/p' "$MODULE_SRC")
[ "$(printf '%s\n' "$DTCLDCR" | grep -c .)" = 1 ] || {
    echo "REFUSED: $MODULE_SRC declares dtcldcr $(printf '%s\n' "$DTCLDCR" | grep -c .) times; the driver's window header needs exactly one" >&2
    exit 2; }
fc "$OUT/g33_refine_driver.o"      "${DRIVER_FLAGS[@]}" "${CPP_FLAGS[@]}" "-DKDM6_DTCLDCR=$DTCLDCR" ${DRVDEF[@]+"${DRVDEF[@]}"} ${DUMP_DEF[@]+"${DUMP_DEF[@]}"} \
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
    "$OUT" "$FC" "$MODULE" "$FIXTURE_SRC" "$0" "$OUT/g33_refine_driver" \
    "$MODULE_SRC" "$MODULE_STAGED"
echo "$OUT"
