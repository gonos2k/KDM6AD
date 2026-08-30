#!/bin/bash
# G3.3-M mutation kill test -- run by hand when g33_selfcheck.py,
# g33_surface_selfcheck.py or the overlays change. Seven drivers broken on
# purpose (make_mutant.py) must each die at the predicted site, for the right
# reason. Not a CI step: the CI gate is selfcheck_gate.sh.
#
#   bash harness/g33_overlay/selfcheck_kill_test.sh [OUT_DIR]
set -u
cd "$(dirname "$0")/../.."
# shellcheck disable=SC1091
source harness/g33_overlay/selfcheck_gate_lib.sh

if [ -n "${1:-}" ]; then
    OUT=$1
else
    _tmp=$(mktemp -d "${TMPDIR:-/tmp}/g33-kill.XXXXXX")
    OUT="$_tmp/out"
    trap '[ "$?" -eq 0 ] && rm -rf "$_tmp"' EXIT
fi
bash harness/g33_overlay/selfcheck_build.sh "$OUT" --with-mutant || exit $?

fail=0
kill_check() {  # $1 label  $2 predicted terminal line  $3.. the checker command
    local label=$1 expected=$2 out rc why; shift 2
    out=$("$@" 2>&1); rc=$?
    if why=$(verdict_mutant "$out" "$rc" "$expected"); then
        echo "  killed  $label"
    else
        echo "  MISSED  $label: $why"; fail=1
    fi
}
SUB=harness/g33_selfcheck.py
SURF=harness/g33_surface_selfcheck.py
kill_check shadow         "FAIL offline!=dumped: legacy L1_main_n2 k=0 qr QR_FALK.falk_precast" \
    python3 $SUB --driver "$OUT/mutant/selfcheck_driver"
kill_check cons-inflow    "FAIL offline!=dumped: conservative L1_main_n1 k=1 qr QR_INFLOW.inflow_final" \
    python3 $SUB --driver "$OUT/mutant_cons/selfcheck_driver"
kill_check cons-prevout   "FAIL causal-link: conservative L1_main_n1 k=1 prev_out != QR_OUTFLOW.dq_out(k-1)" \
    python3 $SUB --driver "$OUT/mutant_prevout/selfcheck_driver"
kill_check cons-poststate "FAIL causal-link: conservative L1_main_n1 k=1 QR_UPDATE.q_post != substep_post.qr[:, k] (returned state diverged)" \
    python3 $SUB --driver "$OUT/mutant_poststate/selfcheck_driver"
kill_check cons-fallacc   "FAIL offline!=dumped: conservative L1_main_n1 k=0 qr QR_FALLACC.fall_after" \
    python3 $SUB --driver "$OUT/mutant_fallacc/selfcheck_driver"
kill_check surface-omit-qi "FAIL surface-offline: conservative L1_surface rain_increment" \
    python3 $SURF --driver "$OUT/mutant_surface_omit_qi/surface_selfcheck_driver" --algorithm conservative
kill_check surface-wrong-bottom "FAIL surface-link: conservative L1_surface bottom_fall_qr != L1_main_n2 QR_FALLACC(k=3).fall_after" \
    python3 $SURF --driver "$OUT/mutant_surface_wrong_bottom/surface_selfcheck_driver" --algorithm conservative

if [ "$fail" -ne 0 ]; then echo "KILL TEST FAIL"; exit 1; fi
echo "KILL TEST PASS: 7 of 7 mutants died at the predicted site"
