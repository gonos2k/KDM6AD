# Green review: retained Jul19 case claims

Reviewed the PR410 source, result and report against the executed PR395/397/398
records and original H/profile source. The endpoint comparison is correctly
bounded; no new M, H, optimizer or native result is claimed.

I independently checked the canonical retained checkpoint NPZ at
`/Users/yhlee/KDM6AD-k/host/research_evidence/pr397_native_tq_20261010/accepted_final_3d2e97f159.npz`.
Its SHA-256 matches the original `8cfe28df…c904c59`. For both `xb`→`mb` and
`xa`→`ma`, only theta differs, by at most `5.684341886080802e-14`; all other
eleven State fields and the four supplied forcing arrays are bit-identical.
The saved `theta*pii` values are bit-identical at all 39 levels in each pair.
Across all four endpoints, I checked every element of `qc, qr, qi, qs, qg` and
`nc`: all are exactly zero, not merely absent from positive-value counts.

The executed source hashes recorded in the PR395 receipt match all 19 current
source files. The H/profile path reduces theta to `T=theta*pii`; cloud DSD
conversion uses the same temperature transform and the unchanged other state,
forcing and frozen optical density. This supports the report's conditional
source/input-equivalence inference under unchanged deterministic H and fixed
auxiliaries. It does not create direct `H(xb)` or `H(xa)` outputs. Actual H
values remain `H(M(xb))` at call 2 and `H(M(xa))` at call 5. PR398's later host
frame H bindings do not supply the missing same-auxiliary initial-state calls.
The result correctly disclaims `M_x=I`, inactive internal rates, named-process
attribution, a separately optimized no-M analysis and forecast skill.

The original observation costs/residuals, support, gradient and stop status
match the retained receipts; the gradient remains above tolerance and
termination is unknown. Existing water and temperature diagnostics are read
from their earlier saved-array interpretation, with no closed external-flux
water/heat budget or named-process attribution. The local comparator records
one retained-array execution with zero native/M/H/K/optimizer calls. The branch
has no PR410 CI run at review time; this local execution is not CI. Prior PR409
CI is separate and does not test this new comparator.

The central document initially had a stale sentence implying these quantities
had not been evaluated at all. It is now resolved: line 122 attributes that
scope to PR409 and links the later PR410 conditional input-equivalence
inference, while retaining the no-new-H qualification. This wording does not
alter the scientific limits above.

No source or historical receipt was changed. No tests, derivatives, costs,
model, RTTOV, optimizer or forecast were rerun for this review. The scoped
Graphify query was generic; authoritative source and retained arrays were
checked directly.
