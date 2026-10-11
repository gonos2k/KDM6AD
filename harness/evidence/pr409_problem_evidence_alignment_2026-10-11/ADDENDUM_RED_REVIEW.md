# Red review: PR409 synthetic-H and optional M diagnostics addendum

## Disposition

No blocking issue found. The new language correctly narrows what PR408's
synthetic-H result can establish and makes the proposed `R_M` and `I_M`
quantities distinct, optional and uncomputed. It adds no scientific acceptance
claim, completion gate, test, experiment or data request.

## Synthetic-H rank, permutation and NC limits

The source-backed expression matches
`oracle/tests/test_da_single_column.py::_install_synthetic_allsky`: it computes
one scalar from Exner-scaled theta, qv and qc, then expands that value across
seven outputs. Its local observation-map Jacobian therefore has seven identical
rows and rank at most one, including after the real KDM map M. This is a bound
on the synthetic fixture, not an observed rank for physical AMI/RTTOV. The
fixture asserts the incoming channel tuple is 10–16, but its repeated scalar
cannot distinguish channel-specific spectral response or a BT permutation.
With equal unit sigma and all-one support, permuting the seven targets leaves
its summed loss and state pullback unchanged. The draft explicitly separates
metadata/order validation from this physical-response limitation.

The callback reads only theta, qv and qc; its constructed adjoint has nonzero
entries only for those fields. It has no direct NC term. That says nothing
against NC changes or sensitivity mediated by M in a physical observation
operator; the document keeps those questions separate and does not label the
synthetic result an NC retrieval or NC sensitivity result.

The retained PR408 result's initial synthetic BT is 281.179394596 K across
channels, with targets 282–288 K, unit sigma and Huber delta 1 K. Thus one
initial residual is within the quadratic region and six are in the linear
region. The addendum correctly prevents transferring an all-linear statement
from the real case to this synthetic result. It describes the synthetic cost
reduction as an objective result, not weather improvement.

## Optional `R_M` and `I_M`

The definitions are algebraically consistent:

- `R_M(x) = H(M(x)) - H(x)` is the one-state observation change under the
  selected evolution map and fixed H auxiliaries.
- `I_M = R_M(x_a) - R_M(x_b)` is the change in that evolution response across
  the accepted and background initial states. It is equivalently the difference
  between the M-evolved and identity observation increments.

The report correctly allows `R_M` to be nonzero while `I_M` is zero, recommends
using the four retained background/accepted and slot-state arrays first, and
makes further H values conditional on a specific missing claim. It keeps same
auxiliaries and the existing seven-channel admissibility rule, and it disclaims
same-valid-time host forecast and individual-process causal interpretations.
No `R_M`, `I_M`, or new H result was calculated here.

## Preservation and checks

The review is documentation-only. The worktree diff contains no change to PR408
test/source/result/receipt artifacts or to KDM/RTTOV code. The Graphify query
returned generic capture nodes rather than this claim path, so I verified the
source and retained record directly. No test suite, numerical calculation,
model/native read, M/H call, optimizer, or archive search/request was performed.
