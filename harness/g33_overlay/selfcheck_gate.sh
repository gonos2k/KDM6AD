#!/bin/bash
# The ENFORCED standing kill gate for the §5a self-check.
#
# selfcheck_build.sh --with-mutant only BUILDS the shadow mutant; nothing there
# runs the pair or requires an outcome — the "gate" existed as a one-off shell
# loop in a session transcript, which is exactly how a falsification stops
# protecting anything. This script is the committed enforcement:
#
#   real driver   -> self-check must PASS (rc 0)
#   shadow mutant -> self-check must FAIL, and for the RIGHT reason: a
#                    fidelity mismatch (offline!=dumped or shadow!=actual),
#                    never a SKIP, a crash, or a configuration error. A mutant
#                    "killed" by rc alone could be a missing file.
set -u
cd "$(dirname "$0")/../.."
OUT=${1:-/tmp/g33_selfcheck_build}

bash harness/g33_overlay/selfcheck_build.sh "$OUT" --with-mutant || exit $?

real_out=$(python3 harness/g33_selfcheck.py --driver "$OUT/selfcheck_driver" 2>&1)
real_rc=$?
mut_out=$(python3 harness/g33_selfcheck.py --driver "$OUT/mutant/selfcheck_driver" 2>&1)
mut_rc=$?

echo "$real_out" | tail -3
if [ "$real_rc" -ne 0 ]; then
    echo "KILL GATE FAIL: real driver did not PASS (rc=$real_rc)"
    echo "$real_out" | tail -5
    exit 1
fi
if [ "$mut_rc" -eq 0 ]; then
    echo "KILL GATE FAIL: shadow mutant PASSED — the self-check is vacuous"
    exit 1
fi
case "$mut_out" in
    *"FAIL offline!=dumped"* | *"FAIL shadow!=actual"*) ;;
    *)
        echo "KILL GATE FAIL: mutant failed for the WRONG reason (rc=$mut_rc):"
        echo "$mut_out" | tail -5
        exit 1
        ;;
esac
echo "KILL GATE PASS: real=PASS, mutant killed by fidelity check:"
echo "$mut_out" | tail -1
