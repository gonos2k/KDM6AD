#!/bin/bash
# Verdict helpers for selfcheck_gate.sh, extracted so the acceptance logic can
# be driven directly with synthetic (output, rc) pairs — the gate's own runs
# always rebuild real artifacts, so its branches were unfalsifiable in place.

# verdict_mutant OUT RC EXPECTED_KILL -> 0 iff this is the CONTROLLED predicted
# failure and nothing else:
#   rc == 1 exactly        a SystemExit check failure; crashes carry other codes
#                          (segv 139, abort 134), SKIP is 2 — none are kills
#   last line == expected  the kill must be the terminal verdict; output that
#                          continues past it means something ELSE ended the run
#   no Python traceback    an uncontrolled exception is a broken harness, not a
#                          localized first divergence, even at rc 1
verdict_mutant() {
    local out="$1" rc="$2" expected="$3"
    [ "$rc" -eq 1 ] || { echo "mutant rc=$rc is not a controlled check failure"; return 1; }
    case "$out" in *"Traceback (most recent call last)"*)
        echo "mutant output contains a Python traceback — a crash, not a kill"; return 1;;
    esac
    local last
    last=$(printf '%s\n' "$out" | tail -1)
    [ "$last" = "$expected" ] || {
        echo "mutant's terminal line is not the predicted kill:"
        echo "  expected: $expected"
        echo "  got:      $last"
        return 1
    }
    return 0
}
