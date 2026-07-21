#!/bin/bash
# Build the G3.3 self-check driver: overlay TUs + driver, linked so the overlay
# objects REPLACE the canonical archive members (an archive member is only
# pulled for an undefined symbol; the overlay objects define those symbols
# first). The result is one executable that CONTAINS the instrumented code, so
# the dladdr binding resolves the artifact the evidence must describe.
#
# HERMETIC: `set -euo pipefail` + a FRESH output directory + fail-loud missing
# tools, so a stale mutant source/binary from a previous run can never be
# recompiled and mistaken for this run's evidence (a false-green path).
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

# Torch lib dir straight from the interpreter (works for site-/dist-packages and
# other layouts), not by parsing CMake include flags. It is the same torch the
# CMake configure used (-DCMAKE_PREFIX_PATH came from this interpreter).
# `|| true` so a missing python3/torch does not trip `set -e` before the check
# below — otherwise the helpful message is dead code.
TORCHLIB=$(python3 -c 'import pathlib, torch; print(pathlib.Path(torch.__file__).resolve().parent / "lib")' 2>/dev/null || true)
[ -n "$TORCHLIB" ] && [ -d "$TORCHLIB" ] || { echo "torch lib dir not found (is python3/torch installed?): '$TORCHLIB'" >&2; exit 2; }

# Supported OSes are ENUMERATED fail-loud, not "everything that is not macOS is
# .so" — an unexpected platform is an explicit error, not a wrong default.
# MACFLAGS: on macOS pass the CURRENT SDK sysroot explicitly. flags.make's
# CXX_FLAGS carry an -isysroot, but on a CI runner it can point at a different /
# stale SDK than `xcrun -f c++` resolves — the observed failure was libc++'s
# <cstddef> not found. Appending our -isysroot AFTER $FLGS makes clang use the
# live SDK (last -isysroot wins). Empty on Linux.
MACFLAGS=()
case "$(uname -s)" in
    Darwin) LIB_EXT=dylib
            SDK=$(xcrun --show-sdk-path 2>/dev/null || true)
            [ -n "$SDK" ] && MACFLAGS=(-isysroot "$SDK") ;;
    Linux)  LIB_EXT=so ;;
    *) echo "unsupported OS: $(uname -s)" >&2; exit 2 ;;
esac
# Bash array (not a space-joined string) so a TORCHLIB path with spaces stays one
# argument per lib under "${TORCHLIBS[@]}".
TORCHLIBS=(
    "$TORCHLIB/libtorch.$LIB_EXT"
    "$TORCHLIB/libtorch_cpu.$LIB_EXT"
    "$TORCHLIB/libc10.$LIB_EXT"
)
for lib in "${TORCHLIBS[@]}"; do
    [ -f "$lib" ] || { echo "missing Torch library: $lib" >&2; exit 2; }
done

# FRESH, owned output directory — NEVER destructive. An explicit path must not
# already exist (we create and own it, so no stale artifact can survive into
# this run); with no argument we make a private mktemp dir. This removes the
# `rm -rf` entirely (and with it every path-normalization / symlink-bypass
# concern) while still guaranteeing a clean build tree.
if [ -n "${1:-}" ]; then
    OUT=$1
    [ -e "$OUT" ] && { echo "output path already exists (refusing): $OUT" >&2; exit 2; }
    mkdir -p "$OUT"
else
    OUT=$(mktemp -d "${TMPDIR:-/tmp}/g33-selfcheck.XXXXXX")
fi

compile() {  # $1 src  $2 out.o
    # shellcheck disable=SC2086
    "$CXX" $DEFS -DKDM6_G33_OP_DUMP $FLGS $INCS -I harness/g33_overlay \
        "${MACFLAGS[@]}" -x c++ -c "$1" -o "$2" 2>"$2.err" \
        || { echo "COMPILE FAILED: $1"; head -15 "$2.err"; exit 1; }
}

link_driver() {  # $1 sed.o  $2 sed_cons.o  $3 outdir  $4 label
    # shellcheck disable=SC2086
    "$CXX" $FLGS "$OUT/driver.o" "$1" "$2" "$AR" \
        "${TORCHLIBS[@]}" \
        -Wl,-rpath,"$TORCHLIB" -o "$3/selfcheck_driver" 2>"$3/link.err" \
        || { echo "LINK FAILED ($4)"; head -20 "$3/link.err"; exit 1; }
    echo "built: $3/selfcheck_driver ($4)"
}

compile harness/g33_overlay/sedimentation.cpp.overlay              "$OUT/sed.o"
compile harness/g33_overlay/sedimentation_conservative.cpp.overlay "$OUT/sed_cons.o"
compile harness/g33_overlay/selfcheck_driver.cpp                   "$OUT/driver.o"

link_driver "$OUT/sed.o" "$OUT/sed_cons.o" "$OUT" "real"

# ── standing mutation kill (owner kill-table: "shadow expression 변경") ───────
# With --with-mutant, additionally build one driver per mutant and require the
# self-check to FAIL on each at its predicted site. A self-check that cannot kill
# a mutant is vacuous. make_mutant.py exits non-zero (→ set -e aborts here) if an
# anchor count drifts, so a silently-vacuous mutant cannot slip through.
if [ "${2:-}" = "--with-mutant" ]; then
    MK=harness/g33_overlay/make_mutant.py
    SED=harness/g33_overlay/sedimentation.cpp.overlay
    SED_CONS=harness/g33_overlay/sedimentation_conservative.cpp.overlay

    # MUTANT 1 — legacy SHADOW ladder drops the gate rung (shared FALK proof).
    M="$OUT/mutant"; mkdir "$M"
    python3 "$MK" shadow "$SED" "$M/sedimentation.cpp.overlay"
    compile "$M/sedimentation.cpp.overlay" "$M/sed.o"
    link_driver "$M/sed.o" "$OUT/sed_cons.o" "$M" "shadow mutant"

    # MUTANT 2 — conservative INFLOW drops /dst_metric: the rho*dz interface
    # transfer that is conservative-ONLY, the load-bearing G3.3-M operation.
    M2="$OUT/mutant_cons"; mkdir "$M2"
    python3 "$MK" cons_inflow "$SED_CONS" "$M2/sedimentation_conservative.cpp.overlay"
    compile "$M2/sedimentation_conservative.cpp.overlay" "$M2/sed_cons.o"
    link_driver "$OUT/sed.o" "$M2/sed_cons.o" "$M2" "conservative inflow mutant"

    # MUTANT 3 — conservative carries the WRONG neighbour outflow into the next
    # cell's inflow (s->prev_out *= 1.03125). Every within-record recompute stays
    # self-consistent; only the cross-record interface link can catch it.
    M3="$OUT/mutant_prevout"; mkdir "$M3"
    python3 "$MK" cons_prevout "$SED_CONS" "$M3/sedimentation_conservative.cpp.overlay"
    compile "$M3/sedimentation_conservative.cpp.overlay" "$M3/sed_cons.o"
    link_driver "$OUT/sed.o" "$M3/sed_cons.o" "$M3" "conservative prev_out mutant"

    # MUTANT 4 — conservative returns a WRONG whole-field column (qr.cols[1] *=
    # 1.03125) after the per-cell op records are written. Only the per-cell-q_post
    # == substep_post link (PR B2.2 §2.1) can catch it.
    M4="$OUT/mutant_poststate"; mkdir "$M4"
    python3 "$MK" cons_poststate "$SED_CONS" "$M4/sedimentation_conservative.cpp.overlay"
    compile "$M4/sedimentation_conservative.cpp.overlay" "$M4/sed_cons.o"
    link_driver "$OUT/sed.o" "$M4/sed_cons.o" "$M4" "conservative poststate mutant"

    # MUTANT 5 — conservative fall accumulator perturbed (s->fall *= 1.03125).
    # Outflow and state intact, so only the §5 QR_FALLACC.fall_after replay catches it.
    M5="$OUT/mutant_fallacc"; mkdir "$M5"
    python3 "$MK" cons_fallacc "$SED_CONS" "$M5/sedimentation_conservative.cpp.overlay"
    compile "$M5/sedimentation_conservative.cpp.overlay" "$M5/sed_cons.o"
    link_driver "$OUT/sed.o" "$M5/sed_cons.o" "$M5" "conservative fallacc mutant"
fi
