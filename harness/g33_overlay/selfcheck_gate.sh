#!/bin/bash
# Enforced G3.3-M gate.
#
# The main driver proves the qr/nr substep operator. The focused surface driver
# proves the final bottom-fall -> precipitation path. The full-step A/B/C pair
# then proves that the diagnostic overlay is non-invasive with env absent and
# active. Real drivers must pass; each mutant must fail at its predicted site —
# never because of a build error, SKIP, crash, or malformed evidence.
set -u
cd "$(dirname "$0")/../.."
# shellcheck disable=SC1091
source harness/g33_overlay/selfcheck_gate_lib.sh

# Callers may provide a fresh runner-owned path for artifact collection. Without
# one, use a private temp dir and remove it only on success; failures retain all
# build errors, mutant sources/binaries, and evidence.
if [ -n "${1:-}" ]; then
    OUT=$1
else
    _gate_tmp=$(mktemp -d "${TMPDIR:-/tmp}/g33-gate.XXXXXX")
    OUT="$_gate_tmp/out"
    trap '[ "$?" -eq 0 ] && rm -rf "$_gate_tmp"' EXIT
fi

bash harness/g33_overlay/selfcheck_build.sh "$OUT" --with-mutant || exit $?

# ── Main qr/nr substep proof ─────────────────────────────────────────────────
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
    echo "KILL GATE FAIL: real substep driver did not PASS (rc=$real_rc)"
    echo "$real_out" | tail -8
    exit 1
fi

LEGACY_LINE="legacy: PASS — 2 containers, 16 shadow==actual, 72 FALK + 0 INFLOW + 0 LADDER offline rungs bit-exact, 2 producer cross-checks"
CONS_LINE="conservative: PASS — 2 containers, 16 shadow==actual, 72 FALK + 24 INFLOW + 80 LADDER offline rungs bit-exact, 2 producer cross-checks"
for pin in "$LEGACY_LINE" "$CONS_LINE"; do
    if ! printf '%s\n' "$real_out" | grep -qF "$pin"; then
        echo "KILL GATE FAIL: substep coverage drifted; missing:"
        echo "  $pin"
        printf '%s\n' "$real_out" | grep -E '^(legacy|conservative):'
        exit 1
    fi
done

EXPECTED_KILL="FAIL offline!=dumped: legacy L1_main_n2 k=0 qr QR_FALK.falk_precast"
if ! why=$(verdict_mutant "$mut_out" "$mut_rc" "$EXPECTED_KILL"); then
    echo "KILL GATE FAIL: shadow mutant not the controlled predicted kill: $why"
    echo "$mut_out" | tail -5
    exit 1
fi
CONS_KILL="FAIL offline!=dumped: conservative L1_main_n1 k=1 qr QR_INFLOW.inflow_final"
if ! why=$(verdict_mutant "$cons_out" "$cons_rc" "$CONS_KILL"); then
    echo "KILL GATE FAIL: conservative inflow mutant not the predicted kill: $why"
    echo "$cons_out" | tail -5
    exit 1
fi
PREVOUT_KILL="FAIL causal-link: conservative L1_main_n1 k=1 prev_out != QR_OUTFLOW.dq_out(k-1)"
if ! why=$(verdict_mutant "$prevout_out" "$prevout_rc" "$PREVOUT_KILL"); then
    echo "KILL GATE FAIL: prev_out mutant not the predicted kill: $why"
    echo "$prevout_out" | tail -5
    exit 1
fi
POSTSTATE_KILL="FAIL causal-link: conservative L1_main_n1 k=1 QR_UPDATE.q_post != substep_post.qr[:, k] (returned state diverged)"
if ! why=$(verdict_mutant "$poststate_out" "$poststate_rc" "$POSTSTATE_KILL"); then
    echo "KILL GATE FAIL: poststate mutant not the predicted kill: $why"
    echo "$poststate_out" | tail -5
    exit 1
fi
FALLACC_KILL="FAIL offline!=dumped: conservative L1_main_n1 k=0 qr QR_FALLACC.fall_after"
if ! why=$(verdict_mutant "$fallacc_out" "$fallacc_rc" "$FALLACC_KILL"); then
    echo "KILL GATE FAIL: fallacc mutant not the predicted kill: $why"
    echo "$fallacc_out" | tail -5
    exit 1
fi

# ── Focused bottom-fall -> surface proof ──────────────────────────────────────
surface_out=$(python3 harness/g33_surface_selfcheck.py \
    --driver "$OUT/surface_selfcheck_driver" --algorithm both 2>&1)
surface_rc=$?
surface_omit_out=$(python3 harness/g33_surface_selfcheck.py \
    --driver "$OUT/mutant_surface_omit_qi/surface_selfcheck_driver" \
    --algorithm conservative 2>&1)
surface_omit_rc=$?
surface_bottom_out=$(python3 harness/g33_surface_selfcheck.py \
    --driver "$OUT/mutant_surface_wrong_bottom/surface_selfcheck_driver" \
    --algorithm conservative 2>&1)
surface_bottom_rc=$?

echo "$surface_out" | tail -3
if [ "$surface_rc" -ne 0 ]; then
    echo "KILL GATE FAIL: real surface driver did not PASS (rc=$surface_rc)"
    echo "$surface_out" | tail -8
    exit 1
fi
SURFACE_LEGACY="legacy: SURFACE PASS — 3 containers, qr bottom link + 9 fields bit-exact"
SURFACE_CONS="conservative: SURFACE PASS — 3 containers, qr bottom link + 9 fields bit-exact"
for pin in "$SURFACE_LEGACY" "$SURFACE_CONS" "SURFACE SELF-CHECK PASS"; do
    if ! printf '%s\n' "$surface_out" | grep -qF "$pin"; then
        echo "KILL GATE FAIL: surface coverage drifted; missing: $pin"
        echo "$surface_out" | tail -8
        exit 1
    fi
done

SURFACE_OMIT_KILL="FAIL surface-offline: conservative L1_surface rain_increment"
if ! why=$(verdict_mutant "$surface_omit_out" "$surface_omit_rc" "$SURFACE_OMIT_KILL"); then
    echo "KILL GATE FAIL: surface omit-qi mutant not the predicted kill: $why"
    echo "$surface_omit_out" | tail -5
    exit 1
fi
SURFACE_BOTTOM_KILL="FAIL surface-link: conservative L1_surface bottom_fall_qr != L1_main_n2 QR_FALLACC(k=3).fall_after"
if ! why=$(verdict_mutant "$surface_bottom_out" "$surface_bottom_rc" "$SURFACE_BOTTOM_KILL"); then
    echo "KILL GATE FAIL: surface wrong-bottom mutant not the predicted kill: $why"
    echo "$surface_bottom_out" | tail -5
    exit 1
fi

# ── Full-step C++ A/B/C non-invasiveness ─────────────────────────────────────
abc_out=$(python3 harness/g33_abc_noninvasiveness.py \
    --canonical-driver "$OUT/abc_canonical_driver" \
    --diagnostic-driver "$OUT/abc_diagnostic_driver" 2>&1)
abc_rc=$?
echo "$abc_out" | tail -5
if [ "$abc_rc" -ne 0 ]; then
    echo "ABC GATE FAIL: canonical/env-off/env-on outputs or C evidence failed (rc=$abc_rc)"
    echo "$abc_out" | tail -12
    exit 1
fi
abc_count=$(printf '%s\n' "$abc_out" | grep -c '^ABC PASS ' || true)
if [ "$abc_count" -ne 4 ] || \
   ! printf '%s\n' "$abc_out" | grep -qF \
       "C++ A/B/C NON-INVASIVENESS PASS — 4 algorithm/case pairs, strict raw-bit"; then
    echo "ABC GATE FAIL: coverage drifted (ABC PASS lines=$abc_count, expected 4)"
    echo "$abc_out" | tail -12
    exit 1
fi

echo "G3.3 CONTINUOUS GATE PASS: substep+surface real checks, seven predicted-site mutant kills, and C++ A/B/C strict-bitwise"
echo "  shadow:        $(printf '%s\n' "$mut_out" | grep -v '^[(]evidence' | tail -1)"
echo "  cons:          $(printf '%s\n' "$cons_out" | grep -v '^[(]evidence' | tail -1)"
echo "  prevout:       $(printf '%s\n' "$prevout_out" | grep -v '^[(]evidence' | tail -1)"
echo "  poststate:     $(printf '%s\n' "$poststate_out" | grep -v '^[(]evidence' | tail -1)"
echo "  fallacc:       $(printf '%s\n' "$fallacc_out" | grep -v '^[(]evidence' | tail -1)"
echo "  surface-omit:  $(printf '%s\n' "$surface_omit_out" | grep -v '^[(]evidence' | tail -1)"
echo "  surface-layer: $(printf '%s\n' "$surface_bottom_out" | grep -v '^[(]evidence' | tail -1)"
