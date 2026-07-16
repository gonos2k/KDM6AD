# P0-4b — sedimentation gap attribution (complete)

Attributes the P0-4 finding that the operator-implied column-water loss
(`sed_column_loss = −ΔW_sed`) and the WRF fallout diagnostic (`rain_increment`)
disagree by O(1) kg/m². **Attribution only** — no forward-path change (the
diagnostics-on state stays `torch.equal` to the plain path; frozen dylib/C++/
Fortran untouched).

## Verdict

**The gap is 100% the internal interface defect from the post-update-reservoir
inflow cap, and the mechanism is reference-faithful — present verbatim in the
original Fortran KDM6.**

On the P0-4 heavy-rain case (2 columns, K=4, dt=120):

| quantity (kg/m²) | col0 | col1 |
|---|---:|---:|
| P0-4 gap `G = P − L` | −4.801248 | −6.018130 |
| bottom diag gap `B = P − O_bottom` | ~0 (−3e-16) | ~0 |
| positivity projection `ΣA` | 0 | 0 |
| **interface defect `ΣD`** | **4.801248** | **6.018130** |
| attributed `B − ΣD + ΣA` | −4.801248 | −6.018130 |
| **unattributed residual** | **−8.9e-16** | **−8.9e-16** |

- The identity `P_s − L_s = B_s − ΣD_s + ΣA_s` closes to the fp64 machine floor,
  per column and per species.
- `qr_inflow_cap` bound at **every** internal interface (3/3 for K=4), per-interface
  defect [1.80, 1.60, 1.40] decreasing with depth.
- The bottom diagnostic itself is **fine** here (`B ≈ 0`): `rain_increment` matches
  the actual bottom-cell outflow. The diagnostic doesn't under-report the surface —
  the column loses extra mass **at internal interfaces** that never reaches the bottom.

## Mechanism (numerically proven, then source-confirmed)

Per interior cell k (K-order, 0 = top), the update is

    dq_k     = min(falk_k·dtcld/dend,                     q_k^entry)       # outflow, entry-capped
    dq_above = min(falk_{k−1}·Δz_{k−1}/Δz_k·dtcld/dend,   q_{k−1}^POST)    # inflow, POST-capped
    q_k ← max(q_k − dq_k + dq_above, 0)

The inflow flux is the **stored** `falk` of the cell above (computed from its
*entry* mass), but the min caps it by the above cell's **post-update** reservoir —
already depleted by its own outflow. In a draining column (CFL·per-substep close
to 1), the above cell keeps only ~(1−CFL) of its entry mass, so the lower cell can
receive at most that, while the above cell lost ~CFL of it: the difference vanishes
at the interface. Summed over interfaces and substeps this is exactly `ΣD`.

Uncapped, the scheme is exactly conservative (even with varying ρ, Δz):
`O_{k−1} = falk·dtcld·Δz_{k−1} = I_k` — verified (T3/T5). The top cell is the only
place a positivity projection can occur (it subtracts the raw flux then clamps);
interior projections are structurally zero (T4 asserts this).

## Reference-faithfulness (3-way)

`host_fortran/module_mp_kdm6.F` (interior sweep `k = kte−1 → kts`; the k+1 cell was
updated in the previous iteration):

```fortran
dqs(i,k)   = min(falk(i,k,2)*dtcld/dend(i,k), qrs(i,k,2))
dqs(i,k+1) = min(falk(i,k+1,2)*delz(i,k+1)/delz(i,k)*dtcld/dend(i,k), qrs(i,k+1,2))
qrs(i,k,2) = max(qrs(i,k,2)-dqs(i,k)+dqs(i,k+1), 0.)
```

`qrs(i,k+1,2)` at this point is the POST-update value — the same post-update
reservoir cap. The oracle mirrors the C++ port, which is strict-bitwise-validated
against this Fortran through the 12 h campaign. **Oracle-only difference: none.**

Per the P0-4b merge policy this is therefore a **documented, quantified,
reference-faithful algorithmic sink**: any fix (e.g. capping the stored flux at
the source cell, or removing the post-reservoir cap) would change the operational
trajectory and belongs to a separately-approved freeze-lift, not this PR.

## Water-budget impact

For a precipitating column the sink scales with the number of cap-bound interfaces ×
per-substep CFL fraction: in the heavy-rain case, 4.8–6.0 kg/m² per 2-minute step —
**larger than the surface precipitation itself** (2.0–3.0 kg/m²). In columns/steps
where no inflow cap binds (light precipitation, small CFL), D = 0 and the budget
closes. Long-integration accumulation over a domain is case-dependent; the
per-column `interface_defect_detail` + `cap_flags` diagnostics make it measurable
in any run via `kdm6_step_with_sed_attribution`.

## Exact decomposition (implemented, all per column)

In ρΔz mass units, with per-level bookkeeping `ρΔz(q_entry − q_post) = O − I − A`:

    L_s = O_bottom + ΣD − ΣA                       (state loss decomposition)
    P_s − L_s = B_s − ΣD + ΣA,   B_s = P_s − O_bottom

`O` = outflow actually used in the update (top: the RAW uncapped subtraction;
interior: the entry-capped min). `I` = inflow actually used. `A` = positivity-
projection addition. `D_k = O_{k−1} − I_k`. All terms recorded inside the substep
functions per species (qr, qs, qg via the main chain; qi via the ice chain),
detached and opt-in.

## API

    from kdm6.water_budget import kdm6_step_with_sed_attribution
    out, budget, att = kdm6_step_with_sed_attribution(state, forcing, dt=120.0)
    # att: SedimentationAttribution — per-species dicts, each (B,):
    #   column_loss / wrf_fallout_diag / gap, bottom_actual_outflow / bottom_diag_gap,
    #   interface_defect (+ (B,K−1) detail), positivity_projection (+ (B,K) detail),
    #   cap_flags (bind counts), worst_interface_index,
    #   attributed_gap, unattributed_residual (≈ fp64 floor)

Acceptance tests: `oracle/tests/test_sed_attribution.py` (T1–T9: single-layer
uncapped/capped, interface conservation, cap-bound defect, variable metric,
projection exactness, species isolation incl. ice, mstep × subcycle, and the
heavy-rain regression pinning `gap ≈ [−4.8012, −6.0181]` with the residual at the
fp64 floor). Non-invasiveness is `torch.equal`-asserted.

## Scope

P0-4b ends here (attribution complete). Deferred:
- **fix decision** — freeze-lift candidate (reference-faithful, changes trajectories);
- **P0-4c** — process-wise latent/thermal work ledger (no state-function assumption);
- **P0-4d** — scheme-consistent energy-invariant existence assessment.
