---
title: Host-column FD step selection and future receipt bridge
type: source
date: 2026-11-12
---

# Host-column FD step selection and future receipt bridge

The [gate and receipt report](../../docs/NATIVE_HOST_GATE_RECEIPT_BRIDGE_20261112.md) resolves a false-negative path in the [[native-host-capture-preflight-2026-11-12|SPEC_ONLY preflight]]: the two smallest planned step sizes determine local numerical classification, while larger diagnostic steps retain their observed branch crossings without vetoing those two. Canonical upper PII synthetic regression distinguishes a `10⁻⁴` diagnostic crossing from consistent `10⁻⁵` and `10⁻⁶` steps; a selected-step mismatch or unresolved signal still prevents local consistency. This does not establish a real PII derivative.

Future source-only validators bind all 100 planned call slots, 624-word input and 468-word output assets, source/DSO hash claims, nominal JVP/VJP seed bytes and **21 represented per-step JVP seed/output payloads**, full record identities, seven field groups, same-call/layer/substep false-mask absence reasons, and the synthetic budget scheduler's call/path/digest envelope. Their checks are internal consistency on submitted bytes. The scheduler only runs a SHA-pinned fixed test stub in explicit synthetic mode and is production-blocked for the current `SPEC_ONLY` plan. Effective **intermediate** tangents and independent execution provenance remain unverified, so `fd_gate_ready=false` and both numeric and receipt results stay `NOT_ELIGIBLE`. No new native model call or physical budget was performed; scientific and physical-unit statuses remain `INCONCLUSIVE`.
