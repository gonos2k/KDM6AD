#!/bin/bash
# G3.3 overlay compile smoke + macro-off OBJECT equivalence.
#
# Two gates per instrumented TU, using the EXACT flags of the real kdm6_c build
# (parsed from the CMake flags.make so this cannot drift from what ships):
#
#   1) The overlay must COMPILE with -DKDM6_G33_OP_DUMP — the diagnostic build.
#      The textual 4-check cannot see a C++ error; before this script the three
#      overlay TUs had never been compiled at all.
#
#   2) With the macro OFF, the overlay's object must equal the canonical
#      object. Both are compiled from the SAME path so __FILE__ cannot differ.
#      Direct identity can still fail for one benign reason: the g33 blocks
#      occupy source lines even when compiled out, and TORCH_CHECK materializes
#      __LINE__ as an integer immediate in __text, so every check AFTER an
#      insertion shifts. The line-shift proof disambiguates: compile the
#      CANONICAL text laid out with the overlay's blank lines — if THAT object
#      is byte-identical to the macro-off overlay object, the difference is
#      line numbering and nothing else; anything less is a FAIL.
#
# This is a build-level gate, not a run-level one: non-invasiveness of the
# ENABLED instrumentation is still established only by the 3-way A/B/C output
# equality (protocol §10).
set -u
cd "$(dirname "$0")/../.."

FM=libtorch/build/CMakeFiles/kdm6_c.dir/flags.make
if [ ! -f "$FM" ]; then
    echo "SKIP: $FM not found — configure the libtorch build first"; exit 2
fi
DEFS=$(sed -n 's/^CXX_DEFINES = //p' "$FM")
INCS=$(sed -n 's/^CXX_INCLUDES = //p' "$FM")
FLGS=$(sed -n 's/^CXX_FLAGS = //p' "$FM")
CXX=$(xcrun -f c++ 2>/dev/null || command -v c++)
W=$(mktemp -d /tmp/g33_compile_smoke.XXXXXX)
trap 'rm -rf "$W"' EXIT

compile() {   # $1 src  $2 out.o  $3 extra defines
    # shellcheck disable=SC2086
    "$CXX" $DEFS $3 $FLGS $INCS -I harness/g33_overlay \
        -x c++ -c "$1" -o "$2" 2>"$2.err"
}

rc=0
for tu in sedimentation sedimentation_conservative runtime coordinator; do
    ovl="harness/g33_overlay/$tu.cpp.overlay"
    canon="libtorch/src/$tu.cpp"

    if compile "$ovl" "$W/on.o" "-DKDM6_G33_OP_DUMP"; then
        echo "$tu: macro-ON compiles"
    else
        echo "$tu: macro-ON COMPILE FAILED"; head -15 "$W/on.o.err"; rc=1; continue
    fi

    cp "$canon" "$W/$tu.cpp"
    compile "$W/$tu.cpp" "$W/canon.o" "" || { echo "$tu: canonical COMPILE FAILED"; rc=1; continue; }
    cp "$ovl" "$W/$tu.cpp"
    compile "$W/$tu.cpp" "$W/off.o" "" || { echo "$tu: macro-off COMPILE FAILED"; head -15 "$W/off.o.err"; rc=1; continue; }

    if cmp -s "$W/canon.o" "$W/off.o"; then
        echo "$tu: macro-OFF object IDENTICAL to canonical"
        continue
    fi
    # line-shift proof: canonical text in the overlay's line layout
    python3 - "$ovl" "$canon" "$W/$tu.cpp" <<'PY' || { echo "$tu: line-shift construction failed"; exit 1; }
import re, sys
ovl, canon, out = sys.argv[1:4]
s = open(ovl).read()
shifted = re.sub(r'#ifdef KDM6_G33_OP_DUMP.*?#endif[^\n]*',
                 lambda m: '\n' * m.group(0).count('\n'), s, flags=re.S)
c = open(canon).read()
# the shifted text must BE the canonical text modulo blank lines, or the
# "proof" would be comparing against something other than the canonical TU
assert [l for l in shifted.splitlines() if l.strip()] == \
       [l for l in c.splitlines() if l.strip()], "non-blank drift vs canonical"
open(out, 'w').write(shifted)
PY
    compile "$W/$tu.cpp" "$W/shift.o" "" || { echo "$tu: shifted COMPILE FAILED"; rc=1; continue; }
    if cmp -s "$W/shift.o" "$W/off.o"; then
        echo "$tu: macro-OFF object differs from canonical ONLY by __LINE__ (line-shift proven)"
    else
        echo "$tu: macro-OFF object differs BEYOND line numbering — FAIL"; rc=1
    fi
done
exit $rc
