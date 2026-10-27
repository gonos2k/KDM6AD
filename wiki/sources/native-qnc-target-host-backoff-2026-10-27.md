---
title: Native QNC target backoff full-host result — 2026-10-27
type: source
date: 2026-10-27
---
# Native QNC target backoff full-host result

An isolated full-domain MP137 variant applies one lower binary32 limiter-scale word only to target QNC/RK3 at native `(221,63,6)`. Four actual 20-second steps compare control and historical alpha0.25 with tracing off/on. Both same-input off/on checkpoints agree over 652 variables and 322,426,586 numeric elements. The variant changes `module_advect_em.o` only; operational KDM, ABI and nonadiabatic forward settings remain fixed. A source-pinned mask producer rerun on three private checkpoint hashes reproduces the public full-domain hard-admission masks byte for byte.

Immediate RK3 NC matches [[native-qnc-scale-backoff-2026-10-27]]: `+10.699481010` control and `+1.991152167` alpha. KDM output amplifies the control to `+277,381.21875` but retains alpha at `+1.991152167`. Relative to historical same-input checkpoints, only target `QNCLOUD` and forward `RE_CLOUD` differ. The alpha target's QC-positive/NC-zero mismatch is repaired, yet 54 other fixed-support profiles (378 channel cells) remain invalid. No full-domain candidate cost or accepted update exists.

Two direct-only RTTOV calls on the original B512 block 28 retain its 2,009 fixed-support cells. Target IR105 simulated-minus-observed BT falls from `+11.445589991` to `+11.119604505 K`; block RMSE falls `24.476204946 → 24.474283624 K`. Target RTTOV liquid Deff changes `52 → 5.02 μm` across the `ncmin=10` inactive slope gate: the observation adapter passes raw NC divided by live dry density, and the dry-number bridge multiplies by that same density before this numerical comparison. This is a local finite response at model 00:01 against nominal observation 00:00; pixel UTC, physical raw-NC units, a general limiter rule and second assimilation remain open.

See [report](../../docs/NATIVE_QNC_TARGET_HOST_BACKOFF_20261027.md), [source/build boundary](../../harness/evidence/native_qnc_host_backoff_2026-10-27/SOURCE_RESOLUTION.md) and [replay packet](../../harness/evidence/native_qnc_host_backoff_2026-10-27/README.md).
