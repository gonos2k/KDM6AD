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
fi
