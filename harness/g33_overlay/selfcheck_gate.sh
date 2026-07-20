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
# shellcheck disable=SC1091
source harness/g33_overlay/selfcheck_gate_lib.sh
OUT=${1:-/tmp/g33_selfcheck_build}

bash harness/g33_overlay/selfcheck_build.sh "$OUT" --with-mutant || exit $?

real_out=$(python3 harness/g33_selfcheck.py --driver "$OUT/selfcheck_driver" 2>&1)
real_rc=$?
mut_out=$(python3 harness/g33_selfcheck.py --driver "$OUT/mutant/selfcheck_driver" 2>&1)
mut_rc=$?
cons_out=$(python3 harness/g33_selfcheck.py --driver "$OUT/mutant_cons/selfcheck_driver" 2>&1)
cons_rc=$?
prevout_out=$(python3 harness/g33_selfcheck.py --driver "$OUT/mutant_prevout/selfcheck_driver" 2>&1)
prevout_rc=$?
poststate_out=$(python3 harness/g33_selfcheck.py --driver "$OUT/mutant_poststate/selfcheck_driver" 2>&1)
poststate_rc=$?
fallacc_out=$(python3 harness/g33_selfcheck.py --driver "$OUT/mutant_fallacc/selfcheck_driver" 2>&1)
fallacc_rc=$?

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
# contract, PER ALGORITHM: 16 shadow==actual and 72 FALK rungs both ways;
# INFLOW is conservative-only — 0 for legacy, 24 (3 interior/bottom cells x 4
# rho*dz rungs x 2 substeps) for conservative. Changing the fixture must change
# these lines CONSCIOUSLY.
# LADDER = OUTFLOW+FALLACC offline replay (PR B2.2 §5), conservative-only: per
# cell qr(3 outflow+3 fallacc)+nr(2 outflow+2 fallacc)=10, x 4 cells x 2 substeps
# = 80. Legacy stays 0 (that ladder's arithmetic differs and is not the G3.3-M
# path). INFLOW is 24; FALK 72 both ways.
LEGACY_LINE="legacy: PASS — 2 containers, 16 shadow==actual, 72 FALK + 0 INFLOW + 0 LADDER offline rungs bit-exact, 2 producer cross-checks"
CONS_LINE="conservative: PASS — 2 containers, 16 shadow==actual, 72 FALK + 24 INFLOW + 80 LADDER offline rungs bit-exact, 2 producer cross-checks"
for pin in "$LEGACY_LINE" "$CONS_LINE"; do
    if ! printf '%s\n' "$real_out" | grep -qF "$pin"; then
        echo "KILL GATE FAIL: coverage drifted from the pinned counts; missing:"
        echo "  $pin"
        printf '%s\n' "$real_out" | grep -E '^(legacy|conservative):'
        exit 1
    fi
done
if [ "$mut_rc" -eq 0 ]; then
    echo "KILL GATE FAIL: shadow mutant PASSED — the self-check is vacuous"
    exit 1
fi
# The EXPECTED kill, not any fidelity failure — and only the CONTROLLED one:
# the fixture is deterministic, so the first divergent rung is too, and the
# verdict (selfcheck_gate_lib.sh) demands rc==1 exactly, the predicted kill as
# the TERMINAL line, and no Python traceback. A substring match on any nonzero
# exit accepted a crash that happened to contain the line.
EXPECTED_KILL="FAIL offline!=dumped: legacy L1_main_n2 k=0 qr QR_FALK.falk_precast"
if ! why=$(verdict_mutant "$mut_out" "$mut_rc" "$EXPECTED_KILL"); then
    echo "KILL GATE FAIL: not the controlled predicted kill: $why"
    echo "$mut_out" | tail -3
    exit 1
fi
# MUTANT 2 — the conservative-ONLY rho*dz inflow. Killing this is what makes
# "the self-check observes the conservative-only operation" a claim with
# evidence, not just the shared FALK path (owner review). Predicted site is the
# first interior cell's inflow_final.
CONS_KILL="FAIL offline!=dumped: conservative L1_main_n1 k=1 qr QR_INFLOW.inflow_final"
if [ "$cons_rc" -eq 0 ]; then
    echo "KILL GATE FAIL: conservative inflow mutant PASSED — the INFLOW replay is vacuous"
    exit 1
fi
if ! why=$(verdict_mutant "$cons_out" "$cons_rc" "$CONS_KILL"); then
    echo "KILL GATE FAIL: conservative mutant not the controlled predicted kill: $why"
    echo "$cons_out" | tail -3
    exit 1
fi
# MUTANT 3 — the cross-record interface link (PR B2.1). The carried neighbour
# outflow is wrong, but every within-record recompute is self-consistent, so
# this can ONLY die at the causal-link check, not the offline replay. Predicted
# site is the first interior cell's QR interface link.
PREVOUT_KILL="FAIL causal-link: conservative L1_main_n1 k=1 prev_out != QR_OUTFLOW.dq_out(k-1)"
if [ "$prevout_rc" -eq 0 ]; then
    echo "KILL GATE FAIL: prev_out mutant PASSED — the causal-link layer is vacuous"
    exit 1
fi
if ! why=$(verdict_mutant "$prevout_out" "$prevout_rc" "$PREVOUT_KILL"); then
    echo "KILL GATE FAIL: prev_out mutant not the controlled predicted kill: $why"
    echo "$prevout_out" | tail -3
    exit 1
fi
# MUTANT 4 — the returned whole-field state link (PR B2.2 §2.1). The diagnostic
# q_post is correct and continuity is self-consistent, so this can ONLY die at
# the per-cell-q_post == substep_post link. Predicted site: first perturbed cell.
POSTSTATE_KILL="FAIL causal-link: conservative L1_main_n1 k=1 QR_UPDATE.q_post != substep_post.qr[:, k] (returned state diverged)"
if [ "$poststate_rc" -eq 0 ]; then
    echo "KILL GATE FAIL: poststate mutant PASSED — the returned-state link is vacuous"
    exit 1
fi
if ! why=$(verdict_mutant "$poststate_out" "$poststate_rc" "$POSTSTATE_KILL"); then
    echo "KILL GATE FAIL: poststate mutant not the controlled predicted kill: $why"
    echo "$poststate_out" | tail -3
    exit 1
fi
# MUTANT 5 — the OUTFLOW/FALLACC ladder (PR B2.2 §5). Outflow and state intact,
# so only the QR_FALLACC.fall_after offline replay can catch the perturbed
# accumulator. Predicted site: first cell.
FALLACC_KILL="FAIL offline!=dumped: conservative L1_main_n1 k=0 qr QR_FALLACC.fall_after"
if [ "$fallacc_rc" -eq 0 ]; then
    echo "KILL GATE FAIL: fallacc mutant PASSED — the OUTFLOW/FALLACC ladder is vacuous"
    exit 1
fi
if ! why=$(verdict_mutant "$fallacc_out" "$fallacc_rc" "$FALLACC_KILL"); then
    echo "KILL GATE FAIL: fallacc mutant not the controlled predicted kill: $why"
    echo "$fallacc_out" | tail -3
    exit 1
fi
echo "KILL GATE PASS: real=PASS with pinned coverage; all five mutants killed at their predicted sites:"
echo "  shadow:    $(echo "$mut_out" | grep -v '^(evidence' | tail -1)"
echo "  cons:      $(echo "$cons_out" | grep -v '^(evidence' | tail -1)"
echo "  prevout:   $(echo "$prevout_out" | grep -v '^(evidence' | tail -1)"
echo "  poststate: $(echo "$poststate_out" | grep -v '^(evidence' | tail -1)"
echo "  fallacc:   $(echo "$fallacc_out" | grep -v '^(evidence' | tail -1)"
