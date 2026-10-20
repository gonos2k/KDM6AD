# Native restart-entry diagnostic consumers

The 120 s restart-entry history comparison remains different in seven fields:
`FOGFRAC_SFC`, `NOAHRES`, `REFL_10CM`, `RHO_ICE`, `VIS_SFC`,
`VIS_SFC_CAPPED`, and `VIS_SFC_RAW`. This is a history-diagnostic comparison,
separate from the complete checkpoint-state comparison. The private receipt is
`host/research_evidence/mp137_native_replay_20261020/VARIANT_VERIFICATION.json`;
the active private host tree cited below is absent from public clones.

| NetCDF name | Active Registry member / flags | Producer and known active-host readers |
|---|---|---|
| `FOGFRAC_SFC` | `fogfrac_sfc`, `h` (`Registry.EM_COMMON:2811`) | `module_diag_fogvis.F:573–601` computes the output; `module_diagnostics_driver.F:408–434` calls it only when `fogvis_opt != 0`. No later host read found. |
| `VIS_SFC` | `vis_sfc`, `h` (`:2808`) | `module_diag_fogvis.F:513–534` computes raw/capped visibility and writes this value. History output only in the searched active sources. |
| `VIS_SFC_RAW` | `vis_sfc_raw`, `h` (`:2809`) | `module_diag_fogvis.F:513–516` writes it before the visibility cap. No later host read found. |
| `VIS_SFC_CAPPED` | `vis_sfc_capped`, `h` (`Registry.EM_COMMON:2810`) | `module_diag_fogvis.F:514–516` sets the cap flag. No later host read found. |
| `NOAHRES` | `NOAHRES`, `h` (`Registry.EM_COMMON:1866`) | Noah computes the surface energy-balance residual in `module_sf_noahdrv.F:1341–1351`; `module_surface_driver.F:1163` declares the optional output. No later host read found. |
| `REFL_10CM` | `refl_10cm`, `hdu` (`Registry.EM_COMMON:1610`) | MP137 computes dBZ in `module_mp_kdm6ad.F:383–414`. Known diagnostic reads are the reflectivity reductions in `module_diag_nwp.F:372–376` and `module_diag_refl.F:73–77`; the driver can also copy the lowest model level to `refl_sfc` (`module_microphysics_driver.F:3344–3365`). These are radar/diagnostic outputs, not feedback into the KDM state transition. |
| `RHO_ICE` | `rhopo3d`, external name/description `rho_ice`, `hdu` (`Registry.EM_COMMON:1617`) | The MP137 driver passes `rhopo3d` as `diag_rhog` (`module_microphysics_driver.F:2755`); `module_mp_kdm6ad.F:342` copies `RHOG_OUT` into that output. No downstream read of the stored `rhopo3d` field was found in the active host search. This is distinct from a microphysics constant named `RHO_ICE`. |

The `h` and `hdu` flags do not mark these fields as restart state. Their entry-
history differences therefore do not establish a mismatch in the checkpoint's
prognostic state or in values required to continue the MP137 step. They remain
an explicit limit on complete history-field replay at that timestamp.

## Current AMI–RTTOV reader

The public frame reader selects pressure/geometry and the KDM state fields:
`QVAPOR`, `THM`, `P`, `PB`, `PH`, `PHB`, `XLAND`, `QNCCN`, `QCLOUD`,
`QRAIN`, `QICE`, `QSNOW`, `QGRAUP`, `QNCLOUD`, `QNICE`, and `QNRAIN`
([`frame_reader.py`](../oracle/kdm6/io/frame_reader.py:147)). The profile builder
emits layer T/Q, pressure grids, and optional cloud content/effective diameters;
it states that surface tensors are deferred
([`model_profile_builder.py`](../oracle/kdm6/obs/model_profile_builder.py:70),
[`model_profile_builder.py`](../oracle/kdm6/obs/model_profile_builder.py:313)).
The RTTOV input builder serializes only profile T/Q, pressure, and present cloud
slots ([`rttov_input_builder.py`](../oracle/kdm6/obs/rttov_input_builder.py:168),
[`rttov_input_builder.py`](../oracle/kdm6/obs/rttov_input_builder.py:183)).
The RTTOV operator's declared connected fields are T/Q for clear sky and T/Q,
cloud contents, and cloud number moments for all sky
([`rttov_obs_operator.py`](../oracle/kdm6/obs/rttov_obs_operator.py:41)).

None of these seven history diagnostics is directly read by that current AMI
profile/RTTOV path. The P0 observations can proceed without adding them to the
KDM AD ABI. A future fog/visibility or radar observation operator needs its own
explicit state, timing, units, and derivative contract; this source review does
not claim that every future backend or external consumer has been searched.
