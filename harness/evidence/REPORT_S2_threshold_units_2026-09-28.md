# S2 dry-number threshold interpretation

The opt-in dry-number boundary converts the host's four QN state fields from
number per kg dry air to internal volume number with entry
`rho_d = rho/(1+qv)`, and converts the four outputs back with the same density.
The kernel's existing `ncmin_land/sea` controls and hard-coded number gates,
floors and caps still apply their **unchanged numeric values** to that internal
volume-number state. The public C/Fortran ABI comments now state this executed
contract. No equation, selector, threshold value or operational default changed.

This choice is dimensionally coherent **if** the existing thresholds were
specified as number per cubic metre. It is not equivalent to treating their
numeric values as number per kg dry air. For example, at
`rho_d=0.2 kg_d/m^3`, a hypothetical specific threshold of `100 #/kg_d` maps
to `20 #/m^3`; applying the existing raw `100` in the volume kernel instead
gates at five times that volume concentration. The example is dimensional
arithmetic, not a new meteorological run.

The Registry declares host QN fields as `#/kg`, while the original kernel's
DSD and process equations consume number with a volume interpretation. The
source alone does not establish the intended units of every legacy threshold
or the calibration basis of empirical number-rate coefficients. If those
thresholds are intended to be specific, their cellwise `rho_d` transforms
must be carried through all NC/NR/NI/NCCN gates and caps together. Changing
one scalar or multiplying empirical coefficients blindly would leave an
inconsistent operator. This report records the current opt-in convention and
keeps the S2 physical-unit/threshold approval OPEN; it does not add a native,
RTTOV or observation experiment.
