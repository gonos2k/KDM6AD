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
# COVERAGE pin, not just rc: the mutant dies at k=0 no matter how much of the
# k-loop survives a refactor, so "real PASS + mutant FAIL" alone would stay
# green while 90% of the rungs silently left the check. The fixture is
# deterministic (B=3, K=4, mstepmax=2), so the exact counts are part of the
# contract: 16 shadow==actual (2 species x 4 k x 2 n) and 72 offline rungs
# ((5+4 FALK rungs) x 4 k x 2 n) per algorithm. Changing the fixture must
# change this line CONSCIOUSLY.
for algo in legacy conservative; do
    if ! echo "$real_out" | grep -q         "^$algo: PASS — 2 containers, 16 shadow==actual, 72 offline rungs bit-exact, 2 producer cross-checks$"; then
        echo "KILL GATE FAIL: $algo coverage drifted from the pinned counts:"
        echo "$real_out" | grep "^$algo:" || echo "  (no $algo line at all)"
        exit 1
    fi
done
if [ "$mut_rc" -eq 0 ]; then
    echo "KILL GATE FAIL: shadow mutant PASSED — the self-check is vacuous"
    exit 1
fi
# The EXPECTED kill, not any fidelity failure: the fixture is deterministic, so
# the first divergent rung is too — the gate that exists to prove first-
# divergence localization must demand the exact site it predicts.
EXPECTED_KILL="FAIL offline!=dumped: legacy L1_main_n2 k=0 qr QR_FALK.falk_precast"
case "$mut_out" in
    *"$EXPECTED_KILL"*) ;;
    *)
        echo "KILL GATE FAIL: mutant did not die at the predicted site (rc=$mut_rc):"
        echo "  expected: $EXPECTED_KILL"
        echo "$mut_out" | tail -3
        exit 1
        ;;
esac
echo "KILL GATE PASS: real=PASS with pinned coverage, mutant killed at the predicted site:"
echo "$mut_out" | tail -1
