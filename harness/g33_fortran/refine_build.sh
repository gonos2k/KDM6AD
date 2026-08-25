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
    # ARM N: legacy's interface, two transfer lines changed, so no driver
    # define -- the conservative arm needs one because its CALL SHAPE differs.
    # THE FACTORIAL'S SIX DERIVED ARMS. Each is a base plus the N and/or L
    # edit, so the driver define is the BASE's (conservative changes the call
    # shape; N and L do not) and the ALGOTAG define names the arm. Written as
    # one pattern rather than six cases: six near-identical lines is six
    # chances for one to name the wrong file.
    # `nmass_dry` joins the same pattern: it is a base plus the N edit in its
    # dry form, so the driver define is legacy's (none) and the ALGOTAG define
    # names the arm (owner freeze-lift, 2026-08-22).
    nmass|lncmin|nmasslncmin|nmass_dry|nmass_dry_window|melt_g1|melt_g2|melt_g3|melt_g4|cons_nmass|cons_lncmin|cons_nmasslncmin)
        MODULE="$HOST/phys/module_mp_kdm6_${ALGO}.F"
        DRVDEF=(-DKDM6_ARM_"$(printf %s "$ALGO" | tr '[:lower:]' '[:upper:]')")
        case "$ALGO" in cons_*) DRVDEF+=(-DKDM6_CONS) ;; esac ;;
    *) echo "--algo must be one of: legacy conservative nmass lncmin"\
            " nmasslncmin nmass_dry nmass_dry_window cons_nmass cons_lncmin"\
            " cons_nmasslncmin" >&2
       exit 2 ;;
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
# COPY FIRST, then hash the COPY, and name it by that (Codex). Hashing the
# source and copying it afterwards left the same window staging exists to
# close, one level down: an edit in between stored bytes under an address
# that is not their digest, and the store is shared and persistent, so the
# next build to ask for the ORIGINAL digest was handed those bytes by the
# existence check and compiled them. Reproduced -- the entry's name and its
# content disagreed, and a later build restoring the original source
# compiled the poisoned copy. Deriving the address from the stored bytes
# makes a concurrent edit produce a DIFFERENT address instead.
#
# ...and VERIFIED ON READ, not only on write (owner review §4). Naming an
# entry by its digest makes writes honest; it does not make the store
# immutable. `$TMPDIR` is shared and long-lived, so an entry already sitting
# at an address -- left by the pre-#140 implementation that could write one,
# by an interrupted run, or by anything else with write access -- was handed
# straight to the compiler because the existence check asked only whether a
# path was there. Reproduced: the store returned B under A's address and the
# build compiled B. The name is a CLAIM about the bytes; a claim from a
# shared location is untrusted input.
# The digest a content-addressed path CLAIMS, or empty when the path is not
# one of ours: `<64hex>-<name>` under the staging root, `g33-ovl-<64hex>.F`
# for the generated overlay.
addr_claim() {                      # path -> digest or ""
    local b; b=$(basename "$1")
    case "$1" in
        "$STAGE"/*) [[ "$b" =~ ^([0-9a-f]{64})- ]] && printf '%s' "${BASH_REMATCH[1]}" ;;
        *) [[ "$b" =~ ^g33-ovl-([0-9a-f]{64})\.F$ ]] && printf '%s' "${BASH_REMATCH[1]}" ;;
    esac
}
addr_verify() {                     # path, want-digest, what-for
    local p="$1" want="$2" what="$3" got
    [ ! -L "$p" ] || { echo "REFUSED: $what $p is a symlink; a content address must be the bytes, not a pointer to them" >&2; exit 2; }
    [ -f "$p" ]   || { echo "REFUSED: $what $p is not a regular file" >&2; exit 2; }
    got=$(shasum -a 256 "$p" | cut -d' ' -f1)
    [ "$got" = "$want" ] || {
        echo "REFUSED: $what $p holds ${got:0:12} but its address claims ${want:0:12}; the store is corrupt at this entry" >&2
        exit 2; }
}
# Install without clobbering, then verify UNCONDITIONALLY. `ln` reports
# success when the target is a DIRECTORY -- like `cp` and `mv` it then means
# "put it inside" -- so `if ln; then trust` accepted a directory sitting at a
# content address and returned it as the compile input (found by the probe
# list). Verifying whatever ends up at the address costs the same three lines
# and stops depending on which failure modes `ln` signals.
addr_install() {                    # tmp, dst, digest, what-for
    local tmp="$1" dst="$2" d="$3" what="$4"
    [ -e "$dst" ] || [ -L "$dst" ] || ln "$tmp" "$dst" 2>/dev/null || true
    rm -f "$tmp"
    addr_verify "$dst" "$d" "$what"
}
# Publishes into $STAGED rather than to stdout. It was called as
# `fc ... "$(stage "$SRC")"`, and a command substitution is a SUBSHELL: the
# `exit 2` above ended only the substitution, the script continued, and `fc`
# was handed an EMPTY last argument -- every refusal added here was
# unreachable from the one place that calls it (found by the probe list).
# Fail-closed logic cannot live behind `$( )`.
stage() {
    local src="$1" b tmp d dst
    b=$(basename "$src")
    tmp=$(mktemp "$STAGE/.staging.XXXXXX")
    cp "$src" "$tmp"
    d=$(shasum -a 256 "$tmp" | cut -d' ' -f1)
    dst="$STAGE/$d-$b"
    addr_install "$tmp" "$dst" "$d" "staged source"
    printf '%s\t%s\n' "$dst" "$src" >>"$STAGE_MAP"
    STAGED="$dst"
}

SRCLOG="$OUT/sources.txt"; : >"$SRCLOG"
fc() { local o="$1"; shift
       # The LOGICAL path with the digest of the bytes ACTUALLY COMPILED
       # (Codex): logging the logical path alone sent the collector back to
       # the host file, which is the very re-read staging exists to remove --
       # an edit between compile and collect would then record bytes the
       # compiler never saw. The name says what this source IS; the digest
       # says what was fed to the compiler, taken here, at that moment.
       local last="${@: -1}" logical sha claimed
       logical=$(awk -F'\t' -v k="$last" '$1==k{print $2}' "$STAGE_MAP" 2>/dev/null | tail -1)
       # A content-addressed input is checked against its own name BEFORE and
       # AFTER the compiler reads it (owner review §4): before, because the
       # store is shared; after, because "the entry was right when we looked"
       # is not "the entry was right when the compiler read it".
       claimed=$(addr_claim "$last")
       [ -z "$claimed" ] || addr_verify "$last" "$claimed" "compile input"
       sha=$(shasum -a 256 "$last" | cut -d' ' -f1)
       printf '%s\t%s\n' "${logical:-$last}" "$sha" >>"$SRCLOG"
       printf '%q ' "$FC" -c "$@" -J"$OUT" -I"$OUT" -o "$o" >>"$CMDLOG"; printf '\n' >>"$CMDLOG"
       "$FC" -c "$@" -J"$OUT" -I"$OUT" -o "$o" 2>"$o.err" \
        || { echo "COMPILE FAILED: $*"; head -25 "$o.err"; exit 1; }
       [ -z "$claimed" ] || addr_verify "$last" "$claimed" "compile input (after)"; }

stage "$FIXTURE_SRC"; FIXTURE_STAGED="$STAGED"
fc "$OUT/g33_fixture_v1.o"         "${DRIVER_FLAGS[@]}" "$STAGED"
stage "$HOST/frame/libmassv.F"
fc "$OUT/libmassv.o"               "${REF_FLAGS[@]}" "${CPP_FLAGS[@]}" "$STAGED"
stage "$HERE/stub_wrf_error.f90"
fc "$OUT/stub_wrf_error.o"         "${REF_FLAGS[@]}" "$STAGED"
stage "$HOST/share/module_model_constants.F"
fc "$OUT/module_model_constants.o" "${REF_FLAGS[@]}" "${CPP_FLAGS[@]}" "$STAGED"
stage "$HOST/phys/module_mp_radar.F"
fc "$OUT/module_mp_radar.o"        "${REF_FLAGS[@]}" "${CPP_FLAGS[@]}" "$STAGED"
# The PINNED module by default: this measures the reference operator, and
# instrumentation would otherwise be a second difference between sweep members.
# --dump swaps in the generated overlay, whose macro-OFF form is textually
# identical to the pinned source (the A/B/C non-invasiveness proof).
stage "$MODULE"; MODULE_STAGED="$STAGED"
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
    # ...copied BEFORE it is hashed, for the reason `stage` is (Codex): the
    # address has to be the digest of the bytes at the address.
    OVLTMP=$(mktemp "${TMPDIR:-/tmp}/g33-ovl.XXXXXX")
    cp "$OUT/module_mp_ovl.F" "$OVLTMP"
    OVLFULL=$(shasum -a 256 "$OVLTMP" | cut -d' ' -f1)
    # CONTENT-ADDRESSED on the FULL digest (owner §13 P1-4). A 16-hex truncation
    # left a real race: two builds whose overlays share a 64-bit prefix but
    # differ in content both see "no file", both write, and the loser's compile
    # can read the winner's source. With the whole digest in the name, same
    # digest means same content and different content means a different path,
    # so there is no collision to guard -- only a partial write, which the
    # temp-then-rename handles.
    MODULE_SRC="${TMPDIR:-/tmp}/g33-ovl-${OVLFULL}.F"
    addr_install "$OVLTMP" "$MODULE_SRC" "$OVLFULL" "staged overlay"
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
# ...and the driver is staged like every other compiled source. It was the one
# input read straight from the tree, so `fc` hashed it and the compiler read it
# again -- the window this staging exists to close, left open on the file that
# writes the window header (Codex).
stage "$HERE/g33_refine_driver.f90"; DRIVER_STAGED="$STAGED"
fc "$OUT/g33_refine_driver.o"      "${DRIVER_FLAGS[@]}" "${CPP_FLAGS[@]}" "-DKDM6_DTCLDCR=$DTCLDCR" ${DRVDEF[@]+"${DRVDEF[@]}"} ${DUMP_DEF[@]+"${DUMP_DEF[@]}"} \
                                   "$DRIVER_STAGED"
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
    "$MODULE_SRC" "$MODULE_STAGED" "$FIXTURE_STAGED"
echo "$OUT"
