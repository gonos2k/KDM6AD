#!/bin/bash
# G3.3-M CI gate: four measurements on the real instrumented drivers -- the
# qr/nr substep proof, the bottom-fall -> surface proof, the shared four-backend
# fixture binding, and full-step C++ A/B/C non-invasiveness.
# The mutation kill test that shows these checks can fail is
# selfcheck_kill_test.sh, run by hand when the self-check itself changes.
set -u
cd "$(dirname "$0")/../.."

if [ -n "${1:-}" ]; then
    OUT=$1
else
    _gate_tmp=$(mktemp -d "${TMPDIR:-/tmp}/g33-gate.XXXXXX")
    OUT="$_gate_tmp/out"
    trap '[ "$?" -eq 0 ] && rm -rf "$_gate_tmp"' EXIT
fi
bash harness/g33_overlay/selfcheck_build.sh "$OUT" || exit $?

# ── qr/nr substep proof ──────────────────────────────────────────────────────
real_out=$(python3 harness/g33_selfcheck.py --driver "$OUT/selfcheck_driver" 2>&1); real_rc=$?
echo "$real_out" | tail -3
if [ "$real_rc" -ne 0 ]; then
    echo "GATE FAIL: substep driver did not PASS (rc=$real_rc)"
    echo "$real_out" | tail -8; exit 1
fi
LEGACY_LINE="legacy: PASS — 2 containers, 16 shadow==actual, 72 FALK + 0 INFLOW + 0 LADDER offline rungs bit-exact, 2 producer cross-checks"
CONS_LINE="conservative: PASS — 2 containers, 16 shadow==actual, 72 FALK + 24 INFLOW + 80 LADDER offline rungs bit-exact, 2 producer cross-checks"
for pin in "$LEGACY_LINE" "$CONS_LINE"; do
    if ! printf '%s\n' "$real_out" | grep -qF "$pin"; then
        echo "GATE FAIL: substep coverage drifted; missing: $pin"
        printf '%s\n' "$real_out" | grep -E '^(legacy|conservative):'; exit 1
    fi
done

# The surface count includes the newly verified surface_denr operand.
# ── bottom-fall -> surface proof ─────────────────────────────────────────────
surface_out=$(python3 harness/g33_surface_selfcheck.py --driver "$OUT/surface_selfcheck_driver" --algorithm both 2>&1); surface_rc=$?
echo "$surface_out" | tail -3
if [ "$surface_rc" -ne 0 ]; then
    echo "GATE FAIL: surface driver did not PASS (rc=$surface_rc)"; exit 1
fi
for pin in \
  "legacy: SURFACE PASS — 3 containers, qr bottom link + 10 fields bit-exact" \
  "conservative: SURFACE PASS — 3 containers, qr bottom link + 10 fields bit-exact" \
  "SURFACE SELF-CHECK PASS"; do
    printf '%s\n' "$surface_out" | grep -qF "$pin" || {
        echo "GATE FAIL: surface coverage drifted; missing: $pin"; exit 1; }
done

# ── shared four-backend fixture binding ──────────────────────────────────────
fourcase_out=$(TMPDIR="$OUT" python3 harness/g33_fourcase_fixture_check.py \
    --canonical-driver "$OUT/abc_canonical_driver" \
    --diagnostic-driver "$OUT/abc_diagnostic_driver" 2>&1)
fourcase_rc=$?
printf '%s\n' "$fourcase_out" > "$OUT/fourcase_fixture.log"
echo "$fourcase_out" | tail -3
if [ "$fourcase_rc" -ne 0 ] || \
   ! printf '%s\n' "$fourcase_out" | grep -qF "FOURCASE FIXTURE PASS"; then
    echo "FOURCASE FIXTURE GATE FAIL (rc=$fourcase_rc)"
    echo "$fourcase_out" | tail -12; exit 1
fi

# ── full-step C++ A/B/C non-invasiveness ─────────────────────────────────────
abc_out=$(TMPDIR="$OUT" python3 harness/g33_abc_noninvasiveness.py \
    --canonical-driver "$OUT/abc_canonical_driver" \
    --diagnostic-driver "$OUT/abc_diagnostic_driver" 2>&1)
abc_rc=$?
printf '%s\n' "$abc_out" > "$OUT/abc_gate.log"
echo "$abc_out" | tail -5
if [ "$abc_rc" -ne 0 ]; then
    echo "ABC GATE FAIL: canonical/env-off/env-on outputs or C evidence failed (rc=$abc_rc)"
    echo "$abc_out" | tail -12; exit 1
fi
abc_count=$(printf '%s\n' "$abc_out" | grep -c '^ABC PASS ' || true)
if [ "$abc_count" -ne 4 ] || \
   ! printf '%s\n' "$abc_out" | grep -qF \
       "C++ A/B/C NON-INVASIVENESS PASS — 4 algorithm/case pairs, strict raw-bit"; then
    echo "ABC GATE FAIL: coverage drifted (ABC PASS lines=$abc_count, expected 4)"; exit 1
fi

echo "G3.3 GATE PASS: substep+surface, shared fixture, C++ A/B/C"
