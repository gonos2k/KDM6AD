# QNC producer and QI writer boundaries, 2026-10-28

This packet extends the PR #468 representative-stage witnesses for the same
READY40 control and rejected α=0.25 T/Q candidate. The isolated executable
retains PR #465's target-only one-ULP donor-scale experiment at `(221,63,6)`.
Only `module_advect_em.o` and `solve_em.o` were rebuilt to record new values.
The compiled `module_advect_em.mod` is byte-identical to the inherited module
interface. The active canonical host source and operational KDM install were
not changed.

Four independent, one-rank/one-thread, 234×282×39 full-host 20 s runs compare
control and alpha with the new traces off/on. `mp_physics=137`,
`no_mp_heating=0`, and the configured radiation remain active in the forward.
The saved namelist has `scalar_adv_opt=1`, `moist_adv_opt=1`, `specified=.true.`
and `spec_zone=1`. `use_q_diabatic=0` omits a separate RK water-tendency
correction; it does not disable KDM forward water updates or latent heating.
The path-free `execution_summary.json` records the source, build, input, ACK,
checkpoint and trace SHA identities. The private executable and full
checkpoints are retained locally, not published.

## QNC transport at native `(i,j,k)=(113,70,12)`

The opt-in `qnc_producer.tsv` has 77 typed records per case. The RK2 ordinary
scalar advection call records initial tendency and the actual Y→X→Z updates;
RK3 records the positive-definite limiter's seven-cell decisions, pre/post
shared faces and actual Z→X→Y updates. The last recorded tendency in each
call matches the previous PR #468 `RKSCALAR_BEFORE.ADVECT_TEND` word at the
same cell and RK stage.

| RK2 captured stage | Control tendency | Alpha tendency | Interpretation |
| --- | ---: | ---: | --- |
| Start | 0 | 0 | Same input tendency. |
| After Y | −8,411,937,792 | −8,411,937,792 | Y lower face differs by one stored word, but the accumulated tendency does not. |
| After X | −15,488,231,424 | −15,488,232,448 | **First recorded applied-tendency bit difference.** |
| After Z | −16,758,736,896 | −16,758,738,944 | This is the actual RK2 QNC update input. |

The X upper face differs by one binary32 ULP. A source-order calculation that
allows a single-rounded FMA in each axis reproduces all six recorded
post-axis words in both cases. Separate binary32 operations also reproduce
the control, but miss alpha after X/Z. This identifies a compatible arithmetic
sequence; it does **not** identify the compiler's emitted instructions.

At RK3, both cases enter the target outgoing-limiter branch and the applied
scale has the same raw word `3C54898F`. Their stored `PH_LOW`, `FLUX_OUT`,
several faces and directional tendencies differ. The packet keeps the
seven-cell limiter and face records in raw bits; it does not turn this one
location into a general correction rule or a domain conservation claim.
All NC values and tendency budgets here remain numerical coordinates without
certified physical number units.

## QI and QC writers

The opt-in `qi_writer_moments.tsv` has 678 typed records per case: the 568
PR #468 stage values plus five QI stages and five QC stages. All 568 inherited
values match PR #468 raw bits in each case.

At `(1,168,33)`, QI is `80000000` (negative zero) before its RK3 moist-state
update. Both executions write `00000007` immediately after that update. The
subsequent conditional `flow_dep_bdy` call has `specified=true` and
`have_bcs_moist=false`; after it, control has `00000000` and alpha has
`00000002`. In the retained source, a positive output at the x-start boundary
is consistent with copying an interior value rather than assigning literal
zero. The donor cell value and boundary velocity at that instant were not
recorded, so the two experiments' different branch/donor inputs remain open.

At `(155,120,15)`, QC is exactly zero before the RK1 moist update in both
executions and `354ECF22` immediately afterward. NC remains zero at those
sampled points. This locates the common QC appearance at the RK1 moist-state
update, before the later QNC validity split.

## Offline replay and scientific limit

```bash
python3 -m harness.evidence.native_qnc_advect_qi_2026-10-28.replay
```

The replay verifies source and packet pins, both strict trace inventories,
the PR #468 raw-bit joins, the recorded run receipt, RK2 source-compatible
arithmetic, and the QI/QC writer stage conclusions. It makes **zero** host,
KDM, RTTOV or optimizer calls. The four private runs are separate evidence.

The candidate's complete checkpoint matches PR #468, so the fixed full-domain
M0 still loses **54 profiles and 378 channel cells**. Its full-support RTTOV
cost is undefined. No analysis was accepted or carried into a second
assimilation. The current packet does not certify a QNC physical unit, a
domain-wide number budget, a full-host Jacobian, or forecast skill.
