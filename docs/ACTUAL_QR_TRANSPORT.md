# QR-only actual-departure research candidate

This opt-in fp64 map retains the accepted `norm_actual` ice candidate and the
original B512 schedule. It replaces only main-substep QR state/fall updates.
NR, QS, QG and BRS retain their direct main-substep recurrence formulas.
Re-sloping from changed QR can still change later work and their full-step
trajectories; output equality between variants is not promised. All other microphysics,
cleanup, finish, native prep/profile and ABI contracts are reused. Operational
sources, install and f32 defaults are not modified by the generated overlay.

## Applied mass and first-order contract

Use native dry density rho>QCRMIN, depth dz>QCRMIN, nonnegative entry QR q and
nonnegative normalized work w and accumulated fall rate. The integer local count m and gate g are fixed
within a differentiable branch. At each top-first layer:

```
f = rho * q * w / m * g
attempt = f * dt / rho
departure = min(attempt, q)
arrival[0] = 0
arrival[k] = departure[k-1] * (rho[k-1] * dz[k-1]) / (rho[k] * dz[k])
q_after = q - departure + arrival
fall_after = fall_before + departure * rho / dt
```

The surface routine is unchanged and converts the accumulated actual QR rate
using its original `fall * dz / DENR * dt * 1000` order. Actual bottom departure
and bottom net depletion remain different when arrival is nonzero. The incoming
amount is not capped again against the donor's post-update remainder. Since
`0 <= departure <= q` and arrival>=0, no positivity projection is needed.
With mu=rho*dz, each interface has `mu_lower*arrival = mu_upper*departure` up
to floating roundoff. Thus `sum(mu*(q_after-q)) + mu_bottom*departure_bottom`
closes to a declared binary64 arithmetic envelope on this fixed call measure.
It is not an RK/map-area/energy/whole-host budget.

For a smooth active min branch, departure tangent is either attempt tangent or
entry-q tangent. At a tie, framework minimum's selected subgradient is retained;
central differences across a tie are not a classical derivative certificate.
For each interface:

```
d_arrival = (mu_upper/mu_lower) * d_departure_upper
          + departure_upper/mu_lower * d_mu_upper
          - arrival/mu_lower * d_mu_lower
 d_mu = dz*d_rho + rho*d_dz
 d_q_after = d_q - d_departure + d_arrival
 d_fall_after = d_fall_before + (rho*d_departure + departure*d_rho)/dt
```

Autograd transposes this complete graph. Density/depth contributions at shared
interfaces must accumulate, and fixed dt/count/gate are not advertised as
continuous controls. No scalar extraction belongs to these arithmetic paths;
entry validation and optional trace serialization have explicit value-only
scopes. The Python oracle and generated private C++ helper use the same order.

## Deliberate limits

The unchanged NR map can retain an imperfect rain mass/number pair; this is a
QR-mass-only counterfactual, not number conservation or a new DSD closure.
Inputs/results must record finite/nonnegative moments and changes in active
mass-with-zero-number counts. Existing subsequent DSD limiters are preserved,
not replaced by an invented density/unit correction. Historical native number
payload units remain unknown; the observation calculation separately defines
its source-qualified dry-number coordinate once at the reference point.

Before broader use, compare original blocks34/40, actual QR transfer/ground
accounting and all-species raw/cleanup budgets. Reuse the admitted(131,88)
native T/Q → actual RTTOV directional test. A coefficient-domain rejection is
not a zero-cost fit. Neither a locally closed QR budget nor a JVP/VJP identity
certifies forecast skill, full-host/RK/HVP, or operational adoption.

## Repeatable local execution

The readable source is `harness/run_native_candidate_observation.py`. Run
`python -m harness.run_native_candidate_observation --help` for its path
arguments. The default experiment is defined once in `EXPERIMENT`; the CLI
requires a fresh output directory and attests the selected candidate binary
against its build and overlay receipts before model evaluation. `prepared.json`
is saved before the first forward. `--qr-transport legacy` is separate from
library role and requests the retained map; actual_departure is never inferred
from a filename. Private native/RTTOV assets and a matching isolated build are
required; a public clone does not acquire substitute weather data.

```sh
python -m harness.run_native_candidate_observation \
  --output-dir /absolute/new_run_directory \
  --library-role candidate --qr-transport actual_departure
```

The new result stores per-endpoint quality, mask, cloud fraction and finish/
cleanup signatures. Eligibility preserves those arrays only. Actual QR cap
masks and KDM integer schedules are not recorded at FD endpoints; no all-kernel
branch-stability certificate is made. See the evidence report for the three
T/Q direction results and the unchanged observation cost at this single point.
