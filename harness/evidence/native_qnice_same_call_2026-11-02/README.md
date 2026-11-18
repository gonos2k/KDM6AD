# QNICE coordinate boundary at the captured native call

This offline replay authenticates the existing [312-row C5 packet](../native_c5_limiter_call_2026-11-01/README.md) before reading either selected level. It checks the host `MP_INPUT` NI, DEN and QI f32 words against the C ABI ingress, the exact f32-to-f64 widening of NI, DEN and QV at converted ingress, and the f32 writeback of final NI. The host trace contains Q but the ABI capture did not separately record Q; the QV check is host-to-converted-ingress, with the public packing source as the intervening link. The verified raw packet is read once. The parent verifier runs Python C5/limiter process and derivative replays; this analysis performs no new native host, compiled KDM runtime or RTTOV execution.

| Native level | Host QV | Host DEN | Host NI | Host NI × DEN, conditional `#/m³` | Host NI × DEN/(1+QV), generic v2 candidate |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 21 | `0.0013171497266739607` | `0.49126261472702026` | `0.1376752108335495` | `0.06763468405718331` | `0.06754571623550572` |
| 23 | `0.0006171652930788696` | `0.41745808720588684` | `116719.8203125` | `48725.63292667107` | `48695.57970495081` |

The two right columns are **counterfactual binary64 coordinate calculations on the captured, f32-widened ingress numbers**. The selected run consumed raw NI and DEN; neither dry-number conversion was executed. These columns do not claim binary32 bit parity with an executed v2 option. The generic v2 multiplier is smaller than DEN by about 0.1315% at level 21 and 0.0617% at level 23. The comparison does not determine which physical unit the historical QNICE payload actually had, nor does it predict an alternative kernel output. The generic v2 option also replaces the coordinator's `dend` with its derived density, so its effect cannot be represented by NI multiplication alone.

## Source boundary and provenance

The active private host source currently labels QNICE `# kg-1` in `Registry/Registry.EM_COMMON:536`. In its call chain, `dyn_em/solve_em.F:3663–3664` runs `moist_physics_prep_em`, whose active body at `dyn_em/module_big_step_utilities_em.F:5542` assigns `rho=1/(AL+ALB)` before `solve_em.F:3727` passes that rho into `module_microphysics_driver.F:2894–2899` as DEN for mp137 (and `2752–2755` for mp37). `phys/module_mp_kdm6ad.F:245,248,339` copies NI and DEN into and NI out of the legacy C ABI without a density conversion. The mp37 wrapper likewise copies the raw NI. These are **source-level findings from the current canonical private tree**, not an attestation that the historical captured executable was compiled from those exact files.

The reviewed private source SHA-256 values are:

| Active private file under `host/KIM-meso_v1.0/` | SHA-256 |
| --- | --- |
| `Registry/Registry.EM_COMMON` | `6741720cba12ad7ee1c172339bd8def5973b22f4e88ab9cd152f3ba3df456e37` |
| `dyn_em/solve_em.F` | `d66e9db1bba8f37e3f46d30c2fd74bdf8def411adf233376a69e0b401c6d3d1f` |
| `dyn_em/module_big_step_utilities_em.F` | `27ce690b27b24c80247a5551b48d37fc32fc47470d806cbef1bb859d58edc31c` |
| `phys/module_microphysics_driver.F` | `94db84c45b7422b62e04967cb3cd1362311abdb02fa3d374d881799c0bce7e84` |
| `phys/module_mp_kdm6ad.F` | `c56499524c73bec4e5092e7aecfde244d072f9572733708226c7f6d743cc9e67` |
| `phys/module_mp_kdm6.F` | `fc0a72d33a5e61803fea56eb9118018039c6da8b5775813032b4861a2bd66eb5` |

The public v2 C ABI's `dry_number=1` path is explicit and value-only. In [runtime.cpp](../../../libtorch/src/runtime.cpp), it computes `rho_dry=forcing.rho/(1+state.qv)`, multiplies the four number fields by that value, sets `cf.dend=rho_dry`, and divides output numbers by the **entry** value. If the active host's DEN is already dry as the source path above indicates, simply passing that DEN into v2 would divide it by `(1+QV)` again. Supplying a synthetic moist density to compensate would also change the physical forcing passed to the kernel. Neither operation is an approved native fix.

The already implemented [native dry-number research boundary](../../../docs/NATIVE_DRY_NUMBER_BOUNDARY.md) instead uses `rho_d=DEN`, leaves physical forcing unchanged, and includes entry and exit JVP/VJP terms. It explicitly defines a new research coordinate pulled back from captured kernel-volume operands; it does **not** certify the original host payload's unit or change operational mp137. This packet does not duplicate that implementation.

## Remaining evidence

The C5 packet has QV and DEN at the selected call but no same-call AL/ALB values, no ABI Q word, and no origin-to-restart QNICE producer ledger. The current private source hashes above are not bound to the historical executable's build receipt. A further native trace must bind AL, ALB, QV, DEN and QNICE at the microphysics call, plus source/build identity and the producer or restart path of QNICE. A physical number budget must include applied generation, removal and sedimentation amounts in a declared coordinate. Until then, `physical_unit_status: INCONCLUSIVE`.

```bash
python -m harness.evidence.native_qnice_same_call_2026-11-02.replay
python -m unittest discover -s harness/evidence/native_qnice_same_call_2026-11-02 -v
```
