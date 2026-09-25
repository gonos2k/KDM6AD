# S2 conditional layered oracle witness (2026-09-25)

This report records a synthetic three-layer representation test and a source
inventory for a possible opt-in number-basis variant. It does not select that
variant, close S2, change the operational mp37/mp137 path, or authorize a native
run. Registry metadata and WRF scalar transport declare the host QN prognostic
basis as number per dry-air mass. The first-step KDM6 CCN initializer is an
explicit internal concentration-valued exception; the full conversion remains
blocked on process, density, threshold, and AD choices.

## Evidence identity and checks

The public source is based on `main` at `2a635b60` after PR #275. The four synthetic
number-value map cases remain in
[`test_replay_number_boundary.py`](../tests/test_replay_number_boundary.py).
The live oracle checks are in
[`test_s2_conditional_layered_oracle.py`](../../oracle/tests/test_s2_conditional_layered_oracle.py):

- Four synthetic number-value cases in the torch-free harness suite exercise the generic map
  `N = rho_d * n_d` and inverse `n_d = N / rho_d` on three different densities.
  The names QNCCN, QNCLOUD, QNICE, and QNRAIN label the examples; they do not
  bind the test to Registry storage or ABI slots.
- A live `oracle.kdm6.warm.accretion_torch` check uses three different `rho_d`
  and `qv` values, preserves the same `rho_d*q_d` and `rho_d*n_d` input moments,
  recalculates the DSD in each coordinate system, and checks small- and
  big-drop selection, a mixed active/inactive rain gate, mass/number rate-map
  equality, and a conditional local water/number amount ledger.
- A separate deliberately oversized synthetic `dt` exercises both per-cell
  inventory caps under both representations. It is a branch stress, not an
  atmospheric timestep.

The production warm-accretion function returns tendencies; the test applies
those tendencies algebraically to cloud water, rain water, and cloud number.
It does not execute the coordinator update, another process, sedimentation,
host dynamics, or C++ f32. Both representations call the same oracle producer,
so the rate comparison is a metamorphic check; the direct-volume helper is used
only for branch/cap metadata and not as an independent numerical rate oracle.
Its equations run in the oracle's fp64 arithmetic and do not establish Fortran
operation-order parity. The existing adjacent
three-layer test checks paired `q`, `brs`, and number moments plus their density
JVP/VJP algebra, but neither test validates an end-to-end corrected KDM6 map.

The harness boundary suite passes 24 tests with torch imports blocked, and the
oracle suite passes the two live layered cases; both use warnings as errors.
Ruff and `git diff --check` pass. Graphify refreshed the rebased source to
13,535 nodes, 23,232 edges, and 1,059 communities, including the seven-node,
seven-edge semantic fragment for this report. HTML output was skipped over the
5,000-node limit. Post-update queries link the layered oracle tests to
`accretion_torch`, `_fresh_dsd`, and the direct volume-rate helper, and link the
candidate map to the dry host basis and density derivative contract.

## Source identity reviewed

Private source was read-only in canonical root `/Users/yhlee/KDM6AD-k`. The
active files reviewed and their SHA-256 values were:

| Source | SHA-256 |
| --- | --- |
| `host/KIM-meso_v1.0/Registry/Registry.EM_COMMON` | `6741720cba12ad7ee1c172339bd8def5973b22f4e88ab9cd152f3ba3df456e37` |
| `host/KIM-meso_v1.0/phys/module_microphysics_driver.F` | `94db84c45b7422b62e04967cb3cd1362311abdb02fa3d374d881799c0bce7e84` |
| `host/KIM-meso_v1.0/phys/module_mp_kdm6.F` | `fc0a72d33a5e61803fea56eb9118018039c6da8b5775813032b4861a2bd66eb5` |

The first two hashes identify the local source observations below; the last is
also the private-source identity in the bounded S2/S14 capture reports. The
public worktree has no private host sources and cannot reproduce this source
review independently.

## Number-state inventory and conversion obligations

The Registry declares `qnn`, `qnc`, `qni`, and `qnr` as scalar fields in
`# kg(-1)` units (Registry lines 535–553); `qib` is a scalar in `m(3) kg(-1)`
(line 570). WRF's scalar update weights these fields by dry-air column mass.
`rho_d=1/alt` is the host dry density, while the KDM6 call receives moist
`DEN=rho_m=(1+qv)*rho_d`. The mp37 wrapper copies `qnc/qni/qnn/qnr` directly to
`nci(1/2/3)/nrs(1)` and back (module_mp_kdm6.F lines 383–432); it maps `qib`
directly to `brs`. No density conversion appears at that boundary.

For the proposed volume-coordinate adapter only, the candidate map is
`N_s = rho_d*n_s` for each stored number field, `C_x = rho_d*q_x` for each
water mixing ratio used as a DSD mass moment, and `B_g = rho_d*brs` for the
graupel volume moment. Here `s` spans CCN, cloud, ice, and rain. `rho_m` is not
the candidate dry-moment density: substituting it into `rho_m*q_d` adds
`(1+qv)` to the paired mass moment. This map is conditional and has not been
installed.

| Source / consumer group | Active mp37 source behavior | Required treatment in a complete dry-state adapter |
| --- | --- | --- |
| Host boundary and return (`module_mp_kdm6.F:383–432`; driver `:2742–2760`) | `nci(1)=QNCLOUD`, `nci(2)=QNICE`, `nci(3)=QNCCN`, `nrs(1)=QNRAIN`; `nrs(2:3)=0`; `brs=QIB`. Copy-back is direct. | Convert all four incoming/outgoing prognostic numbers using the same explicit `rho_d` field. Keep `QIB` paired with `QG` under the declared volume-moment map if the chosen variant changes its DSD measure. Preserve zero snow/graupel prognostic-number semantics unless separately designed. |
| First-step CCN initialization (`module_mp_kdm6.F:309–333`) | The `itimestep==1` block overwrites `nn/QNCCN` with a vertical profile ending in `*1.e6`, i.e. a volume concentration expression, before physics. | A volume-kernel adapter may keep this internal concentration and divide by `rho_d` on return. A direct dry-state kernel must initialize in `# kg_d^-1`. Include the initializer in any QNCCN test and source receipt. |
| Number DSD closures and clamps (`:1550–1589`, `:1773–1812`, `:3255–3295`) | Rain/cloud/ice slopes use `N/(DEN*q)`; limiter rewrites assign `DEN*q*lambda**dm/pidn`. Rain/cloud/ice gates use raw `nrmin`, `ncmin`, maxima and q thresholds. | Pair volume `N` with the selected volume mass moment `rho_d*q_d` at every closure and rewrite. If number cutoffs mean physical `m^-3` limits, map each to stored coordinates as `N_min/rho_d`; do not assume the legacy numeric gates have that meaning. Keep q thresholds on their declared mixing-ratio coordinate. |
| Cloud number `nci(1)` sources/sinks (`:1400–1435`, `:1606–1644`, `:1870–1918`, `:2140–2215`, `:2800–2814`, `:3183–3220`) | Ice melt and freezing exchange cloud/ice number; warm autoconversion transfers cloud to rain; accretion/self-collection and cold collection consume cloud number; CCN activation supplies cloud number; complete cloud evaporation returns it to CCN. Process rates have source-specific caps and share a grouped cloud limiter. | Keep every source/arrival and sink/departure in the same representation; map source amounts, grouped limiter floors, and any state rewrite at the location where applied. The test covers only warm accretion's cloud-number sink. |
| Rain number `nrs(1)` sources/sinks (`:1387–1415`, `:1668–1675`, `:1875–1967`, `:2273–2331`, `:2805–2807`, `:3166–3167`) | Snow/graupel melt supplies rain number; autoconversion supplies rain number; rain self-collection, ice/snow/graupel collection and freezing consume it; complete evaporation or small-drop relabeling transfers rain number to CCN/cloud. A grouped rain limiter and `nrmin/nrmax` gates also apply. | Convert all rate amounts and all destination fields consistently, preserve the exact applied cap/floor order, and return all updated number reservoirs in stored basis. No single boundary factor validates the inner transfer budget. |
| Cloud-ice number `nci(2)` (`:1428–1431`, `:1523–1530`, `:1606–1644`, `:2065–2124`, `:2490–2525`, `:2587`, `:2811–2814`) | Homogeneous/instant melt and cloud freezing exchange ice/cloud counts; ice nucleation adds number; rain/snow/graupel collection and snow autoconversion consume it; complete sublimation can zero it. The grouped ice limiter has number floors and multiplicative rate scaling. | Carry mapped donor and recipient amounts through process-specific caps, the grouped limiter, and full-depletion paths. `Nid` is computed as a concentration (capped at `500e3 m^-3`) before comparison with internal ice number, so the dry-state variant must convert that source/floor too. |
| CCN number `nci(3)` (`:316–340`, `:1966–1967`, `:3183–3195`, `:3215–3220`, `:3288`) | First-step profile initialization; evaporated rain/cloud number returns to CCN; activation transfers CCN to cloud; a raw `[1e8,2e10]` clamp applies. | Convert initialization, every evaporation/activation transfer, and both clamp endpoints under the chosen number basis. CCN has no paired liquid/ice mass moment but still needs the same density-aware state conversion and unit contract. |
| Rain and ice sedimentation (`:1192–1230`, `:1280–1308`) | Rain/ice number departure is `N*workn/mstep`, with donor and dz-ratio arrival caps; number state updates omit `dend`. Mass uses `dend*q*work/dz` and divides by `dend` on update. Bottom export is an explicit number departure. | Derive the physical column measure and face amount for each number species, including unequal layer thickness, density differences, donor/receiver caps, bottom export, and substep rounding. Do not infer the dry-mass ledger from a `dz*N` replay or mass-path formula alone. |
| Post-process cleaning and derived outputs (`:848–862`, `:1686–1688`, `:3230–3295`, `:3785–3908`) | Entry clamps nonnegative number, bounds CCN and ice; final q-floor cleanup zeros companion numbers; DSD rewrites and maxima can replace numbers; derived terminal velocity, effective size, and radar paths consume numbers. | Apply the chosen number units before every comparison and rewrite, then confirm all downstream consumers see the intended internal basis. Diagnose-only fields remain outside the packed AD ABI. |

This inventory is a static source map, not a complete applied-number ledger. The
bounded S2 rain trace and S14 selected-column ledger give separate executed
evidence for a subset of rain sources and sedimentation transfers. They do not
cover the initializer, all species, all branches, host scalar transport, or
mp137.

## Variant interface and acceptance gates

A boundary adapter is the smaller conceptual variant, but it still needs a
versioned opt-in entry that receives `rho_d` with explicit provenance and
returns all number state in the declared host basis. Current fp64 ABI packs
12 state fields and only four forcings (`rho`, `pii`, `p`, `delz`); its JVP/VJP
buffers return state directions only. It therefore cannot advertise a live
`rho_d` direction. For a differentiable adapter, the JVP must include
`dN=rho_d*dn_d+n_d*d(rho_d)` and the VJP must return both
`rho_d*barN` and `n_d*barN`; this requires a separate forcing-gradient contract
or a clearly frozen-density scope.

Any eventual f32 variant needs a source-identified receipt, explicit dry-density
provenance, `-ffp-contract=off`, fixed multiply/divide placement, and captured
branch/cap/site ledgers. Legacy mp37 raw-bit comparison remains its own baseline;
between-variant changes are reported separately. S8's local normalized-ABI
evidence has since been recorded, but that evidence does not exercise the S2
number-basis conversion. This branch contains no S2
shadow build or retained-input control/capture, so native S2 conversion remains
absent. Until the density in DSD, meaning of each number threshold, complete
species transfers, and density-gradient contract are chosen, no full adapter
or corrected kernel is source-selected.
