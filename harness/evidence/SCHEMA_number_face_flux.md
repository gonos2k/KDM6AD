# Native number face-flux capture v1

`number_face_flux_2026-09-24.json` contains two trajectories. All indices are
Fortran one-based. The fixed 16-target schedule is defined in the replay code;
it is the union of inner donors of the original/normalized final-negative cells.

Each `flux` row starts with `tag, step, rk, species, tile, target, i, k, j`.
The following 103 values are indexed **one-based within that value vector**:

| Positions | Meaning |
| --- | --- |
| 1–15 | field, field_old, tendency, mut, mub, mu_old, c1, c2, msftx, msfty, rdx, rdy, rdzw, dt, eps |
| 16–17 | stored ph_low, stored flux_out |
| 18–23 | high-minus-low correction faces xL, xR, yS, yN, zB, zT |
| 24–29 | low-order faces in the same order |
| 30–50 | seven triples `(inside_limiter, ph_low, flux_out)` for self, west, east, south, north, bottom, top |
| 51–57 | current field at those seven cells |
| 58–64 | field_old at those seven cells |
| 65–70 | coupled velocities ru xL/xR, rv yS/yN, rom zB/zT |
| 71–73 | stored-budget comparison, recomputed scale expression, scale-valid flag |
| 74–80 | mut at the seven cells |
| 81–87 | msftx at the seven cells |
| 88–94 | msfty at the seven cells |
| 95–97 | rdzw at k−1,k,k+1 |
| 98–100 | c1 at k−1,k,k+1 |
| 101–103 | c2 at k−1,k,k+1 |

Outside-limiter budget triples use explicit invalid flags and zero placeholders;
no uninitialized budget is read. The scale field is not a capture of the reused
Fortran temporary: it evaluates the expression again only when active. Actual
POST faces independently test its effect. All values are widened from REAL4
and written with 17 decimal digits. PRE/POST/Z/X/Y keep the same field and
metrics; only correction faces and then the tendency change.

`config` rows are: step, rk, species, tile, ids,ide,jds,jde,kds,kde,
limiter_i_start/end, limiter_j_start/end, limiter_k_start/end, horizontal order,
vertical order, specified,nested,periodic_x,open_xs,open_xe,open_ys,open_ye,
zadvect_implicit,degrade_xs,degrade_xe,degrade_ys,degrade_ye.

`summaries` use named fields and distinguish buffer 0 (current scalar) from
buffer 1 (scalar_old). A tile-zero scan covers the whole owned mass domain;
tile scans cover disjoint j strips 1–142 and 143–282. Do not add tile and global
counts. `new_negative`/`recovered` compare each cell with its last scan of the
same buffer; `first_sample` marks the absence of a prior sample. `first_new_*`
is a deterministic lexicographic coordinate, not wall-clock ordering within a
parallel loop. `g2_*` are captured advector context variables; outside the call
they may retain an earlier context and are not independent stage identifiers.

`events` contain named REAL4 operands from `RK_OPERAND`/`PD_OLD_OPERAND` rows,
round-tripped from list-directed REAL4 decimal output. Transition rows include
only bounded examples (eight largest new negatives per scan), with widened
previous/current values. Unused operand fields in transition rows are explicit
zeros, not measurements. `pressure_weighted_deficit` is a diagnostic using
current mu2, including for old-buffer scans; it is not a physical number budget.

`exact_stored_face_budgets` are derived rational-arithmetic diagnostics of stored
face operands. `history_negative_cells` lists all negatives independently
extracted from each of the three capture-history frames. The source/log hashes
are provenance receipts, not authentication performed by the public replay.
