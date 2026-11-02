---
title: Synthetic QNICE applied replay and transfer mismatch — 2026-11-02
type: source
date: 2026-11-02
---
# Synthetic QNICE applied replay and transfer mismatch

The public Python ice substep can record detached NI operands and applied
amounts without changing forward output bits. A versioned synthetic packet
replays the top and interior stores in the recorded f32 or f64 dtype. It
separately reports state replay residual, interface departure–arrival
difference, and `dz`-weighted column change.

In the two-layer capped example, upper NI `10` loses `8` while the lower layer
receives `2`. The state update replays exactly and its arithmetic closure is
zero, but the interface difference is `6` and the column changes by `−6`.
The top-floor example records a scheduled debit of `20`, correction `+10`
and realized loss `10`. A large f32 fall accumulator can have zero recorded
increment while a nonzero fall rate and candidate amount remain.

The replay derives a synthetic fall rate from the supplied normalized speed
and checks candidate, applied, projection and accumulator words. It uses the
executed source order, including f32 conversion of scalar `dtcld`, and
requires identity, geometry and substep continuity. The `NI×dz` measure is a
numerical-coordinate diagnostic. This is **not** a native C++ capture, a
physical particle budget, or QNICE unit certification.

See [synthetic packet and replay](../../harness/evidence/native_qnice_applied_schema_2026-11-02/README.md)
and [native capture contract](../../docs/NATIVE_QNICE_APPLIED_CAPTURE_CONTRACT_20261102.md).
