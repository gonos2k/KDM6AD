#!/bin/bash
# Build the G3.3 self-check drivers: the qr/nr substep proof, the focused
# bottom-fall -> surface-precipitation proof, and the full-step C++ A/B/C
# non-invasiveness pair. Overlay objects replace the matching canonical archive
# members, so dladdr resolves the executable that actually contains the
# instrumented code.
#
# HERMETIC: `set -euo pipefail` + a FRESH output directory + fail-loud missing
# tools, so a stale mutant source/binary from a previous run can never be
# recompiled and mistaken for this run's evidence.
set -euo pipefail
cd "$(dirname "$0")/../.."

FM=libtorch/build/CMakeFiles/kdm6_c.dir/flags.make
AR=libtorch/build/libkdm6.a
if [ ! -f "$FM" ] || [ ! -f "$AR" ]; then
    echo "SKIP: configured libtorch build not found ($FM / $AR)"; exit 2
fi
DEFS=$(sed -n 's/^CXX_DEFINES = //p' "$FM")
INCS=$(sed -n 's/^CXX_INCLUDES = //p' "$FM")
FLGS=$(sed -n 's/^CXX_FLAGS = //p' "$FM")
CXX=$(xcrun -f c++ 2>/dev/null || command -v c++ || true)
[ -n "$CXX" ] || { echo "no C++ compiler (xcrun/c++ not found)" >&2; exit 2; }

TORCHLIB=$(python3 -c 'import pathlib, torch; print(pathlib.Path(torch.__file__).resolve().parent / "lib")' 2>/dev/null || true)
[ -n "$TORCHLIB" ] && [ -d "$TORCHLIB" ] || {
    echo "torch lib dir not found (is python3/torch installed?): '$TORCHLIB'" >&2; exit 2;
}

# On macOS force the SDK resolved by the live xcrun after flags.make's possibly
# stale -isysroot. Empty on Linux.
MACFLAGS=()
case "$(uname -s)" in
    Darwin) LIB_EXT=dylib
            SDK=$(xcrun --show-sdk-path 2>/dev/null || true)
            [ -n "$SDK" ] && MACFLAGS=(-isysroot "$SDK") ;;
    Linux)  LIB_EXT=so ;;
    *) echo "unsupported OS: $(uname -s)" >&2; exit 2 ;;
esac
TORCHLIBS=(
    "$TORCHLIB/libtorch.$LIB_EXT"
    "$TORCHLIB/libtorch_cpu.$LIB_EXT"
    "$TORCHLIB/libc10.$LIB_EXT"
)
for lib in "${TORCHLIBS[@]}"; do
    [ -f "$lib" ] || { echo "missing Torch library: $lib" >&2; exit 2; }
done

# Never delete a caller path. An explicit path must be absent; without one, own a
# private mktemp directory.
if [ -n "${1:-}" ]; then
    OUT=$1
    { [ -e "$OUT" ] || [ -L "$OUT" ]; } && {
        echo "output path already exists (refusing): $OUT" >&2; exit 2;
    }
    mkdir "$OUT"
else
    OUT=$(mktemp -d "${TMPDIR:-/tmp}/g33-selfcheck.XXXXXX")
fi

compile() {  # $1 src  $2 out.o
    # shellcheck disable=SC2086
    "$CXX" $DEFS -DKDM6_G33_OP_DUMP $FLGS $INCS -I harness/g33_overlay \
        "${MACFLAGS[@]}" -x c++ -c "$1" -o "$2" 2>"$2.err" \
        || { echo "COMPILE FAILED: $1"; head -30 "$2.err"; exit 1; }
}

link_substep_driver() {  # $1 sed.o  $2 sed_cons.o  $3 outdir  $4 label
    # shellcheck disable=SC2086
    "$CXX" $FLGS "${MACFLAGS[@]}" "$OUT/driver.o" "$1" "$2" "$AR" \
        "${TORCHLIBS[@]}" -Wl,-rpath,"$TORCHLIB" \
        -o "$3/selfcheck_driver" 2>"$3/link.err" \
        || { echo "LINK FAILED ($4)"; head -40 "$3/link.err"; exit 1; }
    echo "built: $3/selfcheck_driver ($4)"
}

link_surface_driver() {  # $1 sed.o  $2 sed_cons.o  $3 coord.o  $4 outdir  $5 label
    # shellcheck disable=SC2086
    "$CXX" $FLGS "${MACFLAGS[@]}" "$OUT/surface_driver.o" "$1" "$2" "$3" "$AR" \
        "${TORCHLIBS[@]}" -Wl,-rpath,"$TORCHLIB" \
        -o "$4/surface_selfcheck_driver" 2>"$4/surface_link.err" \
        || { echo "SURFACE LINK FAILED ($5)"; head -40 "$4/surface_link.err"; exit 1; }
    echo "built: $4/surface_selfcheck_driver ($5)"
}

link_abc_canonical() {
    # shellcheck disable=SC2086
    "$CXX" $FLGS "${MACFLAGS[@]}" "$OUT/abc_driver.o" "$AR" \
        "${TORCHLIBS[@]}" -Wl,-rpath,"$TORCHLIB" \
        -o "$OUT/abc_canonical_driver" 2>"$OUT/abc_canonical_link.err" \
        || { echo "ABC CANONICAL LINK FAILED"; head -40 "$OUT/abc_canonical_link.err"; exit 1; }
    echo "built: $OUT/abc_canonical_driver (A canonical)"
}

link_abc_diagnostic() {
    # The four overlay TUs define the production symbols before libkdm6.a is
    # searched, so the archive contributes their dependencies but not duplicate
    # canonical members. B and C are the SAME executable; only the environment
    # differs.
    # shellcheck disable=SC2086
    "$CXX" $FLGS "${MACFLAGS[@]}" "$OUT/abc_driver.o" \
        "$OUT/runtime.o" "$OUT/coord.o" "$OUT/sed.o" "$OUT/sed_cons.o" "$AR" \
        "${TORCHLIBS[@]}" -Wl,-rpath,"$TORCHLIB" \
        -o "$OUT/abc_diagnostic_driver" 2>"$OUT/abc_diagnostic_link.err" \
        || { echo "ABC DIAGNOSTIC LINK FAILED"; head -40 "$OUT/abc_diagnostic_link.err"; exit 1; }
    echo "built: $OUT/abc_diagnostic_driver (B/C diagnostic)"
}

SED=harness/g33_overlay/sedimentation.cpp.overlay
SED_CONS=harness/g33_overlay/sedimentation_conservative.cpp.overlay
COORD=harness/g33_overlay/coordinator.cpp.overlay
RUNTIME=harness/g33_overlay/runtime.cpp.overlay
MK=harness/g33_overlay/make_mutant.py

compile "$SED"                                          "$OUT/sed.o"
compile "$SED_CONS"                                     "$OUT/sed_cons.o"
compile harness/g33_overlay/selfcheck_driver.cpp         "$OUT/driver.o"
compile "$COORD"                                        "$OUT/coord.o"
compile harness/g33_overlay/surface_selfcheck_driver.cpp "$OUT/surface_driver.o"
compile "$RUNTIME"                                      "$OUT/runtime.o"
compile harness/g33_overlay/abc_driver.cpp               "$OUT/abc_driver.o"

link_substep_driver "$OUT/sed.o" "$OUT/sed_cons.o" "$OUT" "real"
link_surface_driver "$OUT/sed.o" "$OUT/sed_cons.o" "$OUT/coord.o" "$OUT" "surface real"
link_abc_canonical
link_abc_diagnostic

if [ "${2:-}" = "--with-mutant" ]; then
    M="$OUT/mutant"; mkdir "$M"
    python3 "$MK" shadow "$SED" "$M/sedimentation.cpp.overlay"
    compile "$M/sedimentation.cpp.overlay" "$M/sed.o"
    link_substep_driver "$M/sed.o" "$OUT/sed_cons.o" "$M" "shadow mutant"

    M2="$OUT/mutant_cons"; mkdir "$M2"
    python3 "$MK" cons_inflow "$SED_CONS" "$M2/sedimentation_conservative.cpp.overlay"
    compile "$M2/sedimentation_conservative.cpp.overlay" "$M2/sed_cons.o"
    link_substep_driver "$OUT/sed.o" "$M2/sed_cons.o" "$M2" "conservative inflow mutant"

    M3="$OUT/mutant_prevout"; mkdir "$M3"
    python3 "$MK" cons_prevout "$SED_CONS" "$M3/sedimentation_conservative.cpp.overlay"
    compile "$M3/sedimentation_conservative.cpp.overlay" "$M3/sed_cons.o"
    link_substep_driver "$OUT/sed.o" "$M3/sed_cons.o" "$M3" "conservative prev_out mutant"

    M4="$OUT/mutant_poststate"; mkdir "$M4"
    python3 "$MK" cons_poststate "$SED_CONS" "$M4/sedimentation_conservative.cpp.overlay"
    compile "$M4/sedimentation_conservative.cpp.overlay" "$M4/sed_cons.o"
    link_substep_driver "$OUT/sed.o" "$M4/sed_cons.o" "$M4" "conservative poststate mutant"

    M5="$OUT/mutant_fallacc"; mkdir "$M5"
    python3 "$MK" cons_fallacc "$SED_CONS" "$M5/sedimentation_conservative.cpp.overlay"
    compile "$M5/sedimentation_conservative.cpp.overlay" "$M5/sed_cons.o"
    link_substep_driver "$OUT/sed.o" "$M5/sed_cons.o" "$M5" "conservative fallacc mutant"

    MS1="$OUT/mutant_surface_omit_qi"; mkdir "$MS1"
    python3 "$MK" surface_omit_qi "$SED" "$MS1/sedimentation.cpp.overlay"
    compile "$MS1/sedimentation.cpp.overlay" "$MS1/sed.o"
    link_surface_driver "$MS1/sed.o" "$OUT/sed_cons.o" "$OUT/coord.o" "$MS1" \
        "surface omit-qi mutant"

    MS2="$OUT/mutant_surface_wrong_bottom"; mkdir "$MS2"
    python3 "$MK" surface_wrong_bottom "$COORD" "$MS2/coordinator.cpp.overlay"
    compile "$MS2/coordinator.cpp.overlay" "$MS2/coord.o"
    link_surface_driver "$OUT/sed.o" "$OUT/sed_cons.o" "$MS2/coord.o" "$MS2" \
        "surface wrong-bottom mutant"
fi
