#!/bin/bash
# Build the G3.3 self-check driver: overlay TUs + driver, linked so the overlay
# objects REPLACE the canonical archive members (an archive member is only
# pulled for an undefined symbol; the overlay objects define those symbols
# first). The result is one executable that CONTAINS the instrumented code, so
# the dladdr binding resolves the artifact the evidence must describe.
set -u
cd "$(dirname "$0")/../.."

FM=libtorch/build/CMakeFiles/kdm6_c.dir/flags.make
AR=libtorch/build/libkdm6.a
if [ ! -f "$FM" ] || [ ! -f "$AR" ]; then
    echo "SKIP: configured libtorch build not found ($FM / $AR)"; exit 2
fi
DEFS=$(sed -n 's/^CXX_DEFINES = //p' "$FM")
INCS=$(sed -n 's/^CXX_INCLUDES = //p' "$FM")
FLGS=$(sed -n 's/^CXX_FLAGS = //p' "$FM")
CXX=$(xcrun -f c++ 2>/dev/null || command -v c++)
if [ -z "$CXX" ]; then echo "no C++ compiler (xcrun/c++ not found)"; exit 2; fi
TORCHLIB=$(echo "$INCS" | tr ' ' '\n' | sed -n 's|^/|/|p' | grep 'site-packages/torch/include$' | head -1 | sed 's|/include$|/lib|')
OUT=${1:-/tmp/g33_selfcheck_build}
mkdir -p "$OUT"

compile() {  # $1 src  $2 out.o
    # shellcheck disable=SC2086
    "$CXX" $DEFS -DKDM6_G33_OP_DUMP $FLGS $INCS -I harness/g33_overlay \
        -x c++ -c "$1" -o "$2" 2>"$2.err" || { echo "COMPILE FAILED: $1"; head -15 "$2.err"; exit 1; }
}
compile harness/g33_overlay/sedimentation.cpp.overlay              "$OUT/sed.o"
compile harness/g33_overlay/sedimentation_conservative.cpp.overlay "$OUT/sed_cons.o"
compile harness/g33_overlay/selfcheck_driver.cpp                   "$OUT/driver.o"

# shellcheck disable=SC2086
"$CXX" $FLGS "$OUT/driver.o" "$OUT/sed.o" "$OUT/sed_cons.o" "$AR" \
    "$TORCHLIB/libtorch.dylib" "$TORCHLIB/libtorch_cpu.dylib" "$TORCHLIB/libc10.dylib" \
    -Wl,-rpath,"$TORCHLIB" -o "$OUT/selfcheck_driver" 2>"$OUT/link.err" \
    || { echo "LINK FAILED"; head -20 "$OUT/link.err"; exit 1; }
echo "built: $OUT/selfcheck_driver"

# ── standing mutation kill (owner kill-table: "shadow expression 변경") ───────
# With --with-mutant, additionally build a driver whose SHADOW ladder drops the
# gate rung, and require the self-check to FAIL on it. A self-check that cannot
# kill this mutant is vacuous. The kill lands exactly where the gate first
# matters (n=2, the mstep=1 column) — the first divergent rung, localized.
if [ "${2:-}" = "--with-mutant" ]; then
    MK=harness/g33_overlay/make_mutant.py
    # MUTANT 1 — legacy SHADOW ladder drops the gate rung (shared FALK proof).
    M="$OUT/mutant"; mkdir -p "$M"
    python3 "$MK" shadow harness/g33_overlay/sedimentation.cpp.overlay \
        "$M/sedimentation.cpp.overlay"
    compile "$M/sedimentation.cpp.overlay" "$M/sed.o"
    # shellcheck disable=SC2086
    "$CXX" $FLGS "$OUT/driver.o" "$M/sed.o" "$OUT/sed_cons.o" "$AR" \
        "$TORCHLIB/libtorch.dylib" "$TORCHLIB/libtorch_cpu.dylib" "$TORCHLIB/libc10.dylib" \
        -Wl,-rpath,"$TORCHLIB" -o "$M/selfcheck_driver" 2>"$M/link.err" \
        || { echo "MUTANT LINK FAILED"; head -10 "$M/link.err"; exit 1; }
    echo "built: $M/selfcheck_driver (shadow mutant)"

    # MUTANT 2 — conservative INFLOW drops /dst_metric: the rho*dz interface
    # transfer that is conservative-ONLY, the load-bearing G3.3-M operation.
    M2="$OUT/mutant_cons"; mkdir -p "$M2"
    python3 "$MK" cons_inflow \
        harness/g33_overlay/sedimentation_conservative.cpp.overlay \
        "$M2/sedimentation_conservative.cpp.overlay"
    compile "$M2/sedimentation_conservative.cpp.overlay" "$M2/sed_cons.o"
    # shellcheck disable=SC2086
    "$CXX" $FLGS "$OUT/driver.o" "$OUT/sed.o" "$M2/sed_cons.o" "$AR" \
        "$TORCHLIB/libtorch.dylib" "$TORCHLIB/libtorch_cpu.dylib" "$TORCHLIB/libc10.dylib" \
        -Wl,-rpath,"$TORCHLIB" -o "$M2/selfcheck_driver" 2>"$M2/link.err" \
        || { echo "MUTANT2 LINK FAILED"; head -10 "$M2/link.err"; exit 1; }
    echo "built: $M2/selfcheck_driver (conservative inflow mutant)"

    # MUTANT 3 — conservative carries the WRONG neighbour outflow into the next
    # cell's inflow (s->prev_out *= 1.03125). Every within-record recompute stays
    # self-consistent; only the cross-record interface link can catch it. Proves
    # the causal-link layer (PR B2.1) is not vacuous.
    M3="$OUT/mutant_prevout"; mkdir -p "$M3"
    python3 "$MK" cons_prevout \
        harness/g33_overlay/sedimentation_conservative.cpp.overlay \
        "$M3/sedimentation_conservative.cpp.overlay"
    compile "$M3/sedimentation_conservative.cpp.overlay" "$M3/sed_cons.o"
    # shellcheck disable=SC2086
    "$CXX" $FLGS "$OUT/driver.o" "$OUT/sed.o" "$M3/sed_cons.o" "$AR" \
        "$TORCHLIB/libtorch.dylib" "$TORCHLIB/libtorch_cpu.dylib" "$TORCHLIB/libc10.dylib" \
        -Wl,-rpath,"$TORCHLIB" -o "$M3/selfcheck_driver" 2>"$M3/link.err" \
        || { echo "MUTANT3 LINK FAILED"; head -10 "$M3/link.err"; exit 1; }
    echo "built: $M3/selfcheck_driver (conservative prev_out mutant)"

    # MUTANT 4 — conservative returns a WRONG whole-field column (qr.cols[1] *=
    # 1.03125) after the per-cell op records are written. Diagnostic q_post is
    # correct; the returned state (== substep_post == next pre) is wrong, so only
    # the per-cell-q_post == substep_post link (PR B2.2 §2.1) can catch it.
    M4="$OUT/mutant_poststate"; mkdir -p "$M4"
    python3 "$MK" cons_poststate \
        harness/g33_overlay/sedimentation_conservative.cpp.overlay \
        "$M4/sedimentation_conservative.cpp.overlay"
    compile "$M4/sedimentation_conservative.cpp.overlay" "$M4/sed_cons.o"
    # shellcheck disable=SC2086
    "$CXX" $FLGS "$OUT/driver.o" "$OUT/sed.o" "$M4/sed_cons.o" "$AR" \
        "$TORCHLIB/libtorch.dylib" "$TORCHLIB/libtorch_cpu.dylib" "$TORCHLIB/libc10.dylib" \
        -Wl,-rpath,"$TORCHLIB" -o "$M4/selfcheck_driver" 2>"$M4/link.err" \
        || { echo "MUTANT4 LINK FAILED"; head -10 "$M4/link.err"; exit 1; }
    echo "built: $M4/selfcheck_driver (conservative poststate mutant)"

    # MUTANT 5 — conservative fall accumulator perturbed (s->fall *= 1.03125).
    # Outflow and state are intact, so only the §5 QR_FALLACC.fall_after offline
    # replay can catch it. Proves the OUTFLOW/FALLACC ladder is not vacuous.
    M5="$OUT/mutant_fallacc"; mkdir -p "$M5"
    python3 "$MK" cons_fallacc \
        harness/g33_overlay/sedimentation_conservative.cpp.overlay \
        "$M5/sedimentation_conservative.cpp.overlay"
    compile "$M5/sedimentation_conservative.cpp.overlay" "$M5/sed_cons.o"
    # shellcheck disable=SC2086
    "$CXX" $FLGS "$OUT/driver.o" "$OUT/sed.o" "$M5/sed_cons.o" "$AR" \
        "$TORCHLIB/libtorch.dylib" "$TORCHLIB/libtorch_cpu.dylib" "$TORCHLIB/libc10.dylib" \
        -Wl,-rpath,"$TORCHLIB" -o "$M5/selfcheck_driver" 2>"$M5/link.err" \
        || { echo "MUTANT5 LINK FAILED"; head -10 "$M5/link.err"; exit 1; }
    echo "built: $M5/selfcheck_driver (conservative fallacc mutant)"
fi
