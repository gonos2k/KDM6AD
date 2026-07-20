#!/bin/bash
# Verdict helpers for selfcheck_gate.sh, extracted so the acceptance logic can
# be driven directly with synthetic (output, rc) pairs — the gate's own runs
# always rebuild real artifacts, so its branches were unfalsifiable in place.

# verdict_mutant OUT RC EXPECTED_KILL -> 0 iff this is the CONTROLLED predicted
# failure and nothing else:
#   rc == 5 exactly        g33_selfcheck's EXIT_FIDELITY — the one code only the
#                          COMPARATOR's own mismatch path exits with. Driver
#                          stdout/stderr is interpolated into failure messages,
#                          so a crashing CHILD can put any text on the terminal
#                          line — but it cannot choose the parent's exit code:
#                          a wrapped driver crash exits 3, evidence corruption
#                          4, SKIP 2, a python crash 1/139/134.
#   last line == expected  the kill must be the terminal verdict
#   no Python traceback    an uncontrolled exception is a broken harness
verdict_mutant() {
    local out="$1" rc="$2" expected="$3"
    [ "$rc" -eq 5 ] || { echo "mutant rc=$rc is not the comparator's own fidelity exit (5)"; return 1; }
    case "$out" in *"Traceback (most recent call last)"*)
        echo "mutant output contains a Python traceback — a crash, not a kill"; return 1;;
    esac
    # The kill VERDICT line, ignoring the trailing "(evidence preserved at …)"
    # annotation the self-check prints on every failure (forensic metadata, not
    # a verdict). Take the last line that is not that annotation.
    local last
    last=$(printf '%s\n' "$out" | grep -v '^(evidence preserved at ' | tail -1)
    [ "$last" = "$expected" ] || {
        echo "mutant's terminal line is not the predicted kill:"
        echo "  expected: $expected"
        echo "  got:      $last"
        return 1
    }
    return 0
}
