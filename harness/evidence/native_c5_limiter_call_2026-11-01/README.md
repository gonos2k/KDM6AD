# Native C5 and ordered limiter capture

This packet extends the [same-call C3/C4/DSD evidence](../native_c3_c4_dsd_call_2026-11-01/README.md) at native column `(164,242)`, levels 21 and 23. It records C5's **actual consumed QI, NI, T, density, `supcol`, `dtcld`, parameter values and f32 π**, its unscaled `psaut/nsaut` output, and every selected-cell tensor operand read by the ordered conservation limiter. The diagnostic DSO preserves the prior historical physical archive except for the capture-enabled coordinator object. The 20 s, one-rank, one-thread native host run completed with capture off and on. Both endpoints and the historical baseline share SHA-256 `950bc5d67dc8cf4980091ecac19a9b7b1ba94756e83d9bd101180e55863c0bb6`.

The [selected packet](selected_packet.json) retains **312 raw-bit rows** for the second WRF tile's single substep at zero-based batch `22617`, tensor rows `20` and `22`, plus the relevant host `MP_INPUT/MP_OUTPUT` words, call metadata, build receipts, and full private-capture hashes. The [verifier](verify_packet.py) pins the packet, source and selected capture digests; checks the complete `(one_step_call,runtime_call,substep,B,K)` identity and dtypes; rechecks the original 172 C3/C4/DSD rows; and compares native host, ABI and final output bits. The full captures, executable, checkpoint and asset bytes are private and are attested by hashes rather than redistributed.

The [historical public sources](public_sources/) are checked against the run receipt as immutable evidence, distinct from the [compiled capture sources](executed_sources/). A later change to the live executed C++ source does not invalidate that historical source check. The separately pinned replay implementation and oracle files may still require a reviewed manifest update when they change. For each selected level, the verifier also compares the dtype and raw bits of C3/C5 `pre.supcol` and `forcing.dend`, which were read from unchanged shared tensors; inconsistent re-pinned records are rejected even when a C5 branch is idle.

The C5 oracle, supplied with the **directly captured C5 inputs**, reproduces both raw `psaut/nsaut` outputs at each level bit-for-bit. [The limiter replay](source_order_limiter.py) reads the full pre-limit input inventory and applies all 14 groups in executed C++ order. It reproduces every **captured selected cold-rate output** and the selected QI/NI state update in f64 bits. It does not compare every warm/MF/other cold output because those outputs were not captured. A rehashed change to an unused or inactive input can still round to, or produce, the same selected output; the pinned private capture records attest its execution source.

| Native level | Raw C5 `psaut` | Raw C5 `nsaut` | Final DSD NI change |
| ---: | ---: | ---: | --- |
| 21 | `0` | `0` | None |
| 23 | `1.0039141501525023e−9` | `0.8196165098184177` | None |

The limiter evaluates eight cold-arm and six warm-arm groups. The eight active cold-arm factors are **exactly 1** for the two baselines and every endpoint in the reported local perturbations; warm-arm groups are inactive. The verifier computes and reports each source, reservoir value, factor, binding decision and branch margin from captured inputs. Baseline selected outputs match the native capture; perturbed endpoints are Python replays, not new host executions. These results support the replayed selected-cell limiter branches for the **specified local input directions**. They do not establish global limiter inactivity.

Two local derivative maps are reported:

- **C5 + limiter + selected QI/NI update:** relative working-QI and working-NI directions, with every other producer rate frozen. At level 23 the working-QI direction yields `(dQIout,dNIout)=(+6.155909315749441e−7,−22.931211635055885)` per unit relative change.
- **Conditional C3 + full C4 + C5 + limiter + update:** the same working QI/NI values are shared by the three producers and limiter. At level 23 the working-NI direction yields `dQIout=−5.847242535010653e−7`; the NI tangent cancels to roughly one baseline-output ULP (`1.4551915228366852e−11` JVP, `0` VJP/FD). The branch-stable comparison uses a 16-output-ULP allowance only for near-zero cancellation signals.

Both maps require baseline raw-bit equality, componentwise JVP/VJP checks and three finite differences divided by the **represented** input interval. The C5-only map records C5 and limiter branches. The combined map additionally records C3/C4 gates and cap winners. Both check all 14 limiter decisions and margins and output floor status at center and endpoints. The exact-zero C4 snow and graupel reservoirs are held fixed and checked unchanged in the combined map; their tied activation gates are excluded only from the QI/NI-direction tie test. No derivative with respect to those reservoirs is claimed. The combined map uses source-pinned C3/C4 oracle defaults that were not separately captured, while C5 parameters were captured directly.

These are conditional local derivatives: post-freeze intercepts, slopes, other producer rates and upstream forcing are fixed, and the host does not execute an AD pass. QNICE's physical unit basis, a full mass/number budget, an end-to-end host JVP/VJP and RTTOV effects remain separate. **`scientific_status: INCONCLUSIVE`**.

An additional [ice auxiliary replay](ice_auxiliary_ad.py) authenticates the packet once with the common verifier, then reuses those same parsed bytes for both levels. It recomputes `n0i` and `rslope2_i` from the captured post-freeze QI, NI and density, then passes both through C4, the sequential limiter and the selected QI/NI update. The C4 branch audit now uses the same auxiliary tensors as the calculation and records the raw rate, cap margin, selected rate and winner at the center and both endpoints. The two baseline auxiliaries and final states match captured f64 bits. Relative QI and NI directions keep the ice slope strictly within `9080..1.82e6`, preserve untied C3/C4/C5/limiter branches at both represented endpoints, and compare JVP, VJP and centered differences. At level 23, the additional 20 s QI sensitivities through these auxiliaries are `+7.237213036e−8` (QI direction) and `+1.447442543e−7` (NI direction), agreeing with the independent `a·dt·pidep` and `(1−a)·dt·pidep` expressions for `a=float32(1/3)`. This is conditional on the captured smooth, inactive number-rewrite branch and fixed density/other producers; it does not replay upstream slope production across a rewrite or provide a host derivative.

```bash
python3 -m harness.evidence.native_c5_limiter_call_2026-11-01.verify_packet \
  harness/evidence/native_c5_limiter_call_2026-11-01/selected_packet.json \
  --sha256 cb73fc3c6c2b30c080bde622b88db097e933e7ea88e56d2b9583a46f394d33ba
python3 -m harness.evidence.native_c5_limiter_call_2026-11-01.combined_replay \
  harness/evidence/native_c5_limiter_call_2026-11-01/selected_packet.json \
  --sha256 cb73fc3c6c2b30c080bde622b88db097e933e7ea88e56d2b9583a46f394d33ba
python3 -m unittest discover -s harness/evidence/native_c5_limiter_call_2026-11-01 -v
python3 -m harness.evidence.native_c5_limiter_call_2026-11-01.ice_auxiliary_ad \
  harness/evidence/native_c5_limiter_call_2026-11-01/selected_packet.json \
  --sha256 cb73fc3c6c2b30c080bde622b88db097e933e7ea88e56d2b9583a46f394d33ba
```

The packet includes review snapshots of the executed coordinator, private runner and exporter. Replaying the private host step requires the pinned omitted inputs and executable. The selected-packet digest is co-versioned; the reviewed Git commit is the content identity anchor.
