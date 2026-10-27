# Saved QNC one-ULP donor-scale probe — 2026-10-27

This packet is an **offline counterfactual** on the immutable PR461 control and alpha0.25 traces. It does not patch or run the host limiter. The prior PR461 packet and PR462 state-budget companion are hash-bound inputs; their historical source pins remain separate from this analyzer's source pins.

The original `advect_scalar_pd` outgoing branch was taken at native `(i,j,k)=(221,63,6)` in both runs; the six recorded neighbors did not take that branch. The probe replaces the target donor scale with its immediately lower positive binary32 value. It recomputes the six outgoing correction faces from their saved pre-limiter words and installs each result at **both cells sharing that face**. In alpha0.25, five face words change; `FX_EAST` rounds to its original word. Low-order faces, PD input, source, metrics and all other faces are held fixed.

| Saved-input probe | Control | Alpha0.25 |
| --- | ---: | ---: |
| Original scale word | `3F4C9A4E` | `3F4C9A3C` |
| One-ULP-lower scale word | `3F4C9A4D` | `3F4C9A3B` |
| Original exact RK3 QNC using stored PD old buffer | +0.285426801 | −1.838040504 |
| Counterfactual exact RK3 QNC using stored PD old buffer | +5.211649186 | **+1.648786290** |
| Counterfactual RK3 QNC with arithmetic modes matching the saved run | +10.699481010 | **+1.991152167** |

The replay first reconstructs the original `PH_LOW` and `FLUX_OUT`, confirms target and neighbor limiter branches and scales from those operands, and checks the original correction and low-order faces. It requires the non-`tenddec` final RK path. Each axis mode and ordinary RK3 mode must reproduce the original saved values before that same source-compatible mode is carried through the modified shared faces. There are four direction-mode combinations in control and two in alpha0.25 that are compatible across **all seven cells**; the common RK mode is the FMA candidate. All seven tested cells have nonnegative RK3 QNC even when every individually compatible mode is included. The exact seven-cell operator-weighted face total is unchanged: the six modified faces are internal to the selected star, and both incidences use identical bits. This is a **local saved-input result**, not a whole-domain positivity or physical conservation certificate.

From the repository root:

```sh
python3 -m harness.evidence.native_qnc_scale_backoff_2026-10-27.replay
```

The replay verifies the historical packet assets and new source pins, then reproduces [analysis.json](analysis.json) byte for byte. Its host, KDM6, RTTOV and optimizer call counts are zero. A general limiter rule still needs an applied-flux budget, nonnegative states across the actual domain/tile/halo path, unchanged shared-face consumption, trace-off/on comparison within the new variant, and a full-host fixed-support RTTOV evaluation. The legacy raw NC physical unit remains unverified. This single witness does not justify changing operational defaults or relaxing forward parity.
