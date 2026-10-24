# Unified directions and saved-data attribution

The live observation verifier now calls its already tested `direction_vectors`
function and consumes the returned `(dx, dr)` pairs. The duplicate
`_make_directions` implementation is removed. Preparation, operators, validation
criteria and saved experiments are otherwise unchanged. At the saved native
reference point, all3 old/new helper dx vectors match bitwise in the same
NumPy environment, every dr is zero, and vectors match those used in the
accepted actual run. `direction_replay.json` records this arithmetic check.

The prior executed controller and source-hash test are preserved under
`executed_sources`. The old actual-QR and readable-tools manifests are not
rewritten; `historical_source_resolution.json` identifies the immutable source
bytes they bind. Current code has a separate new manifest. This is an explicit
execution-era source audit, not a claim that the old run executed the new file.

## What the saved K decomposition means

For each stored native direction, profile variable v and channel c, the reader
computes `b[v,c]=fsum(K[v,c,l]*profile_tangent[v,l])`, followed by the saved cost
seed contraction. All products round in binary64 before `math.fsum`. T, Q,
direct center/interface pressure, liquid cloud and ice cloud contributions sum
to the validated total JVP/cost derivative within an explicit arithmetic
rounding envelope. That envelope does not replace or relax the accepted
physical FD gates.

The terms are an algebraic decomposition in RTTOV profile coordinates. T can
include native pressure/Exner effects; the P/P_HALF group is only RTTOV's direct
pressure K term. Liquid and ice groups include both content and effective
**diameter**, with their subcomponents preserved. HYDRO6 is QC-derived liquid;
HYDRO7 is QI+QS-derived ice, not QG. QR/NR are not direct optical inputs here.
These terms are not named-process tendencies, independently validated native
controls or parameter-identifiability certificates. Only the previously
validated total directions have actual finite-difference evidence.

Candidate/reference comparisons require the same saved target, observation,
quality/mask and native direction. A missing legacy rest-direction or cloud-
fraction record is explicitly unmeasured rather than fabricated. Any finite
profile-difference contraction is a first-order diagnostic, not an exact
nonlinear BT change or proof of a physical cause at roundoff-level differences.

## What post_micro decomposition means

The second reader reuses the original two B512 blocks and the actual fixed
DEND×DELZ measure. Water stages are bottom-first; QR trace geometry is reversed
explicitly. Primary column net is one `math.fsum` of already-rounded weighted
species/layer increments. Per-species, per-layer and vapor/liquid/ice subtotals
help locate large opposing movements and small remaining nets. Further subtotal
rounding is recorded separately; regrouping does not redefine the original net
or its physical acceptance criteria.

Here vapor is QV, liquid inventory is QC+QR, and frozen inventory is QI+QS+QG.
Those inventory categories differ from the observation cloud mapping above.
Endpoint species changes describe net inventory movements, not individual
conversion rates or causality. They cannot select a named process, cleanup,
limiter or latent-heat error without additional internal evidence. Offline host
cleanup remains separate from post_sed→post_micro. Full-water closure, energy,
number/moment consistency and host/RK remain uncertified.

Both readers are saved-data-only NumPy arithmetic. This follow-up makes
**zero KDM, RTTOV, host, DA or build calls**. Previously accepted QR and local
observation derivative milestones remain complete in their stated scopes.

## New localization from the same saved arrays

The largest remaining column losses occur at different points from the two
original QR witnesses. Native horizontal coordinates and vertical level numbers
below are1-based, with levels counted upward from the bottom. Contributions
are already weighted kg/m² products on the same actual forcing measure.

| Chunk/native point | Column post_micro net | Dominant native layers and their net changes |
| --- | ---: | --- |
| 34,(140,76),local281 | −7.42200846056e−7 | level19:−4.51353666912e−7; level18:−2.90847180009e−7 |
| 40,(139,89),local250 | −4.17194940053e−7 | level18:−4.17194939830e−7 |

At these dominant loss layers, the nonzero species increments are QV increase
and QS/QG decrease; QC, QR and QI increments are zero. For example, chunk40
level18 has QV+0.007488352443289283, QS−0.007472712536396364 and
QG−0.000016057101832748413 kg/m². Their small unmatched net is the recorded
−4.17194939830e−7, not a QR sedimentation deficit. Endpoints still cannot
distinguish intermediate conversion paths, caps or rate applications; no
specific sublimation or cleanup bug is certified by this pattern.

The original QR witnesses now have substantial opposing post_micro movements
that almost cancel: gross absolute layer/species changes are about0.4534 and
0.8599kg/m², while their net changes are−1.50e−15 and+1.82e−15. Large species
activity and net fixed-measure budget residual are different diagnostics. The small true
remaining block maxima above must not be conflated with these roundoff-level
witness nets, or with separately reported offline cleanup losses.

## Saved observation-coordinate contributions

The following cost directional terms use the actual candidate's saved K and
profile tangents. Values are per the stored native direction amplitudes, not
comparable raw derivative magnitudes across quantities with different units.

| Profile coordinate group | theta_m | qv | mixed |
| --- | ---: | ---: | ---: |
| T | +1.07217217 | −0.03051520 | +1.04165697 |
| Q | +0.00041673 | −0.01704757 | −0.01663084 |
| Direct P+P_HALF | −0.04685142 | −0.00050194 | −0.04735336 |
| Liquid content+Deff | approximately0 | approximately0 | approximately0 |
| Ice content+Deff | −0.72066789 | −0.24553660 | −0.96620449 |
| Total | +0.30506959 | −0.29360131 | +0.01146829 |

The small mixed derivative therefore contains large opposing temperature and
ice-cloud terms. This is a linearized response decomposition, not an observed
process budget, an optimized search direction or proof of identifiability.
The full per-field/per-channel values and arithmetic checks are retained in
`profile_contributions.json`. Direct pressure terms are separated into center
and interface fields there so their own cancellation is visible.

The observation decomposition remains at native(131,88). The largest remaining
post_micro losses at(140,76)/(139,89) are different columns; their layer budget
patterns are not causally joined to this observation Jacobian. This saved-data
follow-up does not evaluate new hotspot radiances or claim their sensitivities.

The legacy zero-rest source contract is verified from the already public
`execution_sources/final_coupling.py.txt`, against its prepared-source digest
and historical manifest execution role. Its old absolute host path is an
identity string only; replay does not require that private file or host tree.
