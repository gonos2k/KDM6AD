#!/bin/bash
# Build the C++ timestep-refinement driver (owner review §3).
#
# Separate from selfcheck_build.sh for the same reason the source is separate from
# abc_driver.cpp: that script builds the A/B/C DECISION drivers whose binary digest
# the bundle manifest anchors. This one links a different translation unit against
# the same canonical archive and writes no bundle, so a refinement run cannot be
# mistaken for, or contaminate, a decision artifact.
#
# Canonical archive only -- never the diagnostic overlay objects. The refinement
# measures the operator, and instrumentation would be a second difference between
# the members of a sweep.
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
FIXDEF=""
OUT=""
for a in "$@"; do
    case "$a" in
        --fixture=multisubcycle)    FIXDEF="-DKDM6_G33_FIXTURE_MULTISUBCYCLE" ;;
        --fixture=boundary_mapping) FIXDEF="-DKDM6_G33_FIXTURE_BOUNDARY_MAPPING" ;;
        --fixture=moisture_gradient) FIXDEF="-DKDM6_G33_FIXTURE_MOISTURE_GRADIENT" ;;
        --fixture=lc05_column)       FIXDEF="-DKDM6_G33_FIXTURE_LC05_COLUMN" ;;
        --fixture=*) echo "unknown --fixture: $a" >&2; exit 2 ;;
        --*) echo "unknown flag: $a" >&2; exit 2 ;;
        *) [ -z "$OUT" ] && OUT="$a" || { echo "unexpected arg: $a" >&2; exit 2; } ;;
    esac
done
CXX=$(xcrun -f c++ 2>/dev/null || command -v c++ || true)
[ -n "$CXX" ] || { echo "no C++ compiler" >&2; exit 2; }
TORCHLIB=$(python3 -c 'import pathlib, torch; print(pathlib.Path(torch.__file__).resolve().parent / "lib")' 2>/dev/null || true)
[ -n "$TORCHLIB" ] && [ -d "$TORCHLIB" ] || { echo "torch lib dir not found" >&2; exit 2; }
MACFLAGS=()
case "$(uname -s)" in
    Darwin) LIB_EXT=dylib; SDK=$(xcrun --show-sdk-path 2>/dev/null || true)
            [ -n "$SDK" ] && MACFLAGS=(-isysroot "$SDK") ;;
    Linux)  LIB_EXT=so ;;
    *) echo "unsupported OS: $(uname -s)" >&2; exit 2 ;;
esac
TORCHLIBS=("$TORCHLIB/libtorch.$LIB_EXT" "$TORCHLIB/libtorch_cpu.$LIB_EXT"
           "$TORCHLIB/libc10.$LIB_EXT" "$TORCHLIB/libc10.$LIB_EXT")
for lib in "${TORCHLIBS[@]}"; do [ -f "$lib" ] || { echo "missing: $lib" >&2; exit 2; }; done
[ -n "$OUT" ] || OUT=$(mktemp -d "${TMPDIR:-/tmp}/g33-refine-cpp.XXXXXX")
[ -d "$OUT" ] || mkdir -p "$OUT"

# shellcheck disable=SC2086
"$CXX" $DEFS $INCS $FLGS "${MACFLAGS[@]}" $FIXDEF \
    -Iharness/g33_overlay -c harness/g33_overlay/g33_refine_driver.cpp \
    -o "$OUT/g33_refine_driver.o" 2>"$OUT/compile.err" \
    || { echo "REFINE COMPILE FAILED"; head -40 "$OUT/compile.err"; exit 1; }
# shellcheck disable=SC2086
"$CXX" $FLGS "${MACFLAGS[@]}" "$OUT/g33_refine_driver.o" "$AR" \
    "${TORCHLIBS[@]}" -Wl,-rpath,"$TORCHLIB" -o "$OUT/g33_refine_driver" \
    2>"$OUT/link.err" || { echo "REFINE LINK FAILED"; head -40 "$OUT/link.err"; exit 1; }
echo "$OUT"
