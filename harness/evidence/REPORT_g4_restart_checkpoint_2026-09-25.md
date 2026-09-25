# G4.2 checkpoint and bounded restart-producer comparison

## Scope

This evidence combines a byte-level replay of the retained G4 checkpoint with
a shadow-instrumented continuous/restart pair using the same G4 inputs. The
shadow probe observes five input-selected columns at `itimestep=2` and eight
stages in `module_first_rk_step_part1`. It does not edit the canonical private
host tree, change the operational executable, or cover the full domain.

## Checkpoint replay

The retained checkpoint SHA-256 is
`2ad545592a9a2a29afbaeb6eab7dcbca636f749c9060e814e8168470373b6a44`.
Its common numeric variables match both the parent history at 20 seconds and
the restarted child's initial history frame **235/235 by raw bytes**. The
parent and child histories share 253 numeric fields at 20 seconds; 246 match.
The seven differences are history-only diagnostics:
`FOGFRAC_SFC`, `NOAHRES`, `REFL_10CM`, `RHO_ICE`, `VIS_SFC`,
`VIS_SFC_CAPPED`, and `VIS_SFC_RAW`.

This establishes saved-file consistency. It does not observe values after
`phy_init` or prove that all hidden restart state is equivalent at its next
consumer.

## Shadow build and execution

The retained G4 link recipe, run without instrumentation, reproduced the G4
executable SHA-256 exactly:
`799e389e4a5ae3e032607cb4bba59d881184d74798e90e63ee77f426381d6e3c`.
The shadow executable SHA-256 is
`3197df4dcdcf9c1af4132e15662531bc28be4c61892fac54cf7a015311c24140`.
Only `module_first_rk_step_part1.o` and the regenerated archive symbol index
differ from the retained archive. The source and overlay hashes, compile/link
recipe hashes, and member audit are recorded in
`g4_restart_shadow_build_2026-09-25.json`.

The same shadow executable ran a continuous 0→40 second case and a 20→40
second restart case, both mp237, fixed 20 second timestep, MPI 1, 1×1 process
grid, and one thread. Both runs completed with valid experiment receipts.
The continuous history is raw-bit identical to retained G4 serial history
`a065598b870815220ba36f7b2fbcdc6f65f8d69910c2e261961203b78d6683d8`; the
restart history is raw-bit identical to retained G4 restart history
`c67ec492da28edbb1b95f3eef8ffa6ba137672703ef40509ea482af43ee51cbe`.
Strict comparison reports **253 numeric fields raw-bit equal plus exact
`Times` equality (254 total fields)** at each saved frame. Exact case
directories, launch commands, MPI interface
environment, thread settings, input identities, and trace digests are recorded
in `g4_restart_shadow_runs_2026-09-25.json`.

The probe records raw binary32 words for five preselected profiles: clear
(j145,i11), warm liquid (j139,i106), mixed (j124,i144), ice (j130,i209), and
rain (j112,i212). It covers entry, after physics preparation, radiation,
surface, PBL, cumulus, shallow cumulus, and FDDA. The parser pins the declared
G4 schema: 39 mass levels (1–39), 40 interfaces (1–40), 7 moist and 6 scalar
species, and 4 soil levels. It requires the complete expected
stage×profile×field×level key universe in each trace, including rejection of
out-of-plan records even if a mutation preserves the total row count.

## First observed bounded difference

The two step-2 traces contain 48,120 corresponding records. At entry, the only
differences are 390 `PPHY`/`PIPHY` words (39 levels × five profiles × two
fields). These fields are raw-bit equal after `phy_prep`; the selected values
also match after radiation. Thus the entry differences are overwritten before
the later recorded stages, without inferring their initialization history.

The first observed surface-output differences occur immediately after the
surface driver (stage 3): `HFX`, `LH`, `QFX`, and `UST` differ at the selected
clear, ice, and rain profiles (12 words total). The warm-liquid and mixed
profiles match at this stage. After PBL (stage 4), 70 words differ across
clear, ice, rain, and warm-liquid profiles; the differences persist through
cumulus, shallow cumulus, and FDDA. There are no recorded radiation-stage
differences.

This localizes the first observed relevant output producer to the surface
driver for three of these five profiles. It does **not** establish why those
outputs differ: the trace omits several surface-driver operands, including
some land/vegetation/snow/urban properties. It also cannot establish the
first differing producer elsewhere in the domain. No timer/cache cause has
been demonstrated; sampled timers match through the radiation stage, while
the complete dependency set for the surface outputs was not captured.

## Limits and next measurement

The direct checkpoint mapper was removed from the probe interface because it
compared the checkpoint to a later step-2 state after solver preparation; that
temporal pairing is not a valid restart-equivalence test. The valid comparison
is continuous step 2 against restarted step 2. The retained checkpoint/history
replay remains separately available through
`replay_restart_checkpoint.py`.

G4.2 remains **OPEN** for causal attribution. The smallest useful follow-up is
to add the missing surface-driver input fields for the three affected
profiles, then compare those operands immediately before the surface call.
If inputs differ, trace their producer back to restart initialization; if
inputs match but outputs differ, inspect the surface routine's hidden state,
lookup/cache inputs, and call-order dependencies. Broader domain coverage is
needed before claiming a global first divergence. The current evidence does
not justify attributing the mismatch to a restart cache or timer.

The run and trace artifacts are diagnostic evidence only. They do not change
the operating mp237 path or resolve any previously open physical or
observation-validation status.
