# F6: trial, accepted interval and restart-prefix bookkeeping

The verification-only `accepted_interval_ledger.py` uses X5's independent
`IntegrationPlan` and full-plan SHA-256. Its inputs are **already integrated**
signed amounts; X5 separately checks rate×each interval's own duration and
producer dependency validity. This pilot separates a trial ID from an
acceptance ID and stores immutable accepted and rejected records. Acceptance
is allowed only for the next planned interval. The cumulative amount is the
`math.fsum` of accepted amounts, never of all attempted amounts.

For the declared intervals `[0,0.2]` and `[0.2,1.0] s`, X5 integrates
`2` and `8 W/m²` to `0.4` and `6.4 J/m²`. A first trial requests
`10 J/m²` but is rejected; the accepted retry and second interval total
**6.8 J/m²**, not 16.8 or 18. The rejected trial changes neither the
physical cumulative amount nor its completed interval prefix. An identical
accepted-event delivery is inert even after later intervals; a reused
acceptance ID with changed trial content is rejected. A rejected trial ID
cannot subsequently be accepted.

The checkpoint carries the full plan digest, accepted prefix, exact
end-of-prefix time, acceptance IDs, trial payload hashes, rejected trial
records, units and cumulative amount. Restore checks each record's source
dependency revisions and content digest, recomputes the cumulative from the
accepted records, and returns the checkpoint without applying them again.
Tampered plan, time, prefix, amount, acceptance ID or payload fails. A
rejected event for a future interval also fails the schedule check. Signed
negative accepted exchange is allowed and remains in the same ledger.

Five new test functions plus retained parameterized X5 tests produce 18
passing cases with warnings as errors; Ruff passes. The generic plan must
be fixed independently of observed events; coupled plan/record shrinkage
cannot be detected by an arithmetic consumer alone. Payload hashes guard
record consistency but do not authenticate an external producer. Rejection
before acceptance models a rollback of a *trial*, not a post-commit undo of
a physical state. There is no native host restart, MPI run or RTTOV call here.
In particular, G4's continuous-versus-restart trajectory mismatch remains
open and is not converted into a pass by this bookkeeping result.
