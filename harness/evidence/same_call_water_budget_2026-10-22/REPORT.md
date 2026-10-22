# Same-call native-column water accounting — 2026-10-22

The measurement gap is resolved: one fresh fp64 legacy KDM call now supplies
its exact input forcing, before/after state, and all three surface increments.
**The measured water budget does not close.** No physics or tolerance was
changed to remove the residual. The accepted #433 number-boundary and local
observation-cost derivative results are not reopened by this value diagnostic.

## Executed case and build

- Source base: `5202ea117c1661472b79411e07e854b532367854`, feature branch,
  separate from main and the operational installation.
- Native case: 39 levels at `(i=156,j=21)`, step-2 operands reconstructed for
  the previous admitted single-column research experiment. Input provenance
  and historical number-unit limits are those in the pinned #433 admission.
- Call: dt=20 s, XLAND=2, ncmin_land=ncmin_sea=10, physics variant 0,
  internal volume numbers (`dry_number=false`). Explicit dry-coordinate
  boundary entry conversion is reproduced before calling KDM.
- Fresh isolated source build with libtorch 2.13.0, CPU binary64,
  `-ffp-contract=off`, rank-independent offline tool, one thread. No native
  WRF integration or RTTOV execution was performed in this experiment.
- `kdm6_column_budget` returns one FnResult. Exact echoes and the unchanged
  operand-tensor checks bind state and forcing to that call. Namelist/checkpoint
  pins independently bind dt, ncmin and XLAND before execution.
- The published result is the final bound capture, one call. Three earlier
  private calls on the same input occurred during producer development
  (serialization fix, added provenance checks and final replay-code freeze); their outputs are not mixed
  with this result. The separate CTest fixture also calls the kernel and is
  interoperability evidence, not this native budget.

`build_manifest.json` pins the complete public core/header sources and new
capture tool, configuration, compiler, executable, and static core. The native
source audit is separate in `SOURCE_AUDIT.md`; it is not a second host run.

## Measured balance

All values below use **this call's actual fp64 DEN and DELZ**, not widened
captured f32 operands, post-finish density, or MU/g.

| Quantity | kg m-2 |
| --- | ---: |
| Dry-air column measure, Σ DEN × DELZ | 9739.965155746619 |
| Initial total water | 61.01652065852701 |
| Raw final total water | 61.01522210932224 |
| KDM state change | -0.0012985492047658913 |
| Total surface export | 0 |
| KDM change + export residual | **-0.0012985492047658913** |
| Cleanup change | -0.0000005449926229476307 |
| Applied change | -0.001299094197388839 |

The total surface export is the runtime's `rain_increment`: it already
includes rain, snow, graupel and ice. Snow/ice and graupel subset outputs are
also zero. They are not added again, and no extra dt factor is applied.
No external top influx is part of this column operator. The six summed water
species include vapor; water redistributed among ice/snow/graupel is not
misclassified as loss solely because one species decreases.

The diagnostic numerical gate, declared before interpreting the case, is
`256*eps*max(1,abs(Win)+abs(Wout)+abs(export)) = 6.9367014684672334e-12 kg m-2`.
The residual fails it by many orders of magnitude. This is a numerical
comparison gate, not a physical truncation-error bound. Both
`within_numerical_gate=false` and `closed_water_budget_certified=false` are
preserved. `diagnostic_complete=true` reports complete accounting inputs and
an algebraically consistent change split, not conservation.

The newly captured raw state is **468/468 binary64 values bit-identical** to
the previous #433 kernel output. Cleaned water is bit-identical too. Thus
the new capture path preserves that result while exposing its previously
unavailable surface export. This is fp64 research-path noninterference,
not a fresh operational f32/native-parity campaign.

## Cleanup and interpretation

The pinned interior cleanup removes tiny QI at levels 19–21 without a vapor
or heat compensation or a number-field cleanup. Its sink is reported
separately and is far smaller than the raw KDM residual. It cannot explain
away the raw residual. Finish changes temperature coordinates and uses the
cleaned water fields, so the applied-water ledger uses those fields.

The existing legacy-interface-cap attribution in
`docs/P0-4b_sedimentation_attribution.md` identifies a possible legacy
nonconservative path in a different example. That historical result alone
does not attribute the present residual to sedimentation or to a named
microphysics process. The same-call result is the primary measurement;
any separately instrumented localization must retain its own source/build
pins and demonstrate identical final state and export.

## Separately instrumented stage localization

The pinned runtime overlay records binary64 six-species water states, DEN and
DELZ at entry, before/after sedimentation, after the microphysics pass, and exit.
It is generated outside the source/install tree. Only the runtime object is
replaced in a **copy** of the fresh static archive, with the exact original
compiler flags; this is an attributed forensic build, not the primary capture.
The overlay response, with tracing disabled and enabled, is bit-identical to
the primary response, including inputs, all state outputs and three increments.

The `pre_sed` record is top-first (`cur_pyc`, `cf_pyc`); all other stage records
are WRF bottom-first. Reverse `pre_sed` before comparing per-level states and
weights. Matched per-level differences, reduced with the same weights, give:

| Transition | Total-water change, kg m-2 |
| --- | ---: |
| Entry → pre-sedimentation | 0 |
| Pre → post-sedimentation | **-0.0012979597722250025** |
| Post-sedimentation → post-microphysics | **-0.0000005894325408886351** |
| Post-microphysics → exit | 0 |

The sedimentation-stage loss is entirely QI within numerical summation error;
its weighted inventory decreases from about 0.00129795977475 to
2.52475883511e-12 kg m-2. Other water species do not receive that mass, and the
surface export remains zero. The later microphysics residual involves mixed
vapor/rain/ice/snow changes. Thus the dominant residual is now localized to
the sedimentation transition, with a smaller additional microphysics residual.
This does **not** yet identify the responsible internal limiter/interface
update or establish that it is exactly the historical heavy-rain defect.
No legacy physics is changed in this PR.

The next narrow investigation is the QI sedimentation departure/arrival and
bottom-flux accounting for this same case, followed by the smaller microphysics
residual. Full RK/host coupling is not needed to resolve these local balances.

## Reproduction and boundaries

Build the optional tool, then run `python -m harness.same_call_water_budget`
with `--report`, `--admission`, `--namelist`, `--checkpoint`, `--executable`,
`--workspace` (new directory) and `--output` (new file). The report/admission
are the public #433 artifacts; the two native inputs remain private.
Public arithmetic reproduction is covered by
`harness/tests/test_same_call_water_budget.py`; it recomputes the saved ledger
and retains the failed conservation gate without a private execution.

This is a fixed-call-density/thickness water diagnostic. It is not a complete
host/RK mass-flux ledger, a number/energy budget, a migration of historical
number payloads, a new observation fit, forecast skill, or a full-host AD
certificate. Previously recorded pressure-sweep, raw-NCCN stress and pixel-time
limitations remain in their original evidence.

## Local validation

- Full harness at the earlier complete source collection: 2,607 passed,
  59 skipped, 309 deselected. Later public-ledger and overlay additions were
  checked in the final focused run: 27 passed.
- Fresh isolated C++/Fortran CTest: 23/23 passed, including the new same-call
  CLI/direct-call bit comparison and truncated-request refusal.
- Undefined-name lint passed for the new producer and ledger tests.
- Green/Red source review checked overlapping exports, exact operands,
  independent scalar provenance, failed-closure claims and stage orientation.
  The identified scalar-provenance gap was fixed and has mutation tests.
