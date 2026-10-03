# PR #361 review follow-up

Baseline: `94fdaf5929e43375d63fff7c8b92657227b72d7e`.
Keep NCCN arithmetic, 17-digit output, operational defaults and existing gates fixed.
No release/deployment or new general-purpose specification framework.

- [x] Report solver BT/NC differences on the same seven quality-supported
  channels, with declared normalization and weak-channel absolute errors.
  DOM32 is the highest installed-table-supported **numerical reference**;
  observed cost does not select it. Physical tolerance/accuracy approval is OPEN.
- [x] Define and implement an explicit same-entry density map for a single
  fp64 dry-number KDM call followed by optics. Preserve frozen-background
  density as the default; do not infer entry density from output humidity.
- [x] Execute the composed Python KDM→optics→actual RTTOV map in an entry-qv
  direction, including the live density tangent, JVP/VJP and independent FD.
  Two fixed chronological native inputs at the same prior-selected coordinate
  pass the bounded gates. No native C ABI or DAWindow integration is claimed.
- [x] Repeat on the next retained input state, fixed before its outputs.
  The 40-second frame uses its own state, forcing, surface and native pressure
  interfaces; failures are retained and no easier replacement was selected.
- [ ] Establish original land/sea 100/10 threshold units and empirical calibration.
  Registry units remain blank; the owner clarification is pending. Kernel-volume
  conventions and dimensional algebra are documented, not calibration evidence.
- [ ] Approve physical solver/optical accuracy and observational error policy.
  Current solver differences and one-/two-state numerical checks cannot provide
  a physical error budget or certify full assimilation accuracy.

[Implementation and actual evidence](REPORT_shared_entry_density_2026-10-03.md)
keeps state-input sensitivity separate from named-process attribution, native
host execution, full DA controls, observation-cost approval and forecast skill.
