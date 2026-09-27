# S2 fp64 dry-number AD boundary

The [opt-in C++ operator](REPORT_S2_cpp_dry_number_2026-09-28.md) keeps the
dry-number conversion inside its Torch graph. Existing fp64 C ABI entries did
not expose that choice. The additive `kdm6_step_ad_number_c` entry takes the
existing explicit physics variant plus a signed `dry_number` selector (0/1).
The old `kdm6_step_ad_c` and `kdm6_step_ad_variant_c` signatures and their
legacy-number behavior remain unchanged. The two variant-aware entries share
one internal implementation; `kdm6_step_ad_c` retains its existing body. The public
ISO_C_BINDING module adds a matching `kdm6_step_ad_number` wrapper. The C
export surface grows from 10 to 11 named symbols without leaking C++ symbols.

For selector 1, packed QN input/output blocks are number per kg dry air.
The forward graph converts them to volume number with entry
`rho_d = forcing.rho/(1+state.qv)` and converts the outputs back using that
same entry density. JVP/VJP are therefore derivatives in the caller's
dry-specific state coordinates, including the qv dependence of this mapping.
The four forcing blocks, including moist `rho`, remain fixed and are not
returned as gradients. Numeric number thresholds retain the experiment's
volume-concentration interpretation.

Focused local checks passed: `c_abi` and `fortran_normalized_ad` CTests,
the exact 11-symbol export checker and fresh-process KMP environment check.
The C test checks exact old-entry/new-selector-0 forward equality; a live
selector-1 graph with finite QN JVP/VJP, a `1e-10` duality bound and independent
central differences satisfying `|JVP-FD| <= 1e-4*max(1,|JVP|)`; invalid
negative/out-of-range selectors with untouched outputs and NULL handles; and
a finite conservative-interface composition. The Fortran test calls the new
symbol through the public wrapper, obtains a live handle and a finite JVP.
These are selected synthetic inputs, not meteorological native host calls.

The private mp337 DA probe and its private ISO mirror still use the earlier
fp64 symbol and do not select this dry-number mode. Branch-boundary
derivatives, forcing-density gradients, full native host AD routing, RTTOV
accuracy and accepted observation cost remain unapproved. S2 and S8 stay OPEN.
No release or deployment action is part of this change.
