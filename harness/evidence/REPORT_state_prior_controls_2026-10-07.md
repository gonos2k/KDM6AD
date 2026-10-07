# Existing state-prior controls in the internal research route

Authoring base: PR #380 source head `b30ac950`. The opt-in normalized KMA
full-domain analysis now forwards caller-declared state sigma overrides to the
existing diagonal CVT. Legacy defaults and warm-process parameter priors are
unchanged. No KDM process, physical threshold, ABI or BT conversion changed.

## Executed comparison

[Producer](STATE_prior_controls_source_2026-10-07.py),
[result](STATE_prior_controls_result_2026-10-07.json), and
[receipts](STATE_prior_controls_receipts_2026-10-07.zip) record two predeclared
one-iteration trials. Each uses the retained native C5 column, 20 s Python f64
KDM and actual DOM32 RTTOV with the A1 synthetic fixed sigma/bias assumptions.
These are engineering assumptions, not calibrated B/R or bias.

| Initial NC state control | Total initial cost | Total final cost | Initial NC increment norm | Slot NC increment norm |
| --- | ---: | ---: | ---: | ---: |
| sigma NC = 0 | 10.20315994312423 | 6.730148668289557 | 0 | 90027236.7100843 |
| sigma NC = 0.15 | 10.20315994312423 | 6.72990123538216 | 7570.357801944017 | 90034807.06931938 |

The fixed initial NC case has 79 active state components (39 th, 39 qv, 1 qc);
the enabled case adds one NC component. Four warm log-parameter controls retain
their original priors in both cases. Each objective and final audit retains the
same seven-channel support and observation signature. All 54 Python source
hashes are identical before/after the experiment. Saved fields and producer
hashes are checked; receipt ZIP CRCs pass.

The two objectives have different state priors. Their cost difference does not
select a physical NC policy. Final gradient norms 0.94583/0.94535 and one L-BFGS
iteration do not demonstrate convergence. Fixed initial NC still changes at
the observation slot through the coupled model; this is not a frozen-NC model.
Existing nominal-time/product/geometry limitations of C5 remain. No independent
case, scientifically valid NC reconstruction, new forecast skill, host writeback,
full water/enthalpy budget or calibrated prior is certified.

## Validation and scope

Final focused tests: **44 passed**. Final public-only authoring-tree oracle:
**1658 passed, 93 skipped, 51 warnings**. Counts overlap and are not summed. Private RTTOV is
explicitly absent from that broad suite; its live execution above is separate.
Unbuilt C++/private-input tests are skipped with reasons in the receipt log.
No new C++/Fortran/native host build or host time integration was performed.

The A2 code-integration row closes only this declared initial state-prior input
and metadata path. Scientific B, number conventions, observation correspondence,
physical budgets, timestep accuracy and independent cases remain open.

Green/Red review found and resolved one early-input guard gap: conserving
partition calls now reject nonzero qr/qg/bg as well as qc/qi/qs before preparing
RTTOV. Final focused, broad and live checks above use the corrected source.
Graphify structural refresh and a bounded semantic fragment trace the new input
to the existing CVT; public graph coverage does not replace private-host checks.
