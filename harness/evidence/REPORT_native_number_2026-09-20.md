# Native host number boundaries and applied sedimentation

This follows PR230's offline scalar replay. The experiment retains existing
5 km model inputs, 39 native layers and column 35711 (zero-based j=152,i=143;
Fortran j=153,i=144). The fixed window is 40 s with dt=20 s, mp37,
MPI np1 and one thread. No alternate column is selected based on the result.

## Contracts before measurement

The native boundary in this experiment is Fortran mp37. It is not the mp137
C ABI or a new density adapter. The operational source remains unchanged;
read-only instrumentation is confined to a generated isolated source copy.
The rebuilt module uses the current canonical `.F`, while other host objects
and libraries are inherited dependencies whose identities must be recorded.
This is not a claim that every host object was freshly rebuilt from source.

Initial model values, the actual accretion invocation, the post-limiter values,
state application and host return are separate observation points. In native
Fortran the inline freezing/melting amounts have already been applied before
the later nc rate update. They must not be added a second time merely to make
the native trace resemble the offline coordinator's budget layout.

## Applied sedimentation measures

For each species and actual substep, record the whole 39-layer column. Interior
outgoing/incoming operands are the original post-cap dnr/dni values. The top
update stores no explicit min-departure; retain its offered removal and pre/post
state and label min(pre,offer) as a **derived implicit removal**. It is distinct
from subtracting two rounded endpoint states.

For an upper cell u and lower cell l, define a conditional weight w and report

    interface mismatch = w_l * incoming_l - w_u * outgoing_u
    state delta = sum_k w_k * (post_k - pre_k)
    state rounding = sum_k w_k * (post_k - pre_k + outgoing_k - incoming_k)
    state delta = sum(interface mismatch) - bottom departure + state rounding

The three weights are dz, source rho*dz and rho/(1+qv)*dz. They respectively
represent conditional volume-number, source-moist-mass-number and dry-mass-number
interpretations. The identity can close while the interface mismatch is nonzero;
closing this ledger must not be reported as physical conservation approval.
Surface removal uses the actual bottom departure, not the uncapped falln sum.

Density and qv are captured at the update. The check is local to each call and
substep. It does not assume a fixed density across the two evolving host calls.
Neither this ledger nor PR230's variable-density scalar derivative test validates
all dynamics–microphysics density coupling.

## Completion gates

Execution, noninterference and measured findings are recorded only after runs
complete. Required controls are identical input identities, a fresh baseline
module with the same compilation settings, the instrumented module, and raw-bit
comparison of all common numeric history variables. Build failures are not runs.

Physical number basis and threshold policy, mp137 native ABI measurement,
other species, full dynamics budgets, independent radiation accuracy and liquid
observation approval remain separate questions. Existing liquid approval is 0/9.

## Completed native experiment

Two 40-second integrations completed: isolated uninstrumented control and
read-only capture, each mp37, dt=20 s, np1, one thread. Existing model inputs
were used without external atmospheric data. Both runner validity records are
true. Compilation/link failures preceding these runs are not integrations.
The original installed executable, source and archive were retained. Both
isolated executables use a freshly compiled current canonical microphysics
module and the same inherited host dependencies (not a complete host rebuild).
Compilation retained binary32 and `-ffp-contract=off`; gfortran assembly was
assembled with LLVM and linked with the installed CLT linker. Commands and
identities are in the JSON. No license acceptance or RTTOV call was required.

At 0, 20 and 40 s, all **254 common numeric variables are raw-bit identical**
between control and capture. The two history files also have the same SHA-256.
Captured returned nc/nr match all 39 corresponding NetCDF values at 20 and 40 s
exactly. The public replay checks recorded arithmetic and comparison evidence;
it does not rerun the private host or independently rehash original files.
This comparison establishes instrumentation noninterference for these runs,
not new mp37-versus-mp137 parity evidence.

The lossless capture contains 12,050 scalars in 1,014 grouped records:

| Measured boundary | Rows checked |
|---|---:|
| Host entry = local entry; local return = host return | 78 |
| Actual producer input → source-ordered f32 pracw/nracw | 78 |
| Complete source-ordered f32 nc rate update | 78 |
| Rain/ice sedimentation state updates | 156 |

The first call has zero accretion; the second has nonzero accretion at native
1-based layers 12, 13, 15 and 16. The fourth is weak. Inputs are actual process
invocation values, not time-step initial values. Native inline freezing/melting
amounts precede the recorded nc update; the replay does not count them again.
The recorded limited rates and complete nc update retain both naacw subtractions.
This is source execution reproduction, not a physical endorsement of each term.

## Measured nonzero transport and unresolved conservation

The first sedimentation call is zero. The second contains actual nonzero rain
and ice departures and arrivals; each species uses one substep. Bottom departure
is **zero** in both calls, so nonzero surface export is not newly verified.
The following are step-2 sums over the 38 internal interfaces, evaluated from
actual post-cap operands. Numerical values retain conditional unit meanings.

| Species | Conditional weight | Departure | Arrival | Arrival minus departure |
|---|---|---:|---:|---:|
| Ice | dz | 415967125.4978605 | 492.8096111117247 | −415966632.6882494 |
| Ice | rho dz | 163300273.9917248 | 261.5463496282252 | −163300012.4453752 |
| Ice | rho/(1+qv) dz | 163214681.0224848 | 261.1470766519178 | −163214419.8754081 |
| Rain | dz | 49835.83761279426 | 49835.83996150252 | +0.002348708254 |
| Rain | rho dz | 39206.93183781241 | 41250.61292520710 | +2043.681087395 |
| Rain | rho/(1+qv) dz | 38891.94634393401 | 40880.21635421681 | +1988.270010283 |

Rain volume-weighted mismatch is about 4.71e-8 of internal departure; the
conditional density-weighted mismatches are about 5.21% and 5.11%. These
contrasting measures do not determine the intended physical number unit.
Ice volume-weighted mismatch is about −0.9999988153 of internal departure.
That ratio is **not a percentage of total model ice or BT sensitivity lost**.
It describes this substep's applied interfacial number transfers only.

The largest ice mismatch is upper native layer 24 → lower 23 (1-based).
The upper pre-state is 436252.71875; its offered removal is 475605.5;
actual `dni(24)` departure is 436252.71875 and its post-state is zero.
The next descending iteration recomputes incoming `dni(24)` and caps it using
that already-updated `nci(24,2)=0`, yielding incoming zero. With upper thickness
726.5537109375, the volume-weighted mismatch is −316961031.714386.
The authoritative number expressions are canonical `module_mp_kdm6.F`
lines 1304–1307 (`dni`/`nci`, distinct from adjacent mass `dqi`/`qci`).
The replay verifies that each recorded upper state is the preceding upper
post-state, density/thickness pairing is exact, and departures obey their
recorded storage cap. It does not reconstruct the incoming fall-speed expression
from rounded offered removal, which would change operation order.

Thus this native measurement identifies a source-order transfer inconsistency;
it is not a parser pairing artifact or proof of physical unit resolution.
No production correction or density factor has been inserted. A future fix must
separately address the paired transfer contract and operational parity policy.

The signed ledger closes after retaining state-update rounding. Rain volume
state change is 0.004023080400657, of which 0.001674372146226 is recorded f32
update rounding; ice rounding is zero here. Residuals across the conditional
ledgers are at most 1.37e-12. The replay's 32-ULP arithmetic closure allowance
is based on the summed ledger scale, **not a physical conservation tolerance**.

## Status and validation

Python 3.12 focused replay tests: **15 passed**, including the actual complete
capture, missing/changed record rejection, upper-state pairing, approval flag
rejection and refusal under `-O`. Synthetic examples test separate measures and
surface bookkeeping and are not counted as native experiments.

Native entry/application/return and nonzero rain/ice internal transfer are now
measured for this fixed mp37 column. Physical number basis, repaired transfer
conservation, mp137 ABI, other species/mass budgets, nonzero surface export,
density-coupled dynamics and independent radiative accuracy remain open.
Liquid observation/cost approval remains **0/9**; there were **zero RTTOV calls**.
