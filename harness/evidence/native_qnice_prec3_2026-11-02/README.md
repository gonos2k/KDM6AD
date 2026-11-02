# Native NI intervals before C3 and saved endpoint density

This offline packet starts from the independently pinned [native C5 same-call packet](../native_c5_limiter_call_2026-11-01/README.md). Its [replay](replay.py) invokes that packet's full verifier on the original bytes before reading the selected ingress, post-sedimentation step entry, C3 input and final DSD output. The three intervals below are **net differences in the kernel's recorded numerical NI coordinate**, not a physical particle budget or process attribution.

| Native level | Ingress NI | Post-sedimentation step-entry NI | C3-input NI | Final DSD NI | Ingress→step net | C3→final net |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 21 | `0.1376752108335495` | `40.72736922974132` | `40.72736922974132` | `40.72736922974132` | `+40.58969401890777` | `0` |
| 23 | `116719.8203125` | `116548.15443662195` | `116548.15443662195` | `119786.63415268344` | `−171.66587587805407` | `+3238.479716061498` |

Step entry and C3 input match in f64 bits at both selected cells. That does **not** prove the intervening D1 melt, homogeneous/D2–D4 freezing, slope limits or dtype conversions were all inactive: their effects may be zero at the selected endpoints or cancel. The ingress→step interval contains sedimentation, its intermediate resloping, and dtype operations. Two selected levels cannot explain neighbor inflow, top/bottom outflow or a full-column number budget.

The [private exporter](export_private_endpoint.py) read the retained `00:01:00` NetCDF endpoint **only after its full file SHA-256 matched** `950bc5d67dc8cf4980091ecac19a9b7b1ba94756e83d9bd101180e55863c0bb6`, checked the field dimensions and saved `Times` word, disabled automatic scaling/masking, and checked the file hash again afterward. The public [selected f32 words](endpoint_density_words.json) have independent SHA-256 `84c5c44ccac4980697dfccd1e971f10c7799b3194302490d551d509f35e4e631`. For both cells, f32 source-order `1/(AL+ALB)` equals the endpoint RHO word, and endpoint RHO equals the **earlier** host `MP_INPUT.DEN` word. Endpoint QNICE equals `MP_OUTPUT.NI`; endpoint QV differs from input Q at both levels. These are cross-time observations. The active host calls `calc_p_rho_phi` after microphysics, so saved AL·ALB cannot stand in for **same-call** AL·ALB, even when the later RHO word agrees.

The needed next capture is an isolated, source/build-pinned run. At the `moist_physics_prep_em` assignment and the selected mp137 call it must record native `(i,j,k)`, time, tile/rank/call, AL, ALB, RHO/DEN, QV and QNICE f32 words. It must bind the instrumented host source and objects to the actual executable and DSO, then compare capture-off/on endpoints. To explain pre-C3 NI changes, capture full-column pre/post sedimentation with applied departure/arrival, top/bottom fluxes and density/layer geometry, and the ordered NI updates and number rewrites between step entry and C3. Equal sparse endpoints alone are insufficient. The original QNICE producer/restart history remains separate.

No new host, compiled C++/Fortran or RTTOV execution was performed here. The parent verifier **does** run local Python C5/limiter and derivative replays. Private endpoint bytes are not redistributed; the extraction and source hash are attestations with an auditable selection recipe. `physical_unit_status: INCONCLUSIVE`.

```bash
python -m harness.evidence.native_qnice_prec3_2026-11-02.replay
python -m unittest discover -s harness/evidence/native_qnice_prec3_2026-11-02 -v
```
