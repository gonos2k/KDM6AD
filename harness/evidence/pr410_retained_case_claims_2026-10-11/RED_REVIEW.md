# Red review: retained Jul19 H and M evidence

## Disposition

No blocker found in the retained-case postprocessor or its bounded inference. It
preserves the distinction between actual saved H outputs, source-derived H-input
equivalence, and unmeasured internal process behavior. PR398/399 H records do
not fill the PR397 identity-state H gap.

## PR397 state and H trace

The original [capture receipt](../pr395_tq_state_capture_2026-10-10/RESULT_3d2e97f159.json)
binds four private checkpoint state groups:

- `background_initial` = x_b;
- `returned_analysis_initial` = x_a;
- `background_slot` = M(x_b);
- `final_slot` = M(x_a).

Logical H calls 1 and 2 have identical per-field state and forcing hashes for
`background_slot`; call 1 is the zero-mask quality probe, while call 2 is the
actual initial zero-control closure. Calls 4 and 5 have identical state and
forcing hashes for `final_slot`; call 5 is the final accepted-state audit.
Both objective calls keep AMI channels 10–16, all-seven frozen support, and
zero model rad_quality. Their saved Huber Jo values are 26.588575903055926 and
26.135616402715186. This is a legitimate same-case observation-cost change
between H(M(x_b)) and H(M(x_a)) under the declared T/Q analysis. It is not an
isolated microphysics contribution. The preceding call 1 zero-mask cost is
not the objective baseline.

No PR397 logical H call has the saved `background_initial` or
`returned_analysis_initial` state hash. Direct H(x_b) and H(x_a) outputs are
therefore absent; the four stored States should not be described as four
executed H evaluations.

## Conditional input equivalence

The postprocessor verifies all 11 non-theta fields match bitwise in each pair
x_b→M(x_b) and x_a→M(x_a), while theta differs by at most
5.684341886080802e−14 K. It independently projects both theta arrays through
the fixed native frame-0 Exner forcing using NumPy and Torch and records
physical T=theta*pii bitwise-identical. The supplied forcing hashes, frozen
optical rho_d hash and 19 executed-source hashes are bound to the original
receipt; I checked that the postprocessor source hash, receipt/diagnostic
input hashes and all 19 current source hashes match the saved result.

The H input path supports the inference: `_state_to_coord` maps theta only to
`t=th*pii`; the profile builder uses the same `T=th*pii` conversion; cloud
profile construction uses the remaining State/Forcing fields, and the capture
uses the same frozen H configuration/auxiliaries. Under the postprocessor's
explicit assumption of the same deterministic unchanged H and fixed
auxiliaries, equal profile inputs imply inferred R_M(x_b)=R_M(x_a)=0 and
I_M=0 for these endpoints. The record marks direct H(x_b)/H(x_a) as
`NOT_EXECUTED_OR_STORED`; these zeros are conditional source/input-equivalence
inferences, not measured RTTOV output vectors.

This endpoint equality does not imply M(x)=x as a full state map, M_x=I,
zero internal process rates, or zero named-process effects. It also does not
establish a separately reoptimized no-M solution. The recorded G_M is only
the observed Jo difference between the two H(M(x)) calls; G_0 and the equality
of those contrasts are inferred under the same input-equivalence condition.

## Why PR398/399 do not fill the gap

PR398 is explicitly `H(native saved State_t, Forcing_t)` at saved frames
05:56:00, 05:57:00 and 05:57:40, with no KDM M or backward calls. Its
05:56:00 candidate-geometry row has the same nominal time, channel IDs,
seven-channel support and viewing geometry as PR397. Its frame-1 state-field
hashes differ from all four PR397 state groups; its forcing, pressure/profile
and optical-density hashes also differ. It is a direct host-frame H response,
not H(x_b), H(x_a), H(M(x_b)) or H(M(x_a)). PR398 records RTTOV executable
and coefficient hashes, but PR397 does not bind those binaries by hash, so no
cross-receipt binary identity is asserted.

PR399 evaluates direct H at neighboring native columns and reuses the PR398
center result. It records zero M and optimizer calls. Different spatial states
and associated inputs make those rows spatial sensitivity evidence, not
same-state R_M/I_M data.

## Scope

No native, M, H/K, optimizer, test, or new calculation was run for this review.
No private NPZ was reopened by Red. PR397 retains its outer-harness exit 120,
unknown optimizer termination, above-tolerance final gradient, nominal-time
assumption and absent pixel-time/footprint validation. No source/build
identity beyond the pinned files and hashes stated above is claimed.
